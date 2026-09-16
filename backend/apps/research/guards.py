"""D10, enforced at the cursor rather than promised in a docstring.

§10 Phase 11: "All commands here run against the research DB (D8) and never
write operational tables (D10)", and its acceptance asks for "zero writes to
operational tables (asserted)". There are three ways to satisfy that sentence
and only one of them survives the next person to edit the command.

*Reviewing the code* satisfies it for today's code. *Counting rows after a
test run* satisfies it for the paths the test happened to take — and a corpus
run's interesting paths are the failure ones, which a happy-path test does not
visit. This module satisfies it for every statement the command actually
issues, including the ones nobody wrote by hand: a cascade, a `bulk_create`, a
lazily-saved related object, a `get_or_create` reached through three frames of
library code.

It hooks `connection.execute_wrapper`, which is below the ORM rather than
beside it. Signals were the obvious alternative and are not enough on their
own: `bulk_create` and `queryset.update()` send no `pre_save`, and those are
precisely the shapes a scan writer reaches for. SQL is what everything becomes.

**Deny by default.** The allowlist is the three permanent tables (§5.1, D9),
and anything else writing is refused — including tables that do not exist yet.
An allowlist that named the operational tables would silently admit the next
one added.

The guard raises rather than logs. A corpus run that wrote a `scan_runs` row
has already violated D8's separation by the time anyone reads a log line, and
on the teammate's machine it would be writing into the *research* database —
producing an operational row in the one place nothing is ever meant to read
operational rows from.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection

#: §5.1's permanent tables — the only ones any command in this app may write
#: (D9, D10). `agent_execution_traces` is here for Phase 13's runner, which
#: writes traces from the research side under the same rule.
RESEARCH_TABLES: frozenset[str] = frozenset(
    {"scan_history", "dependency_history", "agent_execution_traces"}
)

#: The leading verb and its target table. Postgres and SQLite both quote
#: identifiers, and Django always quotes them, so the quote characters are
#: optional in the pattern only to keep a hand-written statement readable.
_WRITE = re.compile(
    r"""^\s*
        (?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?)
        \s+
        [`"\[]?(?P<table>[A-Za-z_][A-Za-z0-9_$]*)
    """,
    re.IGNORECASE | re.VERBOSE,
)


class OperationalWriteRefused(Exception):
    """A research command tried to write a table outside §5.1's permanent set.

    Carries the statement's verb and table rather than the whole SQL: the
    parameters of a refused write can hold repository content, and this
    exception's text reaches a terminal and a log (§9.5).
    """

    def __init__(self, table: str, statement: str) -> None:
        self.table = table
        super().__init__(
            f"D10: refusing to write the operational table {table!r} from a "
            f"research command ({statement}). Only {', '.join(sorted(RESEARCH_TABLES))} "
            f"may be written here."
        )


def _verb(sql: str) -> str:
    return sql.strip().split(None, 1)[0].upper() if sql.strip() else "?"


def check_statement(sql: str) -> None:
    """Raise if `sql` writes anything outside `RESEARCH_TABLES`.

    Reads are not examined at all. A corpus command reads whatever it likes —
    the weights registry lives in a file, but a future one may well want to
    look at an operational row, and D10 is about writes.
    """
    match = _WRITE.match(sql)
    if match is None:
        # Not a write: SELECT, SAVEPOINT, RELEASE, SET, BEGIN, PRAGMA.
        return
    table = match.group("table")
    if table.lower() not in RESEARCH_TABLES:
        raise OperationalWriteRefused(table, _verb(sql))


@contextmanager
def no_operational_writes() -> Iterator[None]:
    """Refuse every write to a table outside §5.1's permanent three.

    Wrap the whole of a research command's work, not just its persistence
    step: the point is to catch the write nobody intended, and an unintended
    write is by definition not inside the block someone thought to guard.
    """

    def wrapper(execute, sql, params, many, context):
        check_statement(sql)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(wrapper):
        yield
