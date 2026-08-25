# RepoVitals — Parallel Work Plan (File B)

**Status of this document.** Files A, B, and C together supersede and replace every earlier project document. This file is complete in itself — you never need to read the codebase or any older document to execute it. File A is the developer's build plan; File C is the research plan that starts after A and B are done.

**Who executes this file:** the teammate. Every work package (WP) below is yours end-to-end — including the long tool-assisted runs. The developer never executes any WP; you never write code that gets committed to the repository.

**What you produce:** results, not commits. Each WP ends in a **deliverable** with an exact format defined below. You hand it to the developer, who feeds it into the build at the marked phase gate. A late deliverable blocks its phase (one exception: WP-1 has a fallback).

**The system in two minutes.** RepoVitals scans GitHub repositories (Node.js/npm and Python/PyPI), extracts every dependency, checks each against registry metadata and the OSV vulnerability database, and computes a deterministic 0–100 risk score from four signals — deprecation, vulnerability severity, vulnerability count, staleness. The *weights* on those signals are your responsibility (WP-1 informal now, WP-3 rigorous later). An AI agent separately produces citation-backed remediation reports; validating the automated judge of those reports is also yours (WP-9). The research needs data at two scales: a ~1,000-repository corpus with reconstructed monthly score history (WP-4, WP-5) and a small cohort of real users scanning real repos monthly (WP-7).

---

## 1. Deliverable registry

| WP | Deliverable file(s) | Format | Gates File A phase |
|---|---|---|---|
| WP-1 | `wp1_tier1_weights.yaml` + `wp1_method_note.md` | YAML + prose | Phase 4 acceptance |
| WP-2 | `wp2_anchor_set.csv` | CSV (§WP-2) | Phase 12 validation run |
| WP-3 | `wp3_matrix_A.csv`, `wp3_matrix_B.csv`, `wp3_matrix_reconciled.csv`, `wp3_session_notes.md` | CSV matrices + prose | Phase 12 (weights v2) |
| WP-4 | `corpus_manifest.json`, `strata_report.md` + sign-off note | tool-generated + prose | Phase 12 inputs |
| WP-5 | backfill completion report + **research-DB dump file** + sign-off note | tool-generated + prose | Phase 12/13 inputs |
| WP-6 | `validation_report/` folder + `wp6_signoff.md` | tool-generated + prose | **Phase 12 acceptance** |
| WP-7 | `wp7_cohort_tracker.csv` (living; monthly updates) | CSV (§WP-7) | starts after Phase 6; feeds WP-10 |
| WP-8 | `runs/` folders + `wp8_run_log.md` | tool-generated + prose | Phase 14 acceptance |
| WP-9 | `wp9_judge_labels.csv` | CSV (§WP-9) | Phase 14 acceptance |
| WP-10 | agreement report + `wp10_signoff.md` | tool-generated + prose | no phase gate; **required before the S2 paper is drafted** (File C) |

**Handoff etiquette:** zip each deliverable as `WPx_YYYYMMDD.zip`, send to the developer, keep a copy. Never edit a deliverable after handoff — send a v2 zip instead. The developer archives everything under the repo's `research_data/deliverables/`.

---

## 2. Master timeline

Read as: *"my deliverable must arrive before that phase can close."*

| When (relative to File A) | Your work |
|---|---|
| While Phases 1–3 are built | **WP-1** (half a day). Begin **WP-2** browsing (no tooling needed). |
| Before Phase 4 closes | WP-1 delivered. |
| While Phases 5–10 are built | **WP-2** completed. **WP-3** session held (any time after WP-1). |
| Immediately after Phase 6 deploys | **WP-7 starts** — the longest lead-time item in the project; every week of delay costs a week of longitudinal data. Monthly ritual thereafter. |
| After Phase 11 code lands | **WP-4** (≈1 h + review), then **WP-5** (overnight + review + dump handoff). *(File A may pull Phase 11 earlier — if so, so do these.)* |
| During Phase 12 | **WP-6** (runs + review + sign-off). Phase 12 cannot close without it. |
| After Phase 13 code lands | **WP-8** (multi-day paced runs), then **WP-9** (one sitting, 3–4 h). Both before Phase 14 closes. |
| ≥3 monthly WP-7 waves after Phase 6 | **WP-10** (run + review). Calendar it the day WP-7 starts. |

Total effort ≈ 6–8 working days spread across the build + ~1 h/month for WP-7 + wall-clock waiting on runs.

---

## 3. Tooling prerequisites (one-time, ~45 min, developer-assisted)

The developer gives you: a checkout of the repository, a filled `.env` (contains the GitHub token and API keys — **treat as secrets**; don't paste into chats or commit anywhere), and the activation one-liner for the Python environment. You additionally need:

- **Docker Desktop** installed. Your machine hosts the **research database** — a local Postgres started once with `docker compose --profile research up -d` from `backend/`. All corpus/backfill data lives there (it is far too large for the free cloud database, by design). Expect **2–5 GB disk** total.
- Internet on first run: the tools download a small (~90 MB) embedding model once.
- A spreadsheet app for CSVs and a calendar for WP-7's monthly ritual.

Every WP states its exact commands. You don't need to understand the code — run the command, watch for the completion summary, review outputs against the checklist. If a command crashes: rerun once with `--resume` (safe by design); if it crashes again, send the developer the last 30 lines of output and stop.

---

## WP-1 — Tier-1 weight assignment (informal pairwise pass)

**Gate:** before Phase 4 closes. **Effort:** 2–4 hours. **Depends on:** nothing — do this first.

**Purpose.** The score is `100 − 100·(w_dep·P_dep + w_sev·S_cvss + w_cnt·S_count + w_stl·S_stale)`, weights summing to 1. Version 1 of the weights ships in the product. Deliberately informal — the rigorous derivation is WP-3; Tier 1 needs a defensible, documented starting point.

**The four signals, in plain terms:**

| Signal | Meaning | Why it might matter most |
|---|---|---|
| Deprecation | maintainer explicitly said "stop using this" | first-party, zero-ambiguity declaration |
| Severity | how bad the worst known vulnerability is (CVSS 0–10) | one critical hole can be fatal regardless of count |
| Count | how many known vulnerabilities affect the version | breadth of exposure |
| Staleness | time since the package last shipped anything | abandonment proxy; undisclosed-risk proxy |

**Procedure.**
1. One joint session with the developer (the only WP done jointly — you drive and own the deliverable). For each of the 6 signal pairs: *"is A more important than B for real-world dependency risk, and by roughly how much?"* on Saaty's scale (Appendix A).
2. Starting matrix you may adjust rather than begin blank (inherited from the project's earlier design work): Deprecation vs Severity 2, vs Count 3, vs Staleness 4; Severity vs Count 2, vs Staleness 3; Count vs Staleness 2. Challenge every cell; note what you change and why.
3. Convert to weights (normalize by eye, or via the `ahpy` helper if ready — either is fine at Tier 1). Must sum to 1.
4. Produce a **second vector for PyPI**. PyPI's deprecation signal (release "yanking" + an "Inactive" classifier) is real but carries less information than npm's free-text deprecation message (which often names a successor). Decide in writing: lower `deprecation`'s PyPI weight (redistributing to staleness/severity) or keep vectors identical. Either is defensible **if the reasoning is written down**.

**Deliverable — `wp1_tier1_weights.yaml`:**
```yaml
weights:
  npm:  { deprecation: 0.xx, severity: 0.xx, count: 0.xx, staleness: 0.xx }
  pypi: { deprecation: 0.xx, severity: 0.xx, count: 0.xx, staleness: 0.xx }
```
**Plus `wp1_method_note.md`** (goes into the report verbatim): one paragraph — weights informed by AHP principles (pairwise judgment, Saaty scale) but not independently cross-validated; the full derivation is the Tier-2 study — plus 2–3 sentences on the PyPI decision.

**Quality checks:** each vector sums to 1.00 (±0.01); no weight is 0 or > 0.6; PyPI reasoning written.

---

## WP-2 — Anchor set curation (30–50 hand-picked repositories)

**Gate:** before WP-6. **Effort:** 1–2 days, spreadable. **Depends on:** nothing.

**Purpose.** Statistical validation runs on the big automated corpus, but statistics can't catch a formula that is *obviously* wrong on *known* cases. You curate 30–50 real repositories whose risk level is knowable by inspection. If the formula doesn't flag the known-bad ones as at least Medium, it fails regardless of any correlation numbers.

**Composition.**

| Bucket | Count | How to find |
|---|---|---|
| Healthy | 15–20 | actively maintained (pushed recently), reputable orgs, no obviously dead dependencies |
| Risky | 15–20 | not pushed in 3+ years; 2017–2020 tutorial/boilerplate repos; anything depending on famously dead packages (old `request`, `lodash` 3.x, Python-2-era libs, old Django 1.x pins) |
| In-between | 10–15 | maintained but far behind on majors, or stale but small/clean |

**Coverage requirements (all must hold):** ≥5–10 repos with 100+ dependencies; ≥5 "known-anchor" repos containing a famously vulnerable/deprecated package (mark them — the hard pass/fail cases); some repos with lockfiles, some without; both ecosystems (~60/40 either way); **no near-duplicates** — skip anything forked from the same boilerplate as one already picked.

**Procedure.** Browse GitHub (`pushed:<2022-01-01 language:javascript` style filters help). Open each candidate's `package.json`/`requirements.txt`, skim, record a row. **Do not** run any scoring on them and do not ask the developer to — your bucket judgment must be formed *before* seeing the formula's output (anchoring bias).

**Deliverable — `wp2_anchor_set.csv`:**
```
repo_url, ecosystem, bucket_seeded, is_known_anchor, anchor_package, approx_dep_count, has_lockfile, why_this_bucket
```
`why_this_bucket` = one sentence; `anchor_package` only for known anchors (e.g. `request@2.x`).

**Quality checks:** 30–50 rows; bucket counts in range; ≥5 known anchors named; both ecosystems; no near-identical dependency lists.

---

## WP-3 — Full AHP judgment session (Tier-2 weights)

**Gate:** before Phase 12 completes. **Effort:** half a day + a reconciliation meeting. **Depends on:** WP-1 (calibration on the signals).

**Purpose.** Tier-2 weights come from the Analytic Hierarchy Process: two people judge all signal pairs **independently**, judgments are checked for internal consistency, reconciled, and the final matrix's principal eigenvector becomes the weight vector. This is the project's headline methodology claim — this deliverable is what examiners and reviewers will probe, and it is yours to defend.

**Why independence matters:** one person's gut produces circular judgments (A>B, B>C, C>A). Two independent judges + a mathematical consistency check + documented reconciliation is what separates "derived weights" from "picked numbers."

**Procedure.**
1. You and a second judge (the developer is acceptable — the method requires independent *judgments*, not independent people) each fill the blank 4×4 matrix **without conferring** (template below). Upper triangle only; diagonal 1; lower triangle reciprocal.
2. Hand both CSVs to the developer, who runs the consistency tool. It computes each matrix's **Consistency Ratio** (Appendix B). CR < 0.10 = coherent. CR ≥ 0.10 → the tool names your most contradictory judgment triads — re-think *those specific cells* and resubmit. Don't tweak randomly until it passes.
3. Reconciliation meeting: the tool lists cells where you two diverge by more than 2 scale steps. Discuss each to agreement or accept the tool's geometric-mean merge. The merged matrix must itself pass CR < 0.10.
4. Optional, decided in-session and recorded either way: a second 5×5 matrix including EPSS (exploit likelihood) for a Tier-2 research variant. Only if you both can judge EPSS meaningfully; otherwise write "EPSS deferred from AHP."

**Matrix template (`wp3_matrix_X.csv`):**
```
,Deprecation,Severity,Count,Staleness
Deprecation,1,,,
Severity,,1,,
Count,,,1,
Staleness,,,,1
```

**Deliverables:** both independent matrices, the reconciled matrix, and `wp3_session_notes.md`: date, who judged, divergent cells and how resolved, the EPSS decision, 3–5 sentences of rationale for the most debated judgments (this prose goes nearly verbatim into the paper's methodology section).

**Quality checks:** all three matrices CR < 0.10 (tool-verified); reciprocals exact; notes name the top-2 debated cells.

---

## WP-4 — Corpus construction run

**Gate:** Phase 12 input; runnable any time after Phase 11 code lands. **Effort:** ~1 h wall clock + 30 min review. **Depends on:** Phase 11 code; research DB up (§3); PAT in `.env`.

**Purpose.** Builds the ~1,000-repository research corpus (≈500 npm / ≈500 PyPI) by stratified, seeded, deduplicated sampling of GitHub — the dataset for the scoring-validation and longitudinal studies. You run it and confirm the output is sane.

**Procedure.**
1. `docker compose --profile research up -d` (once per boot).
2. `python manage.py build_corpus --seed 42 --target 1000 --config corpus_frame.yaml`
3. Paces itself (~1 h). Interrupted → rerun with `--resume`. Writes `corpus_manifest.json` + `strata_report.md`.

**Review checklist (your actual work):** total admitted 900–1,100; ecosystem split within 45/55; **no stratum cell empty** — especially the old/stale cells (they carry the research; a zero stale cell → flag, don't accept); admission rate 40–60% (well below 40% suggests a verification bug → flag); dedup discard count > 0 (zero discards over 1,000+ candidates is suspicious); seed, timestamp, grid config present in the report (reproducibility fields).

**Deliverable:** both generated files + a 5-line sign-off note (date, checklist outcomes, anything flagged).

---

## WP-5 — Backfill run (the overnight one)

**Gate:** Phase 12/13 inputs; run after WP-4. **Effort:** ~6 h wall clock unattended + 30 min review. **Depends on:** WP-4.

**Purpose.** For every corpus repository, reconstructs what its dependency manifests looked like at each month-end over the past 5 years (public git history) and what was *known* about each dependency at that time (CVE disclosure dates, release dates), then scores each monthly snapshot. ≈60,000 scored repo-months — five years of longitudinal data collected in one night.

**Procedure.**
1. Evening: `python manage.py backfill --corpus research_data/corpus/corpus_manifest.json --resume`
2. Checkpoints continuously; crashes/sleep cost nothing — rerun the same command. May pause itself near GitHub's hourly limit (normal). ~6 h.
3. Morning: read the completion report.
4. Produce the DB dump for the developer (they need the data locally to build Phases 12–13): `docker exec repovitals-research-db pg_dump -U postgres -Fc repovitals_research > wp5_research_db.dump` (exact command confirmed by the developer).

**Review checklist:** ≥95% of corpus repos completed (a handful of deleted/renamed repos is normal; 50+ failures is not → flag); snapshot count within the report's own expected range; ask the developer for 2–3 `plot_history` charts and eyeball them — curves should *move* (a corpus where nothing ever changes classification would be useless, and itself worth flagging).

**Deliverable:** completion report + `wp5_research_db.dump` + 5-line sign-off note.

---

## WP-6 — Formula validation run + sign-off (closes Phase 12)

**Gate:** **Phase 12 acceptance** — weights v2 waits on you. **Effort:** ~2–3 h of runs (mostly waiting) + 2–3 h review. **Depends on:** WP-2, WP-3, WP-4, WP-5.

**Purpose.** Your AHP matrices become the product's validated weights. The harness computes the AHP weight vector from your reconciled matrix, computes an independent entropy-based vector from the corpus data, validates the formula against external references at corpus scale, stress-tests it under perturbation, and checks your anchors. You run it, read it, and sign off — or bounce it.

**Procedure.**
1. `git pull` (Phase 12 code), research DB up.
2. `python manage.py validate_formula --ahp wp3_matrix_reconciled.csv --anchors wp2_anchor_set.csv`
3. Read `research_data/validation_report/` (report.md + charts).

**Sign-off checklist — every line addressed in your note:**
1. Reconciled matrix CR < 0.10 (the tool refuses otherwise — a refusal is a WP-3 revisit, not a tweak).
2. **Anchors:** every known-anchor repo classified Medium or High-Alert. Any known-bad anchor scoring Safe = automatic fail → send the report back; do not sign.
3. AHP-vs-entropy: broad agreement (similar signal ranking) = strong story. Sharp disagreement is not automatic failure but must be explicitly acknowledged in your note — a discussed limitation, never a hidden one.
4. Correlation vs the independent reference (deps.dev Scorecard): positive and non-trivial; write the number down. Confirm the report's circularity caveat on the OSV-rollup reference is present.
5. Sensitivity: note the bucket-flip rate under ±10–20% perturbation for both vectors. Under ~15% = robust; higher → raise with the developer before signing.
6. Final vectors (both ecosystems) sum to 1 and look non-degenerate (a weight ≈0 or ≈0.8 needs a sentence of justification or a bounce).

**Deliverable:** the `validation_report/` folder + `wp6_signoff.md` walking all six checks. Your sign-off is the event that ships weights v2.

---

## WP-7 — Prospective cohort (the recruiting job) — START EARLY

**Gate:** starts immediately after Phase 6 deploys; monthly thereafter. **Effort:** 2–3 h to recruit; ~1 h/month ritual. **Depends on:** the product live with both ecosystems.

**Purpose.** The longitudinal study's historical data is *reconstructed* (WP-5). Science requires showing the reconstruction matches reality — real repositories scanned live, monthly, going forward. That validation (WP-10) needs **≥3 monthly waves**, so every week of late start pushes the study's earliest defensible date a week out. The most calendar-critical item in either file.

**Targets:** ≥8 people (course-mates with GitHub repos — the product requires they *own* or have write access to what they register); ≥30 repositories total; both ecosystems (aim ≥10 each — ask specifically for Python repos; JS is what everyone offers first).

**Recruit message (adapt):** *"We built a tool that scores your GitHub repos' dependency health (0–100) and explains exactly which packages are risky and why. Five minutes: log in with GitHub at <URL>, register 3–5 of your own repos (Node or Python), done — it scans automatically. Once a month I'll ask you to press one Rescan button per repo. Your scan data will be used, anonymized, in our final-year academic research — by registering you're okay with that."*

**Consent is mandatory:** the research use must be stated up front (it's in the message above); record their agreement in the tracker. No consent recorded → their data stays out of the research set.

**Setup per recruit:** they log in, register 3–5 own repos, initial scan runs automatically; you add tracker rows (aliases, not names). If a repo is rejected at registration, record the rejection reason — that's useful data too.

**Monthly ritual (fixed slot — e.g. 1st weekend):** message every recruit to hit Rescan per repo (or sit with them — it's minutes); verify in the tracker; chase stragglers within 3 days — a missed month is an unfillable hole in a time series; send the updated tracker to the developer.

**Deliverable — `wp7_cohort_tracker.csv` (living):**
```
person_alias, consent_ok, repo_url, ecosystem, registered_date, wave_1_date, wave_1_done, wave_2_date, wave_2_done, ...
```

**Quality checks:** ≥8 people / ≥30 repos within two weeks of Phase 6; `consent_ok=yes` on every row; per-wave completion ≥80%; ecosystem mix recorded.

---

## WP-8 — S3 experiment runs (the paced multi-day one)

**Gate:** before Phase 14 closes. **Effort:** ~30 min/day of babysitting across 2–4 days. **Depends on:** Phase 13 code with its pilot passed; research DB up.

**Purpose.** The grounding study compares three pipelines on the same 150 flagged dependencies (75 npm / 75 PyPI): **A** the LLM with no retrieved evidence, **B** grounded in changelog text, **C** the full branching agent. (Possibly an internal condition **D** — broader retrieval; the developer will say.) You execute; analysis is scripted.

**Procedure.**
1. Confirm with the developer the labelled set is frozen (`labelled_set.jsonl`, 150 items).
2. One condition at a time: `python manage.py run_experiment --condition A --items labelled_set.jsonl --resume` — then B, then C (then D if instructed). **Never two conditions simultaneously** (they'd fight over the same free-tier rate budget).
3. Runs checkpoint per item and stop cleanly at daily caps — rerun the same command next day to continue.
4. Afterwards: `python manage.py analyze_experiment --runs <run_ids>`; confirm tables render.

**Review checklist:** each condition reports 150/150 items completed; failures per condition < 5 and retried; all condition × ecosystem cells populated in the tables. **Do not interpret results** — whether C beats A is the paper's job; a null result is a valid outcome and gets reported exactly as enthusiastically.

**Deliverable:** the `runs/` folders + `wp8_run_log.md` (dates, interruptions, completion counts, anomalies).

---

## WP-9 — Judge-validation labelling (the one manual-judgment task)

**Gate:** before Phase 14 closes. **Effort:** one undisturbed sitting, 3–4 h. **Depends on:** WP-8 (≥1 full condition done).

**Purpose.** The study scores "faithfulness" — whether a generated remediation's claims are actually supported by the source text it retrieved — with an automated LLM judge. Reviewers will ask how we know the judge measures what we claim. The answer is you: 50 items labelled blind, and the agreement statistic (Cohen's kappa) between you and the judge is what makes every automated verdict credible. Small task, outsized scientific weight.

**Procedure.**
1. The developer generates your packet (50 stratified items, **judge verdicts hidden**). Each shows: the flagged dependency, the generated remediation, and the exact source chunks retrieved for it.
2. Per item, check the remediation **claim by claim** against the shown source text only — not your own knowledge, not the internet. A claim is supported only if the shown text states or directly entails it. Version numbers, package names, migration steps all count as claims.
3. Label: `faithful` (every material claim supported) / `minor_unsupported` (≤1 peripheral claim unsupported; core recommendation supported) / `major_unsupported` (a core claim — recommended version, replacement package, a breaking-change assertion — is not in the source). One-line note naming the offending claim for every non-faithful label.
4. Rules: one sitting if possible; no conferring mid-task; empty/unreadable source → `major_unsupported` with a note; no skipped items.
5. Return the CSV; the developer computes kappa. If agreement is poor, the *rubric* gets tightened and worst-case you re-label a fresh 50 — a finding about the rubric, not about you.

**Deliverable — `wp9_judge_labels.csv`:** `item_id, label, note`

**Quality checks:** 50/50 labelled; only the three allowed values; notes on every `major_unsupported`.

**Worked examples: Appendix C.**

---

## WP-10 — Backfill-vs-reality agreement run

**Gate:** none in File A — **required before the S2 paper is drafted** (File C blocks on it). Earliest date: 3 monthly WP-7 waves after Phase 6. Calendar it the day WP-7 starts. **Effort:** ~1 h + 1 h review.

**Purpose.** WP-5 reconstructed history from public records. This run proves the reconstruction is trustworthy: for the cohort's repositories, it compares the backfill engine's reconstruction of recent months against the *actual live scans* your recruits performed in those months. Close agreement makes the 5-year corpus defensible — the difference between "we cleverly reconstructed history" and "we validated a reconstruction method." The second is publishable.

**Procedure.**
1. Confirm ≥3 completed waves in the tracker.
2. Get the cohort live-scan export file from the developer (one command on their side).
3. `python manage.py backfill_validate --cohort wp7_cohort_tracker.csv --live-export live_scans_cohort.parquet`
4. Read the agreement report: per-repo-month score deltas, classification agreement (kappa), per-signal attribution of disagreements.

**Review checklist:** classification agreement high (the report flags its own threshold); deltas *attributed* in the per-signal table (expected sources: the known deprecation-timing limitation; packages published between snapshot and scan) — explainable deltas are fine, unexplained systematic drift is not → flag; your sign-off records the agreement number and dominant disagreement source.

**Deliverable:** the agreement report + `wp10_signoff.md` (5–10 lines).

---

## Appendix A — Saaty's 1–9 scale (WP-1, WP-3)

| Value | Meaning |
|---|---|
| 1 | A and B equally important |
| 3 | A moderately more important |
| 5 | A strongly more important |
| 7 | A very strongly / demonstrably more important |
| 9 | A extremely more important |
| 2,4,6,8 | intermediate steps |
| 1/3, 1/5 … | reciprocals — B over A by that step |

## Appendix B — Consistency Ratio, in one paragraph (WP-3)

If you say deprecation is 3× severity and severity is 2× count, logic implies deprecation ≈ 6× count; judging deprecation-vs-count as 2 contradicts yourself. CR measures total contradiction across all pairs against what random judgments would produce. CR < 0.10 = coherent enough for the derived weights to mean something; at/above it, the named contradictory triads must be re-judged. It's a coherence check on the judgments, not a correctness check on the weights — correctness is WP-6's validation.

## Appendix C — Faithfulness labelling, worked examples (WP-9)

- Remediation: "upgrade to 4.17.21, which patches the prototype-pollution issue" — shown changelog says "4.17.21 fixes prototype pollution" → **supported**.
- Remediation: "migrate to axios" — shown source never mentions axios (even if you know it's the community answer) → `major_unsupported` (core recommendation ungrounded).
- Remediation adds "this release also improved performance" — source silent on performance; core upgrade advice grounded → `minor_unsupported`.
- Remediation: "insufficient information to recommend a specific migration" — and the source is indeed thin → **faithful** (honesty about weak evidence is exactly the designed behavior).
