"""The corpus panel, the statistics underneath, and entropy weights (RQ1).

Entropy is checked against the formula worked by hand on a three-row column,
and against its two defining behaviours: a signal that never varies carries no
weight, and a rare-but-present one carries more than an evenly spread one —
which is exactly why File C expects entropy and AHP to disagree about
deprecation and calls that a finding rather than a failure.
"""

from __future__ import annotations

import math
import random
from datetime import date
from decimal import Decimal

import pytest

from apps.research.models import DataSource
from apps.research.validation import entropy, panel, stats
from apps.scoring.engine import roll_up, score_occurrence
from apps.scoring.weights import active_weights, load_weights
from tests.corpus_rows import SNAPSHOT, corpus_repository, signals_of

# ── stats ──────────────────────────────────────────────────────────────────


class TestStats:
    def test_ties_share_the_average_rank(self):
        assert stats.ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]

    def test_spearman_of_a_monotone_relation_is_one(self):
        x = [1, 2, 3, 4, 5]
        assert stats.spearman(x, [v**3 for v in x]) == pytest.approx(1.0)
        assert stats.spearman(x, [-v for v in x]) == pytest.approx(-1.0)

    def test_spearman_matches_the_textbook_formula_without_ties(self):
        x = [1, 2, 3, 4, 5, 6]
        y = [2, 1, 4, 3, 6, 5]
        d2 = sum(
            (a - b) ** 2 for a, b in zip(stats.ranks(x), stats.ranks(y), strict=True)
        )
        n = len(x)
        assert stats.spearman(x, y) == pytest.approx(1 - 6 * d2 / (n * (n * n - 1)))

    def test_a_constant_series_has_no_correlation_not_a_zero_one(self):
        assert stats.pearson([1, 2, 3], [5, 5, 5]) is None
        assert stats.spearman([1, 2, 3], [5, 5, 5]) is None

    def test_integer_weights_are_frequencies(self):
        x, y, w = [1, 2, 3, 4], [2, 1, 5, 3], [1, 3, 2, 1]
        replicated_x = [v for v, k in zip(x, w, strict=True) for _ in range(k)]
        replicated_y = [v for v, k in zip(y, w, strict=True) for _ in range(k)]
        assert stats.pearson(x, y, w) == pytest.approx(
            stats.pearson(replicated_x, replicated_y)
        )

    def test_cosine(self):
        assert stats.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
        assert stats.cosine([1, 2], [2, 4]) == pytest.approx(1.0)
        assert stats.cosine([0, 0], [1, 1]) is None

    def test_percentile_interpolates(self):
        assert stats.percentile([0, 10], 0.25) == 2.5
        assert stats.percentile([1, 2, 3, 4, 5], 0.5) == 3


# ── the panel ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestThePanel:
    def test_one_snapshot_is_chosen_without_being_asked(self):
        corpus_repository("a/one", [{"vulns": 1, "cvss": 7.5}])
        loaded = panel.load_panel()
        assert loaded.snapshot_date == SNAPSHOT
        assert [repository.full_name for repository in loaded.repositories] == ["a/one"]
        assert len(loaded.repositories[0].occurrences) == 1

    def test_two_snapshots_must_be_told_which(self):
        """§11.28's split, or a second snapshot on purpose: either way one
        cross-section is one date, and pooling would count repositories twice."""
        corpus_repository("a/one", [{}], snapshot=date(2026, 9, 26))
        corpus_repository("a/one", [{}], snapshot=date(2026, 9, 27))
        with pytest.raises(panel.PanelError, match="more than one corpus snapshot"):
            panel.load_panel()
        assert panel.load_panel(date(2026, 9, 27)).snapshot_date == date(2026, 9, 27)

    def test_an_empty_database_says_where_the_rows_come_from(self):
        with pytest.raises(panel.PanelError, match="scan_corpus"):
            panel.load_panel()

    def test_a_date_with_no_rows_lists_the_dates_there_are(self):
        corpus_repository("a/one", [{}])
        with pytest.raises(panel.PanelError, match=SNAPSHOT.isoformat()):
            panel.load_panel(date(2020, 1, 1))

    def test_live_scan_rows_are_never_in_it(self):
        """File C §1.2: the two data sources never blend."""
        corpus_repository("a/corpus", [{}])
        corpus_repository("u/live", [{}], data_source=DataSource.LIVE_SCAN.value)
        assert [r.full_name for r in panel.load_panel().repositories] == ["a/corpus"]

    def test_a_polyglot_repository_is_its_own_group(self):
        corpus_repository("a/both", [{"ecosystem": "npm"}, {"ecosystem": "pypi"}])
        assert panel.load_panel().repositories[0].ecosystem == panel.MIXED

    def test_recomputing_under_the_stored_version_gives_back_the_stored_score(self):
        corpus_repository("a/one", [{"vulns": 2, "cvss": 9.8}, {"deprecated": True}])
        corpus_repository("a/two", [{"staleness": 2000}, {"unassessable": True}])
        loaded = panel.load_panel()

        scores = panel.score_panel(loaded, active_weights())
        assert [s.score for s in scores] == [r.stored_score for r in loaded.repositories]

        check = panel.reproduction_check(loaded, load_weights)
        assert check.all_match
        assert check.checked == 2

    def test_a_score_that_does_not_reproduce_is_named(self):
        entry = corpus_repository("a/one", [{"vulns": 2, "cvss": 9.8}])
        entry.risk_score = Decimal("99.99")
        entry.save(update_fields=["risk_score"])

        check = panel.reproduction_check(panel.load_panel(), load_weights)
        assert not check.all_match
        assert check.mismatches[0][0] == "a/one"

    def test_the_memo_changes_nothing(self):
        """The sweep's memo caches the engine's answer; it must not alter it."""
        rng = random.Random(7)
        occurrences = [
            {
                "ecosystem": rng.choice(["npm", "pypi"]),
                "deprecated": rng.random() < 0.1,
                "vulns": rng.choice([0, 0, 0, 1, 3]),
                "cvss": rng.choice([None, 5.3, 9.8]),
                "staleness": rng.choice([None, 10, 400, 900, 2000]),
            }
            for _ in range(60)
        ]
        corpus_repository("a/many", occurrences)
        loaded = panel.load_panel()
        weights = active_weights()

        expected = roll_up(
            [
                score_occurrence(o.signals, weights, o.ecosystem).penalty
                for o in loaded.repositories[0].occurrences
                if not o.is_unassessable
            ],
            weights,
        ).score
        assert panel.score_panel(loaded, weights)[0].score == expected


# ── entropy ────────────────────────────────────────────────────────────────


def sums(values: list[float]) -> entropy.ColumnSums:
    total = entropy.ColumnSums()
    for value in values:
        total = total + entropy.ColumnSums(
            count=1.0,
            total=value,
            xlogx=value * math.log(value) if value > 0 else 0.0,
            nonzero=int(value > 0),
        )
    return total


class TestTheEntropyFormula:
    def test_a_three_row_column_by_hand(self):
        """x = (1, 1, 2): p = (1/4, 1/4, 1/2), E = -(1/ln 3)·Σ p ln p."""
        p = [0.25, 0.25, 0.5]
        expected = -sum(v * math.log(v) for v in p) / math.log(3)
        assert entropy.column_entropy(sums([1, 1, 2])) == pytest.approx(expected)

    def test_an_even_column_has_entropy_one(self):
        assert entropy.column_entropy(sums([0.3, 0.3, 0.3, 0.3])) == pytest.approx(1.0)

    def test_a_column_concentrated_on_one_row_has_entropy_zero(self):
        assert entropy.column_entropy(sums([0, 0, 0, 1])) == pytest.approx(0.0)

    def test_an_all_zero_column_carries_no_information(self):
        assert entropy.column_entropy(sums([0, 0, 0])) == 1.0

    def test_one_row_is_undefined(self):
        assert entropy.column_entropy(sums([0.4])) is None


@pytest.mark.django_db
class TestEntropyOverTheCorpus:
    def corpus(self):
        # Deprecation rare (1 in 20), staleness spread evenly, no CVEs at all.
        for repo in range(4):
            occurrences = [
                {"staleness": 300 + 10 * index, "deprecated": repo == 0 and index == 0}
                for index in range(5)
            ]
            corpus_repository(f"org/r{repo}", occurrences)
        return panel.load_panel()

    def test_a_signal_that_never_varies_gets_no_weight(self):
        result = entropy.entropy_weights(self.corpus(), active_weights(), "npm")
        vector = result.vector()
        assert vector["count"] == 0.0
        assert vector["severity"] == 0.0
        assert sum(vector.values()) == pytest.approx(1.0)

    def test_a_rare_signal_outweighs_an_evenly_spread_one(self):
        vector = entropy.entropy_weights(self.corpus(), active_weights(), "npm").vector()
        assert vector["deprecation"] > vector["staleness"]

    def test_an_unmeasured_staleness_is_left_out_of_that_column_only(self):
        corpus_repository("org/x", [{"staleness": None}, {"staleness": 100}])
        result = entropy.entropy_weights(panel.load_panel(), active_weights(), "npm")
        rows = {column.signal: column.rows for column in result.columns}
        assert rows["staleness"] == 1
        assert rows["deprecation"] == 2

    def test_unassessable_rows_are_not_rows(self):
        corpus_repository("org/x", [{"staleness": 10}, {"unassessable": True}])
        result = entropy.entropy_weights(panel.load_panel(), active_weights(), "npm")
        assert {column.rows for column in result.columns} == {1}

    def test_ecosystems_are_separate(self):
        corpus_repository(
            "org/both",
            [
                {"ecosystem": "npm", "staleness": 10},
                {"ecosystem": "pypi", "staleness": 20},
            ],
        )
        loaded = panel.load_panel()
        npm = entropy.entropy_weights(loaded, active_weights(), "npm")
        pypi = entropy.entropy_weights(loaded, active_weights(), "pypi")
        assert npm.columns[0].rows == pypi.columns[0].rows == 1

    def test_sampling_weights_count_as_frequencies(self):
        """Weight 3 on a repository is that repository three times over."""
        corpus_repository(
            "org/heavy", [{"staleness": 100}, {"deprecated": True}], sampling_weight=3
        )
        corpus_repository("org/light", [{"staleness": 900}], sampling_weight=1)
        weighted = entropy.entropy_weights(
            panel.load_panel(), active_weights(), "npm", sampling_weighted=True
        )
        weighted_vector = weighted.vector()

        heavy, light = panel.load_panel().repositories  # ordered by name
        heavy.sampling_weight = light.sampling_weight = None
        replicated = panel.CorpusPanel(
            snapshot_date=SNAPSHOT, repositories=[heavy, heavy, heavy, light]
        )
        plain = entropy.entropy_weights(replicated, active_weights(), "npm").vector()

        for signal in plain:
            assert weighted_vector[signal] == pytest.approx(plain[signal])

    def test_the_bootstrap_is_seeded_and_brackets_the_estimate(self):
        loaded = self.corpus()
        first = entropy.entropy_weights(
            loaded, active_weights(), "npm", bootstrap=200, seed=11
        )
        second = entropy.entropy_weights(
            loaded, active_weights(), "npm", bootstrap=200, seed=11
        )
        assert first.intervals == second.intervals
        low, high = first.intervals["staleness"]
        assert low <= first.vector()["staleness"] <= high

    def test_the_vector_is_the_datas_not_the_files(self):
        """The weights file supplies caps only; two files with the same caps
        and different vectors give the same entropy vector."""
        loaded = self.corpus()
        v0 = entropy.entropy_weights(loaded, load_weights("v0_equal"), "npm").vector()
        v1 = entropy.entropy_weights(loaded, load_weights("v1"), "npm").vector()
        assert v0 == v1


class TestComparingVectors:
    def test_identical_vectors_agree_strongly(self):
        vector = {"deprecation": 0.4, "severity": 0.3, "count": 0.2, "staleness": 0.1}
        comparison = entropy.compare_vectors(
            vector, dict(vector), first_name="AHP", second_name="entropy"
        )
        assert comparison.cosine == pytest.approx(1.0)
        assert comparison.spearman == pytest.approx(1.0)
        assert comparison.top_two_identical
        assert comparison.band == "strong"

    def test_the_bands_are_file_cs(self):
        def band(cosine):
            return entropy.VectorComparison("a", "b", {}, {}, cosine, None).band

        assert band(0.95) == "strong"
        assert band(0.90) == "strong"
        assert band(0.80) == "partial"
        assert band(0.75) == "partial"
        assert band(0.74) == "tension"

    def test_the_largest_gap_names_the_signal(self):
        comparison = entropy.compare_vectors(
            {"deprecation": 0.4, "severity": 0.3, "count": 0.2, "staleness": 0.1},
            {"deprecation": 0.7, "severity": 0.1, "count": 0.1, "staleness": 0.1},
            first_name="AHP",
            second_name="entropy",
        )
        signal, gap = comparison.largest_gap
        assert signal == "deprecation"
        assert gap == pytest.approx(0.3)
        # Entropy's three-way tie at 0.1 resolves in D3's order, so severity is
        # second in both and the top two still agree.
        assert comparison.top_two_identical

    def test_rank_order_breaks_ties_canonically(self):
        assert entropy.rank_order(
            {"staleness": 0.25, "count": 0.25, "severity": 0.25, "deprecation": 0.25}
        ) == ("deprecation", "severity", "count", "staleness")


def test_signals_of_matches_the_scorer_input():
    """The helper the tests build rows with reads the same four fields."""
    signal = signals_of({"deprecated": True, "vulns": 2, "cvss": 7.5, "staleness": 9})
    assert signal.cvss_max == Decimal("7.5")
    assert signal.staleness_days == 9
