"""`validate_formula`, end to end: one command, S1's whole results section.

§10 Phase 12's acceptance: "`validate_formula` runs end-to-end on the WP-5 data
in one command". File B's WP-6 types exactly one:

    python manage.py validate_formula --ahp wp3_matrix_reconciled.csv --anchors wp2_anchor_set.csv

**The order is the order a refusal should happen in.** The AHP gate runs first
and stops everything if the reconciled matrix is incoherent (File B: "a
refusal is a WP-3 revisit, not a tweak") — there is no point fetching a
thousand Scorecards to validate weights that are about to be re-judged. The
corpus is loaded and its stored scores reproduced next, because every later
number is a recomputation and D6's identity is what licenses it. Only then
does anything touch the network.

**Three formulas are carried through every analysis.** The active file (`v1`,
what the product ships today), the AHP candidate for `v2` (what WP-6 is
deciding whether to ship), and the entropy vector (the objective
cross-check). They differ only in their per-ecosystem weights — the caps, flag
rule, roll-up and thresholds are the active file's — so every difference in
the report is a difference of weights. The candidate is what the sign-off
checklist is computed for; the other two are beside it so a reader can see
what moved.

**Nothing is written to the database.** The whole run is inside D10's guard,
and the only outputs are files under `--out`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from apps.research.github import ResearchClient
from apps.scoring.normalize import SIGNAL_NAMES
from apps.scoring.weights import WeightSet, active_weights, load_weights

from . import agree, ahp, anchors, candidates, entropy, reference, sensitivity
from .panel import (
    CorpusPanel,
    RepoScore,
    ReproductionCheck,
    load_panel,
    reproduction_check,
    score_panel,
)

logger = logging.getLogger(__name__)

ECOSYSTEMS: tuple[str, ...] = ("npm", "pypi")

#: The derivation tag the candidate file carries until WP-6 signs it off. §5.4
#: names `ahp-entropy-validated` for `v2`; writing that before the validation
#: has been read and signed would be the claim the 2026-09-24 review bounced
#: the teammate's draft for making.
CANDIDATE_DERIVATION = "ahp-candidate-pending-wp6"

CANDIDATE = "v2-candidate (AHP)"
ENTROPY = "entropy"

SCORECARD = "scorecard"
OSV = "osv_rollup"


class ValidationError(Exception):
    """An input the harness cannot proceed from; the message says which."""


@dataclass(frozen=True)
class ValidationInputs:
    ahp_path: Path
    out_dir: Path
    anchors_path: Path | None = None
    snapshot_date: date | None = None
    baseline_version: str | None = None
    pypi_shift: str | None = None
    seed: int = 42
    bootstrap: int = 2000
    skip_reference: bool = False
    rescan_anchors: bool = False
    wait_for_reset: bool = True


@dataclass
class VectorScores:
    label: str
    weights: WeightSet
    scores: list[RepoScore]


@dataclass
class ValidationRun:
    inputs: ValidationInputs
    generated_at: str
    ahp: ahp.AhpResult
    ahp_sha256: str
    baseline: WeightSet
    candidate: WeightSet
    pypi_rule: str
    panel: CorpusPanel
    reproduction: ReproductionCheck
    entropy: dict[str, entropy.EntropyResult]
    entropy_weighted: dict[str, entropy.EntropyResult]
    entropy_weights: WeightSet
    entropy_notes: list[str]
    comparisons: list[entropy.VectorComparison]
    vectors: list[VectorScores]
    scorecards: dict[str, reference.ScorecardReading] | None
    osv_health: dict[str, float]
    agreements: list[agree.Agreement]
    sensitivity: dict[str, list[sensitivity.FlipCount]]
    summaries: dict[str, sensitivity.SweepSummary]
    anchor_rows: list[anchors.AnchorRow] = field(default_factory=list)
    anchor_scan: dict | None = None
    anchor_sha256: str | None = None
    anchor_results: dict[str, list[anchors.AnchorResult]] = field(default_factory=dict)
    anchor_checks: list[anchors.SetCheck] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)

    def vector(self, label: str) -> VectorScores:
        for found in self.vectors:
            if found.label == label:
                return found
        raise KeyError(label)


def _say(progress, message: str) -> None:
    if progress is not None:
        progress(message)


def gate_matrix(path: Path) -> ahp.AhpResult:
    """Read the reconciled matrix and refuse it unless it is coherent and Tier-1."""
    result = ahp.evaluate(ahp.read_matrix(path))
    ahp.require_consistent(result)
    if set(result.matrix.signals) != set(SIGNAL_NAMES):
        raise ValidationError(
            f"{result.matrix.source} compares {', '.join(result.matrix.labels)}. The "
            f"weights file is D3's four Tier-1 signals ({', '.join(SIGNAL_NAMES)}); "
            f"a 5x5 EPSS matrix is WP-3's optional research variant and is checked "
            f"with `ahp_check`, not validated here."
        )
    return result


def build_candidate(
    result: ahp.AhpResult, baseline: WeightSet, shift_text: str | None
) -> tuple[WeightSet, str]:
    npm = result.weight_vector()
    shift = candidates.parse_shift(shift_text)
    if shift:
        pypi = candidates.apply_shift(npm, shift)
        rule = (
            "PyPI vector = the AHP vector shifted by "
            + ", ".join(f"{signal} {value:+.4f}" for signal, value in shift.items())
            + " (--pypi-shift; File C limitation L4: reasoned redistribution in the "
            "same session, not an independent calibration)."
        )
    else:
        pypi = dict(npm)
        rule = (
            "PyPI vector = the npm (AHP) vector, unchanged: no --pypi-shift was "
            "given. WP-1 lowered PyPI's deprecation weight on the grounds that its "
            "deprecation signal carries less information (D2); if WP-3's notes "
            "state a PyPI rule, re-run with it."
        )
    candidate = candidates.weightset_from(
        baseline,
        {"npm": npm, "pypi": pypi},
        version="v2",
        derivation=CANDIDATE_DERIVATION,
    )
    return candidate, rule


def run_validation(
    inputs: ValidationInputs,
    *,
    client_factory=None,
    depsdev: reference.DepsDevClient | None = None,
    progress=None,
) -> ValidationRun:
    """Everything §10 Phase 12 asks the harness to compute, in refusal order."""
    _say(progress, f"AHP: {inputs.ahp_path}")
    result = gate_matrix(inputs.ahp_path)

    baseline = (
        load_weights(inputs.baseline_version)
        if inputs.baseline_version
        else active_weights()
    )
    candidate, pypi_rule = build_candidate(result, baseline, inputs.pypi_shift)

    panel = load_panel(inputs.snapshot_date)
    _say(
        progress,
        f"corpus: {len(panel.repositories)} repositories, {panel.occurrence_count} "
        f"occurrences as of {panel.snapshot_date}",
    )
    reproduction = reproduction_check(panel, load_weights)
    if reproduction.checked and not reproduction.all_match:
        _say(
            progress,
            f"WARNING: {reproduction.checked - reproduction.matched} stored score(s) "
            f"do not reproduce under their own version",
        )

    # ── RQ1: entropy, and its comparison with AHP ──
    entropy_results: dict[str, entropy.EntropyResult] = {}
    entropy_weighted: dict[str, entropy.EntropyResult] = {}
    entropy_vectors: dict[str, dict[str, float]] = {}
    notes: list[str] = []
    for ecosystem in ECOSYSTEMS:
        found = entropy.entropy_weights(
            panel, baseline, ecosystem, bootstrap=inputs.bootstrap, seed=inputs.seed
        )
        entropy_results[ecosystem] = found
        entropy_weighted[ecosystem] = entropy.entropy_weights(
            panel, baseline, ecosystem, sampling_weighted=True
        )
        if found.degenerate:
            notes.append(
                f"No signal varies across the {ecosystem} occurrences, so there is no "
                f"entropy vector for {ecosystem}; the entropy formula uses the AHP "
                f"vector there and every {ecosystem} entropy figure below is undefined."
            )
            entropy_vectors[ecosystem] = {
                signal: float(weight)
                for signal, weight in candidate.weights[ecosystem].items()
            }
        else:
            entropy_vectors[ecosystem] = found.vector()
    entropy_weights = candidates.weightset_from(
        baseline, entropy_vectors, version="entropy", derivation="entropy"
    )

    comparisons: list[entropy.VectorComparison] = []
    for ecosystem in ECOSYSTEMS:
        if entropy_results[ecosystem].degenerate:
            continue
        for label, weights in ((CANDIDATE, candidate), (baseline.version, baseline)):
            comparisons.append(
                entropy.compare_vectors(
                    {s: float(w) for s, w in weights.weights[ecosystem].items()},
                    entropy_vectors[ecosystem],
                    first_name=f"{label} [{ecosystem}]",
                    second_name=f"{ENTROPY} [{ecosystem}]",
                )
            )

    # ── scores under the three formulas ──
    vectors = [
        VectorScores(baseline.version, baseline, score_panel(panel, baseline)),
        VectorScores(CANDIDATE, candidate, score_panel(panel, candidate)),
        VectorScores(ENTROPY, entropy_weights, score_panel(panel, entropy_weights)),
    ]

    # ── RQ2: the references ──
    names = [repository.full_name for repository in panel.repositories]
    osv_health = {
        repository.full_name: reference.osv_health(repository)
        for repository in panel.repositories
    }
    scorecards: dict[str, reference.ScorecardReading] | None = None
    if not inputs.skip_reference:
        _say(progress, f"deps.dev: Scorecard for {len(names)} repositories (cached)")
        inputs.out_dir.mkdir(parents=True, exist_ok=True)
        scorecards = reference.fetch_scorecards(
            names,
            inputs.out_dir / reference.CACHE_FILENAME,
            depsdev,
            progress=progress,
        )

    references: list[tuple[str, dict[str, float | None]]] = []
    if scorecards is not None:
        references.append(
            (SCORECARD, {name: reading.score for name, reading in scorecards.items()})
        )
    references.append((OSV, dict(osv_health)))

    agreements: list[agree.Agreement] = []
    for scored in vectors:
        for reference_name, values in references:
            agreements.extend(
                agree.by_group(
                    scored.scores,
                    values,
                    vector=scored.label,
                    reference=reference_name,
                    bootstrap=inputs.bootstrap,
                    seed=inputs.seed,
                )
            )

    # ── RQ3: both vectors, one parameter at a time ──
    _say(progress, "sensitivity: sweeping both vectors")
    flips = {
        CANDIDATE: sensitivity.sweep(panel, candidate, vector=CANDIDATE),
        ENTROPY: sensitivity.sweep(panel, entropy_weights, vector=ENTROPY),
    }
    summaries = {label: sensitivity.summarise(rows) for label, rows in flips.items()}

    run = ValidationRun(
        inputs=inputs,
        generated_at=datetime.now(UTC).isoformat(),
        ahp=result,
        ahp_sha256=anchors.file_digest(inputs.ahp_path),
        baseline=baseline,
        candidate=candidate,
        pypi_rule=pypi_rule,
        panel=panel,
        reproduction=reproduction,
        entropy=entropy_results,
        entropy_weighted=entropy_weighted,
        entropy_weights=entropy_weights,
        entropy_notes=notes,
        comparisons=comparisons,
        vectors=vectors,
        scorecards=scorecards,
        osv_health=osv_health,
        agreements=agreements,
        sensitivity=flips,
        summaries=summaries,
    )

    # ── RQ4: the anchors ──
    if inputs.anchors_path is not None:
        run.anchor_rows = anchors.read_anchor_set(inputs.anchors_path)
        run.anchor_sha256 = anchors.file_digest(inputs.anchors_path)
        directory = inputs.out_dir / "anchors"
        scan = (
            None
            if inputs.rescan_anchors
            else anchors.load_scan(directory / anchors.SCAN_FILENAME)
        )
        if scan is not None and scan.get("anchor_set_sha256") != run.anchor_sha256:
            _say(
                progress,
                "anchors: the saved scan is of a different anchor set; rescanning",
            )
            scan = None
        if scan is None:
            factory = client_factory or ResearchClient.from_settings
            client = factory(wait_for_reset=inputs.wait_for_reset)
            _say(progress, f"anchors: scanning {len(run.anchor_rows)} repositories")
            scan = anchors.scan_anchor_set(
                run.anchor_rows,
                client,
                directory,
                source=inputs.anchors_path,
                progress=progress,
            )
        else:
            _say(progress, f"anchors: reusing the scan of {scan.get('scanned_at')}")
        run.anchor_scan = scan
        run.anchor_results = {
            CANDIDATE: anchors.evaluate(run.anchor_rows, scan, candidate),
            baseline.version: anchors.evaluate(run.anchor_rows, scan, baseline),
        }
        run.anchor_checks = anchors.anchor_set_checks(run.anchor_rows, scan)

    return run
