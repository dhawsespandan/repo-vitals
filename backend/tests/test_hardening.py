"""Phase 9's hardening sweep: throttles, log context, research-table exposure.

§10 Phase 9: "DRF throttles on auth + generation endpoints; structured logging
(request id, user id, scan id) with **assertions that no token/secret appears
in logs**; ... admin read-only for research tables."

The logging tests build a handler the way `settings.LOGGING` does — same
formatter string, same filters, same order — rather than exercising the filter
classes in isolation. The filters are already unit-tested in
`test_log_redaction.py`; what is untested by that, and what actually ships, is
the *configuration*: a format string referencing an attribute no filter sets
raises inside logging, where the symptom is the log line silently vanishing.
"""

from __future__ import annotations

import logging
import threading
from io import StringIO

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

from apps.common.logging import (
    REDACTED,
    ContextFilter,
    RedactSecretsFilter,
    bind,
    current_context,
)
from apps.common.middleware import HEADER
from apps.reports.models import ReportType
from apps.scanning.models import ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    ReportFactory,
    RepositoryFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db


class Captured:
    """A handler wired exactly as `settings.LOGGING` wires the console one."""

    def __init__(self) -> None:
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(
            logging.Formatter(settings.LOGGING["formatters"]["standard"]["format"])
        )
        # Order matters and is asserted by `test_a_token_is_redacted_even_with_context`:
        # `request_context` must run first because the formatter references the
        # attribute it sets.
        self.handler.addFilter(ContextFilter())
        self.handler.addFilter(RedactSecretsFilter())

    def __enter__(self) -> Captured:
        root = logging.getLogger()
        self._previous_level = root.level
        root.addHandler(self.handler)
        root.setLevel(logging.INFO)
        return self

    def __exit__(self, *exc) -> None:
        root = logging.getLogger()
        root.removeHandler(self.handler)
        root.setLevel(self._previous_level)

    @property
    def text(self) -> str:
        self.handler.flush()
        return self.stream.getvalue()


@pytest.fixture
def rate(monkeypatch):
    """Lower a throttle rate for one test.

    **`override_settings(REST_FRAMEWORK=...)` does not work here**, and fails
    silently, which is the trap worth recording. DRF binds
    `SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES`
    as a *class attribute at import time*; `api_settings.reload()` on
    `setting_changed` rebinds the settings object and leaves the class
    attribute pointing at the original dict. Measured directly: with
    `generation` overridden to "3/min", the class still read "20/min" and five
    POSTs produced no 429 at all. A throttle test written that way runs at the
    production rate and asserts nothing — the exact shape of `docs/decisions.md`
    §8.15, a control that was run and could not have failed.

    `monkeypatch.setitem` changes the dict the throttle actually reads, and
    restores it afterwards.
    """

    def set_rate(scope: str, value: str) -> None:
        monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, value)

    return set_rate


@pytest.fixture
def completed_scan(user):
    scan = ScanRunFactory(
        repository=RepositoryFactory(user=user),
        triggered_by=user,
        status=ScanStatus.COMPLETED.value,
    )
    return scan


# ── Throttles ───────────────────────────────────────────────────────────────


def test_the_configured_rates_are_the_ones_phase_9_chose():
    """The numbers, asserted where a change to them is visible in a diff."""
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    assert rates["generation"] == "20/min"
    assert rates["auth"] == "60/min"
    # No blanket throttle: the product's own polling loops are the heaviest
    # caller of the read routes, and a default class would eventually throttle
    # the product rather than an abuser.
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] == []


def test_the_generation_route_is_throttled(rate, auth_client, completed_scan):
    """The scope is wired to the view, at whatever rate is configured.

    Three allowed then a 429, against a rate of three — the assertion is about
    the scope, not about twenty being the right number. Twenty is asserted
    above, where it reads as a decision rather than as a loop bound.

    What the allowed three answer is deliberately not asserted: it depends on
    whether the machine running the suite has a `GROQ_API_KEY` (503 without
    one, 202 then 409 with). The throttle runs in `initial()`, before the
    handler, so it bounds the request rate whatever the view then decides.
    """
    rate("generation", "3/min")
    url = reverse("scan-combined-report", kwargs={"scan_id": completed_scan.pk})

    statuses = [auth_client.post(url).status_code for _ in range(4)]

    assert 429 not in statuses[:3]
    assert statuses[3] == 429


def test_the_per_dependency_route_shares_the_budget(
    rate, auth_client, completed_scan, user
):
    """Both generation routes are one scope, because both reach one wallet.

    Two scopes would mean an abuser gets two budgets for the same resource —
    the model, and the eight threads that call it.
    """
    rate("generation", "2/min")
    occurrence = DependencyOccurrenceFactory(
        manifest=ManifestFileFactory(scan=completed_scan), is_flagged=True
    )
    combined = reverse("scan-combined-report", kwargs={"scan_id": completed_scan.pk})
    per_dependency = reverse("dependency-report", kwargs={"dependency_id": occurrence.pk})

    first = auth_client.post(combined).status_code
    second = auth_client.post(per_dependency).status_code
    third = auth_client.post(per_dependency).status_code

    assert 429 not in (first, second)
    assert third == 429


def test_the_session_route_is_throttled(rate, api_client):
    """Unauthenticated too — which is the case that needs the bound.

    DRF keys an anonymous bucket on the client IP, which is why the shipped
    rate is 60/min rather than something tighter: one office behind one NAT is
    one bucket.
    """
    rate("auth", "2/min")
    url = reverse("auth-session")

    statuses = [api_client.get(url).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_reading_a_stored_report_is_never_throttled(rate, auth_client, completed_scan):
    """The read path carries the UI's polling and must not be rationed.

    At a rate of one per minute — a rate the generation route would refuse the
    second request at — ten reads still succeed, because the read routes carry
    no `throttle_scope` at all. A report panel polls this route every few
    seconds while a generation runs.
    """
    rate("generation", "1/min")
    rate("auth", "1/min")
    report = ReportFactory(scan=completed_scan)
    url = reverse("report-detail", kwargs={"report_id": report.pk})

    statuses = {auth_client.get(url).status_code for _ in range(10)}

    assert statuses == {200}


def test_a_throttled_request_answers_in_the_standard_envelope(
    rate, auth_client, completed_scan
):
    """`{code, message}` like every other failure — the client branches on code."""
    rate("generation", "1/min")
    url = reverse("scan-combined-report", kwargs={"scan_id": completed_scan.pk})
    auth_client.post(url)

    response = auth_client.post(url)

    assert response.status_code == 429
    assert response.json()["code"] == "throttled"
    # DRF's own detail, kept deliberately: it names the wait, which is the one
    # actionable thing a throttled caller can be told.
    assert "throttled" in response.json()["message"].lower()


# ── Structured logging ──────────────────────────────────────────────────────


def test_a_request_stamps_every_line_it_writes(auth_client, user, completed_scan):
    """Request id and user id, on a line written by a real view."""
    report = ReportFactory(scan=completed_scan, fixes_json=[])
    url = reverse("report-download", kwargs={"report_id": report.pk})

    with Captured() as captured:
        response = auth_client.get(url + "?fmt=md")

    assert response.status_code == 200
    # `views.py` logs "Report ... downloaded as md." on this path.
    assert "downloaded as md" in captured.text
    assert f"user_id={user.pk}" in captured.text
    assert "request_id=" in captured.text


def test_the_response_carries_the_id_the_logs_used(auth_client, completed_scan):
    """Otherwise the id is greppable and nobody knows which one to grep for."""
    report = ReportFactory(scan=completed_scan, fixes_json=[])
    url = reverse("report-download", kwargs={"report_id": report.pk})

    with Captured() as captured:
        response = auth_client.get(url + "?fmt=json")

    assert f"request_id={response[HEADER]}" in captured.text


def test_an_inbound_request_id_is_ignored(auth_client, completed_scan):
    """A client-chosen id is a client-chosen string in every line of the log.

    Honouring `X-Request-ID` is a common convenience; a newline inside it
    forges a log entry, and there is no upstream tracing system here whose id
    would be worth adopting.
    """
    report = ReportFactory(scan=completed_scan, fixes_json=[])
    url = reverse("report-download", kwargs={"report_id": report.pk})

    response = auth_client.get(
        url + "?fmt=json", HTTP_X_REQUEST_ID="injected\nWARNING forged line"
    )

    assert response[HEADER] != "injected\nWARNING forged line"
    assert "\n" not in response[HEADER]


def test_an_anonymous_request_has_no_user_id(api_client):
    with Captured() as captured:
        api_client.get(reverse("auth-session"))
        logging.getLogger("repovitals.test").info("anonymous line")

    assert "user_id=" not in captured.text


def test_a_line_outside_any_request_is_unchanged():
    """No empty brackets on startup lines. `[- - -]` on every library message
    is how structured logging becomes noise nobody reads."""
    with Captured() as captured:
        logging.getLogger("repovitals.test").info("starting up")

    assert "starting up" in captured.text
    assert "[" not in captured.text.split("starting up")[0].split("repovitals.test")[-1]


def test_a_background_thread_binds_its_own_context_not_the_requests():
    """The reason the transport is `contextvars` rather than a thread-local.

    A `threading.Thread` starts with an empty context rather than a copy of its
    parent's, so a scan thread cannot inherit the request id of whoever pressed
    the button — which is correct, because it is no longer serving that
    request. It binds the one identifier that still applies.
    """
    seen: dict[str, dict] = {}

    def worker() -> None:
        with bind(scan_id="scan-42"):
            seen["inside"] = current_context()

    with bind(request_id="req-1", user_id="7"):
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        seen["outside"] = current_context()

    assert seen["inside"] == {"scan_id": "scan-42"}
    assert seen["outside"] == {"request_id": "req-1", "user_id": "7"}
    # And nothing leaks back out of the block.
    assert current_context() == {}


def test_a_token_is_redacted_even_with_context(user):
    """§10's "assertions that no token/secret appears in logs", through the
    real handler chain.

    Both filters run on one record here, in the order `settings.LOGGING` gives
    them. The order is not cosmetic: the formatter references `context`, so a
    chain that dropped the context filter would raise inside logging and the
    line would simply not appear — a failure that looks exactly like nothing
    being logged.
    """
    token = "gho_" + "c" * 36

    with Captured() as captured, bind(request_id="req-9", user_id=str(user.pk)):
        logging.getLogger("repovitals.test").info("calling with token=%s", token)

    assert token not in captured.text
    assert REDACTED in captured.text
    assert "request_id=req-9" in captured.text


def test_the_encrypted_token_never_reaches_a_log_line(user):
    """The at-rest form too: a row dump is the other way a token escapes."""
    with Captured() as captured:
        logging.getLogger("repovitals.test").warning(
            "row: %s", user.encrypted_github_token
        )

    assert user.encrypted_github_token not in captured.text
    assert REDACTED in captured.text


# ── No write surface over the research tables ───────────────────────────────
#
# §10 Phase 9 asks for "admin read-only for research tables". This codebase has
# no Django admin at all, which is that requirement met in its stronger form,
# and building one would have made the guarantee *weaker* rather than better:
# the `User` model extends `AbstractBaseUser` with no `is_staff` and no
# `has_perm`, so giving it an admin means adding `PermissionsMixin` — two join
# tables beyond §5.1's schema, and a password login to a product whose whole
# identity story is that GitHub owns identity. `docs/decisions.md` §9.7.
#
# What replaces the read-only ModelAdmin is these four assertions, which fail
# the moment any of that stops being true.


def test_there_is_no_admin_site():
    """The app is not installed, so there is no admin to make read-only.

    If this ever fails, §9.7's reasoning needs re-reading before the commit
    that installs it lands: the research tables are D9's permanent record, and
    an admin is a change form and a delete button over them.
    """
    assert "django.contrib.admin" not in settings.INSTALLED_APPS


def test_no_route_reaches_the_research_tables():
    """No serializer, no view, no URL — they are written by code and read by
    commands.

    Phase 10 adds a history *endpoint* over `scan_history`, filtered to
    `live_scan` rows; that is a curated read of one table, and this assertion
    will need updating to name it. Nothing today should match.
    """
    from django.urls import get_resolver

    names = {
        entry.name
        for entry in get_resolver().url_patterns
        if getattr(entry, "name", None)
    }

    assert not {name for name in names if "history" in name or "trace" in name}


def test_the_user_model_cannot_enter_an_admin_even_if_one_existed():
    """The second lock, and the reason the first one is cheap to keep.

    Django's `AdminSite.has_permission` reads `is_active and is_staff`, and
    every `ModelAdmin` permission check calls `has_perm`. `AbstractBaseUser`
    provides neither, and nothing in this project adds them — so no account
    this product can create is an account an admin would admit.
    """
    from apps.accounts.models import User

    arrival = User.objects.create_user(
        github_user_id=987654, github_username="oauth-arrival"
    )

    assert not hasattr(arrival, "is_staff")
    assert not hasattr(arrival, "has_perm")
    # And no password to log in with. The manager is the only creation path —
    # there is no signup form — and it sets the password unusable on the way in.
    assert not arrival.has_usable_password()


def test_the_permanent_tables_have_no_inbound_foreign_key():
    """D9 in the schema: nothing can cascade into the research record.

    The admin was one of two ways these rows could be destroyed; this is the
    other, and it is the one a cascade added three phases from now would open
    silently. `dependency_history` points at `scan_history` and that is the
    only edge — within the app, and pointing inward.
    """
    from django.apps import apps as django_apps

    from apps.research import models as research_models

    permanent = {
        model
        for model in django_apps.get_models()
        if model.__module__ == research_models.__name__
    }
    assert len(permanent) == 3

    offenders = []
    for model in django_apps.get_models():
        if model in permanent:
            continue
        for field in model._meta.get_fields():
            if field.is_relation and field.related_model in permanent:
                offenders.append(f"{model.__name__}.{field.name}")

    assert not offenders, f"a relation reaches the permanent tables: {offenders}"


def test_the_occurrence_graph_is_unaffected_by_any_of_this(user):
    """A sanity anchor: the hardening changed no product behaviour.

    Every test above is about a control. This one is about the thing the
    controls sit around — a scan still has its manifests, occurrences and
    reports, reachable the way the product reaches them.
    """
    scan = ScanRunFactory(
        repository=RepositoryFactory(user=user),
        triggered_by=user,
        status=ScanStatus.COMPLETED.value,
    )
    occurrence = DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=scan))
    report = ReportFactory(
        scan=scan, dependency=occurrence, report_type=ReportType.PER_DEPENDENCY.value
    )

    assert report.scan.repository.user == user
    assert occurrence.manifest.scan == scan
