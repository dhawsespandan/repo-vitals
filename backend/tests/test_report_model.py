"""§5.1's `reports` constraints, asserted against the database.

These are `CheckConstraint`s and partial `UniqueConstraint`s, so the only way
to test them is to try the write and watch it fail. A model-level assertion
would test Django's opinion of the row; this tests the rule that is actually
enforced when two threads race.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.reports.models import Report, ReportStatus, ReportType
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    ReportFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db


def test_combined_report_may_not_name_a_dependency():
    """The first half of §5.1's biconditional: combined => dependency is null."""
    scan = ScanRunFactory()
    occurrence = DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=scan))

    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            scan=scan,
            dependency=occurrence,
            report_type=ReportType.COMBINED.value,
            status=ReportStatus.QUEUED.value,
        )


def test_per_dependency_report_requires_a_dependency():
    """The half that is easy to omit, and the one that breaks the drill-down."""
    scan = ScanRunFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            scan=scan,
            dependency=None,
            report_type=ReportType.PER_DEPENDENCY.value,
            status=ReportStatus.QUEUED.value,
        )


def test_only_one_combined_report_per_scan():
    """The cache key, expressed as a constraint.

    This is the third of the three layers behind "one generation per scan" —
    the one that holds when the in-process lock does not, because the process
    that raced is a different process.
    """
    scan = ScanRunFactory()
    ReportFactory(scan=scan)

    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            scan=scan,
            report_type=ReportType.COMBINED.value,
            status=ReportStatus.QUEUED.value,
        )


def test_a_second_scan_may_have_its_own_combined_report():
    """The unique is per scan, not per repository: a rescan gets a fresh one."""
    first = ScanRunFactory()
    second = ScanRunFactory(repository=first.repository)

    ReportFactory(scan=first)
    ReportFactory(scan=second)

    assert Report.objects.count() == 2


def test_only_one_per_dependency_report_per_occurrence():
    scan = ScanRunFactory()
    occurrence = DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=scan))
    ReportFactory(
        scan=scan,
        dependency=occurrence,
        report_type=ReportType.PER_DEPENDENCY.value,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            scan=scan,
            dependency=occurrence,
            report_type=ReportType.PER_DEPENDENCY.value,
            status=ReportStatus.QUEUED.value,
        )


def test_two_dependencies_may_each_have_a_report():
    scan = ScanRunFactory()
    manifest = ManifestFileFactory(scan=scan)
    for _ in range(2):
        ReportFactory(
            scan=scan,
            dependency=DependencyOccurrenceFactory(manifest=manifest),
            report_type=ReportType.PER_DEPENDENCY.value,
        )

    assert Report.objects.count() == 2


def test_reports_cascade_with_their_scan():
    """§5.7's retention destroys a scan's reports along with its occurrences.

    Asserted here rather than assumed from the FK: it is the behaviour Phase 9
    puts a confirmation dialog in front of, and a report that outlived its scan
    would be an interpretation of a measurement that no longer exists.
    """
    scan = ScanRunFactory()
    ReportFactory(scan=scan)

    scan.delete()

    assert Report.objects.count() == 0


def test_an_unknown_status_is_refused():
    scan = ScanRunFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        Report.objects.create(
            scan=scan,
            report_type=ReportType.COMBINED.value,
            status="almost_done",
        )
