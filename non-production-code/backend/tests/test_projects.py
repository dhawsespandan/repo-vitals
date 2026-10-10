"""Projects — §10 Phase 10's creation rules, reads, and ungrouping.

§10's first acceptance criterion is "cannot create a project with a foreign or
single repo". Both halves have a quieter variant that a length check would
wave through, and each has its own case here: `[a, a]` is a project of one, and
a malformed id is an id that names nothing. The foreign case asserts the
answer is *identical* to the missing case, not merely also a refusal, because
§11's BOLA rule is about what a refusal reveals.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.repositories.models import Project, Repository
from apps.repositories.projects import MAX_NAME_LENGTH
from apps.scanning.models import ScanRun, ScanStatus
from tests.factories import (
    ProjectFactory,
    RepositoryFactory,
    ScanRunFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

PROJECTS_URL = "/api/projects/"


def create(client, name, *members):
    return client.post(
        PROJECTS_URL,
        {
            "name": name,
            "repositoryIds": [
                str(member.pk) if isinstance(member, Repository) else member
                for member in members
            ],
        },
        format="json",
    )


def grouped(user, name="Checkout", count=2) -> tuple[Project, list[Repository]]:
    """A valid project: `count` of one user's repositories, grouped."""
    project = ProjectFactory(user=user, name=name)
    members = [RepositoryFactory(user=user, project=project) for _ in range(count)]
    return project, members


class TestCreate:
    def test_two_of_your_own_repositories_become_a_project(self, auth_client, user):
        api = RepositoryFactory(user=user, name="api")
        web = RepositoryFactory(user=user, name="web")

        response = create(auth_client, "Checkout", api, web)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Checkout"
        assert sorted(member["id"] for member in body["repositories"]) == sorted(
            [str(api.pk), str(web.pk)]
        )
        project = Project.objects.get(pk=body["id"])
        assert project.user == user
        assert set(project.repositories.values_list("pk", flat=True)) == {
            api.pk,
            web.pk,
        }

    def test_a_single_repository_is_not_a_project(self, auth_client, user):
        only = RepositoryFactory(user=user)

        response = create(auth_client, "Alone", only)

        assert response.status_code == 422
        assert response.json()["code"] == "project_too_small"
        assert Project.objects.count() == 0

    def test_the_same_repository_twice_is_still_a_project_of_one(self, auth_client, user):
        """A length check sees two ids. There is one repository."""
        only = RepositoryFactory(user=user)

        response = create(auth_client, "Twice", only, str(only.pk).upper())

        assert response.status_code == 422
        assert response.json()["code"] == "project_too_small"
        assert Project.objects.count() == 0

    def test_a_body_without_repository_ids_is_too_small(self, auth_client):
        response = auth_client.post(PROJECTS_URL, {"name": "Empty"}, format="json")

        assert response.status_code == 422
        assert response.json()["code"] == "project_too_small"

    def test_a_foreign_repository_is_refused_and_nothing_is_grouped(
        self, auth_client, user
    ):
        own = RepositoryFactory(user=user)
        theirs = RepositoryFactory(user=UserFactory())

        response = create(auth_client, "Mixed", own, theirs)

        assert response.status_code == 422
        assert response.json()["code"] == "project_repository_unknown"
        assert Project.objects.count() == 0
        own.refresh_from_db()
        theirs.refresh_from_db()
        assert own.project_id is None
        assert theirs.project_id is None

    def test_a_foreign_id_and_a_missing_id_are_the_same_answer(self, auth_client, user):
        own = RepositoryFactory(user=user)
        theirs = RepositoryFactory(user=UserFactory())

        foreign = create(auth_client, "Mixed", own, theirs)
        missing = create(auth_client, "Mixed", own, str(uuid.uuid4()))

        assert foreign.status_code == missing.status_code == 422
        assert foreign.json() == missing.json()

    def test_a_malformed_id_is_an_id_that_names_nothing(self, auth_client, user):
        own = RepositoryFactory(user=user)

        response = create(auth_client, "Typo", own, "not-a-repository-id")

        assert response.status_code == 422
        assert response.json()["code"] == "project_repository_unknown"

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_a_name_is_required(self, auth_client, user, name):
        first, second = RepositoryFactory(user=user), RepositoryFactory(user=user)

        response = create(auth_client, name, first, second)

        assert response.status_code == 400
        assert response.json()["code"] == "project_name_required"
        assert Project.objects.count() == 0

    def test_whitespace_in_a_name_is_collapsed(self, auth_client, user):
        first, second = RepositoryFactory(user=user), RepositoryFactory(user=user)

        response = create(auth_client, "  Check \n  out  ", first, second)

        assert response.status_code == 201
        assert response.json()["name"] == "Check out"

    def test_an_overlong_name_is_refused(self, auth_client, user):
        first, second = RepositoryFactory(user=user), RepositoryFactory(user=user)

        response = create(auth_client, "x" * (MAX_NAME_LENGTH + 1), first, second)

        assert response.status_code == 400
        assert response.json()["code"] == "project_name_too_long"

    def test_a_repository_already_in_a_project_is_not_moved(self, auth_client, user):
        """Moving it would leave its old project with one member."""
        existing, (api, _web) = grouped(user)
        spare = RepositoryFactory(user=user)

        response = create(auth_client, "Second", api, spare)

        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "repository_in_project"
        assert body["repositoryIds"] == [str(api.pk)]
        assert body["message"] == (
            f"{api.full_name} is already in a project. A repository belongs to "
            "one project at a time - ungroup that project first."
        )
        api.refresh_from_db()
        spare.refresh_from_db()
        assert api.project_id == existing.pk
        assert spare.project_id is None
        assert Project.objects.count() == 1

    def test_creating_requires_a_session(self, api_client, user):
        first, second = RepositoryFactory(user=user), RepositoryFactory(user=user)

        response = create(api_client, "Anonymous", first, second)

        assert response.status_code == 403
        assert Project.objects.count() == 0


class TestRead:
    def test_only_your_own_projects_are_listed(self, auth_client, user):
        mine, _ = grouped(user, name="Mine")
        grouped(UserFactory(), name="Theirs")

        rows = auth_client.get(PROJECTS_URL).json()

        assert [row["id"] for row in rows] == [str(mine.pk)]

    def test_members_carry_their_scan_state(self, auth_client, user):
        project, (first, _second) = grouped(user)
        scan = ScanRunFactory(repository=first, status=ScanStatus.COMPLETED.value)

        response = auth_client.get(f"{PROJECTS_URL}{project.pk}/")

        assert response.status_code == 200
        members = {member["id"]: member for member in response.json()["repositories"]}
        assert members[str(first.pk)]["latestCompletedScanId"] == str(scan.pk)
        assert members[str(first.pk)]["project"] == {
            "id": str(project.pk),
            "name": project.name,
        }

    def test_the_repository_list_names_each_repositorys_project(self, auth_client, user):
        project, (member, _) = grouped(user, name="Checkout")
        independent = RepositoryFactory(user=user)

        rows = {row["id"]: row for row in auth_client.get("/api/repositories/").json()}

        assert rows[str(member.pk)]["project"] == {
            "id": str(project.pk),
            "name": "Checkout",
        }
        assert rows[str(independent.pk)]["project"] is None

    def test_listing_costs_the_same_queries_for_one_project_as_for_four(
        self, auth_client, user
    ):
        """No query per member and none per project.

        §3.13's lesson: nothing on screen shows a request count, so it is
        counted. Scan state is batch-loaded and membership is prefetched;
        either done per row would make this number grow with the list.
        """
        grouped(user, name="first", count=3)
        with CaptureQueriesContext(connection) as one:
            assert auth_client.get(PROJECTS_URL).status_code == 200

        for index in range(3):
            grouped(user, name=f"more-{index}", count=3)
        with CaptureQueriesContext(connection) as four:
            assert len(auth_client.get(PROJECTS_URL).json()) == 4

        assert len(four.captured_queries) == len(one.captured_queries)


class TestUngroup:
    def test_ungrouping_keeps_every_member_and_its_scans(self, auth_client, user):
        project, (first, second) = grouped(user)
        scan = ScanRunFactory(repository=first)

        response = auth_client.delete(f"{PROJECTS_URL}{project.pk}/")

        assert response.status_code == 204
        assert not Project.objects.filter(pk=project.pk).exists()
        for member in (first, second):
            member.refresh_from_db()
            assert member.project_id is None
        assert ScanRun.objects.filter(pk=scan.pk).exists()

    def test_a_foreign_project_is_not_ungrouped(self, auth_client):
        theirs, (member, _) = grouped(UserFactory())

        response = auth_client.delete(f"{PROJECTS_URL}{theirs.pk}/")

        assert response.status_code == 404
        member.refresh_from_db()
        assert member.project_id == theirs.pk

    def test_ungrouped_repositories_can_be_grouped_again(self, auth_client, user):
        project, (first, second) = grouped(user)
        auth_client.delete(f"{PROJECTS_URL}{project.pk}/")

        response = create(auth_client, "Again", first, second)

        assert response.status_code == 201
