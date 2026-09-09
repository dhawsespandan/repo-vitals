"""§5.8's report payload, and the rule that keeps it honest.

Two checks run over every generation, and they answer different questions.

**Is it the right shape?** Pydantic against §5.8. An LLM answer is untrusted
input like any other, and JSON mode guarantees only that the document parses —
not that `fixes` is a list, that `priority` is a number, or that `fix_type` is
one of the four §5.8 names. A schema violation buys one repair retry (§10
Phase 7); the second failure fails the generation.

**Does it describe something we actually scanned?** §10 Phase 7's acceptance:
"every fix references a real scanned row (validator cross-checks)". A fix is
matched against the rows the prompt was built from, on the identity triple
(ecosystem, package, manifest_path). An unmatched fix is a package this
repository does not have, in a file that may not exist — the most damaging
thing this surface could print, because it reads exactly like the ones that are
real.

From the match comes the rule that shapes the whole module:

    **The model is never the source of a fact we already measured.**

`current_version`, `cves` and `severity` are copied from the matched scan row,
not from the answer. The model decides what to *do* — upgrade or replace, to
what, in what order — and the report states measurements only where a stored
signal put them. This is the same principle as §5.1's raw/derived split and
Phase 5's recomputed breakdown: one source of truth per number. It also removes
a whole class of on-screen wrongness that no amount of prompting prevents, and
it lets the prompt ask for seven fields instead of ten.

The emitted payload is still exactly §5.8's — the fields the model did not
supply are filled here, so a download and a database row conform to the spec
whatever the model chose to include.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

FixType = Literal["upgrade", "replace", "remove", "investigate"]
EcosystemName = Literal["npm", "pypi"]

#: A summary longer than this is not a triage summary. The cap is applied after
#: validation rather than as a schema bound so that an over-long answer is
#: trimmed rather than thrown away — the first paragraphs are the useful part,
#: and failing the whole generation over length would spend a second call to
#: get back something we already had.
MAX_SUMMARY_CHARS = 4000

#: How many fixes a report may carry. The scan rows sent are already capped
#: (see `combined.py`), so this bounds the page rather than the prompt.
MAX_FIXES = 30


class GeneratedFix(BaseModel):
    """What the model is asked for: the decision, not the measurements."""

    # Unknown keys are dropped rather than rejected. A model that helpfully
    # echoes `current_version` back should not fail a generation over it — and
    # the echo is discarded either way, because the scan row is authoritative.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    package: str = Field(min_length=1, max_length=214)
    manifest_path: str = Field(min_length=1, max_length=500)
    ecosystem: EcosystemName
    fix_type: FixType
    target_version: str | None = Field(default=None, max_length=100)
    replacement_package: str | None = Field(default=None, max_length=214)
    priority: int = Field(ge=1, le=999)


class GeneratedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary_md: str = Field(min_length=1)
    fixes: list[GeneratedFix] = Field(default_factory=list)


class PayloadInvalid(Exception):
    """The answer did not satisfy §5.8. Carries text the repair retry can use."""

    def __init__(self, message: str, detail: str) -> None:
        super().__init__(message)
        #: A short, model-readable account of what was wrong, fed back verbatim
        #: on the repair attempt. Written as instructions to fix, not as a
        #: stack trace: a validation error printed at a model is noise.
        self.detail = detail


def parse(raw: dict) -> GeneratedPayload:
    """The shape check on its own. Raises `PayloadInvalid`, never pydantic's.

    Separated from the cross-check because the two failures are answered
    differently: an invented package can be dropped, a malformed document
    cannot. Both callers go through here so that *every* schema violation
    leaves this module wearing this project's exception type — the first
    version let pydantic's own escape `drop_unmatched`, past a caller that was
    only catching `PayloadInvalid`.
    """
    try:
        return GeneratedPayload.model_validate(raw)
    except ValidationError as exc:
        raise PayloadInvalid(
            "The generated report did not match the required schema.",
            _repair_hint(exc),
        ) from exc


def validate_payload(raw: dict, rows: list[dict]) -> dict:
    """Return the §5.8 payload, or raise `PayloadInvalid`.

    `rows` is what the prompt was built from — the scanned occurrences, each
    already carrying the measurements this function copies across.
    """
    parsed = parse(raw)

    index = {
        _key(row["ecosystem"], row["package"], row["manifest_path"]): row for row in rows
    }

    kept: list[dict] = []
    unmatched: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for fix in parsed.fixes[:MAX_FIXES]:
        key = _key(fix.ecosystem, fix.package, fix.manifest_path)
        row = index.get(key)
        if row is None:
            unmatched.append(f"{fix.package} in {fix.manifest_path} ({fix.ecosystem})")
            continue
        if key in seen:
            # Two fixes for one occurrence is not two pieces of advice, it is
            # one contradicted. The first is kept: the model ordered its own
            # answer, and re-ranking below preserves that order.
            continue
        seen.add(key)
        kept.append(_merge(fix, row))

    if unmatched:
        raise PayloadInvalid(
            "The generated report named dependencies this scan did not find.",
            "These entries name dependencies that are not in the data you were "
            "given, so they were rejected: "
            + "; ".join(unmatched[:10])
            + ". Every fix must copy `package`, `manifest_path` and `ecosystem` "
            "verbatim from one of the dependency rows in the input.",
        )

    return {
        "summary_md": parsed.summary_md.strip()[:MAX_SUMMARY_CHARS],
        "fixes": _rank(kept),
    }


def drop_unmatched(raw: dict, rows: list[dict]) -> dict:
    """Validate, keeping only the fixes that match a scanned row.

    The second half of the repair policy. A model that still invents rows after
    being told exactly which ones it invented is not going to be talked round
    by a third attempt, so the invented entries are dropped and the rest is
    kept: a shorter list of real dependencies is a better answer than a
    plausible list containing packages this repository does not have.

    Schema violations are *not* forgiven here — there is nothing to salvage
    from a document whose `fixes` is not a list — and they still leave as
    `PayloadInvalid`, so the caller has one exception type to answer.
    """
    parsed = parse(raw)
    index = {_key(row["ecosystem"], row["package"], row["manifest_path"]) for row in rows}
    survivors = [
        fix
        for fix in parsed.fixes
        if _key(fix.ecosystem, fix.package, fix.manifest_path) in index
    ]
    dropped = len(parsed.fixes) - len(survivors)
    if dropped:
        logger.warning(
            "Dropped %d generated fix(es) naming dependencies this scan did not find.",
            dropped,
        )
    return validate_payload(
        {
            "summary_md": parsed.summary_md,
            "fixes": [fix.model_dump() for fix in survivors],
        },
        rows,
    )


def _key(ecosystem: str, package: str, manifest_path: str) -> tuple[str, str, str]:
    """The identity triple, matched case-insensitively on the name only.

    Package names are lowercase by rule on npm and case-insensitive by PEP 503
    on PyPI, so a model that title-cases one has not named a different package.
    Paths are matched exactly: `Src/package.json` and `src/package.json` are
    two different files on the platforms this project's repositories live on.
    """
    return (ecosystem, package.strip().lower(), manifest_path.strip())


def _merge(fix: GeneratedFix, row: dict) -> dict:
    """One §5.8 fix: the model's decision, the scan's measurements."""
    return {
        "package": row["package"],
        "manifest_path": row["manifest_path"],
        "ecosystem": row["ecosystem"],
        "current_version": row.get("current_version") or "",
        "fix_type": fix.fix_type,
        "target_version": fix.target_version or None,
        "replacement_package": fix.replacement_package or None,
        "cves": list(row.get("cves") or []),
        "severity": row.get("highest_severity") or "",
        "priority": fix.priority,
    }


def _rank(fixes: list[dict]) -> list[dict]:
    """Renumber to 1..N, preserving the model's own ordering.

    A prioritized list whose priorities read 1, 1, 3 is a list that has not
    quite prioritized. The sort is stable and keyed on the model's number
    alone, so ties keep the order the model put them in and nothing is
    reordered on the strength of an assumption about what it meant.
    """
    ordered = sorted(fixes, key=lambda fix: fix["priority"])
    for position, fix in enumerate(ordered, start=1):
        fix["priority"] = position
    return ordered


def _repair_hint(exc: ValidationError) -> str:
    """Pydantic's errors, rewritten as instructions rather than diagnostics."""
    lines = []
    for error in exc.errors()[:8]:
        location = ".".join(str(part) for part in error["loc"]) or "(root)"
        lines.append(f"- {location}: {error['msg']}")
    return "The previous answer had these problems:\n" + "\n".join(lines)
