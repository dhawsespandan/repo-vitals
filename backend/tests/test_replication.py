"""The replication notebooks' code (§10 Phase 14 commit 2).

Phase 14's acceptance: "exports regenerate every notebook table". Each test
here builds the signed artifact the way the study did — `validate_formula`
over corpus rows, `analyze_experiment` over runs — exports it with
`export_research_data`, and regenerates it from the export alone:

* the panel built from Parquet is the panel `load_panel` builds from the
  database, repository for repository and score for score;
* WP-6's run, re-run from the export with no database query and no socket,
  writes the same report folder;
* WP-8's tables, re-rendered with correctness recomputed, are the same files;
* both notebooks execute top to bottom against such an export, so a notebook
  cell that drifts from the code it calls fails here rather than in File C.
"""

from __future__ import annotations

import json
import shutil
import socket
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.research import export, replication
from apps.research.validation import panel
from apps.scoring.weights import load_weights
from tests.test_experiment_analysis import runs  # noqa: F401 - fixture
from tests.test_export_research_data import fake_deliverables
from tests.test_validation_harness import anchor_files, build_corpus_rows
from tests.test_validation_pipeline import RECONCILED

NOTEBOOKS = Path(settings.BASE_DIR).parent / "notebooks"


@pytest.fixture
def no_sockets(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(f"network access attempted: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def signed_validation(tmp_path, deliverables: Path) -> Path:
    """WP-6's folder, produced by `validate_formula` exactly as WP-6 ran it."""
    matrix = deliverables / "wp-3" / "wp3_matrix_final.csv"
    matrix.write_text(RECONCILED, encoding="utf-8")
    out = deliverables / "wp-6" / "validation_report"
    shutil.rmtree(out)
    source = anchor_files(tmp_path, out)
    anchors_csv = deliverables / "wp-2" / "wp2_anchor_set.csv"
    shutil.copyfile(source, anchors_csv)
    call_command(
        "validate_formula",
        "--ahp", str(matrix),
        "--anchors", str(anchors_csv),
        "--out", str(out),
        "--skip-reference",
        "--bootstrap", "40",
        "--pypi-shift", "deprecation=-0.14,severity=+0.07,staleness=+0.07",
        stdout=StringIO(),
    )  # fmt: skip
    # WP-6's folder holds the anchor scan beside the report, not under anchors/.
    shutil.move(out / "anchors" / "anchor_scan.json", out / "anchor_scan.json")
    shutil.rmtree(out / "anchors")
    return out


def signed_runs(fixture: dict, deliverables: Path) -> Path:
    """WP-8's folders: the runs, the labelled set, and `analyze_experiment`'s tables."""
    runs_dir = deliverables / "wp-8" / "runs"
    shutil.rmtree(runs_dir)
    runs_dir.mkdir()
    for directory in fixture["dirs"]:
        shutil.copytree(directory, runs_dir / directory.name)
    shutil.copyfile(fixture["labelled"], deliverables / "wp-8" / "labelled_set.jsonl")
    call_command(
        "analyze_experiment",
        "--runs", *[d.name for d in fixture["dirs"]],
        "--runs-dir", str(fixture["runs_dir"]),
        "--items", str(fixture["labelled"]),
        "--out", str(runs_dir / "analysis"),
        "--bootstrap", "30",
        stdout=StringIO(),
    )  # fmt: skip
    return runs_dir


def exported(tmp_path, deliverables: Path) -> Path:
    out = tmp_path / "research_data" / "exports"
    call_command(
        "export_research_data",
        "--out", str(out),
        "--deliverables", str(deliverables),
        "--no-archive",
        stdout=StringIO(),
    )  # fmt: skip
    return out


@pytest.fixture
def study(tmp_path, runs):  # noqa: F811 - the imported fixture
    """A complete export: corpus rows, WP-6's folder and WP-8's, as signed."""
    build_corpus_rows()
    deliverables = fake_deliverables(tmp_path / "wp")
    signed_validation(tmp_path, deliverables)
    signed_runs(runs, deliverables)
    return exported(tmp_path, deliverables)


# ── the panel ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestThePanel:
    def test_the_exported_panel_is_the_database_panel(self, study):
        from_database = panel.load_panel()
        from_export = replication.panel_from_export(study)

        assert from_export.snapshot_date == from_database.snapshot_date
        assert [r.full_name for r in from_export.repositories] == sorted(
            r.full_name for r in from_database.repositories
        )
        by_name = {r.full_name: r for r in from_database.repositories}
        for repository in from_export.repositories:
            original = by_name[repository.full_name]
            assert repository.occurrences == original.occurrences
            assert repository.stored_score == original.stored_score
            assert repository.sampling_weight == original.sampling_weight
        for version in ("v1", "v2", "v0_equal"):
            weights = load_weights(version)
            ours = {
                s.repository.full_name: s.score
                for s in panel.score_panel(from_export, weights)
            }
            theirs = {
                s.repository.full_name: s.score
                for s in panel.score_panel(from_database, weights)
            }
            assert ours == theirs, version

    def test_an_order_is_followed_and_must_be_complete(self, study):
        names = [r.full_name for r in replication.panel_from_export(study).repositories]
        reordered = replication.panel_from_export(study, order=names[::-1])
        assert [r.full_name for r in reordered.repositories] == names[::-1]
        with pytest.raises(replication.ReplicationError, match="not in the order"):
            replication.panel_from_export(study, order=names[1:])

    def test_a_tampered_file_is_named(self, study):
        assert replication.verify_export(study).ok
        target = study / "dependency_history.csv"
        target.write_text(target.read_text("utf-8") + "\n", encoding="utf-8")
        (study / "runs" / "analysis" / "tables.md").unlink()
        check = replication.verify_export(study)
        assert not check.ok
        assert check.mismatched == ["dependency_history.csv"]
        assert check.missing == ["runs/analysis/tables.md"]


# ── S1 ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestS1Regenerates:
    def test_wp6s_folder_comes_back_from_the_export_alone(
        self, study, tmp_path, no_sockets, django_assert_max_num_queries
    ):
        with django_assert_max_num_queries(0):
            run = replication.rerun_validation(study, tmp_path / "again")
        assert run.reproduction.all_match
        results = replication.compare_folders(
            tmp_path / "again",
            study / replication.VALIDATION_DIR,
            list(replication.VALIDATION_FILES),
        )
        assert [r.name for r in results if r.status != "identical"] == []

    def test_a_different_matrix_is_refused(self, study, tmp_path):
        matrix = study / "ahp" / "wp3_matrix_final.csv"
        matrix.write_text(matrix.read_text("utf-8").replace("2.8284", "3"), "utf-8")
        with pytest.raises(replication.ReplicationError, match="sha256 differs"):
            replication.rerun_validation(study, tmp_path / "again")


# ── S3 ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestS3Regenerates:
    def test_wp8s_tables_come_back_with_correctness_recomputed(self, study, tmp_path):
        replicated = replication.s3_dataset(study)
        assert replicated.disagreements == []
        assert len(replicated.dataset.rows) == 48

        bootstrap, seed = replication.analysis_parameters(study)
        assert (bootstrap, seed) == (30, 42)
        replication.s3_tables(
            replicated.dataset, tmp_path / "again", bootstrap=bootstrap, seed=seed
        )
        results = replication.compare_folders(
            tmp_path / "again",
            study / replication.ANALYSIS_DIR,
            replication.s3_table_files(study),
        )
        assert {r.name for r in results} >= {
            "tables.md",
            "metrics.csv",
            "paired_tests.csv",
        }
        assert [r.name for r in results if r.status != "identical"] == []

    def test_a_changed_generation_is_a_disagreement(self, study):
        """Correctness is recomputed, not read: edit an answer and it shows."""
        items = study / "runs" / "B_abcdef12_model" / "items.jsonl"
        lines = items.read_text("utf-8").splitlines()
        first = json.loads(lines[0])
        first["generation"]["fixes"][0]["target_version"] = "4.17.20"
        items.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n", "utf-8")

        disagreements = replication.s3_dataset(study).disagreements
        assert (first["item_id"], "B", "correct", "True", "False") in disagreements


# ── comparisons ────────────────────────────────────────────────────────────


class TestComparisons:
    def test_a_float_in_its_last_digits_is_reported_as_such(self):
        signed = "a,b\nx,0.051428571428571435\n"
        regenerated = "a,b\nx,0.05142857142857143\n"
        result = replication.compare_text("precision.csv", regenerated, signed)
        assert result.identical
        assert result.status == "equal to float precision"
        assert result.float_cells == 1

    def test_a_different_number_is_a_difference(self):
        result = replication.compare_text("p.csv", "a\n0.0515\n", "a\n0.0514\n")
        assert not result.identical
        assert result.status == "differs"
        # A rounded table is never forgiven: markdown is compared as text.
        assert not replication.compare_text(
            "t.md", "0.05142857142857143", "0.051428571428571435"
        ).identical

    def test_only_the_generated_at_lines_are_skipped(self):
        signed = (
            "Generated by `manage.py validate_formula` (x) on 2026-10-08.\nrho 0.047\n"
        )
        regenerated = (
            "Generated by `manage.py validate_formula` (x) on 2026-10-10.\nrho 0.047\n"
        )
        assert replication.compare_text("report.md", regenerated, signed).identical
        assert not replication.compare_text(
            "report.md", regenerated.replace("0.047", "0.048"), signed
        ).identical


# ── the notebooks ──────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["13_3_validation.ipynb", "13_1_analysis.ipynb"])
def test_the_notebook_runs_against_an_export(study, name, monkeypatch, tmp_path):
    """Every cell, top to bottom, in a fresh kernel; their asserts are the checks."""
    import nbformat
    from nbclient import NotebookClient

    monkeypatch.setenv("RV_EXPORTS", str(study))
    monkeypatch.setenv("RV_NOTEBOOK_WORK", str(tmp_path / "work"))
    monkeypatch.delenv("RV_WP9_KEY", raising=False)
    notebook = nbformat.read(NOTEBOOKS / name, as_version=4)
    NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOKS)}},
    ).execute()
    errors = [
        output
        for cell in notebook.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "error"
    ]
    assert errors == []


def test_the_committed_notebooks_carry_no_local_path():
    for name in ("13_3_validation.ipynb", "13_1_analysis.ipynb"):
        text = (NOTEBOOKS / name).read_text(encoding="utf-8")
        assert "/home/" not in text and "C:\\\\Users" not in text, name


def test_the_notebook_settings_open_no_database():
    """`config.settings.offline` is the notebooks' guarantee, so it is tested."""
    import subprocess
    import sys

    code = (
        "import os, django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings.offline'; "
        "django.setup(); from django.db import connection\n"
        "try:\n    connection.cursor()\nexcept Exception as exc:\n    print(type(exc).__name__)"
    )
    found = subprocess.run(  # noqa: S603 - this interpreter, a fixed script
        [sys.executable, "-c", code],
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in __import__("os").environ.items() if k != "DATABASE_URL"},
    )
    assert found.stdout.strip() == "ImproperlyConfigured"


def test_the_export_interface_names_what_file_c_reads():
    """File C §0.1's inventory, by the paths the notebooks open."""
    targets = {document.target for document in export.DOCUMENTS}
    for needed in (
        "validation_report",
        "runs",
        "runs/ground_truth/labelled_set.jsonl",
        "corpus/corpus_manifest.json",
        "judge_validation/wp9_judge_labels.csv",
        "ahp/wp3_matrix_final.csv",
        "anchors/wp2_anchor_set.csv",
    ):
        assert needed in targets, needed
