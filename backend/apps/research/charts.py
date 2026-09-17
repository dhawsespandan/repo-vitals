"""`corpus_report`'s figures — S1's descriptive statistics, and the demo artefact.

§10 Phase 11 asks for two: "score histogram per ecosystem + flagged-rate by
stratum". Both are read from the research database's `corpus_scan` rows and
joined to their strata through `corpus_manifest.json`, because the stratum a
repository was drawn from is a property of the *frame*, not of the scan — and
putting it in a database column would mean `scan_history` carried a field that
only ever applies to one of its two data sources.

**The figures are where WP-5's hardest review question is answered.** File B
asks the teammate to confirm the score distribution *spreads*: "a corpus where
almost everything lands in one class would be useless for weight derivation,
and itself worth flagging". A number cannot make that judgement and a
histogram can, which is why this exists at all rather than being three lines
in the completion report.

**matplotlib is imported inside the function and is not a runtime dependency.**
It is declared in `requirements-research.txt`, which Render never installs:
§8's 512 MB tier holds Django, the scan threads and fastembed's ONNX model, and
matplotlib plus NumPy is ~50 MB of import that no request path would ever use.
The import is inside `render_figures` so that this module — and the command
that owns it — loads on a machine without it and says what to install.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from apps.scoring.weights import WeightsError, WeightSet, active_weights, load_weights

from .models import DataSource, DependencyHistory, ScanHistory

logger = logging.getLogger(__name__)

#: §5.3's bands, and the colours the product's own badge uses for them. Kept
#: here rather than derived from the weights file because a figure is read
#: beside the product, and a band boundary that moved would need the figure
#: regenerated anyway.
CLASS_ORDER: tuple[str, ...] = ("safe", "medium", "high_alert")
CLASS_LABELS: dict[str, str] = {
    "safe": "Safe (>=80)",
    "medium": "Medium (50-79)",
    "high_alert": "High alert (<50)",
}

HISTOGRAM_FILENAME = "score_histogram.png"
FLAGGED_RATE_FILENAME = "flagged_rate_by_stratum.png"
SUMMARY_FILENAME = "corpus_report.md"

#: 0-100 in fives. Twenty bins over a thousand repositories is enough to show
#: the shape without showing the noise, and the boundaries land on §5.3's
#: thresholds (50 and 80) rather than straddling them.
HISTOGRAM_BINS = 20


class ChartsUnavailable(Exception):
    """matplotlib is not installed. Research-only, and deliberately so."""


@dataclass
class Stratum:
    """One cell's scanned repositories, as the figures need them."""

    key: str
    ecosystem: str
    pushed: str
    scores: list[float] = field(default_factory=list)
    flagged_occurrences: int = 0
    occurrences: int = 0

    @property
    def flagged_rate(self) -> float:
        return self.flagged_occurrences / self.occurrences if self.occurrences else 0.0


@dataclass
class CorpusStats:
    snapshot_date: date | None
    scores_by_ecosystem: dict[str, list[float]]
    classification_counts: dict[str, dict[str, int]]
    strata: list[Stratum]
    repositories: int
    occurrences: int
    unassessable: int
    flagged: int
    #: Repositories with a corpus row but no entry in the manifest — a corpus
    #: scanned against a manifest it did not come from. Reported rather than
    #: silently dropped, because it means the two artefacts have drifted.
    unmatched: int


def collect(manifest_path: Path, snapshot_date: date | None = None) -> CorpusStats:
    """Read the corpus rows and join them to their strata.

    `snapshot_date` defaults to the most recent one present, so the common
    case — "chart the run that just finished" — needs no argument, and a
    research database holding two runs charts one of them rather than both
    superimposed.
    """
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame = {
        int(row["github_repo_id"]): row
        for row in document.get("repositories") or []
        if isinstance(row, dict) and row.get("github_repo_id")
    }
    cell_pushed = {
        str(cell.get("key")): str(cell.get("pushed") or "")
        for cell in document.get("cells") or []
        if isinstance(cell, dict)
    }

    rows = ScanHistory.objects.filter(data_source=DataSource.CORPUS_SCAN.value)
    if snapshot_date is None:
        snapshot_date = (
            rows.order_by("-snapshot_date")
            .values_list("snapshot_date", flat=True)
            .first()
        )
    if snapshot_date is not None:
        rows = rows.filter(snapshot_date=snapshot_date)

    scores_by_ecosystem: dict[str, list[float]] = defaultdict(list)
    classification_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: dict.fromkeys(CLASS_ORDER, 0)
    )
    strata: dict[str, Stratum] = {}
    repositories = 0
    unmatched = 0

    flagged_by_scan = _flagged_counts(rows, _weights_for(rows))

    for row in rows.iterator(chunk_size=500):
        repositories += 1
        entry = frame.get(row.github_repo_id)
        if entry is None:
            unmatched += 1
            continue

        # `ecosystems` on the row is what was actually parsed; the manifest's
        # is what the frame sampled for. They differ for a polyglot repository,
        # and the frame's is the right one for a stratum — that is the cell it
        # was drawn from.
        ecosystem = str(entry.get("ecosystem") or row.ecosystems)
        score = float(row.risk_score)
        scores_by_ecosystem[ecosystem].append(score)
        if row.classification in classification_counts[ecosystem]:
            classification_counts[ecosystem][row.classification] += 1

        cell_key = str(entry.get("cell") or "")
        stratum = strata.get(cell_key)
        if stratum is None:
            stratum = Stratum(
                key=cell_key,
                ecosystem=ecosystem,
                pushed=cell_pushed.get(cell_key, _pushed_from_key(cell_key)),
            )
            strata[cell_key] = stratum
        stratum.scores.append(score)
        counts = flagged_by_scan.get(row.pk, (0, 0, 0))
        stratum.occurrences += counts[0]
        stratum.flagged_occurrences += counts[1]

    totals = [0, 0, 0]
    for counts in flagged_by_scan.values():
        totals = [total + value for total, value in zip(totals, counts, strict=True)]

    return CorpusStats(
        snapshot_date=snapshot_date,
        scores_by_ecosystem=dict(scores_by_ecosystem),
        classification_counts={
            ecosystem: dict(counts) for ecosystem, counts in classification_counts.items()
        },
        strata=sorted(strata.values(), key=lambda s: s.key),
        repositories=repositories,
        occurrences=totals[0],
        flagged=totals[1],
        unassessable=totals[2],
        unmatched=unmatched,
    )


def _weights_for(scans) -> WeightSet:
    """The weights the rows being charted were scored under, not today's.

    `signals.weights_for_scan` makes the same argument for the drill-down
    panel: `active_weights()` answers "what would we score with now", which is
    the wrong question when explaining a number that has already been
    computed. A corpus scanned under `v1` and charted after `WEIGHTS_VERSION`
    moved to `v2` would otherwise get a flagged rate computed at a
    `stale_flag_days` no row in the figure was ever measured against.
    """
    # `.order_by()` clears `Meta.ordering` before the DISTINCT. Without it
    # Django has to add `scanned_at` to the select list to satisfy the sort,
    # which makes the DISTINCT two columns wide and returns one row per scan —
    # the Python `set` still answers correctly, over a thousand rows fetched to
    # learn one string.
    versions = set(
        scans.order_by().values_list("scoring_formula_version", flat=True).distinct()
    )
    if len(versions) == 1:
        version = versions.pop()
        try:
            return load_weights(version)
        except WeightsError:
            logger.warning(
                "Corpus rows are tagged weights '%s', which cannot be loaded; "
                "charting the flag rule under the active file instead.",
                version,
            )
    return active_weights()


def _flagged_counts(scans, weights: WeightSet) -> dict:
    """`(occurrences, flagged, unassessable)` per scan, in one query.

    Flagged is recomputed from §5.2's rule rather than read from a column,
    because `dependency_history` has no `is_flagged` and should not: the flag
    is a derived property of the four signals, and D6 keeps derived properties
    out of the permanent record so that a weights revision cannot turn a
    stored boolean into a lie.

    This is §5.2's rule in full — the deprecation, vulnerability and staleness
    clauses — evaluated against `weights.stale_flag_days`. It is not
    `engine.flag_reasons` only because that takes a `Signals` record per row
    and this counts tens of thousands of rows through `values_list`; the
    disjunction is three terms and is asserted against `flag_reasons` in the
    tests rather than trusted to stay in step.
    """
    counts: dict = defaultdict(lambda: [0, 0, 0])
    # `.order_by()` again: `Meta.ordering` would sort forty thousand rows by
    # manifest path and package name for a pass that only counts them.
    rows = (
        DependencyHistory.objects.filter(scan_history__in=scans)
        .order_by()
        .values_list(
            "scan_history_id",
            "is_unassessable",
            "is_deprecated",
            "vulnerability_count",
            "staleness_days",
        )
    )
    for scan_id, unassessable, deprecated, vulnerabilities, staleness in rows.iterator(
        chunk_size=2000
    ):
        entry = counts[scan_id]
        entry[0] += 1
        if unassessable:
            entry[2] += 1
            continue
        stale = staleness is not None and staleness >= weights.stale_flag_days
        if deprecated or (vulnerabilities or 0) > 0 or stale:
            entry[1] += 1
    return {key: tuple(value) for key, value in counts.items()}


def _pushed_from_key(cell_key: str) -> str:
    """The pushed band out of a cell key, for a manifest with no `cells` list."""
    parts = cell_key.split("|")
    return parts[2] if len(parts) > 2 else ""


def render_figures(stats: CorpusStats, out_dir: Path) -> list[Path]:
    """Write §10 Phase 11's two figures. Requires matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")  # No display on a research box or in CI.
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised by absence
        raise ChartsUnavailable(
            "matplotlib is needed for the corpus figures and is not installed. "
            "It is research-only and deliberately absent from the runtime "
            "requirements (§8's 512 MB tier): "
            "`pip install -r requirements-research.txt`."
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # ── score histogram, one panel per ecosystem ──
    ecosystems = sorted(stats.scores_by_ecosystem)
    if ecosystems:
        figure, axes = plt.subplots(
            1, len(ecosystems), figsize=(6 * len(ecosystems), 4.5), squeeze=False
        )
        for axis, ecosystem in zip(axes[0], ecosystems, strict=True):
            scores = stats.scores_by_ecosystem[ecosystem]
            axis.hist(scores, bins=HISTOGRAM_BINS, range=(0, 100), edgecolor="white")
            # §5.3's class boundaries, drawn on the axis rather than described
            # in a caption: a reader judging "does this spread" is really
            # asking whether it spreads *across the bands*.
            for boundary in (50, 80):
                axis.axvline(boundary, linestyle="--", linewidth=1, color="#888")
            axis.set_title(f"{ecosystem} (n={len(scores)})")
            axis.set_xlabel("Repository risk score (0-100)")
            axis.set_ylabel("Repositories")
            axis.set_xlim(0, 100)
        figure.suptitle(
            f"Corpus score distribution, as of {stats.snapshot_date or 'unknown date'} "
            f"- dashed lines are the Safe/Medium/High-alert boundaries"
        )
        figure.tight_layout()
        path = out_dir / HISTOGRAM_FILENAME
        figure.savefig(path, dpi=150)
        plt.close(figure)
        written.append(path)

    # ── flagged rate by stratum ──
    strata = [stratum for stratum in stats.strata if stratum.occurrences]
    if strata:
        figure, axis = plt.subplots(figsize=(max(8, len(strata) * 0.32), 6))
        axis.bar(
            range(len(strata)),
            [stratum.flagged_rate * 100 for stratum in strata],
        )
        axis.set_xticks(range(len(strata)))
        axis.set_xticklabels([stratum.key for stratum in strata], rotation=90, fontsize=6)
        axis.set_ylabel("Flagged occurrences (%)")
        axis.set_title(
            f"Flagged rate by stratum, as of {stats.snapshot_date or 'unknown date'}"
        )
        figure.tight_layout()
        path = out_dir / FLAGGED_RATE_FILENAME
        figure.savefig(path, dpi=150)
        plt.close(figure)
        written.append(path)

    return written


def summary(stats: CorpusStats, figures: list[Path]) -> str:
    """The prose beside the figures — what they show and what they do not."""
    unassessable_rate = (
        stats.unassessable / stats.occurrences if stats.occurrences else 0.0
    )
    flagged_rate = stats.flagged / stats.occurrences if stats.occurrences else 0.0
    lines = [
        "# Corpus descriptive report",
        "",
        "Generated by `manage.py corpus_report` (§10 Phase 11). Reads only",
        "`data_source='corpus_scan'` rows; no product data is in any figure here.",
        "",
        f"- Snapshot date: `{stats.snapshot_date or 'none'}`",
        f"- Repositories: {stats.repositories}",
        f"- Dependency occurrences: {stats.occurrences}",
        f"- Flagged occurrences: {stats.flagged} ({flagged_rate:.1%})",
        f"- Unassessable occurrences: {stats.unassessable} ({unassessable_rate:.1%})",
        f"- Strata with at least one scanned repository: {len(stats.strata)}",
    ]
    if stats.unmatched:
        lines.append(
            f"- **{stats.unmatched} corpus row(s) had no entry in this manifest.** "
            "The database and the manifest describe different runs; check which "
            "corpus was scanned before using these figures."
        )

    lines += [
        "",
        "## Classification split",
        "",
        "| Ecosystem | " + " | ".join(CLASS_LABELS[name] for name in CLASS_ORDER) + " |",
        "|---|" + "---|" * len(CLASS_ORDER),
    ]
    for ecosystem in sorted(stats.classification_counts):
        counts = stats.classification_counts[ecosystem]
        lines.append(
            f"| {ecosystem} | "
            + " | ".join(str(counts.get(name, 0)) for name in CLASS_ORDER)
            + " |"
        )

    lines += ["", "## Figures", ""]
    for path in figures:
        lines.append(f"- `{path.name}`")
    if not figures:
        lines.append("- none: there were no corpus rows to chart.")

    lines += [
        "",
        "## What these figures cannot show",
        "",
        "- The corpus is a **cross-section as of one date** (D14). Nothing here",
        "  is a trend, and a repository appears exactly once.",
        "- The flagged rate is per *occurrence*, not per repository: one",
        "  repository with forty stale packages moves it more than forty",
        "  repositories with one each. That is §5.3's own emphasis, but it makes",
        "  the bars a statement about dependencies rather than about projects.",
        "- Strata are unweighted here. The stale cells are deliberately",
        "  oversampled (D14), so the *shape* of these distributions is the",
        "  corpus's, not GitHub's — apply `sampling_weight` before making any",
        "  claim about the population.",
        "",
    ]
    return "\n".join(lines)
