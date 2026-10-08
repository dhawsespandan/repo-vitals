# WP-6 sign-off: formula validation

**Run:** 2026-10-08, by Spandan, on the research database at code `a293a18` (`v0.12.0`).

```
validate_formula --ahp ../wp/wp-3/wp3_matrix_final.csv --anchors ../wp/wp-2/wp2_anchor_set.csv \
    --snapshot-date 2026-10-07 \
    --pypi-shift "deprecation=-0.0816,severity=+0.0408,staleness=+0.0408"
```

- **Duration:** 23 minutes, exit 0.
- **Inputs:** WP-5's snapshot (914 repositories, 29,494 occurrences), WP-3's matrix and WP-2's 49-row anchor set.
- **Reproduction check:** all 914 stored scores reproduce exactly when recomputed.
- **Output:** the report is in `validation_report/`, copied unedited from `research_data/validation_report/`. The anchor manifest blobs are left out; they can be re-fetched by SHA.

## Decision: SIGNED. Weights v2 are approved for adoption.

Checks 1, 2, 5 and 6 pass. Checks 3 and 4 do not show what File B hoped for, and both are acknowledged below, as File B requires. Neither is a defect that a different weighting would fix: no weighting of these four signals correlates with Scorecard, and the entropy disagreement is mechanical. So neither is grounds for a bounce.

Adoption is Phase 12's commit 7: copy `validation_report/weights_v2_candidate.yaml` to `backend/weights/weights_v2.yaml` and mark it validated. Production keeps scoring under `v1` until that commit lands and `WEIGHTS_VERSION=v2` is set on Render.

## The six checks

**1. Matrix CR < 0.10: pass.**
- CR = 0.0054 (λmax 4.0145, CI 0.0048, RI 0.90).
- This is **a single judgment, with no reconciliation**: WP-3's final decision (see `../wp-3/wp3_session_notes.md`).
- Every place these weights are reported must say so.

**2. Every known anchor ≥ Medium: pass.**
- **12 of 12 known anchors pass under v2, and under v1.** Each was scanned today, and the scan saw the anchor package at the named version, flagged.
- No known anchor is Safe. The closest is `openai/jukebox`, at 69.81 (Medium).
- Of all 20 risky-seeded repositories, none is Safe: 17 are High alert, and 3 are Medium (`strongloop/loopback` 55.18, `openai/jukebox` 69.81, `YelpArchive/elastalert` 74.22).

**3. AHP vs entropy: disagreement, acknowledged.**

| | npm | PyPI |
|---|---|---|
| Cosine | 0.898 ("partial"; File C's H1 needs ≥ 0.90) | 0.691 ("tension") |
| Rank ρ | 0.40 | 0.40 |
| AHP order | severity > deprecation > count > staleness | severity > deprecation > count > staleness |
| Entropy order | count > severity > deprecation > staleness | deprecation 0.515 > count > severity > staleness |
| Same top two signals? | no | no |

- **H1 is not supported in either ecosystem.** That is a result to report.
- **The PyPI gap is mechanical, and interpretable.**
  - Entropy weights a signal by how *unevenly* it is spread, so a rare signal earns a large weight whatever it means.
  - Only 48 of 8,922 PyPI occurrences are deprecated. That rarity alone puts PyPI's entropy deprecation weight at 0.515.
  - Meanwhile both WP-1 and WP-3 lower PyPI deprecation on purpose: a yank or an "Inactive" flag says less than npm's deprecation message (D2, L4).
  - So the two vectors are answering different questions. "Which signal varies most" is not "which signal matters most" (File C §2.4.2).
- **v1's PyPI vector sits closer to entropy (cosine 0.890)** than v2 does. v2 moves away because of the matrix's emphasis on severity.
- **Both points go in S1's discussion.** WP-3 being a single judgment makes this the most important comparison in the study.

**4. Scorecard correlation: not met; a null result, documented.**

| Vector | Spearman ρ vs Scorecard | 95% interval |
|---|---|---|
| v2 | 0.047 | [-0.077, 0.169] |
| v1 | 0.084 | |
| entropy | 0.060 | |

- All three intervals include zero, over the 289 of 914 repositories deps.dev has a Scorecard for. That coverage is 32%: 468 not found, 157 with no Scorecard.
- **File C's H2 (ρ 0.3–0.6) is not supported.**
- The scatter (`correlation_scatter.png`) also shows range restriction: most covered repositories score between 2 and 4 out of 10 on Scorecard, which weakens any correlation.
- Since every weighting is near zero, the null is not evidence against v2. It says Scorecard measures a different construct: a repository's own security practices, not its dependencies' risk (L2). Tuning weights toward it would be fitting to the reference.
- The independent-convergence claim therefore cannot be made. S1 has to rest on the anchors (RQ4), robustness (RQ3) and RQ1, and say this plainly.
- **The circularity caveat is present beside the OSV roll-up number,** as required. v2 vs OSV roll-up: ρ = 0.863 (v1: 0.673), which is partly the formula agreeing with its own inputs (L1).

**5. Sensitivity: pass.** File B's threshold is 15%.

| Vector | Max flip rate at ±10% | Max flip rate at ±20% |
|---|---|---|
| v2 | 1.4% | 4.7% |
| entropy | 1.9% | 3.8% |

The largest flip rate across every parameter is 8.1%: v2 with `safe_min` +5.

**6. Final vectors sum to 1 and are non-degenerate: pass.**

| Ecosystem | deprecation | severity | count | staleness |
|---|---|---|---|---|
| npm | 0.2720 | 0.4829 | 0.1570 | 0.0881 |
| PyPI | 0.1904 | 0.5237 | 0.1570 | 0.1289 |

No weight is near 0 or near 0.8. The largest is PyPI's severity at 0.52. It is justified because PyPI's explicit deprecation evidence is weak, so known vulnerabilities are the strongest evidence that ecosystem offers.

## Also found, for S1

**The PyPI trust gate (RQ5) passes on distribution.** Under v2, PyPI scores span 0–100 and populate every class: 162 Safe, 70 Medium, 170 High alert. Its anchors pass. The gate's third condition, roll-up behaviour on matched dependency-count strata, is not computed by the harness and remains an S1 analysis.

**Score falls with dependency count**, measured on the anchor set:
- Spearman ρ between observed occurrences and v2 score is −0.51.
- Seeded-healthy repositories score *lower* than in-between ones: median 63.95 vs 82.39. Healthy repos declare about four times as many dependencies (median 60 vs 15.5).
- The risky bucket still separates cleanly, with a median of 10.39.
- This is decisions §11.27's confound, now measured. S1 must control for dependency count before ranking repositories or comparing ecosystems.

**Healthy-seeded outliers come from example and docs manifests**, which the scanner reads by design (every manifest outside vendored directories):

| Repository | Score | Cause |
|---|---|---|
| `pallets/flask` | 0.00 | entirely from `examples/celery/requirements.txt`, which pins jinja2 3.1.2, werkzeug 2.3.3 and flask 2.3.2, all with advisories |
| `scrapy/scrapy` | 0.00 | entirely from `docs/requirements.txt` |
| `vercel/next.js` | 0.00 | a real root pin (`turbo` 2.9.4, CVSS 9.8) plus several examples |

"Repository dependency risk" here includes manifests that do not ship. That is a construct limitation to state in S1. Weighting by a manifest's role is future work, not a WP-6 defect.
