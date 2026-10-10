"""Agreement with the references (RQ2), the sensitivity sweep (RQ3), and the
candidate weight sets both are computed under.

The sweep's expected flip counts are not read off the code. Each test places a
repository at a score whose class the perturbation must — or must not — change,
works out the answer from §5.2-§5.3 by hand, and then asks the sweep.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.research.validation import agree, candidates, panel, sensitivity, stats
from apps.scoring.weights import active_weights, parse_weights
from tests.corpus_rows import corpus_repository

# ── stats added for this commit ────────────────────────────────────────────


class TestKappaAndFriends:
    def test_kappa_by_hand_two_by_two(self):
        """p_o = 35/50 = 0.7; p_e = (25·30 + 25·20)/50² = 0.5; κ = 0.4."""
        assert stats.cohen_kappa([[20, 5], [10, 15]]) == pytest.approx(0.4)

    def test_kappa_by_hand_three_by_three(self):
        matrix = [[10, 2, 0], [3, 8, 1], [0, 2, 4]]
        total = 30
        observed = 22 / total
        rows = [12, 12, 6]
        columns = [13, 12, 5]
        expected = sum(r * c for r, c in zip(rows, columns, strict=True)) / total**2
        assert stats.cohen_kappa(matrix) == pytest.approx(
            (observed - expected) / (1 - expected)
        )

    def test_perfect_agreement_is_one_and_total_chance_is_undefined(self):
        assert stats.cohen_kappa([[5, 0], [0, 5]]) == pytest.approx(1.0)
        assert stats.cohen_kappa([[9, 0], [0, 0]]) is None

    def test_confusion_counts_pairs(self):
        matrix = stats.confusion(["a", "a", "b"], ["a", "b", "b"], ["a", "b"])
        assert matrix == [[1, 1], [0, 1]]

    def test_buckets_include_their_upper_cut(self):
        assert [stats.bucket(v, [3, 6]) for v in (1, 3, 4, 6, 7)] == [0, 0, 1, 1, 2]

    def test_the_bootstrap_is_seeded_and_brackets_a_perfect_correlation(self):
        x = list(range(30))
        y = [v * 2 for v in x]

        def statistic(indices):
            return stats.spearman([x[i] for i in indices], [y[i] for i in indices])

        first = stats.bootstrap_interval(30, statistic, iterations=200, seed=3)
        assert first == stats.bootstrap_interval(30, statistic, iterations=200, seed=3)
        assert first == pytest.approx((1.0, 1.0))


# ── agreement ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAgreement:
    def corpus(self):
        # Five repositories from clean to dire; references in the same order.
        for index, cvss in enumerate([None, 3.0, 5.5, 7.5, 9.8]):
            occurrence = {"vulns": 0 if cvss is None else 2, "cvss": cvss}
            corpus_repository(f"org/r{index}", [occurrence])
        return panel.score_panel(panel.load_panel(), active_weights())

    def test_a_reference_that_orders_alike_correlates_perfectly(self):
        scores = self.corpus()
        reference = {
            result.repository.full_name: float(result.score) / 10 for result in scores
        }
        found = agree.agreement(
            scores, reference, vector="v1", reference="scorecard", bootstrap=50
        )
        assert found.correlation("spearman").value == pytest.approx(1.0)
        assert found.correlation("pearson").value == pytest.approx(1.0)
        assert found.correlation("spearman").interval == pytest.approx((1.0, 1.0))

    def test_repositories_without_a_reference_are_counted_not_zeroed(self):
        scores = self.corpus()
        reference = {
            result.repository.full_name: float(result.score) / 10 for result in scores
        }
        reference["org/r0"] = None
        found = agree.agreement(
            scores, reference, vector="v1", reference="scorecard", bootstrap=0
        )
        assert found.repositories == 5
        assert found.covered == 4
        assert found.correlation("spearman").n == 4

    def test_the_three_bucketings_are_all_reported(self):
        scores = self.corpus()
        reference = {
            result.repository.full_name: float(result.score) / 10 for result in scores
        }
        found = agree.agreement(
            scores, reference, vector="v1", reference="scorecard", bootstrap=0
        )
        assert [c.bucketing for c in found.confusions] == [
            agree.TERTILES,
            agree.MATCHED,
            agree.EQUAL_THIRDS,
        ]

    def test_matched_proportions_holds_the_marginals_equal(self):
        """Cut where the formula's own class shares fall, the reference's
        buckets have the same sizes as the formula's classes — so a perfect
        ordering agrees perfectly."""
        scores = self.corpus()
        reference = {
            result.repository.full_name: float(result.score) / 10 for result in scores
        }
        found = agree.agreement(
            scores, reference, vector="v1", reference="scorecard", bootstrap=0
        )
        matched = found.confusion(agree.MATCHED)
        rows = [sum(row) for row in matched.matrix]
        columns = [sum(matched.matrix[i][j] for i in range(3)) for j in range(3)]
        assert rows == columns
        assert matched.agreement == 1.0

    def test_too_few_covered_repositories_reports_nothing_rather_than_noise(self):
        scores = self.corpus()
        found = agree.agreement(
            scores, {"org/r1": 5.0}, vector="v1", reference="scorecard", bootstrap=0
        )
        assert found.covered == 1
        assert found.correlations == []

    def test_groups_are_all_then_each_ecosystem(self):
        corpus_repository("py/one", [{"ecosystem": "pypi", "vulns": 1, "cvss": 9.0}])
        corpus_repository("py/two", [{"ecosystem": "pypi"}])
        corpus_repository("mix/one", [{"ecosystem": "pypi"}, {"ecosystem": "npm"}])
        scores = panel.score_panel(panel.load_panel(), active_weights())
        reference = {r.repository.full_name: float(r.score) for r in scores}
        groups = agree.by_group(
            scores, reference, vector="v1", reference="osv", bootstrap=0, seed=1
        )
        assert [(g.group, g.repositories) for g in groups] == [("all", 3), ("pypi", 2)]


# ── sensitivity ────────────────────────────────────────────────────────────


class TestPerturbation:
    def test_a_perturbed_vector_still_sums_to_one_in_both_ecosystems(self):
        perturbed = sensitivity.perturb_weight(active_weights(), "deprecation", 20)
        for ecosystem in ("npm", "pypi"):
            assert sum(perturbed.weights[ecosystem].values()) == Decimal(1)

    def test_the_other_signals_keep_their_ratios(self):
        base = active_weights()
        perturbed = sensitivity.perturb_weight(base, "deprecation", -10)
        before = base.weights["npm"]["severity"] / base.weights["npm"]["count"]
        after = perturbed.weights["npm"]["severity"] / perturbed.weights["npm"]["count"]
        assert float(after) == pytest.approx(float(before), rel=1e-4)

    def test_the_perturbed_signal_moves_the_right_way(self):
        base = active_weights()
        up = sensitivity.perturb_weight(base, "staleness", 20)
        down = sensitivity.perturb_weight(base, "staleness", -20)
        assert up.weights["pypi"]["staleness"] > base.weights["pypi"]["staleness"]
        assert down.weights["pypi"]["staleness"] < base.weights["pypi"]["staleness"]

    def test_every_variant_file_a_names_is_swept(self):
        found = sensitivity.variants(active_weights())
        parameters = [variant.parameter for variant in found]
        assert parameters.count("weight:deprecation") == 4
        assert parameters.count("rollup.decay") == 4
        assert parameters.count("rollup.max_terms") == 4
        assert parameters.count("thresholds.safe_min") == 2
        assert parameters.count("thresholds.medium_min") == 2
        assert len(found) == 16 + 4 + 4 + 4


@pytest.mark.django_db
class TestFlipCounting:
    def test_a_repository_far_from_every_line_does_not_move(self):
        """One stale-only npm dependency at 1,095 days: S_stale = 1, penalty
        100 x 0.10 = 10, score 90. The largest staleness weight any variant
        produces is 0.12/1.02 = 0.118, so the score never falls below 88.2 —
        clear of a safe line moved to 85, and of everything else."""
        weights = active_weights()
        assert weights.weights["npm"]["staleness"] == Decimal("0.10")
        corpus_repository("org/ninety", [{"staleness": 1095}])
        loaded = panel.load_panel()
        assert panel.score_panel(loaded, weights)[0].score == Decimal("90.00")

        rows = sensitivity.sweep(loaded, weights, vector="v1")
        assert rows
        assert all(row.flips == 0 for row in rows)

    def test_flips_are_counted_against_the_same_vector_unperturbed(self):
        """A repository at 80.40 is Safe; safe_min +5 makes it Medium — one flip
        of three, and only that row moves it."""
        weights = active_weights()
        # count=1 of 10 (0.16·0.1·100 = 1.6) + severity 0.28·0.65·100 = 18.2,
        # staleness 0 -> penalty 19.80 -> score 80.20.
        corpus_repository("org/edge", [{"vulns": 1, "cvss": 6.5, "staleness": 0}])
        corpus_repository("org/clean", [{"staleness": 0}])
        corpus_repository("org/dire", [{"deprecated": True, "staleness": 1095}])
        loaded = panel.load_panel()
        scores = {s.repository.full_name: s for s in panel.score_panel(loaded, weights)}
        assert scores["org/edge"].score == Decimal("80.20")
        assert scores["org/edge"].classification == "safe"

        rows = {
            (row.parameter, row.change): row
            for row in sensitivity.sweep(loaded, weights, vector="v1")
        }
        moved = rows[("thresholds.safe_min", "+5 (85)")]
        assert moved.flips == 1
        assert moved.rate == pytest.approx(1 / 3)
        assert rows[("thresholds.safe_min", "-5 (75)")].flips == 0
        assert rows[("thresholds.medium_min", "+5 (55)")].flips == 0

    def test_reusing_penalties_equals_rescoring_from_scratch(self):
        weights = active_weights()
        corpus_repository(
            "org/a",
            [{"vulns": 3, "cvss": 9.8}, {"deprecated": True}, {"staleness": 800}],
        )
        corpus_repository("org/b", [{"vulns": 1, "cvss": 5.0}, {"staleness": 2000}])
        loaded = panel.load_panel()
        for variant in sensitivity.variants(weights):
            if not variant.reuses_penalties:
                continue
            shortcut = panel.roll_up_panel(
                loaded, panel.occurrence_penalties(loaded, weights), variant.weights
            )
            full = panel.score_panel(loaded, variant.weights)
            assert [s.score for s in shortcut] == [s.score for s in full]

    def test_the_summary_applies_file_cs_lines(self):
        flips = [
            sensitivity.FlipCount("v", "weight:severity", "+20%", 20, 3, 10, {}),
            sensitivity.FlipCount("v", "weight:severity", "+10%", 10, 1, 10, {}),
            sensitivity.FlipCount("v", "rollup.decay", "+20% (0.6)", 20, 1, 10, {}),
        ]
        summary = sensitivity.summarise(flips)
        assert summary.max_weight_rate_20 == pytest.approx(0.3)
        assert summary.max_weight_rate_10 == pytest.approx(0.1)
        assert not summary.robust
        assert summary.to_discuss == ("weight:severity +20%",)


# ── candidate weight sets ──────────────────────────────────────────────────


class TestCandidates:
    def test_rounding_sums_to_exactly_one(self):
        rounded = candidates.round_vector(
            {
                "deprecation": 0.40287,
                "severity": 0.33693,
                "count": 0.15235,
                "staleness": 0.10785,
            }
        )
        assert sum(rounded.values()) == Decimal(1)
        assert rounded["deprecation"] == Decimal("0.4029")

    def test_rounding_hands_the_last_unit_to_the_largest_remainder(self):
        rounded = candidates.round_vector(
            {"deprecation": 1 / 3, "severity": 1 / 3, "count": 1 / 3, "staleness": 0.0}
        )
        assert sum(rounded.values()) == Decimal(1)
        assert sorted(rounded.values())[-1] == Decimal("0.3334")

    def test_a_shift_must_move_weight_not_create_it(self):
        assert candidates.parse_shift(
            "deprecation=-0.14,severity=+0.07,staleness=+0.07"
        ) == {
            "deprecation": -0.14,
            "severity": 0.07,
            "staleness": 0.07,
        }
        with pytest.raises(candidates.CandidateError, match="sums to"):
            candidates.parse_shift("deprecation=-0.14,severity=+0.07")
        with pytest.raises(candidates.CandidateError, match="names 'epss'"):
            candidates.parse_shift("epss=0.1,count=-0.1")

    def test_a_shift_cannot_go_below_zero(self):
        with pytest.raises(candidates.CandidateError, match="below zero"):
            candidates.apply_shift(
                {"deprecation": 0.1, "severity": 0.5, "count": 0.2, "staleness": 0.2},
                {"deprecation": -0.2, "severity": 0.2},
            )

    def test_only_the_vectors_change(self):
        base = active_weights()
        vector = {"deprecation": 0.4, "severity": 0.3, "count": 0.2, "staleness": 0.1}
        built = candidates.weightset_from(
            base, {"npm": vector, "pypi": vector}, version="v2", derivation="ahp"
        )
        assert built.rollup == base.rollup
        assert built.thresholds == base.thresholds
        assert built.normalization == base.normalization
        assert built.weights["npm"]["deprecation"] == Decimal("0.4000")

    def test_the_rendered_file_is_one_the_loader_accepts(self, tmp_path):
        base = active_weights()
        vector = {
            "deprecation": 0.4029,
            "severity": 0.3369,
            "count": 0.1524,
            "staleness": 0.1078,
        }
        built = candidates.weightset_from(
            base, {"npm": vector, "pypi": vector}, version="v2", derivation="ahp"
        )
        text = candidates.render_weights_file(built, ["candidate", "", "pending WP-6"])
        import yaml

        reread = parse_weights(yaml.safe_load(text), tmp_path / "weights_v2.yaml", "v2")
        assert reread.weights == built.weights
        assert text.startswith("# candidate\n#\n# pending WP-6\n")
