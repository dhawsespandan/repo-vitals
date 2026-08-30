"""The two enrichment clients: npm's registry, and OSV.

The CVSS cases are checked against the specification's own published worked
examples rather than against what this implementation happens to produce.
That distinction matters more here than anywhere else in the codebase: §5.2
multiplies `cvss_max / 10` straight into the score, Phase 5's whole purpose is
to show that arithmetic to a reader, and a base-score formula that is subtly
wrong would be invisible in every test that checked it against itself.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import responses

from apps.common import http
from apps.scanning import osv
from apps.scanning.adapters.registry_clients import NpmRegistryClient
from apps.scanning.models import Severity

NPM_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "npm"
OSV_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "osv"


def npm_doc(name: str) -> dict:
    return json.loads((NPM_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def osv_doc(name: str) -> dict:
    return json.loads((OSV_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    """`responses` patches the adapter, so a session cached across tests lies."""
    monkeypatch.setattr(http, "_local", type(http._local)())


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)


def register(name: str) -> None:
    responses.add(
        responses.GET,
        f"https://registry.npmjs.org/{name}",
        json=npm_doc(name),
        status=200,
    )


class TestNpmRegistryClient:
    @responses.activate
    def test_the_document_is_fetched_once_per_package_per_run(self):
        """A monorepo asking about one package from nine manifests: one call."""
        register("express")
        client = NpmRegistryClient()

        for _ in range(9):
            client.facts("express", "4.17.1")

        assert len(responses.calls) == 1

    @responses.activate
    def test_staleness_is_measured_from_the_packages_latest_release(self, settings):
        """Not from the resolved version's release date.

        The signal answers "is anyone still maintaining this?", which is a
        question about the package. An old pinned version of an actively
        released package is a different problem with a different remedy, and
        `versions_behind_*` is where that one is recorded.
        """
        register("express")

        facts = NpmRegistryClient().facts("express", "4.16.0")

        # 4.19.2 shipped 2024-03-25; 4.16.0 shipped in 2017.
        assert facts.latest_release_at.year == 2024
        assert facts.staleness_days is not None
        assert facts.staleness_days < 3000

    @responses.activate
    def test_versions_behind_is_counted_against_the_assessed_version(self):
        register("express")

        facts = NpmRegistryClient().facts("express", "4.16.0")

        # Above 4.16.0 within major 4: minors 17, 18, 19. No major above 4
        # (5.0.0-beta.1 is a prerelease and does not count).
        assert (facts.versions_behind_major, facts.versions_behind_minor) == (0, 3)

    @responses.activate
    def test_deprecation_is_read_from_the_resolved_version_not_the_latest(self):
        """4.17.19 is deprecated; 4.17.21 is not. Which one we ask about decides."""
        register("lodash")
        client = NpmRegistryClient()

        old = client.facts("lodash", "4.17.19")
        current = client.facts("lodash", "4.17.21")

        assert old.is_deprecated
        assert "command injection" in old.deprecation_reason
        assert not current.is_deprecated
        assert current.deprecation_reason is None

    @responses.activate
    def test_a_boolean_deprecation_is_an_empty_reason_not_an_absent_one(self):
        """npm accepts `"deprecated": true`. That is a deprecation with no text.

        D2 makes the *information content* of this text S3's variable, so a
        deprecation carrying nothing has to be distinguishable from no
        deprecation at all.
        """
        register("left-pad")

        facts = NpmRegistryClient().facts("left-pad", "1.3.0")

        assert facts.is_deprecated
        assert facts.deprecation_reason == ""

    @responses.activate
    def test_a_range_with_no_lockfile_is_assessed_against_latest(self):
        register("express")

        facts = NpmRegistryClient().facts("express", None)

        assert facts.assessed_version == "4.19.2"
        assert facts.latest_version == "4.19.2"

    @responses.activate
    def test_a_package_the_registry_never_published_is_not_found(self):
        responses.add(
            responses.GET, "https://registry.npmjs.org/ghost-pkg", json={}, status=404
        )

        facts = NpmRegistryClient().facts("ghost-pkg", "1.0.0")

        assert facts.not_found
        assert not facts.unavailable

    @responses.activate
    def test_an_unreachable_registry_is_not_the_same_as_a_missing_package(self):
        """One is a fact about the package; the other about our afternoon."""
        responses.add(
            responses.GET, "https://registry.npmjs.org/express", json={}, status=503
        )

        facts = NpmRegistryClient().facts("express", "4.17.1")

        assert facts.unavailable
        assert not facts.not_found

    @responses.activate
    def test_a_scoped_name_is_one_path_segment(self):
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/@scope%2Fpkg",
            json={"dist-tags": {"latest": "1.0.0"}, "versions": {"1.0.0": {}}},
            status=200,
        )

        facts = NpmRegistryClient().facts("@scope/pkg", "1.0.0")

        assert facts.latest_version == "1.0.0"

    @responses.activate
    def test_the_registry_url_stored_is_the_page_a_person_would_open(self):
        register("express")

        facts = NpmRegistryClient().facts("express", "4.17.1")

        assert facts.registry_url == "https://www.npmjs.com/package/express"


class TestCvssArithmetic:
    """CVSS v3.1 §8.1, checked against the specification's worked examples."""

    @pytest.mark.parametrize(
        ("vector", "expected"),
        [
            ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1),
            ("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H", 8.8),
            ("CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H", 7.8),
            ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),
            ("CVSS:3.0/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:L", 3.7),
            ("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:H/A:N", 5.9),
        ],
    )
    def test_base_scores_match_the_specification(self, vector, expected):
        assert osv.cvss_v3_base_score(vector) == expected

    def test_a_vector_with_no_impact_scores_zero(self):
        vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N"

        assert osv.cvss_v3_base_score(vector) == 0.0

    @pytest.mark.parametrize(
        "vector",
        [
            "",
            "garbage",
            "CVSS:2.0/AV:N/AC:L/Au:N/C:P/I:P/A:P",
            "CVSS:3.1/AV:N/AC:L",
            "CVSS:3.1/AV:X/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        ],
    )
    def test_an_unusable_vector_is_none_rather_than_a_guess(self, vector):
        """§5.2 has a policy for a missing CVSS. Inventing one has no policy."""
        assert osv.cvss_v3_base_score(vector) is None

    @pytest.mark.parametrize(
        ("score", "bucket"),
        [
            (9.8, Severity.CRITICAL.value),
            (9.0, Severity.CRITICAL.value),
            (8.9, Severity.HIGH.value),
            (7.0, Severity.HIGH.value),
            (6.9, Severity.MEDIUM.value),
            (4.0, Severity.MEDIUM.value),
            (3.9, Severity.LOW.value),
            (0.0, Severity.LOW.value),
        ],
    )
    def test_the_qualitative_scale_matches_the_specification(self, score, bucket):
        assert osv.severity_bucket(score) == bucket


class TestOsvDocuments:
    def test_every_stored_field_comes_off_the_document(self):
        vuln = osv.build_vulnerability(
            osv_doc("vuln_lodash_command_injection"), "lodash"
        )

        assert vuln.osv_id == "GHSA-35jh-r3h4-6jhm"
        assert vuln.cve_id == "CVE-2021-23337"
        assert vuln.severity == Severity.HIGH.value
        assert vuln.cvss_score == 9.8
        # D17: the disclosure date cannot be recovered once an advisory is
        # edited, and the backfill's as-of filter needs it.
        assert vuln.published_at.year == 2021
        assert vuln.affected_range == ">=0 <4.17.21"
        assert vuln.fixed_version == "4.17.21"
        assert vuln.source_url.endswith("GHSA-35jh-r3h4-6jhm")

    def test_the_publishers_own_severity_word_wins_over_the_derived_bucket(self):
        """They agree here; where they disagree, the analyst's word is stored.

        Only the label moves — §5.2's arithmetic consumes `cvss_score`, so a
        disagreement changes what the user reads and never the score.
        """
        document = osv_doc("vuln_lodash_command_injection")
        document["database_specific"]["severity"] = "MODERATE"

        vuln = osv.build_vulnerability(document, "lodash")

        assert vuln.severity == Severity.MEDIUM.value
        assert vuln.cvss_score == 9.8

    def test_an_advisory_with_no_severity_at_all_is_unknown_with_no_score(self):
        vuln = osv.build_vulnerability(osv_doc("vuln_no_severity"), "left-pad")

        assert vuln.severity == Severity.UNKNOWN.value
        assert vuln.cvss_score is None

    def test_an_advisory_with_no_fix_records_the_last_affected_version(self):
        vuln = osv.build_vulnerability(osv_doc("vuln_no_severity"), "left-pad")

        assert vuln.fixed_version is None
        assert vuln.affected_range == ">=0 <=1.3.0"

    def test_a_missing_reference_falls_back_to_the_osv_page(self):
        vuln = osv.build_vulnerability(
            {"id": "GHSA-abcd", "affected": []}, "anything"
        )

        assert vuln.source_url == "https://osv.dev/vulnerability/GHSA-abcd"


class TestOsvBatching:
    @responses.activate
    def test_queries_are_chunked_to_the_batch_size(self, monkeypatch):
        monkeypatch.setattr(osv, "BATCH_SIZE", 3)
        targets = [(f"pkg-{index}", "1.0.0") for index in range(7)]

        def answer(request):
            queries = json.loads(request.body)["queries"]
            return (200, {}, json.dumps({"results": [{} for _ in queries]}))

        responses.add_callback(
            responses.POST,
            "https://api.osv.dev/v1/querybatch",
            callback=answer,
            content_type="application/json",
        )

        osv.OsvClient().query_batch("npm", targets)

        assert len(responses.calls) == 3

    @responses.activate
    def test_the_same_package_at_two_versions_is_two_queries(self):
        """Two manifests pinning different versions have different answers."""
        captured: list[list] = []

        def answer(request):
            queries = json.loads(request.body)["queries"]
            captured.append(queries)
            return (200, {}, json.dumps({"results": [{} for _ in queries]}))

        responses.add_callback(
            responses.POST,
            "https://api.osv.dev/v1/querybatch",
            callback=answer,
            content_type="application/json",
        )

        osv.OsvClient().query_batch(
            "npm", [("lodash", "4.17.19"), ("lodash", "4.17.21")]
        )

        assert [query["version"] for query in captured[0]] == ["4.17.19", "4.17.21"]

    @responses.activate
    def test_a_result_count_mismatch_is_refused_rather_than_misaligned(self):
        """OSV answers positionally; a short list would shift every answer."""
        responses.add(
            responses.POST,
            "https://api.osv.dev/v1/querybatch",
            json={"results": [{}]},
            status=200,
        )

        with pytest.raises(ValueError):
            osv.OsvClient().query_batch(
                "npm", [("a", "1.0.0"), ("b", "1.0.0")]
            )

    @responses.activate
    def test_advisory_details_are_fetched_once_and_reused_across_packages(self):
        document = osv_doc("vuln_lodash_command_injection")
        responses.add(
            responses.GET,
            f"https://api.osv.dev/v1/vulns/{document['id']}",
            json=document,
            status=200,
        )
        client = osv.OsvClient()

        first = client.detail(document["id"], "lodash")
        second = client.detail(document["id"], "lodash")

        assert len(responses.calls) == 1
        assert first == second

    @responses.activate
    def test_an_advisory_id_with_no_detail_is_skipped_not_fatal(self):
        responses.add(
            responses.GET,
            "https://api.osv.dev/v1/vulns/GHSA-missing",
            json={},
            status=404,
        )

        assert osv.OsvClient().detail("GHSA-missing", "lodash") is None
