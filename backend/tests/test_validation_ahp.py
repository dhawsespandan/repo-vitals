"""`validation/ahp.py` — §10 Phase 12's first two acceptance clauses.

"`ahp.py` reproduces a textbook AHP example exactly" and "CR gate demonstrably
blocks an inconsistent matrix and names the worst triads".

"Textbook" is taken in its strongest form: cases whose answer is a theorem, so
the expected values are derived rather than copied from a table somebody typed.

* A perfectly consistent matrix `a_ij = w_i / w_j` has eigenvector `w` and
  λ_max = n exactly (Saaty 1977, the definition the whole method rests on).
* For n = 3 the principal eigenvector *is* the normalised row geometric mean,
  and λ_max = 1 + t + 1/t with t = (a12·a23/a13)^(1/3) — the closed form for
  3x3 reciprocal matrices.

Then the project's own matrices, at the values the 2026-09-24 review
recomputed independently by hand: WP-1's seed (λ_max 4.031, CI 0.0103, CR
0.0115), the delivered Matrix B (λ_max 4.154, CR 0.057), and their reconciled
merge (λ_max 4.077, CR 0.028).
"""

from __future__ import annotations

import math
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.research.validation import ahp

TEMPLATE_HEADER = ",Deprecation,Severity,Count,Staleness\n"

#: WP-1's starting matrix, as File B's template writes it: upper triangle only.
SEED = (
    TEMPLATE_HEADER
    + "Deprecation,1,2,3,4\n"
    + "Severity,,1,2,3\n"
    + "Count,,,1,2\n"
    + "Staleness,,,,1\n"
)

#: The 2026-09-24 delivery's Matrix B, upper triangle.
MATRIX_B = (
    TEMPLATE_HEADER
    + "Deprecation,1,1,3,2\n"
    + "Severity,,1,4,3\n"
    + "Count,,,1,2\n"
    + "Staleness,,,,1\n"
)


def matrix(text: str, source: str = "test.csv") -> ahp.PairwiseMatrix:
    return ahp.parse_matrix(text, source=source)


def consistent(weights: list[float]) -> ahp.PairwiseMatrix:
    labels = ["Deprecation", "Severity", "Count", "Staleness"][: len(weights)]
    rows = [",".join(["", *labels])]
    for i, label in enumerate(labels):
        cells = [
            "1" if i == j else (f"{weights[i] / weights[j]!r}" if j > i else "")
            for j in range(len(labels))
        ]
        rows.append(",".join([label, *cells]))
    return matrix("\n".join(rows))


# ── textbook ───────────────────────────────────────────────────────────────


class TestTheTheorems:
    def test_a_consistent_matrix_returns_its_generating_weights_exactly(self):
        weights = [0.4, 0.3, 0.2, 0.1]
        result = ahp.evaluate(consistent(weights))

        for got, expected in zip(result.weights, weights, strict=True):
            assert got == pytest.approx(expected, abs=1e-12)
        assert result.lambda_max == pytest.approx(4.0, abs=1e-12)
        assert result.consistency_ratio == pytest.approx(0.0, abs=1e-12)
        assert result.passes

    def test_three_by_three_matches_the_closed_form(self):
        """λ_max = 1 + t + 1/t, eigenvector = normalised row geometric mean."""
        a12, a13, a23 = 3.0, 5.0, 3.0
        result = ahp.evaluate(
            matrix(
                ",Deprecation,Severity,Count\n"
                f"Deprecation,1,{a12},{a13}\n"
                f"Severity,,1,{a23}\n"
                "Count,,,1\n"
            )
        )

        t = (a12 * a23 / a13) ** (1 / 3)
        assert result.lambda_max == pytest.approx(1 + t + 1 / t, abs=1e-12)

        means = [
            (1 * a12 * a13) ** (1 / 3),
            ((1 / a12) * 1 * a23) ** (1 / 3),
            ((1 / a13) * (1 / a23) * 1) ** (1 / 3),
        ]
        total = sum(means)
        for got, mean in zip(result.weights, means, strict=True):
            assert got == pytest.approx(mean / total, abs=1e-12)

        ci = (result.lambda_max - 3) / 2
        assert result.consistency_index == pytest.approx(ci, abs=1e-12)
        assert result.consistency_ratio == pytest.approx(ci / 0.58, abs=1e-12)

    @pytest.mark.parametrize(
        ("n", "ri"), [(3, 0.58), (4, 0.90), (5, 1.12), (6, 1.24), (7, 1.32)]
    )
    def test_the_random_index_is_the_table_file_a_gives(self, n, ri):
        assert ahp.RANDOM_INDEX[n] == ri

    def test_a_two_by_two_is_consistent_by_definition(self):
        result = ahp.evaluate(
            matrix(",Deprecation,Severity\nDeprecation,1,7\nSeverity,,1\n")
        )
        assert result.consistency_ratio == 0.0
        assert result.weights[0] == pytest.approx(7 / 8, abs=1e-12)


class TestTheProjectsOwnMatrices:
    """The values the 2026-09-24 review recomputed by hand, as regression oracles."""

    def test_wp1s_seed_matrix(self):
        result = ahp.evaluate(matrix(SEED))
        assert round(result.lambda_max, 3) == 4.031
        assert round(result.consistency_index, 4) == 0.0103
        assert round(result.consistency_ratio, 4) == 0.0115
        assert result.passes

    def test_the_delivered_matrix_b(self):
        result = ahp.evaluate(matrix(MATRIX_B))
        assert round(result.lambda_max, 3) == 4.154
        assert round(result.consistency_ratio, 3) == 0.057
        assert [round(weight, 3) for weight in result.weights] == [
            0.338,
            0.401,
            0.143,
            0.119,
        ]

    def test_their_geometric_mean_merge(self):
        merged = ahp.geometric_merge(matrix(SEED), matrix(MATRIX_B))
        result = ahp.evaluate(merged)
        assert round(result.lambda_max, 3) == 4.077
        assert round(result.consistency_ratio, 3) == 0.028
        assert [round(weight, 2) for weight in result.weights] == [0.40, 0.34, 0.15, 0.11]

    def test_the_weights_come_back_keyed_by_signal(self):
        vector = ahp.evaluate(matrix(SEED)).weight_vector()
        assert list(vector) == ["deprecation", "severity", "count", "staleness"]
        assert sum(vector.values()) == pytest.approx(1.0, abs=1e-12)


# ── the gate ───────────────────────────────────────────────────────────────

#: Circular on purpose: deprecation beats severity, severity beats count, and
#: count beats deprecation — each by the scale's maximum.
CIRCULAR = ",Deprecation,Severity,Count\nDeprecation,1,9,1/9\nSeverity,,1,9\nCount,,,1\n"


class TestTheConsistencyGate:
    def test_it_blocks_an_inconsistent_matrix(self):
        result = ahp.evaluate(matrix(CIRCULAR, "circular.csv"))
        assert not result.passes
        with pytest.raises(ahp.InconsistentMatrix) as refused:
            ahp.require_consistent(result)
        assert "circular.csv" in str(refused.value)

    def test_the_refusal_names_the_contradicting_triad(self):
        """File B: "the tool names your most contradictory judgment triads" —
        the sentence has to say which judgements, and what they imply."""
        text = ahp.refusal(ahp.evaluate(matrix(CIRCULAR)))
        assert (
            "Deprecation vs Severity = 9 and Severity vs Count = 9 imply "
            "Deprecation vs Count of about 81, but it is judged 1/9." in text
        )
        assert "Adjusting values at random" in text

    def test_the_worst_triad_is_listed_first(self):
        mild = (
            TEMPLATE_HEADER
            + "Deprecation,1,2,3,4\n"
            + "Severity,,1,2,3\n"
            + "Count,,,1,1/5\n"  # contradicts count > staleness elsewhere
            + "Staleness,,,,1\n"
        )
        triads = ahp.evaluate(matrix(mild)).triads(limit=None)
        assert [triad.deviation for triad in triads] == sorted(
            (triad.deviation for triad in triads), reverse=True
        )
        assert {triads[0].first, triads[0].middle, triads[0].last} >= {
            "Count",
            "Staleness",
        }

    def test_the_boundary_is_strict(self):
        """`CR < 0.10` passes and `CR = 0.10` does not — File B's wording."""
        base = ahp.evaluate(matrix(SEED))
        at = ahp.AhpResult(**{**base.__dict__, "consistency_ratio": ahp.CR_THRESHOLD})
        below = ahp.AhpResult(**{**base.__dict__, "consistency_ratio": 0.0999})
        assert not at.passes
        assert below.passes

    def test_cell_errors_point_at_the_judgement_that_does_not_fit(self):
        result = ahp.evaluate(matrix(CIRCULAR))
        worst = result.cell_errors(limit=1)[0]
        assert (worst.row, worst.column) == ("Deprecation", "Count")


# ── reading File B's template ──────────────────────────────────────────────


class TestReadingTheTemplate:
    def test_the_lower_triangle_is_computed_exactly(self):
        parsed = matrix(SEED)
        assert parsed.value("Severity", "Deprecation") == 0.5
        assert parsed.value("Count", "Deprecation") == 1 / 3
        assert parsed.notes == ()

    def test_fractions_are_read_as_fractions(self):
        parsed = matrix(",Deprecation,Severity\nDeprecation,1,1/3\nSeverity,,1\n")
        assert parsed.value("Deprecation", "Severity") == 1 / 3
        assert parsed.value("Severity", "Deprecation") == 3.0

    def test_a_typed_lower_triangle_within_rounding_is_noted_and_replaced(self):
        """The 2026-09-24 delivery typed 0.333 for 1/3. Accepted, with the
        exact reciprocal used and a note saying so."""
        parsed = matrix(
            TEMPLATE_HEADER
            + "Deprecation,1,2,3,4\n"
            + "Severity,0.500,1,2,3\n"
            + "Count,0.333,0.500,1,2\n"
            + "Staleness,0.250,0.333,0.500,1\n"
        )
        assert parsed.value("Count", "Deprecation") == 1 / 3
        assert any("exact reciprocals" in note for note in parsed.notes)

    def test_a_lower_triangle_that_contradicts_the_upper_is_refused(self):
        with pytest.raises(ahp.MatrixError, match=r"\(Severity, Deprecation\) is 2"):
            matrix(",Deprecation,Severity\nDeprecation,1,2\nSeverity,2,1\n")

    def test_comment_lines_are_skipped_and_noted(self):
        parsed = matrix("# Judge: someone\n# CR: 0.01\n" + SEED)
        assert any("comment line" in note for note in parsed.notes)

    def test_a_blank_judgement_names_its_cell(self):
        with pytest.raises(ahp.MatrixError, match=r"\(Severity, Count\) is blank"):
            matrix(
                TEMPLATE_HEADER
                + "Deprecation,1,2,3,4\n"
                + "Severity,,1,,3\n"
                + "Count,,,1,2\n"
                + "Staleness,,,,1\n"
            )

    def test_a_judgement_typed_into_the_lower_triangle_gets_a_hint(self):
        with pytest.raises(ahp.MatrixError, match="upper triangle"):
            matrix(",Deprecation,Severity\nDeprecation,1,\nSeverity,3,1\n")

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ("Deprecation,1,12\nSeverity,,1\n", "outside Saaty's scale"),
            ("Deprecation,2,3\nSeverity,,1\n", "diagonal"),
            ("Severity,1,3\nDeprecation,,1\n", "same order as the header"),
            ("Deprecation,1,abc\nSeverity,,1\n", "not a number"),
            ("Deprecation,1,-2\nSeverity,,1\n", "not a positive number"),
            ("Deprecation,1,3\n", "at least two signal rows"),
        ],
    )
    def test_malformed_files_are_refused_with_the_reason(self, body, message):
        with pytest.raises(ahp.MatrixError, match=message):
            matrix(",Deprecation,Severity\n" + body)

    def test_off_scale_values_are_noted_not_refused(self):
        parsed = matrix(",Deprecation,Severity\nDeprecation,1,2.8284\nSeverity,,1\n")
        assert any("Not on Saaty's 1-9 scale" in note for note in parsed.notes)

    def test_a_written_matrix_reads_back_identically(self, tmp_path):
        merged = ahp.geometric_merge(matrix(SEED), matrix(MATRIX_B))
        path = ahp.write_matrix(merged, tmp_path / "rec.csv")
        again = ahp.read_matrix(path)
        assert all("Saaty" in note for note in again.notes)
        for i in range(4):
            for j in range(4):
                assert again.values[i][j] == pytest.approx(merged.values[i][j], rel=1e-5)
        # File B's shape: header plus four rows, lower triangle blank.
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
        assert lines[2].startswith("Severity,,1,")


# ── reconciliation ─────────────────────────────────────────────────────────


class TestReconciliation:
    def test_steps_are_counted_on_saatys_scale(self):
        assert ahp.scale_position(3) == 2
        assert ahp.scale_position(1) == 0
        assert ahp.scale_position(1 / 3) == -2

    def test_a_divergence_across_one_counts_both_sides(self):
        cell = ahp.CellDivergence("A", "B", first=3.0, second=0.5, merged=math.sqrt(1.5))
        assert cell.steps == 3
        assert cell.needs_discussion

    def test_two_steps_apart_is_not_more_than_two(self):
        """The delivered A and B differ by exactly two steps in two cells. File
        B sends cells differing by *more than* two to the meeting, so neither
        qualifies — which the delivered notes got wrong."""
        cells = ahp.divergence(matrix(SEED), matrix(MATRIX_B))
        by_cell = {(cell.row, cell.column): cell for cell in cells}
        assert by_cell[("Deprecation", "Staleness")].steps == 2
        assert by_cell[("Severity", "Count")].steps == 2
        assert not any(cell.needs_discussion for cell in cells)

    def test_the_merge_is_the_geometric_mean_and_stays_reciprocal(self):
        merged = ahp.geometric_merge(matrix(SEED), matrix(MATRIX_B))
        assert merged.value("Deprecation", "Staleness") == pytest.approx(math.sqrt(8))
        assert merged.value("Staleness", "Deprecation") == pytest.approx(1 / math.sqrt(8))

    def test_an_override_replaces_one_cell_and_is_recorded(self):
        merged = ahp.geometric_merge(
            matrix(SEED), matrix(MATRIX_B), {("Deprecation", "Staleness"): 3.0}
        )
        assert merged.value("Deprecation", "Staleness") == 3.0
        assert merged.value("Severity", "Count") == pytest.approx(math.sqrt(8))
        assert any("Re-judged" in note for note in merged.notes)

    def test_matrices_over_different_signals_are_refused(self):
        other = matrix(",Deprecation,Severity\nDeprecation,1,2\nSeverity,,1\n")
        with pytest.raises(ahp.MatrixError, match="different signals"):
            ahp.divergence(matrix(SEED), other)


# ── the command WP-3 step 2 runs ───────────────────────────────────────────


class TestTheCommand:
    def test_it_prints_the_three_numbers_the_session_notes_quote(self, tmp_path):
        path = tmp_path / "wp3_matrix_A.csv"
        path.write_text(SEED, encoding="utf-8")
        out = StringIO()
        call_command("ahp_check", str(path), stdout=out)
        text = out.getvalue()
        assert "λ_max = 4.0310" in text
        assert "CI = 0.0103" in text
        assert "CR = 0.0115 (passes CR < 0.10)" in text

    def test_two_matrices_get_a_divergence_table_and_a_merge(self, tmp_path):
        first = tmp_path / "A.csv"
        second = tmp_path / "B.csv"
        first.write_text(SEED, encoding="utf-8")
        second.write_text(MATRIX_B, encoding="utf-8")
        merged = tmp_path / "reconciled.csv"
        out = StringIO()

        call_command(
            "ahp_check", str(first), str(second), "--merge", str(merged), stdout=out
        )

        assert "| Deprecation vs Staleness | 4 | 2 | 2.00 | no |" in out.getvalue()
        assert "## reconciled.csv" in out.getvalue()
        assert ahp.read_matrix(merged).value("Severity", "Count") == pytest.approx(
            math.sqrt(8), rel=1e-5
        )

    def test_a_failing_matrix_is_reported_and_then_exits_non_zero(self, tmp_path):
        path = tmp_path / "circular.csv"
        path.write_text(CIRCULAR, encoding="utf-8")
        out = StringIO()
        with pytest.raises(CommandError, match=r"circular\.csv"):
            call_command("ahp_check", str(path), stdout=out)
        assert "the most inconsistent triads" in out.getvalue()

    def test_an_unreadable_matrix_is_a_command_error(self, tmp_path):
        with pytest.raises(CommandError, match="No matrix file"):
            call_command("ahp_check", str(tmp_path / "missing.csv"), stdout=StringIO())
