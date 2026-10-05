"""The corpus cross-section, loaded once and scored by the shipped engine.

Every S1 analysis starts from the same thing: the `corpus_scan` rows of one
snapshot (D14), each repository with its occurrences' four stored signals.
Entropy weights read the signals; the correlation, the sensitivity sweep and
the anchor check read repository scores recomputed from them under a chosen
weights version. This module is the one place that loading and that
recomputation happen, so the analyses cannot disagree about what the corpus
is.

**Scores are recomputed, never read** (D6, File C §1.1). The stored
`risk_score` is what the product showed on the day under the version tagged on
the row; a study asks "what would this formula say", which is a recomputation
over the stored signals with `engine.score_occurrence` and `engine.roll_up` —
the functions the product scores with, imported, exactly as `rescore` and the
corpus scan itself import them (§11.1). The stored score is kept beside the
recomputed one for one purpose: proving that recomputing under the stored
version reproduces it, which `reproduction_check` does on every run.

**One snapshot, chosen explicitly when there is a choice.** A research database
can hold two snapshots — a second taken on purpose, or the split §11.28 fixed.
Pooling them would put one repository in the sample twice and blend two dates
into one "cross-section", so the loader refuses an ambiguous database rather
than picking the newest the way `corpus_report` does for a chart.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scoring.engine import classify, is_flagged, roll_up, score_occurrence
from apps.scoring.normalize import Signals
from apps.scoring.weights import WeightSet

#: Repositories whose manifests span both ecosystems. Their score rolls up
#: occurrences scored under two vectors, so any per-ecosystem repository
#: statistic either drops them or reports them as their own group.
MIXED = "mixed"


class PanelError(Exception):
    """No corpus to analyse, or more than one and no instruction which."""


@dataclass(frozen=True)
class Occurrence:
    """One `dependency_history` row, reduced to what the formula reads."""

    ecosystem: str
    is_unassessable: bool
    signals: Signals


@dataclass
class PanelRepository:
    """One corpus repository: its identity, its frame weight, its occurrences."""

    scan_history_id: str
    github_repo_id: int
    full_name: str
    owner: str
    ecosystems: str
    sampling_weight: float | None
    stored_score: Decimal
    stored_classification: str
    stored_version: str
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def ecosystem(self) -> str:
        """`npm`, `pypi`, or `mixed` — the group a repository-level statistic uses."""
        found = {part for part in self.ecosystems.split(",") if part}
        if len(found) == 1:
            return found.pop()
        return MIXED if found else ""

    @property
    def weight(self) -> float:
        """The expansion weight, or 1 for a row that carries none."""
        return float(self.sampling_weight) if self.sampling_weight else 1.0


@dataclass
class CorpusPanel:
    snapshot_date: date
    repositories: list[PanelRepository]

    @property
    def occurrence_count(self) -> int:
        return sum(len(repository.occurrences) for repository in self.repositories)

    def ecosystems(self) -> list[str]:
        return sorted({repository.ecosystem for repository in self.repositories})


def corpus_snapshot_dates() -> list[date]:
    """Every snapshot date the research database holds corpus rows for."""
    return sorted(
        ScanHistory.objects.filter(data_source=DataSource.CORPUS_SCAN.value)
        .exclude(snapshot_date=None)
        .order_by()
        .values_list("snapshot_date", flat=True)
        .distinct()
    )


def resolve_snapshot(requested: date | None) -> date:
    """The snapshot to analyse, or a refusal that lists the choices."""
    available = corpus_snapshot_dates()
    listed = ", ".join(day.isoformat() for day in available) or "none"
    if requested is not None:
        if requested not in available:
            raise PanelError(
                f"No corpus_scan rows as of {requested.isoformat()}. Snapshot dates "
                f"in this database: {listed}."
            )
        return requested
    if not available:
        raise PanelError(
            "This database holds no corpus_scan rows. Run `scan_corpus` (WP-5), or "
            "point DATABASE_URL at the research database the dump was restored "
            "into (D8)."
        )
    if len(available) > 1:
        raise PanelError(
            f"This database holds more than one corpus snapshot ({listed}). One "
            f"cross-section is one date (D14): pass --snapshot-date with the one "
            f"to analyse."
        )
    return available[0]


def load_panel(snapshot_date: date | None = None) -> CorpusPanel:
    """Every corpus repository of one snapshot, with its occurrences.

    Two queries — the repositories, then all their occurrences in one pass —
    rather than one per repository: a thousand round trips is what makes a
    research command slow on the teammate's laptop. `.order_by()` clears
    `Meta.ordering` on both, for §11.21's reason.
    """
    snapshot = resolve_snapshot(snapshot_date)
    scans = ScanHistory.objects.filter(
        data_source=DataSource.CORPUS_SCAN.value, snapshot_date=snapshot
    ).order_by("repo_full_name", "scan_history_id")

    repositories: dict = {}
    for row in scans.iterator(chunk_size=1000):
        repositories[row.pk] = PanelRepository(
            scan_history_id=str(row.pk),
            github_repo_id=row.github_repo_id,
            full_name=row.repo_full_name,
            owner=row.github_username,
            ecosystems=row.ecosystems,
            sampling_weight=float(row.sampling_weight)
            if row.sampling_weight is not None
            else None,
            stored_score=row.risk_score,
            stored_classification=row.classification,
            stored_version=row.scoring_formula_version,
        )

    rows = (
        DependencyHistory.objects.filter(scan_history__in=scans.order_by())
        .order_by()
        .values_list(
            "scan_history_id",
            "ecosystem",
            "is_unassessable",
            "is_deprecated",
            "vulnerability_count",
            "cvss_max",
            "staleness_days",
            "manifest_path",
            "package_name",
        )
    )
    grouped: dict = defaultdict(list)
    for (
        scan_id,
        ecosystem,
        unassessable,
        deprecated,
        vulnerabilities,
        cvss,
        staleness,
        manifest_path,
        package_name,
    ) in rows.iterator(chunk_size=5000):
        grouped[scan_id].append(
            (
                manifest_path,
                package_name,
                Occurrence(
                    ecosystem=ecosystem,
                    is_unassessable=bool(unassessable),
                    # The same construction `signals.signals_for` makes from a
                    # row; spelled out because a `values_list` tuple is not one.
                    signals=Signals(
                        is_deprecated=bool(deprecated),
                        vulnerability_count=int(vulnerabilities or 0),
                        cvss_max=Decimal(cvss) if cvss is not None else None,
                        staleness_days=staleness,
                    ),
                ),
            )
        )
    for scan_id, occurrences in grouped.items():
        repository = repositories.get(scan_id)
        if repository is None:  # pragma: no cover - the filter makes this unreachable
            continue
        # A fixed order, so anything that iterates occurrences (a bootstrap,
        # a tie in the roll-up's sort) is reproducible across databases.
        occurrences.sort(key=lambda entry: (entry[0], entry[1]))
        repository.occurrences = [entry[2] for entry in occurrences]

    return CorpusPanel(snapshot_date=snapshot, repositories=list(repositories.values()))


# ── scoring ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RepoScore:
    repository: PanelRepository
    score: Decimal
    classification: str
    assessed: int
    flagged: int


def occurrence_penalties(
    panel: CorpusPanel, weights: WeightSet
) -> list[tuple[list[Decimal], int]]:
    """`(penalties, flagged)` per repository, in panel order, under `weights`.

    Memoized on `(ecosystem, signals)` for the duration of one call: a corpus of
    forty thousand occurrences holds far fewer distinct signal tuples (every
    clean dependency released on the same day is the same tuple), and the
    sensitivity sweep calls this dozens of times. The memo caches the shipped
    engine's answer; it does not replace the engine.
    """
    memo: dict[tuple[str, Signals], Decimal] = {}
    flag_memo: dict[Signals, bool] = {}
    out: list[tuple[list[Decimal], int]] = []
    for repository in panel.repositories:
        penalties: list[Decimal] = []
        flagged = 0
        for occurrence in repository.occurrences:
            if occurrence.is_unassessable:
                continue
            key = (occurrence.ecosystem, occurrence.signals)
            penalty = memo.get(key)
            if penalty is None:
                penalty = score_occurrence(
                    occurrence.signals, weights, occurrence.ecosystem
                ).penalty
                memo[key] = penalty
            penalties.append(penalty)
            flag = flag_memo.get(occurrence.signals)
            if flag is None:
                flag = is_flagged(occurrence.signals, weights)
                flag_memo[occurrence.signals] = flag
            flagged += int(flag)
        out.append((penalties, flagged))
    return out


def roll_up_panel(
    panel: CorpusPanel,
    penalties: list[tuple[list[Decimal], int]],
    weights: WeightSet,
) -> list[RepoScore]:
    """§5.3 over precomputed penalties — the cheap half of a re-score.

    Split from `occurrence_penalties` because a change to `decay`,
    `max_terms` or the thresholds leaves every occurrence's penalty where it
    was; the sensitivity sweep re-rolls rather than re-scoring forty thousand
    rows to move one threshold.
    """
    scores: list[RepoScore] = []
    for repository, (repo_penalties, flagged) in zip(
        panel.repositories, penalties, strict=True
    ):
        result = roll_up(repo_penalties, weights)
        scores.append(
            RepoScore(
                repository=repository,
                score=result.score,
                classification=classify(result.score, weights),
                assessed=result.assessed_count,
                flagged=flagged,
            )
        )
    return scores


def score_panel(panel: CorpusPanel, weights: WeightSet) -> list[RepoScore]:
    """Every repository of the panel, scored and classified under `weights`."""
    return roll_up_panel(panel, occurrence_penalties(panel, weights), weights)


@dataclass(frozen=True)
class ReproductionCheck:
    """Does recomputing under each row's own version give back the stored score?

    D6's claim, checked on the data rather than asserted about it. A mismatch
    means the weights file for that version changed on disk after the scan, or
    the rows were written by something other than the shipped pipeline — and
    either way every recomputed number in the report is suspect until it is
    explained.
    """

    checked: int
    matched: int
    unloadable_versions: tuple[str, ...]
    mismatches: tuple[tuple[str, str, str], ...]

    @property
    def all_match(self) -> bool:
        return self.checked > 0 and self.matched == self.checked


def reproduction_check(panel: CorpusPanel, load) -> ReproductionCheck:
    """Recompute every repository under the version tagged on its row.

    `load` is `weights.load_weights`, passed in so a test can supply files that
    are not on disk.
    """
    from apps.scoring.weights import WeightsError

    by_version: dict[str, list[int]] = defaultdict(list)
    for index, repository in enumerate(panel.repositories):
        by_version[repository.stored_version].append(index)

    matched = 0
    checked = 0
    unloadable: list[str] = []
    mismatches: list[tuple[str, str, str]] = []
    for version, indexes in sorted(by_version.items()):
        try:
            weights = load(version)
        except WeightsError:
            unloadable.append(version)
            continue
        subset = CorpusPanel(
            snapshot_date=panel.snapshot_date,
            repositories=[panel.repositories[index] for index in indexes],
        )
        for result in score_panel(subset, weights):
            checked += 1
            if result.score == result.repository.stored_score:
                matched += 1
            else:
                mismatches.append(
                    (
                        result.repository.full_name,
                        str(result.repository.stored_score),
                        str(result.score),
                    )
                )
    return ReproductionCheck(
        checked=checked,
        matched=matched,
        unloadable_versions=tuple(unloadable),
        mismatches=tuple(mismatches[:20]),
    )
