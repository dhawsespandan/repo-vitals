"""Session lifecycle: bootstrap, persistence across requests, logout."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_anonymous_session_is_a_200_not_an_error(api_client):
    """The SPA bootstraps from this endpoint; nobody-signed-in is normal."""
    response = api_client.get(reverse("auth-session"))

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}


@pytest.mark.django_db
def test_session_endpoint_plants_the_csrf_cookie(api_client):
    response = api_client.get(reverse("auth-session"))

    assert "csrftoken" in response.cookies


@pytest.mark.django_db
def test_authenticated_session_returns_the_github_identity(auth_client, user):
    response = auth_client.get(reverse("auth-session"))

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == user.github_username
    assert body["user"]["id"] == str(user.user_id)
    assert body["user"]["avatarUrl"] == user.avatar_url


@pytest.mark.django_db
def test_session_survives_repeated_requests(auth_client):
    """Covers the "refresh persists" line of the Phase 1 acceptance criteria."""
    for _ in range(3):
        assert auth_client.get(reverse("auth-session")).json()["authenticated"] is True


@pytest.mark.django_db
def test_logout_ends_the_session(auth_client):
    assert auth_client.post(reverse("auth-logout")).status_code == 204
    assert auth_client.get(reverse("auth-session")).json()["authenticated"] is False


@pytest.mark.django_db
def test_logout_requires_authentication(api_client):
    response = api_client.post(reverse("auth-logout"))

    assert response.status_code in (401, 403)
    assert "code" in response.json()


@pytest.mark.django_db
def test_logout_rejects_get(auth_client):
    """A GET logout would fire on any prefetch and break the back-nav guard."""
    response = auth_client.get(reverse("auth-logout"))

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


@pytest.mark.django_db
def test_errors_use_the_shared_envelope(api_client):
    response = api_client.post(reverse("auth-logout"))

    body = response.json()
    assert set(body) == {"code", "message"}
    assert isinstance(body["message"], str) and body["message"]
