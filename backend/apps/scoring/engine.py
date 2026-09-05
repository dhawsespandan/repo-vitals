"""Occurrence scoring, the flag rule, the roll-up, and the classifier.

    occurrence_score = 100 - 100 · Σ wᵢ·Sᵢ                         (§5.2)
    repo_score       = 100 - Σ_{k≥0} penalties[k] · decayᵏ         (§5.3)

Pure functions over a `Signals` record and a `WeightSet`: no database, no
settings lookup, no clock. §10 Phase 4 requires that, and it is what lets the
golden fixtures assert exact numbers rather than approximate ones.

**Rounding is part of the specification here, not an afterthought.** Every
term is quantized to two decimals before it is summed, and the occurrence
penalties fed into the roll-up are the two-decimal values that were *stored*.
The alternative — full precision internally, rounding only for display — makes
the on-screen breakdown fail to add up by a hundredth or two, and this
product's entire claim is "here is the arithmetic". So the arithmetic a reader
can do by hand from the dependency table is the arithmetic that produced the
number. It also makes D6 exact rather than approximate: research recomputing a
repository score from stored `dependency_history` rows gets the same value the
product showed, bit for bit.

**The roll-up's properties are load-bearing and worth restating** (§5.3 asks
for them verbatim in any write-up): the worst occurrence is undecayed, so it
dominates; each further bad occurrence adds a real but geometrically
diminishing penalty, so breadth counts without mean-dilution; clean rows
contribute exactly zero rather than diluting a denominator, so 500 healthy
dependencies cannot mask three critical ones; the sum Σ decayᵏ converges to
1/(1-decay), which bounds the maximum deduction at 2x the worst penalty for
the default decay of 0.5; and it is monotone — a newly-bad dependency can
never raise a score.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.scanning.models import Classification

from .normalize import Normalized, Signals, normalize, redistribute
from .weights import WeightSet

ZERO = Decimal(0)
HUNDRED = Decimal(100)
CENTS = Decimal("0.01")


def q2(value: Decimal) -> Decimal:
    """Two decimals, half-up — the precision of every score column in §5.1."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return low if value < low else high if value > high else value


@dataclass(frozen=True)
class TermContribution:
    """One signal's share of one occurrence's penalty.

    `weight` is the *effective* weight — after §5.2's redistribution, which is
    why it can differ from the weights file. Phase 5's breakdown panel renders
    these four fields directly, and `points` is what the bar's length and the
    number beside it both come from.
    """

    signal: str
    normalized: Decimal
    weight: Decimal
    points: Decimal


@dataclass(frozen=True)
class OccurrenceScore:
    score: Decimal
    penalty: Decimal
    terms: tuple[TermContribution, ...]
    cvss_reduced_confidence: bool
    #: True when a signal was unmeasured and its weight was redistributed.
    redistributed: bool


def score_occurrence(
    signals: Signals, weights: WeightSet, ecosystem: str
) -> OccurrenceScore:
    """§5.2 for one assessable occurrence, under one ecosystem's vector."""
    normalized: Normalized = normalize(
        signals,
        cve_count_cap=weights.normalization.cve_count_cap,
        staleness_cap_days=weights.normalization.staleness_cap_days,
        include_epss=weights.epss_enabled,
    )
    declared = weights.for_ecosystem(ecosystem)
    present = frozenset(normalized.terms)
    effective = redistribute(declared, present)

    terms: list[TermContribution] = []
    penalty = ZERO
    # Iterated in the canonical signal order rather than the dict's, so the
    # breakdown panel lists signals the same way every time, for every
    # repository — which is what makes two of them comparable at a glance.
    for signal in weights.signal_order:
        if signal not in effective:
            continue
        value = normalized.terms[signal]
        weight = effective[signal]
        points = q2(weight * value * HUNDRED)
        penalty += points
        terms.append(
            TermContribution(
                signal=signal, normalized=value, weight=weight, points=points
            )
        )

    # Quantized after the clamp, not before: the clamp's own bounds carry no
    # decimals, so a fully-saturated penalty would otherwise come back as
    # `Decimal("100")` where every other row says `100.00`. Numerically
    # identical, and different in every artifact that renders it as text —
    # `rescore`'s CSV panel among them.
    penalty = q2(_clamp(penalty, ZERO, HUNDRED))
    return OccurrenceScore(
        score=q2(HUNDRED - penalty),
        penalty=penalty,
        terms=tuple(terms),
        cvss_reduced_confidence=normalized.cvss_reduced_confidence,
        redistributed=len(effective) < len(declared),
    )


#: The three clauses of §5.2's flag rule, as the names the UI renders. They are
#: codes rather than sentences for the same reason §5.6's outcomes are: the
#: frontend branches on a code and phrases it, and a reworded sentence must not
#: be able to change what the backend asserted.
FLAG_DEPRECATED = "deprecated"
FLAG_VULNERABLE = "vulnerable"
FLAG_STALE = "stale"


def flag_reasons(signals: Signals, weights: WeightSet) -> tuple[str, ...]:
    """Which clauses of §5.2's flag rule fired, in the order the rule states.

    The rule is a disjunction, so `is_flagged` only ever answers *that* a row
    needs a human. Phase 5's panel has to answer *why*, and re-deriving the
    three clauses in the serializer -- or worse, in TypeScript from the row's
    other fields -- would be a second copy of the rule, free to disagree with
    the boolean beside it the day `stale_flag_days` moves. So the disjunction
    is evaluated once, here, and `is_flagged` is its emptiness test.
    """
    reasons: list[str] = []
    if signals.is_deprecated:
        reasons.append(FLAG_DEPRECATED)
    if signals.vulnerability_count > 0:
        reasons.append(FLAG_VULNERABLE)
    days = signals.staleness_days
    if days is not None and days >= weights.stale_flag_days:
        reasons.append(FLAG_STALE)
    return tuple(reasons)


def is_flagged(signals: Signals, weights: WeightSet) -> bool:
    """§5.2's flag rule — fixed, and deliberately independent of the score.

    A flag answers "does this need a human?", which is not the same question as
    "how much did this cost the repository". Tying flags to a score threshold
    would make them move every time the weights change, and a deprecated
    package with no CVEs would drop off the list the moment deprecation was
    reweighted — while still being deprecated. So the rule is a disjunction
    over the raw signals and nothing else.
    """
    return bool(flag_reasons(signals, weights))


@dataclass(frozen=True)
class Contribution:
    """One occurrence's decayed share of a repository's deduction."""

    rank: int
    penalty: Decimal
    #: `penalty · decayᵏ` — the points this occurrence actually cost.
    points: Decimal


@dataclass(frozen=True)
class RepositoryScore:
    score: Decimal
    deduction: Decimal
    contributions: tuple[Contribution, ...]
    #: How many assessable occurrences the roll-up saw, before `max_terms`.
    assessed_count: int


def roll_up(penalties: list[Decimal], weights: WeightSet) -> RepositoryScore:
    """§5.3's rank-decayed penalty aggregation over one scan's occurrences.

    `penalties` must already be the stored two-decimal values; the caller sorts
    nothing, because sorting is part of the definition and belongs here.
    """
    ordered = sorted(penalties, reverse=True)[: weights.rollup.max_terms]

    contributions: list[Contribution] = []
    deduction = ZERO
    factor = Decimal(1)
    for rank, penalty in enumerate(ordered):
        points = q2(penalty * factor)
        deduction += points
        contributions.append(Contribution(rank=rank, penalty=penalty, points=points))
        factor *= weights.rollup.decay

    score = q2(_clamp(HUNDRED - deduction, ZERO, HUNDRED))
    return RepositoryScore(
        score=score,
        deduction=q2(deduction),
        contributions=tuple(contributions),
        assessed_count=len(penalties),
    )


def classify(score: Decimal, weights: WeightSet) -> str:
    """`≥80 Safe · 50-79 Medium · <50 High-Alert` (§5.3), thresholds from the file."""
    if score >= weights.thresholds.safe_min:
        return Classification.SAFE.value
    if score >= weights.thresholds.medium_min:
        return Classification.MEDIUM.value
    return Classification.HIGH_ALERT.value
