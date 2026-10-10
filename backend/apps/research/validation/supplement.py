"""S1's analyses beyond WP-6's harness (File C §1.3, §2.4.6, §2.4.7).

`validate_formula` answered RQ1-RQ4 and WP-6 signed it. File C asks for four
more things before S1 can be written, and none of them needs new data — each
is a recomputation over the same corpus panel, through the same engine (§1.1):

1. **Sampling-weighted population estimates** (§1.3). The corpus oversampled
   stale repositories on purpose, so a class distribution read off the 914
   rows describes the sample, not the frame. Each share is given weighted by
   `sampling_weight`, with the unweighted count beside it.
2. **RQ5, the PyPI trust gate** (§2.4.6), which S3 waits on. File C states it
   in words; the criteria below make it a computation, and were fixed in this
   module before it was first run on the corpus (decisions §15.2).
3. **Dependency count, controlled** (WP-6's sign-off, WP-5's flag). Score
   falls with dependency count by construction — every assessed dependency is
   one more term the roll-up can add — so an ecosystem comparison, or a
   correlation with a reference, that ignores it can be a dependency-count
   comparison in disguise.
4. **The robustness rerun under `v1`** (§2.4.7). WP-6 swept RQ3 under `v2`
   and entropy; `v1` is swept here, and the hypotheses are tabulated under
   both so a conclusion that survives both weightings is marked as such.

**The trust gate's criteria**, as fixed before the first run:

* **G1, the distribution is not degenerate.** Over PyPI-only repositories,
  the scores span at least `G1_MIN_RANGE` points, and every class holds at
  least `G1_MIN_SHARE` of them — unweighted and sampling-weighted.
* **G2, the anchors pass.** Every PyPI known anchor of WP-2's set is at least
  Medium, with the anchor package seen at its version (WP-6's `pass`).
* **G3, the roll-up behaves alike on matched dependency counts.** Repositories
  are put in `STRATA` by assessed-occurrence count. In every stratum holding
  at least `G3_MIN_REPOSITORIES` npm-only *and* PyPI-only repositories, both
  ecosystems populate at least two classes, and their median *tail share*
  differs by at most `G3_MAX_TAIL_GAP`. The tail share is the part of a
  repository's deduction that the roll-up adds beyond its worst dependency —
  `(deduction - top term) / deduction` — so it measures the roll-up itself
  rather than the vector: a PyPI arm whose scores came mostly from the decayed
  tail where npm's came from the worst term would be a roll-up behaving
  differently. And score must fall with dependency count in both ecosystems
  (Spearman rho below zero in each), the shape the roll-up has by design.

The gate passes when all three pass. File C §2.4.6: a pass makes S3's PyPI arm
interpretable; a fail sends the PyPI vector back through WP-6's path before S3.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from apps.scoring.engine import roll_up
from apps.scoring.weights import WeightSet

from . import stats
from .panel import MIXED, CorpusPanel, RepoScore, occurrence_penalties, roll_up_panel
from .sensitivity import FlipCount, summarise, sweep

CLASSES: tuple[str, ...] = ("safe", "medium", "high_alert")
GROUPS: tuple[str, ...] = ("all", "npm", "pypi", MIXED)

#: Assessed-occurrence strata for G3 and the dependency-count tables: `(label,
#: low, high)`, both ends inclusive, `None` for open. Roughly geometric, so each
#: holds a comparable share of a corpus whose dependency counts are skewed.
STRATA: tuple[tuple[str, int, int | None], ...] = (
    ("1-5", 1, 5),
    ("6-15", 6, 15),
    ("16-40", 16, 40),
    ("41-100", 41, 100),
    ("101+", 101, None),
)
NO_ASSESSED = "0"

G1_MIN_RANGE = 90.0
G1_MIN_SHARE = 0.10
G3_MIN_REPOSITORIES = 15
G3_MAX_TAIL_GAP = 0.15
G3_MIN_CLASSES = 2

#: File C's hypothesis lines, restated so the table can mark each verdict.
H1_MIN_COSINE = 0.90
H2_BAND = (0.3, 0.6)
H3_MAX_RATE = 0.15


class SupplementError(Exception):
    """An input the supplement needs is missing or does not match the panel."""


# ── Inputs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnchorClass:
    """One known anchor as WP-6 recorded it, joined to WP-2's ecosystem column."""

    repo_url: str
    ecosystem: str
    package: str
    seen: bool
    classes: dict[str, str]


@dataclass(frozen=True)
class Inputs:
    panel: CorpusPanel
    #: Repository full name -> deps.dev Scorecard (0-10), for those WP-6 found.
    scorecards: dict[str, float]
    anchors: list[AnchorClass]
    #: The signed report's own numbers for RQ1 and RQ2, read rather than
    #: recomputed: they are WP-6's, and the hypotheses table cites them.
    rq1: dict[tuple[str, str], dict[str, float]]
    rq2: dict[str, dict[str, float | None]]
    #: WP-6's RQ3 sweep of `v2`, as signed.
    sensitivity_v2: list[dict]


#: The signed report's name for `v2` (decisions §12.19: the candidate became
#: `v2` with only its derivation tag changed).
SIGNED_NAMES = {"v1": "v1", "v2": "v2-candidate (AHP)"}


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        raise SupplementError(f"{path.name} is not in {path.parent}.")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_inputs(export: Path, panel: CorpusPanel) -> Inputs:
    """Everything the supplement reads, from an export folder."""
    report = export / "validation_report"
    names = {repository.full_name for repository in panel.repositories}

    scorecards: dict[str, float] = {}
    for row in _rows(report / "scores.csv"):
        if row["repository"] not in names:
            raise SupplementError(
                f"{row['repository']} is in scores.csv but not in the panel."
            )
        if row.get("scorecard_status") == "ok" and row.get("scorecard"):
            scorecards[row["repository"]] = float(row["scorecard"])

    ecosystems = {
        row["repo_url"]: row["ecosystem"].strip().lower()
        for row in _rows(export / "anchors" / "wp2_anchor_set.csv")
    }
    anchors = [
        AnchorClass(
            repo_url=row["repo_url"],
            ecosystem=ecosystems.get(row["repo_url"], ""),
            package=row["anchor_package"],
            seen=row.get("anchor_seen") == "True",
            classes={
                version: row.get(f"class_{signed}", "")
                for version, signed in SIGNED_NAMES.items()
            },
        )
        for row in _rows(report / "anchors.csv")
        if row["is_known_anchor"] == "True"
    ]

    vectors = {
        (row["formula"], row["ecosystem"]): {
            signal: float(row[signal])
            for signal in ("deprecation", "severity", "count", "staleness")
        }
        for row in _rows(report / "weights_comparison.csv")
        if row["ecosystem"]
    }
    rq2: dict[str, dict[str, float | None]] = {}
    for row in _rows(report / "correlation.csv"):
        if (
            row["reference"] == "scorecard"
            and row["group"] == "all"
            and row["method"] == "spearman"
            and row["weighted"] == "False"
        ):
            rq2[row["formula"]] = {
                "value": _number(row["value"]),
                "low": _number(row["ci_low"]),
                "high": _number(row["ci_high"]),
                "covered": float(row["covered"]),
            }
    return Inputs(
        panel=panel,
        scorecards=scorecards,
        anchors=anchors,
        rq1=vectors,
        rq2=rq2,
        sensitivity_v2=[
            row
            for row in _rows(report / "sensitivity.csv")
            if row["formula"] == SIGNED_NAMES["v2"]
        ],
    )


def _number(text: str) -> float | None:
    return float(text) if text not in ("", None) else None


# ── Per-repository facts under one weighting ──────────────────────────────


@dataclass(frozen=True)
class RepoFacts:
    full_name: str
    ecosystem: str
    weight: float
    score: float
    classification: str
    assessed: int
    deduction: float
    top_term: float

    @property
    def tail_share(self) -> float | None:
        """The share of the deduction the roll-up adds beyond the worst term."""
        if self.deduction <= 0:
            return None
        return (self.deduction - self.top_term) / self.deduction

    @property
    def stratum(self) -> str:
        return stratum_of(self.assessed)


def stratum_of(assessed: int) -> str:
    for label, low, high in STRATA:
        if assessed >= low and (high is None or assessed <= high):
            return label
    return NO_ASSESSED


def facts(panel: CorpusPanel, weights: WeightSet) -> list[RepoFacts]:
    """Every repository's score, class, count and roll-up shape under `weights`."""
    penalties = occurrence_penalties(panel, weights)
    scored: list[RepoScore] = roll_up_panel(panel, penalties, weights)
    out: list[RepoFacts] = []
    for score, (repo_penalties, _flagged) in zip(scored, penalties, strict=True):
        result = roll_up(repo_penalties, weights)
        top = result.contributions[0].points if result.contributions else Decimal(0)
        out.append(
            RepoFacts(
                full_name=score.repository.full_name,
                ecosystem=score.repository.ecosystem,
                weight=score.repository.weight,
                score=float(score.score),
                classification=score.classification,
                assessed=score.assessed,
                deduction=float(result.deduction),
                top_term=float(top),
            )
        )
    return out


def _in_group(rows: Sequence[RepoFacts], group: str) -> list[RepoFacts]:
    return list(rows) if group == "all" else [r for r in rows if r.ecosystem == group]


# ── 1. Sampling-weighted class shares (§1.3) ──────────────────────────────


@dataclass(frozen=True)
class ClassShare:
    version: str
    group: str
    classification: str
    repositories: int
    of: int
    share: float
    weighted_share: float


def class_shares(version: str, rows: Sequence[RepoFacts]) -> list[ClassShare]:
    out: list[ClassShare] = []
    for group in GROUPS:
        members = _in_group(rows, group)
        if not members:
            continue
        total_weight = sum(r.weight for r in members)
        for name in CLASSES:
            inside = [r for r in members if r.classification == name]
            out.append(
                ClassShare(
                    version=version,
                    group=group,
                    classification=name,
                    repositories=len(inside),
                    of=len(members),
                    share=len(inside) / len(members),
                    weighted_share=(
                        sum(r.weight for r in inside) / total_weight
                        if total_weight
                        else 0.0
                    ),
                )
            )
    return out


# ── 2. Dependency-count strata ────────────────────────────────────────────


@dataclass(frozen=True)
class StratumRow:
    version: str
    stratum: str
    ecosystem: str
    repositories: int
    shares: dict[str, float]
    weighted_shares: dict[str, float]
    median_score: float | None
    median_tail_share: float | None

    @property
    def classes_populated(self) -> int:
        return sum(1 for share in self.shares.values() if share > 0)


def strata_table(version: str, rows: Sequence[RepoFacts]) -> list[StratumRow]:
    labels = [NO_ASSESSED, *(label for label, _, _ in STRATA)]
    out: list[StratumRow] = []
    for label in labels:
        for ecosystem in ("npm", "pypi"):
            members = [r for r in rows if r.stratum == label and r.ecosystem == ecosystem]
            total_weight = sum(r.weight for r in members)
            tails = [r.tail_share for r in members if r.tail_share is not None]
            out.append(
                StratumRow(
                    version=version,
                    stratum=label,
                    ecosystem=ecosystem,
                    repositories=len(members),
                    shares={
                        name: (
                            sum(1 for r in members if r.classification == name)
                            / len(members)
                            if members
                            else 0.0
                        )
                        for name in CLASSES
                    },
                    weighted_shares={
                        name: (
                            sum(r.weight for r in members if r.classification == name)
                            / total_weight
                            if total_weight
                            else 0.0
                        )
                        for name in CLASSES
                    },
                    median_score=(
                        statistics.median(r.score for r in members) if members else None
                    ),
                    median_tail_share=statistics.median(tails) if tails else None,
                )
            )
    return out


# ── 3. Correlations, with dependency count controlled ─────────────────────


@dataclass(frozen=True)
class Correlation:
    version: str
    statistic: str
    group: str
    n: int
    value: float | None
    low: float | None
    high: float | None


def partial_spearman(
    x: Sequence[float], y: Sequence[float], z: Sequence[float]
) -> float | None:
    """Spearman's rho of x and y with z partialled out of both, on ranks.

    The first-order partial correlation formula applied to rank correlations:
    `(r_xy - r_xz*r_yz) / sqrt((1 - r_xz^2)(1 - r_yz^2))`. None when any of the
    three is undefined or z explains x or y completely.
    """
    r_xy = stats.spearman(x, y)
    r_xz = stats.spearman(x, z)
    r_yz = stats.spearman(y, z)
    if r_xy is None or r_xz is None or r_yz is None:
        return None
    denominator = ((1 - r_xz**2) * (1 - r_yz**2)) ** 0.5
    if denominator == 0:
        return None
    return max(-1.0, min(1.0, (r_xy - r_xz * r_yz) / denominator))


def _with_interval(
    n: int,
    statistic: Callable[[list[int]], float | None],
    *,
    iterations: int,
    seed: int,
) -> tuple[float | None, float | None, float | None]:
    value = statistic(list(range(n)))
    interval = (
        stats.bootstrap_interval(n, statistic, iterations=iterations, seed=seed)
        if value is not None
        else None
    )
    return value, *(interval if interval else (None, None))


def correlations(
    version: str,
    rows: Sequence[RepoFacts],
    scorecards: dict[str, float],
    *,
    iterations: int,
    seed: int,
) -> list[Correlation]:
    """Score against dependency count, and against Scorecard net of it."""
    out: list[Correlation] = []
    for group in ("all", "npm", "pypi"):
        members = _in_group(rows, group)
        scores = [r.score for r in members]
        counts = [float(r.assessed) for r in members]
        value, low, high = _with_interval(
            len(members),
            lambda sample, s=scores, c=counts: stats.spearman(
                [s[i] for i in sample], [c[i] for i in sample]
            ),
            iterations=iterations,
            seed=seed,
        )
        out.append(
            Correlation(
                version, "rho(score, assessed)", group, len(members), value, low, high
            )
        )

        covered = [r for r in members if r.full_name in scorecards]
        s = [r.score for r in covered]
        ref = [scorecards[r.full_name] for r in covered]
        c = [float(r.assessed) for r in covered]
        for name, statistic in (
            (
                "rho(score, scorecard)",
                lambda sample, s=s, ref=ref: stats.spearman(
                    [s[i] for i in sample], [ref[i] for i in sample]
                ),
            ),
            (
                "partial rho(score, scorecard | assessed)",
                lambda sample, s=s, ref=ref, c=c: partial_spearman(
                    [s[i] for i in sample],
                    [ref[i] for i in sample],
                    [c[i] for i in sample],
                ),
            ),
            (
                "rho(scorecard, assessed)",
                lambda sample, ref=ref, c=c: stats.spearman(
                    [ref[i] for i in sample], [c[i] for i in sample]
                ),
            ),
        ):
            value, low, high = _with_interval(
                len(covered), statistic, iterations=iterations, seed=seed
            )
            out.append(Correlation(version, name, group, len(covered), value, low, high))
    return out


# ── 4. The PyPI trust gate (RQ5) ──────────────────────────────────────────


@dataclass(frozen=True)
class GateCheck:
    version: str
    part: str
    criterion: str
    observed: str
    passed: bool


def trust_gate(
    version: str,
    rows: Sequence[RepoFacts],
    strata: Sequence[StratumRow],
    anchors: Sequence[AnchorClass],
    rho_by_group: dict[str, float | None],
) -> list[GateCheck]:
    checks: list[GateCheck] = []
    pypi = _in_group(rows, "pypi")

    span = (max(r.score for r in pypi) - min(r.score for r in pypi)) if pypi else 0.0
    checks.append(
        GateCheck(
            version,
            "G1",
            f"PyPI scores span ≥ {G1_MIN_RANGE:.0f} points",
            f"{span:.2f} ({len(pypi)} repositories)",
            span >= G1_MIN_RANGE,
        )
    )
    shares = {
        s.classification: s for s in class_shares(version, pypi) if s.group == "pypi"
    }
    for weighted in (False, True):
        values = {
            name: (shares[name].weighted_share if weighted else shares[name].share)
            if name in shares
            else 0.0
            for name in CLASSES
        }
        checks.append(
            GateCheck(
                version,
                "G1",
                f"every class ≥ {G1_MIN_SHARE:.0%} of PyPI repositories"
                + (" (sampling-weighted)" if weighted else ""),
                " / ".join(f"{name} {values[name]:.1%}" for name in CLASSES),
                bool(pypi) and min(values.values()) >= G1_MIN_SHARE,
            )
        )

    pypi_anchors = [a for a in anchors if a.ecosystem == "pypi"]
    failing = [
        a.repo_url.removeprefix("https://github.com/")
        for a in pypi_anchors
        if not a.seen or a.classes.get(version) not in ("medium", "high_alert")
    ]
    checks.append(
        GateCheck(
            version,
            "G2",
            "every PyPI known anchor ≥ Medium, seen at its version",
            f"{len(pypi_anchors) - len(failing)}/{len(pypi_anchors)}"
            + (f" (failing: {', '.join(failing)})" if failing else ""),
            bool(pypi_anchors) and not failing,
        )
    )

    by_stratum: dict[str, dict[str, StratumRow]] = {}
    for row in strata:
        if row.version == version and row.stratum != NO_ASSESSED:
            by_stratum.setdefault(row.stratum, {})[row.ecosystem] = row
    compared = 0
    for label, _, _ in STRATA:
        pair = by_stratum.get(label, {})
        npm_row, pypi_row = pair.get("npm"), pair.get("pypi")
        if (
            npm_row is None
            or pypi_row is None
            or min(npm_row.repositories, pypi_row.repositories) < G3_MIN_REPOSITORIES
        ):
            continue
        compared += 1
        checks.append(
            GateCheck(
                version,
                "G3",
                f"stratum {label}: both ecosystems populate ≥ {G3_MIN_CLASSES} classes",
                f"npm {npm_row.classes_populated}, PyPI {pypi_row.classes_populated} "
                f"(n {npm_row.repositories} / {pypi_row.repositories})",
                min(npm_row.classes_populated, pypi_row.classes_populated)
                >= G3_MIN_CLASSES,
            )
        )
        gap = (
            abs(npm_row.median_tail_share - pypi_row.median_tail_share)
            if npm_row.median_tail_share is not None
            and pypi_row.median_tail_share is not None
            else None
        )
        checks.append(
            GateCheck(
                version,
                "G3",
                f"stratum {label}: median tail share differs by ≤ {G3_MAX_TAIL_GAP}",
                (
                    f"npm {npm_row.median_tail_share:.3f}, PyPI "
                    f"{pypi_row.median_tail_share:.3f} (gap {gap:.3f})"
                    if gap is not None
                    else "undefined"
                ),
                gap is not None and gap <= G3_MAX_TAIL_GAP,
            )
        )
    checks.append(
        GateCheck(
            version,
            "G3",
            f"at least one stratum with ≥ {G3_MIN_REPOSITORIES} repositories "
            "in each ecosystem",
            f"{compared} of {len(STRATA)} strata compared",
            compared > 0,
        )
    )
    npm_rho, pypi_rho = rho_by_group.get("npm"), rho_by_group.get("pypi")
    checks.append(
        GateCheck(
            version,
            "G3",
            "score falls with assessed count in both ecosystems (rho < 0)",
            f"npm {_fmt(npm_rho)}, PyPI {_fmt(pypi_rho)}",
            npm_rho is not None and pypi_rho is not None and npm_rho < 0 and pypi_rho < 0,
        )
    )
    return checks


def gate_passes(checks: Sequence[GateCheck], version: str) -> bool:
    mine = [check for check in checks if check.version == version]
    return bool(mine) and all(check.passed for check in mine)


def _fmt(value: float | None, places: int = 3) -> str:
    return "—" if value is None else f"{value:.{places}f}"


# ── 5. The hypotheses under both weightings (§2.4.7) ──────────────────────


@dataclass(frozen=True)
class Hypothesis:
    hypothesis: str
    version: str
    observed: str
    supported: bool | None


def _top_two(vector: dict[str, float]) -> set[str]:
    return set(sorted(vector, key=lambda signal: -vector[signal])[:2])


def hypotheses(
    inputs: Inputs,
    sweeps: dict[str, list[FlipCount] | list[dict]],
    gates: Sequence[GateCheck],
) -> list[Hypothesis]:
    out: list[Hypothesis] = []
    for version, signed in SIGNED_NAMES.items():
        parts: list[str] = []
        supported = True
        for ecosystem in ("npm", "pypi"):
            ours = inputs.rq1.get((signed, ecosystem))
            entropy = inputs.rq1.get(("entropy", ecosystem))
            if ours is None or entropy is None:
                supported = False
                parts.append(f"{ecosystem} —")
                continue
            order = list(ours)
            cosine = stats.cosine([ours[s] for s in order], [entropy[s] for s in order])
            same = _top_two(ours) == _top_two(entropy)
            parts.append(
                f"{ecosystem} cosine {_fmt(cosine)}, top two {'same' if same else 'differ'}"
            )
            supported = supported and bool(cosine and cosine >= H1_MIN_COSINE and same)
        out.append(Hypothesis("H1 (AHP ≈ entropy)", version, "; ".join(parts), supported))

        rq2 = inputs.rq2.get(signed)
        if rq2 is None or rq2["value"] is None:
            out.append(Hypothesis("H2 (Scorecard rho in [0.3, 0.6])", version, "—", None))
        else:
            out.append(
                Hypothesis(
                    "H2 (Scorecard rho in [0.3, 0.6])",
                    version,
                    f"rho {_fmt(rq2['value'])} [{_fmt(rq2['low'])}, {_fmt(rq2['high'])}], "
                    f"{rq2['covered']:.0f} repositories",
                    H2_BAND[0] <= rq2["value"] <= H2_BAND[1],
                )
            )

        rate = _max_weight_rate(sweeps.get(version, []))
        out.append(
            Hypothesis(
                "H3 (flips < 15% at ±20%)",
                version,
                f"max {rate:.1%}" if rate is not None else "—",
                None if rate is None else rate < H3_MAX_RATE,
            )
        )

        anchors = inputs.anchors
        passing = [
            a
            for a in anchors
            if a.seen and a.classes.get(version) in ("medium", "high_alert")
        ]
        out.append(
            Hypothesis(
                "H4 (known anchors ≥ Medium)",
                version,
                f"{len(passing)}/{len(anchors)}",
                bool(anchors) and len(passing) == len(anchors),
            )
        )
        out.append(
            Hypothesis(
                "RQ5 trust gate (G1-G3)",
                version,
                "pass" if gate_passes(gates, version) else "fail",
                gate_passes(gates, version),
            )
        )
    return out


def _max_weight_rate(rows) -> float | None:
    rates = []
    for row in rows:
        if isinstance(row, FlipCount):
            if row.parameter.startswith("weight:") and row.magnitude == 20:
                rates.append(row.rate)
        elif (
            row["parameter"].startswith("weight:") and row["change"].strip("+-") == "20%"
        ):
            rates.append(float(row["rate"]))
    return max(rates) if rates else None


# ── The run, and its files ────────────────────────────────────────────────


@dataclass
class Supplement:
    snapshot_date: str
    repositories: int
    seed: int
    iterations: int
    versions: tuple[str, ...]
    shares: list[ClassShare] = field(default_factory=list)
    strata: list[StratumRow] = field(default_factory=list)
    correlations: list[Correlation] = field(default_factory=list)
    gate: list[GateCheck] = field(default_factory=list)
    sweep_v1: list[FlipCount] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    inputs_digest: dict[str, str] = field(default_factory=dict)


def run(
    inputs: Inputs,
    weights: dict[str, WeightSet],
    *,
    seed: int = 42,
    iterations: int = 2000,
    inputs_digest: dict[str, str] | None = None,
) -> Supplement:
    """All four analyses, under every weighting in `weights` (`v1`, `v2`)."""
    result = Supplement(
        snapshot_date=inputs.panel.snapshot_date.isoformat(),
        repositories=len(inputs.panel.repositories),
        seed=seed,
        iterations=iterations,
        versions=tuple(weights),
        inputs_digest=dict(inputs_digest or {}),
    )
    for version, weightset in weights.items():
        rows = facts(inputs.panel, weightset)
        result.shares.extend(class_shares(version, rows))
        strata = strata_table(version, rows)
        result.strata.extend(strata)
        correlations_here = correlations(
            version, rows, inputs.scorecards, iterations=iterations, seed=seed
        )
        result.correlations.extend(correlations_here)
        rho = {
            c.group: c.value
            for c in correlations_here
            if c.statistic == "rho(score, assessed)"
        }
        result.gate.extend(trust_gate(version, rows, strata, inputs.anchors, rho))
    if "v1" in weights:
        result.sweep_v1 = sweep(inputs.panel, weights["v1"], vector="v1")
    result.hypotheses = hypotheses(
        inputs, {"v1": result.sweep_v1, "v2": inputs.sensitivity_v2}, result.gate
    )
    return result


#: The export files the supplement reads. Their digests travel with its output,
#: so a committed copy says which data it was computed from (`same_inputs`).
INPUT_FILES: tuple[str, ...] = (
    "scan_history.parquet",
    "dependency_history.parquet",
    "anchors/wp2_anchor_set.csv",
    "validation_report/anchors.csv",
    "validation_report/correlation.csv",
    "validation_report/scores.csv",
    "validation_report/sensitivity.csv",
    "validation_report/weights_comparison.csv",
)


def input_digests(export: Path) -> dict[str, str]:
    """The sha256 the export's own manifest records for each input file."""
    manifest = json.loads((export / "MANIFEST.json").read_text(encoding="utf-8"))
    recorded = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    missing = [name for name in INPUT_FILES if name not in recorded]
    if missing:
        raise SupplementError(f"The export's manifest lists no {', '.join(missing)}.")
    return {name: recorded[name] for name in INPUT_FILES}


def same_inputs(export: Path, committed: Path) -> bool:
    """Was `committed` computed from the data in `export`?

    A committed copy is the paper's; a regeneration is compared with it only
    when both read the same files, because a different export (the suite's
    synthetic corpus, a future snapshot) is meant to give different numbers.
    """
    recorded = committed / "inputs.json"
    if not recorded.exists():
        return False
    digests = json.loads(recorded.read_text(encoding="utf-8")).get("inputs", {})
    return digests == input_digests(export)


FILES: tuple[str, ...] = (
    "inputs.json",
    "supplement.md",
    "class_shares.csv",
    "dependency_strata.csv",
    "correlations.csv",
    "trust_gate.csv",
    "sensitivity_v1.csv",
    "hypotheses.csv",
)


def _write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def write(result: Supplement, out: Path) -> list[Path]:
    """The tables as CSV, and `supplement.md` for the paper's reader."""
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(
        out / "class_shares.csv",
        ["version", "group", "class", "repositories", "of", "share", "weighted_share"],
        [
            [
                s.version,
                s.group,
                s.classification,
                s.repositories,
                s.of,
                _cell(s.share),
                _cell(s.weighted_share),
            ]
            for s in result.shares
        ],
    )
    _write_csv(
        out / "dependency_strata.csv",
        ["version", "stratum", "ecosystem", "repositories"]
        + [f"share_{name}" for name in CLASSES]
        + [f"weighted_share_{name}" for name in CLASSES]
        + ["median_score", "median_tail_share"],
        [
            [r.version, r.stratum, r.ecosystem, r.repositories]
            + [_cell(r.shares[name]) for name in CLASSES]
            + [_cell(r.weighted_shares[name]) for name in CLASSES]
            + [_cell(r.median_score), _cell(r.median_tail_share)]
            for r in result.strata
        ],
    )
    _write_csv(
        out / "correlations.csv",
        ["version", "statistic", "group", "n", "value", "ci_low", "ci_high"],
        [
            [
                c.version,
                c.statistic,
                c.group,
                c.n,
                _cell(c.value),
                _cell(c.low),
                _cell(c.high),
            ]
            for c in result.correlations
        ],
    )
    _write_csv(
        out / "trust_gate.csv",
        ["version", "part", "criterion", "observed", "passed"],
        [[g.version, g.part, g.criterion, g.observed, g.passed] for g in result.gate],
    )
    _write_csv(
        out / "sensitivity_v1.csv",
        [
            "formula",
            "parameter",
            "change",
            "flips",
            "repositories",
            "rate",
            "by_ecosystem",
        ],
        [
            [
                f.vector,
                f.parameter,
                f.change,
                f.flips,
                f.repositories,
                _cell(f.rate),
                json.dumps({k: list(v) for k, v in sorted(f.by_ecosystem.items())}),
            ]
            for f in result.sweep_v1
        ],
    )
    _write_csv(
        out / "hypotheses.csv",
        ["hypothesis", "version", "observed", "supported"],
        [[h.hypothesis, h.version, h.observed, h.supported] for h in result.hypotheses],
    )
    (out / "inputs.json").write_text(
        json.dumps(
            {
                "snapshot_date": result.snapshot_date,
                "repositories": result.repositories,
                "versions": list(result.versions),
                "seed": result.seed,
                "bootstrap": result.iterations,
                "inputs": result.inputs_digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "supplement.md").write_text(render(result), encoding="utf-8")
    return [out / name for name in FILES]


def render(result: Supplement) -> str:
    lines = [
        "# S1 supplementary analyses",
        "",
        "Generated by `apps.research.validation.supplement` from the replication "
        f"export: corpus snapshot `{result.snapshot_date}`, {result.repositories} "
        f"repositories, seed {result.seed}, {result.iterations} bootstrap resamples "
        "of repositories. Every score is recomputed from stored signals (D6, File C "
        "§1.1). Population shares are sampling-weighted, with unweighted counts "
        "beside them (§1.3).",
        "",
    ]
    if result.inputs_digest:
        lines += ["| Input | sha256 |", "|---|---|"]
        lines += [
            f"| `{name}` | `{digest[:16]}…` |"
            for name, digest in sorted(result.inputs_digest.items())
        ]
        lines.append("")

    lines += [
        "## 1. Hypotheses under both weightings (File C §2.4.7)",
        "",
        "H1, H2 and H4 read WP-6's signed numbers; H3 under `v1` and the trust gate "
        "are computed here. A conclusion that holds under both columns survives the "
        "reweighting.",
        "",
        "| Hypothesis | " + " | ".join(f"`{v}`" for v in result.versions) + " |",
        "|---|" + "---|" * len(result.versions),
    ]
    names = list(dict.fromkeys(h.hypothesis for h in result.hypotheses))
    for name in names:
        cells = []
        for version in result.versions:
            match = next(
                (
                    h
                    for h in result.hypotheses
                    if h.hypothesis == name and h.version == version
                ),
                None,
            )
            if match is None:
                cells.append("—")
                continue
            verdict = {True: "supported", False: "**not supported**", None: "n/a"}[
                match.supported
            ]
            if name.startswith("RQ5"):
                verdict = {True: "**pass**", False: "**fail**", None: "n/a"}[
                    match.supported
                ]
                cells.append(verdict)
            else:
                cells.append(f"{verdict}: {match.observed}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## 2. RQ5: the PyPI trust gate (File C §2.4.6)",
        "",
        f"Criteria fixed in `supplement.py` before its first run: G1 range ≥ "
        f"{G1_MIN_RANGE:.0f} and every class ≥ {G1_MIN_SHARE:.0%}; G2 every PyPI "
        f"known anchor ≥ Medium; G3 in strata with ≥ {G3_MIN_REPOSITORIES} "
        f"repositories per ecosystem, ≥ {G3_MIN_CLASSES} classes each and median "
        f"tail shares within {G3_MAX_TAIL_GAP}, and score falling with dependency "
        "count in both ecosystems. The tail share is `(deduction - worst term) / "
        "deduction`: how much of a score the roll-up's decayed tail decides.",
        "",
    ]
    for version in result.versions:
        verdict = "PASS" if gate_passes(result.gate, version) else "FAIL"
        lines += [
            f"### `{version}`: **{verdict}**",
            "",
            "| Part | Criterion | Observed | |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {g.part} | {g.criterion} | {g.observed} | {'ok' if g.passed else '**fail**'} |"
            for g in result.gate
            if g.version == version
        ]
        lines.append("")

    lines += [
        "## 3. The corpus, sampling-weighted (File C §1.3)",
        "",
        "Weighted share (unweighted count of the group). `mixed` repositories hold "
        "manifests of both ecosystems.",
        "",
        "| Weights | Group | Safe | Medium | High alert |",
        "|---|---|---|---|---|",
    ]
    for version in result.versions:
        for group in GROUPS:
            row = {
                s.classification: s
                for s in result.shares
                if s.version == version and s.group == group
            }
            if not row:
                continue
            lines.append(
                f"| `{version}` | {group} (n {row['safe'].of}) | "
                + " | ".join(
                    f"{row[name].weighted_share:.1%} ({row[name].repositories})"
                    for name in CLASSES
                )
                + " |"
            )

    lines += [
        "",
        "## 4. Dependency count, controlled",
        "",
        "### By assessed-dependency stratum",
        "",
        "Unweighted class shares within a stratum (no reweighting is needed within "
        "one, §1.3), median score, and the median tail share of repositories with a "
        "non-zero deduction.",
        "",
        "| Weights | Stratum | Ecosystem | n | Safe | Medium | High alert | "
        "Median score | Median tail share |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in result.strata:
        if not r.repositories:
            continue
        lines.append(
            f"| `{r.version}` | {r.stratum} | {r.ecosystem} | {r.repositories} | "
            + " | ".join(f"{r.shares[name]:.0%}" for name in CLASSES)
            + f" | {_fmt(r.median_score, 2)} | {_fmt(r.median_tail_share)} |"
        )
    lines += [
        "",
        "### Correlations",
        "",
        "Spearman rho with a 95% percentile bootstrap interval over repositories. The "
        "partial rho removes assessed-dependency count from both the score and the "
        "Scorecard before correlating them: RQ2 with dependency count controlled.",
        "",
        "| Weights | Statistic | Group | n | rho | 95% interval |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| `{c.version}` | {c.statistic} | {c.group} | {c.n} | {_fmt(c.value)} | "
        f"[{_fmt(c.low)}, {_fmt(c.high)}] |"
        for c in result.correlations
    ]

    if result.sweep_v1:
        summary = summarise(result.sweep_v1)
        lines += [
            "",
            "## 5. RQ3 under `v1` (File C §2.4.7)",
            "",
            f"Max weight-perturbation flip rate {summary.max_weight_rate_10:.1%} at "
            f"±10%, {summary.max_weight_rate_20:.1%} at ±20%; max over every "
            f"parameter {summary.max_rate_overall:.1%}"
            + (
                f"; over the 20% discussion line: {', '.join(summary.to_discuss)}."
                if summary.to_discuss
                else "."
            ),
            "",
            "| Parameter | Change | Flips | Rate |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {f.parameter} | {f.change} | {f.flips}/{f.repositories} | {f.rate:.1%} |"
            for f in result.sweep_v1
        ]
    lines.append("")
    return "\n".join(lines)
