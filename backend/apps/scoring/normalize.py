"""The four signals, mapped onto 0-1 penalty terms (§5.2).

Normalization is where the formula's honesty lives, so all three of its
awkward cases are handled here rather than papered over upstream.

**A missing value is not a zero.** `staleness_days` is NULL when the registry
published no release history at all — we do not know how stale the package is.
Scoring that as 0 would assert "released today", which is a claim we cannot
make; scoring it as the cap would assert abandonment, equally unfounded. §5.2's
answer is to drop the term and redistribute its weight proportionally across
the signals we *did* measure, so the occurrence is scored on the evidence that
exists and nothing else. A zero CVE count is the opposite case and §5.2 says so
explicitly — it is an informative zero, a measurement, and it stays.

**A known vulnerability with no CVSS anywhere still has to be scored.** OSV
carries no severity for a fraction of advisories, and treating that as "no
severity" would score a real RCE at zero. §5.2's answer is a 5.0 placeholder
with `cvss_reduced_confidence` set, so the number exists and the fact that it
was assumed travels with it. (§5.2 puts an NVD lookup between OSV and the
placeholder; `NVD_API_KEY` is a Phase 12 knob, so until then the fallback is
OSV → placeholder and the reduced-confidence flag marks every row it touched.)

**Caps are applied before division, not after.** `min(cve_count, 10)/10` and
`min(days, 1095)/1095` both saturate: a package with 40 CVEs and one with 10
score the same on that term, and 1095 days of staleness is as stale as the
formula can say. That is deliberate — beyond the cap the signal stops
discriminating, and an uncapped term would let one pathological dependency
dominate a repository through a single unbounded number.

Nothing here touches the database or the weights registry: the inputs are a
`Signals` record and the caps, both passed in. §10 Phase 4 requires the engine
and normalization to be pure functions, which is also what makes the golden
fixtures able to state exact expected values.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#: The four Tier-1 signal names (D3). These strings are the keys of every
#: weights vector, of the normalized-term map, and of the per-term breakdown
#: Phase 5 renders — one vocabulary, so a typo is a KeyError rather than a
#: silently-dropped term.
DEPRECATION = "deprecation"
SEVERITY = "severity"
COUNT = "count"
STALENESS = "staleness"

#: The optional fifth term (D3), included only when a weights file enables it.
EPSS = "epss"

SIGNAL_NAMES: tuple[str, ...] = (DEPRECATION, SEVERITY, COUNT, STALENESS)

#: §5.2's stand-in for a known CVE whose severity nobody has scored.
CVSS_PLACEHOLDER = Decimal("5.0")
#: CVSS is a 0-10 scale; the term is the fraction of the worst possible score.
CVSS_SCALE = Decimal("10")

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True)
class Signals:
    """What one occurrence measured, as stored (§5.1).

    Deliberately a plain record rather than a model reference: the same four
    numbers arrive from a live `dependency_occurrences` row, from a permanent
    `dependency_history` row during a rescore, and from a literal in a test.
    A formula that could only be applied to one of those would make D6's
    "recompute from stored signals under any weights version" impossible.
    """

    is_deprecated: bool = False
    vulnerability_count: int = 0
    cvss_max: Decimal | None = None
    staleness_days: int | None = None
    #: Phase 12, behind `epss.enabled`. Absent here means "not measured", so
    #: an EPSS-enabled weights file redistributes its weight rather than
    #: scoring every occurrence as if exploitation were impossible.
    epss: Decimal | None = None


@dataclass(frozen=True)
class Normalized:
    """The 0-1 terms for one occurrence, and how they were arrived at.

    `terms` holds only the signals that were actually measured. A signal
    missing from this map is missing from the score, and `redistribute` moves
    its weight onto the ones that remain.
    """

    terms: dict[str, Decimal]
    #: True when `severity` rests on the 5.0 placeholder rather than a real
    #: CVSS score. Stored on the occurrence so the claim is auditable.
    cvss_reduced_confidence: bool = False


def _clamp01(value: Decimal) -> Decimal:
    if value < ZERO:
        return ZERO
    if value > ONE:
        return ONE
    return value


def normalize(
    signals: Signals,
    *,
    cve_count_cap: int,
    staleness_cap_days: int,
    include_epss: bool = False,
) -> Normalized:
    """Map one occurrence's stored signals onto §5.2's 0-1 terms."""
    terms: dict[str, Decimal] = {}

    terms[DEPRECATION] = ONE if signals.is_deprecated else ZERO

    # Severity, in the three states it actually comes in. A stored CVSS is used
    # whenever one exists — even in the (contradictory, and so far unobserved)
    # case of a score with no advisory rows behind it, because ignoring a
    # recorded severity could only ever understate risk.
    reduced_confidence = False
    if signals.cvss_max is not None:
        terms[SEVERITY] = _clamp01(Decimal(signals.cvss_max) / CVSS_SCALE)
    elif signals.vulnerability_count > 0:
        terms[SEVERITY] = CVSS_PLACEHOLDER / CVSS_SCALE
        reduced_confidence = True
    else:
        # Informative zero (§5.2): we looked, and there is nothing.
        terms[SEVERITY] = ZERO

    capped_count = min(max(signals.vulnerability_count, 0), cve_count_cap)
    terms[COUNT] = _clamp01(Decimal(capped_count) / Decimal(cve_count_cap))

    if signals.staleness_days is not None:
        capped_days = min(max(signals.staleness_days, 0), staleness_cap_days)
        terms[STALENESS] = _clamp01(Decimal(capped_days) / Decimal(staleness_cap_days))
    # else: no publish history. The term is absent, not zero.

    if include_epss and signals.epss is not None:
        terms[EPSS] = _clamp01(Decimal(signals.epss))

    return Normalized(terms=terms, cvss_reduced_confidence=reduced_confidence)


def redistribute(
    weights: dict[str, Decimal], present: frozenset[str] | set[str]
) -> dict[str, Decimal]:
    """Rescale `weights` onto the signals actually measured, keeping Σw = 1.

    Proportional, per §5.2: each surviving signal keeps its share *relative to
    the others*, so dropping staleness from an npm occurrence leaves
    deprecation still worth roughly 1.6x severity — the elicited ranking is
    preserved, only the absent term's mass is redistributed.

    Two degenerate inputs are handled rather than raised on, because both are
    reachable from a hand-written weights file: nothing present, and everything
    present carrying zero weight. Both yield all-zero weights, which scores the
    occurrence 100 — the correct answer when no measured signal carries any
    weight, and one the caller can see rather than an exception it cannot act on.
    """
    surviving = {name: weight for name, weight in weights.items() if name in present}
    total = sum(surviving.values(), ZERO)
    if total <= ZERO:
        return dict.fromkeys(surviving, ZERO)
    if total == ONE:
        # The common case: nothing was missing. Returned unscaled so the
        # arithmetic in a golden fixture is the weights file's own numbers.
        return surviving
    return {name: weight / total for name, weight in surviving.items()}
