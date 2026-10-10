"""`/api/repositories/` — the endpoints, and the BOLA baseline.

§11 tracks BOLA as a standing suite that every later phase extends, and §5.5
says every resource route sits behind `OwnedQuerySetMixin`. Phase 2 is the
first phase with a resource to reach, so the pattern the rest of the build
follows is established here: for each route, a second user's row must be
invisible — 404, never 403, and never present in a listing.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import responses
from django.urls import reverse

from apps.common import http
from apps.repositories.models import Repository
from tests.factories import RepositoryFactory, UserFactory

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "github"

LIST_URL = "/api/repositories/"
REPO_API = "https://api.github.com/repos/expressjs/express"
TREE_API = "https://api.github.com/repos/expressjs/express/git/trees/master"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())


@pytest.fixture
def owner_user(user):
    user.github_username = "expressjs"
    user.save(update_fields=["github_username"])
    return user


@pytest.fixture
def owner_client(api_client, owner_user):
    api_client.force_login(owner_user)
    return api_client


def mock_eligible_repo():
    responses.add(responses.GET, REPO_API, json=fixture("repo_public.json"), status=200)
    responses.add(
        responses.GET, TREE_API, json=fixture("tree_root_manifest.json"), status=200
    )


@pytest.mark.django_db
class TestRegister:
    @responses.activate
    def test_an_eligible_repository_is_created_from_githubs_answers(
        self, owner_client, owner_user
    ):
        mock_eligible_repo()

        response = owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert response.status_code == 201
        assert response.data["fullName"] == "expressjs/express"
        assert response.data["visibility"] == "public"
        assert response.data["accessLevel"] == "owner"

        stored = Repository.objects.get(user=owner_user)
        assert stored.github_repo_id == 237159
        assert stored.default_branch == "master"

    @responses.activate
    def test_a_rejection_stores_nothing(self, owner_client):
        responses.add(responses.GET, REPO_API, json={}, status=404)

        response = owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert response.status_code == 404
        assert response.data["code"] == "repo_inaccessible"
        assert not Repository.objects.exists()

    @responses.activate
    def test_a_duplicate_is_a_200_carrying_the_existing_row(
        self, owner_client, owner_user
    ):
        """§5.6: the user asked for something they have; point them at it."""
        existing = RepositoryFactory(
            user=owner_user, github_repo_id=237159, owner="expressjs", name="express"
        )
        mock_eligible_repo()

        response = owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert response.status_code == 200
        assert response.data["code"] == "already_registered"
        assert response.data["repository"]["id"] == str(existing.repository_id)
        assert Repository.objects.count() == 1

    def test_a_missing_url_is_answered_in_the_5_6_envelope(self, owner_client):
        """Not DRF's own validation envelope — the frontend branches on `code`."""
        response = owner_client.post(LIST_URL, {}, format="json")

        assert response.status_code == 404
        assert response.data["code"] == "repo_inaccessible"

    def test_registration_requires_a_session(self, api_client):
        """403, not 401: DRF's SessionAuthentication offers no WWW-Authenticate
        challenge, so it reports an anonymous caller as forbidden. What matters
        for the contract is that the call is refused in the shared envelope."""
        response = api_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        assert response.status_code == 403
        assert response.data["code"] == "not_authenticated"

    @responses.activate
    def test_the_users_own_token_is_what_reaches_github(self, owner_client, owner_user):
        """Scans run on the requesting user's token, never a shared one (§8)."""
        mock_eligible_repo()

        owner_client.post(
            LIST_URL, {"url": "github.com/expressjs/express"}, format="json"
        )

        sent = responses.calls[0].request.headers["Authorization"]
        assert sent == f"Bearer {owner_user.get_github_token()}"


@pytest.mark.django_db
class TestList:
    def test_only_the_callers_own_registrations_are_listed(self, auth_client, user):
        mine = RepositoryFactory(user=user)
        RepositoryFactory()  # another user's

        response = auth_client.get(LIST_URL)

        assert response.status_code == 200
        assert [row["id"] for row in response.data] == [str(mine.repository_id)]

    def test_the_stored_token_is_never_serialized(self, auth_client, user):
        RepositoryFactory(user=user)

        body = auth_client.get(LIST_URL).content.decode()

        assert "encrypted_github_token" not in body
        assert user.get_github_token() not in body

    def test_listing_requires_a_session(self, api_client):
        response = api_client.get(LIST_URL)

        assert response.status_code == 403
        assert response.data["code"] == "not_authenticated"


@pytest.mark.django_db
class TestDelete:
    def test_a_user_can_remove_their_own_registration(self, auth_client, user):
        repository = RepositoryFactory(user=user)

        response = auth_client.delete(f"{LIST_URL}{repository.repository_id}/")

        assert response.status_code == 204
        assert not Repository.objects.filter(pk=repository.repository_id).exists()

    def test_deleting_requires_a_session(self, api_client, user):
        repository = RepositoryFactory(user=user)

        response = api_client.delete(f"{LIST_URL}{repository.repository_id}/")

        assert response.status_code == 403
        assert Repository.objects.filter(pk=repository.repository_id).exists()


@pytest.mark.django_db
class TestBolaBaseline:
    """The standing suite from §11. Every phase that adds a route adds a case.

    404 rather than 403 throughout: a 403 on a foreign id still confirms the
    id exists, which is the same leak in a politer voice.
    """

    def test_a_foreign_repository_cannot_be_deleted(self, auth_client):
        theirs = RepositoryFactory(user=UserFactory())

        response = auth_client.delete(f"{LIST_URL}{theirs.repository_id}/")

        assert response.status_code == 404
        assert Repository.objects.filter(pk=theirs.repository_id).exists()

    def test_a_foreign_repository_is_absent_from_the_listing(self, auth_client):
        theirs = RepositoryFactory(user=UserFactory())

        rows = auth_client.get(LIST_URL).data

        assert str(theirs.repository_id) not in [row["id"] for row in rows]

    def test_an_unknown_id_is_the_same_404_as_a_foreign_one(self, auth_client):
        theirs = RepositoryFactory(user=UserFactory())
        unknown = "11111111-1111-4111-8111-111111111111"

        foreign = auth_client.delete(f"{LIST_URL}{theirs.repository_id}/")
        missing = auth_client.delete(f"{LIST_URL}{unknown}/")

        assert foreign.status_code == missing.status_code == 404
        assert foreign.data == missing.data

    def test_two_users_may_each_register_the_same_repository(self, user):
        """Per-user uniqueness (§5.1) — not a leak, and not a conflict either."""
        other = UserFactory()
        RepositoryFactory(user=user, github_repo_id=237159, name="express")
        RepositoryFactory(user=other, github_repo_id=237159, name="express")

        assert Repository.objects.filter(github_repo_id=237159).count() == 2


@pytest.mark.django_db
class TestRouting:
    def test_the_routes_match_the_api_surface_spec(self, user):
        """§5.5 spells these paths out; they are part of the contract."""
        repository = RepositoryFactory(user=user)

        assert reverse("repository-list") == "/api/repositories/"
        assert (
            reverse(
                "repository-detail",
                kwargs={"repository_id": repository.repository_id},
            )
            == f"/api/repositories/{repository.repository_id}/"
        )
