"""EPSS: collected behind `EPSS_ENABLED`, and inert in the formula (D3, §10 Phase 12).

Three properties, each the reason the flag is safe to turn on:

* off (the default), a scan makes no FIRST.org request at all;
* on, the probability lands on `dependency_vulnerabilities.epss_score` and
  **the score does not move** — asserted by scanning the same repository both
  ways and comparing every number;
* an EPSS outage never fails a scan, because nothing the product shows depends
  on it.

The payload shape is FIRST.org's, checked live on 2026-10-05.
"""

from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from apps.common import http
from apps.scanning import epss, scanner
from apps.scanning.models import DependencyOccurrence, DependencyVulnerability
from tests.test_corpus_scan import mock_everything, product_scan

EPSS_URL = "https://api.first.org/data/v1/epss"

KNOWN = {
    "CVE-2021-23337": "0.012340000",
    "CVE-2020-8203": "0.987650000",
}


@pytest.fixture(autouse=True)
def quiet_network(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)


def mock_epss(status: int = 200) -> list[list[str]]:
    """FIRST.org, answering for the CVEs it knows. Returns the batches asked."""
    asked: list[list[str]] = []

    def answer(request):
        if status != 200:
            return (status, {}, "{}")
        cves = parse_qs(urlparse(request.url).query)["cve"][0].split(",")
        asked.append(cves)
        data = [
            {"cve": cve, "epss": KNOWN[cve], "percentile": "0.5", "date": "2026-10-05"}
            for cve in cves
            if cve in KNOWN
        ]
        return (200, {}, json.dumps({"status": "OK", "data": data}))

    responses.add_callback(responses.GET, EPSS_URL, callback=answer)
    return asked


class TestTheClient:
    @responses.activate
    def test_it_batches_and_parses_to_the_columns_precision(self):
        asked = mock_epss()
        ids = [f"CVE-2020-{n:04d}" for n in range(1, 121)] + list(KNOWN)

        found = epss.EpssClient().scores(ids)

        assert [len(batch) for batch in asked] == [50, 50, 22]
        assert found == {
            "CVE-2021-23337": Decimal("0.01234"),
            "CVE-2020-8203": Decimal("0.98765"),
        }

    @responses.activate
    def test_an_unknown_cve_is_absent_not_zero(self):
        mock_epss()
        assert epss.EpssClient().scores(["CVE-1999-0001"]) == {}

    @responses.activate
    def test_each_id_is_asked_once_per_run(self):
        asked = mock_epss()
        client = epss.EpssClient()
        client.scores(list(KNOWN))
        client.scores(list(KNOWN))
        assert len(asked) == 1

    def test_only_cve_ids_are_sent(self):
        assert epss.EpssClient().scores(["GHSA-xxxx-yyyy-zzzz", "", "PYSEC-1"]) == {}

    @pytest.mark.parametrize("raw", ["-0.1", "1.5", "NaN", "abc", None])
    def test_a_value_outside_a_probability_is_dropped(self, raw):
        assert epss._probability(raw) is None

    def test_first_org_is_on_the_allowlist(self):
        assert "api.first.org" in http.ALLOWED_HOSTS


@pytest.mark.django_db
class TestTheFlag:
    @responses.activate
    def test_off_by_default_and_no_request_is_made(self, user, settings):
        assert settings.EPSS_ENABLED is False
        mock_everything()
        product_scan(user)
        assert not any(EPSS_URL in call.request.url for call in responses.calls)
        assert not DependencyVulnerability.objects.exclude(epss_score=None).exists()

    @responses.activate
    def test_on_it_fills_the_column(self, user, settings):
        settings.EPSS_ENABLED = True
        mock_everything()
        mock_epss()
        product_scan(user)

        scores = dict(
            DependencyVulnerability.objects.exclude(cve_id=None).values_list(
                "cve_id", "epss_score"
            )
        )
        assert scores["CVE-2021-23337"] == Decimal("0.01234")
        assert scores["CVE-2020-8203"] == Decimal("0.98765")

    @responses.activate
    def test_on_or_off_the_score_is_identical(self, user, settings):
        """D3: collected, never scored. The whole repository and every
        occurrence's component score must be the same number both ways."""
        mock_everything()
        mock_epss()

        settings.EPSS_ENABLED = False
        off = product_scan(user)
        off_rows = sorted(
            DependencyOccurrence.objects.filter(manifest__scan=off).values_list(
                "manifest__manifest_path", "package__package_name", "risk_component_score"
            )
        )

        settings.EPSS_ENABLED = True
        from tests.factories import UserFactory

        on = product_scan(UserFactory())
        on_rows = sorted(
            DependencyOccurrence.objects.filter(manifest__scan=on).values_list(
                "manifest__manifest_path", "package__package_name", "risk_component_score"
            )
        )

        assert DependencyVulnerability.objects.exclude(epss_score=None).exists()
        assert (on.risk_score, on.classification) == (off.risk_score, off.classification)
        assert on_rows == off_rows

    @responses.activate
    def test_an_epss_outage_does_not_fail_the_scan(self, user, settings):
        settings.EPSS_ENABLED = True
        mock_everything()
        mock_epss(status=503)

        scan = product_scan(user)

        assert scan.risk_score is not None
        assert not DependencyVulnerability.objects.exclude(epss_score=None).exists()


def test_enrichment_leaves_advisories_without_a_cve_alone():
    from apps.scanning.osv import Vulnerability

    pooled = scanner.PooledOccurrence(plan=None, ecosystem="npm", spec=None)
    pooled.vulnerabilities = [Vulnerability(osv_id="GHSA-1"), Vulnerability(osv_id="X")]

    class Never:
        def scores(self, ids):  # pragma: no cover - must not be reached
            raise AssertionError("asked FIRST.org about advisories with no CVE")

    scanner.enrich_from_epss([pooled], client=Never())
    assert [v.epss_score for v in pooled.vulnerabilities] == [None, None]
