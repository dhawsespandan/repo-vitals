"""The two download formats — §10 Phase 9, rendered from one stored row.

    fmt=md    templated summary + fixes + citations + confidence note
    fmt=json  §5.8's payload, as a task handoff

**No second model call, ever.** §5.8 is explicit: "One generation produces one
payload serving both downloads." Everything here is a re-rendering of columns
that were written once, by the generation, and validated then. A download of a
report generated three weeks ago costs one SELECT.

**Two media, one set of facts.** The markdown is for a person: it carries the
confidence caveat, the fixes, and the passages the plan cited, so the file can
be read on its own without the product beside it. The JSON is §5.8's "machine-
parseable task handoff for external coding agents", so it carries the fixes
array verbatim in the spelling the schema validated, plus the provenance a
receiving agent needs to know *what* it is holding. Neither format invents a
field: every number, version and CVE in both came off the scanned row (§7.1).

**The confidence note is the part that matters most.** §8.14 and §8.16 record
the shape this product keeps rediscovering — a plan that reads authoritative
with the caveat somewhere else, or nowhere. A downloaded file has no banner
above it and no citation pane beside it, so whatever the drawer would have said
has to travel *inside* the document. `confidence_note` below branches on the
same two facts the drawer branches on (`grounding_confidence`, and whether the
answer cited anything at all); the wording differs because a file is read
without the pane to point at, and `docs/decisions.md` §9.3 records that the two
renderings are deliberately separate prose over one rule.

**Filenames are §10's**: `repovitals_{repo}_{type}_{scan}.{md|json}`. The repo
half is sanitized rather than trusted — GitHub's own names are already
`[A-Za-z0-9._-]`, and a filename is the one string in this product that is
interpreted by something outside it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from .models import GroundingConfidence, ReportType

#: What survives into a filename. Everything else becomes `-`.
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

#: The one sentence both formats end on, and the product's whole posture in a
#: line. §5.8: "RepoVitals itself only ever suggests fixes, never applies them
#: (no write calls, ever)." A file that leaves the product and lands in a
#: coding agent's context is exactly where that needs saying.
SUGGESTION_NOTE = (
    "RepoVitals suggests fixes and never applies them. Nothing in this "
    "repository has been changed, and no pull request has been opened - "
    "reading this file is the only thing that has happened."
)


def _slug(value: str, fallback: str) -> str:
    cleaned = _FILENAME_SAFE.sub("-", (value or "").strip()).strip("-.")
    return cleaned or fallback


def filename(report, extension: str) -> str:
    """§10's `repovitals_{repo}_{type}_{scan}.{md|json}`.

    The scan id is the full hex rather than a short prefix. It is long, and it
    is the only part of the name that says *which measurement* this file
    interprets — two downloads of the same repository a month apart differ in
    nothing else, and a truncated id that collided would silently file one over
    the other in a downloads folder.
    """
    repository = report.scan.repository
    return (
        f"repovitals_{_slug(repository.name, 'repository')}"
        f"_{report.report_type}"
        f"_{report.scan_id.hex}.{extension}"
    )


def _stamp(value: datetime | None) -> str | None:
    """UTC, to the second, with the `Z` that says so.

    Explicitly UTC rather than local: `astimezone()` with no argument converts
    to whatever zone the *process* is in, so the same stored row would render
    `21:16:39+0530` on a developer's machine and `15:46:39+0000` on Render —
    one report, two timestamps, and no way for a reader holding the file to
    tell which. `TIME_ZONE = "UTC"` in settings makes that mostly academic in
    deployment and not at all academic on the machine this is written on.

    Seconds, not microseconds: sub-second precision on a report is false
    detail, and it is the kind that reads as a measurement.
    """
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cited_chunks(report) -> list[dict]:
    """The retrieved passages the generation actually cited, in report order.

    Read from `retrieved_chunks_json` by id rather than stored twice: §5.8
    keeps `citations` as chunk ids precisely so the text has one home. An id
    that names no retrieved chunk is dropped rather than rendered as an empty
    quotation — the generation's citations are validated at write time
    (`docs/decisions.md` §8.10), so this is belt and braces for rows written
    before that validator or by a future path.
    """
    chunks = {
        str(chunk.get("chunk_id")): chunk
        for chunk in (report.retrieved_chunks_json or [])
        if isinstance(chunk, dict)
    }
    cited: list[dict] = []
    for chunk_id in report.citations_json or []:
        chunk = chunks.get(str(chunk_id))
        if chunk is not None:
            cited.append(chunk)
    return cited


def confidence_note(report) -> str:
    """What this document is worth, in one paragraph, before the plan itself.

    Four branches over two facts, and they are four different findings:

    * a **combined** report retrieved nothing by design (§5.9 keeps COMBINED
      out of the retrieval graph), so "ungrounded" here is a property of the
      surface rather than a disappointment;
    * **low confidence with nothing retrieved** is a statement about the
      *package* — its documentation could not be found at all;
    * **low confidence with weak passages** is a statement about *retrieval* —
      documentation was found and did not bear on the question;
    * **cleared the gate and cited nothing** is the one §8.14 found on a live
      run, and the one a reader cannot detect for themselves: the thresholds
      passed, the model read the passages, and it grounded none of its answer
      in them.
    """
    if report.report_type == ReportType.COMBINED.value:
        return (
            "Not grounded, by design. This is one model call over the signals "
            "the scan already stored - no documents were retrieved and nothing "
            "here is quoted from a source. It is a triage ordering; the cited, "
            "source-backed surface is the per-dependency report."
        )

    chunks = report.retrieved_chunks_json or []
    citations = report.citations_json or []

    if report.grounding_confidence == GroundingConfidence.LOW.value:
        if not chunks:
            return (
                "No source material. None of this package's own documentation "
                "could be retrieved, so the plan below rests on this scan's "
                "measurements and nothing else. It is deliberately short: with "
                "nothing to quote, this tool says so rather than filling the gap."
            )
        return (
            f"Not enough source material. {len(chunks)} "
            f"{'passage' if len(chunks) == 1 else 'passages'} of this package's "
            "documentation were retrieved and none was close enough to the "
            "question to support a detailed plan. They are reproduced in full "
            "below so the judgement can be checked. What follows rests on this "
            "scan's own measurements instead."
        )

    if chunks and not citations:
        return (
            f"Nothing cited. {len(chunks)} "
            f"{'passage' if len(chunks) == 1 else 'passages'} of this package's "
            "documentation were retrieved, and the plan below rests on none of "
            "them - what came back did not cover the question. Read it as a plan "
            "built from this scan's own measurements: there is no quoted source "
            "to check it against."
        )

    count = len(citations)
    return (
        f"Grounded in {count} retrieved "
        f"{'passage' if count == 1 else 'passages'} of this package's own "
        "documentation, reproduced in full under Sources cited below. Every "
        "claim in the plan is checkable against that text."
    )


def _escape_cell(value) -> str:
    """A table cell that cannot break out of its row.

    A `|` in a package name or a manifest path would end the cell early and
    silently shift every column after it - the table would still render, with
    the wrong values under the wrong headings. Newlines do the same to the row.
    """
    text = "" if value is None else str(value)
    return text.replace("|", r"\|").replace("\n", " ").strip()


def _fix_action(fix: dict) -> str:
    """One fix as an imperative, assembled from §5.8's structured fields.

    Never generated. §5.8 has no field for per-fix prose, and inventing one
    would put an unvalidated sentence beside a validated row (§7.1). The web
    table renders the same four cases in its own words
    (`frontend/src/components/ReportsTab.tsx::fixAction`); the facts are the
    same columns, the wording is per medium, and `docs/decisions.md` §9.3 says
    why that is not a drift risk.
    """
    kind = str(fix.get("fix_type") or "").strip()
    if kind == "upgrade":
        target = fix.get("target_version")
        return f"Upgrade to {target}" if target else "Upgrade to a newer release"
    if kind == "replace":
        replacement = fix.get("replacement_package")
        return (
            f"Replace with {replacement}"
            if replacement
            else "Replace - this package is no longer maintained"
        )
    if kind == "remove":
        return "Remove if nothing uses it"
    return "Investigate - the signals do not point to a single fix"


def _fixes_table(fixes: list[dict]) -> list[str]:
    lines = [
        "| # | Package | Manifest | Current | Action | Fixes |",
        "|---|---|---|---|---|---|",
    ]
    for fix in fixes:
        cves = fix.get("cves") or []
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(fix.get("priority")),
                    f"`{_escape_cell(fix.get('package'))}`",
                    _escape_cell(fix.get("manifest_path")) or "-",
                    _escape_cell(fix.get("current_version")) or "-",
                    _escape_cell(_fix_action(fix)),
                    _escape_cell(", ".join(str(cve) for cve in cves)) or "-",
                ]
            )
            + " |"
        )
    return lines


def _blockquote(text: str) -> list[str]:
    """Quote a retrieved passage so it cannot be mistaken for our prose.

    Every line is prefixed, including the blank ones: a blank line inside a
    blockquote ends it in most renderers, and half a changelog entry rendered
    as body text reads as something RepoVitals wrote.
    """
    return [f"> {line}" if line else ">" for line in (text or "").splitlines()] or [">"]


def render_markdown(report) -> str:
    """The human artifact: what the drawer says, in a file that stands alone."""
    scan = report.scan
    repository = scan.repository
    per_dependency = report.report_type == ReportType.PER_DEPENDENCY.value
    subject = report.dependency

    if per_dependency and subject is not None:
        title = f"Remediation plan - {subject.package.package_name}"
    elif per_dependency:
        title = "Remediation plan"
    else:
        title = f"Dependency triage - {repository.full_name}"

    lines: list[str] = [f"# {title}", ""]

    lines.append(f"- **Repository:** {repository.full_name}")
    if per_dependency and subject is not None:
        version = subject.resolved_version or subject.declared_specifier
        lines.append(
            f"- **Dependency:** `{subject.package.package_name}` {version} "
            f"({subject.package.ecosystem}) in `{subject.manifest.manifest_path}`"
        )
    lines.append(f"- **Scan:** `{scan.scan_id}`")
    if scan.completed_at is not None:
        lines.append(f"- **Scanned:** {_stamp(scan.completed_at)}")
    # The weights file the flagged set was decided under. A report is an
    # interpretation of one measurement, and D5 tags every stored score with
    # the formula that produced it; a file that outlives `v1` should say which
    # formula's findings it is arguing about.
    lines.append(f"- **Scoring formula:** {scan.scoring_formula_version}")
    lines.append(
        f"- **Generated:** {_stamp(report.generated_at)}"
        + (f" by `{report.model_name}` at temperature 0" if report.model_name else "")
    )

    lines += ["", f"> {confidence_note(report)}", ""]

    lines += ["## Summary", "", (report.summary_text or "_No summary was written._"), ""]

    fixes = report.fixes_json or []
    lines.append("## Recommended fixes")
    lines.append("")
    if fixes:
        lines += _fixes_table(fixes)
    else:
        lines.append("_No specific action was recommended._")
    lines.append("")

    if per_dependency:
        cited = _cited_chunks(report)
        chunks = report.retrieved_chunks_json or []
        # Cited passages are the evidence; when there are none, the retrieved
        # ones are shown instead under a heading that says what they are. A
        # caveat that says "passages were retrieved and none supported this"
        # with the passages withheld is a caveat the reader cannot check.
        shown, heading = (
            (cited, "Sources cited")
            if cited
            else (chunks, "Sources retrieved (none cited)")
        )
        lines.append(f"## {heading}")
        lines.append("")
        if not shown:
            lines += ["_Nothing was retrieved for this dependency._", ""]
        for position, chunk in enumerate(shown, start=1):
            label = chunk.get("heading") or "(no heading)"
            lines.append(
                f"### {position}. `{chunk.get('source_path') or 'unknown'}`"
                f" - {label} (similarity {chunk.get('similarity')})"
            )
            lines.append("")
            lines += _blockquote(str(chunk.get("text") or ""))
            lines.append("")

    lines += ["---", "", SUGGESTION_NOTE, ""]
    return "\n".join(lines)


def render_json(report) -> dict:
    """The machine artifact: §5.8's payload, plus what it is a payload *about*.

    `summary_md` and `fixes` are §5.8's two keys, in §5.8's snake_case, holding
    exactly what the validator accepted at generation time - the download and
    the browser read one stored value, so they cannot drift (see
    `apps/reports/serializers.py`'s module docstring for the same argument on
    the API side).

    Everything above them is provenance, not content. An agent handed a bare
    fixes array knows what to do and not *to what*: which repository, which
    measurement, which formula decided these rows were worth flagging, and -
    the one that governs how much weight to put on the plan - whether anything
    grounded it.
    """
    scan = report.scan
    subject = report.dependency

    payload: dict = {
        "schema": "repovitals/report@1",
        "report_type": report.report_type,
        "repository": scan.repository.full_name,
        "scan_id": str(report.scan_id),
        "scoring_formula_version": scan.scoring_formula_version,
        "generated_at": _stamp(report.generated_at),
        "model": report.model_name,
        "dependency": None,
        "grounding_confidence": report.grounding_confidence,
        "citations": [],
        "note": SUGGESTION_NOTE,
        # §5.8's payload, verbatim.
        "summary_md": report.summary_text,
        "fixes": report.fixes_json or [],
    }

    if subject is not None:
        payload["dependency"] = {
            "package": subject.package.package_name,
            "ecosystem": subject.package.ecosystem,
            "manifest_path": subject.manifest.manifest_path,
            "resolved_version": subject.resolved_version,
            "declared_specifier": subject.declared_specifier,
        }

    # Chunk ids are content digests and mean nothing outside this product, so a
    # citation travels with the passage it names - the file has to be checkable
    # by whoever receives it, not only by us.
    payload["citations"] = [
        {
            "chunk_id": chunk.get("chunk_id"),
            "source_path": chunk.get("source_path"),
            "source_sha": chunk.get("source_sha"),
            "heading": chunk.get("heading"),
            "similarity": chunk.get("similarity"),
            "text": chunk.get("text"),
        }
        for chunk in _cited_chunks(report)
    ]

    return payload


def render_json_bytes(report) -> bytes:
    """`render_json` as a file: indented, newline-terminated, UTF-8.

    Indented because a task handoff is read by a person at least once - the
    first time, when they decide whether to trust it - and a single-line 40 KB
    document is not readable. `ensure_ascii=False` so a changelog quoted in a
    citation keeps the characters it was written with.
    """
    return (json.dumps(render_json(report), indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
