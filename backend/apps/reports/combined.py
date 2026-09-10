"""One COMBINED generation: scan rows in, a §5.8 payload out.

Pure enough to test without a database transaction or a thread: `build_input`
reads a scan and returns plain dictionaries, and `generate` takes those plus a
callable that behaves like `groq_client.complete_json`. `services.py` owns the
caching, the locking and the row writing; nothing about those belongs here.

**Which rows are sent.** The flagged occurrences, worst first, capped. Clean
rows are excluded because there is nothing to triage about them and they would
be most of the tokens; unassessable rows are excluded because §5.2 could not
measure them, and asking a model to prioritize a dependency nobody assessed
invites exactly the invention this surface must not produce. Both are counted
in the scan summary, so the model is told what it is not seeing rather than
left to assume the flagged rows are the whole repository.

**The retry budget, in full.** One logical call, plus one repair call if the
answer violates §5.8 (§10 Phase 7). Each of those may be re-sent once by
`groq_client` on a transient transport failure. So a generation is at most four
HTTP requests and at most two accepted generations, and `LlmCall.requests`
makes the first number assertable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from apps.scanning.models import DependencyOccurrence, ScanRun
from apps.scoring.engine import flag_reasons
from apps.scoring.signals import signals_for, weights_for_scan

from .llm.groq_client import LlmCall, complete_json, parse_content
from .llm.prompts import COMBINED_SYSTEM_PROMPT, build_combined_user_prompt
from .schema import PayloadInvalid, drop_unmatched, validate_payload

logger = logging.getLogger(__name__)

#: How many flagged occurrences reach the prompt. Thirty is more than any
#: repository in this product's population has as *distinct* problems worth
#: triaging in one sitting, and it bounds the request against the free tier's
#: token-per-day budget (§8). The rows are worst-first, so the cap removes the
#: least consequential findings, and the count of what it removed is sent.
MAX_ROWS = 30

#: Advisories listed per dependency, worst first. A package with forty CVEs is
#: real; forty rows of identifiers in a triage prompt is not information, it is
#: the token budget. The full list is on the drill-down page (§5.5), which is
#: where a reader who wants all of them is already going.
MAX_ADVISORIES_PER_ROW = 5


class GenerationFailed(Exception):
    """The generation could not produce a valid §5.8 payload."""


@dataclass(frozen=True)
class CombinedInput:
    scan_summary: dict
    rows: list[dict]


@dataclass(frozen=True)
class GeneratedCombined:
    payload: dict
    model_name: str
    #: HTTP requests spent. Logged rather than stored — `reports` has no column
    #: for it, and Phase 8's `agent_execution_traces` is where call metadata
    #: becomes permanent.
    requests: int


def build_input(scan: ScanRun) -> CombinedInput:
    """The structured half of the prompt, read from stored signals only."""
    weights = weights_for_scan(scan)

    occurrences = list(
        DependencyOccurrence.objects.filter(
            manifest__scan=scan, is_flagged=True, is_unassessable=False
        )
        .select_related("manifest", "package")
        .prefetch_related("vulnerabilities")
        # Worst first, with the same fully-specified tiebreak `top_contributors`
        # uses: two occurrences can tie on score, and a cap applied to an
        # ambiguous order would send different rows on two runs of one scan.
        .order_by(
            "risk_component_score", "manifest__manifest_path", "package__package_name"
        )
    )

    rows = [_row(occurrence, weights) for occurrence in occurrences[:MAX_ROWS]]

    counts = _counts(scan)
    summary = {
        "repository": scan.repository.full_name,
        "risk_score": _number(scan.risk_score),
        "classification": scan.classification,
        "scoring_formula_version": scan.scoring_formula_version,
        "manifest_count": scan.manifests.count(),
        "dependency_count": counts["total"],
        "flagged_count": counts["flagged"],
        "clean_count": counts["clean"],
        # Sent so the model knows the flagged rows are not the whole picture.
        # §4.7's lesson: a number whose scope is missing reads as a number about
        # everything.
        "unassessable_count": counts["unassessable"],
        "flagged_rows_omitted": max(0, len(occurrences) - MAX_ROWS),
    }
    return CombinedInput(scan_summary=summary, rows=rows)


def generate(scan: ScanRun, *, complete=None) -> GeneratedCombined:
    """Run one generation for `scan`. Raises `GenerationFailed` or `LlmError`.

    `complete` is injectable so the test suite can drive every branch — the
    schema violation, the invented package, the repair that succeeds and the
    repair that does not — without a network or an API key.

    The default is resolved here rather than in the signature, and that is not
    a style choice: `complete=complete_json` binds the function object once, at
    import, so patching this module's `complete_json` would have no effect on a
    caller that did not pass the argument — which is every production caller,
    including `services.run_combined`. A test that patched it would silently
    reach the real endpoint.
    """
    complete = complete or complete_json
    prepared = build_input(scan)
    user_prompt = build_combined_user_prompt(prepared.scan_summary, prepared.rows)

    first: LlmCall = complete(COMBINED_SYSTEM_PROMPT, user_prompt)
    requests = first.requests
    try:
        payload = validate_payload(parse_content(first.content), prepared.rows)
        return GeneratedCombined(payload, first.model, requests)
    except PayloadInvalid as invalid:
        logger.info("Combined report for scan %s needs a repair: %s", scan.pk, invalid)
        repair_reason = invalid.detail

    second: LlmCall = complete(
        COMBINED_SYSTEM_PROMPT,
        f"{user_prompt}\n{repair_reason}\n"
        "Answer again with a corrected JSON object. Same schema, same rules.",
    )
    requests += second.requests

    try:
        # The second answer is allowed to still contain invented rows, and they
        # are dropped rather than argued with (see `schema.drop_unmatched`). A
        # schema violation is not forgiven — there is nothing to salvage.
        payload = drop_unmatched(parse_content(second.content), prepared.rows)
    except PayloadInvalid as invalid:
        raise GenerationFailed(str(invalid)) from invalid

    if prepared.rows and not payload["fixes"]:
        # Every fix was invented. A summary paragraph sitting above an empty
        # fixes list, on a repository with flagged dependencies, is the
        # missing-scope defect this project keeps finding (§4.7, §5.10): the
        # page would read "nothing to do here" about a repository that has
        # things to do. Better to fail visibly with a Try again beside it.
        raise GenerationFailed(
            "The generated report named no dependency this scan actually found."
        )

    return GeneratedCombined(payload, second.model, requests)


def _row(occurrence: DependencyOccurrence, weights) -> dict:
    """One flagged occurrence, as measurements.

    Every value here is a number, a boolean, an enumerated name, an identifier
    or a version string written by a package index. No advisory summary and no
    deprecation message: see this module's prompt docstring for why the
    absence is deliberate.
    """
    advisories = sorted(
        occurrence.vulnerabilities.all(),
        key=lambda vulnerability: (
            -float(vulnerability.cvss_score or 0),
            vulnerability.osv_id,
        ),
    )
    row = {
        "package": occurrence.package.package_name,
        "ecosystem": occurrence.manifest.ecosystem,
        "manifest_path": occurrence.manifest.manifest_path,
        "group": occurrence.dependency_group,
        "declared_specifier": occurrence.declared_specifier,
        "current_version": occurrence.resolved_version,
        # How we know the current version, because it changes what a
        # recommendation means: an approximated row's "current" is the latest
        # release, not what the repository installs (§3.15).
        "version_source": occurrence.resolution,
        "latest_version": occurrence.latest_version,
        "versions_behind": {
            "major": occurrence.versions_behind_major,
            "minor": occurrence.versions_behind_minor,
            "patch": occurrence.versions_behind_patch,
        },
        "deprecated": occurrence.is_deprecated,
        "advisory_count": occurrence.vulnerability_count,
        "highest_severity": occurrence.highest_severity,
        "max_cvss": _number(occurrence.cvss_max),
        "risk_component_score": _number(occurrence.risk_component_score),
        "flag_reasons": list(flag_reasons(signals_for(occurrence), weights)),
        "advisories": [
            {
                "osv_id": vulnerability.osv_id,
                "cve_id": vulnerability.cve_id,
                "severity": vulnerability.severity,
                "cvss": _number(vulnerability.cvss_score),
                "fixed_version": vulnerability.fixed_version,
            }
            for vulnerability in advisories[:MAX_ADVISORIES_PER_ROW]
        ],
    }
    if occurrence.staleness_days is not None:
        # Omitted rather than sent as null when there is no publish history:
        # §5.2 redistributes the staleness weight in that case, so the signal
        # did not merely measure zero, it did not participate. Rule 8 of the
        # system prompt tells the model what an absent key means.
        row["days_since_release"] = occurrence.staleness_days

    # §5.8's `cves` for this row, filled into every fix that names it rather
    # than copied from the model's answer (see `schema._merge`).
    #
    # Deduplicated, because advisories and CVEs are not one to one. OSV
    # routinely returns several records for one underlying vulnerability — a
    # GHSA and a PYSEC advisory for the same CVE is the normal case, not an
    # edge — and `UNIQUE(dependency_id, osv_id)` admits them all, correctly:
    # they are different advisories. Mapping them straight to `cve_id` is what
    # produced "Fixes CVE-2026-25645, CVE-2024-47081, CVE-2024-47081,
    # CVE-2026-25645" on the first live report this project ever generated
    # (§7.13). Order is the advisories' own — worst CVSS first — so the most
    # serious identifier still leads.
    row["cves"] = list(
        dict.fromkeys(
            vulnerability.cve_id or vulnerability.osv_id for vulnerability in advisories
        )
    )
    return row


def _counts(scan: ScanRun) -> dict[str, int]:
    """The partition the detail page shows, counted the same way it counts it."""
    occurrences = DependencyOccurrence.objects.filter(manifest__scan=scan)
    total = occurrences.count()
    unassessable = occurrences.filter(is_unassessable=True).count()
    flagged = occurrences.filter(is_flagged=True).count()
    return {
        "total": total,
        "flagged": flagged,
        "unassessable": unassessable,
        "clean": total - unassessable - flagged,
    }


def _number(value: Decimal | None) -> float | None:
    """Decimals as JSON numbers.

    A `NUMERIC` reaches a prompt as a number rather than as the string DRF
    would render, because "7.5" and 7.5 read differently to a model asked to
    rank by CVSS. Precision is not at stake: nothing downstream computes with
    these, and every number the *report* displays is copied from the row rather
    than from the answer.
    """
    return None if value is None else float(value)
