"""Entropy weights: what the corpus's own variation says each signal is worth.

§10 Phase 12: "Shannon-entropy weights from the corpus's normalized signal
matrix (`corpus_scan` rows of `dependency_history`); comparison vs AHP vector
(cosine similarity + rank order)." This is S1's RQ1 — do a subjective method
(two people judging pairs) and an objective one (the data's dispersion) agree?

**The method, as every MCDM text states it.** For a signal j measured on m
occurrences with normalised values x_ij ≥ 0:

    p_ij = x_ij / Σ_i x_ij
    E_j  = -(1 / ln m) · Σ_i p_ij · ln p_ij          (0 · ln 0 taken as 0)
    d_j  = 1 - E_j
    w_j  = d_j / Σ_k d_k

A signal spread evenly over the corpus has E near 1 and says little about
which occurrence is riskier; one concentrated on a few occurrences has low E
and high weight. **That is why entropy and AHP can legitimately disagree**:
deprecation is rare and decisive, so entropy weights it heavily for the same
reason a judge might — but a judge also weighs *how bad* a deprecation is,
which dispersion cannot see. File C §2.4.2 calls a divergence there "an
interpretable finding, not a failure", and the report says so beside it.

**What a "row" is.** Every assessable occurrence of the snapshot, normalised by
`apps.scoring.normalize.normalize` under the caps in the weights file being
compared — the same 0-1 terms the formula multiplies the weights by.
Unassessable occurrences are excluded, as they are from every denominator
(§5.2). A missing `staleness_days` is a missing *measurement*, not a zero, so
that occurrence is left out of the staleness column only, which is §5.2's
missing-value policy applied to the matrix rather than to one score.

**Per ecosystem.** Each ecosystem carries its own weight vector (D1), so each
gets its own entropy vector, computed over the occurrences scored under it. A
mixed repository contributes its npm rows to npm and its PyPI rows to PyPI.

**Computed from per-repository sums.** E_j depends on the column only through
m, Σx and Σ x·ln x, so each repository is reduced to those three numbers per
signal once. That makes the repository-cluster bootstrap File C §1.4 asks for
— resample repositories, not occurrences, because occurrences in one
repository are not independent — a matter of adding up a few thousand tuples
rather than re-walking forty thousand rows two thousand times.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from apps.scoring.normalize import SIGNAL_NAMES, normalize
from apps.scoring.weights import WeightSet

from . import stats
from .panel import CorpusPanel

#: File C §2.4.2's bands for RQ1, on cosine similarity.
STRONG_AGREEMENT = 0.90
PARTIAL_AGREEMENT = 0.75


@dataclass(frozen=True)
class ColumnSums:
    """One signal's sufficient statistics over some set of occurrences."""

    count: float = 0.0
    total: float = 0.0
    xlogx: float = 0.0
    nonzero: int = 0

    def __add__(self, other: ColumnSums) -> ColumnSums:
        return ColumnSums(
            count=self.count + other.count,
            total=self.total + other.total,
            xlogx=self.xlogx + other.xlogx,
            nonzero=self.nonzero + other.nonzero,
        )

    def scaled(self, factor: float) -> ColumnSums:
        """The same rows counted `factor` times — a frequency weight."""
        return ColumnSums(
            count=self.count * factor,
            total=self.total * factor,
            xlogx=self.xlogx * factor,
            nonzero=self.nonzero,
        )


def column_entropy(column: ColumnSums) -> float | None:
    """E_j from its sums. None when m ≤ 1, where ln m makes it undefined.

    Σ p·ln p = Σ (x/S)(ln x - ln S) = (Σ x·ln x)/S - ln S, so the entropy needs
    only the three sums. A column that is zero everywhere has no distribution
    at all; it is given E = 1 (no information), which is the limit an
    almost-zero column approaches and gives it zero weight.
    """
    if column.count <= 1:
        return None
    if column.total <= 0:
        return 1.0
    entropy = -(column.xlogx / column.total - math.log(column.total)) / math.log(
        column.count
    )
    return min(1.0, max(0.0, entropy))


def repository_sums(
    panel: CorpusPanel, weights: WeightSet, ecosystem: str
) -> list[tuple[float, dict[str, ColumnSums]]]:
    """`(sampling weight, {signal: sums})` per repository with rows in `ecosystem`."""
    caps = weights.normalization
    out: list[tuple[float, dict[str, ColumnSums]]] = []
    for repository in panel.repositories:
        columns = {signal: ColumnSums() for signal in SIGNAL_NAMES}
        used = False
        for occurrence in repository.occurrences:
            if occurrence.is_unassessable or occurrence.ecosystem != ecosystem:
                continue
            used = True
            terms = normalize(
                occurrence.signals,
                cve_count_cap=caps.cve_count_cap,
                staleness_cap_days=caps.staleness_cap_days,
            ).terms
            for signal in SIGNAL_NAMES:
                if signal not in terms:
                    continue  # unmeasured, not zero (§5.2)
                value = float(terms[signal])
                columns[signal] = columns[signal] + ColumnSums(
                    count=1.0,
                    total=value,
                    xlogx=value * math.log(value) if value > 0 else 0.0,
                    nonzero=int(value > 0),
                )
        if used:
            out.append((repository.weight, columns))
    return out


@dataclass(frozen=True)
class EntropyColumn:
    signal: str
    #: Occurrences in the column — frequency-weighted when the run is.
    rows: float
    nonzero: int
    entropy: float | None
    divergence: float
    weight: float | None


@dataclass(frozen=True)
class EntropyResult:
    ecosystem: str
    sampling_weighted: bool
    repositories: int
    columns: tuple[EntropyColumn, ...]
    #: 95% percentile intervals from the repository-cluster bootstrap, or
    #: empty when no bootstrap was asked for.
    intervals: dict[str, tuple[float, float]]
    bootstrap: int
    seed: int | None

    @property
    def degenerate(self) -> bool:
        """No signal varies at all, so there is nothing to weight by."""
        return all(column.weight is None for column in self.columns)

    def vector(self) -> dict[str, float]:
        return {
            column.signal: column.weight
            for column in self.columns
            if column.weight is not None
        }


def _weights_from(columns: dict[str, ColumnSums]) -> tuple[dict, dict, dict]:
    entropies = {signal: column_entropy(column) for signal, column in columns.items()}
    divergences = {
        signal: (1.0 - entropy) if entropy is not None else 0.0
        for signal, entropy in entropies.items()
    }
    total = sum(divergences.values())
    weights = {
        signal: (divergence / total) if total > 0 else None
        for signal, divergence in divergences.items()
    }
    return entropies, divergences, weights


def _summed(rows: list[tuple[float, dict[str, ColumnSums]]], weighted: bool) -> dict:
    totals = {signal: ColumnSums() for signal in SIGNAL_NAMES}
    for repository_weight, columns in rows:
        for signal in SIGNAL_NAMES:
            column = columns[signal]
            totals[signal] = totals[signal] + (
                column.scaled(repository_weight) if weighted else column
            )
    return totals


def entropy_weights(
    panel: CorpusPanel,
    weights: WeightSet,
    ecosystem: str,
    *,
    sampling_weighted: bool = False,
    bootstrap: int = 0,
    seed: int = 42,
) -> EntropyResult:
    """The entropy vector for one ecosystem, optionally with bootstrap intervals.

    `weights` supplies only the normalisation caps — the vector is the data's,
    not the file's. `sampling_weighted` treats each repository's frame weight
    as a frequency (File C §1.3: population estimates are weighted, with the
    unweighted figure beside them).
    """
    rows = repository_sums(panel, weights, ecosystem)
    totals = _summed(rows, sampling_weighted)
    entropies, divergences, point = _weights_from(totals)

    intervals: dict[str, tuple[float, float]] = {}
    if bootstrap and rows:
        rng = random.Random(seed)  # noqa: S311 - resampling, not crypto
        draws: dict[str, list[float]] = {signal: [] for signal in SIGNAL_NAMES}
        for _ in range(bootstrap):
            sample = [rows[rng.randrange(len(rows))] for _ in range(len(rows))]
            _, _, resampled = _weights_from(_summed(sample, sampling_weighted))
            for signal, value in resampled.items():
                if value is not None:
                    draws[signal].append(value)
        for signal, values in draws.items():
            if values:
                values.sort()
                intervals[signal] = (
                    stats.percentile(values, 0.025),
                    stats.percentile(values, 0.975),
                )

    return EntropyResult(
        ecosystem=ecosystem,
        sampling_weighted=sampling_weighted,
        repositories=len(rows),
        columns=tuple(
            EntropyColumn(
                signal=signal,
                rows=totals[signal].count,
                nonzero=totals[signal].nonzero,
                entropy=entropies[signal],
                divergence=divergences[signal],
                weight=point[signal],
            )
            for signal in SIGNAL_NAMES
        ),
        intervals=intervals,
        bootstrap=bootstrap if rows else 0,
        seed=seed if bootstrap else None,
    )


# ── AHP vs entropy (RQ1) ───────────────────────────────────────────────────


def rank_order(vector: dict[str, float]) -> tuple[str, ...]:
    """Signals heaviest first; a tie keeps D3's canonical order."""
    canonical = {signal: index for index, signal in enumerate(SIGNAL_NAMES)}
    return tuple(
        sorted(vector, key=lambda signal: (-vector[signal], canonical.get(signal, 99)))
    )


@dataclass(frozen=True)
class VectorComparison:
    first_name: str
    second_name: str
    first: dict[str, float]
    second: dict[str, float]
    cosine: float | None
    spearman: float | None

    @property
    def first_order(self) -> tuple[str, ...]:
        return rank_order(self.first)

    @property
    def second_order(self) -> tuple[str, ...]:
        return rank_order(self.second)

    @property
    def top_two_identical(self) -> bool:
        """File C H1's second clause: the same two signals, in the same order."""
        return self.first_order[:2] == self.second_order[:2]

    @property
    def band(self) -> str:
        """File C §2.4.2: strong ≥ 0.90 / partial 0.75-0.90 / tension < 0.75."""
        if self.cosine is None:
            return "undefined"
        if self.cosine >= STRONG_AGREEMENT:
            return "strong"
        if self.cosine >= PARTIAL_AGREEMENT:
            return "partial"
        return "tension"

    @property
    def largest_gap(self) -> tuple[str, float]:
        """The signal the two vectors disagree about most, and by how much."""
        gaps = {
            signal: self.second.get(signal, 0.0) - self.first.get(signal, 0.0)
            for signal in SIGNAL_NAMES
        }
        signal = max(gaps, key=lambda name: (abs(gaps[name]), name))
        return signal, gaps[signal]


def compare_vectors(
    first: dict[str, float],
    second: dict[str, float],
    *,
    first_name: str,
    second_name: str,
) -> VectorComparison:
    """Cosine similarity and rank agreement between two weight vectors."""
    a = [float(first.get(signal, 0.0)) for signal in SIGNAL_NAMES]
    b = [float(second.get(signal, 0.0)) for signal in SIGNAL_NAMES]
    return VectorComparison(
        first_name=first_name,
        second_name=second_name,
        first={signal: float(first.get(signal, 0.0)) for signal in SIGNAL_NAMES},
        second={signal: float(second.get(signal, 0.0)) for signal in SIGNAL_NAMES},
        cosine=stats.cosine(a, b),
        spearman=stats.spearman(a, b),
    )
