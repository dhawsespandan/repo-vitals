import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_reports_ok_and_touches_the_database(api_client):
    response = api_client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_health_needs_no_authentication(api_client):
    """The keepalive cron is unauthenticated; it must stay that way (§4.2)."""
    assert api_client.get("/api/health/").status_code == 200
