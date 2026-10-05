"""The Analytic Hierarchy Process: pairwise judgements to a weight vector (WP-3).

§10 Phase 12: "matrix CSV -> principal eigenvector, λ_max, CI, CR (Random Index
table n=3-7: 0.58, 0.90, 1.12, 1.24, 1.32); reject CR >= 0.10 with a report
naming the most-inconsistent judgment triads (actionable revisit);
reconciliation helper: cell-wise divergence report between two matrices +
geometric-mean merge."

This is the headline methodology claim of S1, and the module is written so an
examiner can check every number in it by hand.

**The matrix is the upper triangle.** File B's template, and the 2026-09-24
review, ask each judge to fill the upper triangle and leave the lower one
blank. The lower triangle is then *computed* as exact reciprocals, because a
hand-typed `0.333` is not `1/3` and a matrix that is not exactly reciprocal is
not the matrix the theory is about. A lower triangle that *was* filled in is
checked against the upper one and refused if it contradicts it; one that agrees
to within rounding is accepted, and the report says the exact reciprocals were
used instead.

**The eigenvector is computed by power iteration, in plain floats.** A positive
reciprocal matrix has a unique positive principal eigenvector (Perron), and
repeated multiplication converges to it fast — the second eigenvalue of a
near-consistent matrix is close to zero. Thirty lines of arithmetic anyone can
follow beat a linear-algebra import nobody on the viva panel will open.

**The consistency gate refuses rather than warns.** File B's WP-6 checklist
item 1: "the tool refuses otherwise — a refusal is a WP-3 revisit, not a
tweak". A refusal that only said "CR = 0.14" would invite exactly the random
tweaking File B forbids, so it names the triads whose judgements contradict
each other and the single cells that sit furthest from what the weights imply.
Those are the cells to re-think.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations
from pathlib import Path

#: Saaty's Random Index, the consistency a random matrix of size n would show
#: on average (§10 Phase 12 gives n=3-7). Sizes 1 and 2 are always perfectly
#: consistent — there is no triad to contradict — so their RI is 0 and CR is
#: defined as 0 rather than 0/0.
RANDOM_INDEX: dict[int, float] = {
    1: 0.0,
    2: 0.0,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
}

#: File B Appendix B: below this the judgements are coherent enough for the
#: derived weights to mean something.
CR_THRESHOLD = 0.10

#: Saaty's scale runs 1-9 and its reciprocals. A merged matrix sits between
#: scale points (the geometric mean of 2 and 4 is 2.83), which is fine; a value
#: outside the range is not a judgement anyone could have made.
SAATY_MIN = 1 / 9
SAATY_MAX = 9.0

#: How far a hand-filled lower triangle may sit from the exact reciprocal of
#: the upper one: `|a_ij * a_ji - 1|`. The delivered files of 2026-09-24 typed
#: `0.333` for 1/3, an error of 0.001; anything past 1% is a different judgement.
RECIPROCAL_TOLERANCE = 0.01

#: File B WP-3 step 3: cells where the two judges "diverge by more than 2
#: scale steps" go to the reconciliation meeting.
DIVERGENCE_STEPS = 2

#: Power-iteration stopping rule. Each weight is a number around 0.1-0.5, so a
#: change below this is far under the three decimals any report prints.
CONVERGENCE = 1e-14
MAX_ITERATIONS = 10_000

#: The labels File B's template uses, mapped onto the signal names the weights
#: registry uses (`apps.scoring.normalize.SIGNAL_NAMES`). EPSS is here for WP-3
#: step 4's optional 5x5 variant.
SIGNAL_LABELS: dict[str, str] = {
    "deprecation": "deprecation",
    "severity": "severity",
    "count": "count",
    "staleness": "staleness",
    "epss": "epss",
}


class MatrixError(Exception):
    """A matrix file that cannot be read as a reciprocal pairwise matrix.

    The message names the file and the cell, because the person reading it is
    the judge who typed the file and the fix is always "change this cell".
    """


# ── reading ────────────────────────────────────────────────────────────────


def parse_value(text: str) -> float | None:
    """One cell: `3`, `1/3`, `0.25`, `2.8284`. Blank is None.

    `Fraction` rather than `float` first, so `1/3` is read as the fraction it
    is written as — and so a value like `1/0` or `abc` fails here, with the
    cell's position attached by the caller, rather than deep in the arithmetic.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        value = float(Fraction(raw))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{raw!r} is not a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{raw!r} is not a positive number")
    return value


def format_value(value: float) -> str:
    """A judgement as a person would write it: `3`, `1/3`, `2.83`."""
    if abs(value - 1) < 1e-9:
        return "1"
    if value >= 1:
        rounded = round(value)
        if abs(value - rounded) < 1e-9:
            return str(rounded)
        return f"{value:.2f}"
    inverse = 1 / value
    rounded = round(inverse)
    if abs(inverse - rounded) < 1e-9:
        return f"1/{rounded}"
    return f"{value:.3f}"


def _on_saaty_scale(value: float) -> bool:
    inverse = 1 / value
    return any(
        abs(value - point) < 1e-9 or abs(inverse - point) < 1e-9 for point in range(1, 10)
    )


@dataclass(frozen=True)
class PairwiseMatrix:
    """A reciprocal pairwise comparison matrix, as it will be computed on.

    `labels` are as written in the file; `signals` are the same, lower-cased
    onto the weights registry's names where they match one. `values[i][j]` is
    how much more important `labels[i]` is than `labels[j]`.
    """

    labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]
    source: str = ""
    #: Things the reader should know that are not errors: comment lines that
    #: were skipped, a lower triangle that was typed rather than left blank,
    #: values off Saaty's scale.
    notes: tuple[str, ...] = field(default=())

    @property
    def n(self) -> int:
        return len(self.labels)

    @property
    def signals(self) -> tuple[str, ...]:
        return tuple(_signal_key(label) for label in self.labels)

    def value(self, row: str, column: str) -> float:
        keys = self.signals
        return self.values[keys.index(_signal_key(row))][keys.index(_signal_key(column))]

    def upper_cells(self) -> list[tuple[int, int]]:
        return [(i, j) for i in range(self.n) for j in range(i + 1, self.n)]


def _signal_key(label: str) -> str:
    key = label.strip().lower()
    return SIGNAL_LABELS.get(key, key)


def read_matrix(path: Path) -> PairwiseMatrix:
    """Read one `wp3_matrix_X.csv`, or refuse with the file and cell named."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise MatrixError(f"No matrix file at {path}.") from exc
    return parse_matrix(text, source=Path(path).name)


def parse_matrix(text: str, *, source: str = "matrix") -> PairwiseMatrix:
    """Parse File B's template: header, then one row per signal, upper triangle filled.

    Comment lines (`#`) and blank lines are skipped and noted. The review of
    2026-09-24 asked for files without them, but refusing a file over a comment
    would be refusing the judgement over its packaging.
    """
    notes: list[str] = []
    kept: list[str] = []
    skipped_comments = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            skipped_comments += 1
            continue
        kept.append(line)
    if skipped_comments:
        notes.append(
            f"{skipped_comments} comment line(s) were ignored; only the CSV grid is read."
        )

    rows = list(csv.reader(io.StringIO("\n".join(kept))))
    if len(rows) < 3:
        raise MatrixError(
            f"{source}: expected a header row and at least two signal rows; "
            f"found {len(rows)} row(s)."
        )

    header = [cell.strip() for cell in rows[0]]
    labels = tuple(cell for cell in header[1:] if cell)
    n = len(labels)
    if n < 2:
        raise MatrixError(f"{source}: the header names {n} signal(s); need at least 2.")
    if len({_signal_key(label) for label in labels}) != n:
        raise MatrixError(f"{source}: the header names a signal twice: {labels}.")
    if n not in RANDOM_INDEX:
        raise MatrixError(
            f"{source}: {n} signals is outside Saaty's Random Index table "
            f"(sizes {min(RANDOM_INDEX)}-{max(RANDOM_INDEX)})."
        )

    body = rows[1:]
    if len(body) != n:
        raise MatrixError(
            f"{source}: the header names {n} signals but there are {len(body)} "
            f"data rows. A pairwise matrix is square."
        )

    raw: list[list[float | None]] = []
    for i, row in enumerate(body):
        label = (row[0] if row else "").strip()
        if _signal_key(label) != _signal_key(labels[i]):
            raise MatrixError(
                f"{source}: row {i + 1} is labelled {label!r} but column "
                f"{i + 1} is {labels[i]!r}. Rows must be in the same order as "
                f"the header."
            )
        cells = list(row[1:])
        # A trailing comma or two is how spreadsheets write blank cells; more
        # cells than signals is a different matrix.
        while len(cells) > n and not cells[-1].strip():
            cells.pop()
        if len(cells) > n:
            raise MatrixError(
                f"{source}: row {label!r} has {len(cells)} values for {n} signals."
            )
        cells += [""] * (n - len(cells))
        parsed: list[float | None] = []
        for j, cell in enumerate(cells):
            try:
                parsed.append(parse_value(cell))
            except ValueError as exc:
                raise MatrixError(
                    f"{source}: ({labels[i]}, {labels[j]}): {exc}."
                ) from exc
        raw.append(parsed)

    values = [[1.0] * n for _ in range(n)]
    typed_lower = 0
    worst_mismatch = 0.0
    off_scale: list[str] = []
    for i in range(n):
        diagonal = raw[i][i]
        if diagonal is not None and abs(diagonal - 1.0) > 1e-9:
            raise MatrixError(
                f"{source}: the diagonal cell ({labels[i]}, {labels[i]}) is "
                f"{format_value(diagonal)}; a signal compared with itself is 1."
            )
    for i, j in combinations(range(n), 2):
        upper = raw[i][j]
        lower = raw[j][i]
        if upper is None:
            hint = (
                " The lower triangle has a value there; the template puts the "
                "judgement in the upper triangle (row before column)."
                if lower is not None
                else ""
            )
            raise MatrixError(
                f"{source}: ({labels[i]}, {labels[j]}) is blank. Every "
                f"upper-triangle cell is a judgement and must be filled.{hint}"
            )
        if not (SAATY_MIN - 1e-9 <= upper <= SAATY_MAX + 1e-9):
            raise MatrixError(
                f"{source}: ({labels[i]}, {labels[j]}) is {format_value(upper)}, "
                f"outside Saaty's scale (1/9 to 9)."
            )
        if not _on_saaty_scale(upper):
            off_scale.append(f"({labels[i]}, {labels[j]}) = {format_value(upper)}")
        if lower is not None:
            typed_lower += 1
            mismatch = abs(lower * upper - 1.0)
            if mismatch > RECIPROCAL_TOLERANCE:
                raise MatrixError(
                    f"{source}: ({labels[j]}, {labels[i]}) is {format_value(lower)}, "
                    f"but ({labels[i]}, {labels[j]}) is {format_value(upper)}, whose "
                    f"reciprocal is {format_value(1 / upper)}. Leave the lower "
                    f"triangle blank and it is computed exactly."
                )
            worst_mismatch = max(worst_mismatch, mismatch)
        values[i][j] = upper
        values[j][i] = 1.0 / upper

    if typed_lower:
        notes.append(
            f"The lower triangle was filled in ({typed_lower} cell(s)); it agrees "
            f"with the upper one to within {worst_mismatch:.4f}, and exact "
            f"reciprocals of the upper triangle were used instead."
        )
    if off_scale:
        notes.append(
            "Not on Saaty's 1-9 scale: "
            + ", ".join(off_scale)
            + ". Expected for a merged matrix; not for one judge's."
        )

    return PairwiseMatrix(
        labels=labels,
        values=tuple(tuple(row) for row in values),
        source=source,
        notes=tuple(notes),
    )


# ── the eigenvector and the consistency ratio ──────────────────────────────


def principal_eigenvector(values) -> tuple[tuple[float, ...], float, int]:
    """`(weights, λ_max, iterations)` for a positive reciprocal matrix.

    Power iteration from the uniform vector: multiply, normalise to sum 1,
    repeat until no weight moves by more than `CONVERGENCE`. With the vector
    normalised to sum 1, λ_max is the sum of `A·w` — the eigen-equation
    `A·w = λ·w` summed over its rows.
    """
    n = len(values)
    weights = [1.0 / n] * n
    iterations = 0
    for iterations in range(1, MAX_ITERATIONS + 1):  # noqa: B007 - read after the loop
        product = [sum(values[i][j] * weights[j] for j in range(n)) for i in range(n)]
        total = sum(product)
        updated = [entry / total for entry in product]
        moved = max(abs(new - old) for new, old in zip(updated, weights, strict=True))
        weights = updated
        if moved < CONVERGENCE:
            break
    product = [sum(values[i][j] * weights[j] for j in range(n)) for i in range(n)]
    return tuple(weights), sum(product), iterations


@dataclass(frozen=True)
class CellError:
    """How far one judgement sits from what the derived weights imply.

    `ratio` is Saaty's ε: `a_ij · w_j / w_i`. A perfectly consistent judgement
    has ε = 1; the cells with the largest `|ln ε|` are the ones pulling the
    matrix away from consistency, and so the ones worth re-thinking first.
    """

    row: str
    column: str
    judged: float
    implied: float
    ratio: float

    @property
    def deviation(self) -> float:
        return abs(math.log(self.ratio))

    def sentence(self) -> str:
        return (
            f"({self.row}, {self.column}) is judged {format_value(self.judged)}; "
            f"the weights it produced imply about {format_value(self.implied)}."
        )


@dataclass(frozen=True)
class Triad:
    """Three signals whose three judgements do not agree with each other.

    File B Appendix B's own example: deprecation 3x severity and severity 2x
    count imply deprecation ~6x count, so judging that pair 2 contradicts the
    other two. `deviation` is `|ln(a_ij · a_jk / a_ik)|`, zero for a coherent
    triad, and symmetric in how far over or under the implied value it lies.
    """

    first: str
    middle: str
    last: str
    first_middle: float
    middle_last: float
    first_last: float

    @property
    def implied(self) -> float:
        return self.first_middle * self.middle_last

    @property
    def deviation(self) -> float:
        return abs(math.log(self.implied / self.first_last))

    def sentence(self) -> str:
        return (
            f"{self.first} vs {self.middle} = {format_value(self.first_middle)} and "
            f"{self.middle} vs {self.last} = {format_value(self.middle_last)} imply "
            f"{self.first} vs {self.last} of about {format_value(self.implied)}, but "
            f"it is judged {format_value(self.first_last)}."
        )


@dataclass(frozen=True)
class AhpResult:
    """One matrix, computed: its weights and whether to believe them."""

    matrix: PairwiseMatrix
    weights: tuple[float, ...]
    lambda_max: float
    consistency_index: float
    random_index: float
    consistency_ratio: float
    iterations: int

    @property
    def passes(self) -> bool:
        """CR strictly below 0.10 (File B: "CR < 0.10 = coherent")."""
        return self.consistency_ratio < CR_THRESHOLD

    def weight_vector(self) -> dict[str, float]:
        """Weights keyed by signal name, in the matrix's own order."""
        return dict(zip(self.matrix.signals, self.weights, strict=True))

    def triads(self, limit: int | None = 3) -> list[Triad]:
        return inconsistent_triads(self.matrix, limit=limit)

    def cell_errors(self, limit: int | None = 3) -> list[CellError]:
        """Upper-triangle judgements furthest from what the weights imply."""
        found: list[CellError] = []
        labels = self.matrix.labels
        for i, j in self.matrix.upper_cells():
            judged = self.matrix.values[i][j]
            implied = self.weights[i] / self.weights[j]
            found.append(
                CellError(
                    row=labels[i],
                    column=labels[j],
                    judged=judged,
                    implied=implied,
                    ratio=judged / implied,
                )
            )
        found.sort(key=lambda error: (-error.deviation, error.row, error.column))
        return found if limit is None else found[:limit]

    def as_dict(self) -> dict:
        return {
            "source": self.matrix.source,
            "labels": list(self.matrix.labels),
            "weights": {
                signal: round(weight, 6)
                for signal, weight in self.weight_vector().items()
            },
            "lambda_max": round(self.lambda_max, 6),
            "consistency_index": round(self.consistency_index, 6),
            "random_index": self.random_index,
            "consistency_ratio": round(self.consistency_ratio, 6),
            "passes": self.passes,
            "threshold": CR_THRESHOLD,
            "notes": list(self.matrix.notes),
        }


def evaluate(matrix: PairwiseMatrix) -> AhpResult:
    """Weights, λ_max, CI = (λ_max - n)/(n - 1), and CR = CI / RI."""
    weights, lambda_max, iterations = principal_eigenvector(matrix.values)
    n = matrix.n
    random_index = RANDOM_INDEX[n]
    if n <= 2:
        # Every 2x2 reciprocal matrix is consistent; λ_max is exactly 2 up to
        # float noise, which would otherwise surface as a CI of 1e-16.
        consistency_index = 0.0
        ratio = 0.0
    else:
        consistency_index = max(0.0, (lambda_max - n) / (n - 1))
        ratio = consistency_index / random_index
    return AhpResult(
        matrix=matrix,
        weights=weights,
        lambda_max=lambda_max,
        consistency_index=consistency_index,
        random_index=random_index,
        consistency_ratio=ratio,
        iterations=iterations,
    )


def inconsistent_triads(matrix: PairwiseMatrix, limit: int | None = 3) -> list[Triad]:
    """Every triad of signals, the least coherent first."""
    labels = matrix.labels
    values = matrix.values
    triads = [
        Triad(
            first=labels[i],
            middle=labels[j],
            last=labels[k],
            first_middle=values[i][j],
            middle_last=values[j][k],
            first_last=values[i][k],
        )
        for i, j, k in combinations(range(matrix.n), 3)
    ]
    triads.sort(key=lambda triad: (-triad.deviation, triad.first, triad.middle))
    return triads if limit is None else triads[:limit]


class InconsistentMatrix(Exception):
    """A matrix whose CR is at or above 0.10, refused with what to revisit."""

    def __init__(self, result: AhpResult) -> None:
        self.result = result
        super().__init__(refusal(result))


def refusal(result: AhpResult) -> str:
    """The sentence File B's WP-6 item 1 means by "the tool refuses"."""
    lines = [
        f"{result.matrix.source}: consistency ratio {result.consistency_ratio:.4f} "
        f"is not below {CR_THRESHOLD:.2f}, so these judgements contradict each "
        f"other too much for their weights to mean anything (File B, Appendix B).",
        "Re-think these triads, not the weights:",
    ]
    lines += [f"  - {triad.sentence()}" for triad in result.triads()]
    lines.append("The single judgements furthest from what the matrix implies:")
    lines += [f"  - {error.sentence()}" for error in result.cell_errors()]
    lines.append(
        "Change only those cells and resubmit (File B WP-3 step 2). "
        "Adjusting values at random until the ratio passes is not a revision."
    )
    return "\n".join(lines)


def require_consistent(result: AhpResult) -> AhpResult:
    """The gate: returns the result, or raises `InconsistentMatrix`."""
    if not result.passes:
        raise InconsistentMatrix(result)
    return result


# ── reconciliation (File B WP-3 step 3) ────────────────────────────────────


def scale_position(value: float) -> float:
    """Where a value sits on Saaty's scale, counted in steps from 1.

    `... 1/3, 1/2, 1, 2, 3 ...` are `... -2, -1, 0, 1, 2 ...`. A value between
    scale points (a merged 2.83) sits between steps; the distance between two
    judgements is the difference of their positions.
    """
    return value - 1 if value >= 1 else -(1 / value - 1)


@dataclass(frozen=True)
class CellDivergence:
    row: str
    column: str
    first: float
    second: float
    merged: float

    @property
    def steps(self) -> float:
        return abs(scale_position(self.first) - scale_position(self.second))

    @property
    def needs_discussion(self) -> bool:
        """File B: cells that "diverge by more than 2 scale steps"."""
        return self.steps > DIVERGENCE_STEPS + 1e-9


def _aligned(first: PairwiseMatrix, second: PairwiseMatrix) -> list[int]:
    """`second`'s row index for each of `first`'s signals, or refuse."""
    if set(first.signals) != set(second.signals):
        raise MatrixError(
            f"{first.source} and {second.source} compare different signals: "
            f"{sorted(first.signals)} vs {sorted(second.signals)}."
        )
    return [second.signals.index(signal) for signal in first.signals]


def divergence(first: PairwiseMatrix, second: PairwiseMatrix) -> list[CellDivergence]:
    """Cell-by-cell distance between two judges, in `first`'s order."""
    order = _aligned(first, second)
    cells: list[CellDivergence] = []
    for i, j in first.upper_cells():
        a = first.values[i][j]
        b = second.values[order[i]][order[j]]
        cells.append(
            CellDivergence(
                row=first.labels[i],
                column=first.labels[j],
                first=a,
                second=b,
                merged=math.sqrt(a * b),
            )
        )
    return cells


def geometric_merge(
    first: PairwiseMatrix,
    second: PairwiseMatrix,
    overrides: dict[tuple[str, str], float] | None = None,
    *,
    source: str = "merged",
) -> PairwiseMatrix:
    """The reconciled matrix: the geometric mean of the two judges, cell by cell.

    The geometric mean rather than the arithmetic one because it is the only
    mean that preserves reciprocity: `sqrt(a·b)` and `sqrt((1/a)·(1/b))` are
    reciprocals of each other, where `(a+b)/2` and `(1/a+1/b)/2` are not.

    `overrides` holds the cells re-judged in the meeting, keyed
    `(row label, column label)`; the review of 2026-09-24 asks that any such
    cell be recorded with its old and new value, so they are named here rather
    than edited into the output by hand.
    """
    overrides = {
        (_signal_key(row), _signal_key(column)): value
        for (row, column), value in (overrides or {}).items()
    }
    order = _aligned(first, second)
    n = first.n
    values = [[1.0] * n for _ in range(n)]
    used: set[tuple[str, str]] = set()
    for i, j in first.upper_cells():
        key = (first.signals[i], first.signals[j])
        reverse = (first.signals[j], first.signals[i])
        if key in overrides:
            merged = overrides[key]
            used.add(key)
        elif reverse in overrides:
            merged = 1 / overrides[reverse]
            used.add(reverse)
        else:
            merged = math.sqrt(first.values[i][j] * second.values[order[i]][order[j]])
        values[i][j] = merged
        values[j][i] = 1 / merged
    unknown = set(overrides) - used
    if unknown:
        raise MatrixError(
            f"Override names a cell that is not in the matrix: {sorted(unknown)}."
        )
    notes = [f"Geometric-mean merge of {first.source} and {second.source}."]
    if used:
        notes.append(
            "Re-judged in reconciliation: "
            + ", ".join(f"({row}, {column})" for row, column in sorted(used))
            + "."
        )
    return PairwiseMatrix(
        labels=first.labels,
        values=tuple(tuple(row) for row in values),
        source=source,
        notes=tuple(notes),
    )


def write_matrix(matrix: PairwiseMatrix, path: Path) -> Path:
    """File B's template, filled: header, upper triangle, diagonal 1, lower blank.

    Six significant figures — enough that the reciprocal the reader computes
    agrees with the one this module computed far past any printed decimal.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["", *matrix.labels])
    for i, label in enumerate(matrix.labels):
        row: list[str] = [label]
        for j in range(matrix.n):
            if i == j:
                row.append("1")
            elif j > i:
                row.append(f"{matrix.values[i][j]:.6g}")
            else:
                row.append("")
        writer.writerow(row)
    Path(path).write_text(buffer.getvalue(), encoding="utf-8")
    return Path(path)
