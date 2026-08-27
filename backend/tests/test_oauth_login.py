"""The OAuth entry points and the login signal that captures the token.

The GitHub round-trip itself is not re-tested here — that is allauth's job and
it has its own suite. What is tested is everything RepoVitals adds on top: the
URL shapes §5.5 promises, the identity columns §5.1 requires, and the
encryption §11 requires.
"""

from types import SimpleNamespace

import pytest
from allauth.account.signals import user_logged_in
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin, SocialToken
from django.test import override_settings
from django.urls import resolve, reverse

from apps.accounts.adapters import GitHubSocialAccountAdapter
from apps.accounts.crypto import decrypt_token
from apps.accounts.models import User
from apps.accounts.oauth import SCOPES_ATTR, RepoVitalsGitHubOAuth2Adapter

EXTRA_DATA = {
    "id": 4242,
    "login": "arjun-dev",
    "name": "Arjun D",
    "email": "arjun@example.com",
    "avatar_url": "https://avatars.githubusercontent.com/u/4242",
}

TOKEN = "gho_" + "z" * 36


def test_oauth_urls_match_the_api_surface_spec():
    """§5.5 spells these exactly; allauth's own default callback path differs."""
    assert reverse("github_login") == "/api/auth/github/login/"
    assert reverse("github_callback") == "/api/auth/github/callback/"
    assert resolve("/api/auth/github/callback/").url_name == "github_callback"


def test_adapter_captures_the_granted_scope_string():
    adapter = RepoVitalsGitHubOAuth2Adapter.__new__(RepoVitalsGitHubOAuth2Adapter)

    token = adapter.parse_token(
        {"access_token": TOKEN, "scope": "repo,read:user", "token_type": "bearer"}
    )

    assert getattr(token, SCOPES_ATTR) == "repo,read:user"


def test_adapter_tolerates_a_response_without_scope():
    adapter = RepoVitalsGitHubOAuth2Adapter.__new__(RepoVitalsGitHubOAuth2Adapter)

    token = adapter.parse_token({"access_token": TOKEN})

    assert getattr(token, SCOPES_ATTR) == ""


@pytest.mark.django_db
def test_populate_user_fills_the_identity_columns():
    """github_user_id is NOT NULL, so it must be set before the first save."""
    sociallogin = SocialLogin(
        user=User(),
        account=SocialAccount(provider="github", uid="4242", extra_data=EXTRA_DATA),
    )

    populated = GitHubSocialAccountAdapter().populate_user(None, sociallogin, {})

    assert populated.github_user_id == 4242
    assert populated.github_username == "arjun-dev"
    assert populated.display_name == "Arjun D"
    assert populated.avatar_url == EXTRA_DATA["avatar_url"]


def _sociallogin(user, token_value=TOKEN, scopes="repo,read:user"):
    token = SocialToken(token=token_value)
    setattr(token, SCOPES_ATTR, scopes)
    return SimpleNamespace(
        account=SocialAccount(provider="github", uid="4242", extra_data=EXTRA_DATA),
        token=token,
        user=user,
    )


@pytest.mark.django_db
def test_login_signal_encrypts_and_stores_the_token(user):
    user_logged_in.send(
        sender=User, request=None, user=user, sociallogin=_sociallogin(user)
    )

    user.refresh_from_db()
    assert user.encrypted_github_token != TOKEN
    assert decrypt_token(user.encrypted_github_token) == TOKEN
    assert user.token_scopes == "repo,read:user"


@pytest.mark.django_db
def test_login_signal_refreshes_a_renamed_github_account(user):
    """Identity is the numeric id; a rename must update the row, not fork it."""
    user.github_user_id = 4242
    user.github_username = "old-name"
    user.save(update_fields=["github_user_id", "github_username"])

    user_logged_in.send(
        sender=User, request=None, user=user, sociallogin=_sociallogin(user)
    )

    user.refresh_from_db()
    assert user.github_username == "arjun-dev"
    assert user.github_user_id == 4242
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_login_signal_ignores_non_social_logins(user):
    before = user.encrypted_github_token

    user_logged_in.send(sender=User, request=None, user=user)

    user.refresh_from_db()
    assert user.encrypted_github_token == before


@override_settings(FRONTEND_URL="https://app.example.com")
def test_authentication_error_redirects_to_the_frontend_login_screen():
    """A failed GitHub login must never surface allauth's own HTML page.

    An earlier version of this hook only recorded the error on the request
    and returned None — a no-op, since ImmediateHttpResponse is the only
    documented way for this hook to short-circuit allauth's view. That let
    every OAuth failure fall through to allauth's generic 401 template
    instead of the SPA's login screen.
    """
    adapter = GitHubSocialAccountAdapter()

    with pytest.raises(ImmediateHttpResponse) as excinfo:
        adapter.on_authentication_error(
            request=None,
            provider=SimpleNamespace(id="github"),
            error="access_denied",
            exception=None,
            extra_context=None,
        )

    response = excinfo.value.response
    assert response.status_code == 302
    assert (
        response["Location"] == "https://app.example.com/login?error=github_oauth_failed"
    )
