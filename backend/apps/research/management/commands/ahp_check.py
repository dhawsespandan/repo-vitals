"""`manage.py ahp_check` — File B WP-3's "consistency tool".

    python manage.py ahp_check wp3_matrix_A.csv
    python manage.py ahp_check wp3_matrix_A.csv wp3_matrix_B.csv --merge wp3_matrix_reconciled.csv
    python manage.py ahp_check A.csv B.csv --merge rec.csv --override "Deprecation,Staleness=3"

WP-3 step 2: "Hand both CSVs to the developer, who runs the consistency tool.
It computes each matrix's Consistency Ratio. CR >= 0.10 -> the tool names your
most contradictory judgment triads." Step 3: "the tool lists cells where you
two diverge by more than 2 scale steps ... or accept the tool's geometric-mean
merge. The merged matrix must itself pass CR < 0.10."

That is this command. It prints λ_max, CI, RI and CR for every matrix it is
given — the three numbers the 2026-09-24 review asks to be quoted in the
session notes — and, given two, the divergence table and the merged matrix.
`validate_formula` runs the same gate on the reconciled matrix and refuses to
continue past a failing one; this command reports and then exits non-zero.

It reads files and writes at most the merged CSV. No database access at all.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.research.validation import ahp


def _override(text: str) -> tuple[tuple[str, str], float]:
    """`"Deprecation,Staleness=3"` -> `(("Deprecation", "Staleness"), 3.0)`."""
    cell, _, value = text.partition("=")
    row, _, column = cell.partition(",")
    if not (row.strip() and column.strip() and value.strip()):
        raise CommandError(
            f"--override {text!r}: expected ROW,COLUMN=VALUE, "
            f'e.g. "Deprecation,Staleness=3".'
        )
    try:
        parsed = ahp.parse_value(value)
    except ValueError as exc:
        raise CommandError(f"--override {text!r}: {exc}.") from exc
    if parsed is None:
        raise CommandError(f"--override {text!r}: no value.")
    return (row.strip(), column.strip()), parsed


class Command(BaseCommand):
    help = (
        "Consistency check for AHP matrices (WP-3): λ_max, CI, CR, the most "
        "inconsistent triads, and — given two — the divergence table and the "
        "geometric-mean merge."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("matrices", nargs="+", metavar="MATRIX.csv")
        parser.add_argument(
            "--merge",
            metavar="OUT.csv",
            help="With two matrices: write their geometric-mean merge here.",
        )
        parser.add_argument(
            "--override",
            action="append",
            default=[],
            metavar="ROW,COLUMN=VALUE",
            help="A cell re-judged in the reconciliation meeting; used in the "
            "merge instead of the geometric mean. Repeatable.",
        )

    def handle(self, *args, **options) -> None:
        paths = [Path(path).expanduser() for path in options["matrices"]]
        if len(paths) > 2:
            raise CommandError("Give one matrix, or the two judges' matrices.")
        if (options["merge"] or options["override"]) and len(paths) != 2:
            raise CommandError("--merge and --override need exactly two matrices.")

        try:
            matrices = [ahp.read_matrix(path) for path in paths]
        except ahp.MatrixError as exc:
            raise CommandError(str(exc)) from exc

        failing: list[str] = []
        for matrix in matrices:
            result = ahp.evaluate(matrix)
            self._print_result(result)
            if not result.passes:
                failing.append(matrix.source)

        if len(matrices) == 2:
            first, second = matrices
            try:
                cells = ahp.divergence(first, second)
                overrides = dict(_override(text) for text in options["override"])
                merged = ahp.geometric_merge(
                    first,
                    second,
                    overrides,
                    source=Path(options["merge"]).name if options["merge"] else "merged",
                )
            except ahp.MatrixError as exc:
                raise CommandError(str(exc)) from exc

            self.stdout.write(f"\n## Divergence: {first.source} vs {second.source}\n")
            self.stdout.write("| Cell | First | Second | Steps apart | Discuss? |")
            self.stdout.write("|---|---|---|---|---|")
            for cell in cells:
                self.stdout.write(
                    f"| {cell.row} vs {cell.column} | {ahp.format_value(cell.first)} | "
                    f"{ahp.format_value(cell.second)} | {cell.steps:.2f} | "
                    f"{'yes' if cell.needs_discussion else 'no'} |"
                )
            discuss = [cell for cell in cells if cell.needs_discussion]
            self.stdout.write(
                f"\n{len(discuss)} cell(s) differ by more than "
                f"{ahp.DIVERGENCE_STEPS} scale steps and go to the reconciliation "
                f"meeting (File B WP-3 step 3)."
            )

            merged_result = ahp.evaluate(merged)
            self.stdout.write("")
            self._print_result(merged_result)
            if not merged_result.passes:
                failing.append(merged.source)
            if options["merge"]:
                written = ahp.write_matrix(merged, Path(options["merge"]).expanduser())
                self.stdout.write(f"  wrote {written}")

        if failing:
            raise CommandError(
                f"Consistency ratio at or above {ahp.CR_THRESHOLD:.2f}: "
                f"{', '.join(failing)}. The triads above are the cells to revisit."
            )

    def _print_result(self, result: ahp.AhpResult) -> None:
        verdict = "passes" if result.passes else "FAILS"
        self.stdout.write(f"## {result.matrix.source}\n")
        self.stdout.write(
            f"- λ_max = {result.lambda_max:.4f}   CI = {result.consistency_index:.4f}   "
            f"RI = {result.random_index:.2f}   CR = {result.consistency_ratio:.4f} "
            f"({verdict} CR < {ahp.CR_THRESHOLD:.2f})"
        )
        self.stdout.write(
            "- weights (principal eigenvector): "
            + ", ".join(
                f"{label} {weight:.3f}"
                for label, weight in zip(
                    result.matrix.labels, result.weights, strict=True
                )
            )
        )
        for note in result.matrix.notes:
            self.stdout.write(f"- note: {note}")
        if not result.passes:
            self.stdout.write(
                self.style.WARNING("- the most inconsistent triads, worst first:")
            )
            for triad in result.triads():
                self.stdout.write(f"    {triad.sentence()}")
            self.stdout.write("- the judgements furthest from what the weights imply:")
            for error in result.cell_errors():
                self.stdout.write(f"    {error.sentence()}")
