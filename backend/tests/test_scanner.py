"""The scan orchestrator, end to end against a golden repository.

The fixtures are built so that the *wrong* implementations pass a naive test
and fail these ones:

* the root lockfile pins `express` and `lodash` below the newest release their
  manifest ranges allow, so a scanner that resolves ranges against the registry
  reports this repository clean;
* `lodash` appears in three manifests at two different versions, so a scanner
  that deduplicates by package name reports one occurrence and loses two;
* a vendored `node_modules/left-pad/package.json` sits in the tree, so a
  scanner that matches basenames without excluding vendor directories invents
  a fourth manifest.

Every external call is mocked through `responses`; nothing here touches the
network, and the background thread is stubbed out in `conftest.py`, so the
scan runs synchronously inside the test's own transaction.
"""

from __future__ import annotations

import base64
import json
import pathlib

import pytest
import responses

from apps.common import http
from apps.scanning import scanner
from apps.scanning.models import (
    DependencyOccurrence,
    DependencyVulnerability,
    ManifestFile,
    Resolution,
    ScanRun,
    Severity,
)
from tests.factories import RepositoryFactory

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

REPO_API = "https://api.github.com/repos/acme/shop"
TREE_API = f"{REPO_API}/git/trees/main"


def load(rel: str) -> dict:
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


def blob_response(rel: str) -> dict:
    """A GitHub blob envelope around a fixture file."""
    raw = (FIXTURES / rel).read_bytes()
    return {
        "sha": rel,
        "size": len(raw),
        "encoding": "base64",
        "content": base64.b64encode(raw).decode(),
    }


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)


@pytest.fixture
def repository(user):
    return RepositoryFactory(
        user=user, owner="acme", name="shop", full_name="acme/shop", default_branch="main"
    )


@pytest.fixture
def scan(repository):
    return ScanRun.objects.create(
        repository=repository,
        triggered_by=repository.user,
        trigger_type="initial",
        scoring_formula_version="unscored",
    )


def mock_github(tree: dict | None = None) -> None:
    responses.add(
        responses.GET,
        TREE_API,
        json=tree or load("github/tree_npm_monorepo.json"),
        status=200,
    )
    for sha, rel in (
        ("root-manifest", "manifests/root_package.json"),
        ("root-lock", "manifests/root_package_lock.json"),
        ("api-manifest", "manifests/api_package.json"),
        ("worker-manifest", "manifests/worker_package.json"),
        ("vendored", "manifests/api_package.json"),
    ):
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/{sha}",
            json=blob_response(rel),
            status=200,
        )


def mock_registry() -> None:
    for name in ("express", "lodash", "left-pad", "react", "typescript"):
        responses.add(
            responses.GET,
            f"https://registry.npmjs.org/{name}",
            json=load(f"npm/{name}.json"),
            status=200,
        )


def mock_osv(advisories: dict[tuple[str, str], list[str]] | None = None) -> None:
    """Answer `querybatch` positionally, then serve each advisory document."""
    found = advisories or {
        ("lodash", "4.17.19"): [
            "GHSA-35jh-r3h4-6jhm",
            "GHSA-p6mc-m468-83gg",
        ]
    }

    def answer(request):
        queries = json.loads(request.body)["queries"]
        results = []
        for query in queries:
            key = (query["package"]["name"], query["version"])
            ids = found.get(key, [])
            results.append({"vulns": [{"id": osv_id} for osv_id in ids]} if ids else {})
        return (200, {}, json.dumps({"results": results}))

    responses.add_callback(
        responses.POST,
        "https://api.osv.dev/v1/querybatch",
        callback=answer,
        content_type="application/json",
    )
    for name in (
        "vuln_lodash_command_injection",
        "vuln_lodash_prototype_pollution",
        "vuln_no_severity",
    ):
        document = load(f"osv/{name}.json")
        responses.add(
            responses.GET,
            f"https://api.osv.dev/v1/vulns/{document['id']}",
            json=document,
            status=200,
        )


def mock_everything() -> None:
    mock_github()
    mock_registry()
    mock_osv()


def occurrences(scan: ScanRun):
    return DependencyOccurrence.objects.filter(manifest__scan=scan).select_related(
        "manifest", "package"
    )


@pytest.mark.django_db
class TestGoldenRepository:
    @responses.activate
    def test_every_manifest_in_the_tree_is_read(self, scan):
        mock_everything()

        scanner.run_scan(scan)

        assert sorted(
            ManifestFile.objects.filter(scan=scan).values_list("manifest_path", flat=True)
        ) == [
            "package.json",
            "services/api/package.json",
            "services/worker/package.json",
        ]

    @responses.activate
    def test_a_vendored_manifest_is_not_one_of_them(self, scan):
        """A checked-in node_modules would otherwise become a fourth manifest."""
        mock_everything()

        scanner.run_scan(scan)

        paths = ManifestFile.objects.filter(scan=scan).values_list(
            "manifest_path", flat=True
        )
        assert not any("node_modules" in path for path in paths)

    @responses.activate
    def test_the_lockfile_path_is_recorded_only_where_one_was_read(self, scan):
        """It is the reason the rows below it say `lockfile` or `approximated`."""
        mock_everything()

        scanner.run_scan(scan)

        by_path = dict(
            ManifestFile.objects.filter(scan=scan).values_list(
                "manifest_path", "lockfile_path"
            )
        )
        assert by_path["package.json"] == "package-lock.json"
        assert by_path["services/api/package.json"] is None

    @responses.activate
    def test_the_lockfile_beats_the_range_and_that_is_what_finds_the_cve(self, scan):
        """`^4.17.0` allows the patched 4.17.21; the lockfile installs 4.17.19.

        If resolution ever falls back to the range here, this repository
        reports clean — which is the failure this whole product exists to
        prevent, and it is invisible from the outside.
        """
        mock_everything()

        scanner.run_scan(scan)

        root_lodash = occurrences(scan).get(
            manifest__manifest_path="package.json", package__package_name="lodash"
        )
        assert root_lodash.resolved_version == "4.17.19"
        assert root_lodash.resolution == Resolution.LOCKFILE.value
        assert root_lodash.vulnerability_count == 2
        assert root_lodash.highest_severity == Severity.HIGH.value
        assert float(root_lodash.cvss_max) == 9.8

    @responses.activate
    def test_a_range_without_a_lockfile_is_tagged_as_approximated(self, scan):
        mock_everything()

        scanner.run_scan(scan)

        react = occurrences(scan).get(package__package_name="react")
        assert react.resolved_version == "18.3.1"
        assert react.resolution == Resolution.RANGE_LATEST_APPROX.value

    @responses.activate
    def test_raw_signals_are_stored_even_where_nothing_consumes_them_yet(self, scan):
        """D17: `versions_behind_*` is not a formula term and is recorded anyway.

        It cannot be reconstructed after the fact — the registry moves on — and
        the research needs it as a covariate.
        """
        mock_everything()

        scanner.run_scan(scan)

        express = occurrences(scan).get(package__package_name="express")
        assert express.latest_version == "4.19.2"
        assert express.latest_release_at is not None
        assert express.staleness_days is not None
        assert express.versions_behind_minor == 2

    @responses.activate
    def test_deprecation_text_is_stored_verbatim(self, scan):
        """S3's independent variable is this text's information content (D2)."""
        mock_everything()

        scanner.run_scan(scan)

        root_lodash = occurrences(scan).get(
            manifest__manifest_path="package.json", package__package_name="lodash"
        )
        assert root_lodash.is_deprecated
        assert root_lodash.deprecation_reason == (
            "Versions below 4.17.21 are vulnerable to command injection; "
            "upgrade to 4.17.21."
        )

    @responses.activate
    def test_every_advisory_field_the_research_needs_is_written(self, scan):
        mock_everything()

        scanner.run_scan(scan)

        vuln = DependencyVulnerability.objects.get(osv_id="GHSA-35jh-r3h4-6jhm")
        assert vuln.cve_id == "CVE-2021-23337"
        assert float(vuln.cvss_score) == 9.8
        assert vuln.published_at.year == 2021
        assert vuln.fixed_version == "4.17.21"

    @responses.activate
    def test_the_scan_is_one_batch_call_and_one_fetch_per_distinct_advisory(self, scan):
        """§8: batching is what makes this fit a free tier at all."""
        mock_everything()

        scanner.run_scan(scan)

        batches = [call for call in responses.calls if "querybatch" in call.request.url]
        details = [call for call in responses.calls if "/v1/vulns/" in call.request.url]
        assert len(batches) == 1
        assert len(details) == 2

    @responses.activate
    def test_a_rescan_of_an_unchanged_repository_records_the_same_signals(
        self, repository
    ):
        """§4.4's determinism suite. Timestamps move; measurements do not."""
        mock_everything()

        def run_one():
            run = ScanRun.objects.create(
                repository=repository,
                triggered_by=repository.user,
                trigger_type="manual",
                scoring_formula_version="unscored",
            )
            scanner.run_scan(run)
            return sorted(
                occurrences(run).values_list(
                    "manifest__manifest_path",
                    "package__package_name",
                    "resolved_version",
                    "resolution",
                    "is_deprecated",
                    "vulnerability_count",
                    "highest_severity",
                    "is_unassessable",
                    "unassessable_reason",
                )
            )

        assert run_one() == run_one()


@pytest.mark.django_db
class TestMonorepoPooling:
    @responses.activate
    def test_the_same_package_in_three_manifests_is_three_rows(self, scan):
        """Three installations, three remediations — §5.3 counts them apart."""
        mock_everything()

        scanner.run_scan(scan)

        lodash = occurrences(scan).filter(package__package_name="lodash")
        assert lodash.count() == 3
        assert sorted(row.manifest.manifest_path for row in lodash) == [
            "package.json",
            "services/api/package.json",
            "services/worker/package.json",
        ]

    @responses.activate
    def test_they_carry_the_versions_their_own_manifest_resolves_to(self, scan):
        """The root's lockfile must not leak into a sibling that has none."""
        mock_everything()

        scanner.run_scan(scan)

        versions = {
            row.manifest.manifest_path: (row.resolved_version, row.resolution)
            for row in occurrences(scan).filter(package__package_name="lodash")
        }
        assert versions["package.json"] == ("4.17.19", Resolution.LOCKFILE.value)
        assert versions["services/worker/package.json"] == (
            "4.17.21",
            Resolution.PINNED.value,
        )
        assert versions["services/api/package.json"] == (
            "4.17.21",
            Resolution.RANGE_LATEST_APPROX.value,
        )

    @responses.activate
    def test_only_the_vulnerable_occurrence_carries_the_advisories(self, scan):
        """The point of counting them separately: one is broken, two are not."""
        mock_everything()

        scanner.run_scan(scan)

        counts = {
            row.manifest.manifest_path: row.vulnerability_count
            for row in occurrences(scan).filter(package__package_name="lodash")
        }
        assert counts == {
            "package.json": 2,
            "services/api/package.json": 0,
            "services/worker/package.json": 0,
        }

    @responses.activate
    def test_one_packages_row_is_shared_by_all_three_occurrences(self, scan):
        """`packages` is identity (§5.1); the volatile facts live per occurrence."""
        mock_everything()

        scanner.run_scan(scan)

        package_ids = {
            row.package_id
            for row in occurrences(scan).filter(package__package_name="lodash")
        }
        assert len(package_ids) == 1


@pytest.mark.django_db
class TestUnassessableOccurrences:
    @responses.activate
    def test_non_registry_specifiers_are_recorded_with_their_reasons(self, scan):
        mock_everything()

        scanner.run_scan(scan)

        reasons = {
            row.package.package_name: row.unassessable_reason
            for row in occurrences(scan).filter(is_unassessable=True)
        }
        assert reasons == {
            "shared-utils": "file_specifier",
            "internal-tool": "git_specifier",
        }

    @responses.activate
    def test_they_are_never_queried_against_a_registry_or_osv(self, scan):
        mock_everything()

        scanner.run_scan(scan)

        queried = json.loads(
            next(
                call.request.body
                for call in responses.calls
                if "querybatch" in call.request.url
            )
        )
        names = {query["package"]["name"] for query in queried["queries"]}
        assert "shared-utils" not in names
        assert "internal-tool" not in names

    @responses.activate
    def test_a_package_missing_from_the_registry_is_unassessable_not_clean(self, scan):
        mock_github()
        mock_osv()
        for name in ("express", "lodash", "react", "typescript"):
            responses.add(
                responses.GET,
                f"https://registry.npmjs.org/{name}",
                json=load(f"npm/{name}.json"),
                status=200,
            )
        responses.add(
            responses.GET, "https://registry.npmjs.org/left-pad", json={}, status=404
        )

        scanner.run_scan(scan)

        left_pad = occurrences(scan).get(package__package_name="left-pad")
        assert left_pad.is_unassessable
        assert left_pad.unassessable_reason == scanner.REASON_NOT_IN_REGISTRY


@pytest.mark.django_db
class TestFailureHandling:
    @responses.activate
    def test_one_malformed_manifest_does_not_cost_the_others_their_scan(self, scan):
        mock_registry()
        mock_osv()
        responses.add(
            responses.GET,
            TREE_API,
            json=load("github/tree_npm_monorepo.json"),
            status=200,
        )
        for sha, rel in (
            ("root-manifest", "manifests/root_package.json"),
            ("root-lock", "manifests/root_package_lock.json"),
            ("worker-manifest", "manifests/worker_package.json"),
        ):
            responses.add(
                responses.GET,
                f"{REPO_API}/git/blobs/{sha}",
                json=blob_response(rel),
                status=200,
            )
        broken = base64.b64encode(b"{ not json").decode()
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/api-manifest",
            json={"encoding": "base64", "content": broken, "size": 10},
            status=200,
        )

        scanner.run_scan(scan)

        paths = set(
            ManifestFile.objects.filter(scan=scan).values_list("manifest_path", flat=True)
        )
        assert "services/api/package.json" not in paths
        assert "package.json" in paths

    @responses.activate
    def test_a_revoked_token_says_so_rather_than_asking_for_a_retry(self, scan):
        """A retry cannot un-revoke a token; the message has to name the fix."""
        responses.add(responses.GET, TREE_API, json={}, status=401)

        with pytest.raises(scanner.ScanFailed) as failure:
            scanner.run_scan(scan)

        assert "sign in again" in str(failure.value)

    @responses.activate
    def test_an_osv_outage_fails_the_scan_rather_than_reporting_clean(self, scan):
        """A missing batch answer is indistinguishable from 'no advisories'."""
        mock_github()
        mock_registry()
        responses.add(
            responses.POST, "https://api.osv.dev/v1/querybatch", json={}, status=503
        )

        with pytest.raises(scanner.ScanFailed) as failure:
            scanner.run_scan(scan)

        assert "vulnerability database" in str(failure.value)
        assert not DependencyOccurrence.objects.filter(manifest__scan=scan).exists()

    @responses.activate
    def test_a_registry_that_answers_nothing_at_all_fails_the_scan(self, scan):
        """One dead package is unassessable; a dead registry is a failed scan."""
        mock_github()
        mock_osv()
        for name in ("express", "lodash", "left-pad", "react", "typescript"):
            responses.add(
                responses.GET,
                f"https://registry.npmjs.org/{name}",
                json={},
                status=503,
            )

        with pytest.raises(scanner.ScanFailed) as failure:
            scanner.run_scan(scan)

        assert "package registry" in str(failure.value)

    @responses.activate
    def test_a_failed_scan_leaves_no_half_written_manifests_behind(self, scan):
        """A manifest row with nothing under it reads as 'declares nothing'."""
        mock_github()
        mock_registry()
        responses.add(
            responses.POST, "https://api.osv.dev/v1/querybatch", json={}, status=503
        )

        with pytest.raises(scanner.ScanFailed):
            scanner.run_scan(scan)

        assert not ManifestFile.objects.filter(scan=scan).exists()

    @responses.activate
    def test_a_repository_whose_manifests_vanished_says_which_problem_it_is(self, scan):
        responses.add(
            responses.GET,
            TREE_API,
            json={"tree": [{"path": "README.md", "type": "blob", "sha": "r", "size": 1}]},
            status=200,
        )

        with pytest.raises(scanner.ScanFailed) as failure:
            scanner.run_scan(scan)

        assert "dependency manifest" in str(failure.value)


@pytest.mark.django_db
class TestSizeCaps:
    @responses.activate
    def test_an_oversized_manifest_is_skipped_before_it_is_fetched(self, scan):
        """The tree carries the size, so the cap costs nothing to enforce."""
        tree = load("github/tree_npm_monorepo.json")
        for entry in tree["tree"]:
            if entry["path"] == "services/api/package.json":
                entry["size"] = scanner.MAX_MANIFEST_BYTES + 1
        mock_github(tree)
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        fetched = [call.request.url for call in responses.calls]
        assert not any("api-manifest" in url for url in fetched)

    @responses.activate
    def test_an_oversized_lockfile_degrades_the_manifest_to_ranges(self, scan):
        tree = load("github/tree_npm_monorepo.json")
        for entry in tree["tree"]:
            if entry["path"] == "package-lock.json":
                entry["size"] = scanner.MAX_LOCKFILE_BYTES + 1
        mock_github(tree)
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        root = ManifestFile.objects.get(scan=scan, manifest_path="package.json")
        assert root.lockfile_path is None
        express = occurrences(scan).get(manifest=root, package__package_name="express")
        assert express.resolution == Resolution.RANGE_LATEST_APPROX.value


def mock_workspaces_github() -> None:
    responses.add(
        responses.GET,
        TREE_API,
        json=load("github/tree_npm_workspaces.json"),
        status=200,
    )
    for sha, rel in (
        ("ws-root-manifest", "manifests/workspaces_root_package.json"),
        ("ws-root-lock", "manifests/workspaces_root_lock.json"),
        ("ws-ui-manifest", "manifests/workspaces_ui_package.json"),
        ("ws-api-manifest", "manifests/workspaces_api_package.json"),
        ("ws-demo-manifest", "manifests/workspaces_demo_package.json"),
    ):
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/{sha}",
            json=blob_response(rel),
            status=200,
        )


@pytest.mark.django_db
class TestWorkspacesMonorepo:
    """One lockfile at the root, by design — and members that must use it.

    A sibling-only lockfile rule is right for an unrelated nested project and
    wrong here: every workspace package would fall to `range_latest_approx` and
    be checked against the registry's newest release instead of what it
    installs. The fixture is built so that mistake reports the repository
    clean, because `^4.17.0` permits the patched lodash 4.17.21 while the root
    lock installs the vulnerable 4.17.19.
    """

    @responses.activate
    def test_a_workspace_member_resolves_from_the_root_lockfile(self, scan):
        mock_workspaces_github()
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        api_lodash = occurrences(scan).get(
            manifest__manifest_path="packages/api/package.json",
            package__package_name="lodash",
        )
        assert api_lodash.resolved_version == "4.17.19"
        assert api_lodash.resolution == Resolution.LOCKFILE.value

    @responses.activate
    def test_that_is_what_finds_the_vulnerability(self, scan):
        """The whole point. Under the old rule this row reported clean."""
        mock_workspaces_github()
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        api_lodash = occurrences(scan).get(
            manifest__manifest_path="packages/api/package.json",
            package__package_name="lodash",
        )
        assert api_lodash.vulnerability_count == 2
        assert api_lodash.is_deprecated

    @responses.activate
    def test_the_inherited_lockfile_path_is_recorded_as_the_root_one(self, scan):
        """So a reader can see *which* lockfile produced the resolution."""
        mock_workspaces_github()
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        member = ManifestFile.objects.get(
            scan=scan, manifest_path="packages/api/package.json"
        )
        assert member.lockfile_path == "package-lock.json"

    @responses.activate
    def test_a_directory_outside_the_globs_does_not_borrow_it(self, scan):
        """`examples/demo` is not a declared member, so it must not inherit.

        This is the case the sibling-only rule got right, and it stays right:
        borrowing a lockfile that never described you invents resolutions.
        """
        mock_workspaces_github()
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        demo = ManifestFile.objects.get(
            scan=scan, manifest_path="examples/demo/package.json"
        )
        assert demo.lockfile_path is None
        demo_react = occurrences(scan).get(
            manifest__manifest_path="examples/demo/package.json",
            package__package_name="react",
        )
        assert demo_react.resolution == Resolution.RANGE_LATEST_APPROX.value

    @responses.activate
    def test_the_shared_lockfile_is_fetched_once(self, scan):
        """Three members pointing at one root lock is one blob fetch, not three."""
        mock_workspaces_github()
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        lock_fetches = [
            call
            for call in responses.calls
            if call.request.url.endswith("/git/blobs/ws-root-lock")
        ]
        assert len(lock_fetches) == 1


@pytest.mark.django_db
class TestSkippedManifestsAreCounted:
    """Three paths drop a manifest; none of them used to leave a trace.

    The detail page says "pooled across N manifests" with complete confidence,
    so a manifest vanishing into a log line is the silent miscount this product
    defines itself against (§3.13).
    """

    @responses.activate
    def test_a_clean_scan_reports_none_skipped(self, scan):
        mock_everything()

        scanner.run_scan(scan)

        scan.refresh_from_db()
        assert scan.skipped_manifest_count == 0

    @responses.activate
    def test_an_unparseable_manifest_is_counted(self, scan):
        mock_registry()
        mock_osv()
        responses.add(
            responses.GET,
            TREE_API,
            json=load("github/tree_npm_monorepo.json"),
            status=200,
        )
        for sha, rel in (
            ("root-manifest", "manifests/root_package.json"),
            ("root-lock", "manifests/root_package_lock.json"),
            ("worker-manifest", "manifests/worker_package.json"),
        ):
            responses.add(
                responses.GET,
                f"{REPO_API}/git/blobs/{sha}",
                json=blob_response(rel),
                status=200,
            )
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/api-manifest",
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"{ not json").decode(),
                "size": 10,
            },
            status=200,
        )

        scanner.run_scan(scan)

        scan.refresh_from_db()
        assert scan.skipped_manifest_count == 1

    @responses.activate
    def test_an_oversized_manifest_is_counted(self, scan):
        tree = load("github/tree_npm_monorepo.json")
        for entry in tree["tree"]:
            if entry["path"] == "services/api/package.json":
                entry["size"] = scanner.MAX_MANIFEST_BYTES + 1
        mock_github(tree)
        mock_registry()
        mock_osv()

        scanner.run_scan(scan)

        scan.refresh_from_db()
        assert scan.skipped_manifest_count == 1

    @responses.activate
    def test_manifests_past_the_cap_are_counted(self, scan, monkeypatch):
        """Truncation is not a failure to read, but it is still an omission."""
        monkeypatch.setattr(scanner, "MAX_MANIFESTS", 2)
        mock_everything()

        scanner.run_scan(scan)

        scan.refresh_from_db()
        assert ManifestFile.objects.filter(scan=scan).count() == 2
        assert scan.skipped_manifest_count == 1


# ── Phase 6: the same orchestrator, a second ecosystem ─────────────────────
# Nothing below calls a different function, passes a flag, or reaches a branch
# `scanner.py` grew for PyPI -- there is none. These tests run `run_scan`
# exactly as the npm ones above do, against a Python repository, and that is
# the soundness claim `docs/adapter_soundness.md` states in prose.

PYPI_BLOBS: tuple[tuple[str, str], ...] = (
    ("py-requirements", "manifests/pypi_requirements.txt"),
    ("py-requirements-dev", "manifests/pypi_requirements_dev.txt"),
    ("py-pipfile", "manifests/pypi_pipfile.toml"),
    ("py-pipfile-lock", "manifests/pypi_pipfile_lock.json"),
    ("py-pyproject", "manifests/pypi_pyproject.toml"),
    ("py-poetry-lock", "manifests/pypi_poetry.lock"),
    ("py-setup", "manifests/pypi_setup_py.txt"),
)


def mock_pypi_github(tree_name: str = "github/tree_pypi_repo.json") -> None:
    responses.add(responses.GET, TREE_API, json=load(tree_name), status=200)
    for sha, rel in PYPI_BLOBS:
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/{sha}",
            json=blob_response(rel),
            status=200,
        )


def mock_pypi_registry() -> None:
    for name in ("django", "flask", "requests", "urllib3", "oauth2client"):
        responses.add(
            responses.GET,
            f"https://pypi.org/pypi/{name}/json",
            json=load(f"pypi/{name}.json"),
            status=200,
        )


@pytest.mark.django_db
class TestPypiRepository:
    """A Python repository through the unchanged pipeline (§10 Phase 6)."""

    @responses.activate
    def test_all_five_manifest_formats_are_read_in_one_scan(self, scan):
        mock_pypi_github()
        mock_pypi_registry()
        mock_osv({})

        scanner.run_scan(scan)

        rows = ManifestFile.objects.filter(scan=scan)
        assert sorted(rows.values_list("manifest_path", flat=True)) == [
            "Pipfile",
            "legacy/setup.py",
            "requirements-dev.txt",
            "requirements.txt",
            "service/pyproject.toml",
        ]
        # Every row is PyPI, and each says which of the five parsers read it.
        assert set(rows.values_list("ecosystem", flat=True)) == {"pypi"}
        assert sorted(rows.values_list("parser_name", flat=True)) == [
            "pypi/pipfile@1",
            "pypi/pyproject@1",
            "pypi/requirements@1",
            "pypi/requirements@1",
            "pypi/setup_py@1",
        ]

    @responses.activate
    def test_a_vendored_virtualenv_is_not_a_manifest(self, scan):
        """`.venv/lib/site-packages/**/setup.py` is other people's packages.

        The npm equivalent is a checked-in `node_modules`; a Python repository
        that committed its virtualenv would otherwise report every installed
        package's own dependencies as its own.
        """
        mock_pypi_github()
        mock_pypi_registry()
        mock_osv({})

        scanner.run_scan(scan)

        paths = ManifestFile.objects.filter(scan=scan).values_list(
            "manifest_path", flat=True
        )
        assert not any(".venv" in path for path in paths)

    @responses.activate
    def test_the_lockfile_beats_the_range_and_that_is_what_finds_the_yank(self, scan):
        """PyPI's version of the finding the npm suite turns on.

        `pyproject.toml` allows `Django>=4.2`, which the newest release
        satisfies. `poetry.lock` installs 4.2.12, which PyPI yanked. Resolve
        the range against the registry instead and this repository reports
        clean -- with every row looking perfectly well-formed.
        """
        mock_pypi_github()
        mock_pypi_registry()
        mock_osv({})

        scanner.run_scan(scan)

        row = occurrences(scan).get(
            manifest__manifest_path="service/pyproject.toml",
            package__package_name="django",
        )
        assert row.resolved_version == "4.2.12"
        assert row.resolution == Resolution.LOCKFILE.value
        assert row.is_deprecated
        assert "Windows end-of-line characters" in row.deprecation_reason

    @responses.activate
    def test_an_inactive_project_is_deprecated_at_every_version(self, scan):
        """D2's second half, and the reason the composite exists: PyPI has no
        per-version deprecation string, so a project that has stopped says so
        through a trove classifier instead."""
        mock_pypi_github()
        mock_pypi_registry()
        mock_osv({})

        scanner.run_scan(scan)

        rows = occurrences(scan).filter(package__package_name="oauth2client")
        assert rows.exists()
        for row in rows:
            assert row.is_deprecated
            assert row.deprecation_reason == "Development Status :: 7 - Inactive"
            # And it is stale by the same measurement npm uses.
            assert row.staleness_days > 730

    @responses.activate
    def test_every_unassessable_row_survives_with_its_reason(self, scan):
        """Three specifier families no registry can describe, and one `setup.py`
        argument we declined to evaluate. Four rows, four reasons, none of them
        counted as clean."""
        mock_pypi_github()
        mock_pypi_registry()
        mock_osv({})

        scanner.run_scan(scan)

        reasons = dict(
            occurrences(scan)
            .filter(is_unassessable=True)
            .values_list("package__package_name", "unassessable_reason")
        )
        assert reasons["widget"] == "vcs_specifier"
        assert reasons["shared"] == "local_path_specifier"
        assert reasons["local-thing"] == "local_path_specifier"
        assert reasons["setup.py:extras_require"] == "dynamic_setup_py"

    @responses.activate
    def test_one_package_in_four_manifests_is_four_occurrences(self, scan):
        """§5.1: duplicates across manifests are independent rows, because each
        is an independent installation needing its own remediation. `django` is
        declared in the requirements file, the Pipfile, the pyproject and the
        setup.py -- at three different resolved versions.
        """
        mock_pypi_github()
        mock_pypi_registry()
        mock_osv({})

        scanner.run_scan(scan)

        rows = occurrences(scan).filter(package__package_name="django")
        assert rows.count() == 4
        assert {row.resolved_version for row in rows} == {"2.2", "2.2.28", "4.2.12"}

    @responses.activate
    def test_a_scan_of_an_unchanged_repository_repeats_itself(self, scan, repository):
        """§4.4's determinism suite, extended to the second ecosystem."""
        mock_pypi_github()
        mock_pypi_registry()
        mock_osv({})
        scanner.run_scan(scan)
        first = sorted(
            occurrences(scan).values_list(
                "manifest__manifest_path",
                "package__package_name",
                "resolved_version",
                "resolution",
                "is_unassessable",
            )
        )

        second_scan = ScanRun.objects.create(
            repository=repository,
            triggered_by=repository.user,
            trigger_type="manual",
            scoring_formula_version="unscored",
        )
        scanner.run_scan(second_scan)
        second = sorted(
            occurrences(second_scan).values_list(
                "manifest__manifest_path",
                "package__package_name",
                "resolved_version",
                "resolution",
                "is_unassessable",
            )
        )

        assert first == second


@pytest.mark.django_db
class TestMixedEcosystemRepository:
    """One repository, two ecosystems, one scan and one roll-up (§10 Phase 6).

    The pooling rule does not know there are two: `scanner.py` groups by
    `occurrence.ecosystem` when it asks a registry, because each adapter names
    its own client, and does nothing else differently. The scoring engine picks
    a weight vector per occurrence from the same field (§5.4), so a mixed
    repository gets npm's vector on its npm rows and PyPI's on its PyPI rows
    without either layer branching on an ecosystem name.
    """

    @responses.activate
    def test_both_ecosystems_land_in_one_scan(self, scan):
        mock_github(load("github/tree_mixed_ecosystem.json"))
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/py-requirements",
            json=blob_response("manifests/pypi_requirements.txt"),
            status=200,
        )
        mock_registry()
        mock_pypi_registry()
        mock_osv()

        scanner.run_scan(scan)

        by_path = dict(
            ManifestFile.objects.filter(scan=scan).values_list(
                "manifest_path", "ecosystem"
            )
        )
        assert by_path == {"package.json": "npm", "api/requirements.txt": "pypi"}

    @responses.activate
    def test_each_registry_is_asked_only_about_its_own_packages(self, scan):
        """A cross-ecosystem lookup would be silently wrong rather than loud:
        npm has a `requests` and PyPI has a `flask`, and asking the wrong one
        returns a real document about a different package."""
        mock_github(load("github/tree_mixed_ecosystem.json"))
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/py-requirements",
            json=blob_response("manifests/pypi_requirements.txt"),
            status=200,
        )
        mock_registry()
        mock_pypi_registry()
        mock_osv()

        scanner.run_scan(scan)

        asked_npm = {
            call.request.url.rsplit("/", 1)[-1]
            for call in responses.calls
            if "registry.npmjs.org" in call.request.url
        }
        asked_pypi = {
            call.request.url.rsplit("/", 2)[-2]
            for call in responses.calls
            if "pypi.org" in call.request.url
        }

        # The root `package.json`'s four registry packages; its `file:` and
        # `git+` entries are unassessable and never reach a registry.
        assert asked_npm == {"express", "lodash", "left-pad", "typescript"}
        assert asked_pypi == {"django", "flask", "requests", "urllib3", "oauth2client"}

    @responses.activate
    def test_osv_is_asked_under_each_ecosystems_own_name(self, scan):
        """`npm` and `PyPI`. One batch per ecosystem, each spelled OSV's way."""
        mock_github(load("github/tree_mixed_ecosystem.json"))
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/py-requirements",
            json=blob_response("manifests/pypi_requirements.txt"),
            status=200,
        )
        mock_registry()
        mock_pypi_registry()
        mock_osv()

        scanner.run_scan(scan)

        ecosystems = set()
        for call in responses.calls:
            if "querybatch" not in call.request.url:
                continue
            for query in json.loads(call.request.body)["queries"]:
                ecosystems.add(query["package"]["ecosystem"])
        assert ecosystems == {"npm", "PyPI"}
