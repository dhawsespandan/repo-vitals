# WP-6 Formula Validation Sign-off

**Deliverable:** `validation_report/` folder (tool-generated) + this sign-off  
**Command run:** `python manage.py validate_formula --ahp wp3_matrix_reconciled.csv --anchors wp2_anchor_set.csv`  
**Depends on:** WP-2 (anchor set), WP-3 (reconciled matrix), WP-4 (corpus manifest), WP-5 (research DB populated)  
**Date run:** FILL_IN_AFTER_RUN  
**Phase gate:** Phase 12 acceptance — weights v2 ships only after this sign-off.

---

## Six-check sign-off (File B §WP-6 — every line must be addressed)

> Complete each section after reading `research_data/validation_report/report.md` and charts.  
> **Do not sign if any hard-fail condition is met.** Send the report back to the developer for a fix pass instead.

---

### Check 1 — Reconciled matrix CR < 0.10

The tool recomputes CR from `wp3_matrix_reconciled.csv` as its first step. If CR ≥ 0.10 the tool refuses to proceed — a refusal here means WP-3 must be revisited, not tweaked.

| Item | Value |
|---|---|
| CR reported by tool | FILL_IN |
| Pass threshold | < 0.10 |
| **Result** | **PASS / FAIL** |

**Notes:** FILL_IN (expected CR ≈ 0.029 from our computation; tool should agree within floating-point rounding)

---

### Check 2 — Anchor classification (hard pass/fail)

Every repo flagged `is_known_anchor = true` in `wp2_anchor_set.csv` must score **Medium or High-Alert**. Any known-bad anchor scoring **Safe is an automatic fail** — do not sign; send back.

| Anchor repo | Anchor package | Score | Class | Pass? |
|---|---|---|---|---|
| nicedoc/nicedoc.io | request@2.88.2 | FILL_IN | FILL_IN | FILL_IN |
| TalAter/UpUp | lodash@3.10.1 | FILL_IN | FILL_IN | FILL_IN |
| strongloop/loopback | moment@2.24.0 | FILL_IN | FILL_IN | FILL_IN |
| omab/django-social-auth | django@1.8.x | FILL_IN | FILL_IN | FILL_IN |
| pinax/pinax | django@1.4.x | FILL_IN | FILL_IN | FILL_IN |

**Overall Check 2 result:** PASS / FAIL  
**Action if fail:** Stop. Do not sign. Return the report to the developer with this table filled in.

---

### Check 3 — AHP vs entropy weight agreement

The tool computes an entropy-based weight vector from the corpus data and compares it to the AHP reconciled vector.

| Signal | AHP weight (reconciled) | Entropy weight | Rank match? |
|---|---|---|---|
| Deprecation | 0.401 | FILL_IN | FILL_IN |
| Severity | 0.336 | FILL_IN | FILL_IN |
| Count | 0.154 | FILL_IN | FILL_IN |
| Staleness | 0.109 | FILL_IN | FILL_IN |

**Cosine similarity (AHP vs entropy):** FILL_IN  
**Top-2 signal ranking match:** FILL_IN (yes / no — if no, which signals swapped?)

**Interpretation (required sentence):**  
FILL_IN — broad agreement (cosine ≥ 0.90) is the strong story; partial agreement (0.75–0.90) should name which signal diverges and why (variance-driven entropy differs where a signal is rare-but-decisive, e.g. deprecation); < 0.75 is a genuine tension to lead the discussion with.

**Result:** (note — AHP vs entropy disagreement is not automatic failure; it must be explicitly acknowledged, never hidden)

---

### Check 4 — Correlation vs deps.dev Scorecard (external convergent validity)

The tool correlates the formula's repo score against the deps.dev/OpenSSF Scorecard score as the independent reference.

| Metric | Value |
|---|---|
| Spearman ρ (formula vs Scorecard) | FILL_IN |
| Pearson r (formula vs Scorecard) | FILL_IN |
| Bootstrap 95% CI (Spearman ρ) | [FILL_IN, FILL_IN] |
| n repos with Scorecard data | FILL_IN |

**Expected range:** ρ ∈ [0.3, 0.6] — deliberately not high (different construct; see L2 in File C)  
**Circularity caveat on OSV reference present in report?** YES / NO (must be YES — if absent, send back)

**Notes:** FILL_IN

---

### Check 5 — Sensitivity / perturbation stress test

The tool perturbs each weight ±10% and ±20% and reports the bucket-flip rate (fraction of repos changing class: Safe ↔ Medium ↔ High-Alert). **File B requires this to be reported for BOTH the AHP vector and the entropy vector.**

#### 5A — AHP vector (from wp3_matrix_reconciled.csv)

| Parameter | Perturbation | Flip rate | Flag? |
|---|---|---|---|
| Deprecation weight | +10% | FILL_IN % | FILL_IN |
| Deprecation weight | -10% | FILL_IN % | FILL_IN |
| Severity weight | +10% | FILL_IN % | FILL_IN |
| Severity weight | -10% | FILL_IN % | FILL_IN |
| Count weight | +10% | FILL_IN % | FILL_IN |
| Count weight | -10% | FILL_IN % | FILL_IN |
| Staleness weight | +10% | FILL_IN % | FILL_IN |
| Staleness weight | -10% | FILL_IN % | FILL_IN |
| Decay parameter | +20% | FILL_IN % | FILL_IN |
| Decay parameter | -20% | FILL_IN % | FILL_IN |
| max_terms | +5 (25 terms) | FILL_IN % | FILL_IN |
| max_terms | -5 (15 terms) | FILL_IN % | FILL_IN |
| Thresholds | ±5 pts | FILL_IN % | FILL_IN |

#### 5B — Entropy vector (computed from corpus by entropy.py)

| Parameter | Perturbation | Flip rate | Flag? |
|---|---|---|---|
| Deprecation weight | +10% | FILL_IN % | FILL_IN |
| Deprecation weight | -10% | FILL_IN % | FILL_IN |
| Severity weight | +10% | FILL_IN % | FILL_IN |
| Severity weight | -10% | FILL_IN % | FILL_IN |
| Count weight | +10% | FILL_IN % | FILL_IN |
| Count weight | -10% | FILL_IN % | FILL_IN |
| Staleness weight | +10% | FILL_IN % | FILL_IN |
| Staleness weight | -10% | FILL_IN % | FILL_IN |

**Acceptance:** flip rate < ~15% = robust. Higher → raise with developer before signing.  
**Note:** File A §12 `sensitivity.py` sweeps ±10–20% per-weight perturbation (renormalized), both vectors, plus `rollup.decay`, `max_terms`, and thresholds ±5 — all of these are required in this sign-off.

**Overall flip rate assessment:** FILL_IN  
**Any single parameter driving > 20% flips?** YES (name it: FILL_IN) / NO


---

### Check 6 — Final weight vectors sanity

Final vectors published by the tool (both ecosystems):

| Ecosystem | Deprecation | Severity | Count | Staleness | Sum | Any weight ≈ 0 or ≈ 0.8? |
|---|---|---|---|---|---|---|
| npm | FILL_IN | FILL_IN | FILL_IN | FILL_IN | FILL_IN | FILL_IN |
| PyPI | FILL_IN | FILL_IN | FILL_IN | FILL_IN | FILL_IN | FILL_IN |

**Each vector sums to 1.00 ± 0.01:** PASS / FAIL  
**Any degenerate weight (≈ 0 or ≈ 0.8) requiring justification:** YES (note: FILL_IN) / NO

**Calibration parameters confirmation** (must match what was tested in Check 5):  
`rollup.decay`: FILL_IN (expected 0.5) | `rollup.max_terms`: FILL_IN (expected 20) | `thresholds.safe_min`: FILL_IN (expected 80) | `thresholds.medium_min`: FILL_IN (expected 50)

---

## Overall sign-off decision

- [ ] Check 1 (CR < 0.10): PASS
- [ ] Check 2 (all anchors ≥ Medium): PASS — **hard gate**
- [ ] Check 3 (AHP vs entropy acknowledged): noted
- [ ] Check 4 (correlation present and caveat in report): PASS
- [ ] Check 5 (sensitivity acceptable): PASS
- [ ] Check 6 (vectors sum to 1, non-degenerate): PASS

**Sign-off status:** PENDING  
**Signed by (teammate):** ________________  
**Date signed:** FILL_IN

> Signing this document authorises the developer to ship `weights_v2.yaml` and close Phase 12.  
> A signed copy with all cells filled is the deliverable. Do not sign with any cell empty or any hard-gate failing.

---

## Handoff

- [ ] `validation_report/` folder copied to deliverables zip
- [ ] This sign-off (with all cells filled) included in zip
- [ ] Zipped as `WP6_YYYYMMDD.zip` and sent to developer
