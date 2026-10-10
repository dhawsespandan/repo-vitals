"""The formula, checked against arithmetic done by hand (§10 Phase 4).

Every expected number in this file was computed on paper from the shipped
`weights_v1.yaml` vector before the code was run, and the working is written
into each test. That is the point of a golden fixture: a test that asserts
whatever the implementation happens to produce cannot tell you the
implementation is wrong, and the score is the one output of this product that
nobody can eyeball for plausibility.

The npm vector under test is WP-1's:

    deprecation 0.46 · severity 0.28 · count 0.16 · staleness 0.10
    caps: cve_count 10, staleness 1095 days
    rollup: decay 0.5, max_terms 20 · thresholds: safe 80, medium 50

Beside the golden cases sit the four *properties* §10 Phase 4 names, which are
what a future weights version has to keep true even when every number here
changes: monotonicity, no mean-dilution, the classification boundaries, and
exact reproducibility.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.scoring.engine import classify, is_flagged, roll_up, score_occurrence
from apps.scoring.normalize import (
    COUNT,
    DEPRECATION,
    SEVERITY,
    STALENESS,
    Signals,
    normalize,
    redistribute,
)
from apps.scoring.weights import load_weights

NPM = "npm"
PYPI = "pypi"


@pytest.fixture(scope="module")
def v1():
    return load_weights("v1")


@pytest.fixture(scope="module")
def v0():
    return load_weights("v0_equal")


def score(signals: Signals, weights, ecosystem: str = NPM) -> Decimal:
    return score_occurrence(signals, weights, ecosystem).score


class TestGoldenOccurrenceScores:
    """Hand-computed §5.2 arithmetic, one case per shape the signal set takes."""

    def test_clean_package_scores_100(self, v1):
        # Nothing deprecated, no advisories, released today:
        #   0.46*0 + 0.28*0 + 0.16*0 + 0.10*0 = 0  ->  100 - 0
        assert score(Signals(staleness_days=0), v1) == Decimal("100.00")

    def test_deprecated_and_fully_stale(self, v1):
        #   deprecation 0.46 * 1.0            * 100 = 46.00
        #   severity    0.28 * 0.0            * 100 =  0.00
        #   count       0.16 * 0.0            * 100 =  0.00
        #   staleness   0.10 * 1.0 (capped)   * 100 = 10.00
        #                                    penalty = 56.00
        result = score_occurrence(
            Signals(is_deprecated=True, staleness_days=4000), v1, NPM
        )
        assert result.penalty == Decimal("56.00")
        assert result.score == Decimal("44.00")

    def test_two_critical_cves_on_a_recent_release(self, v1):
        #   deprecation 0.46 * 0.0                 * 100 =  0.00
        #   severity    0.28 * 0.98  (9.8/10)      * 100 = 27.44
        #   count       0.16 * 0.2   (2/10)        * 100 =  3.20
        #   staleness   0.10 * 0.0913 (100/1095)   * 100 =  0.91
        #                                        penalty = 31.55
        result = score_occurrence(
            Signals(vulnerability_count=2, cvss_max=Decimal("9.8"), staleness_days=100),
            v1,
            NPM,
        )
        assert result.penalty == Decimal("31.55")
        assert result.score == Decimal("68.45")
        assert not result.cvss_reduced_confidence

    def test_advisory_with_no_cvss_uses_the_5_0_placeholder(self, v1):
        #   severity 0.28 * 0.5 (5.0/10) * 100 = 14.00
        #   count    0.16 * 0.1 (1/10)   * 100 =  1.60
        #                              penalty = 15.60
        result = score_occurrence(
            Signals(vulnerability_count=1, cvss_max=None, staleness_days=0), v1, NPM
        )
        assert result.penalty == Decimal("15.60")
        assert result.score == Decimal("84.40")
        # The number exists; the fact that part of it was assumed travels with it.
        assert result.cvss_reduced_confidence

    def test_unknown_staleness_redistributes_its_weight(self, v1):
        # Staleness is unmeasured, so 0.10 is redistributed across the three
        # signals that were measured (they sum to 0.90):
        #   deprecation 0.46/0.90 = 0.51111... -> 51.11 points at value 1.0
        #   severity    0.28/0.90, count 0.16/0.90, both at value 0.0
        result = score_occurrence(
            Signals(is_deprecated=True, staleness_days=None), v1, NPM
        )
        assert result.redistributed
        assert result.penalty == Decimal("51.11")
        assert result.score == Decimal("48.89")
        assert [term.signal for term in result.terms] == [DEPRECATION, SEVERITY, COUNT]

    def test_the_pypi_vector_scores_the_same_signals_differently(self, v1):
        # WP-1's PyPI vector deliberately inverts npm's top two signals
        # (severity 0.35 > deprecation 0.32), so one deprecated package costs
        # a Python project less than the same package costs a Node one.
        signals = Signals(is_deprecated=True, staleness_days=0)
        assert score(signals, v1, NPM) == Decimal("54.00")  # 100 - 46
        assert score(signals, v1, PYPI) == Decimal("68.00")  # 100 - 32

    def test_caps_saturate(self, v1):
        # 40 CVEs and 10 CVEs are the same measurement once the cap bites, and
        # so are 4000 and 1095 days.
        ten = Signals(
            vulnerability_count=10, cvss_max=Decimal("5.0"), staleness_days=1095
        )
        forty = Signals(
            vulnerability_count=40, cvss_max=Decimal("5.0"), staleness_days=4000
        )
        assert score(ten, v1) == score(forty, v1)

    def test_the_worst_possible_occurrence_scores_zero(self, v1):
        result = score_occurrence(
            Signals(
                is_deprecated=True,
                vulnerability_count=10,
                cvss_max=Decimal("10.0"),
                staleness_days=1095,
            ),
            v1,
            NPM,
        )
        assert result.penalty == Decimal("100.00")
        assert result.score == Decimal("0.00")

    def test_the_breakdown_adds_up_to_the_penalty(self, v1):
        """The arithmetic a reader can do by hand is the arithmetic used.

        Phase 5 renders these four terms; if they did not sum to the penalty on
        the badge, the page would be showing its own working and getting a
        different answer.
        """
        result = score_occurrence(
            Signals(
                is_deprecated=True,
                vulnerability_count=3,
                cvss_max=Decimal("7.5"),
                staleness_days=800,
            ),
            v1,
            NPM,
        )
        assert sum(term.points for term in result.terms) == result.penalty
        assert result.score + result.penalty == Decimal("100.00")


class TestFlagRule:
    """`is_deprecated OR vulnerability_count > 0 OR staleness_days >= 730`."""

    def test_clean_recent_package_is_not_flagged(self, v1):
        assert not is_flagged(Signals(staleness_days=10), v1)

    def test_each_disjunct_flags_on_its_own(self, v1):
        assert is_flagged(Signals(is_deprecated=True, staleness_days=0), v1)
        assert is_flagged(Signals(vulnerability_count=1, staleness_days=0), v1)
        assert is_flagged(Signals(staleness_days=730), v1)

    def test_the_staleness_threshold_is_inclusive(self, v1):
        assert not is_flagged(Signals(staleness_days=729), v1)
        assert is_flagged(Signals(staleness_days=730), v1)

    def test_unknown_staleness_does_not_flag(self, v1):
        # Not knowing how stale something is is not evidence that it is stale.
        assert not is_flagged(Signals(staleness_days=None), v1)

    def test_flagging_is_independent_of_the_weights(self, v1, v0):
        # The rule is fixed (§5.2). Reweighting changes what a finding costs,
        # never whether it is a finding.
        signals = Signals(is_deprecated=True, staleness_days=0)
        assert is_flagged(signals, v1) == is_flagged(signals, v0)


class TestRollUp:
    def test_golden_three_occurrence_rollup(self, v1):
        #   rank 0: 56.00 * 1.00  = 56.00
        #   rank 1: 31.55 * 0.50  = 15.775 -> 15.78
        #   rank 2: 15.60 * 0.25  =  3.90
        #                deduction = 75.68  ->  100 - 75.68
        result = roll_up([Decimal("31.55"), Decimal("15.60"), Decimal("56.00")], v1)
        assert [c.points for c in result.contributions] == [
            Decimal("56.00"),
            Decimal("15.78"),
            Decimal("3.90"),
        ]
        assert result.deduction == Decimal("75.68")
        assert result.score == Decimal("24.32")

    def test_the_worst_occurrence_is_undecayed(self, v1):
        assert roll_up([Decimal("40.00")], v1).score == Decimal("60.00")

    def test_every_score_carries_two_decimals(self, v1):
        """`Decimal("100") == Decimal("100.00")`, and they are not the same text.

        Both are written to `NUMERIC(5,2)` columns, which normalizes them — so
        the difference is invisible in the database and visible in every
        artifact rendered straight from the engine, `rescore`'s CSV panel
        included. An equality assertion cannot see it; this one can.
        """
        assert str(roll_up([], v1).score) == "100.00"
        assert str(roll_up([Decimal("100.00")] * 5, v1).score) == "0.00"
        assert str(score_occurrence(Signals(staleness_days=0), v1, NPM).score) == "100.00"

    def test_a_repository_with_nothing_assessable_scores_100(self, v1):
        # §5.2 excludes unassessable occurrences from every denominator, so a
        # repository with no assessable dependency has no penalty to carry. The
        # UI states the assessable count beside the number so the 100 is never
        # read as "we checked everything".
        assert roll_up([], v1).score == Decimal("100.00")
        assert roll_up([], v1).assessed_count == 0

    def test_the_deduction_is_bounded_at_twice_the_worst(self, v1):
        # Sum of 0.5^k converges to 2, so 20 maximally-bad occurrences cannot
        # deduct more than 2x the worst one — and the clamp holds the floor.
        result = roll_up([Decimal("100.00")] * 40, v1)
        assert result.deduction <= Decimal("200.00")
        assert result.score == Decimal("0.00")

    def test_only_max_terms_occurrences_contribute(self, v1):
        assert len(roll_up([Decimal("10.00")] * 50, v1).contributions) == 20

    def test_duplicate_occurrences_count_independently(self, v1):
        """The same package in three manifests is three penalties (§5.3).

        A monorepo that installs one vulnerable package three times has three
        installations to remediate, and collapsing them would understate it.
        """
        one = roll_up([Decimal("40.00")], v1).score
        three = roll_up([Decimal("40.00")] * 3, v1).score
        assert three < one


class TestProperties:
    """The four §10 Phase 4 acceptance properties, stated as tests."""

    def test_adding_a_cve_never_raises_a_score(self, v1):
        previous = Decimal("101")
        for count in range(0, 15):
            current = score(
                Signals(
                    vulnerability_count=count,
                    cvss_max=Decimal("7.0") if count else None,
                    staleness_days=0,
                ),
                v1,
            )
            assert current <= previous
            previous = current

    @pytest.mark.parametrize("field", ["staleness_days", "cvss_max"])
    def test_every_signal_is_monotone(self, v1, field):
        previous = Decimal("101")
        steps = range(0, 1200, 50) if field == "staleness_days" else range(0, 11)
        for step in steps:
            value = step if field == "staleness_days" else Decimal(step)
            signals = Signals(
                vulnerability_count=0 if field == "staleness_days" else 1,
                staleness_days=step if field == "staleness_days" else 0,
                cvss_max=None if field == "staleness_days" else value,
            )
            current = score(signals, v1)
            assert current <= previous
            previous = current

    def test_deprecation_never_raises_a_score(self, v1):
        clean = Signals(staleness_days=0)
        deprecated = Signals(is_deprecated=True, staleness_days=0)
        assert score(deprecated, v1) < score(clean, v1)

    def test_two_hundred_clean_dependencies_cannot_mask_three_critical_ones(self, v1):
        """§10 Phase 4: the addition must move the score by under one point.

        It moves it by exactly zero. Clean occurrences carry a penalty of 0 and
        contribute 0 at every rank — there is no denominator for them to
        dilute, which is the whole reason §5.3 aggregates penalties rather than
        averaging scores.
        """
        critical = [Decimal("100.00")] * 3
        before = roll_up(critical, v1).score
        after = roll_up(critical + [Decimal("0.00")] * 200, v1).score
        assert abs(after - before) < Decimal("1")
        assert after == before

    def test_scoring_is_reproducible(self, v1):
        """Rescanning an unchanged repository produces an identical score."""
        signals = Signals(
            is_deprecated=True,
            vulnerability_count=4,
            cvss_max=Decimal("6.3"),
            staleness_days=921,
        )
        first = score_occurrence(signals, v1, NPM)
        second = score_occurrence(signals, v1, NPM)
        assert first == second
        assert roll_up([first.penalty], v1) == roll_up([second.penalty], v1)


class TestClassificationBoundaries:
    """`>=80 Safe · 50-79 Medium · <50 High-Alert` — checked on the edges."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("100.00", "safe"),
            ("80.00", "safe"),
            ("79.99", "medium"),
            ("50.00", "medium"),
            ("49.99", "high_alert"),
            ("0.00", "high_alert"),
        ],
    )
    def test_boundaries(self, v1, value, expected):
        assert classify(Decimal(value), v1) == expected

    def test_an_anchor_repository_classifies_medium_or_worse(self, v1):
        """§10 Phase 4's anchor sanity check.

        A repository pinning an old `request` — deprecated in 2020, no release
        since — must not come out Safe. One deprecated, fully stale occurrence
        costs 56 points undecayed, so the repository lands at 44: High-Alert,
        comfortably the wrong side of the Safe line even before its other
        dependencies are considered.
        """
        request = score_occurrence(
            Signals(is_deprecated=True, staleness_days=2000), v1, NPM
        )
        repository = roll_up([request.penalty, Decimal("0.00")], v1)
        assert classify(repository.score, v1) in ("medium", "high_alert")


class TestNormalizationUnits:
    def test_zero_cves_is_an_informative_zero_not_a_missing_value(self):
        result = normalize(
            Signals(vulnerability_count=0, staleness_days=0),
            cve_count_cap=10,
            staleness_cap_days=1095,
        )
        assert result.terms[SEVERITY] == 0
        assert result.terms[COUNT] == 0
        assert not result.cvss_reduced_confidence

    def test_unknown_staleness_is_absent_rather_than_zero(self):
        result = normalize(
            Signals(staleness_days=None), cve_count_cap=10, staleness_cap_days=1095
        )
        assert STALENESS not in result.terms

    def test_redistribute_preserves_the_relative_ranking(self):
        weights = {
            DEPRECATION: Decimal("0.46"),
            SEVERITY: Decimal("0.28"),
            COUNT: Decimal("0.16"),
            STALENESS: Decimal("0.10"),
        }
        rescaled = redistribute(weights, {DEPRECATION, SEVERITY, COUNT})
        assert sum(rescaled.values()) == Decimal(1)
        # 0.46/0.28 before, and after.
        assert (
            rescaled[DEPRECATION] / rescaled[SEVERITY]
            == weights[DEPRECATION] / weights[SEVERITY]
        )

    def test_redistribute_returns_the_file_values_when_nothing_is_missing(self):
        weights = {DEPRECATION: Decimal("0.5"), SEVERITY: Decimal("0.5")}
        assert redistribute(weights, {DEPRECATION, SEVERITY}) == weights

    def test_negative_and_oversized_inputs_are_clamped(self):
        result = normalize(
            Signals(vulnerability_count=-3, cvss_max=Decimal("99.9"), staleness_days=-10),
            cve_count_cap=10,
            staleness_cap_days=1095,
        )
        assert result.terms[COUNT] == 0
        assert result.terms[SEVERITY] == 1
        assert result.terms[STALENESS] == 0
