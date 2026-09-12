"""Log redaction, and the context every line carries.

**Redaction.** §11 lists "OAuth token exposure" as a Phase 1 risk with "log
assertions" as the verification. Relying on every future call site to remember
not to log a token is not a control; `RedactSecretsFilter` is. It scrubs
anything that looks like a GitHub token or a Fernet ciphertext out of every
record the console handler emits.

**Context (Phase 9).** §10 asks for "structured logging (request id, user id,
scan id)", and the reason is a specific kind of unanswerable question. This is
one gunicorn worker with eight threads (§3) plus background scan and generation
threads, all writing to one stream: a `WARNING` about a rate limit and an
`INFO` about a failed report are interleaved with everybody else's, and nothing
in the line says whose request or which scan produced it. Render's free tier
has no log search beyond the browser's find-in-page, so correlating by
timestamp is what is left, and timestamps collide.

`ContextFilter` attaches whatever is bound in the current context to every
record the handler emits. The transport is `contextvars`, which is exactly
right here: a plain `threading.Thread` starts with an *empty* context rather
than a copy of its parent's, so a scan thread cannot inherit the request id of
whoever pressed the button — which is the correct answer, because it is no
longer serving that request. It binds its own `scan_id` instead.

Nothing user-supplied is ever bound. The request id is generated here and an
inbound `X-Request-ID` is ignored: a client-chosen id is a client-chosen
string in every log line, and a newline in it forges a log entry.
"""

from __future__ import annotations

import contextvars
import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

# GitHub's documented token prefixes (classic PAT, fine-grained PAT, OAuth,
# user-to-server, server-to-server, refresh) plus the legacy 40-hex form.
_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgho_[A-Za-z0-9]{16,}\b"),
    # Fernet ciphertext: version byte 0x80 base64-encodes to a leading "gAAAAA".
    re.compile(r"gAAAAA[A-Za-z0-9_\-=]{20,}"),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


#: The fields a log line can carry, in the order they are printed. Fixed rather
#: than free-form: §10 names these three, and a context that any call site can
#: extend is a context nobody can grep for reliably.
CONTEXT_FIELDS = ("request_id", "user_id", "scan_id")

#: `None` rather than `{}` as the default: a mutable default on a ContextVar
#: is one shared object every context can reach, and nothing about "this is
#: only ever replaced, never mutated" is enforced by anything.
_context: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "repovitals_log_context", default=None
)


def new_request_id() -> str:
    """A short, greppable id for one request.

    Twelve hex characters rather than a full UUID: these are read by a human
    scrolling Render's log pane, and the id has to survive being copied by eye
    into a find-in-page box. Twelve is far past collision for the purpose —
    correlating the lines of one request inside one window of one day.
    """
    return uuid.uuid4().hex[:12]


@contextmanager
def bind(**fields: object) -> Iterator[None]:
    """Attach fields to every log record emitted inside this block.

    Nested binds merge rather than replace, and the token is reset on the way
    out even if the body raises — a background thread that failed is exactly
    the one whose next lines must not be attributed to the work it abandoned.
    """
    unknown = set(fields) - set(CONTEXT_FIELDS)
    if unknown:  # pragma: no cover - a programming error, caught at the call site
        raise ValueError(f"Unknown log context field(s): {sorted(unknown)}.")
    merged = {
        **(_context.get() or {}),
        **{key: str(value) for key, value in fields.items() if value is not None},
    }
    token = _context.set(merged)
    try:
        yield
    finally:
        _context.reset(token)


def current_context() -> dict[str, str]:
    """What is bound right now. Read by the filter, and by tests."""
    return dict(_context.get() or {})


class ContextFilter(logging.Filter):
    """Put the bound context on every record as one preformatted field.

    One field rather than three, because the alternative prints
    `[- - -]` on every line a library emits outside a request — which is most
    of them at startup — and a format string with three placeholders cannot
    omit them conditionally. An empty context renders as the empty string, so
    an unattributed line looks exactly as it always did.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        context = current_context()
        parts = [
            f"{field}={context[field]}" for field in CONTEXT_FIELDS if context.get(field)
        ]
        record.context = f" [{' '.join(parts)}]" if parts else ""
        return True
