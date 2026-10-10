"""S3's analysis (§10 Phase 13 commit 7): the paired tests by hand, then the
tables over runs whose correctness pattern is known in advance.

§10 Phase 13's acceptance: "analysis renders from the pilot". Here it renders
from three synthetic runs; the pilot is the live version of the same command.
"""

from __future__ import annotations

import json
import math
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.research.corpus import append_jsonl
from apps.research.experiment import analysis, judge, runner
from apps.research.validation import stats
from tests.test_experiment_metrics import CVE_ITEM

# ── the statistics ─────────────────────────────────────────────────────────


class TestPairedStatistics:
    def test_mcnemar_exact_by_hand(self):
        """b=1, c=5: P(X<=1 | n=6) = (1+6)/64, two-sided = 14/64."""
        assert stats.mcnemar_exact(1, 5) == pytest.approx(14 / 64)
        assert stats.mcnemar_exact(5, 1) == pytest.approx(14 / 64)
        assert stats.mcnemar_exact(0, 0) == 1.0
        assert stats.mcnemar_exact(3, 3) == 1.0

    def test_signed_rank_exact_by_hand(self):
        """Five positive, untied differences: W+ = 15, the most extreme of the
        2^5 sign patterns, so the two-sided p is 2/32."""
        result = stats.wilcoxon_signed_rank([1, 2, 3, 4, 5])
        assert result["method"] == "exact"
        assert result["w_plus"] == 15
        assert result["p"] == pytest.approx(2 / 32)
        assert result["r"] == 1.0

    def test_signed_rank_with_ties_uses_the_corrected_normal(self):
        differences = [1, 1, 1, 1, 2, 2, -1, 0, 0]
        result = stats.wilcoxon_signed_rank(differences)
        assert result["method"] == "normal"
        assert result["n"] == 7  # zeros dropped
        # By hand: |d| ranks: the five 1s share ranks 1-5 (3.0), the two 2s 6-7 (6.5).
        w_plus = 4 * 3.0 + 2 * 6.5
        assert result["w_plus"] == w_plus
        mean = 7 * 8 / 4
        variance = 7 * 8 * 15 / 24 - ((5**3 - 5) + (2**3 - 2)) / 48
        z = (w_plus - mean - 0.5) / math.sqrt(variance)
        assert result["p"] == pytest.approx(math.erfc(z / math.sqrt(2)))

    def test_no_nonzero_difference_is_no_evidence(self):
        assert stats.wilcoxon_signed_rank([0, 0, 0])["p"] == 1.0

    def test_holm_by_hand(self):
        assert stats.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
        assert stats.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])


# ── the tables ─────────────────────────────────────────────────────────────


def item(index: int, ecosystem: str = "npm") -> dict:
    built = json.loads(json.dumps(CVE_ITEM))
    built["item_id"] = f"S3-{ecosystem}{index:03d}"
    built["ecosystem"] = ecosystem
    built["context_rows"] = [{"package": "lodash"}]
    return built


def record(entry: dict, condition: str, *, correct: bool, status: str = "ok") -> dict:
    version = "4.17.21" if correct else "4.17.20"
    return {
        "item_id": entry["item_id"],
        "condition": condition,
        "status": status,
        "grounding": "low" if condition == "C" and not correct else "sufficient",
        "generation": {
            "summary_md": "Could not retrieve enough documentation."
            if condition == "C" and not correct
            else "Upgrade.",
            "fixes": [
                {"package": "lodash", "fix_type": "upgrade", "target_version": version}
            ],
        },
        "retrieved": [],
        "shown_chunk_ids": [],
    }


#: Which items each condition gets right: A 2/8, B 6/8, C 7/8 (npm and PyPI alike).
PATTERN = {"A": {0, 1}, "B": {0, 1, 2, 3, 4, 5}, "C": {0, 1, 2, 3, 4, 5, 6}}


@pytest.fixture
def runs(tmp_path):
    items = [item(i, eco) for eco in ("npm", "pypi") for i in range(8)]
    runs_dir = tmp_path / "runs"
    cache = judge.JudgeCache(runs_dir / judge.CACHE_FILENAME)
    dirs = []
    for condition, right in PATTERN.items():
        directory = runs_dir / f"{condition}_abcdef12_model"
        directory.mkdir(parents=True)
        (directory / runner.RUN_FILENAME).write_text(
            json.dumps(
                {
                    "run_id": directory.name,
                    "condition": condition,
                    "items_file": "labelled_set.jsonl",
                    "items_sha256": "abcdef12" * 8,
                    "items": len(items),
                    "generator_model": "test-model",
                }
            )
        )
        for entry in items:
            index = int(entry["item_id"][-3:])
            status = (
                "failed" if (condition, entry["item_id"]) == ("A", "S3-npm007") else "ok"
            )
            rec = record(entry, condition, correct=index in right, status=status)
            append_jsonl(directory / runner.ITEMS_FILENAME, rec)
            if status != "ok":
                continue
            verdict = judge.FAITHFUL if index in right else judge.MAJOR
            cache.put(
                judge.cache_key(
                    judge.FAITHFULNESS,
                    entry["item_id"],
                    condition,
                    {
                        "target": entry["target"],
                        "generation": rec["generation"],
                        "shown": [],
                    },
                ),
                {
                    "verdict": verdict,
                    "stated_verdict": verdict,
                    "item_id": entry["item_id"],
                },
            )
        dirs.append(directory)
    labelled = tmp_path / "labelled_set.jsonl"
    for entry in items:
        append_jsonl(labelled, entry)
    return {
        "dirs": dirs,
        "items": {entry["item_id"]: entry for entry in items},
        "cache": judge.JudgeCache(runs_dir / judge.CACHE_FILENAME),
        "labelled": labelled,
        "runs_dir": runs_dir,
    }


class TestTheTables:
    def test_correctness_rates_are_the_known_pattern(self, runs):
        dataset = analysis.load(runs["dirs"], runs["items"], runs["cache"])
        text, tables = analysis.render(dataset, bootstrap=50, seed=1)
        rates = {
            (row[0], row[1], row[2]): (int(row[3]), int(row[4]))
            for row in tables["correctness.csv"][1:]
        }
        assert rates[("B", "npm", "all")] == (8, 6)
        assert rates[("C", "pypi", "all")] == (8, 7)
        assert rates[("A", "npm", "all")] == (7, 2)  # the failed generation is not scored
        assert "## Correctness (deterministic)" in text

    def test_mcnemar_counts_discordant_pairs_and_excludes_failures(self, runs):
        dataset = analysis.load(runs["dirs"], runs["items"], runs["cache"])
        tests = {
            (t.first, t.second, t.group): t
            for t in analysis.correctness_tests(dataset, 50, 1)
        }
        ab_npm = tests[("A", "B", "npm")]
        # A right on {0,1}; B right on {0..5}; item 7 failed under A.
        assert ab_npm.statistic["first_only_correct"] == 0
        assert ab_npm.statistic["second_only_correct"] == 4
        assert (ab_npm.n, ab_npm.excluded) == (7, 1)
        assert ab_npm.p == pytest.approx(stats.mcnemar_exact(0, 4))
        # Holm adjusted within the family, never below the raw p.
        assert all(t.p_holm >= t.p for t in tests.values())

    def test_faithfulness_is_tested_on_the_ordinal_scale(self, runs):
        dataset = analysis.load(runs["dirs"], runs["items"], runs["cache"])
        tests = {
            (t.first, t.second, t.group): t for t in analysis.faithfulness_tests(dataset)
        }
        bc = tests[("B", "C", "all")]
        assert bc.statistic["r"] == 1.0  # every change is B major -> C faithful
        assert bc.n == 16

    def test_the_answer_not_given_items_are_their_own_table_and_family(self, runs):
        """decisions §13.13. Items 0-3 show a fix that is correct if copied."""
        items = json.loads(json.dumps(runs["items"]))
        for entry in items.values():
            if int(entry["item_id"][-3:]) < 4:
                entry["target"]["advisories"] = [
                    {"osv_id": "A", "fixed_version": "4.17.21"}
                ]
        dataset = analysis.load(runs["dirs"], items, runs["cache"])
        text, tables = analysis.render(dataset, bootstrap=20, seed=1)

        rates = {
            (row[0], row[1]): (int(row[2]), int(row[3]))
            for row in tables["correctness_not_given.csv"][1:]
        }
        # Items 4-7 only: A right on none (and npm 7 failed), B on 4-5, C on 4-6.
        assert rates[("A", "npm")] == (3, 0)
        assert rates[("B", "all")] == (8, 4)
        assert rates[("C", "pypi")] == (4, 3)
        assert "answer given 8, not given 8" in text

        family = analysis.correctness_tests(dataset, 20, 1, answer_not_given=True)
        bc = {(t.first, t.second, t.group): t for t in family}[("B", "C", "all")]
        assert bc.metric == analysis.NOT_GIVEN
        assert bc.n == 8
        assert bc.statistic["first_only_correct"] == 0
        assert bc.statistic["second_only_correct"] == 2
        assert analysis.NOT_GIVEN in {row[0] for row in tables["paired_tests.csv"][1:]}

    def test_an_all_given_set_says_the_restricted_comparison_is_empty(self, runs):
        items = json.loads(json.dumps(runs["items"]))
        for entry in items.values():
            entry["target"]["advisories"] = [{"osv_id": "A", "fixed_version": "4.17.21"}]
        text, tables = analysis.render(
            analysis.load(runs["dirs"], items, runs["cache"]), bootstrap=20, seed=1
        )
        assert "this comparison is empty" in text
        assert len(tables["correctness_not_given.csv"]) == 1

    def test_the_cve_fix_contrast_comes_before_the_confounded_one(self, runs):
        text, _ = analysis.render(
            analysis.load(runs["dirs"], runs["items"], runs["cache"]),
            bootstrap=20,
            seed=1,
        )
        assert text.index("| cve_fix | A |") < text.index(
            "| full set (case-mix confounded) |"
        )

    def test_the_calibration_table_crosses_declaration_with_the_flag(self, runs):
        _, tables = analysis.render(
            analysis.load(runs["dirs"], runs["items"], runs["cache"]), bootstrap=0, seed=1
        )
        rows = {(r[0], r[1], r[2]): r for r in tables["calibration.csv"][1:]}
        assert rows[("C", "npm", "low")][4] == 1  # the one C got wrong, declared
        assert rows[("C", "npm", "sufficient")][4] == 0

    def test_unjudged_generations_are_counted(self, runs):
        empty = judge.JudgeCache(runs["runs_dir"] / "other_cache.jsonl")
        dataset = analysis.load(runs["dirs"], runs["items"], empty)
        assert dataset.unjudged == 47
        text, _ = analysis.render(dataset, bootstrap=0, seed=1)
        assert "47 successful generation(s) are not judged yet" in text

    def test_judging_the_missing_ones_then_rereading_hits_the_cache(self, runs):
        path = runs["runs_dir"] / "fresh_cache.jsonl"
        asked = []

        def fake(system, user):
            asked.append(1)
            return {"claims": [], "verdict": "faithful", "note": ""}

        analysis.load(
            runs["dirs"],
            runs["items"],
            judge.JudgeCache(path),
            judge_missing=judge.Judge(
                cache=judge.JudgeCache(path), complete=fake, pace_seconds=0
            ),
        )
        reread = analysis.load(runs["dirs"], runs["items"], judge.JudgeCache(path))
        assert len(asked) == 47
        assert reread.unjudged == 0


class TestRefusals:
    def test_two_runs_of_one_condition_are_refused(self, runs):
        with pytest.raises(analysis.AnalysisError, match="one run per condition"):
            analysis.load(
                [runs["dirs"][0], runs["dirs"][0]], runs["items"], runs["cache"]
            )

    def test_runs_over_different_labelled_sets_are_not_paired(self, runs):
        manifest = runs["dirs"][1] / runner.RUN_FILENAME
        data = json.loads(manifest.read_text())
        data["items_sha256"] = "0" * 64
        manifest.write_text(json.dumps(data))
        with pytest.raises(analysis.AnalysisError, match="different labelled sets"):
            analysis.load(runs["dirs"], runs["items"], runs["cache"])


class TestTheCommand:
    def test_it_writes_the_tables(self, runs, tmp_path):
        out = tmp_path / "analysis"
        stdout = StringIO()
        call_command(
            "analyze_experiment",
            "--runs", *[d.name for d in runs["dirs"]],
            "--runs-dir", str(runs["runs_dir"]),
            "--items", str(runs["labelled"]),
            "--out", str(out),
            "--bootstrap", "20",
            stdout=stdout,
        )  # fmt: skip
        for name in ("tables.md", "correctness.csv", "paired_tests.csv", "metrics.csv"):
            assert (out / name).exists(), name
        assert (
            "Analysed 48 item-condition record(s) across 3 condition(s)."
            in stdout.getvalue()
        )

    def test_judging_needs_the_key(self, runs, settings):
        settings.GEMINI_API_KEY = ""
        with pytest.raises(CommandError, match="GEMINI_API_KEY"):
            call_command(
                "analyze_experiment", "--runs", runs["dirs"][0].name,
                "--runs-dir", str(runs["runs_dir"]), "--items", str(runs["labelled"]),
                "--judge", stdout=StringIO(),
            )  # fmt: skip
