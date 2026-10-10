"""`GET /api/repositories/{id}/history/` — the trend chart's data (§10 Phase 10).

§10's acceptance for the chart: "trend chart shows movement across rescans;
zero corpus rows in it". The first half is a property of retention, not of
this route - the operational scan is deleted on every rescan (§5.7), so the
only way a chart can show movement is by reading the table D9 never deletes -
and one test walks two scans through exactly that to say so.

The second half is parametrized over every `data_source` value that is not
`live_scan`, rather than naming the one that exists today. The plan has
already renamed that value once (`backfill` -> `corpus_scan`); a test that
names it would keep passing against a filter that had quietly stopped
excluding the new one.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.research import history as research_history
from apps.research.history import record_scan
from apps.research.models import DataSource, ScanHistory
from apps.scanning.models import ScanRun, ScanStatus
from apps.scanning.retention import prune_prior_scans
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    RepositoryFactory,
    ScanRunFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

NOT_LIVE = [value for value in DataSource.values if value != DataSource.LIVE_SCAN.value]


def url(repository) -> str:
    return f"/api/repositories/{repository.pk}/history/"


def history_row(
    repository,
    *,
    score="70.00",
    classification="medium",
    version="v1",
    source=DataSource.LIVE_SCAN.value,
    at=None,
    user=None,
) -> ScanHistory:
    owner = user or repository.user
    live = source == DataSource.LIVE_SCAN.value
    return ScanHistory.objects.create(
        github_user_id=owner.github_user_id,
        github_username=owner.github_username,
        github_repo_id=repository.github_repo_id,
        repo_full_name=repository.full_name,
        ecosystems="npm",
        risk_score=Decimal(score),
        classification=classification,
        dependency_count=3,
        flagged_dependency_count=1,
        scoring_formula_version=version,
        data_source=source,
        snapshot_date=None if live else date(2026, 9, 1),
        sampling_weight=None if live else Decimal("1.5"),
        scanned_at=at or timezone.now(),
    )


def scored_scan(repository, score: str, classification: str) -> ScanRun:
    scan = ScanRunFactory(
        repository=repository,
        status=ScanStatus.COMPLETED.value,
        risk_score=Decimal(score),
        classification=classification,
    )
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=scan), is_flagged=True)
    return scan


def test_the_route_is_the_one_5_5_names(user):
    repository = RepositoryFactory(user=user)

    assert reverse("repository-history", kwargs={"repository_id": repository.pk}) == (
        f"/api/repositories/{repository.pk}/history/"
    )


def test_a_repository_never_scanned_has_an_empty_history(auth_client, user):
    body = auth_client.get(url(RepositoryFactory(user=user))).json()

    assert body == {"total": 0, "limit": 200, "points": [], "thresholds": {}}


def test_a_recorded_scan_is_a_point_carrying_what_was_shown_that_day(auth_client, user):
    repository = RepositoryFactory(user=user)
    scan = scored_scan(repository, "68.45", "medium")
    record_scan(scan)

    body = auth_client.get(url(repository)).json()

    assert body["total"] == 1
    (point,) = body["points"]
    assert point["scanId"] == str(scan.pk)
    assert point["riskScore"] == "68.45"
    assert point["classification"] == "medium"
    assert point["scoringFormulaVersion"] == "v1"
    assert point["dependencyCount"] == 1
    assert point["flaggedDependencyCount"] == 1
    # The research table's identifying snapshots are not part of this surface.
    assert "repoFullName" not in point
    assert "githubUsername" not in point


def test_movement_across_rescans_survives_the_retention_that_deletes_each_scan(
    auth_client, user
):
    """The first scan's operational rows are gone; its point is not."""
    repository = RepositoryFactory(user=user)
    first = scored_scan(repository, "72.50", "medium")
    record_scan(first)
    second = scored_scan(repository, "41.00", "high_alert")
    record_scan(second)
    prune_prior_scans(second)

    body = auth_client.get(url(repository)).json()

    assert not ScanRun.objects.filter(pk=first.pk).exists()
    assert [point["riskScore"] for point in body["points"]] == ["72.50", "41.00"]
    assert [point["classification"] for point in body["points"]] == [
        "medium",
        "high_alert",
    ]


def test_points_are_oldest_first(auth_client, user):
    repository = RepositoryFactory(user=user)
    now = timezone.now()
    history_row(repository, score="50.00", at=now)
    history_row(repository, score="90.00", at=now - timedelta(days=2))
    history_row(repository, score="70.00", at=now - timedelta(days=1))

    points = auth_client.get(url(repository)).json()["points"]

    assert [point["riskScore"] for point in points] == ["90.00", "70.00", "50.00"]


@pytest.mark.parametrize("source", NOT_LIVE)
def test_only_live_scans_are_charted(auth_client, user, source):
    """§10: "zero corpus rows in it"."""
    repository = RepositoryFactory(user=user)
    live = history_row(repository, score="80.00")
    history_row(repository, score="10.00", source=source)

    body = auth_client.get(url(repository)).json()

    assert [point["id"] for point in body["points"]] == [str(live.pk)]
    assert body["total"] == 1


def test_another_users_scans_of_the_same_github_repository_are_not_charted(
    auth_client, user
):
    """A registration is a per-user claim (§5.1); so is its history."""
    mine = RepositoryFactory(user=user, github_repo_id=237159)
    theirs = RepositoryFactory(user=UserFactory(), github_repo_id=237159)
    own = history_row(mine)
    history_row(theirs)

    body = auth_client.get(url(mine)).json()

    assert [point["id"] for point in body["points"]] == [str(own.pk)]


def test_history_outlives_removing_and_registering_the_repository_again(
    auth_client, user
):
    repository = RepositoryFactory(user=user, github_repo_id=424242)
    record_scan(scored_scan(repository, "66.00", "medium"))
    assert auth_client.delete(f"/api/repositories/{repository.pk}/").status_code == 204

    again = RepositoryFactory(user=user, github_repo_id=424242, name="renamed")
    body = auth_client.get(url(again)).json()

    assert [point["riskScore"] for point in body["points"]] == ["66.00"]


def test_a_long_history_keeps_the_latest_points_and_says_how_many_there_are(
    monkeypatch, auth_client, user
):
    monkeypatch.setattr(research_history, "HISTORY_LIMIT", 2)
    repository = RepositoryFactory(user=user)
    now = timezone.now()
    for days, score in ((3, "10.00"), (2, "20.00"), (1, "30.00")):
        history_row(repository, score=score, at=now - timedelta(days=days))

    body = auth_client.get(url(repository)).json()

    assert body["total"] == 3
    assert body["limit"] == 2
    assert [point["riskScore"] for point in body["points"]] == ["20.00", "30.00"]


def test_each_formula_version_carries_its_own_bands(auth_client, user):
    """A version whose weights file is gone gets null, not a guessed 80/50."""
    repository = RepositoryFactory(user=user)
    now = timezone.now()
    history_row(repository, version="v0_equal", at=now - timedelta(days=2))
    history_row(repository, version="v1", at=now - timedelta(days=1))
    history_row(repository, version="retired", at=now)

    thresholds = auth_client.get(url(repository)).json()["thresholds"]

    assert thresholds == {
        "v0_equal": {"safeMin": "80", "mediumMin": "50"},
        "v1": {"safeMin": "80", "mediumMin": "50"},
        "retired": None,
    }


def test_a_foreign_repository_has_no_history_to_read(auth_client):
    theirs = RepositoryFactory(user=UserFactory())
    history_row(theirs)

    response = auth_client.get(url(theirs))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
