"""Copying a completed scan into the permanent record (§5.7, first half).

§5.7's order is not a suggestion: history rows are written, and only then is
the previous scan deleted. Reversed, a failure between the two steps destroys
the only copy of a repository's state. So both live inside one transaction at
the call site, and this module's job is just to produce the rows.

**Every occurrence is recorded, not only the interesting ones.** A clean
dependency and an unassessable one are as much a part of the measurement as a
critical CVE — §5.1 says so, and the reason is that a hazard model needs to
know how many packages were at risk and did *not* fail. Filtering here would
produce a dataset that can only ever answer questions about failures.

**Nothing here reads from the network or recomputes anything.** The scan has
already been scored; this copies stored values across, with the identifying
fields flattened into text so the row survives the repository being renamed or
the user deleting their account (D9).
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.scanning.models import DependencyOccurrence, ScanRun

from .models import DataSource, DependencyHistory, ScanHistory

logger = logging.getLogger(__name__)

#: `dependency_history` rows per INSERT. A large monorepo scan is a few
#: hundred rows; batching keeps one statement from growing without bound while
#: still being one round trip per few hundred rows rather than per row.
INSERT_BATCH = 200

#: Points the product's trend chart receives, newest kept (§10 Phase 10). A
#: repository rescanned daily for half a year is under two hundred, and a chart
#: of more points than it has pixels per point is not more information. The
#: total is sent beside them, so a truncated chart can say it is one.
HISTORY_LIMIT = 200


class NotScored(Exception):
    """A scan reached history without a score. `risk_score` is NOT NULL (§5.1)."""


def record_scan(scan: ScanRun) -> ScanHistory:
    """Write one `scan_history` row and its `dependency_history` rows.

    Call inside the same transaction as retention, and only after `score_scan`.
    """
    if scan.risk_score is None or not scan.classification:
        raise NotScored(
            f"Scan {scan.pk} has no score; history rows would violate §5.1's "
            f"NOT NULL columns. Score the scan before recording it."
        )

    repository = scan.repository
    user = repository.user

    occurrences = list(
        DependencyOccurrence.objects.filter(manifest__scan=scan).select_related(
            "manifest", "package"
        )
    )

    ecosystems = sorted({occurrence.manifest.ecosystem for occurrence in occurrences})
    if not ecosystems:
        # A scan that read manifests declaring nothing still has an ecosystem;
        # it just has no occurrence to read it off.
        ecosystems = sorted(scan.manifests.values_list("ecosystem", flat=True).distinct())

    entry = ScanHistory.objects.create(
        source_scan_id=scan.pk,
        github_user_id=user.github_user_id,
        github_username=user.github_username,
        github_repo_id=repository.github_repo_id,
        repo_full_name=repository.full_name,
        ecosystems=",".join(ecosystems),
        risk_score=scan.risk_score,
        classification=scan.classification,
        dependency_count=len(occurrences),
        flagged_dependency_count=sum(
            1 for occurrence in occurrences if occurrence.is_flagged
        ),
        scoring_formula_version=scan.scoring_formula_version,
        data_source=DataSource.LIVE_SCAN.value,
        # NULL on both: a live scan has no sampling frame behind it and no
        # as-of date other than `scanned_at`. Inventing either would let a
        # corpus query silently pick up product rows.
        snapshot_date=None,
        sampling_weight=None,
        scanned_at=scan.completed_at or timezone.now(),
    )

    DependencyHistory.objects.bulk_create(
        [
            DependencyHistory(
                scan_history=entry,
                ecosystem=occurrence.manifest.ecosystem,
                package_name=occurrence.package.package_name,
                manifest_path=occurrence.manifest.manifest_path,
                dependency_group=occurrence.dependency_group,
                declared_specifier=occurrence.declared_specifier,
                resolved_version=occurrence.resolved_version,
                resolution=occurrence.resolution,
                latest_version=occurrence.latest_version,
                staleness_days=occurrence.staleness_days,
                versions_behind_major=occurrence.versions_behind_major,
                versions_behind_minor=occurrence.versions_behind_minor,
                versions_behind_patch=occurrence.versions_behind_patch,
                is_deprecated=occurrence.is_deprecated,
                deprecation_reason=occurrence.deprecation_reason,
                vulnerability_count=occurrence.vulnerability_count,
                highest_severity=occurrence.highest_severity,
                cvss_max=occurrence.cvss_max,
                is_unassessable=occurrence.is_unassessable,
                risk_component_score=occurrence.risk_component_score,
            )
            for occurrence in occurrences
        ],
        batch_size=INSERT_BATCH,
    )

    logger.info(
        "Recorded scan %s to history as %s (%d dependency row(s)).",
        scan.pk,
        entry.pk,
        len(occurrences),
    )
    return entry


def live_history_for(repository) -> tuple[list[ScanHistory], int]:
    """A repository's live scans, oldest first (at most `HISTORY_LIMIT`), and the total.

    The one function in this app that request-handling code calls - §3's
    "never imported by request-handling code (except the history endpoint
    helper)" - so the product's only read of the permanent tables goes through
    one place that can be audited.

    **`live_scan` rows only, by a positive filter.** §10: "corpus rows must never
    pollute the product chart". The filter names the source it wants rather
    than excluding the one it does not, so a `data_source` added later - or the
    `corpus_scan` value being renamed again - cannot leak into a user's chart
    by default.

    **Matched on GitHub's ids, not on the registration.** `scan_history` has no
    foreign key (D9), and that is what makes this chart survive a repository
    being removed and registered again, or renamed: the row carries
    `github_repo_id`, which neither changes. It is scoped to the owner's
    `github_user_id` as well, because a registration is a per-user claim (§5.1)
    and two users tracking one repository must not see each other's scans.
    """
    rows = ScanHistory.objects.filter(
        data_source=DataSource.LIVE_SCAN.value,
        github_repo_id=repository.github_repo_id,
        github_user_id=repository.user.github_user_id,
    )
    total = rows.count()
    latest = list(rows.order_by("-scanned_at", "-scan_history_id")[:HISTORY_LIMIT])
    latest.reverse()
    return latest, total
