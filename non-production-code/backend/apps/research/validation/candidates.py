"""Weight vectors turned into weight sets the shipped engine can score with.

The harness compares three formulas over the same stored signals: the active
file (`v1`), the AHP-derived candidate for `v2`, and the entropy vector. The
engine scores only `WeightSet`s, so the two derived vectors are turned into
one here — same caps, flag rule, roll-up and thresholds as the base file, only
the per-ecosystem vectors replaced. Anything else would compare formulas that
differ in more than their weights, and the sensitivity analysis is where the
other parameters are varied, one at a time, on purpose.

**Rounding sums to exactly 1.** The weights loader accepts ±0.001 (§5.4), but
a candidate file is written to be *committed* after WP-6, and four weights
rounded independently to four decimals can sum to 0.9999 — a file whose own
arithmetic does not close. The largest-remainder method rounds them so they
sum to 1 exactly, moving each by less than one unit in the last place.

**PyPI's vector is a stated rule, not a second matrix.** File C limitation L4:
the PyPI vector is "derived by reasoning + the same AHP session". The 2026-09-24
review asks the WP-3 notes to state that rule explicitly — how much
deprecation weight is removed and how it is split — and `--pypi-shift` is
where it enters: `deprecation=-0.14,severity=+0.07,staleness=+0.07`. Without
one, the PyPI vector is the npm vector, and the report says so in a sentence
of its own rather than leaving it to be noticed.
"""

from __future__ import annotations

import dataclasses
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import yaml

from apps.scoring.normalize import SIGNAL_NAMES
from apps.scoring.weights import REQUIRED_ECOSYSTEMS, WeightSet, parse_weights

#: Four decimals: the precision of the vectors the candidate file states.
PLACES = 4


class CandidateError(Exception):
    """A vector or a shift that cannot become a valid weights file."""


def round_vector(vector: dict[str, float], places: int = PLACES) -> dict[str, Decimal]:
    """Round to `places` decimals so the result sums to exactly 1.

    Largest remainder: floor every share, then hand the missing units to the
    shares that lost the most. Ties go in D3's canonical order, so the result
    is a function of the input and nothing else.
    """
    total = sum(vector.get(signal, 0.0) for signal in SIGNAL_NAMES)
    if total <= 0:
        raise CandidateError("A weight vector must have a positive sum.")
    unit = Decimal(1).scaleb(-places)
    scaled = {
        signal: Decimal(repr(vector.get(signal, 0.0) / total)) / unit
        for signal in SIGNAL_NAMES
    }
    floored = {
        signal: value.to_integral_value(rounding=ROUND_FLOOR)
        for signal, value in scaled.items()
    }
    missing = int(Decimal(1) / unit - sum(floored.values()))
    order = sorted(
        SIGNAL_NAMES,
        key=lambda signal: (
            -(scaled[signal] - floored[signal]),
            SIGNAL_NAMES.index(signal),
        ),
    )
    for signal in order[:missing]:
        floored[signal] += 1
    return {signal: floored[signal] * unit for signal in SIGNAL_NAMES}


def parse_shift(text: str | None) -> dict[str, float]:
    """`"deprecation=-0.14,severity=+0.07,staleness=+0.07"` -> a zero-sum shift."""
    if not text:
        return {}
    shift: dict[str, float] = {}
    for part in text.split(","):
        name, _, value = part.partition("=")
        name = name.strip().lower()
        if name not in SIGNAL_NAMES:
            raise CandidateError(
                f"--pypi-shift names {name!r}; the signals are {', '.join(SIGNAL_NAMES)}."
            )
        try:
            shift[name] = float(value)
        except ValueError as exc:
            raise CandidateError(f"--pypi-shift: {value!r} is not a number.") from exc
    if abs(sum(shift.values())) > 1e-9:
        raise CandidateError(
            f"--pypi-shift must move weight between signals, not add or remove it; "
            f"it sums to {sum(shift.values()):+.4f}."
        )
    return shift


def apply_shift(vector: dict[str, float], shift: dict[str, float]) -> dict[str, float]:
    shifted = {
        signal: vector.get(signal, 0.0) + shift.get(signal, 0.0)
        for signal in SIGNAL_NAMES
    }
    negative = [signal for signal, value in shifted.items() if value < 0]
    if negative:
        raise CandidateError(f"--pypi-shift takes {', '.join(negative)} below zero.")
    return shifted


def weightset_from(
    base: WeightSet,
    vectors: dict[str, dict[str, float]],
    *,
    version: str,
    derivation: str,
) -> WeightSet:
    """`base` with its per-ecosystem vectors replaced, rounded to sum to 1."""
    missing = [ecosystem for ecosystem in REQUIRED_ECOSYSTEMS if ecosystem not in vectors]
    if missing:
        raise CandidateError(f"No vector for {', '.join(missing)}.")
    return dataclasses.replace(
        base,
        version=version,
        derivation=derivation,
        weights={
            ecosystem: round_vector(vectors[ecosystem])
            for ecosystem in REQUIRED_ECOSYSTEMS
        },
        epss_enabled=False,
        epss_weight=Decimal(0),
    )


def render_weights_file(weights: WeightSet, header: list[str]) -> str:
    """The candidate as a §5.4 weights file, validated by the loader itself.

    Parsed back through `weights.parse_weights` before it is returned, so a
    candidate the product would refuse to load is caught here rather than on
    the day someone sets `WEIGHTS_VERSION=v2`.
    """

    def vector(ecosystem: str) -> str:
        values = weights.weights[ecosystem]
        return ", ".join(f"{signal}: {values[signal]}" for signal in SIGNAL_NAMES)

    lines = [f"# {line}" if line else "#" for line in header]
    lines += [
        "",
        f"version: {weights.version}",
        f"derivation: {weights.derivation}",
        "normalization: { "
        f"cve_count_cap: {weights.normalization.cve_count_cap}, "
        f"staleness_cap_days: {weights.normalization.staleness_cap_days} }}",
        f"flag_rule:     {{ stale_flag_days: {weights.stale_flag_days} }}",
        "thresholds:    { "
        f"safe_min: {weights.thresholds.safe_min}, "
        f"medium_min: {weights.thresholds.medium_min} }}",
        f"rollup:        {{ decay: {weights.rollup.decay}, max_terms: {weights.rollup.max_terms} }}",
        "weights:",
        *(
            f"  {ecosystem}:{' ' * (5 - len(ecosystem))}{{ {vector(ecosystem)} }}"
            for ecosystem in REQUIRED_ECOSYSTEMS
        ),
        "epss: { enabled: false, weight: 0.0 }",
        "",
    ]
    text = "\n".join(lines)
    parse_weights(
        yaml.safe_load(text), Path(f"weights_{weights.version}.yaml"), weights.version
    )
    return text
