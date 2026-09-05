"""Where stored rows meet the pure formula.

`engine.py` and `normalize.py` know nothing about Django by design (§10 Phase
4). This module is the seam: it reads the signals off whatever recorded them,
applies the engine, and writes the derived columns back.

Two callers, one formula. A live scan reads `dependency_occurrences` and
writes `risk_component_score`, `is_flagged`, `cvss_reduced_confidence`,
`scan_runs.risk_score` and `scan_runs.classification`. A research rescore reads
`dependency_history` — the permanent, never-mutated record — and writes a file
(D6). Both go through `signals_for(...)`, so the number a study computes under
`v1` three years from now is the number the product showed on the day.

**Unassessable occurrences are not scored and not flagged** (§5.2). They keep
`risk_component_score = NULL`, which is the difference between "we assessed
this and it is clean" and "we could not assess this at all". A zero there would
collapse the two, and the second is exactly what this product refuses to hide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.scanning.models import DependencyOccurrence, ScanRun

from .engine import classify, is_flagged, roll_up, score_occurrence
from .normalize import Signals
from .weights import WeightSet, active_weights

logger = logging.getLogger(__name__)

#: `bulk_update` batch size. A monorepo scan can carry several hundred
#: occurrences and Postgres does not enjoy a single statement per row, nor one
#: enormous CASE expression covering all of them.
UPDATE_BATCH = 200

DERIVED_FIELDS = ("risk_component_score", "is_flagged", "cvss_reduced_confidence")


def signals_for(row) -> Signals:
    """The four signals off any row that stores them under §5.1's names.

    Duck-typed on purpose: `dependency_occurrences` and `dependency_history`
    carry the same four column names, and D6 requires that a history row be
    scoreable by exactly the code that scored the live one.
    """
    cvss = row.cvss_max
    return Signals(
        is_deprecated=bool(row.is_deprecated),
        vulnerability_count=int(row.vulnerability_count or 0),
        cvss_max=Decimal(cvss) if cvss is not None else None,
        staleness_days=row.staleness_days,
    )


@dataclass(frozen=True)
class ScanScore:
    """What scoring one scan concluded."""

    version: str
    risk_score: Decimal
    classification: str
    assessed_count: int
    flagged_count: int
    unassessable_count: int


def score_scan(scan: ScanRun, weights: WeightSet | None = None) -> ScanScore:
    """Score every occurrence of one scan, then the scan itself (§5.2-§5.3).

    Idempotent: it derives everything from stored signals and overwrites the
    derived columns, so running it twice on an unchanged scan produces an
    identical result — which is also §10 Phase 4's "rescan of an unchanged
    repository → identical score", one layer down.
    """
    weights = weights or active_weights()

    occurrences = list(
        DependencyOccurrence.objects.filter(manifest__scan=scan).select_related(
            "manifest"
        )
    )

    penalties: list[Decimal] = []
    flagged = 0
    unassessable = 0

    for occurrence in occurrences:
        if occurrence.is_unassessable:
            unassessable += 1
            occurrence.risk_component_score = None
            occurrence.is_flagged = False
            occurrence.cvss_reduced_confidence = False
            continue

        signals = signals_for(occurrence)
        result = score_occurrence(signals, weights, occurrence.manifest.ecosystem)

        occurrence.risk_component_score = result.score
        occurrence.is_flagged = is_flagged(signals, weights)
        occurrence.cvss_reduced_confidence = result.cvss_reduced_confidence
        penalties.append(result.penalty)
        flagged += int(occurrence.is_flagged)

    repository = roll_up(penalties, weights)
    classification = classify(repository.score, weights)

    with transaction.atomic():
        DependencyOccurrence.objects.bulk_update(
            occurrences, DERIVED_FIELDS, batch_size=UPDATE_BATCH
        )
        scan.risk_score = repository.score
        scan.classification = classification
        # Re-stamped from the file that actually scored this scan. `start_scan`
        # wrote the version that was active when the row was created; if the
        # deployment's `WEIGHTS_VERSION` changed while the scan ran, the tag
        # has to name the formula the number came from.
        scan.scoring_formula_version = weights.version
        scan.save(
            update_fields=["risk_score", "classification", "scoring_formula_version"]
        )

    logger.info(
        "Scored scan %s under %s: %s (%s) over %d assessable occurrence(s).",
        scan.pk,
        weights.version,
        repository.score,
        classification,
        len(penalties),
    )
    return ScanScore(
        version=weights.version,
        risk_score=repository.score,
        classification=classification,
        assessed_count=len(penalties),
        flagged_count=flagged,
        unassessable_count=unassessable,
    )


@dataclass(frozen=True)
class TopContributor:
    """One row of the detail page's "where the points went" strip."""

    dependency_id: str
    package_name: str
    manifest_path: str
    penalty: Decimal
    points: Decimal


def top_contributors(
    scan: ScanRun, limit: int = 3, weights: WeightSet | None = None
) -> list[TopContributor]:
    """The occurrences that cost this repository the most, worst first.

    Derived from the stored `risk_component_score` values rather than stored
    alongside them: the roll-up is a pure function of those scores, so a
    materialized copy would be a second source of truth that could disagree
    with the table a reader is looking at.

    Ordering is fully specified — penalty, then manifest path, then package
    name — because two occurrences can tie on penalty and the decay factor
    makes rank matter. Without the tiebreak the same scan could attribute
    different point totals to the same two packages on two page loads.
    """
    weights = weights or active_weights()

    rows = list(
        DependencyOccurrence.objects.filter(
            manifest__scan=scan,
            is_unassessable=False,
            risk_component_score__isnull=False,
        )
        .select_related("manifest", "package")
        .order_by(
            "risk_component_score", "manifest__manifest_path", "package__package_name"
        )[: weights.rollup.max_terms]
    )

    contributions = roll_up(
        [Decimal(100) - row.risk_component_score for row in rows], weights
    ).contributions

    top: list[TopContributor] = []
    for row, contribution in zip(rows, contributions, strict=True):
        if contribution.points <= 0:
            # A clean occurrence deducts nothing. Listing it under "top
            # contributors" would name a package that cost the repository
            # zero points, which is worse than a shorter list.
            break
        top.append(
            TopContributor(
                dependency_id=str(row.pk),
                package_name=row.package.package_name,
                manifest_path=row.manifest.manifest_path,
                penalty=contribution.penalty,
                points=contribution.points,
            )
        )
        if len(top) >= limit:
            break
    return top
