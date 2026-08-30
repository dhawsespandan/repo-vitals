"""Pre-scan validation — the §5.6 outcome matrix, plus §1.12's ownership rule.

The acceptance criterion for Phase 2 is that *every row of §5.6's table* is
reproduced, so the table is the structure of this file. Payloads come from the
recorded fixtures in `tests/fixtures/github/` (§4.4); variants override
individual keys so each test states exactly what it changes.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import responses

from apps.common import http
from apps.common.errors import ApiError
from apps.repositories.validation import (
    DuplicateRegistration,
    parse_repo_url,
    validate_and_describe,
)
from tests.factories import RepositoryFactory

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "github"

REPO_URL = "https://api.github.com/repos/expressjs/express"
TREE_URL = "https://api.github.com/repos/expressjs/express/git/trees/master"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def repo_payload(**overrides) -> dict:
    payload = fixture("repo_public.json")
    permissions = overrides.pop("permissions", None)
    if permissions is not None:
        payload["permissions"] = permissions
    owner_login = overrides.pop("owner_login", None)
    if owner_login is not None:
        payload["owner"]["login"] = owner_login
        payload["full_name"] = f"{owner_login}/{payload['name']}"
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())


@pytest.fixture
def owner_user(user):
    """The recorded repository's owner, so the ownership rule passes by default."""
    user.github_username = "expressjs"
    user.save(update_fields=["github_username"])
    return user


def mock_github(
    repo: dict | None = None,
    tree: str | dict = "tree_root_manifest.json",
    *,
    owner: str = "expressjs",
    name: str = "express",
):
    """Mock the two calls validation makes, at the URLs it will actually build.

    `owner`/`name` follow the *pasted* URL, which is what determines the
    outbound path — the payload's own owner field is a separate thing, and the
    ownership tests deliberately vary the two independently.
    """
    base = f"https://api.github.com/repos/{owner}/{name}"
    if repo is not None:
        responses.add(responses.GET, base, json=repo, status=200)
    if isinstance(tree, str):
        tree = fixture(tree)
    branch = (repo or {}).get("default_branch") or "master"
    responses.add(responses.GET, f"{base}/git/trees/{branch}", json=tree, status=200)


class TestUrlParsing:
    """The pasted URL becomes `owner/repo` and is discarded (§5.6 SSRF note)."""

    @pytest.mark.parametrize(
        "raw",
        [
            "https://github.com/expressjs/express",
            "http://github.com/expressjs/express",
            "github.com/expressjs/express",
            "www.github.com/expressjs/express",
            "https://github.com/expressjs/express/",
            "https://github.com/expressjs/express.git",
            "git@github.com:expressjs/express.git",
            "https://github.com/expressjs/express/tree/master/lib",
            "https://github.com/expressjs/express/blob/master/package.json",
            "  https://github.com/expressjs/express  ",
            "expressjs/express",
        ],
    )
    def test_the_shapes_people_actually_paste(self, raw):
        assert parse_repo_url(raw) == ("expressjs", "express")

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "https://gitlab.com/owner/repo",
            "https://github.evil.com/owner/repo",
            "https://github.com/onlyowner",
            "https://github.com/-badowner/repo",
            "https://github.com/owner/..",
            "https://github.com/owner/re$po",
            "file:///etc/passwd",
            "https://169.254.169.254/latest/meta-data/",
        ],
    )
    def test_anything_else_is_repo_inaccessible(self, raw):
        with pytest.raises(ApiError) as caught:
            parse_repo_url(raw)
        assert caught.value.code == "repo_inaccessible"
        assert caught.value.status_code == 404


@pytest.mark.django_db
class TestOutcomeMatrix:
    """One test per row of §5.6, in the table's own order."""

    @responses.activate
    def test_an_eligible_repository_is_described_from_githubs_answers(self, owner_user):
        mock_github(repo_payload())

        result = validate_and_describe(owner_user, "github.com/expressjs/express")

        assert result.github_repo_id == 237159
        assert result.owner == "expressjs"
        assert result.name == "express"
        assert result.full_name == "expressjs/express"
        assert result.default_branch == "master"
        assert result.visibility == "public"
        assert result.access_level == "owner"

    @responses.activate
    def test_not_found_is_repo_inaccessible(self, owner_user):
        responses.add(responses.GET, REPO_URL, json={}, status=404)

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "repo_inaccessible"
        assert caught.value.status_code == 404
        assert caught.value.message == (
            "We couldn't access this repository. Check the link, or make sure it's public."
        )

    @responses.activate
    def test_read_only_access_is_no_write_access(self, user):
        """Read-only public repos and fork-and-PR workflows both land here."""
        mock_github(
            repo_payload(
                owner_login="expressjs",
                permissions={"admin": False, "push": False, "pull": True},
            )
        )

        with pytest.raises(ApiError) as caught:
            validate_and_describe(user, "github.com/expressjs/express")

        assert caught.value.code == "no_write_access"
        assert caught.value.status_code == 403
        assert caught.value.message == (
            "You need write or collaborator access on this repository to monitor it here."
        )

    @responses.activate
    def test_a_duplicate_carries_the_existing_repository(self, owner_user):
        existing = RepositoryFactory(
            user=owner_user, github_repo_id=237159, owner="expressjs", name="express"
        )
        mock_github(repo_payload())

        with pytest.raises(DuplicateRegistration) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.repository == existing

    @responses.activate
    def test_a_repo_renamed_on_github_is_still_recognised_as_a_duplicate(
        self, owner_user
    ):
        """github_repo_id is checked first precisely because names change."""
        existing = RepositoryFactory(
            user=owner_user, github_repo_id=237159, owner="expressjs", name="old-name"
        )
        mock_github(repo_payload())

        with pytest.raises(DuplicateRegistration) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.repository == existing

    @responses.activate
    def test_another_users_registration_is_not_a_duplicate(self, owner_user):
        """Registrations are per-user (§5.1): two users may track one repo."""
        RepositoryFactory(github_repo_id=237159, owner="expressjs", name="express")
        mock_github(repo_payload())

        assert validate_and_describe(owner_user, "github.com/expressjs/express")

    @responses.activate
    def test_no_supported_manifest_is_ecosystem_unsupported(self, owner_user):
        mock_github(repo_payload(), tree="tree_no_manifest.json")

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "ecosystem_unsupported"
        assert caught.value.status_code == 422
        assert caught.value.message == (
            "This repository's dependency ecosystem isn't supported yet. "
            "We currently support Node.js/npm projects."
        )

    @responses.activate
    def test_an_empty_tree_is_repo_empty(self, owner_user):
        mock_github(repo_payload(), tree="tree_empty.json")

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "repo_empty"
        assert caught.value.status_code == 422
        assert caught.value.message == (
            "This repository appears to be empty — there's nothing to scan."
        )

    @responses.activate
    def test_a_repo_with_no_commits_is_repo_empty_without_a_tree_call(self, owner_user):
        """No default branch means no commits; the tree call would only 409."""
        responses.add(
            responses.GET, REPO_URL, json=repo_payload(default_branch=""), status=200
        )

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "repo_empty"
        assert len(responses.calls) == 1

    @responses.activate
    def test_githubs_409_for_an_empty_repository_is_repo_empty(self, owner_user):
        responses.add(responses.GET, REPO_URL, json=repo_payload(), status=200)
        responses.add(responses.GET, TREE_URL, json={}, status=409)

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "repo_empty"

    @responses.activate
    def test_a_rate_limit_is_github_rate_limited(self, owner_user):
        responses.add(
            responses.GET,
            REPO_URL,
            json={},
            status=403,
            headers={"x-ratelimit-remaining": "0"},
        )

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "github_rate_limited"
        assert caught.value.status_code == 503
        assert caught.value.message == (
            "We're temporarily unable to check this repository. "
            "Please try again in a few minutes."
        )


@pytest.mark.django_db
class TestOwnershipRule:
    """§1.12 — private repositories only in the user's own namespace."""

    @responses.activate
    def test_a_private_repo_owned_by_someone_else_is_refused(self, user):
        mock_github(
            repo_payload(owner_login="acme-corp", private=True), owner="acme-corp"
        )

        with pytest.raises(ApiError) as caught:
            validate_and_describe(user, "github.com/acme-corp/express")

        assert caught.value.code == "private_repo_not_owned"
        assert caught.value.status_code == 403

    @responses.activate
    def test_ownership_is_decided_before_write_access(self, user):
        """Both checks fail on a private org repo the user can push to.

        Whichever runs first is the reason the user sees, and "you need write
        access" would send them to obtain access that changes nothing (§2.2).
        """
        mock_github(
            repo_payload(
                owner_login="acme-corp",
                private=True,
                permissions={"admin": False, "push": True, "pull": True},
            ),
            owner="acme-corp",
        )

        with pytest.raises(ApiError) as caught:
            validate_and_describe(user, "github.com/acme-corp/express")

        assert caught.value.code == "private_repo_not_owned"

    @responses.activate
    def test_a_public_repo_owned_by_someone_else_is_fine(self, user):
        """The rule is about *private* repositories, not about ownership alone."""
        mock_github(
            repo_payload(
                owner_login="acme-corp",
                private=False,
                permissions={"admin": False, "push": True, "pull": True},
            ),
            owner="acme-corp",
        )

        result = validate_and_describe(user, "github.com/acme-corp/express")

        assert result.visibility == "public"
        assert result.access_level == "write"

    @responses.activate
    def test_a_private_repo_in_the_users_own_namespace_is_fine(self, owner_user):
        mock_github(repo_payload(private=True))

        result = validate_and_describe(owner_user, "github.com/expressjs/express")

        assert result.visibility == "private"
        assert result.access_level == "owner"

    @responses.activate
    def test_the_username_comparison_ignores_case(self, user):
        """GitHub logins are case-insensitive; the rule must be too."""
        user.github_username = "ExpressJS"
        user.save(update_fields=["github_username"])
        mock_github(repo_payload(owner_login="expressjs", private=True))

        assert validate_and_describe(user, "github.com/expressjs/express")


@pytest.mark.django_db
class TestManifestSearch:
    """§5.6: patterns are matched anywhere in the recursive tree."""

    @responses.activate
    def test_a_manifest_only_deep_in_the_tree_still_counts(self, owner_user):
        """The split-by-functionality case a root-only check silently misses."""
        mock_github(repo_payload(), tree="tree_nested_manifest.json")

        assert validate_and_describe(owner_user, "github.com/expressjs/express")

    @responses.activate
    def test_a_vendored_node_modules_does_not_count(self, owner_user):
        """Otherwise a checked-in node_modules makes any repo an npm project."""
        mock_github(repo_payload(), tree="tree_vendored_only.json")

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "ecosystem_unsupported"

    @responses.activate
    def test_a_truncated_tree_proceeds_on_what_came_back(self, owner_user):
        """§5.6's documented, accepted limitation."""
        mock_github(repo_payload(), tree="tree_truncated.json")

        assert validate_and_describe(owner_user, "github.com/expressjs/express")

    @responses.activate
    def test_the_tree_is_requested_recursively(self, owner_user):
        mock_github(repo_payload())

        validate_and_describe(owner_user, "github.com/expressjs/express")

        assert "recursive=1" in responses.calls[-1].request.url


@pytest.mark.django_db
class TestUpstreamFailures:
    @responses.activate
    def test_github_being_down_is_reported_separately_from_a_rate_limit(
        self, owner_user, monkeypatch
    ):
        """§2.1: same advice for the user, different diagnosis in the logs."""
        monkeypatch.setattr(http, "_sleep", lambda _seconds: None)
        for _ in range(http.MAX_RETRIES + 1):
            responses.add(responses.GET, REPO_URL, json={}, status=502)

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "github_unavailable"
        assert caught.value.status_code == 503

    @responses.activate
    def test_a_revoked_token_asks_the_user_to_sign_in_again(self, owner_user):
        """Found by running the phase against a revoked token.

        GitHub answers 401 "Bad credentials". Before this, that fell through to
        github_unavailable — "try again in a few minutes" — which is advice
        that can never come true, because retrying does not un-revoke a token.
        """
        responses.add(responses.GET, REPO_URL, json={}, status=401)

        with pytest.raises(ApiError) as caught:
            validate_and_describe(owner_user, "github.com/expressjs/express")

        assert caught.value.code == "github_reauth_required"
        assert caught.value.status_code == 401
        assert len(responses.calls) == 1

    @responses.activate
    def test_a_user_without_a_stored_token_cannot_reach_anything(self, user):
        user.encrypted_github_token = ""
        user.save(update_fields=["encrypted_github_token"])

        with pytest.raises(ApiError) as caught:
            validate_and_describe(user, "github.com/expressjs/express")

        assert caught.value.code == "repo_inaccessible"
        assert len(responses.calls) == 0
