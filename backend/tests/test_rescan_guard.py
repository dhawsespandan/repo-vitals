"""The rescan confirmation — §10 Phase 9's confirm matrix.

    POST /api/repositories/{id}/scan/   202 | 409 confirm_required | 202 on confirm

Acceptance: "Rescan with reports blocks until confirmed, then old reports gone,
history + traces intact." The last clause is the interesting one and is tested
end to end rather than asserted about the guard alone — the guard exists
*because* §5.7's cascade is real, and a test that only checked the 409 would
pass just as happily if the cascade had quietly stopped working.

**What the guard is not.** It is not a cooldown. §10 is explicit — "value-based
guard — no cooldown timers" — so a repository with nothing generated rescans
without a dialog however recently it last ran, and one with a report is asked
however long ago it was written. The tests are written around that distinction
because a timer is the obvious wrong implementation and would pass a naive
"second rescan is refused" test.
"""

from __future__ import annotations

import pytest

from apps.reports.models import Report, ReportStatus, ReportType
from apps.research.models import DependencyHistory, ScanHistory
from apps.scanning.background import finalize
from apps.scanning.models import ScanRun, ScanStatus
from apps.scanning.retention import reports_at_risk
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    ReportFactory,
    RepositoryFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db


def scan_url(repository) -> str:
    return f"/api/repositories/{repository.pk}/scan/"


@pytest.fixture
def repository(user):
    return RepositoryFactory(user=user)


@pytest.fixture
def scanned(repository, user):
    """A repository whose latest scan completed and has one occurrence."""
    scan = ScanRunFactory(
        repository=repository, triggered_by=user, status=ScanStatus.COMPLETED.value
    )
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=scan))
    return scan


# ── The matrix ──────────────────────────────────────────────────────────────


def test_a_repository_with_nothing_generated_rescans_without_a_dialog(
    auth_client, scanned
):
    """Nothing would be destroyed, so nothing is asked."""
    response = auth_client.post(scan_url(scanned.repository))

    assert response.status_code == 202


def test_a_completed_report_blocks_the_rescan(auth_client, scanned):
    ReportFactory(scan=scanned)

    response = auth_client.post(scan_url(scanned.repository))

    assert response.status_code == 409
    assert response.json()["code"] == "confirm_required"
    # No scan was started. A guard that answered 409 *after* queuing the work
    # would be a dialog asking permission for something already happening.
    assert ScanRun.objects.filter(repository=scanned.repository).count() == 1


def test_the_refusal_carries_the_count_the_dialog_names(auth_client, scanned):
    """ "Some reports" is not something a reader can weigh."""
    ReportFactory(scan=scanned)
    ReportFactory(
        scan=scanned,
        dependency=DependencyOccurrenceFactory(
            manifest=ManifestFileFactory(scan=scanned, manifest_path="api/package.json")
        ),
        report_type=ReportType.PER_DEPENDENCY.value,
    )

    body = auth_client.post(scan_url(scanned.repository)).json()

    assert body["reportsCount"] == 2
    assert "2 generated reports" in body["message"]


def test_confirming_starts_the_scan(auth_client, scanned):
    ReportFactory(scan=scanned)

    response = auth_client.post(
        scan_url(scanned.repository), {"confirm": True}, format="json"
    )

    assert response.status_code == 202
    assert ScanRun.objects.filter(repository=scanned.repository).count() == 2


def test_one_report_is_named_in_the_singular(auth_client, scanned):
    """§6.7: the finished sentence, not substrings of it."""
    ReportFactory(scan=scanned)

    body = auth_client.post(scan_url(scanned.repository)).json()

    assert body["message"] == (
        "This repository has 1 generated report. A new scan replaces these "
        "results and clears them - regenerating costs a fresh model call."
    )


# ── What counts, and what does not ──────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [ReportStatus.QUEUED.value, ReportStatus.RUNNING.value, ReportStatus.FAILED.value],
)
def test_an_unfinished_or_failed_report_is_not_something_to_lose(
    auth_client, scanned, status
):
    """ "This scan has 1 generated report" is false about a generation that failed.

    The count is the number of *answers that exist*, which is what the dialog
    claims it is. A failed row holds an error message; a queued one holds
    nothing at all.
    """
    ReportFactory(scan=scanned, status=status, generated_at=None)

    assert reports_at_risk(scanned.repository.pk) == 0
    assert auth_client.post(scan_url(scanned.repository)).status_code == 202


def test_reports_on_a_superseded_scan_still_count(auth_client, repository, user):
    """The case "the latest scan" would answer zero about.

    A *failed* scan prunes nothing (§5.7's cascade runs on completion), so a
    repository can hold a completed scan with reports plus a newer failed one.
    The rescan about to run destroys the older scan and its reports, and the
    guard has to know that.
    """
    completed = ScanRunFactory(
        repository=repository, triggered_by=user, status=ScanStatus.COMPLETED.value
    )
    ReportFactory(scan=completed)
    ScanRunFactory(
        repository=repository,
        triggered_by=user,
        status=ScanStatus.FAILED.value,
        error_message="GitHub rate-limited this scan.",
    )

    response = auth_client.post(scan_url(repository))

    assert response.status_code == 409
    assert response.json()["reportsCount"] == 1


def test_another_repositorys_reports_are_not_counted(auth_client, scanned, user):
    other = ScanRunFactory(
        repository=RepositoryFactory(user=user, name="other", full_name="acme/other"),
        triggered_by=user,
        status=ScanStatus.COMPLETED.value,
    )
    ReportFactory(scan=other)

    assert auth_client.post(scan_url(scanned.repository)).status_code == 202


def test_the_guard_is_value_based_not_a_cooldown(auth_client, scanned):
    """Two rescans back to back, with nothing generated, are both allowed.

    The wrong implementation — refuse a rescan that follows another too
    closely — would pass every test above and fail this one. §10 rules it out
    in as many words: "value-based guard - no cooldown timers".
    """
    first = auth_client.post(scan_url(scanned.repository))
    # The first scan is now active, so a second POST is refused for being
    # concurrent rather than for being soon. Finish it and try again.
    ScanRun.objects.filter(
        repository=scanned.repository, status__in=("queued", "running")
    ).update(status=ScanStatus.FAILED.value)

    second = auth_client.post(scan_url(scanned.repository))

    assert first.status_code == 202
    assert second.status_code == 202


# ── Only a deliberate "yes" counts ──────────────────────────────────────────


@pytest.mark.parametrize("value", [True, "true", "True", "TRUE", " true "])
def test_the_confirmations_that_are_accepted(auth_client, scanned, value):
    ReportFactory(scan=scanned)

    response = auth_client.post(
        scan_url(scanned.repository), {"confirm": value}, format="json"
    )

    assert response.status_code == 202


@pytest.mark.parametrize("value", [False, "false", 1, 0, "yes", "on", "maybe", None, ""])
def test_everything_else_is_not_a_confirmation(auth_client, scanned, value):
    """A destructive guard does not guess.

    `_boolean_param` is deliberately generous with query strings — `1`, `yes`,
    `on` all mean true for a filter — and that generosity is wrong here. A
    stale client sending `confirm: 1` meaning something else entirely would
    destroy a report on the strength of a value nobody defined.
    """
    ReportFactory(scan=scanned)

    response = auth_client.post(
        scan_url(scanned.repository), {"confirm": value}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "confirm_required"


def test_a_confirmation_on_a_repository_with_nothing_to_lose_is_harmless(
    auth_client, scanned
):
    """Confirming something that was never going to be asked is still a scan."""
    response = auth_client.post(
        scan_url(scanned.repository), {"confirm": True}, format="json"
    )

    assert response.status_code == 202


# ── And the thing the guard is guarding ─────────────────────────────────────


def test_the_confirmed_rescan_destroys_the_reports_and_keeps_the_history(
    auth_client, repository, user
):
    """§10's acceptance, end to end.

    The guard is worth nothing as a claim unless the cascade it warns about
    actually happens — and unless the permanent record actually survives it.
    Both halves are asserted here, on one repository, in the order a user
    experiences them.
    """
    first = ScanRunFactory(
        repository=repository, triggered_by=user, status=ScanStatus.COMPLETED.value
    )
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=first))
    finalize(first)  # writes history for the scan being replaced
    report = ReportFactory(scan=first)

    blocked = auth_client.post(scan_url(repository))
    assert blocked.status_code == 409

    confirmed = auth_client.post(scan_url(repository), {"confirm": True}, format="json")
    assert confirmed.status_code == 202

    # The scan the thread would have run, run here instead: the fixture stubs
    # `spawn`, so nothing races these assertions.
    second = ScanRun.objects.exclude(pk=first.pk).get()
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=second))
    finalize(second)

    assert not Report.objects.filter(pk=report.pk).exists()
    assert not ScanRun.objects.filter(pk=first.pk).exists()
    # D9: the permanent record has no foreign key anything can cascade down.
    assert ScanHistory.objects.count() == 2
    assert DependencyHistory.objects.count() == 2


def test_the_report_route_404s_once_its_scan_is_gone(auth_client, repository, user):
    """What the user sees after confirming: the id they had is simply not there.

    Worth stating as its own case because it is the observable half of the
    cascade — the acceptance run for Phase 7 checked exactly this on prod, and
    a stale tab holding a report id is the ordinary way to reach it.
    """
    first = ScanRunFactory(
        repository=repository, triggered_by=user, status=ScanStatus.COMPLETED.value
    )
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=first))
    report = ReportFactory(scan=first)
    finalize(first)

    second = ScanRunFactory(
        repository=repository, triggered_by=user, status=ScanStatus.COMPLETED.value
    )
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=second))
    finalize(second)

    assert auth_client.get(f"/api/reports/{report.pk}/").status_code == 404
