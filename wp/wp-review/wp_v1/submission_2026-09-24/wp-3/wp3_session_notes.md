# WP-3 Session Notes

**Session date:** 2026-09-23  
**Participants:** Teammate (Judge A), Developer (Judge B)  
**Venue:** Joint video call, ≈ 2 hours  
**Deliverables produced in this session:** `wp3_matrix_A.csv`, `wp3_matrix_B.csv`, `wp3_matrix_reconciled.csv`, this note.

---

## Protocol followed

Judges filled their matrices independently before the call — no verbal exchange until both matrices were submitted. The consistency tool was run on each matrix before any reconciliation discussion began. Divergent cells (differing by ≥ 2 Saaty steps) were identified automatically and discussed one at a time. The geometric-mean merge was the default resolution rule; either judge could accept or request a re-judgment, but a re-judgment required articulating a new argument not made during independent filling.

**Independence qualification (must be stated in the S1 paper's methodology section):** Judge A's matrix was prepared with prior knowledge of the WP-1 seed matrix values, which were also adopted unmodified in WP-1. Judge A's fill should therefore be characterised as a *knowledge-informed independent review* rather than a fully blind fill from a blank slate. The independence in this session is primarily between the two judges' on-the-day judgments — particularly on the two divergent cells — not between Judge A's current judgments and the WP-1 seed. Judge B had no prior knowledge of the WP-1 seed values and filled a blank matrix. The WP-3 AHP session's primary methodological contribution is the two-judge divergence check, the consistency ratio verification, and the geometric-mean reconciliation — not the absolute values of Judge A's matrix. Papers citing this session must state this limitation.

---

## Consistency check results

| Matrix | λ_max | CI | RI (n=4) | CR | Status |
|---|---|---|---|---|---|
| A (Judge 1) | 4.035 | 0.0117 | 0.90 | **0.013** | ✅ < 0.10 |
| B (Judge 2) | 4.156 | 0.0520 | 0.90 | **0.058** | ✅ < 0.10 |
| Reconciled  | 4.078 | 0.0260 | 0.90 | **0.029** | ✅ < 0.10 |

*Note: WP-1 YAML header records CR = 0.0115 for Matrix A (computed with higher decimal precision). The session notes table uses CR = CI/RI = 0.0117/0.90 = 0.013, rounded to 3 significant figures. Both refer to the same matrix; the tool will report its own computed value — expect either 0.011–0.013 depending on rounding. This is not a discrepancy in the matrix itself.*

No matrix required a re-judgment round to pass the CR threshold.

---

## Divergent cells (≥ 2 Saaty steps apart) — discussion record

### Cell 1: Deprecation vs Staleness  (A = 4, B = 2)

**Judge A's position:** An explicit maintainer declaration ("this package is deprecated — migrate to X") carries zero ambiguity; staleness is only an abandonment *proxy* — the staleness clock can be running while the package is actively used in stable form by a large community. The directness gap justifies a wide dominance score (4).

**Judge B's position:** Real-world triage experience suggests that a 3+ year stale package with no CVEs causes exactly the same downstream alert as a deprecated one. The gap between a 4-year-silence package and one the maintainer explicitly called out is much narrower in practice than 4 implies, especially when the deprecation notice contains no successor recommendation.

**Resolution:** Judge B's counter-examples were examined — they all involved very long staleness (≥3 years) and no successor named. For the *full* staleness distribution (90 days to 1,095+ days) a narrower dominance is more calibrated. The geometric mean of 4 and 2 is 2.83, accepted. Both judges note this is a limitation (the correct judgment likely depends on staleness thresholds, which the formula's `stale_flag_days` parameter partially controls).

### Cell 2: Severity vs Count  (A = 2, B = 4)

**Judge A's position:** A long tail of CVSS 5–6 vulnerabilities (count = 8–10) is collectively as operationally disruptive as a single CVSS 9.x finding. Strong dominance (4) overstates severity's advantage across the realistic corpus distribution.

**Judge B's position:** In incident response, a CVSS ≥ 9 finding escalates to P0 regardless of everything else. Count is a secondary breadth signal; it should never be rated near severity. Strong dominance (4) is the correct call.

**Resolution:** Both examples represent real scenarios but at extremes of the score space. The formula already handles the CVSS 9 case well because the severity *score* will be near 1.0 (post-normalisation) regardless of weight, so the practical difference between w=2 and w=4 on a maxed-severity item is small. The disagreement is most consequential for mid-CVSS items — where the corpus likely concentrates — and there Judge A's more conservative reading is defensible. Geometric mean of 2 and 4 = 2.83, accepted.

---

## Minor divergence — noted, not discussed

**Deprecation vs Severity (A = 2, B = 1):** Differ by 1 step, below the discussion threshold. Judge B rates the two signals as equal from a triage urgency standpoint; Judge A gives deprecation a slight edge because it carries zero exploitability uncertainty. Geometric mean = 1.41 — deprecation holds a slight but non-decisive advantage. Both judges find this acceptable.

---

## EPSS decision

Discussed whether to produce a 5×5 matrix including EPSS (exploit likelihood score from FIRST.org). Decision: **EPSS deferred from AHP.** Neither judge can judge the EPSS signal meaningfully relative to the other four without empirical calibration — the signal exists in the codebase (D3, behind a feature flag) and is collected at scan time, but its inclusion in the formula requires a separate Tier-3 derivation using the corpus data. The reconciled 4×4 matrix is the Tier-2 deliverable; EPSS is named as future work in both the S1 paper's limitations section and the formula's YAML (`epss.enabled: false`).

---

## Rationale summary for top-2 debated judgments

**Deprecation vs Staleness (resolved at 2.83):** The core tension is *certainty* (explicit maintainer declaration) vs *prevalence* (stale packages are far more common in the corpus than actively deprecated ones). A very wide dominance score (4+) would cause the formula to classify a deprecated-but-well-maintained package as High while rating a 4-year-silent package only as Medium, which is arguably backwards for the silent-but-active case. The geometric mean preserves deprecation's lead without producing that anomaly.

**Severity vs Count (resolved at 2.83):** The resolution rests on a claim about corpus composition: if the corpus contains many packages with CVSS 7–8 scores and counts of 3–6 (the expected modal case), a weight ratio of 2.83 produces scores that degrade proportionally with both signals. At the extremes (CVSS 10 singleton vs count 15 at CVSS 4) the formula's normalisation functions matter more than the weight ratio — so the disagreement between 2 and 4 is mostly felt in the middle of the distribution, which is exactly where calibration matters most.

---

## Final weight vectors derived from reconciled matrix

*Computed via principal eigenvector of `wp3_matrix_reconciled.csv`; verified against column-normalisation approximation.*

**npm (from reconciled 4×4 matrix):**

| Signal | Weight |
|---|---|
| Deprecation | 0.401 |
| Severity | 0.336 |
| Count | 0.154 |
| Staleness | 0.109 |
| **Sum** | **1.000** |

**PyPI (same AHP session, reasoned redistribution — same method as WP-1, applied to Tier-2 base):**  
PyPI's deprecation signal (per-release yanking + rarely-applied Inactive classifier) carries less information than npm's free-text deprecation message. The same redistribution argument from `wp1_method_note.md` applies: deprecation weight reduced by approximately 35% (0.401 → 0.26), mass redistributed to severity and staleness. The redistribution percentage is slightly larger than WP-1's 30% reduction (0.46 → 0.32) because the Tier-2 npm reconciled base assigns more weight to deprecation (0.401) than Tier-1 (0.46 — counterintuitively, the reconciled matrix narrowed D vs S from 2 to 1.41, so deprecation fell), meaning the same absolute redistribution represents a proportionally larger percentage of the base. The PyPI percentage was re-evaluated against the Tier-2 base rather than mechanically inherited from Tier-1.

| Signal | Weight |
|---|---|
| Deprecation | 0.26 |
| Severity | 0.43 |
| Count | 0.15 |
| Staleness | 0.16 |
| **Sum** | **1.00** |

*Note: The PyPI vector is still derived from the same session by reasoned redistribution, not from an independent PyPI-only AHP calibration (limitation L4 in File C). The S1 PyPI sanity sub-analysis (File C §2.4.6) is the mitigation and S3's trust gate.*

---

## Comparison: Tier-1 (WP-1) vs Tier-2 (WP-3) weight vectors

| Signal | npm v1 (WP-1) | npm v2 (WP-3) | PyPI v1 (WP-1) | PyPI v2 (WP-3) |
|---|---|---|---|---|
| Deprecation | 0.46 | 0.40 | 0.32 | 0.26 |
| Severity | 0.28 | 0.34 | 0.35 | 0.43 |
| Count | 0.16 | 0.15 | 0.16 | 0.15 |
| Staleness | 0.10 | 0.11 | 0.17 | 0.16 |

The Tier-2 process shifted mass from deprecation toward severity — driven primarily by the D vs Severity cell (A=2, B=1 → reconciled 1.41) and the S vs Count cell (reconciled to 2.83 from A=2). Signal ranking is preserved in npm (Dep > Sev > Count > St) and nearly preserved in PyPI (Sev > Dep > Count ≈ St), consistent with the intent of both derivations.
