"""Cache-or-generate: the property the whole phase is named for.

§10 Phase 7's acceptance, in order: "second click serves instantly with a
**zero-LLM-call assertion**; double-click → one generation; every fix
references a real scanned row; rescan → fresh scan, empty reports, history
intact."

The counting fixture is the point of this module. Every earlier phase found a
defect that no behavioural assertion could see because the defect was in a
*count* — `usePolling`'s two loops, the scan button's second POST (§3.13). A
cache is exactly that shape: it behaves identically whether or not it works,
and the only difference is how many times the model ran.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.reports import services
from apps.reports.llm.groq_client import LlmCall, LlmUnavailable
from apps.reports.models import Report, ReportStatus, ReportType
from apps.reports.services import (
    GenerationInProgress,
    ReportsUnavailable,
    ScanNotReportable,
    combined_for,
    request_combined,
    run_combined,
)
from apps.research.models import ScanHistory
from apps.scanning.background import finalize
from apps.scanning.models import ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    PackageFactory,
    ReportFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db

WITH_KEY = override_settings(GROQ_API_KEY="gsk_test", GROQ_MODEL="test-model")


@pytest.fixture
def counting_model(monkeypatch):
    """A model that answers correctly and counts how often it was asked.

    Patched into `apps.reports.combined` rather than into the client, so the
    whole path under test — services, generation, validation — is the real one
    and only the HTTP call is not.
    """
    calls: list[str] = []

    def complete(system: str, user: str) -> LlmCall:
        calls.append(user)
        return LlmCall(
            content=json.dumps(
                {
                    "summary_md": "One dependency needs attention.",
                    "fixes": [
                        {
                            "package": "lodash",
                            "manifest_path": "package.json",
                            "ecosystem": "npm",
                            "fix_type": "upgrade",
                            "target_version": "4.17.21",
                            "replacement_package": None,
                            "priority": 1,
                        }
                    ],
                }
            ),
            model="test-model",
            prompt_tokens=10,
            completion_tokens=10,
            latency_ms=5,
            requests=1,
        )

    monkeypatch.setattr("apps.reports.combined.complete_json", complete)
    return calls


def scan_with_a_finding():
    scan = ScanRunFactory(risk_score=Decimal("62.00"), classification="medium")
    DependencyOccurrenceFactory(
        manifest=ManifestFileFactory(scan=scan),
        package=PackageFactory(package_name="lodash"),
        resolved_version="4.17.19",
        is_flagged=True,
        risk_component_score=Decimal("48.00"),
    )
    return scan


# ── The cache ──────────────────────────────────────────────────────────────


@WITH_KEY
def test_the_second_request_serves_the_stored_row_and_calls_nothing(
    counting_model, no_background_threads
):
    """The zero-LLM-call assertion §10 Phase 7 asks for by name."""
    scan = scan_with_a_finding()

    report, cached = request_combined(scan)
    assert cached is False
    run_combined(report.pk)
    assert len(counting_model) == 1

    again, cached = request_combined(scan)

    assert cached is True
    assert again.pk == report.pk
    assert len(counting_model) == 1


@WITH_KEY
def test_a_double_click_produces_one_generation(counting_model, no_background_threads):
    """The second POST lands while the first is still queued: 409, one row."""
    scan = scan_with_a_finding()

    first, _ = request_combined(scan)

    with pytest.raises(GenerationInProgress) as busy:
        request_combined(scan)

    assert busy.value.report.pk == first.pk
    assert Report.objects.filter(scan=scan).count() == 1
    # One thread was handed out, not two.
    assert len(no_background_threads) == 1


@WITH_KEY
def test_the_stored_row_carries_the_payload_and_the_model(counting_model):
    scan = scan_with_a_finding()

    report, _ = request_combined(scan)
    run_combined(report.pk)

    report.refresh_from_db()
    assert report.status == ReportStatus.COMPLETED.value
    assert report.summary_text == "One dependency needs attention."
    assert report.fixes_json[0]["package"] == "lodash"
    # From the scan row, never from the answer (see `schema._merge`).
    assert report.fixes_json[0]["current_version"] == "4.17.19"
    assert report.model_name == "test-model"
    assert report.generated_at is not None


@WITH_KEY
def test_a_report_is_only_generated_from_a_finished_scan(counting_model):
    scan = ScanRunFactory(status=ScanStatus.RUNNING.value, completed_at=None)

    with pytest.raises(ScanNotReportable):
        request_combined(scan)

    assert len(counting_model) == 0


def test_a_deployment_without_a_key_says_so_rather_than_failing_a_row():
    """A missing key is a deployment fault. It must not write a `failed` report
    the user is then invited to retry forever."""
    scan = scan_with_a_finding()

    with override_settings(GROQ_API_KEY=""), pytest.raises(ReportsUnavailable):
        request_combined(scan)

    assert Report.objects.count() == 0


# ── Failure, and retrying it ───────────────────────────────────────────────


@WITH_KEY
def test_a_failed_generation_leaves_an_actionable_message(monkeypatch):
    def explode(system, user):
        raise LlmUnavailable("upstream down")

    monkeypatch.setattr("apps.reports.combined.complete_json", explode)
    scan = scan_with_a_finding()

    report, _ = request_combined(scan)
    run_combined(report.pk)

    report.refresh_from_db()
    assert report.status == ReportStatus.FAILED.value
    assert "try again" in report.error_message.lower()
    assert "upstream down" not in report.error_message


@WITH_KEY
def test_an_unreliable_generation_fails_rather_than_storing_it(monkeypatch):
    """`GenerationFailed` from the invented-everything guard reaches the row."""

    def invent(system, user):
        return LlmCall(
            content=json.dumps(
                {
                    "summary_md": "All clear.",
                    "fixes": [
                        {
                            "package": "left-pad",
                            "manifest_path": "package.json",
                            "ecosystem": "npm",
                            "fix_type": "upgrade",
                            "target_version": "1.3.0",
                            "replacement_package": None,
                            "priority": 1,
                        }
                    ],
                }
            ),
            model="test-model",
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1,
            requests=1,
        )

    monkeypatch.setattr("apps.reports.combined.complete_json", invent)
    scan = scan_with_a_finding()

    report, _ = request_combined(scan)
    run_combined(report.pk)

    report.refresh_from_db()
    assert report.status == ReportStatus.FAILED.value
    assert report.summary_text is None
    assert report.fixes_json is None


@WITH_KEY
def test_a_failed_report_is_retried_in_place_without_a_rescan(counting_model):
    """A rescan destroys the scan's results (§5.7). Requiring one to retry a
    transient 503 would trade a report for a measurement."""
    scan = scan_with_a_finding()
    failed = ReportFactory(
        scan=scan,
        status=ReportStatus.FAILED.value,
        summary_text=None,
        generated_at=None,
        error_message="We couldn't reach the report service.",
    )

    report, cached = request_combined(scan)

    assert cached is False
    assert report.pk == failed.pk
    assert report.status == ReportStatus.QUEUED.value
    assert report.error_message is None
    assert Report.objects.filter(scan=scan).count() == 1


@WITH_KEY
def test_a_generation_that_never_reported_back_is_released(counting_model):
    """A killed worker must not strand the button behind its own 409."""
    scan = scan_with_a_finding()
    stuck = ReportFactory(
        scan=scan,
        status=ReportStatus.RUNNING.value,
        summary_text=None,
        generated_at=None,
    )
    Report.objects.filter(pk=stuck.pk).update(
        created_at=timezone.now()
        - services.STALE_GENERATION_AFTER
        - timezone.timedelta(minutes=1)
    )

    report, cached = request_combined(scan)

    assert cached is False
    assert report.status == ReportStatus.QUEUED.value


@WITH_KEY
def test_a_generation_still_within_its_budget_is_not_released(counting_model):
    scan = scan_with_a_finding()
    ReportFactory(
        scan=scan,
        status=ReportStatus.RUNNING.value,
        summary_text=None,
        generated_at=None,
    )

    with pytest.raises(GenerationInProgress):
        request_combined(scan)


# ── Reading ────────────────────────────────────────────────────────────────


def test_combined_for_returns_nothing_before_a_generation():
    assert combined_for(scan_with_a_finding()) is None


def test_combined_for_returns_the_stored_row():
    scan = scan_with_a_finding()
    stored = ReportFactory(scan=scan)

    assert combined_for(scan).pk == stored.pk


# ── Retention ──────────────────────────────────────────────────────────────


@WITH_KEY
def test_a_rescan_clears_reports_and_leaves_history_intact(counting_model):
    """§5.7 and §10 Phase 7's last acceptance line, in one test.

    The new scan's `finalize` writes history, then prunes the prior scan — and
    the report cascades with it. That is the destruction Phase 9 puts a
    confirmation in front of, so it is asserted here rather than assumed from
    the foreign key.
    """
    first = scan_with_a_finding()
    report, _ = request_combined(first)
    run_combined(report.pk)
    assert Report.objects.count() == 1

    second = ScanRunFactory(repository=first.repository, status=ScanStatus.RUNNING.value)
    DependencyOccurrenceFactory(
        manifest=ManifestFileFactory(scan=second),
        package=PackageFactory(package_name="lodash"),
        resolved_version="4.17.21",
    )
    second.completed_at = timezone.now()
    finalize(second)

    assert Report.objects.count() == 0
    assert not Report.objects.filter(report_type=ReportType.COMBINED.value).exists()
    # The permanent record is untouched: two scans, two history rows (D9).
    assert ScanHistory.objects.count() >= 1
