"""The scan routes, the trigger on registration, and the concurrency guard.

Two of these are about things a UI cannot be trusted to prevent. A disabled
button stops the second click on the page you tested; it does nothing about
the second tab, the double-submit, or the request replayed from a terminal.
The lock and the status check are the actual rule, so they are what is tested.
"""

from __future__ import annotations

import json
import pathlib
import threading

import pytest
import responses
from django.utils import timezone

from apps.common import http
from apps.scanning import background
from apps.scanning.models import ScanRun, ScanStatus, TriggerType
from tests.factories import RepositoryFactory, UserFactory

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

LIST_URL = "/api/repositories/"
REPO_API = "https://api.github.com/repos/expressjs/express"
TREE_API = f"{REPO_API}/git/trees/master"


def fixture(rel: str) -> dict:
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())


@pytest.fixture
def repository(user):
    return RepositoryFactory(user=user)


def scan_url(repository) -> str:
    return f"/api/repositories/{repository.repository_id}/scan/"


def status_url(repository) -> str:
    return f"/api/repositories/{repository.repository_id}/scan-status/"


@pytest.mark.django_db
class TestScanTrigger:
    def test_a_trigger_is_202_with_the_new_state(self, auth_client, repository):
        """202, not 201: Render's ~100 s timeout makes an inline scan impossible."""
        response = auth_client.post(scan_url(repository))

        assert response.status_code == 202
        assert response.data["scan"]["status"] == ScanStatus.QUEUED.value
        assert response.data["scan"]["triggerType"] == TriggerType.MANUAL.value
        assert response.data["latestCompletedScanId"] is None

    def test_the_work_is_handed_to_a_thread_not_done_inline(
        self, auth_client, repository, no_background_threads
    ):
        auth_client.post(scan_url(repository))

        assert len(no_background_threads) == 1
        target, args = no_background_threads[0]
        assert target is background.execute
        assert args == (ScanRun.objects.get().pk,)

    def test_the_scan_is_tagged_with_the_active_weights_version(
        self, auth_client, repository, settings
    ):
        """§5.1 makes the column NOT NULL; Phase 3 writes the honest value."""
        auth_client.post(scan_url(repository))

        assert ScanRun.objects.get().scoring_formula_version == settings.WEIGHTS_VERSION


@pytest.mark.django_db
class TestLockContention:
    def test_a_double_click_produces_exactly_one_scan(self, auth_client, repository):
        first = auth_client.post(scan_url(repository))
        second = auth_client.post(scan_url(repository))

        assert first.status_code == 202
        assert second.status_code == 409
        assert second.data["code"] == "scan_in_progress"
        assert ScanRun.objects.count() == 1

    def test_the_409_names_the_scan_already_running(self, auth_client, repository):
        """So the client can go and watch it instead of showing an error."""
        auth_client.post(scan_url(repository))

        conflict = auth_client.post(scan_url(repository))

        assert conflict.data["scanId"] == str(ScanRun.objects.get().pk)

    def test_racing_first_users_of_a_repository_get_the_same_lock(self):
        """The guard around the lock dictionary is not decoration.

        Two threads reaching an unseen repository at once would each create
        their own `threading.Lock` and each acquire it happily — which is no
        lock at all, and would fail silently under exactly the load it exists
        to survive. No database here: this is the dictionary's own race.
        """
        key = "11111111-2222-4333-8444-555555555555"
        barrier = threading.Barrier(8)
        seen: list[int] = []

        def grab():
            barrier.wait()
            seen.append(id(background._lock_for(key)))

        threads = [threading.Thread(target=grab) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert len(seen) == 8
        assert len(set(seen)) == 1

    def test_the_status_check_and_the_insert_happen_inside_the_lock(
        self, repository, monkeypatch
    ):
        """The window a double-click fits through is between these two steps.

        Asserted by observation rather than by racing two threads: a race test
        passes when the timing happens to be kind, and this property is either
        true of the code or it is not. If the lock were released between the
        check and the create — or taken only around one of them — one of these
        observations would be False.
        """
        lock = background._lock_for(repository.pk)
        observed: dict[str, bool] = {}

        real_active_scan = background.active_scan
        real_create = ScanRun.objects.create

        def observing_check(repository_id):
            observed["during_check"] = lock.locked()
            return real_active_scan(repository_id)

        def observing_create(**kwargs):
            observed["during_insert"] = lock.locked()
            return real_create(**kwargs)

        monkeypatch.setattr(background, "active_scan", observing_check)
        monkeypatch.setattr(ScanRun.objects, "create", observing_create)

        background.start_scan(repository, repository.user, TriggerType.MANUAL.value)

        assert observed == {"during_check": True, "during_insert": True}
        # And released once the row exists, so one slow scan does not hold the
        # repository's lock for its whole duration.
        assert not lock.locked()

    def test_a_second_repository_is_not_blocked_by_the_first(
        self, auth_client, user, repository
    ):
        """The lock is per repository; one slow scan must not serialize the rest."""
        other = RepositoryFactory(user=user)

        auth_client.post(scan_url(repository))
        response = auth_client.post(scan_url(other))

        assert response.status_code == 202
        assert ScanRun.objects.count() == 2


@pytest.mark.django_db
class TestStaleScans:
    def test_a_scan_that_never_reported_back_stops_blocking_new_ones(
        self, auth_client, repository
    ):
        """Render restarts free instances at will; a wedged repo is unusable."""
        auth_client.post(scan_url(repository))
        stalled = ScanRun.objects.get()
        ScanRun.objects.filter(pk=stalled.pk).update(
            status=ScanStatus.RUNNING.value,
            created_at=timezone.now() - background.STALE_SCAN_AFTER * 2,
        )

        response = auth_client.post(scan_url(repository))

        assert response.status_code == 202
        stalled.refresh_from_db()
        assert stalled.status == ScanStatus.FAILED.value
        assert stalled.error_message == background.STALLED_MESSAGE

    def test_the_status_route_expires_it_too(self, auth_client, repository):
        """Otherwise the page spins until someone thinks to press Run scan."""
        auth_client.post(scan_url(repository))
        ScanRun.objects.update(
            status=ScanStatus.RUNNING.value,
            created_at=timezone.now() - background.STALE_SCAN_AFTER * 2,
        )

        response = auth_client.get(status_url(repository))

        assert response.data["scan"]["status"] == ScanStatus.FAILED.value


@pytest.mark.django_db
class TestScanStatus:
    def test_a_never_scanned_repository_answers_with_nulls(
        self, auth_client, repository
    ):
        response = auth_client.get(status_url(repository))

        assert response.status_code == 200
        assert response.data == {"scan": None, "latestCompletedScanId": None}

    def test_a_rescan_reports_running_while_still_naming_the_last_results(
        self, auth_client, repository
    ):
        """The two fields answer two questions, which is why there are two.

        Conflating them is how a UI ends up showing a finished dependency table
        under a spinner — or, worse, blanking the table the moment a rescan
        starts.
        """
        done = ScanRun.objects.create(
            repository=repository,
            triggered_by=repository.user,
            trigger_type=TriggerType.INITIAL.value,
            status=ScanStatus.COMPLETED.value,
            scoring_formula_version="unscored",
            completed_at=timezone.now(),
        )
        auth_client.post(scan_url(repository))

        response = auth_client.get(status_url(repository))

        assert response.data["scan"]["status"] == ScanStatus.QUEUED.value
        assert response.data["latestCompletedScanId"] == str(done.pk)

    def test_the_repository_list_carries_the_same_state(self, auth_client, repository):
        """So a dashboard of twelve cards costs one request, not twelve."""
        auth_client.post(scan_url(repository))

        rows = auth_client.get(LIST_URL).data

        assert rows[0]["latestScan"]["status"] == ScanStatus.QUEUED.value

    def test_listing_many_repositories_does_not_scale_its_query_count(
        self, auth_client, user, django_assert_max_num_queries
    ):
        for _ in range(5):
            repository = RepositoryFactory(user=user)
            ScanRun.objects.create(
                repository=repository,
                triggered_by=user,
                trigger_type=TriggerType.INITIAL.value,
                status=ScanStatus.COMPLETED.value,
                scoring_formula_version="unscored",
            )

        with django_assert_max_num_queries(8):
            auth_client.get(LIST_URL)


@pytest.mark.django_db
class TestScanDetailAndDependencies:
    @pytest.fixture
    def completed(self, repository):
        from apps.scanning.models import DependencyOccurrence, ManifestFile, Package

        scan = ScanRun.objects.create(
            repository=repository,
            triggered_by=repository.user,
            trigger_type=TriggerType.INITIAL.value,
            status=ScanStatus.COMPLETED.value,
            scoring_formula_version="unscored",
            completed_at=timezone.now(),
        )
        manifest = ManifestFile.objects.create(
            scan=scan,
            ecosystem="npm",
            manifest_path="package.json",
            lockfile_path="package-lock.json",
            parser_name="npm/package.json@1",
        )
        express = Package.objects.create(ecosystem="npm", package_name="express")
        shared = Package.objects.create(ecosystem="npm", package_name="shared-utils")
        DependencyOccurrence.objects.create(
            manifest=manifest,
            package=express,
            declared_specifier="^4.16.0",
            resolved_version="4.17.1",
            resolution="lockfile",
        )
        DependencyOccurrence.objects.create(
            manifest=manifest,
            package=shared,
            declared_specifier="file:../shared",
            is_unassessable=True,
            unassessable_reason="file_specifier",
        )
        return scan

    def test_the_detail_route_carries_the_manifests_and_the_counts(
        self, auth_client, completed
    ):
        response = auth_client.get(f"/api/scans/{completed.pk}/")

        assert response.status_code == 200
        assert response.data["manifestCount"] == 1
        assert response.data["dependencyCount"] == 2
        assert response.data["unassessableCount"] == 1
        assert response.data["manifests"][0]["lockfilePath"] == "package-lock.json"

    def test_the_dependencies_route_paginates(self, auth_client, completed):
        response = auth_client.get(f"/api/scans/{completed.pk}/dependencies/")

        assert response.status_code == 200
        assert response.data["count"] == 2
        assert {row["packageName"] for row in response.data["results"]} == {
            "express",
            "shared-utils",
        }

    def test_unassessable_rows_sort_last(self, auth_client, completed):
        """They are not findings; opening on them buries the rows that matter."""
        rows = auth_client.get(f"/api/scans/{completed.pk}/dependencies/").data[
            "results"
        ]

        assert [row["isUnassessable"] for row in rows] == [False, True]

    def test_the_flagged_filter_is_honest_before_phase_4_sets_the_flag(
        self, auth_client, completed
    ):
        response = auth_client.get(
            f"/api/scans/{completed.pk}/dependencies/?flagged=true"
        )

        assert response.data["count"] == 0

    def test_a_row_carries_its_manifest_path_and_provenance(
        self, auth_client, completed
    ):
        """Both are the point of the table, so both are on every row."""
        rows = auth_client.get(f"/api/scans/{completed.pk}/dependencies/").data[
            "results"
        ]
        express = next(row for row in rows if row["packageName"] == "express")

        assert express["manifestPath"] == "package.json"
        assert express["resolution"] == "lockfile"
        assert express["declaredSpecifier"] == "^4.16.0"


@pytest.mark.django_db
class TestRegistrationTriggersAScan:
    @pytest.fixture
    def owner_client(self, api_client, user):
        user.github_username = "expressjs"
        user.save(update_fields=["github_username"])
        api_client.force_login(user)
        return api_client

    def mock_eligible(self):
        responses.add(
            responses.GET, REPO_API, json=fixture("github/repo_public.json"), status=200
        )
        responses.add(
            responses.GET,
            TREE_API,
            json=fixture("github/tree_root_manifest.json"),
            status=200,
        )

    @responses.activate
    def test_registering_starts_the_initial_scan(self, owner_client):
        self.mock_eligible()

        response = owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert response.status_code == 201
        scan = ScanRun.objects.get()
        assert scan.trigger_type == TriggerType.INITIAL.value
        assert response.data["latestScan"]["id"] == str(scan.pk)

    @responses.activate
    def test_the_registration_response_does_not_wait_for_the_scan(
        self, owner_client, no_background_threads
    ):
        """§10 Phase 3: registration returns with the scan running behind it."""
        self.mock_eligible()

        owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert len(no_background_threads) == 1

    @responses.activate
    def test_a_scan_that_cannot_start_does_not_undo_the_registration(
        self, owner_client, monkeypatch
    ):
        """The user has the repository; answering 500 would deny they do."""
        self.mock_eligible()

        def explode(*args, **kwargs):
            raise RuntimeError("no threads today")

        monkeypatch.setattr(background, "spawn", explode)

        response = owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert response.status_code == 201

    @responses.activate
    def test_a_rejected_registration_starts_nothing(
        self, owner_client, no_background_threads
    ):
        responses.add(responses.GET, REPO_API, json={}, status=404)

        owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert no_background_threads == []
        assert not ScanRun.objects.exists()


@pytest.mark.django_db
class TestBolaOnScanRoutes:
    """§11's standing suite, extended with every route Phase 3 added.

    404 throughout, never 403: a 403 on a foreign id still confirms the id
    exists, which is the same leak in a politer voice.
    """

    @pytest.fixture
    def theirs(self):
        repository = RepositoryFactory(user=UserFactory())
        scan = ScanRun.objects.create(
            repository=repository,
            triggered_by=repository.user,
            trigger_type=TriggerType.MANUAL.value,
            status=ScanStatus.COMPLETED.value,
            scoring_formula_version="unscored",
        )
        return repository, scan

    def test_a_foreign_repository_cannot_be_scanned(self, auth_client, theirs):
        """Not merely refused — no work is queued against someone else's quota."""
        repository, _ = theirs

        before = ScanRun.objects.filter(repository=repository).count()

        response = auth_client.post(scan_url(repository))

        assert response.status_code == 404
        assert ScanRun.objects.filter(repository=repository).count() == before

    def test_a_foreign_repositorys_status_is_invisible(self, auth_client, theirs):
        repository, _ = theirs

        assert auth_client.get(status_url(repository)).status_code == 404

    def test_a_foreign_repository_cannot_be_read(self, auth_client, theirs):
        repository, _ = theirs

        response = auth_client.get(f"/api/repositories/{repository.repository_id}/")

        assert response.status_code == 404

    def test_a_foreign_scan_is_invisible(self, auth_client, theirs):
        _, scan = theirs

        assert auth_client.get(f"/api/scans/{scan.pk}/").status_code == 404

    def test_a_foreign_scans_dependencies_are_a_404_not_an_empty_page(
        self, auth_client, theirs
    ):
        """An empty page leaks nothing but answers a foreign id as an empty one."""
        _, scan = theirs

        response = auth_client.get(f"/api/scans/{scan.pk}/dependencies/")

        assert response.status_code == 404

    def test_an_unknown_id_is_the_same_404_as_a_foreign_one(self, auth_client, theirs):
        _, scan = theirs
        unknown = "11111111-1111-4111-8111-111111111111"

        foreign = auth_client.get(f"/api/scans/{scan.pk}/")
        missing = auth_client.get(f"/api/scans/{unknown}/")

        assert foreign.status_code == missing.status_code == 404
        assert foreign.data == missing.data

    @pytest.mark.parametrize(
        "path",
        [
            "/api/repositories/{repository_id}/scan-status/",
            "/api/scans/{scan_id}/",
            "/api/scans/{scan_id}/dependencies/",
        ],
    )
    def test_every_scan_route_requires_a_session(self, api_client, theirs, path):
        repository, scan = theirs

        response = api_client.get(
            path.format(repository_id=repository.repository_id, scan_id=scan.pk)
        )

        assert response.status_code == 403
        assert response.data["code"] == "not_authenticated"


@pytest.mark.django_db
class TestRouting:
    def test_the_routes_match_the_api_surface_spec(self, repository):
        """§5.5 spells these paths out; they are part of the contract."""
        from django.urls import reverse

        scan = ScanRun.objects.create(
            repository=repository,
            triggered_by=repository.user,
            trigger_type=TriggerType.MANUAL.value,
            scoring_formula_version="unscored",
        )

        assert (
            reverse("repository-scan", kwargs={"repository_id": repository.pk})
            == f"/api/repositories/{repository.pk}/scan/"
        )
        assert (
            reverse("repository-scan-status", kwargs={"repository_id": repository.pk})
            == f"/api/repositories/{repository.pk}/scan-status/"
        )
        assert reverse("scan-detail", kwargs={"scan_id": scan.pk}) == (
            f"/api/scans/{scan.pk}/"
        )
        assert reverse("scan-dependencies", kwargs={"scan_id": scan.pk}) == (
            f"/api/scans/{scan.pk}/dependencies/"
        )
