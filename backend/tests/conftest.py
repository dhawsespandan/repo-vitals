import pytest
from rest_framework.test import APIClient

from apps.scanning import background
from tests.factories import UserFactory


@pytest.fixture(autouse=True)
def no_background_threads(monkeypatch):
    """Scans never reach a real thread in a test run.

    Registration triggers a scan (§10 Phase 3), so without this every test that
    registers a repository would spawn a thread that opens its own database
    connection outside the test's transaction, races the assertions, and spends
    the retry budget in real seconds against `responses`' refusals.

    The fixture records what *would* have been spawned, so a test can assert
    that a trigger happened without depending on when it finished. Tests that
    want the scan to actually run call `background.execute(...)` themselves —
    synchronously, in the test's own transaction, where its effects are
    inspectable.
    """
    spawned: list[tuple] = []
    monkeypatch.setattr(
        background, "spawn", lambda target, *args: spawned.append((target, args))
    )
    return spawned


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
