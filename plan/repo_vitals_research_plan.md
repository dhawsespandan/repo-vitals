# RepoVitals — Research Execution Plan (File C)

**Status of this document.** Files A, B, and C together supersede and replace every earlier project document. File C governs everything after engineering ends: analysis, drafting, submission, and revision for the three studies. **Work in this file starts only when File A is complete through `v1.0.0` and File B's WP-1…WP-9 are delivered** (WP-10 is the one time-gated exception, handled in §0.2). From this point the project produces papers, not code — if an analysis seems to need new engineering, the correct response is to re-read §2.1 (almost everything is recomputable from stored signals) and only then, as a last resort, treat it as a scoped exception.

**The three studies:**

- **S1 — Validated deterministic scoring** (was "13.3"): is the AHP-derived, entropy-cross-checked risk formula internally consistent, externally convergent, and robust?
- **S2 — Dependency risk as a stochastic process** (was "13.2"): can repository risk transitions and time-to-vulnerability be modelled from reconstructed longitudinal data, and does a forward-looking model beat the static score at anticipating risk?
- **S3 — Retrieval grounding across ecosystems** (was "13.1"): does retrieval grounding improve remediation correctness/faithfulness, and does quality degrade when the ecosystem's deprecation metadata carries less information (PyPI vs npm)?

Plus an optional quick win: **P0 — a tool/demo paper** describing the system itself.

---

## 0. Prerequisites and inputs

### 0.1 Artifact inventory (produced by Files A + B; verify all exist before starting)

| Artifact | Producer | Consumed by |
|---|---|---|
| `research_data/exports/scan_history.parquet` | File A `export_research_data` | S1, S2 |
| `research_data/exports/dependency_history.parquet` | same | S1, S2 |
| `research_data/exports/agent_traces.parquet` | same | S3 |
| `research_data/exports/live_scans_cohort.parquet` | same (prod) | S2 (validation) |
| `research_data/corpus/corpus_manifest.json` + `strata_report.md` | WP-4 | S1, S2 (sampling frame) |
| `backend/weights/weights_v1.yaml`, `weights_v2.yaml` | WP-1, WP-6 | S1, S2 |
| `research_data/validation_report/` | WP-6 (Phase 12 harness) | S1 |
| WP-3 matrices + session notes | WP-3 | S1 (methodology section) |
| `wp2_anchor_set.csv` + anchor results | WP-2 / Phase 12 | S1 |
| `research_data/runs/` (conditions A/B/C[,D] × 150) + `wp8_run_log.md` | WP-8 | S3 |
| `labelled_set.jsonl` (+ extraction coverage rate) | Phase 13 | S3 |
| `wp9_judge_labels.csv` + kappa output | WP-9 / Phase 13 | S3 |
| `wp7_cohort_tracker.csv` (with consent column) | WP-7 | S2 |
| WP-10 agreement report | WP-10 | S2 (submission gate) |
| `notebooks/13_1_analysis`, `13_2_markov_hazard`, `13_3_validation` | Phase 14 | all — the analysis homes |
| `REPLICATION.md` + pinned lockfiles + `docs/adapter_soundness.md` | Phase 14 / Phase 6 | all papers' artifact packages |

### 0.2 Execution order and why

**S1 → S2 → S3**, overlapping where §9's timeline allows.

S1 first: its analysis is already materialized by the Phase 12 harness (the study is largely *interpretation and writing*), it carries no time gate, and it produces two things the other studies consume — the validated weights narrative, and the **PyPI trust gate** (§3.6) that S3 requires. S2 second: its modelling is the heaviest analysis, and its submission (not its analysis) is gated on WP-10, which is time-locked by the cohort calendar — start the modelling immediately, draft everything except the validation subsection, and slot WP-10 in when it lands. S3 last: it needs S1's trust gate to interpret the PyPI arm, and its runs (WP-8) are already done by Phase 14.

P0 (tool paper) can be drafted at any point after File A completes — it depends on nothing in this file.

---

## 1. Shared foundations (read before any study)

### 1.1 The recomputation principle

Stored history scores exist for product display. **Every research analysis recomputes scores from stored raw signals** (`dependency_history` columns) under an explicitly declared weights version, using the same pure functions the product uses (exposed to the notebooks). Consequences: any study can be run under v1 and v2 weights to show robustness of conclusions to the weighting; no analysis ever mixes scores computed under different formula versions without saying so; and a reviewer request like "what if staleness were weighted double?" is a notebook cell, not a data-collection round.

### 1.2 The two data sources never blend silently

`data_source ∈ {live_scan, backfill}` separates reconstructed history from observed reality. Default analysis posture: fit on backfill, validate on live. Any table or figure that pools them must say so explicitly. The product's cohort rows are additionally filtered to `consent_ok = yes` recruits only (via the WP-7 tracker).

### 1.3 Sampling weights

The corpus deliberately oversampled stale repositories (File A D14). Every population-level estimate from corpus data (transition probabilities, hazard rates, score distributions) is reported **weighted** (using `sampling_weight`) with the unweighted version in an appendix. Stratum-conditional analyses (e.g. "among repos untouched for 4+ years…") need no reweighting within the stratum. State this in each paper's methodology.

### 1.4 Reproducibility rules (all studies)

Notebooks are the single home of analysis — no untracked side scripts; every figure/table in a paper regenerates from a notebook cell reading only §0.1 artifacts. Seeds fixed and printed in every notebook. Bootstrap iterations ≥ 2,000, seeded. Statistical software versions pinned (`requirements-research.txt`, committed). Each paper ships the replication package: `REPLICATION.md` + relevant exports + the notebook — assembled per-paper in §8.4.

### 1.5 Ethics and consent

All corpus data is public repository metadata and manifests — no human subjects, no personal data beyond public GitHub usernames, which are stored only in research tables and **anonymized before any per-repo example appears in a paper** (refer to corpus repos by stratum + anonymized id; naming a specific public repo is acceptable only for well-known anchor examples like `request`, where the point is that it's famous). Cohort participants: consent recorded in the tracker (WP-7); aliases only; their repos are never named in any paper; any participant may withdraw → their rows are dropped from analysis sets (the permanent tables keep the rows — the manual-anonymization posture from File A D9 — but analysis exports exclude them).

### 1.6 Consolidated limitations register (every paper draws its threats-to-validity from here)

| # | Limitation | Affects | Handling in papers |
|---|---|---|---|
| L1 | Deprecation/yank events are not timestamped by registries → treated as time-invariant in backfill | S2 | primary datable event = CVE disclosure; deprecation enters as a fixed covariate; stated explicitly |
| L2 | Reconstruction is "risk as now known to have existed then," not "as knowable then" (OSV entries can be added/edited retroactively) | S2 | framed as standard practice for disclosure-dated reconstruction; WP-10 validates the recent window empirically |
| L3 | OSV feeds two of four formula signals → OSV-rollup reference is partially circular | S1 | deps.dev Scorecard is the primary reference; circular one reported with the caveat, never alone |
| L4 | deps.dev Scorecard measures repo health *practices*, not dependency risk — an independent but different construct | S1 | framed as convergent validity (moderate positive correlation expected), not ground truth |
| L5 | No real-world exploitation ground truth anywhere | S1, S2 | stated; EPSS collected as future signal |
| L6 | PyPI weight vector derived by reasoning + the same AHP session, not an independent PyPI-only calibration | S1, S3 | the S1 PyPI sanity sub-analysis (§3.6) is the mitigation and S3's gate |
| L7 | Judge is an LLM; validated on 50 human-labelled items only | S3 | kappa reported; conclusions qualified by it; disagreement analysis included |
| L8 | Ground-truth extraction covers only automatable cases (~60–70% expected); the remainder is dropped | S3 | coverage rate reported; selection-bias paragraph |
| L9 | Case-type mix differs by ecosystem (PyPI's replacement stratum thin) | S3 | the stratified design (§5.3) is the control; cve_fix stratum is the head-to-head |
| L10 | Single LLM generator (Groq Llama), single embedding model | S3 | scoped claim ("for this model class"); generalization = future work |
| L11 | Corpus is GitHub-only, JS/TS + Python only, ≥5 stars | S1, S2 | external-validity paragraph |
| L12 | Cohort is small (~8–10 users, ~30 repos) and student-drawn | S2 | used for reconstruction validation, not population estimates |
| L13 | Tree-truncation on ~100k-entry repos; manifest-only analysis (no transitive deps, no call sites) | all | scope statements |
| L14 | Free-tier infrastructure (rate pacing shaped run schedules) | S3 | noted in replication package; no effect on results validity |

---

## 2. Study S1 — A validated, explainable deterministic scoring methodology

### 2.1 Positioning

**Contribution:** a documented, auditable weight-derivation pipeline for dependency-risk scoring — AHP (subjective, consistency-checked) cross-validated by entropy weighting (objective, variance-derived from ~1,000 repositories), externally checked against an independent reference, stress-tested by perturbation, and floor-checked by known-bad anchors — plus the two-level scoring design (per-occurrence formula + rank-decayed roll-up) with proven non-dilution properties. Not claimed: outperforming commercial scanners on coverage. The honest comparison class is *scoring methodology transparency*, where npm audit/Dependabot/Snyk publish nothing reviewable.

### 2.2 Research questions and hypotheses

- **RQ1 (internal coherence):** do independently derived subjective (AHP) and objective (entropy) weight vectors agree? *H1: cosine similarity ≥ 0.90 and identical top-2 signal ranking.*
- **RQ2 (external convergence):** does the formula's repo score correlate with an independent repo-health reference (deps.dev/OpenSSF Scorecard)? *H2: positive, moderate (Spearman ρ ∈ [0.3, 0.6]) — deliberately not high, different construct (L4).*
- **RQ3 (robustness):** do classifications survive weight/parameter perturbation? *H3: bucket-flip rate < 15% under ±20% perturbation, under both vectors.*
- **RQ4 (sanity floor):** do known-bad anchors classify ≥ Medium? *H4: 100% of known anchors.*
- **RQ5 (ecosystem transfer):** does the PyPI vector behave sanely on PyPI data (the trust gate, §3.6)?

### 2.3 Data

`validation_report/` (primary — the Phase 12 harness already computed everything), corpus panel (current-month cross-section, weighted per §1.3), anchor results, WP-3 matrices + notes, `13_3_validation` notebook.

### 2.4 Analysis plan with decision rules

1. **Weight derivation narrative:** reconciled matrix, eigenvector, CR (< 0.10 by construction — report the value), the divergent-cell reconciliation story from WP-3 notes (reviewers reward this honesty).
2. **RQ1:** cosine + Spearman rank agreement between vectors, per ecosystem. Bands: ≥0.90 strong / 0.75–0.90 partial (discuss which signal diverges and why — variance-driven entropy *should* differ where a signal is rare-but-decisive, e.g. deprecation; this is an interpretable finding, not a failure) / <0.75 report as a genuine tension and lead the discussion with it.
3. **RQ2:** Spearman (primary; monotone relation suffices) + Pearson vs Scorecard, with bootstrap CIs (cluster = repo); scatter figure; same vs OSV rollup with the L3 caveat sentence adjacent to the number, not buried.
4. **RQ3:** flip-rate table: per-weight ±10/±20%, both vectors, plus `decay`, `max_terms`, thresholds ±5. Any single parameter driving >20% flips gets a dedicated discussion paragraph.
5. **RQ4:** anchor table (every anchor, seeded bucket, score, class). One failing anchor = the paper explains the failure mechanism or the formula is revisited *before* submission — no silent exclusions.
6. **RQ5 (PyPI sanity / S3 trust gate):** on the PyPI corpus stratum + PyPI anchors: score distribution not degenerate (uses the full range; classes populated), anchors pass, and the roll-up behaves identically to npm's on matched dependency-count strata. **Gate rule:** pass → S3's PyPI arm is interpretable; fail → fix the PyPI vector (re-run WP-6 path) before S3 analysis, and say so in both papers.
7. **Robustness rerun under v1 weights** (recomputation principle): conclusions that survive both weightings are marked as such.

### 2.5 Paper skeleton (8 pages + refs, conference format)

Intro (scoring tools are black boxes; auditable alternative) → Related work (MCDM/AHP+entropy precedent, dependency-risk scoring, OpenSSF) → System context (2 col-inches: pipeline, signals, two-level scoring with the non-dilution property stated formally) → Methodology (AHP session protocol, entropy, references, perturbation) → Results (RQ1–RQ5) → Threats (L3, L4, L5, L6, L11, L13) → Future (EPSS, Road-A validation, learned interactions) → Conclusion. **Figures:** weight-vector comparison chart; correlation scatter; sensitivity heat/flip table; anchor table.

### 2.6 Venue path and effort

Primary: ICSME or SANER (technical track); alternate MSR. Journal step-up if results are strong: EMSE/JSS. Step-down: national conference / student symposium. Effort: **2–3 weeks** (analysis is mostly reading the harness output; writing dominates).

---

## 3. Study S2 — Dependency risk as a stochastic process (the flagship)

### 3.1 Positioning

**Contributions (three, any two suffice for a strong paper):** (a) a *validated reconstruction method* — building multi-year monthly dependency-risk panels from public records (manifest git history × OSV disclosure dates × registry publish dates), validated against prospective live scans; (b) *empirical transition dynamics* of repository risk (Markov analysis, npm vs PyPI); (c) *forward-looking risk modelling* — hazard models over per-dependency covariates that anticipate risk the static score only reports after the fact. MSR-shaped: mining + method + empirical findings.

### 3.2 Research questions

- **RQ1 (reconstruction validity):** how closely do backfill-reconstructed recent months match prospective live scans? (WP-10; kappa + attributed deltas.)
- **RQ2 (dynamics):** what are the Safe/Medium/High-Alert transition probabilities per month? Do they differ by ecosystem, repo size, activity stratum? Practical form: "given Medium today, P(High-Alert within 3 months)?"
- **RQ3 (hazard):** which dependency-level covariates (staleness, versions-behind, deprecation, ecosystem, dependency count) predict time-to-first-CVE-disclosure?
- **RQ4 (anticipation):** does a fitted forward-looking model predict next-quarter High-Alert entry better than the current static score alone?

### 3.3 Data

Backfill panel: ~59k weighted repo-months (`scan_history`, `data_source='backfill'`) and ~2–4M dependency-month rows (`dependency_history`) over 60 months; cohort live waves (validation only, per §1.2, consented rows); WP-10 report; `13_2_markov_hazard` notebook.

### 3.4 Methods, exactly

**RQ1 — reconstruction validation.** From the WP-10 report: per-repo-month classification agreement (Cohen's kappa; prespecified adequacy: κ ≥ 0.75 = strong support; 0.6–0.75 = usable with the disagreement-attribution table front and center; < 0.6 = the reconstruction section becomes the paper's main caveat and RQ2–4 claims are correspondingly softened — decide the framing from the number, never hide it), score-delta distribution (median absolute delta), and the per-signal attribution table (L1 should dominate; unexplained drift → investigate before drafting).

**RQ2 — Markov analysis.** Unit: repo-month pairs (t, t+1), backfill only, weighted (§1.3). Estimate the 3×3 transition matrix by MLE (row-normalized weighted counts); CIs by cluster bootstrap (resample *repos*, 2,000 iterations). Report: matrix per ecosystem + pooled; 3-/6-/12-month powers for the practical questions; expected sojourn times per state. Checks: **time-homogeneity** — split the window into two eras, compare matrices (bootstrap test on cell differences); if inhomogeneous, report era-specific matrices rather than a misleading pooled one. **Ecosystem difference:** cell-wise bootstrap difference CIs. Exploratory Bayesian variant (fits the "stochastic modelling" framing cheaply): Dirichlet(1,1,1) prior per row → posterior credible intervals alongside the bootstrap CIs.

**RQ3 — hazard modelling.** Unit: dependency-spell — a (repo, package, manifest) occurrence from first appearance in the panel until first CVE disclosure affecting its resolved version (event) or panel end / removal from manifest (right-censored). Time scale: months since first appearance. Model: Cox proportional hazards with covariates staleness (time-varying, monthly), versions_behind_major (time-varying), is_deprecated (fixed, L1), ecosystem, log dependency-count of the host repo; **cluster-robust SEs by repo** (dependencies within a repo are correlated). Diagnostics: Schoenfeld residuals for PH; violations → stratify or report time-varying coefficients. Descriptive companions: Kaplan-Meier curves by staleness band and by ecosystem. Report hazard ratios with CIs; effect sizes in plain language ("a dependency ≥2 majors behind has ×H the monthly hazard of a current one").

**RQ4 — anticipation test.** Temporal split: fit RQ2/RQ3 models on months 1–48; predict months 49–60. Task: repo-month → P(enter High-Alert within 3 months). Baseline: logistic on current static score alone. Comparison: AUC + Brier, cluster-bootstrap CIs on the difference. Honest framing: the static score is *designed* to be a present-state audit, not a forecaster — RQ4 quantifies what forward-looking modelling *adds*, it doesn't dunk on the score.

**Robustness:** rerun RQ2 headline cells and RQ3 coefficient signs under v1 weights (classification thresholds shift with weights; the recomputation principle makes this one notebook cell); report "conclusions unchanged/changed."

### 3.5 Paper skeleton (10–11 pages, MSR/ICSME technical)

Intro (risk is reported statically; dynamics unknown; reconstruction unlocks them) → Related (mining package ecosystems, vulnerability lifecycle studies, survival analysis in SE) → Reconstruction method (the star: as-of semantics, L1/L2 upfront, validation design) → Dataset (corpus frame, strata, weights; descriptive stats) → RQ1 results → RQ2 → RQ3 → RQ4 → Threats (L1, L2, L5, L11, L12, L13) → Implications (for tools: when to alert; for maintainers: what predicts trouble) → Conclusion. **Figures:** reconstruction-agreement plot; transition diagram with probabilities; KM curves; hazard-ratio forest plot; AUC comparison.

### 3.6 Gates and effort

Analysis starts immediately after prerequisites; **submission blocked on WP-10** (and on κ handling per RQ1 rule). The S1 PyPI trust gate (§2.4.6) also conditions any ecosystem-difference claims here. Effort: **4–6 weeks** analysis + drafting; the heaviest study.

### 3.7 Venue path

Primary: **MSR technical track**. Alternates: ICSME, SANER. Journal extension: EMSE (add eras, more covariates, Bayesian elaboration). Step-down: ESEM registered-report style, then national venues.

---

## 4. Study S3 — Retrieval grounding across ecosystems

*(Numbered §5.x tables in some tools; here §4 = S3 throughout.)*

### 4.1 Positioning

**Contribution:** a controlled, paired comparison of no-retrieval vs single-source RAG vs branching-agent RAG for dependency remediation, across two ecosystems whose deprecation metadata differs in *information content* (npm's free-text successor-naming messages vs PyPI's terse/empty yank reasons) — with deterministic correctness ground truth, a human-validated automated faithfulness judge, and full traces published. The ecosystem-metadata angle and the deterministic correctness metric are the differentiators in a crowded RAG-evaluation field.

### 4.2 Research questions

- **RQ1:** does retrieval grounding (B) improve remediation correctness and faithfulness over no-retrieval (A)?
- **RQ2:** does the branching agent (C) add anything over fixed-framing RAG (B)? (The "was the agent complexity warranted?" question — a null here is a publishable, honest answer.)
- **RQ3:** do correctness/faithfulness differ between npm and PyPI, controlling for case type — i.e., does poorer deprecation metadata degrade grounded remediation?
- **RQ4 (if condition D was run):** does broader retrieval (issues/discussions) recover PyPI's gap?

### 4.3 Design (fixed by Files A/B; restated for the record)

150 items (75/75 npm/PyPI), stratified `cve_fix` vs `deprecation_replacement` (quotas recorded at sampling; PyPI's replacement stratum expectedly thin — **the cve_fix stratum is the controlled ecosystem head-to-head**, L9). Same item → all conditions (paired design). Generator: Groq Llama, temp 0. Judge: Gemini (different provider), validated by WP-9's 50-item kappa. Metrics: correctness (deterministic version/replacement match — no LLM), faithfulness (3-level ordinal via judge), retrieval precision@k (judged chunk relevance, B/C/D).

### 4.4 Analysis plan with decision rules

1. **Judge credibility first:** report WP-9 kappa + the disagreement listing. Prespecified: κ ≥ 0.70 → judge verdicts used as-is; 0.5–0.7 → all faithfulness results additionally reported on the human-labelled 50 and claims softened; < 0.5 → tighten rubric, re-judge, re-validate (File B anticipated this loop).
2. **Correctness (binary):** per condition-pair, per ecosystem: **McNemar exact test** on paired outcomes; effect size = discordant-pair odds ratio + absolute correctness-rate difference with bootstrap CI.
3. **Faithfulness (ordinal):** paired **Wilcoxon signed-rank** per condition-pair per ecosystem; effect size = matched rank-biserial. Also report the `major_unsupported` *rate* per condition — hallucinated core claims are the practically fatal category and deserve their own table.
4. **Precision@k:** means with cluster-bootstrap CIs (cluster = item), B vs C (vs D).
5. **Multiplicity:** Holm correction within each metric's family of condition-pair tests; ecosystem comparisons are a separate prespecified family.
6. **RQ3 properly:** ecosystem contrast **within cve_fix stratum** (matched availability) is the headline; full-set contrast reported second with the case-mix caveat (L9). Interaction check: condition × ecosystem (does grounding help PyPI *more* — compensating for weak metadata — or *less* — nothing good to retrieve? Either direction is a finding).
7. **Insufficient-information behavior:** rate at which C declares insufficient information, by ecosystem, cross-tabbed with whether its grounding-confidence flag was low — honesty calibration of the deterministic check (traces make this free).
8. **Null-result rule:** every RQ's answer is reported at face value with CIs; the paper's value proposition (controlled design + traces + validated judge) survives any direction of result. No post-hoc metric shopping: metrics and tests above are the prespecified set; anything else is labelled exploratory.
9. **Qualitative slice:** 6–10 trace-backed examples (one per interesting cell: grounded-and-correct, grounded-but-wrong, honest-abstention, hallucinated-replacement…) — RAG papers live and die on these.

### 4.5 Paper skeleton (10 pages)

Intro (flag→fix gap; grounding hypothesis; ecosystem-metadata angle) → Related (RAG evaluation, LLMs for vulnerability repair, agentic SE + "Agentless" line) → System + conditions (graph figure; D13 posture for condition D) → Ground truth + judge (extraction coverage L8; WP-9 protocol + kappa) → Results (RQ1–4) → Qualitative analysis → Threats (L6→gate outcome, L7, L8, L9, L10, L14) → Implications (when is retrieval worth it; what registries should put in deprecation metadata — a concrete, citable recommendation: *structured successor fields*, which NuGet already has) → Conclusion. **Figures:** condition × ecosystem correctness/faithfulness bars with CIs; case-type breakdown; insufficient-information calibration table; example traces.

### 4.6 Gates, effort, venue

Gates: S1's PyPI trust gate passed (§2.4.6); WP-8/WP-9 in hand. Effort: **3–4 weeks**. Venue: MSR (primary), alternates ICSME/SANER; AI-for-SE venues (CAIN, AIware) as strong alternates; journal EMSE. Step-down: workshops co-located with the above, then national venues.

---

## 5. P0 — Optional tool/demo paper (quick win)

4-page tool-track paper (MSR/ICSME/SANER demo tracks) or student symposium entry: the system, the two-level explainable scoring, the grounded-report UX (screenshot of the citation pane), the adapter-soundness evidence (`docs/adapter_soundness.md`), the research instrumentation posture (permanent traces/history). Material: Phase 14's demo script + existing figures. Effort: 3–4 days, any time after File A completes. Value: an early publication line on the CV, a citable system reference for S1–S3, and seminar collateral.

---

## 6. Writing and submission logistics

**Order of drafting:** S1 → S2 (minus validation subsection) → WP-10 lands → finish S2 → S3. P0 opportunistically.

**Shared-text policy:** each paper describes the system independently in its own words (2–3 paragraphs max, citing P0 if published); never paste system sections between papers (self-plagiarism risk at journals); the scoring formula and graph figure may be reused as *figures* with consistent notation.

**Preprints:** put each paper on arXiv at submission time unless the target venue forbids it (most SE venues allow; double-blind venues require the anonymized version + delayed arXiv — check the specific CFP).

**Anonymization for double-blind:** repo URL scrubbed from the PDF; replication package via anonymized artifact link (Zenodo anonymous or the venue's artifact channel); the live demo URL goes only in camera-ready.

**Authorship & acknowledgment:** both team members on all papers (developer: system + analysis; teammate: methodology judgments, labelling, runs — genuine contributions on any criteria); mentor/guide per institutional norms — ask them early, not at camera-ready.

**Review-cycle plan:** expect rejection as the modal first outcome at primary venues; every review is mined into a revision matrix (comment → change → where) before resubmitting down the ladder; a paper never gets resubmitted unchanged.

**Venue calendars change — do not trust remembered deadlines.** At execution time, check each venue's current CFP for dates, page limits, and artifact/badging tracks. The ladder in §2.6/§3.7/§4.6 is the route; the calendar is looked up fresh.

### 6.4 Per-paper replication package (assembled from Phase 14 materials)

Each submission's artifact = the study's notebook + only the exports it reads + `REPLICATION.md` excerpt + seeds/versions + (S3) prompts, judge rubric, labelled set, WP-9 labels + (S2) corpus manifest + WP-10 report + (S1) matrices, session notes, validation report. Target the venue's artifact-evaluation badge where offered — this project was built to earn it.

---

## 7. Decision checkpoints (pre-registered, so results don't bend the rules)

| Checkpoint | Rule already fixed above |
|---|---|
| S1 anchors fail | explain mechanism or revisit formula **before** submission (§2.4.5) |
| S1 AHP-entropy disagree (<0.75) | lead the discussion with it; still publishable (§2.4.2) |
| PyPI trust gate fails | fix vector via WP-6 path before S3 analysis; disclose in both papers (§2.4.6) |
| WP-10 κ < 0.6 | reconstruction caveat becomes S2's centerpiece; RQ2–4 claims softened (§3.4) |
| Judge κ < 0.5 | tighten rubric, re-judge, re-validate before any S3 claims (§4.4.1) |
| Any RQ null | report at face value; framing already null-proof (§4.4.8; §3.4 RQ4 framing) |
| Reviewer asks for reweighted analysis | notebook cell via recomputation principle (§1.1) — never new data collection |

---

## 8. Timeline (relative weeks after prerequisites; overlaps intended)

| Weeks | Work |
|---|---|
| 1–3 | S1 analysis + full draft; P0 drafted in parallel if desired |
| 2–7 | S2 modelling (RQ2–4), draft minus validation subsection |
| WP-10 lands | S2 RQ1 section + final framing pass; submit-ready |
| 6–9 | S3 analysis + draft (after S1 gate) |
| ongoing | submissions per current CFPs; revision matrices on returns |

Total: roughly 8–10 working weeks of analysis + writing for all three, plus review cycles.

---

## 9. Definition of done (research phase)

1. Three notebooks fully regenerate every number and figure in their papers from §0.1 artifacts alone.
2. S1, S2, S3 drafted, internally reviewed (each author reads the other's paper adversarially once), and submitted to their primary venues; P0 decision made either way.
3. Every §7 checkpoint outcome documented in the paper it affects.
4. Replication packages archived (Zenodo or equivalent) with DOIs at first acceptance.
5. The revision matrix process running for anything under review.

Nothing in this file requires writing new product code. The system, by design, is done.
