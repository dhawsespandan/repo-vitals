import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.scanning import background
from tests.factories import UserFactory


@pytest.fixture(autouse=True)
def empty_throttle_history():
    """Phase 9's throttles start every test with a clean bucket.

    DRF's `ScopedRateThrottle` counts in Django's cache, which is a process-wide
    LocMemCache here — so without this, request counts leak between tests and a
    file that exercises one endpoint thirty times fails on whichever test
    happens to be thirtieth. That failure would be real but about the previous
    tests, which is the worst kind.

    The throttles stay *on* in the suite rather than being disabled in test
    settings. A rate limit that only exists in production is a rate limit
    nobody has run: the one that matters is the one on the generation route,
    and its rate has to be wrong in a test before it is wrong on prod.
    """
    cache.clear()
    yield
    cache.clear()


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

    def record(target, *args, **kwargs):
        """Mirror `spawn`'s signature, including the keywords it ignores here.

        `scan_id` is Phase 9's log context for the thread, and there is no
        thread to give it to. Swallowing it keeps what the fixture records —
        `(target, args)` — the same shape every existing assertion reads.
        """
        spawned.append((target, args))

    monkeypatch.setattr(background, "spawn", record)
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
