"""How well the formula's scores track a reference (RQ2).

§10 Phase 12: "Pearson + Spearman vs both references (with CIs); 3-class
confusion + Cohen's kappa (reference bucketed by tertiles; bucketing-choice
sensitivity reported)."

**Spearman is primary.** File C §2.4.3: a monotone relation is all convergent
validity needs, and Spearman does not care that a Scorecard of 6 and a score of
40 are on different scales. Pearson is reported beside it because a reviewer
will ask, and a large gap between the two says the relation is monotone but
not linear — itself worth a sentence.

**The confidence intervals resample repositories.** The bootstrap draws
repositories with replacement and recomputes the statistic, File C §2.4.3's
"cluster = repo". Seeded and printed, two thousand iterations by default
(File C §1.4).

**A kappa depends on where the reference is cut, so it is reported under
three cuts.** The formula has three classes with thresholds of its own; a
continuous reference has none, and any cut is a choice. Tertiles are the
choice §10 Phase 12 names. Matching the formula's own class proportions asks
the purer question — do the two *order* repositories alike? — by holding the
marginals equal. Equal thirds of the reference's 0-10 scale is the cut a
reader would draw by eye. If the three disagree sharply, the kappa is a
statement about the cut rather than about the formula, and that is what
"bucketing-choice sensitivity" means.

**Missing references are excluded, and counted.** A repository deps.dev has no
scorecard for is not a zero; the report states how many of the corpus each
correlation covers, because a correlation over the 60% that have a scorecard
is a claim about that 60%.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.scanning.models import Classification

from . import stats
from .panel import RepoScore

#: §5.3's classes, worst first — the order every confusion matrix is printed in.
CLASSES: tuple[str, ...] = (
    Classification.HIGH_ALERT.value,
    Classification.MEDIUM.value,
    Classification.SAFE.value,
)

TERTILES = "tertiles"
MATCHED = "matched_proportions"
EQUAL_THIRDS = "equal_thirds_of_scale"

#: Both references run 0-10 once oriented healthy-high: Scorecard natively,
#: OSV as `10 - worst CVSS`.
REFERENCE_SCALE: tuple[float, float] = (0.0, 10.0)


@dataclass(frozen=True)
class Correlation:
    method: str  # "spearman" | "pearson"
    weighted: bool
    n: int
    value: float | None
    interval: tuple[float, float] | None


@dataclass(frozen=True)
class Confusion:
    bucketing: str
    cuts: tuple[float, ...]
    #: `matrix[i][j]`: formula class `CLASSES[i]`, reference bucket `CLASSES[j]`.
    matrix: list[list[int]]
    kappa: float | None
    n: int

    @property
    def agreement(self) -> float:
        total = sum(sum(row) for row in self.matrix)
        return (
            sum(self.matrix[i][i] for i in range(len(CLASSES))) / total if total else 0.0
        )


@dataclass
class Agreement:
    """One weights version against one reference, overall or for one ecosystem."""

    vector: str
    reference: str
    group: str
    repositories: int
    covered: int
    correlations: list[Correlation] = field(default_factory=list)
    confusions: list[Confusion] = field(default_factory=list)

    def correlation(self, method: str, *, weighted: bool = False) -> Correlation | None:
        for correlation in self.correlations:
            if correlation.method == method and correlation.weighted == weighted:
                return correlation
        return None

    def confusion(self, bucketing: str) -> Confusion | None:
        for found in self.confusions:
            if found.bucketing == bucketing:
                return found
        return None


def _bucketed(values: list[float], cuts: list[float]) -> list[str]:
    return [CLASSES[stats.bucket(value, cuts)] for value in values]


def _matched(
    references: list[float], classes: list[str]
) -> tuple[list[str], list[float]]:
    """Reference buckets sized exactly like the formula's classes, by rank.

    By rank rather than by a value cut, because a value cut cannot express an
    empty class — a cut at the 0th percentile still captures the minimum — and
    the whole point of this bucketing is that the marginals are equal. Ties at
    a boundary are split in a fixed order (value, then position), which is
    arbitrary but reproducible; the cuts returned are the boundary values, for
    the report.
    """
    sizes = [sum(1 for value in classes if value == name) for name in CLASSES]
    order = sorted(range(len(references)), key=lambda index: (references[index], index))
    buckets = [""] * len(references)
    cuts: list[float] = []
    start = 0
    for position, size in enumerate(sizes):
        for index in order[start : start + size]:
            buckets[index] = CLASSES[position]
        start += size
        if position < len(CLASSES) - 1 and start:
            cuts.append(references[order[start - 1]])
    return buckets, cuts


def _cuts(bucketing: str, references: list[float]) -> list[float]:
    if bucketing == TERTILES:
        return stats.quantile_cuts(references, (1 / 3, 2 / 3))
    if bucketing == EQUAL_THIRDS:
        start, end = REFERENCE_SCALE
        width = (end - start) / 3
        return [start + width, start + 2 * width]
    raise ValueError(f"unknown bucketing {bucketing!r}")


def agreement(
    scores: list[RepoScore],
    references: dict[str, float | None],
    *,
    vector: str,
    reference: str,
    group: str = "all",
    bootstrap: int = 2000,
    seed: int = 42,
) -> Agreement:
    """Correlations and confusion matrices for the repositories with a reference."""
    covered = [
        (result, references[result.repository.full_name])
        for result in scores
        if references.get(result.repository.full_name) is not None
    ]
    found = Agreement(
        vector=vector,
        reference=reference,
        group=group,
        repositories=len(scores),
        covered=len(covered),
    )
    if len(covered) < 3:
        return found

    x = [float(result.score) for result, _ in covered]
    y = [float(value) for _, value in covered]
    w = [result.repository.weight for result, _ in covered]

    for method, function in (("spearman", stats.spearman), ("pearson", stats.pearson)):

        def statistic(indices, function=function):
            return function([x[i] for i in indices], [y[i] for i in indices])

        found.correlations.append(
            Correlation(
                method=method,
                weighted=False,
                n=len(x),
                value=function(x, y),
                interval=stats.bootstrap_interval(
                    len(x), statistic, iterations=bootstrap, seed=seed
                ),
            )
        )
        found.correlations.append(
            Correlation(
                method=method,
                weighted=True,
                n=len(x),
                value=function(x, y, w),
                interval=None,
            )
        )

    classes = [result.classification for result, _ in covered]
    for bucketing in (TERTILES, MATCHED, EQUAL_THIRDS):
        if bucketing == MATCHED:
            buckets, cuts = _matched(y, classes)
        else:
            cuts = _cuts(bucketing, y)
            buckets = _bucketed(y, cuts)
        matrix = stats.confusion(classes, buckets, CLASSES)
        found.confusions.append(
            Confusion(
                bucketing=bucketing,
                cuts=tuple(cuts),
                matrix=matrix,
                kappa=stats.cohen_kappa(matrix),
                n=len(classes),
            )
        )
    return found


def by_group(
    scores: list[RepoScore],
    references: dict[str, float | None],
    *,
    vector: str,
    reference: str,
    bootstrap: int,
    seed: int,
) -> list[Agreement]:
    """The whole corpus, then each single-ecosystem group of it.

    Mixed repositories are in the overall figure and not in either ecosystem's:
    their score rolls up occurrences scored under two vectors, so they belong to
    neither.
    """
    groups = [("all", scores)]
    for ecosystem in sorted({result.repository.ecosystem for result in scores}):
        if ecosystem in ("npm", "pypi"):
            groups.append(
                (ecosystem, [r for r in scores if r.repository.ecosystem == ecosystem])
            )
    return [
        agreement(
            subset,
            references,
            vector=vector,
            reference=reference,
            group=group,
            bootstrap=bootstrap,
            seed=seed,
        )
        for group, subset in groups
    ]
