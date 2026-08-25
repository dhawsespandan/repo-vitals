import pytest
from rest_framework.test import APIClient

from tests.factories import UserFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def auth_client(api_client, user) -> APIClient:
    api_client.force_login(user)
    return api_client
