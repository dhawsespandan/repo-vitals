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
from apps.scanning.adapters.registry_clients import (
    NpmRegistryClient,
    PypiRegistryClient,
)
from apps.scanning.models import Severity

NPM_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "npm"
PYPI_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "pypi"
OSV_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "osv"


def npm_doc(name: str) -> dict:
    return json.loads((NPM_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def pypi_doc(name: str) -> dict:
    return json.loads((PYPI_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


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


def register_pypi(name: str) -> None:
    responses.add(
        responses.GET,
        f"https://pypi.org/pypi/{name}/json",
        json=pypi_doc(name),
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
        vuln = osv.build_vulnerability(osv_doc("vuln_lodash_command_injection"), "lodash")

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
        vuln = osv.build_vulnerability({"id": "GHSA-abcd", "affected": []}, "anything")

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

        osv.OsvClient().query_batch("npm", [("lodash", "4.17.19"), ("lodash", "4.17.21")])

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
            osv.OsvClient().query_batch("npm", [("a", "1.0.0"), ("b", "1.0.0")])

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


class TestPackumentSizeFallback:
    """A packument too large for this tier still answers three of four questions.

    §8's memory budget is the constraint; §5.2's missing-value policy is what
    makes the degradation safe. Losing the `time` map costs `staleness_days`
    and nothing else, and an unknown staleness has a defined behaviour — the
    term is dropped and its weight redistributed — where a wrong one does not.
    """

    @responses.activate
    def test_an_oversized_packument_falls_back_to_the_abbreviated_form(self):
        from apps.scanning.adapters import registry_clients

        # First call (full) is over the cap; second (abbreviated) is not.
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/huge",
            body="x" * (registry_clients.MAX_PACKUMENT_BYTES + 1),
            status=200,
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/huge",
            json={
                "dist-tags": {"latest": "5.0.0"},
                "versions": {
                    "4.0.0": {"deprecated": "moved to 5"},
                    "5.0.0": {},
                },
                "modified": "2026-01-01T00:00:00.000Z",
            },
            status=200,
        )

        facts = NpmRegistryClient().facts("huge", "4.0.0")

        assert len(responses.calls) == 2
        assert responses.calls[1].request.headers["Accept"] == (
            registry_clients.ABBREVIATED_ACCEPT
        )
        # Still answered: latest, versions-behind, deprecation.
        assert facts.latest_version == "5.0.0"
        assert facts.versions_behind_major == 1
        assert facts.is_deprecated
        assert facts.deprecation_reason == "moved to 5"

    @responses.activate
    def test_the_fallback_reports_staleness_unknown_rather_than_guessing(self):
        """`modified` is present and deliberately not used.

        It moves when metadata is edited — a deprecation being added is enough
        — so reading it as a release date would report an abandoned package as
        freshly maintained. NULL means unknown, which §5.2 handles.
        """
        from apps.scanning.adapters import registry_clients

        responses.add(
            responses.GET,
            "https://registry.npmjs.org/huge",
            body="x" * (registry_clients.MAX_PACKUMENT_BYTES + 1),
            status=200,
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/huge",
            json={
                "dist-tags": {"latest": "5.0.0"},
                "versions": {"5.0.0": {}},
                "modified": "2026-01-01T00:00:00.000Z",
            },
            status=200,
        )

        facts = NpmRegistryClient().facts("huge", "5.0.0")

        assert facts.staleness_days is None
        assert facts.latest_release_at is None

    @responses.activate
    def test_an_abbreviated_document_also_over_the_cap_is_unavailable(self):
        """Not silently clean: a package this tier cannot read is unassessable."""
        from apps.scanning.adapters import registry_clients

        responses.add(
            responses.GET,
            "https://registry.npmjs.org/enormous",
            body="x" * (registry_clients.MAX_PACKUMENT_BYTES + 1),
            status=200,
            content_type="application/json",
        )
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/enormous",
            body="x" * (registry_clients.MAX_ABBREVIATED_BYTES + 1),
            status=200,
            content_type="application/json",
        )

        facts = NpmRegistryClient().facts("enormous", "1.0.0")

        assert facts.unavailable
        assert not facts.not_found

    @responses.activate
    def test_the_abbreviated_cap_is_wide_enough_for_typescript(self):
        """Measured: typescript abbreviates to 8.7 MB.

        A cap below that would make one of npm's most common dev dependencies
        permanently unassessable — a worse outcome than the memory it saves.
        """
        from apps.scanning.adapters import registry_clients

        assert registry_clients.MAX_ABBREVIATED_BYTES > 9 * 1024 * 1024


class TestPypiRegistryClient:
    """PyPI's answers, and the deprecation composite D2 builds out of two of them.

    The npm client reads one field for deprecation. This one reads two that
    make different claims -- a per-release yank (PEP 592) and a project-wide
    `Development Status :: 7 - Inactive` classifier -- and the tests keep them
    apart, because the whole point of D2 is that npm and PyPI carry different
    *information content* rather than different amounts of signal.
    """

    @responses.activate
    def test_the_document_is_fetched_once_per_package_per_run(self):
        register_pypi("django")
        client = PypiRegistryClient()

        for _ in range(9):
            client.facts("django", "4.2.11")

        assert len(responses.calls) == 1

    @responses.activate
    def test_three_spellings_of_one_project_are_one_lookup(self):
        """PEP 503 again, this time as a quota question.

        A monorepo writing `Django`, `django` and `DJANGO` in three manifests
        is one project. Caching under the spelling would fetch it three times
        and, worse, produce three `packages` rows for one dependency.
        """
        register_pypi("django")
        client = PypiRegistryClient()

        for spelling in ("Django", "django", "DJANGO"):
            client.facts(spelling, "4.2.11")

        assert len(responses.calls) == 1
        assert responses.calls[0].request.url.endswith("/pypi/django/json")

    @responses.activate
    def test_a_yanked_release_is_deprecated_with_its_reason_verbatim(self):
        """PyPI yanked Django 4.2.12 hours after shipping it. The reason is
        stored exactly as PyPI wrote it -- it is S3's information-content
        variable, so normalizing or shortening it would destroy the
        measurement (D2)."""
        register_pypi("django")

        facts = PypiRegistryClient().facts("django", "4.2.12")

        assert facts.is_deprecated
        assert facts.deprecation_reason == (
            "Release files have Windows end-of-line characters and are "
            "missing executable bits."
        )

    @responses.activate
    def test_the_yank_is_read_from_the_resolved_version_not_the_latest(self):
        """4.2.12 is yanked; 4.2.11 and the current release are not. Which
        version the lockfile resolved is what decides."""
        register_pypi("django")
        client = PypiRegistryClient()

        yanked = client.facts("django", "4.2.12")
        fine = client.facts("django", "4.2.11")

        assert yanked.is_deprecated
        assert not fine.is_deprecated
        assert fine.deprecation_reason is None

    @responses.activate
    def test_the_inactive_classifier_deprecates_every_version(self):
        """The other half of D2, and a different claim from a yank: nobody is
        maintaining this project at all. `oauth2client` has said so since 2018.
        """
        register_pypi("oauth2client")
        client = PypiRegistryClient()

        old = client.facts("oauth2client", "3.0.0")
        newest = client.facts("oauth2client", "4.1.3")

        assert old.is_deprecated and newest.is_deprecated
        assert old.deprecation_reason == "Development Status :: 7 - Inactive"

    @responses.activate
    def test_a_yank_with_no_stated_reason_stays_a_deprecation(self):
        """PEP 592 allows an empty `yanked_reason`, and npm's `"deprecated":
        true` is the same statement: a withdrawal carrying no text. Empty and
        absent are different answers, and only one of them means "not
        deprecated"."""
        document = pypi_doc("flask")
        latest = document["info"]["version"]
        document["releases"][latest][0]["yanked"] = True
        document["releases"][latest][0]["yanked_reason"] = None
        responses.add(
            responses.GET, "https://pypi.org/pypi/flask/json", json=document, status=200
        )

        facts = PypiRegistryClient().facts("flask", latest)

        assert facts.is_deprecated
        assert facts.deprecation_reason == ""

    @responses.activate
    def test_a_release_is_only_yanked_when_all_of_its_files_are(self):
        """pip's rule. A release with one withdrawn wheel and a good sdist is
        still installable, and calling it deprecated would flag a dependency
        nobody needs to act on."""
        document = pypi_doc("flask")
        latest = document["info"]["version"]
        good = dict(document["releases"][latest][0])
        withdrawn = {**good, "filename": "other.whl", "yanked": True}
        document["releases"][latest] = [good, withdrawn]
        responses.add(
            responses.GET, "https://pypi.org/pypi/flask/json", json=document, status=200
        )

        assert not PypiRegistryClient().facts("flask", latest).is_deprecated

    @responses.activate
    def test_staleness_is_measured_from_the_packages_latest_release(self):
        """The same reading `NpmRegistryClient` gives §5.1: an old pin of a
        maintained package is `versions_behind_*`, not staleness."""
        register_pypi("django")
        register_pypi("oauth2client")
        client = PypiRegistryClient()

        maintained = client.facts("django", "2.2")
        abandoned = client.facts("oauth2client", "4.1.3")

        # Django's newest release is days old even when the pin is from 2019.
        assert maintained.latest_release_at.year >= 2026
        assert maintained.staleness_days < 365
        # oauth2client last shipped in 2018 -- past §5.2's 1095-day cap and
        # well past the 730-day flag threshold.
        assert abandoned.latest_release_at.year == 2018
        assert abandoned.staleness_days > 1095

    @responses.activate
    def test_versions_behind_is_counted_against_the_assessed_version(self):
        register_pypi("django")

        facts = PypiRegistryClient().facts("django", "2.2")

        # Majors above 2 in the recorded releases: 3, 4 and 6. Within 2.2, one
        # patch above `2.2`: 2.2.28.
        assert facts.versions_behind_major == 3
        assert facts.versions_behind_patch == 1

    @responses.activate
    def test_a_range_is_assessed_against_the_latest_release(self):
        """`resolved_version=None` is the `range_latest_approx` path, and the
        client applies it because what counts as latest is an ecosystem
        question -- PyPI's answer involves yanked releases, npm's does not."""
        register_pypi("flask")

        facts = PypiRegistryClient().facts("flask", None)

        assert facts.assessed_version == facts.latest_version

    @responses.activate
    def test_a_package_pypi_never_published_is_not_found(self):
        """A definite answer about the package, and different from an outage:
        the scanner records `not_in_registry` rather than failing the scan."""
        responses.add(
            responses.GET,
            "https://pypi.org/pypi/nosuchpackage/json",
            json={"message": "Not Found"},
            status=404,
        )

        facts = PypiRegistryClient().facts("NoSuchPackage")

        assert facts.not_found
        assert not facts.unavailable

    @responses.activate
    def test_a_document_over_the_cap_is_an_outage_not_a_clean_package(self):
        """Measured headroom, not a squeeze: the largest document recorded was
        numpy at 3.45 MB. Past 8 MiB the row is unassessable -- never clean."""
        from apps.scanning.adapters import registry_clients

        responses.add(
            responses.GET,
            "https://pypi.org/pypi/enormous/json",
            body="x" * (registry_clients.MAX_PYPI_DOCUMENT_BYTES + 1),
            status=200,
            content_type="application/json",
        )

        facts = PypiRegistryClient().facts("enormous", "1.0.0")

        assert facts.unavailable
        assert not facts.not_found

    @responses.activate
    def test_the_stored_url_is_the_page_a_reader_can_open(self):
        register_pypi("django")

        facts = PypiRegistryClient().facts("Django", "4.2.11")

        assert facts.registry_url == "https://pypi.org/project/django/"


class TestOsvEcosystemNames:
    """OSV spells ecosystems its own way, and only one spelling answers."""

    @responses.activate
    def test_a_pypi_batch_is_sent_under_osvs_own_spelling(self):
        """`PyPI`, not `pypi`. OSV matches the string exactly and answers an
        unknown ecosystem with no vulnerabilities -- which is
        indistinguishable, downstream, from a clean repository."""
        responses.add(
            responses.POST,
            "https://api.osv.dev/v1/querybatch",
            json={"results": [{"vulns": [{"id": "GHSA-xxxx"}]}]},
            status=200,
        )

        found = osv.OsvClient().query_batch("pypi", [("django", "2.2")])

        sent = json.loads(responses.calls[0].request.body)
        assert sent["queries"][0]["package"]["ecosystem"] == "PyPI"
        assert found[("django", "2.2")] == ["GHSA-xxxx"]

    @responses.activate
    def test_an_npm_batch_is_unchanged_by_the_second_ecosystem(self):
        responses.add(
            responses.POST,
            "https://api.osv.dev/v1/querybatch",
            json={"results": [{}]},
            status=200,
        )

        osv.OsvClient().query_batch("npm", [("lodash", "4.17.19")])

        sent = json.loads(responses.calls[0].request.body)
        assert sent["queries"][0]["package"]["ecosystem"] == "npm"
