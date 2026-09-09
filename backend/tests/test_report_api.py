"""The two Phase 7 routes, and the standing BOLA rule they join.

§5.5:

    POST /api/scans/{id}/reports/combined/   200 cached | 202 started | 409 busy
    GET  /api/reports/{id}/

Plus the addition to the scan payload (`combinedReport`, `docs/decisions.md`
§7.7) that lets a page open a cached report without asking the POST route —
which would bill a generation for opening a tab.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.reports.llm.groq_client import LlmCall
from apps.reports.models import Report, ReportStatus
from apps.reports.services import run_combined
from apps.scanning.models import ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    PackageFactory,
    ReportFactory,
    RepositoryFactory,
    ScanRunFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

WITH_KEY = override_settings(GROQ_API_KEY="gsk_test", GROQ_MODEL="test-model")


@pytest.fixture
def stub_model(monkeypatch):
    calls: list[str] = []

    def complete(system: str, user: str) -> LlmCall:
        calls.append(user)
        return LlmCall(
            content=json.dumps(
                {
                    "summary_md": "Upgrade lodash first.",
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
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1,
            requests=1,
        )

    monkeypatch.setattr("apps.reports.combined.complete_json", complete)
    return calls


def scan_for(user):
    scan = ScanRunFactory(
        repository=RepositoryFactory(user=user),
        triggered_by=user,
        risk_score=Decimal("62.00"),
        classification="medium",
    )
    DependencyOccurrenceFactory(
        manifest=ManifestFileFactory(scan=scan),
        package=PackageFactory(package_name="lodash"),
        resolved_version="4.17.19",
        is_flagged=True,
        risk_component_score=Decimal("48.00"),
    )
    return scan


def combined_url(scan):
    return reverse("scan-combined-report", args=[scan.pk])


def report_url(report):
    return reverse("report-detail", args=[report.pk])


# ── POST ───────────────────────────────────────────────────────────────────


@WITH_KEY
def test_a_first_request_is_accepted_and_queued(auth_client, user, stub_model):
    response = auth_client.post(combined_url(scan_for(user)))

    assert response.status_code == 202
    assert response.data["status"] == ReportStatus.QUEUED.value
    assert response.data["type"] == "combined"
    assert response.data["summaryMd"] is None


@WITH_KEY
def test_a_cached_report_answers_200_and_calls_nothing(auth_client, user, stub_model):
    """The mentor-demo sentence, as a status code: "click again: instant"."""
    scan = scan_for(user)
    first = auth_client.post(combined_url(scan))
    run_combined(first.data["id"])
    assert len(stub_model) == 1

    second = auth_client.post(combined_url(scan))

    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert second.data["summaryMd"] == "Upgrade lodash first."
    assert len(stub_model) == 1


@WITH_KEY
def test_a_generation_already_running_answers_409_with_its_id(
    auth_client, user, stub_model
):
    scan = scan_for(user)
    first = auth_client.post(combined_url(scan))

    second = auth_client.post(combined_url(scan))

    assert second.status_code == 409
    assert second.data["code"] == "report_generating"
    # The id is in the body so the client can poll rather than guess.
    assert second.data["reportId"] == first.data["id"]


@WITH_KEY
def test_an_unfinished_scan_is_refused(auth_client, user, stub_model):
    scan = ScanRunFactory(
        repository=RepositoryFactory(user=user),
        triggered_by=user,
        status=ScanStatus.RUNNING.value,
        completed_at=None,
    )

    response = auth_client.post(combined_url(scan))

    assert response.status_code == 409
    assert response.data["code"] == "scan_not_reportable"
    assert len(stub_model) == 0


def test_a_deployment_without_a_generator_answers_503(auth_client, user):
    with override_settings(GROQ_API_KEY=""):
        response = auth_client.post(combined_url(scan_for(user)))

    assert response.status_code == 503
    assert response.data["code"] == "reports_unavailable"
    # And the reader is not told which setting is missing.
    assert "GROQ" not in response.data["message"]
    assert Report.objects.count() == 0


# ── GET ────────────────────────────────────────────────────────────────────


def test_the_detail_route_serves_the_stored_row(auth_client, user):
    report = ReportFactory(
        scan=scan_for(user),
        summary_text="Two things to do.",
        fixes_json=[
            {
                "package": "lodash",
                "manifest_path": "package.json",
                "ecosystem": "npm",
                "current_version": "4.17.19",
                "fix_type": "upgrade",
                "target_version": "4.17.21",
                "replacement_package": None,
                "cves": ["CVE-2021-23337"],
                "severity": "high",
                "priority": 1,
            }
        ],
    )

    response = auth_client.get(report_url(report))

    assert response.status_code == 200
    assert response.data["summaryMd"] == "Two things to do."
    # §5.8's own spelling, not camelCase: this is the download payload too.
    assert response.data["fixes"][0]["current_version"] == "4.17.19"
    assert response.data["fixes"][0]["fix_type"] == "upgrade"


def test_a_failed_report_carries_its_message(auth_client, user):
    report = ReportFactory(
        scan=scan_for(user),
        status=ReportStatus.FAILED.value,
        summary_text=None,
        generated_at=None,
        error_message="We couldn't reach the report service.",
    )

    response = auth_client.get(report_url(report))

    assert response.data["status"] == "failed"
    assert response.data["errorMessage"].startswith("We couldn't reach")


# ── The scan payload's report state ────────────────────────────────────────


def test_a_scan_with_no_report_says_so(auth_client, user):
    response = auth_client.get(reverse("scan-detail", args=[scan_for(user).pk]))

    assert response.data["combinedReport"] is None


def test_a_scan_with_a_report_carries_enough_to_open_it(auth_client, user):
    scan = scan_for(user)
    report = ReportFactory(scan=scan)

    response = auth_client.get(reverse("scan-detail", args=[scan.pk]))

    assert response.data["combinedReport"]["id"] == str(report.pk)
    assert response.data["combinedReport"]["status"] == "completed"
    assert response.data["combinedReport"]["generatedAt"] is not None
    # And not the body — that has its own route (§5.5).
    assert "summaryMd" not in response.data["combinedReport"]


# ── BOLA (§11) ─────────────────────────────────────────────────────────────


@WITH_KEY
def test_a_foreign_scan_cannot_be_made_to_generate(auth_client, stub_model):
    stranger = UserFactory()

    response = auth_client.post(combined_url(scan_for(stranger)))

    assert response.status_code == 404
    assert Report.objects.count() == 0
    assert len(stub_model) == 0


def test_a_foreign_report_is_not_readable(auth_client):
    stranger = UserFactory()
    report = ReportFactory(scan=scan_for(stranger), summary_text="Their findings.")

    response = auth_client.get(report_url(report))

    assert response.status_code == 404
    assert "Their findings" not in json.dumps(response.data)


def test_both_routes_require_a_session(api_client, user):
    scan = scan_for(user)
    report = ReportFactory(scan=scan)

    assert api_client.post(combined_url(scan)).status_code == 403
    assert api_client.get(report_url(report)).status_code == 403


def test_a_404_does_not_name_the_orm(auth_client):
    """§5.12: the panel renders `error.message` verbatim, so a 404 must not
    answer with Django's sentence about a model class."""
    stranger = UserFactory()
    report = ReportFactory(scan=scan_for(stranger))

    response = auth_client.get(report_url(report))

    assert "Report" not in response.data["message"]
    assert response.data["message"] == "We couldn't find that."
