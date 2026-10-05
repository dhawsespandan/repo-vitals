"""Synthetic corpus rows for the Phase 12/13 harness tests.

`corpus_repository(...)` writes one `scan_history` row and its
`dependency_history` rows exactly as `scan_corpus` would — tagged
`corpus_scan`, with a snapshot date and a sampling weight — and stores the
score the shipped engine computes for them, so D6's "recompute under the
stored version gives back the stored score" holds for these rows as it does
for real ones.

An occurrence is a dict with any of: `ecosystem` (default npm), `package`,
`deprecated`, `reason`, `vulns`, `cvss`, `staleness`, `unassessable`,
`version`, `latest`.
"""

from __future__ import annotations

import itertools
import zlib
from datetime import UTC, date, datetime
from decimal import Decimal

from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scoring.engine import classify, roll_up, score_occurrence
from apps.scoring.normalize import Signals
from apps.scoring.weights import WeightSet, active_weights

SNAPSHOT = date(2026, 9, 26)

_ids = itertools.count(910_000)


def signals_of(occurrence: dict) -> Signals:
    cvss = occurrence.get("cvss")
    return Signals(
        is_deprecated=bool(occurrence.get("deprecated", False)),
        vulnerability_count=int(occurrence.get("vulns", 0)),
        cvss_max=Decimal(str(cvss)) if cvss is not None else None,
        staleness_days=occurrence.get("staleness", 30),
    )


def corpus_repository(
    full_name: str,
    occurrences: list[dict],
    *,
    snapshot: date | None = SNAPSHOT,
    weights: WeightSet | None = None,
    sampling_weight: float | None = 1.0,
    repo_id: int | None = None,
    data_source: str = DataSource.CORPUS_SCAN.value,
) -> ScanHistory:
    weights = weights or active_weights()
    penalties = []
    ecosystems = set()
    for occurrence in occurrences:
        ecosystem = occurrence.get("ecosystem", "npm")
        ecosystems.add(ecosystem)
        if occurrence.get("unassessable"):
            continue
        penalties.append(
            score_occurrence(signals_of(occurrence), weights, ecosystem).penalty
        )
    result = roll_up(penalties, weights)

    owner = full_name.partition("/")[0]
    entry = ScanHistory.objects.create(
        source_scan_id=None,
        github_user_id=zlib.crc32(owner.encode()) % 100_000,
        github_username=owner,
        github_repo_id=repo_id if repo_id is not None else next(_ids),
        repo_full_name=full_name,
        ecosystems=",".join(sorted(ecosystems)) or "npm",
        risk_score=result.score,
        classification=classify(result.score, weights),
        dependency_count=len(occurrences),
        flagged_dependency_count=0,
        scoring_formula_version=weights.version,
        data_source=data_source,
        snapshot_date=snapshot if data_source == DataSource.CORPUS_SCAN.value else None,
        sampling_weight=sampling_weight
        if data_source == DataSource.CORPUS_SCAN.value
        else None,
        scanned_at=datetime.now(UTC),
    )
    rows = []
    for index, occurrence in enumerate(occurrences):
        ecosystem = occurrence.get("ecosystem", "npm")
        unassessable = bool(occurrence.get("unassessable", False))
        signals = signals_of(occurrence)
        component = (
            None if unassessable else score_occurrence(signals, weights, ecosystem).score
        )
        rows.append(
            DependencyHistory(
                scan_history=entry,
                ecosystem=ecosystem,
                package_name=occurrence.get("package", f"pkg-{index}"),
                manifest_path=occurrence.get(
                    "manifest",
                    "package.json" if ecosystem == "npm" else "requirements.txt",
                ),
                dependency_group="runtime",
                declared_specifier=occurrence.get("version", "1.0.0"),
                resolved_version=None
                if unassessable
                else occurrence.get("version", "1.0.0"),
                resolution=None if unassessable else "pinned",
                latest_version=occurrence.get("latest", "2.0.0"),
                staleness_days=None if unassessable else signals.staleness_days,
                is_deprecated=False if unassessable else signals.is_deprecated,
                deprecation_reason=occurrence.get("reason"),
                vulnerability_count=0 if unassessable else signals.vulnerability_count,
                cvss_max=None if unassessable else signals.cvss_max,
                is_unassessable=unassessable,
                risk_component_score=component,
            )
        )
    DependencyHistory.objects.bulk_create(rows)
    return entry
