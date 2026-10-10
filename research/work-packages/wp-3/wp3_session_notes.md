# WP-3 session notes: AHP judgments (Tier-2 weights)

**Date:** 2026-10-08
**Matrix:** `wp3_matrix_final.csv`, committed together with these notes and unedited since.
**Consistency:** checked with `ahp_check` (Phase 12) and recomputed independently with numpy.

> **Final decision (Spandan, 2026-10-08): WP-3 follows a single judgment.** No second judge will be added and there is no reconciliation step. `wp3_matrix_final.csv` is the only matrix, and it is the one WP-6, weights v2 and the S1 paper use. Every place that reports these weights must say they come from one judgment.

## Deviation from File B: one judgment, not two independent judges

File B WP-3 asks for two judges who fill the matrix independently, a consistency check, and a documented reconciliation. On 2026-10-08 the team was unavailable, and Spandan completed the remaining work packages alone. At Spandan's direction, the six pairwise judgments were produced with an AI tool, reasoning only from File B's definitions of the four signals. Spandan owns this deliverable.

What this means, stated so it isn't hidden:

- **No independence, divergence table or reconciliation.** Of File B's "two independent judges + a mathematical consistency check + documented reconciliation", only the consistency check is met.
- **The CR shows coherence only.** CR = 0.0054. The WP-1 note said of its own 0.0115 that a ratio this low is the signature of judgments built to be coherent, not of a contested human assessment. It shows the six cells don't contradict each other, and nothing more (File B, Appendix B).
- **The remaining independent check is WP-6's entropy vector.** It is computed from the corpus with no judgment at all. Whether it agrees or disagrees with this matrix is the evidence that carries weight, and WP-6's sign-off must discuss it either way.
- **S1 must list this as a threat to validity,** beside L4: the Tier-2 AHP vector comes from a single, AI-assisted judgment.

## What the judge had seen beforehand

- **The WP-1 seed matrix and WP-1's published vectors.** Seed: Deprecation vs Severity 2, vs Count 3, vs Staleness 4; Severity vs Count 2, vs Staleness 3; Count vs Staleness 2.
- **PR #3's matrix** (`refs/pull/3/head`), read during the 2026-10-07 review. It is not used here: see `wp/wp-review/WP_review.md`.
- **Never seen: any formula output.** No score, class or signal for any anchor or corpus repository existed when the judgments were made. WP-4 and WP-5 had produced no data, and the anchor set has never been scored.

## Posting protocol

There was only one judgment, so no simultaneous posting was needed. The record is the commit that adds this file and the matrix together.

## The matrix

Each cell says how much more important the **row** signal is than the **column** signal for real-world dependency risk (Saaty 1–9). Only the upper triangle is filled; the tool computes the lower triangle as exact reciprocals.

| | Deprecation | Severity | Count | Staleness |
|---|---|---|---|---|
| **Deprecation** | 1 | 1/2 | 2 | 3 |
| **Severity** | | 1 | 3 | 5 |
| **Count** | | | 1 | 2 |
| **Staleness** | | | | 1 |

**Consistency** (`ahp_check`; numpy agrees to 4 decimals):
- λmax = 4.0145
- CI = 0.0048
- RI = 0.90
- **CR = 0.0054**, which passes CR < 0.10

**Principal eigenvector:**

| Deprecation | Severity | Count | Staleness |
|---|---|---|---|
| 0.2720 | 0.4829 | 0.1570 | 0.0882 |

## Where these judgments depart from the WP-1 seed

| Cell | WP-1 seed | WP-3 |
|---|---|---|
| Deprecation vs Severity | 2 | **1/2 (reversed)** |
| Deprecation vs Count | 3 | 2 |
| Deprecation vs Staleness | 4 | 3 |
| Severity vs Count | 2 | 3 |
| Severity vs Staleness | 3 | 5 |
| Count vs Staleness | 2 | 2 |

**The effect:**
- Severity becomes the largest weight: 0.483, against the seed's 0.277.
- Deprecation falls from 0.467 to 0.272.
- Count (0.157 vs 0.160) and staleness (0.088 vs 0.095) barely move.

## The two most debated cells

**1. Deprecation vs Severity: 1/2.** This is the one cell that reverses the seed. A known vulnerability's severity is direct evidence of exposure in the exact version a project uses. A deprecation notice is a first-party statement about the package's future, and on npm it is often not about security at all: a rename, a move to a scoped package, or "this version is no longer supported" on an old release line of a package that is still maintained. Deprecation still matters, because it means no future fixes, so severity is judged only moderately more important (2), not strongly. The seed's opposite view, that an explicit maintainer statement is zero-ambiguity, was weighed and set aside: certainty about a fact is not the same as importance for risk.

**2. Severity vs Staleness: 5.** Staleness is the noisiest of the four signals. Many small, finished packages publish nothing for years and carry no risk, so an old release date is a weak proxy, while a scored vulnerability is concrete. That gap is judged strong (5), not the seed's moderate (3). It stops short of 7 because staleness is the only one of the four that can say anything about *undisclosed* risk in abandoned code.

**The other four, in one line each:**
- **Severity vs Count, 3:** one critical vulnerability outweighs several low ones, and count partly repeats severity, since more advisories tend to raise the maximum.
- **Deprecation vs Count, 2:** a deprecated package's vulnerabilities, present and future, stay unpatched, which slightly outranks the breadth of today's known ones.
- **Deprecation vs Staleness, 3:** both are about maintenance, but deprecation is stated by the maintainer, while staleness is inferred from silence.
- **Count vs Staleness, 2:** count is measured and staleness is inferred.

## EPSS decision

**EPSS deferred from AHP.** File B allows the optional 5×5 matrix only if the judges can judge EPSS meaningfully. With one AI-assisted judgment and no second judge, adding a fifth signal would add a judgment nobody could cross-check. EPSS also stays out of the product weights (weight 0, behind `EPSS_ENABLED`).

## PyPI rule for weights v2

**The rule:** take 30% of the AHP deprecation weight off the PyPI vector and split it equally between severity and staleness. Count is unchanged.

This is the same rule WP-1 used (0.46 → 0.32). Keeping it means the difference between v1 and v2 comes only from the matrix.

**Why:**
- npm's deprecation is a package-level, free-text message that often names a successor.
- PyPI's equivalents carry less information:
  - a yank is per release;
  - the "Inactive" classifier is a single flag with no explanation.

**Applied to the eigenvector above:**

| Signal | Shift | PyPI weight before WP-6's rounding |
|---|---|---|
| deprecation | −0.0816 (30% of 0.2720) | 0.1904 |
| severity | +0.0408 | 0.5237 |
| count | 0 | 0.1570 |
| staleness | +0.0408 | 0.1290 |

WP-6 passes this as:

```
--pypi-shift "deprecation=-0.0816,severity=+0.0408,staleness=+0.0408"
```

**Limitation L4 (File C), unchanged:** the PyPI weight vector is derived by reasoning and the same AHP session, not by an independent PyPI-only calibration. The S1 PyPI sanity sub-analysis (§2.4.6) is the mitigation, and S3's gate.

## Deliberately not in this file

- **No v2 weights file.** WP-6 produces it from this matrix.
- **No claims about how the formula behaves under these weights.**
- **No claims about what the corpus contains.**
