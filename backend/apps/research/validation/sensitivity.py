"""How many classifications move when one parameter does (RQ3).

§10 Phase 12: "±10-20% per-weight perturbation (renormalized), **both**
vectors, plus `rollup.decay`, `max_terms`, and thresholds ±5 -> bucket-flip
counts/rates." File C H3: fewer than 15% of repositories change class under
±20%, under both vectors; any single parameter driving more than 20% gets a
paragraph of its own. The 2026-09-24 review adds that WP-6's sign-off must
cover ±10% *and* ±20% for *both* vectors, so both are always swept.

**One parameter at a time.** A perturbation changes exactly one thing and
leaves the rest of the base file alone, so a flip is attributable to the
parameter in its row. Varying several at once answers a different question
(how robust is the whole calibration) that no hypothesis in File C asks.

**A weight perturbation is renormalised.** Raising deprecation by 20% and
leaving the others where they were would make the weights sum past 1 and
inflate every penalty — a change to the *scale* of the formula, not to the
relative importance of one signal. So the perturbed weight is scaled, then all
four are rescaled to sum to 1: the other three keep their ratios to each other
and give up their share proportionally. Both ecosystems' vectors take the same
relative change to the same signal, because the question is about the signal,
not about one ecosystem's vector.

**A flip is a change of class against the same vector unperturbed.** Not
against `v1`, and not against the stored classification: the sweep measures
the formula's sensitivity to its own parameters, so each vector is its own
baseline.

**Where the arithmetic allows, the roll-up is re-run without re-scoring.**
`decay`, `max_terms` and the thresholds do not touch a single occurrence's
penalty, so those variants re-roll the baseline's stored penalties. The weight
variants re-score, through the shipped engine (`panel.occurrence_penalties`).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from decimal import Decimal

from apps.scoring.normalize import SIGNAL_NAMES
from apps.scoring.weights import REQUIRED_ECOSYSTEMS, Rollup, Thresholds, WeightSet

from .panel import CorpusPanel, occurrence_penalties, roll_up_panel

#: §10 Phase 12's ±10-20%, at both ends.
PERCENTS: tuple[int, ...] = (-20, -10, 10, 20)
#: §10 Phase 12's "thresholds ±5", in score points.
THRESHOLD_SHIFTS: tuple[int, ...] = (-5, 5)

#: File C H3, and its "gets a dedicated discussion paragraph" line.
ROBUST_RATE = 0.15
DISCUSS_RATE = 0.20

SIX_PLACES = Decimal("0.000001")


@dataclass(frozen=True)
class Variant:
    parameter: str
    change: str
    weights: WeightSet
    #: True when only the roll-up or the thresholds changed, so the baseline's
    #: occurrence penalties still hold.
    reuses_penalties: bool
    #: The size of the change as a magnitude, for "under ±20%" summaries:
    #: 10 or 20 for a percentage, 5 for a threshold shift.
    magnitude: int


def _renormalised(vector: dict[str, Decimal]) -> dict[str, Decimal]:
    total = sum(vector.values(), Decimal(0))
    scaled = {
        signal: (value / total).quantize(SIX_PLACES) for signal, value in vector.items()
    }
    # Six decimals can leave the sum a millionth off; give the residue to the
    # largest weight, where it is the smallest relative change.
    residue = Decimal(1) - sum(scaled.values(), Decimal(0))
    if residue:
        largest = max(scaled, key=lambda signal: (scaled[signal], signal))
        scaled[largest] += residue
    return scaled


def perturb_weight(base: WeightSet, signal: str, percent: int) -> WeightSet:
    """`signal` scaled by `1 + percent/100` in every ecosystem, then renormalised."""
    factor = Decimal(100 + percent) / Decimal(100)
    weights = {}
    for ecosystem in REQUIRED_ECOSYSTEMS:
        vector = dict(base.weights[ecosystem])
        vector[signal] = vector[signal] * factor
        weights[ecosystem] = _renormalised(vector)
    return dataclasses.replace(
        base, weights=weights, version=f"{base.version}~{signal}{percent:+d}%"
    )


def variants(base: WeightSet) -> list[Variant]:
    """Every single-parameter change §10 Phase 12 names, in report order."""
    found: list[Variant] = []
    for signal in SIGNAL_NAMES:
        for percent in PERCENTS:
            found.append(
                Variant(
                    parameter=f"weight:{signal}",
                    change=f"{percent:+d}%",
                    weights=perturb_weight(base, signal, percent),
                    reuses_penalties=False,
                    magnitude=abs(percent),
                )
            )
    for percent in PERCENTS:
        decay = base.rollup.decay * Decimal(100 + percent) / Decimal(100)
        if not (Decimal(0) < decay <= Decimal(1)):
            continue
        found.append(
            Variant(
                parameter="rollup.decay",
                change=f"{percent:+d}% ({decay.normalize()})",
                weights=dataclasses.replace(
                    base,
                    rollup=Rollup(decay=decay, max_terms=base.rollup.max_terms),
                    version=f"{base.version}~decay{percent:+d}%",
                ),
                reuses_penalties=True,
                magnitude=abs(percent),
            )
        )
    for percent in PERCENTS:
        terms = max(1, round(base.rollup.max_terms * (100 + percent) / 100))
        if terms == base.rollup.max_terms:
            continue
        found.append(
            Variant(
                parameter="rollup.max_terms",
                change=f"{percent:+d}% ({terms})",
                weights=dataclasses.replace(
                    base,
                    rollup=Rollup(decay=base.rollup.decay, max_terms=terms),
                    version=f"{base.version}~terms{percent:+d}%",
                ),
                reuses_penalties=True,
                magnitude=abs(percent),
            )
        )
    for name in ("safe_min", "medium_min"):
        for shift in THRESHOLD_SHIFTS:
            safe = base.thresholds.safe_min + (shift if name == "safe_min" else 0)
            medium = base.thresholds.medium_min + (shift if name == "medium_min" else 0)
            if not (0 <= medium < safe <= 100):
                continue
            found.append(
                Variant(
                    parameter=f"thresholds.{name}",
                    change=f"{shift:+d} ({safe if name == 'safe_min' else medium})",
                    weights=dataclasses.replace(
                        base,
                        thresholds=Thresholds(safe_min=safe, medium_min=medium),
                        version=f"{base.version}~{name}{shift:+d}",
                    ),
                    reuses_penalties=True,
                    magnitude=abs(shift),
                )
            )
    return found


@dataclass(frozen=True)
class FlipCount:
    vector: str
    parameter: str
    change: str
    magnitude: int
    flips: int
    repositories: int
    by_ecosystem: dict[str, tuple[int, int]]

    @property
    def rate(self) -> float:
        return self.flips / self.repositories if self.repositories else 0.0


def sweep(panel: CorpusPanel, base: WeightSet, *, vector: str) -> list[FlipCount]:
    """Flip counts for every variant of `base`, against `base` itself."""
    base_penalties = occurrence_penalties(panel, base)
    baseline = roll_up_panel(panel, base_penalties, base)

    results: list[FlipCount] = []
    for variant in variants(base):
        penalties = (
            base_penalties
            if variant.reuses_penalties
            else occurrence_penalties(panel, variant.weights)
        )
        perturbed = roll_up_panel(panel, penalties, variant.weights)
        by_ecosystem: dict[str, list[int]] = {}
        flips = 0
        for before, after in zip(baseline, perturbed, strict=True):
            group = by_ecosystem.setdefault(before.repository.ecosystem, [0, 0])
            group[1] += 1
            if before.classification != after.classification:
                flips += 1
                group[0] += 1
        results.append(
            FlipCount(
                vector=vector,
                parameter=variant.parameter,
                change=variant.change,
                magnitude=variant.magnitude,
                flips=flips,
                repositories=len(baseline),
                by_ecosystem={
                    key: (value[0], value[1]) for key, value in by_ecosystem.items()
                },
            )
        )
    return results


@dataclass(frozen=True)
class SweepSummary:
    vector: str
    max_weight_rate_10: float
    max_weight_rate_20: float
    max_rate_overall: float
    #: Parameters whose flip rate passed File C's 20% discussion line.
    to_discuss: tuple[str, ...]

    @property
    def robust(self) -> bool:
        """H3: under 15% flips for every ±20% weight perturbation."""
        return self.max_weight_rate_20 < ROBUST_RATE


def summarise(flips: list[FlipCount]) -> SweepSummary:
    weight_rows = [row for row in flips if row.parameter.startswith("weight:")]
    return SweepSummary(
        vector=flips[0].vector if flips else "",
        max_weight_rate_10=max(
            (row.rate for row in weight_rows if row.magnitude == 10), default=0.0
        ),
        max_weight_rate_20=max(
            (row.rate for row in weight_rows if row.magnitude == 20), default=0.0
        ),
        max_rate_overall=max((row.rate for row in flips), default=0.0),
        to_discuss=tuple(
            sorted(
                {
                    f"{row.parameter} {row.change}"
                    for row in flips
                    if row.rate > DISCUSS_RATE
                }
            )
        ),
    )
