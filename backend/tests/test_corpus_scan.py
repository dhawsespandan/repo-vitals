"""`scan_corpus` — §10 Phase 11's acceptance, as tests.

The phase's acceptance has five clauses and four of them are here:

* "the per-repo scores match a product scan of the same repo exactly (same
  adapters, same weights)" — `TestIdentityWithAProductScan` runs both over the
  same stubbed GitHub, registry and OSV, and compares the number, the
  classification and every stored signal row by row;
* "kill -9 mid-run -> --resume completes without duplicate rows" —
  `TestResume` kills the process in the two places that differ: after the
  checkpoint line, and between the commit and the checkpoint line, which is
  the case a file-only resume cannot survive;
* "zero writes to operational tables (asserted)" — `TestNoOperationalWrites`,
  both by counting rows and by the guard that made the counting unnecessary;
* "product trend endpoint still shows only `live_scan` rows" —
  `TestTheProductNeverSeesThem`.

The fifth ("20-repo pilot corpus end-to-end with sane strata report") is a
live run against GitHub with a PAT and belongs to WP-4/WP-5, not to a suite.

The golden repository is `test_scanner.py`'s: a root manifest whose lockfile
pins `express` and `lodash` below what their ranges allow, `lodash` in three
manifests at two versions, and a vendored `node_modules` manifest. A corpus
scan that resolved ranges against the registry, deduplicated by package name,
or read the vendored manifest would score it differently from the product —
which is exactly what the identity test would catch.
"""

from __future__ import annotations

import base64
import json
import pathlib
from datetime import date

import pytest
import responses

from apps.common import http
from apps.research.corpus_scan import (
    CHECKPOINT_FILENAME,
    REPORT_FILENAME,
    Checkpoint,
    CorpusManifestError,
    load_corpus,
    run_guarded,
)
from apps.research.guards import (
    OperationalWriteRefused,
    check_statement,
    no_operational_writes,
)
from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scanning import scanner
from apps.scanning.models import (
    DependencyOccurrence,
    ManifestFile,
    Package,
    ScanRun,
)
from apps.scoring.signals import score_scan
from apps.scoring.weights import active_weights
from tests.factories import RepositoryFactory

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

OWNER = "acme"
NAME = "shop"
FULL_NAME = f"{OWNER}/{NAME}"
REPO_ID = 778899
OWNER_ID = 4242
REPO_API = f"https://api.github.com/repos/{FULL_NAME}"
SNAPSHOT = date(2026, 9, 16)

#: The manifests the golden tree holds, and the lockfile each one resolves
#: from — the answer `build_corpus` would have recorded after running
#: `adopt_workspace_lockfiles` with the bytes in hand.
GOLDEN_MANIFESTS = (
    {
        "path": "package.json",
        "sha": "root-manifest",
        "size": 612,
        "ecosystem": "npm",
        "parser_name": "npm/package.json@1",
        "lockfile_path": "package-lock.json",
        "lockfile_sha": "root-lock",
        "lockfile_size": 48211,
    },
    {
        "path": "services/api/package.json",
        "sha": "api-manifest",
        "size": 388,
        "ecosystem": "npm",
        "parser_name": "npm/package.json@1",
    },
    {
        "path": "services/worker/package.json",
        "sha": "worker-manifest",
        "size": 214,
        "ecosystem": "npm",
        "parser_name": "npm/package.json@1",
    },
)


def load(rel: str) -> dict:
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


def blob_response(rel: str) -> dict:
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


@pytest.fixture(autouse=True)
def research_pat(settings):
    settings.GITHUB_API_PAT = "ghp_research_token"


def mock_github() -> None:
    responses.add(
        responses.GET,
        f"{REPO_API}/git/trees/main",
        json=load("github/tree_npm_monorepo.json"),
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
            headers={"x-ratelimit-remaining": "4900", "x-ratelimit-reset": "0"},
        )


def mock_registry() -> None:
    for name in ("express", "lodash", "left-pad", "react", "typescript"):
        responses.add(
            responses.GET,
            f"https://registry.npmjs.org/{name}",
            json=load(f"npm/{name}.json"),
            status=200,
        )


def mock_osv() -> None:
    found = {
        ("lodash", "4.17.19"): ["GHSA-35jh-r3h4-6jhm", "GHSA-p6mc-m468-83gg"],
    }

    def answer(request):
        queries = json.loads(request.body)["queries"]
        results = []
        for query in queries:
            ids = found.get((query["package"]["name"], query["version"]), [])
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


def write_manifest(tmp_path, repositories=None, *, archive=False) -> pathlib.Path:
    """A `corpus_manifest.json` in the shape `build_corpus` writes.

    `archive=True` also drops the manifest blobs into `blobs/`, which is the
    normal case: `build_corpus` fetched them to verify the candidate and
    stored them, so a corpus scan reads the same bytes the admission decision
    was made on rather than whatever the repository has become since.
    """
    if repositories is None:
        repositories = [
            {
                "full_name": FULL_NAME,
                "github_repo_id": REPO_ID,
                "owner_login": OWNER,
                "owner_id": OWNER_ID,
                "default_branch": "main",
                "ecosystem": "npm",
                "cell": "javascript|5-20|lt6|le2015",
                "sampling_weight": 12.5,
                "manifests": list(GOLDEN_MANIFESTS),
            }
        ]

    directory = tmp_path / "corpus"
    directory.mkdir(parents=True, exist_ok=True)
    if archive:
        for entry in repositories:
            for record in entry["manifests"]:
                source = {
                    "root-manifest": "manifests/root_package.json",
                    "api-manifest": "manifests/api_package.json",
                    "worker-manifest": "manifests/worker_package.json",
                }[record["sha"]]
                blob = directory / "blobs" / record["sha"][:2] / record["sha"]
                blob.parent.mkdir(parents=True, exist_ok=True)
                blob.write_bytes((FIXTURES / source).read_bytes())
                record["blob_path"] = f"blobs/{record['sha'][:2]}/{record['sha']}"

    path = directory / "corpus_manifest.json"
    path.write_text(
        json.dumps(
            {
                "run_date": SNAPSHOT.isoformat(),
                "seed": 42,
                "cells": [
                    {"key": "javascript|5-20|lt6|le2015", "pushed": "lt6"},
                ],
                "repositories": repositories,
            }
        ),
        encoding="utf-8",
    )
    return path


def run(tmp_path, **kwargs):
    from apps.research.github import ResearchClient

    corpus = load_corpus(kwargs.pop("manifest", None) or write_manifest(tmp_path))
    return run_guarded(
        corpus=corpus,
        client=ResearchClient.from_settings(),
        snapshot_date=kwargs.pop("snapshot_date", SNAPSHOT),
        **kwargs,
    )


def product_scan(user):
    """A live scan of the same repository, scored, for comparison."""
    repository = RepositoryFactory(
        user=user, owner=OWNER, name=NAME, full_name=FULL_NAME, default_branch="main"
    )
    scan = ScanRun.objects.create(
        repository=repository,
        triggered_by=user,
        trigger_type="initial",
        scoring_formula_version="unscored",
    )
    scanner.run_scan(scan)
    score_scan(scan)
    scan.refresh_from_db()
    return scan


# ── the acceptance criterion that matters most ─────────────────────────────


@pytest.mark.django_db
class TestIdentityWithAProductScan:
    """§10 Phase 11: the corpus score must equal the product score, exactly.

    Not "close to". The claim S1 rests on is that the corpus measures the
    shipped formula, and a corpus scan that re-implemented any step — range
    resolution, severity rollup, the roll-up's decay — would still produce a
    plausible number. Only an exact match rules that out.
    """

    @responses.activate
    def test_the_repository_score_is_the_same_number(self, tmp_path, user):
        mock_everything()
        product = product_scan(user)

        run(tmp_path)
        corpus = ScanHistory.objects.get(data_source=DataSource.CORPUS_SCAN.value)

        assert corpus.risk_score == product.risk_score
        assert corpus.classification == product.classification

    @responses.activate
    def test_and_so_is_every_stored_signal(self, tmp_path, user):
        """Row for row, not just in aggregate. Two different measurements can
        roll up to one number by coincidence; forty columns cannot."""
        mock_everything()
        product = product_scan(user)
        run(tmp_path)

        live = {
            (row.manifest.manifest_path, row.package.package_name): row
            for row in DependencyOccurrence.objects.filter(
                manifest__scan=product
            ).select_related("manifest", "package")
        }
        corpus = {
            (row.manifest_path, row.package_name): row
            for row in DependencyHistory.objects.all()
        }

        assert set(corpus) == set(live)
        for key, row in corpus.items():
            other = live[key]
            assert row.resolved_version == other.resolved_version, key
            assert row.resolution == other.resolution, key
            assert row.latest_version == other.latest_version, key
            assert row.staleness_days == other.staleness_days, key
            assert row.is_deprecated == other.is_deprecated, key
            assert row.deprecation_reason == other.deprecation_reason, key
            assert row.vulnerability_count == other.vulnerability_count, key
            assert row.highest_severity == other.highest_severity, key
            assert row.cvss_max == other.cvss_max, key
            assert row.is_unassessable == other.is_unassessable, key
            assert row.risk_component_score == other.risk_component_score, key
            assert row.versions_behind_major == other.versions_behind_major, key

    @responses.activate
    def test_the_lockfile_still_beats_the_range(self, tmp_path):
        """The golden fixture's whole point, carried into the corpus path: the
        root lockfile pins `lodash` at 4.17.19 under a `^4.17.0` range, and
        that pin is what finds the CVE. A corpus scan reading manifests
        without their lockfiles would report this repository clean."""
        mock_everything()
        run(tmp_path)

        row = DependencyHistory.objects.get(
            manifest_path="package.json", package_name="lodash"
        )
        assert row.resolved_version == "4.17.19"
        assert row.resolution == "lockfile"
        assert row.vulnerability_count == 2

    @responses.activate
    def test_the_vendored_manifest_is_not_scanned(self, tmp_path):
        """`build_corpus` never records it — `adapter_for_path` excludes vendor
        directories — and `_plan_from_record` would drop it if a manifest from
        somewhere else named one."""
        mock_everything()
        run(tmp_path)
        assert not DependencyHistory.objects.filter(
            manifest_path__contains="node_modules"
        ).exists()

    @responses.activate
    def test_one_package_in_three_manifests_is_three_rows(self, tmp_path):
        mock_everything()
        run(tmp_path)
        rows = DependencyHistory.objects.filter(package_name="lodash")
        assert rows.count() == 3
        assert {row.manifest_path for row in rows} == {
            "package.json",
            "services/api/package.json",
            "services/worker/package.json",
        }


# ── what the rows say about themselves ─────────────────────────────────────


@pytest.mark.django_db
class TestTheRowsThatAreWritten:
    @responses.activate
    def test_the_row_is_tagged_as_corpus_with_its_frame_attached(self, tmp_path):
        mock_everything()
        run(tmp_path)

        entry = ScanHistory.objects.get()
        assert entry.data_source == DataSource.CORPUS_SCAN.value
        assert entry.snapshot_date == SNAPSHOT
        assert float(entry.sampling_weight) == pytest.approx(12.5)
        assert entry.scoring_formula_version == active_weights().version

    @responses.activate
    def test_there_is_no_scan_run_to_point_at(self, tmp_path):
        """`source_scan_id` is a traceability column, not a foreign key (§5.1).
        A corpus scan has no `scan_runs` row at all, and claiming one would
        name a row that never existed."""
        mock_everything()
        run(tmp_path)
        assert ScanHistory.objects.get().source_scan_id is None

    @responses.activate
    def test_the_identity_columns_carry_the_github_owner(self, tmp_path):
        """There is no RepoVitals user. The honest analogue of "whose
        repository is this" is the GitHub account that owns it, and S1 needs
        to be able to ask how many corpus repositories share an owner."""
        mock_everything()
        run(tmp_path)

        entry = ScanHistory.objects.get()
        assert entry.github_user_id == OWNER_ID
        assert entry.github_username == OWNER
        assert entry.github_repo_id == REPO_ID
        assert entry.repo_full_name == FULL_NAME

    @responses.activate
    def test_clean_and_unassessable_occurrences_are_recorded_too(self, tmp_path):
        """§5.1 says every occurrence. A corpus holding only the bad rows can
        say how many packages were bad and never what fraction that was."""
        mock_everything()
        run(tmp_path)

        rows = DependencyHistory.objects.all()
        assert rows.filter(vulnerability_count=0, is_unassessable=False).exists()
        assert rows.count() == ScanHistory.objects.get().dependency_count

    @responses.activate
    def test_an_unassessable_row_is_not_scored_and_not_counted_as_clean(self, tmp_path):
        """§5.2: `risk_component_score` stays NULL. A zero would collapse "we
        assessed this and it is fine" into "we could not assess this"."""
        mock_everything()
        run(tmp_path)

        for row in DependencyHistory.objects.filter(is_unassessable=True):
            assert row.risk_component_score is None


# ── D10 ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestNoOperationalWrites:
    """§10 Phase 11: "zero writes to operational tables (asserted)".

    Asserted twice, because the two assertions fail at different times. The
    row counts fail when a scan writes one today; the guard fails at the
    statement, including one issued by a `bulk_create`, a cascade, or three
    frames of library code nobody here wrote.
    """

    @responses.activate
    def test_not_one_operational_row_exists_afterwards(self, tmp_path):
        mock_everything()
        run(tmp_path)

        assert ScanRun.objects.count() == 0
        assert ManifestFile.objects.count() == 0
        assert DependencyOccurrence.objects.count() == 0
        assert Package.objects.count() == 0
        # And the research rows it was supposed to write are there, so the
        # zero above is not the zero of a run that did nothing.
        assert ScanHistory.objects.count() == 1
        assert DependencyHistory.objects.count() > 0

    @responses.activate
    def test_the_guard_is_on_during_the_run_not_just_asserted_after_it(
        self, tmp_path, monkeypatch
    ):
        """The counting test cannot see a write that was made and rolled back,
        or one made to a table the test forgot to count. This one refuses at
        the statement."""
        mock_everything()

        def write_an_operational_row(*args, **kwargs):
            Package.objects.create(ecosystem="npm", package_name="sneaky")
            raise AssertionError("unreachable: the guard should have refused")

        monkeypatch.setattr("apps.research.corpus_scan.persist", write_an_operational_row)
        with pytest.raises(OperationalWriteRefused, match="packages"):
            run(tmp_path)

    def test_the_guard_reads_the_statement_not_the_orm(self):
        """Below the ORM on purpose: `bulk_create` and `queryset.update()` send
        no `pre_save` signal, and those are exactly the shapes a scan writer
        reaches for."""
        check_statement('INSERT INTO "scan_history" ("a") VALUES (1)')
        check_statement('SELECT * FROM "repositories"')
        check_statement("SAVEPOINT s1")

        for statement in (
            'INSERT INTO "repositories" ("a") VALUES (1)',
            'UPDATE "scan_runs" SET "status" = %s',
            'DELETE FROM "packages" WHERE 1',
            "TRUNCATE TABLE app_users",
        ):
            with pytest.raises(OperationalWriteRefused):
                check_statement(statement)

    def test_the_allowlist_names_the_permanent_tables_and_nothing_else(self):
        """Deny by default. An allowlist that named the *operational* tables
        would silently admit the next one added."""
        from apps.research.guards import RESEARCH_TABLES

        assert RESEARCH_TABLES == {
            "scan_history",
            "dependency_history",
            "agent_execution_traces",
        }

    @pytest.mark.django_db
    def test_a_research_write_passes_straight_through(self):
        with no_operational_writes():
            ScanHistory.objects.create(
                github_user_id=1,
                github_username="x",
                github_repo_id=2,
                repo_full_name="x/y",
                ecosystems="npm",
                risk_score=90,
                classification="safe",
                scoring_formula_version="v1",
                data_source=DataSource.CORPUS_SCAN.value,
                snapshot_date=SNAPSHOT,
                scanned_at="2026-09-16T00:00:00Z",
            )
        assert ScanHistory.objects.count() == 1


# ── resume ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestResume:
    @responses.activate
    def test_a_resumed_run_skips_what_the_checkpoint_recorded(self, tmp_path):
        mock_everything()
        manifest = write_manifest(tmp_path, archive=True)

        first = run(tmp_path, manifest=manifest)
        second = run(tmp_path, manifest=manifest, resume=True)

        assert first.scanned == 1
        assert second.scanned == 0
        assert second.skipped == 1
        assert ScanHistory.objects.count() == 1

    @responses.activate
    def test_a_kill_between_the_commit_and_the_checkpoint_line_is_survived(
        self, tmp_path
    ):
        """The case a file-only resume cannot survive, and §10 Phase 11's
        acceptance names it: rows committed, checkpoint line never written.
        `--resume` asks the database as well, so the repository is skipped
        rather than scanned again into duplicate rows."""
        mock_everything()
        manifest = write_manifest(tmp_path, archive=True)
        run(tmp_path, manifest=manifest)

        # Exactly what a kill -9 between the two leaves behind.
        Checkpoint(manifest.parent / CHECKPOINT_FILENAME).clear()

        resumed = run(tmp_path, manifest=manifest, resume=True)

        assert resumed.skipped == 1
        assert resumed.scanned == 0
        assert ScanHistory.objects.count() == 1
        assert (
            DependencyHistory.objects.values("manifest_path", "package_name").count()
            == DependencyHistory.objects.count()
        )

    @responses.activate
    def test_a_run_without_resume_scans_again(self, tmp_path):
        """`--resume` is opt-in. Without it the command does what it says, and
        a second snapshot of the same corpus is a legitimate thing to want —
        under a different `--snapshot-date`."""
        mock_everything()
        manifest = write_manifest(tmp_path, archive=True)
        run(tmp_path, manifest=manifest)
        run(tmp_path, manifest=manifest, snapshot_date=date(2026, 10, 1))
        assert ScanHistory.objects.count() == 2

    @responses.activate
    def test_the_checkpoint_line_names_what_was_written(self, tmp_path):
        mock_everything()
        manifest = write_manifest(tmp_path, archive=True)
        run(tmp_path, manifest=manifest)

        rows = Checkpoint(manifest.parent / CHECKPOINT_FILENAME).read()
        assert len(rows) == 1
        assert rows[0]["status"] == "ok"
        assert rows[0]["github_repo_id"] == REPO_ID
        assert rows[0]["scan_history_id"] == str(ScanHistory.objects.get().pk)


# ── failures ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOneRepositorysBadAfternoon:
    @responses.activate
    def test_an_unreachable_repository_fails_alone(self, tmp_path):
        """A corpus of a thousand public repositories always holds some that
        were renamed, emptied or made private between WP-4 and WP-5. WP-5's
        checklist expects a handful and asks the teammate to flag fifty."""
        mock_registry()
        mock_osv()
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/root-manifest",
            json={"message": "Not Found"},
            status=404,
        )
        gone = {
            "full_name": "ghost/repo",
            "github_repo_id": 999,
            "owner_login": "ghost",
            "owner_id": 1,
            "default_branch": "main",
            "ecosystem": "npm",
            "cell": "javascript|5-20|lt6|le2015",
            "sampling_weight": 1.0,
            "manifests": [dict(GOLDEN_MANIFESTS[0])],
        }
        manifest = write_manifest(tmp_path, repositories=[gone])

        outcome = run(tmp_path, manifest=manifest)

        assert outcome.failed == 1
        assert outcome.scanned == 0
        assert ScanHistory.objects.count() == 0

    @responses.activate
    def test_a_failure_is_retried_by_the_next_resume(self, tmp_path):
        mock_everything()
        manifest = write_manifest(tmp_path, archive=True)
        rows = Checkpoint(manifest.parent / CHECKPOINT_FILENAME)
        rows.append(
            {"full_name": FULL_NAME, "github_repo_id": REPO_ID, "status": "failed"}
        )

        outcome = run(tmp_path, manifest=manifest, resume=True)

        assert outcome.scanned == 1
        assert outcome.skipped == 0


# ── the CLI's own arguments ────────────────────────────────────────────────


@pytest.mark.django_db
class TestSelectingWork:
    @responses.activate
    def test_repo_scans_one_and_stops(self, tmp_path):
        mock_everything()
        second = {
            "full_name": "other/thing",
            "github_repo_id": 5,
            "owner_login": "other",
            "owner_id": 6,
            "default_branch": "main",
            "ecosystem": "npm",
            "cell": "javascript|5-20|lt6|le2015",
            "sampling_weight": 1.0,
            "manifests": [],
        }
        document = json.loads(write_manifest(tmp_path).read_text(encoding="utf-8"))
        manifest = write_manifest(
            tmp_path, repositories=[*document["repositories"], second], archive=True
        )

        outcome = run(tmp_path, manifest=manifest, only=FULL_NAME)

        assert outcome.attempted == 1
        assert ScanHistory.objects.get().repo_full_name == FULL_NAME

    def test_repo_naming_something_the_corpus_never_admitted_is_refused(self, tmp_path):
        with pytest.raises(CorpusManifestError, match="nobody/nothing"):
            run(tmp_path, only="nobody/nothing")

    def test_a_missing_manifest_says_which_command_produces_it(self, tmp_path):
        with pytest.raises(CorpusManifestError, match="build_corpus"):
            load_corpus(tmp_path / "nope.json")


# ── the completion report ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCompletionReport:
    @responses.activate
    def test_it_answers_wp5s_checklist(self, tmp_path):
        mock_everything()
        manifest = write_manifest(tmp_path, archive=True)
        outcome = run(tmp_path, manifest=manifest)

        report = (manifest.parent / REPORT_FILENAME).read_text(encoding="utf-8")
        assert "**Corpus coverage:**" in report
        assert "**Unassessable rate:**" in report
        assert "**Scored occurrences written this run:**" in report
        assert "corpus_report" in report  # where the distribution question goes
        assert outcome.report_path == manifest.parent / REPORT_FILENAME

    @responses.activate
    def test_it_flags_coverage_below_the_threshold_wp5_names(self, tmp_path):
        mock_everything()
        unreachable = {
            "full_name": "ghost/repo",
            "github_repo_id": 999,
            "owner_login": "ghost",
            "owner_id": 1,
            "default_branch": "main",
            "ecosystem": "npm",
            "cell": "javascript|5-20|lt6|le2015",
            "sampling_weight": 1.0,
            "manifests": [],
        }
        document = json.loads(write_manifest(tmp_path).read_text(encoding="utf-8"))
        manifest = write_manifest(
            tmp_path,
            repositories=[*document["repositories"], unreachable],
            archive=True,
        )
        run(tmp_path, manifest=manifest)

        report = (manifest.parent / REPORT_FILENAME).read_text(encoding="utf-8")
        assert "below 95%, flag it" in report

    @responses.activate
    def test_it_says_the_corpus_is_a_cross_section(self, tmp_path):
        """D14, in the artefact rather than only in the plan. A reader who
        finds this file in a year must not be able to read a trend into it."""
        mock_everything()
        manifest = write_manifest(tmp_path, archive=True)
        run(tmp_path, manifest=manifest)
        report = (manifest.parent / REPORT_FILENAME).read_text(encoding="utf-8")
        assert "cross-section as of the snapshot date" in report


# ── the corpus never reaches the product ───────────────────────────────────


@pytest.mark.django_db
class TestTheProductNeverSeesThem:
    @responses.activate
    def test_the_trend_endpoint_shows_no_corpus_row(self, tmp_path, auth_client, user):
        """§10 Phase 11's last acceptance clause, and §10 Phase 10's: the
        product chart is a positive filter on `live_scan`, so a corpus row for
        the very same GitHub repository id must not appear in it."""
        from django.urls import reverse

        mock_everything()
        repository = RepositoryFactory(
            user=user,
            owner=OWNER,
            name=NAME,
            full_name=FULL_NAME,
            github_repo_id=REPO_ID,
        )
        run(tmp_path)
        assert ScanHistory.objects.filter(github_repo_id=REPO_ID).exists()

        response = auth_client.get(reverse("repository-history", args=[repository.pk]))

        assert response.status_code == 200
        assert response.json()["points"] == []
        assert response.json()["total"] == 0


# ── the archive ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestManifestSource:
    @responses.activate
    def test_an_archived_manifest_costs_no_github_call(self, tmp_path):
        """`build_corpus` already fetched these to verify the candidate. Reading
        them back is free — and, more to the point, they are the bytes the
        admission decision was made on, so the repository is scanned as the
        thing that was sampled rather than as whatever it has become."""
        mock_registry()
        mock_osv()
        # Only the lockfile is served: if the manifests were re-fetched, this
        # run would fail with a connection refusal from `responses`.
        responses.add(
            responses.GET,
            f"{REPO_API}/git/blobs/root-lock",
            json=blob_response("manifests/root_package_lock.json"),
            status=200,
        )
        manifest = write_manifest(tmp_path, archive=True)

        outcome = run(tmp_path, manifest=manifest)

        assert outcome.scanned == 1
        assert DependencyHistory.objects.count() > 0

    @responses.activate
    def test_a_manifest_with_no_archive_is_fetched_from_github(self, tmp_path):
        mock_everything()
        outcome = run(tmp_path)
        assert outcome.scanned == 1


def test_scan_corpus_is_not_reachable_from_any_request_path():
    """§3 and D10: research code is never imported by request-handling code.

    Checked by import graph rather than by grep: `apps.research.corpus_scan`
    imports `apps.scanning.scanner`, and a view that imported it back would
    make the corpus writer reachable from an HTTP request with a PAT in hand.
    """
    import apps.reports.views
    import apps.repositories.views
    import apps.scanning.views

    for module in (
        apps.scanning.views,
        apps.repositories.views,
        apps.reports.views,
    ):
        names = {getattr(value, "__module__", "") for value in vars(module).values()}
        assert not any(name.startswith("apps.research.corpus") for name in names), (
            module.__name__
        )


def test_the_research_pat_is_read_in_exactly_one_package():
    """§6: "research commands only; never used for user-facing scans".

    Structural rather than conventional. A token with a thousand repositories
    of hourly quota on it must not be spendable by an HTTP request, and the
    way to guarantee that is for no request-handling module to be able to
    name it.
    """
    backend = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in (backend / "apps").rglob("*.py"):
        if "GITHUB_API_PAT" not in path.read_text(encoding="utf-8"):
            continue
        if path.parts[-3:-1] == ("apps", "research") or "research" in path.parts:
            continue
        offenders.append(str(path.relative_to(backend)))

    assert offenders == [], offenders


def test_the_settings_default_is_empty_so_no_phase_before_11_needs_one(settings):
    """CI has no PAT and every phase before this one ran without one. An unset
    variable must be a configuration, not a crash."""
    from apps.research.github import ResearchCredentialMissing, research_token

    settings.GITHUB_API_PAT = ""
    with pytest.raises(ResearchCredentialMissing):
        research_token()
