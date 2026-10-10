"""Deleting a repository that belongs to a project — §10 Phase 10's cascade.

§10: "deleting a repo in a multi-repo project -> 409 `project_cascade_confirm`
+ counts; confirm deletes **all** member repos (normal operational cascades) +
the project row (a project cannot shrink to one member); history/traces
persist."

The confirmation carries the project's id rather than `true`, and that is the
one design decision in this file (`docs/decisions.md` §10.3). A boolean says
"yes, delete"; an id says "yes, delete *this* group" — and the group a reader
saw in a dialog is not guaranteed to be the group that exists when they press
the button. The membership-changed case below is the reason.
"""

from __future__ import annotations

import uuid

import pytest

from apps.repositories.models import Project, Repository
from apps.research.history import record_scan
from apps.research.models import AgentExecutionTrace, DependencyHistory, ScanHistory
from apps.scanning.models import ScanRun, ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    ProjectFactory,
    RepositoryFactory,
    ScanRunFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def delete(client, repository, confirm=None):
    url = f"/api/repositories/{repository.pk}/"
    if confirm is not None:
        url += f"?confirm={confirm}"
    return client.delete(url)


def grouped(user, *names) -> tuple[Project, list[Repository]]:
    project = ProjectFactory(user=user, name="Checkout")
    return project, [
        RepositoryFactory(user=user, project=project, name=name) for name in names
    ]


def recorded_scan(repository) -> ScanRun:
    """A completed, scored scan with its permanent history already written."""
    scan = ScanRunFactory(
        repository=repository,
        status=ScanStatus.COMPLETED.value,
        risk_score="72.50",
        classification="medium",
    )
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=scan))
    record_scan(scan)
    return scan


class TestIndependentRepositories:
    def test_an_independent_repository_is_deleted_without_a_question(
        self, auth_client, user
    ):
        repository = RepositoryFactory(user=user)

        response = delete(auth_client, repository)

        assert response.status_code == 204
        assert not Repository.objects.filter(pk=repository.pk).exists()

    def test_a_confirmation_for_a_project_it_has_left_deletes_only_it(
        self, auth_client, user
    ):
        """A stale tab confirmed a group that has since been ungrouped.

        Deleting the one repository is strictly less than what was confirmed,
        so it proceeds; the siblings it used to have are not touched.
        """
        repository = RepositoryFactory(user=user)
        former_sibling = RepositoryFactory(user=user)

        response = delete(auth_client, repository, confirm=uuid.uuid4())

        assert response.status_code == 204
        assert Repository.objects.filter(pk=former_sibling.pk).exists()


class TestTheQuestion:
    def test_a_member_is_not_deleted_until_the_cascade_is_confirmed(
        self, auth_client, user
    ):
        project, (api, web, worker) = grouped(user, "api", "web", "worker")

        response = delete(auth_client, api)

        assert response.status_code == 409
        body = response.json()
        assert body == {
            "code": "project_cascade_confirm",
            "message": (
                f"{api.full_name} is part of the project Checkout with 2 other "
                "repositories. A project can't shrink to one repository, so "
                "removing it removes all 3, with their scans and reports."
            ),
            "projectId": str(project.pk),
            "projectName": "Checkout",
            "memberCount": 3,
            "otherCount": 2,
            "repositories": sorted([api.full_name, web.full_name, worker.full_name]),
        }
        assert Repository.objects.filter(project=project).count() == 3
        assert Project.objects.filter(pk=project.pk).exists()

    def test_the_sentence_is_singular_for_a_pair(self, auth_client, user):
        _project, (api, _web) = grouped(user, "api", "web")

        body = delete(auth_client, api).json()

        assert body["message"] == (
            f"{api.full_name} is part of the project Checkout with 1 other "
            "repository. A project can't shrink to one repository, so removing "
            "it removes all 2, with their scans and reports."
        )

    @pytest.mark.parametrize("confirm", ["true", "True", "1", "yes", ""])
    def test_a_boolean_is_not_a_confirmation_of_a_cascade(
        self, auth_client, user, confirm
    ):
        """`true` answers "delete?". The question is "delete *which* group?"."""
        project, (api, _web) = grouped(user, "api", "web")

        response = delete(auth_client, api, confirm=confirm)

        assert response.status_code == 409
        assert Repository.objects.filter(project=project).count() == 2

    def test_confirming_a_different_project_is_not_confirming_this_one(
        self, auth_client, user
    ):
        project, (api, _web) = grouped(user, "api", "web")
        other, _ = grouped(user, "docs", "site")

        response = delete(auth_client, api, confirm=other.pk)

        assert response.status_code == 409
        assert response.json()["projectId"] == str(project.pk)
        assert Repository.objects.filter(project=project).count() == 2
        assert Repository.objects.filter(project=other).count() == 2

    def test_a_group_that_changed_since_the_dialog_is_asked_about_again(
        self, auth_client, user
    ):
        """The reader confirmed {api, web}. The group is now {api, billing}.

        With `confirm=true` this would delete `billing`, a repository the reader
        never saw named in the dialog they agreed to.
        """
        first, (api, web) = grouped(user, "api", "web")
        asked = delete(auth_client, api).json()
        # A second tab ungroups, and regroups `api` with something else.
        first.delete()
        billing = RepositoryFactory(user=user, name="billing")
        second = ProjectFactory(user=user, name="Payments")
        Repository.objects.filter(pk__in=[api.pk, billing.pk]).update(project=second)

        response = delete(auth_client, api, confirm=asked["projectId"])

        assert response.status_code == 409
        body = response.json()
        assert body["projectId"] == str(second.pk)
        assert body["repositories"] == sorted([api.full_name, billing.full_name])
        assert Repository.objects.filter(pk__in=[api.pk, web.pk, billing.pk]).count() == 3


class TestTheCascade:
    def test_confirming_removes_every_member_and_the_project(self, auth_client, user):
        project, members = grouped(user, "api", "web", "worker")
        scans = [ScanRunFactory(repository=member) for member in members]

        response = delete(auth_client, members[1], confirm=project.pk)

        assert response.status_code == 204
        assert not Project.objects.filter(pk=project.pk).exists()
        assert not Repository.objects.filter(pk__in=[m.pk for m in members]).exists()
        # The normal operational cascade, for every member rather than one.
        assert not ScanRun.objects.filter(pk__in=[s.pk for s in scans]).exists()

    def test_nothing_outside_the_project_is_touched(self, auth_client, user):
        project, members = grouped(user, "api", "web")
        other_project, other_members = grouped(user, "docs", "site")
        independent = RepositoryFactory(user=user)
        stranger = RepositoryFactory(user=UserFactory())

        delete(auth_client, members[0], confirm=project.pk)

        assert Project.objects.filter(pk=other_project.pk).exists()
        assert Repository.objects.filter(project=other_project).count() == 2
        assert (
            Repository.objects.filter(
                pk__in=[independent.pk, stranger.pk, *[m.pk for m in other_members]]
            ).count()
            == 4
        )

    def test_history_and_traces_outlive_the_cascade(self, auth_client, user):
        """§10: "delete-one -> confirm -> all members + project gone, history intact"."""
        project, (api, web) = grouped(user, "api", "web")
        recorded_scan(api)
        recorded_scan(web)
        AgentExecutionTrace.objects.create(
            github_user_id=user.github_user_id,
            repo_full_name=api.full_name,
            ecosystem="npm",
            package_name="lodash",
            branch_taken="no_reason",
            grounding_confidence="low",
        )
        history_before = ScanHistory.objects.count()
        dependencies_before = DependencyHistory.objects.count()

        response = delete(auth_client, api, confirm=project.pk)

        assert response.status_code == 204
        assert not Repository.objects.filter(pk__in=[api.pk, web.pk]).exists()
        assert history_before == 2
        assert ScanHistory.objects.count() == history_before
        assert DependencyHistory.objects.count() == dependencies_before
        assert set(ScanHistory.objects.values_list("repo_full_name", flat=True)) == {
            api.full_name,
            web.full_name,
        }
        assert AgentExecutionTrace.objects.filter(repo_full_name=api.full_name).exists()

    def test_a_foreign_member_is_not_found_whatever_the_confirmation(self, auth_client):
        stranger = UserFactory()
        project, (api, _web) = grouped(stranger, "api", "web")

        response = delete(auth_client, api, confirm=project.pk)

        assert response.status_code == 404
        assert response.json()["code"] == "not_found"
        assert Repository.objects.filter(project=project).count() == 2
