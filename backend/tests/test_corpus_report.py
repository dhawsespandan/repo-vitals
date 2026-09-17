"""`corpus_report` — the descriptive figures (§10 Phase 11).

Two things are worth testing about a chart and neither is its appearance.

**The numbers behind it.** `collect` joins corpus rows to the strata in
`corpus_manifest.json` and recomputes the flag rule; a figure drawn from the
wrong join, or from the wrong weights file, is an instrument that is accurate
about the wrong quantity — which is worse than none, because it ends the
investigation (`docs/decisions.md` §8.15).

**What it refuses to include.** Only `corpus_scan` rows. A histogram that
quietly mixed in the developer's own live scans would put product data into
S1's descriptive statistics.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date
from decimal import Decimal

import pytest

from apps.research.charts import (
    FLAGGED_RATE_FILENAME,
    HISTOGRAM_FILENAME,
    collect,
    render_figures,
    summary,
)
from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scoring.weights import active_weights

SNAPSHOT = date(2026, 9, 16)
OTHER_SNAPSHOT = date(2026, 8, 1)


def manifest_file(tmp_path, repositories) -> object:
    path = tmp_path / "corpus_manifest.json"
    path.write_text(
        json.dumps(
            {
                "run_date": SNAPSHOT.isoformat(),
                "cells": [
                    {"key": "javascript|5-20|lt6|le2015", "pushed": "lt6"},
                    {"key": "python|5-20|gt48|le2015", "pushed": "gt48"},
                ],
                "repositories": repositories,
            }
        ),
        encoding="utf-8",
    )
    return path


def frame_entry(repo_id: int, ecosystem: str, cell: str) -> dict:
    return {
        "full_name": f"owner/repo-{repo_id}",
        "github_repo_id": repo_id,
        "owner_login": "owner",
        "owner_id": 1,
        "default_branch": "main",
        "ecosystem": ecosystem,
        "cell": cell,
        "sampling_weight": 4.0,
        "manifests": [],
    }


def corpus_row(
    repo_id: int,
    *,
    ecosystem: str = "npm",
    score: str = "72.00",
    classification: str = "medium",
    snapshot: date = SNAPSHOT,
    data_source: str = DataSource.CORPUS_SCAN.value,
    occurrences: list[dict] | None = None,
) -> ScanHistory:
    entry = ScanHistory.objects.create(
        github_user_id=1,
        github_username="owner",
        github_repo_id=repo_id,
        repo_full_name=f"owner/repo-{repo_id}",
        ecosystems=ecosystem,
        risk_score=Decimal(score),
        classification=classification,
        dependency_count=len(occurrences or []),
        flagged_dependency_count=0,
        scoring_formula_version=active_weights().version,
        data_source=data_source,
        snapshot_date=snapshot if data_source == DataSource.CORPUS_SCAN.value else None,
        sampling_weight=Decimal("4.0")
        if data_source == DataSource.CORPUS_SCAN.value
        else None,
        scanned_at="2026-09-16T00:00:00Z",
    )
    for index, occurrence in enumerate(occurrences or []):
        DependencyHistory.objects.create(
            scan_history=entry,
            ecosystem=ecosystem,
            package_name=f"pkg-{index}",
            manifest_path="package.json",
            dependency_group="runtime",
            **occurrence,
        )
    return entry


CLEAN = {"staleness_days": 0}
DEPRECATED = {"staleness_days": 0, "is_deprecated": True}
VULNERABLE = {"staleness_days": 0, "vulnerability_count": 2}
UNASSESSABLE = {"is_unassessable": True}


def _matplotlib_loads() -> str:
    """Empty if matplotlib imports, otherwise why it does not.

    Not `pytest.importorskip`. Two different failures wear the same
    `ImportError`, and only one of them is a reason to skip:

    *Not installed* is a real problem. `requirements-dev.txt` pulls in
    `requirements-research.txt`, so CI has matplotlib, and a run that silently
    skipped these because the install was broken would hide exactly the kind of
    dependency drift `test_matplotlib_is_declared_research_only` exists to
    catch — so that test never skips.

    *Installed but unloadable* is the platform's answer, not the code's. This
    machine blocked matplotlib's `_image` DLL under a Windows Application
    Control policy between one test run and the next; there is nothing to
    verify on such a box and nothing to fix in this repository.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot
    except ImportError as exc:
        return str(exc)
    return ""


MATPLOTLIB_ERROR = _matplotlib_loads()


@pytest.mark.django_db
class TestCollect:
    def test_only_corpus_rows_are_counted(self, tmp_path):
        """A live scan of the developer's own repository sits in the same table
        on a dev machine. Putting it in S1's descriptive statistics would be
        product data in a research figure."""
        corpus_row(1, occurrences=[CLEAN])
        corpus_row(2, data_source=DataSource.LIVE_SCAN.value, occurrences=[CLEAN])
        path = manifest_file(
            tmp_path,
            [
                frame_entry(1, "npm", "javascript|5-20|lt6|le2015"),
                frame_entry(2, "npm", "javascript|5-20|lt6|le2015"),
            ],
        )

        stats = collect(path)

        assert stats.repositories == 1

    def test_it_charts_one_run_not_two_superimposed(self, tmp_path):
        """A research database legitimately holds more than one corpus run.
        Defaulting to the most recent is the useful behaviour; pooling them
        silently is not."""
        corpus_row(1, occurrences=[CLEAN])
        corpus_row(2, snapshot=OTHER_SNAPSHOT, occurrences=[CLEAN])
        path = manifest_file(
            tmp_path,
            [
                frame_entry(1, "npm", "javascript|5-20|lt6|le2015"),
                frame_entry(2, "npm", "javascript|5-20|lt6|le2015"),
            ],
        )

        assert collect(path).snapshot_date == SNAPSHOT
        assert collect(path).repositories == 1
        assert collect(path, OTHER_SNAPSHOT).repositories == 1

    def test_scores_are_grouped_by_the_ecosystem_the_frame_sampled_for(self, tmp_path):
        corpus_row(1, ecosystem="npm", score="90.00", occurrences=[CLEAN])
        corpus_row(2, ecosystem="pypi", score="40.00", occurrences=[CLEAN])
        path = manifest_file(
            tmp_path,
            [
                frame_entry(1, "npm", "javascript|5-20|lt6|le2015"),
                frame_entry(2, "pypi", "python|5-20|gt48|le2015"),
            ],
        )

        stats = collect(path)

        assert stats.scores_by_ecosystem == {"npm": [90.0], "pypi": [40.0]}

    def test_the_flag_rule_is_the_formulas_own_disjunction(self, tmp_path):
        """§5.2: deprecated OR vulnerable OR stale past the threshold. Checked
        against `engine.flag_reasons` rather than trusted, because this counts
        through `values_list` for speed and a fast copy of a rule is a copy
        that can drift."""
        from apps.scoring.engine import flag_reasons
        from apps.scoring.normalize import Signals

        weights = active_weights()
        stale = {"staleness_days": weights.stale_flag_days + 1}
        corpus_row(1, occurrences=[CLEAN, DEPRECATED, VULNERABLE, stale, UNASSESSABLE])
        path = manifest_file(
            tmp_path, [frame_entry(1, "npm", "javascript|5-20|lt6|le2015")]
        )

        stats = collect(path)

        expected = sum(
            1
            for signals in (
                Signals(staleness_days=0),
                Signals(staleness_days=0, is_deprecated=True),
                Signals(staleness_days=0, vulnerability_count=2),
                Signals(staleness_days=weights.stale_flag_days + 1),
            )
            if flag_reasons(signals, weights)
        )
        assert stats.flagged == expected == 3
        assert stats.occurrences == 5
        assert stats.unassessable == 1

    def test_an_unassessable_row_is_never_flagged(self, tmp_path):
        """§5.2 excludes it from scoring and from every denominator. Counting
        it as flagged — or as clean — would both be claims we cannot make."""
        corpus_row(1, occurrences=[UNASSESSABLE, UNASSESSABLE])
        path = manifest_file(
            tmp_path, [frame_entry(1, "npm", "javascript|5-20|lt6|le2015")]
        )
        stats = collect(path)
        assert stats.flagged == 0
        assert stats.unassessable == 2

    def test_a_row_the_manifest_does_not_know_is_reported_not_dropped(self, tmp_path):
        """The database and the manifest describe different runs. Silently
        dropping the row would make the figures look complete."""
        corpus_row(1, occurrences=[CLEAN])
        corpus_row(99, occurrences=[CLEAN])
        path = manifest_file(
            tmp_path, [frame_entry(1, "npm", "javascript|5-20|lt6|le2015")]
        )

        stats = collect(path)

        assert stats.unmatched == 1

    def test_strata_come_from_the_frame_not_from_the_database(self, tmp_path):
        """The cell a repository was drawn from is a property of the sampling
        frame. `scan_history` has no column for it and should not: it would
        only ever apply to one of the table's two data sources."""
        corpus_row(1, occurrences=[DEPRECATED, CLEAN])
        corpus_row(2, ecosystem="pypi", occurrences=[CLEAN, CLEAN])
        path = manifest_file(
            tmp_path,
            [
                frame_entry(1, "npm", "javascript|5-20|lt6|le2015"),
                frame_entry(2, "pypi", "python|5-20|gt48|le2015"),
            ],
        )

        stats = collect(path)

        by_key = {stratum.key: stratum for stratum in stats.strata}
        assert by_key["javascript|5-20|lt6|le2015"].flagged_rate == 0.5
        assert by_key["python|5-20|gt48|le2015"].flagged_rate == 0.0
        assert by_key["python|5-20|gt48|le2015"].pushed == "gt48"


@pytest.mark.django_db
@pytest.mark.skipif(
    bool(MATPLOTLIB_ERROR),
    reason=f"matplotlib will not load here: {MATPLOTLIB_ERROR}",
)
class TestFigures:
    def test_both_figures_are_written(self, tmp_path):
        corpus_row(1, ecosystem="npm", score="90.00", occurrences=[CLEAN])
        corpus_row(2, ecosystem="pypi", score="30.00", occurrences=[DEPRECATED])
        path = manifest_file(
            tmp_path,
            [
                frame_entry(1, "npm", "javascript|5-20|lt6|le2015"),
                frame_entry(2, "pypi", "python|5-20|gt48|le2015"),
            ],
        )

        figures = render_figures(collect(path), tmp_path / "out")

        names = {figure.name for figure in figures}
        assert names == {HISTOGRAM_FILENAME, FLAGGED_RATE_FILENAME}
        for figure in figures:
            assert figure.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_an_empty_corpus_draws_nothing_rather_than_an_empty_axis(self, tmp_path):
        path = manifest_file(tmp_path, [])
        assert render_figures(collect(path), tmp_path / "out") == []


@pytest.mark.django_db
class TestSummary:
    def test_it_states_what_the_figures_cannot_show(self, tmp_path):
        """D14's cross-section, and the oversampling that makes the unweighted
        shape the corpus's rather than GitHub's. Both belong beside the
        picture, because the picture is what gets pasted into a report."""
        corpus_row(1, occurrences=[CLEAN])
        path = manifest_file(
            tmp_path, [frame_entry(1, "npm", "javascript|5-20|lt6|le2015")]
        )

        text = summary(collect(path), [])

        assert "cross-section as of one date" in text
        assert "sampling_weight" in text
        assert "per *occurrence*, not per repository" in text

    def test_it_says_when_the_manifest_and_the_database_disagree(self, tmp_path):
        corpus_row(99, occurrences=[CLEAN])
        path = manifest_file(
            tmp_path, [frame_entry(1, "npm", "javascript|5-20|lt6|le2015")]
        )
        assert "different runs" in summary(collect(path), [])

    def test_it_reports_the_unassessable_rate_wp5_asks_for(self, tmp_path):
        corpus_row(1, occurrences=[CLEAN, UNASSESSABLE])
        path = manifest_file(
            tmp_path, [frame_entry(1, "npm", "javascript|5-20|lt6|le2015")]
        )
        assert "Unassessable occurrences: 1 (50.0%)" in summary(collect(path), [])


def test_matplotlib_is_declared_research_only():
    """§8: it must be installed for the figures and never installed on Render.

    This test never skips, because it is the one that protects the deploy.
    `requirements.txt` is what the web service installs, against a 512 MB tier
    already holding Django, the scan threads and fastembed's ONNX model (§8.9);
    matplotlib and NumPy are ~50 MB of import no request path would reach.
    `requirements-dev.txt` includes the research file so CI has it and
    `TestFigures` runs for real rather than skipping.
    """
    backend = pathlib.Path(__file__).resolve().parent.parent
    runtime = (backend / "requirements.txt").read_text(encoding="utf-8")
    research = (backend / "requirements-research.txt").read_text(encoding="utf-8")
    dev = (backend / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "matplotlib" in research
    assert "matplotlib" not in runtime
    assert "-r requirements-research.txt" in dev


def test_the_charts_module_imports_without_matplotlib():
    """The import is inside `render_figures`, so `corpus_report` loads on a
    machine that has no matplotlib and refuses with a sentence naming the file
    to install — rather than failing at import time, several frames from the
    cause."""
    import importlib

    module = importlib.import_module("apps.research.charts")
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    header, _, _ = source.partition("def render_figures")
    assert "import matplotlib" not in header
