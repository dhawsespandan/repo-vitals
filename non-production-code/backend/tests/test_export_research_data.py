"""`export_research_data` (§10 Phase 14 commit 1): the files File C reads.

The export is the interface File C consumes, so its contract is tested as one:
every interface file present and listed with a true sha256; the tables exact
(decimals as decimals, not floats — D6's reproduction has to survive the
copy); corpus rows only unless asked (File C §1.2), with live traces counted
as live data; nothing written to any table; a missing signed deliverable
refused before a byte is written; and the same database exported twice giving
the same files.
"""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from io import StringIO

import pyarrow.parquet as pq
import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.research import export
from apps.research.guards import WriteRefused, check_read_only, no_writes
from apps.research.models import AgentExecutionTrace, DataSource, ScanHistory
from tests.corpus_rows import corpus_repository


def fake_deliverables(root):
    """A `wp/` holding every file the export copies, plus what it must skip."""
    for document in export.DOCUMENTS:
        source = root / document.source
        if document.source.endswith(("validation_report", "runs")):
            (source / "inner").mkdir(parents=True, exist_ok=True)
            (source / "inner" / "data.json").write_text(
                json.dumps({"from": document.source}), encoding="utf-8"
            )
            (source / "report.md").write_text(f"# {document.target}\n", encoding="utf-8")
        else:
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(f"{document.source}\n", encoding="utf-8")
    # Not a File B deliverable: the developer's own review notes.
    (root / "wp-review").mkdir(exist_ok=True)
    (root / "wp-review" / "WP_review.md").write_text("notes\n", encoding="utf-8")
    return root


def run_export(tmp_path, *extra, deliverables=None):
    deliverables = deliverables or fake_deliverables(tmp_path / "wp")
    out = tmp_path / "exports"
    archive = tmp_path / "deliverables"
    stdout = StringIO()
    call_command(
        "export_research_data",
        "--out", str(out),
        "--deliverables", str(deliverables),
        "--archive", str(archive),
        *extra,
        stdout=stdout,
    )  # fmt: skip
    return out, archive, stdout.getvalue()


def corpus():
    corpus_repository(
        "o/vulnerable",
        [{"vulns": 2, "cvss": 9.8, "staleness": 900}, {"staleness": 12}],
        sampling_weight=12.345678,
    )
    corpus_repository(
        "p/py",
        [{"ecosystem": "pypi", "deprecated": True, "staleness": None}],
    )


def live_rows():
    corpus_repository(
        "user/private-repo",
        [{"vulns": 1, "cvss": 5.3}],
        data_source=DataSource.LIVE_SCAN.value,
        sampling_weight=None,
    )
    AgentExecutionTrace.objects.create(
        github_user_id=7,
        repo_full_name="user/private-repo",
        ecosystem="npm",
        package_name="lodash",
        resolved_version="4.17.20",
        branch_taken="no_reason",
        retrieval_query="lodash security fix",
        retrieved_chunks_json=[{"chunk_id": "c1", "score": 0.5}],
        generation_json={"summary_md": "Upgrade.", "fixes": []},
        grounding_confidence="sufficient",
        model_name="openai/gpt-oss-120b",
    )


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.django_db
class TestTheInterface:
    def test_every_file_is_written_and_the_manifest_is_true(self, tmp_path):
        corpus()
        out, _, stdout = run_export(tmp_path)

        manifest = json.loads((out / export.MANIFEST_FILENAME).read_text("utf-8"))
        listed = {entry["path"]: entry for entry in manifest["files"]}
        for name in ("scan_history", "dependency_history", "agent_traces"):
            assert f"{name}.parquet" in listed
            assert f"{name}.csv" in listed
        for document in export.DOCUMENTS:
            assert any(
                path == document.target or path.startswith(document.target + "/")
                for path in listed
            ), document.target
        assert "weights/weights_v1.yaml" in listed
        assert "weights/weights_v2.yaml" in listed
        # Every listed file exists and its digest is its own.
        for path, entry in listed.items():
            assert sha(out / path) == entry["sha256"], path
            assert (out / path).stat().st_size == entry["bytes"]
        # And nothing is in the folder that the manifest does not vouch for.
        on_disk = {
            p.relative_to(out).as_posix()
            for p in out.rglob("*")
            if p.is_file() and p.name != export.MANIFEST_FILENAME
        }
        assert on_disk == set(listed)

        assert manifest["tables"]["scan_history"]["rows"] == 2
        assert manifest["tables"]["dependency_history"]["rows"] == 3
        assert manifest["tables"]["scan_history"]["by_formula_version"] == {"v1": 2}
        assert manifest["sources"] == ["corpus_scan"]
        assert "password" not in json.dumps(manifest["database"])
        assert "Exported" in stdout

    def test_a_document_keeps_its_signed_source(self, tmp_path):
        corpus()
        out, _, _ = run_export(tmp_path)
        manifest = json.loads((out / export.MANIFEST_FILENAME).read_text("utf-8"))
        listed = {entry["path"]: entry["source"] for entry in manifest["files"]}
        assert listed["corpus/corpus_manifest.json"].endswith("wp-4/corpus_manifest.json")
        assert listed["runs/inner/data.json"].endswith("wp-8/runs/inner/data.json")
        assert listed["scan_history.parquet"] == "database:scan_history"
        assert (out / "runs/ground_truth/labelled_set.jsonl").read_text("utf-8") == (
            "wp-8/labelled_set.jsonl\n"
        )

    def test_the_deliverables_are_archived_as_received(self, tmp_path):
        corpus()
        deliverables = fake_deliverables(tmp_path / "wp")
        _, archive, _ = run_export(tmp_path, deliverables=deliverables)

        assert sorted(p.name for p in archive.iterdir()) == sorted(
            p.name for p in deliverables.iterdir() if p.name != "wp-review"
        )
        for path in deliverables.rglob("*"):
            if path.is_file() and "wp-review" not in path.parts:
                copy = archive / path.relative_to(deliverables)
                assert copy.read_bytes() == path.read_bytes()


@pytest.mark.django_db
class TestTheTablesAreExact:
    def test_decimals_come_back_as_the_stored_decimals(self, tmp_path):
        corpus()
        out, _, _ = run_export(tmp_path)

        stored = {row.repo_full_name: row for row in ScanHistory.objects.all().order_by()}
        scans = pq.read_table(out / "scan_history.parquet").to_pylist()
        assert {row["repo_full_name"] for row in scans} == set(stored)
        for row in scans:
            original = stored[row["repo_full_name"]]
            assert row["risk_score"] == original.risk_score
            assert isinstance(row["risk_score"], Decimal)
            assert row["sampling_weight"] == original.sampling_weight
            assert row["snapshot_date"] == original.snapshot_date
            assert row["scan_history_id"] == str(original.scan_history_id)

        occurrences = pq.read_table(out / "dependency_history.parquet").to_pylist()
        cvss = sorted(row["cvss_max"] for row in occurrences if row["cvss_max"])
        assert cvss == [Decimal("9.8")]
        # A missing staleness stays missing: §5.2 treats it as unknown, not 0.
        assert any(row["staleness_days"] is None for row in occurrences)

        with (out / "scan_history.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        weights = {row["repo_full_name"]: row["sampling_weight"] for row in rows}
        assert weights["o/vulnerable"] == "12.345678"
        assert rows[0]["data_source"] == "corpus_scan"

    def test_the_same_database_exports_the_same_files(self, tmp_path):
        corpus()
        first, _, _ = run_export(tmp_path / "one")
        second, _, _ = run_export(tmp_path / "two")
        for name in (
            "scan_history.parquet",
            "scan_history.csv",
            "dependency_history.parquet",
            "dependency_history.csv",
            "agent_traces.parquet",
        ):
            assert sha(first / name) == sha(second / name), name

    def test_rows_sort_bytewise_whatever_the_collation(self, tmp_path):
        """Upper case before lower case is the C collation's order; en_US's
        would interleave them (decisions §14)."""
        corpus_repository("b-lower/repo", [{"staleness": 1}])
        corpus_repository("A-Upper/repo", [{"staleness": 1}])
        corpus_repository("a-lower/repo", [{"staleness": 1}])
        out, _, _ = run_export(tmp_path)
        names = [
            row["repo_full_name"]
            for row in pq.read_table(out / "scan_history.parquet").to_pylist()
        ]
        assert names == ["A-Upper/repo", "a-lower/repo", "b-lower/repo"]


@pytest.mark.django_db
class TestOnlyCorpusRowsUnlessAsked:
    def test_live_rows_and_traces_stay_out_by_default(self, tmp_path):
        corpus()
        live_rows()
        out, _, _ = run_export(tmp_path)

        names = {
            row["repo_full_name"]
            for row in pq.read_table(out / "scan_history.parquet").to_pylist()
        }
        assert "user/private-repo" not in names
        traces = pq.read_table(out / "agent_traces.parquet")
        assert traces.num_rows == 0
        # The empty file still says what it would hold.
        assert "retrieved_chunks_json" in traces.schema.names
        assert "private-repo" not in (out / "dependency_history.csv").read_text("utf-8")

    def test_all_includes_them_with_json_as_text(self, tmp_path):
        corpus()
        live_rows()
        out, _, _ = run_export(tmp_path, "--source", "all")

        manifest = json.loads((out / export.MANIFEST_FILENAME).read_text("utf-8"))
        assert manifest["tables"]["scan_history"]["by_data_source"] == {
            "corpus_scan": 2,
            "live_scan": 1,
        }
        traces = pq.read_table(out / "agent_traces.parquet").to_pylist()
        assert len(traces) == 1
        assert json.loads(traces[0]["retrieved_chunks_json"]) == [
            {"chunk_id": "c1", "score": 0.5}
        ]
        assert traces[0]["created_at"].tzinfo is not None


@pytest.mark.django_db
class TestRefusals:
    def test_a_missing_deliverable_is_named_before_anything_is_written(self, tmp_path):
        corpus()
        deliverables = fake_deliverables(tmp_path / "wp")
        (deliverables / "wp-9" / "wp9_judge_labels.csv").unlink()
        with pytest.raises(CommandError, match=r"wp-9/wp9_judge_labels\.csv"):
            run_export(tmp_path, deliverables=deliverables)
        assert not (tmp_path / "exports").exists()

    def test_a_second_export_needs_overwrite(self, tmp_path):
        corpus()
        run_export(tmp_path)
        with pytest.raises(CommandError, match="--overwrite"):
            run_export(tmp_path)

    def test_overwrite_removes_only_what_the_last_export_wrote(self, tmp_path):
        """research_data/exports/ also holds WP-5's dump and the v2 rescore
        panel on the research machine; an overwrite must never take them."""
        corpus()
        deliverables = fake_deliverables(tmp_path / "wp")
        old_run = deliverables / "wp-8" / "runs" / "A_old_model"
        old_run.mkdir()
        (old_run / "run.json").write_text("{}", encoding="utf-8")
        out, archive, _ = run_export(tmp_path, deliverables=deliverables)
        assert (out / "runs/A_old_model/run.json").exists()

        dump = out / "wp5_research_db.dump"
        dump.write_bytes(b"PGDMP")
        panel = out / "corpus_2026-10-07_v2_repositories.csv"
        panel.write_text("scan_history_id\n", encoding="utf-8")
        received = archive / "WP2_20261006.zip"
        received.write_bytes(b"PK")

        (old_run / "run.json").unlink()
        old_run.rmdir()
        run_export(tmp_path, "--overwrite", deliverables=deliverables)

        assert dump.read_bytes() == b"PGDMP"
        assert panel.exists()
        assert received.read_bytes() == b"PK"
        # The run that is no longer signed is gone with the manifest that listed it.
        assert not (out / "runs/A_old_model/run.json").exists()
        manifest = json.loads((out / export.MANIFEST_FILENAME).read_text("utf-8"))
        assert all("A_old_model" not in entry["path"] for entry in manifest["files"])
        assert all("wp5_research_db" not in entry["path"] for entry in manifest["files"])

    def test_an_archived_deliverable_is_not_copied_over_silently(self, tmp_path):
        corpus()
        _, archive, _ = run_export(tmp_path / "first")
        deliverables = tmp_path / "first" / "wp"
        with pytest.raises(CommandError, match="already holds wp-2, wp-3"):
            call_command(
                "export_research_data",
                "--out", str(tmp_path / "second"),
                "--deliverables", str(deliverables),
                "--archive", str(archive),
                stdout=StringIO(),
            )  # fmt: skip
        assert not (tmp_path / "second").exists()

    def test_no_archive_leaves_the_archive_alone(self, tmp_path):
        corpus()
        _, archive, _ = run_export(tmp_path, "--no-archive")
        assert not archive.exists()


@pytest.mark.django_db
class TestItOnlyReads:
    def test_the_guard_refuses_a_write_even_to_a_research_table(self):
        with pytest.raises(WriteRefused, match="scan_history"):
            check_read_only('INSERT INTO "scan_history" ("x") VALUES (1)')
        check_read_only('SELECT * FROM "scan_history"')  # reads pass

        with pytest.raises(WriteRefused), no_writes(), connection.cursor() as cursor:
            cursor.execute('DELETE FROM "dependency_history"')

    def test_the_export_issues_no_write(self, tmp_path):
        corpus()
        live_rows()
        statements = []

        def record(execute, sql, params, many, context):
            statements.append(sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(record):
            run_export(tmp_path, "--source", "all")
        assert statements  # it did read
        for sql in statements:
            check_read_only(sql)
