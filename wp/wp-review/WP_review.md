# WP review: status and required updates (9 Oct 2026)

This file is the single source of truth for what each work package still needs. It replaces the 7 Oct version, which remains in git history.

**What changed on 8 Oct:** the team became unavailable, and Spandan completed WP-2 to WP-5 alone. Rules that assumed separate people no longer apply:
- Teams zips;
- "don't push to `main`";
- the reviewer's "WP-x accepted" message.

Each WP below says what was done, how it was checked, and what deviates from File B. Folders under `wp/` still hold only validated material.

| WP | Status | Deviation from File B |
|---|---|---|
| WP-1 | **Accepted** (Sep) | none |
| WP-2 | **Complete**: 49 rows, 12 known anchors | Bucket rules written down and applied to verified facts |
| WP-3 | **Complete**: one AI-assisted judgment, CR 0.0054 | **One judgment, not two independent judges (final decision)** |
| WP-4 | **Complete**: 914 repositories over all 240 strata | Allocation fixed mid-run (§11.29); admission rate 68% (flagged, explained) |
| WP-5 | **Complete**: 914/914 scanned, 29,494 occurrences, dump verified | One repo rescanned after a crash damaged its archive (§11.30) |
| WP-6 | **Signed** (8 Oct): weights v2 approved for adoption | Checks 3 and 4 acknowledged (entropy disagreement, Scorecard null); single-judgment matrix |
| WP-8 | **Complete** (9 Oct): A, B and C each 150/150, 0 failed, all judged | Generation divided over four members' free-tier keys (disclosed); PyPI retrieval left as is (S3 limitation); no PyPI replacement items |
| WP-9 | **Ready**: blind packet of 50 items in `wp-9/` | Labeller: one team member, labelling blind |

---

## WP-1: Tier-1 weights. ACCEPTED

`wp-1/`: `wp1_tier1_weights.yaml` and `wp1_method_note.md`. The product uses exactly these values (`backend/weights/weights_v1.yaml`).

**Before the black book:** the PyPI paragraph says the "Inactive" classifier is "rarely applied in practice". Either give a number with its source, or soften the wording.

---

## WP-2: Anchor set. COMPLETE

`wp-2/` holds:
- `wp2_anchor_set.csv`: 49 rows in File B's exact 8-column format.
- `wp2_evidence.md`: what was read for every row, with links pinned to the commit.
- `wp2_verification_note.md`: method, bucket rules, and the candidates left out and why.
- `WP2_20261006.zip`: the 6 Oct partial submission, as received.

**The checks** (all re-run from the files):

| Check | Result |
|---|---|
| Rows | 49 (File B: 30–50) |
| Healthy | 17 (15–20) |
| Risky | 20 (15–20) |
| In-between | 12 (10–15) |
| Known anchors | 12 (at least 5) |
| 100+ dependencies | 8 repos (at least 5) |
| Ecosystems | npm 27 / PyPI 22, i.e. 55/45 (about 60/40 either way) |
| Lockfiles | 14 rows with a readable lockfile, 35 without |
| Near-duplicates | largest overlap of declared dependency names between two rows: 19% |
| Format | loads through the Phase 12 anchor-set reader |

**How the rows were checked:**
- Every value was read on 8 Oct through RepoVitals' own manifest planning and adapters, at a linked commit.
- No scoring was run.
- Every known anchor is:
  - a direct dependency;
  - resolved by an exact pin or a readable lockfile;
  - listed on osv.dev or deprecated on npm, for that exact version.

`bower/bower` (`request@2.67.0`, pinned at runtime) is the twelfth anchor. `googleapis/oauth2client` stays a spare: its pin is only in `samples/`.

**Deviations, both written into the note:**
- **Bucket rules.** Buckets follow File B's criteria, written as explicit rules and applied to the verified facts rather than chosen case by case.
- **Activity date.** "Activity" is the date of the default branch's head commit, not GitHub's `pushed` date as the 7 Oct version of this file asked. Any branch push moves `pushed`: `dropbox/pyannotate` reads "pushed 2026-07-06", yet its code last changed on 2021-10-12. Both dates are in every row.

The AI-drafted worksheet from 5 Oct is superseded by `wp2_evidence.md` and was removed; git history keeps it.

---

## WP-3: AHP matrix. COMPLETE, WITH A STATED DEVIATION

> **Final decision (Spandan, 2026-10-08): WP-3 follows a single judgment.** No second judge will be added and there is no reconciliation step. `wp3_matrix_final.csv` is the only matrix, and it is the one WP-6, weights v2 and the S1 paper use. Every place that reports these weights must say they come from one judgment.

`wp-3/` holds:
- `wp3_matrix_final.csv`: the matrix;
- `wp3_session_notes.md`: the session notes;
- `wp3_matrix_blank.csv`: File B's template.

| Signal | Weight |
|---|---|
| Deprecation | 0.272 |
| Severity | 0.483 |
| Count | 0.157 |
| Staleness | 0.088 |

- **Consistency:** λmax 4.0145, CI 0.0048, **CR 0.0054**.
- **Verified:** with `ahp_check`, and again with numpy. The Phase 12 matrix gate accepts it.
- **EPSS:** deferred from AHP.
- **PyPI rule:** WP-1's rule. 30% of the deprecation weight moves equally to severity and staleness:
  ```
  --pypi-shift "deprecation=-0.0816,severity=+0.0408,staleness=+0.0408"
  ```
  File C's L4 sentence is kept.

**The deviation, and what follows from it.** File B asks for two independent judges and a reconciliation. With the team unavailable, there is one judgment, produced with an AI tool at Spandan's direction, and the notes say so. As a result:
- File B's "independent judges + reconciliation" is not met. Only the consistency check is.
- The CR is low because the judgments were made coherent, not because two people converged on them.
- WP-6's entropy vector is now the only independent cross-check, and its sign-off has to discuss it either way.
- S1's threats-to-validity section must list this.

**No second judge will be added** (decision above). The tooling for one does exist: `ahp_check` with two matrices and `--merge` gives File B's divergence table and geometric-mean merge. So if this decision were ever reversed, the change would be one command, plus a WP-6 re-run.

**Wording for the report and paper** (keep it next to the weights wherever they appear): "The Tier-2 AHP weights were derived from a single pairwise-comparison judgment (CR = 0.0054). The two-judge protocol with reconciliation planned in the work plan was not carried out, so the vector has no inter-judge agreement behind it; the entropy-derived vector computed from the 914-repository corpus is the independent cross-check."

**PR #3's finding, as promised on 7 Oct:** the matrix in `refs/pull/3/head` (`wp3_matrix_updated.csv`) matches the WP-1 seed in 5 of its 6 cells. Only Severity vs Count differs: 3, where the seed has 2. It could not have served as an independent judgment, whatever the posting protocol.

---

## WP-4: Corpus build. COMPLETE

`wp-4/` holds:
- `corpus_manifest.json` and `strata_report.md`: unedited copies of the run's output. `research_data/` is gitignored, so the originals stay local.
- `wp4_signoff.md`: the checklist with every value read from the report.
- `wp4_wp5_runbook.md`: the commands, as reviewed.

| Check | Value | Result |
|---|---|---|
| Admitted | 914 | pass (900–1,100) |
| Ecosystem split | npm 486 / PyPI 428 (53/47) | pass (within 45/55) |
| Strata without an admitted repository | 0 of 240 (per stratum min 1, median 4, max 11) | pass |
| Empty / empty stale cells | 0 / 0 | pass |
| Dedup discards | 4 | pass (above 0) |
| Seed, timestamp, grid | seed 42, run date 2026-10-07 | pass |
| Admission rate | 68% | **flagged**: outside File B's 40–60% |

**The admission rate is genuine, not a verification bug.**
- It is npm-driven: npm admitted 83%, PyPI 57%.
- Every rejection path fired.
- 12 candidates re-checked directly against GitHub all match the builder's verdicts.

**A Phase 11 defect was found and fixed during the run (decisions §11.29, commit `a5ba223`).** `build_corpus` allocated per split search slice rather than per stratum, which would have left 104 of the 240 strata with no repository at all. The strata report would still have said "Empty cells: 0", because that line counts cells GitHub had no repos for. The first attempt was stopped and the fix written with tests. The run then resumed from the first attempt's enumeration, so no search calls were repeated. The report now has a "Strata with no admitted repository" line and a per-stratum table.

**Known limits, stated in the report itself:**
- 307 cells remain over the 1,000-result cap even at the deepest split, and are sampled from their first 1,000 by stars.
- It is a cross-section as of 2026-10-07.

---

## WP-5: Corpus scan. COMPLETE

`wp-5/` holds:
- `scan_corpus_report.md`: the main run's report, unedited.
- `scan_corpus_report_rescan_one_repo.md`: the one-repo rescan's report, unedited.
- `corpus_report.md`, `score_histogram.png` and `flagged_rate_by_stratum.png`.
- `wp5_signoff.md`: the sign-off, with the pasted query output.

| Check | Value | Result |
|---|---|---|
| Completed | 914 of 914, 0 failed | pass (at least 95%) |
| Snapshot dates | exactly one row: `corpus_scan`, 2026-10-07, 914 | pass |
| Weights | `v1` on every row | pass |
| Occurrences | 29,494; every repository's distinct names match the builder's count (914/914) | pass |
| Score spread | Safe 273 / Medium 143 / High alert 498; both ecosystems span 0–100 | pass |
| Unassessable | 691 (2.3%) | pass (not dominant) |
| Product tables in the research DB | all empty | pass (D10) |
| Dump | `research_data/exports/wp5_research_db.dump`, 1.5 MB, sha256 in the sign-off | pass: `pg_restore -l` lists both history tables, and a scratch restore gives the same 914 / 29,494 and the same total score |

**Flagged, not failed: npm skews to High alert.** npm has 301 High-alert repos and only 38 Medium. That matches decisions §11.27's dependency-count confound, and S1 must control for dependency count before any ecosystem comparison.

**The crash and its repair.** WP-4's machine went down mid-run (03:07 IST), leaving two archived manifests zero-filled. That cost one repository two of its three manifests, without any error.
- It was found by the distinct-name check above.
- All 2,542 archived blobs were verified against their git SHAs.
- The 2 bad ones were re-fetched by SHA, and the repository was rescanned.
- The archive now checks every blob against its SHA on write and on read (decisions §11.30).

The same commit fixed `corpus_report`, which had counted 575 "strata" (one per split cell) instead of 240.

**Dump:** committed as `wp-5/wp5_research_db.dump` (1.5 MB; sha256 in the sign-off). Restore it with `pg_restore`.

---

## WP-6: Formula validation sign-off. SIGNED

`wp-6/` holds:
- `wp6_signoff.md`: walks all six of File B's checks with real numbers.
- `validation_report/`: the harness output, unedited. It includes the anchor scan record and the deps.dev answers as observed; the anchor manifest blobs are left out.

**The run:** `validate_formula --ahp ../wp/wp-3/wp3_matrix_final.csv --anchors ../wp/wp-2/wp2_anchor_set.csv --snapshot-date 2026-10-07 --pypi-shift "deprecation=-0.0816,severity=+0.0408,staleness=+0.0408"`. It ran on `v0.12.0` (`a293a18`), over WP-5's 914 repositories, and took 23 minutes. All 914 stored scores reproduce exactly.

| # | Check | Result |
|---|---|---|
| 1 | Matrix CR < 0.10 | pass: 0.0054, from a single judgment with no reconciliation |
| 2 | Known anchors ≥ Medium | pass: 12/12 under v2 and under v1; no risky-seeded repo is Safe |
| 3 | AHP vs entropy | **acknowledged**: cosine npm 0.898, PyPI 0.691, and the top two signals differ in both. PyPI's entropy deprecation weight of 0.515 comes from rarity (48 of 8,922 occurrences), not importance |
| 4 | Scorecard correlation | **not met, documented**: ρ 0.047 [-0.077, 0.169] on 289/914. v1 and entropy are also near zero, so it reflects a different construct, not the weights. The OSV circularity caveat is present |
| 5 | Sensitivity under 15% | pass: v2 4.7% at ±20%, entropy 3.8% |
| 6 | Vectors sum to 1, non-degenerate | pass: npm .272/.483/.157/.088, PyPI .190/.524/.157/.129 |

**Decision: signed.** Weights v2 are approved for adoption. Checks 3 and 4 are findings that no reweighting could legitimately change, so they are not grounds to bounce.

**For S1:**
- Hypotheses H1 and H2 are not supported.
- Score falls with dependency count (ρ −0.51 on the anchors), so seeded-healthy repos score below in-between ones. S1 must control for this.
- The healthy-seeded outliers come from example and docs manifests.
- The PyPI trust gate passes on distribution. Its matched-strata roll-up part remains an S1 analysis.

**Phase 12, commit 7: done** (`docs/decisions.md` §12.19):
1. `backend/weights/weights_v2.yaml` is the signed candidate, with only its derivation tag changed.
2. `rescore --weights v2` materialised the corpus panel offline. All 914 scores equal the report's.
3. The code default is now `v2`, so each deploy scores new scans under it. Stored `v1` rows keep their tag.

## WP-8: S3 experiment runs. COMPLETE

`wp-8/` holds:
- `wp8_run_log.md`: dates, interruptions, completion counts, anomalies and the key ledger.
- `runs/`: the three run folders and `analysis/` (`tables.md` and one CSV per table).
- The runbook, the frozen set and the pilot, as before.

| Check (File B) | Result |
|---|---|
| Each condition 150/150 | pass: A, B and C each 150/150 |
| Failures under 5 | pass: 0 in every condition |
| Every condition × ecosystem cell populated | pass (PyPI × replacement is empty by construction) |
| Judged | 150/150 per condition |

**Run:** 2026-10-09, on `v0.13.0`, with generator `openai/gpt-oss-120b` and judge `gemini-3.5-flash-lite`.

**Deviations, all disclosed in the run log:**
- Generation was divided over four team members' free-tier Groq keys, one at a time, because no paid tier was possible. Model, prompts and pacing were identical throughout.
- PyPI retrieval was left as is: mostly READMEs (decisions §13.14 (4)). That is a threat to validity for S3's PyPI arm.
- One B npm item has no precision@k verdict.

The judge cache is held back until WP-9 is labelled, to keep the labelling blind. Results are not interpreted here; that is the paper's job.

## WP-9: Judge-validation labels. READY

**The labeller needs only `wp-9/`.** Start with `wp-9/README_WP9.md`, which is self-contained: the rules, the rubric, worked examples, hard cases and how to return the labels.

`wp-9/` holds:
- `README_WP9.md`: the full instructions.
- `wp9_labelling_workbook.xlsx`, with four sheets:
  - `Labels`: dropdown labels, note column and per-row checks;
  - `Items`: all 50 items;
  - `Progress`: shows READY TO RETURN when complete;
  - `Start here`.
- `judge_validation_packet.md`: the same 50 items in a readable layout, stratified by condition and ecosystem (A 18, B 16, C 16; 25 npm, 25 PyPI), with the judge's verdicts **hidden**.
- `wp9_judge_labels_template.csv`: a plain-CSV alternative to the workbook.

**The rubric matches the judge's exactly.** The measured facts count as evidence, as do the passages, so an item with no passages can still be `faithful`. The older `wp9_labelling_guide.md` said an empty source is always `major`, which contradicts the judge, so it was removed; git history keeps it. The workbook → CSV → kappa path was tested end to end on 10 Oct with throwaway labels, and the test files were deleted.

The answer key (`research_data/runs/judge_validation/judge_validation_key.json`) stays local and gitignored. **Do not open it, or `research_data/runs/judge_cache.jsonl`, before labelling is finished.**

**Who labels:** one team member, alone. That person must not have seen any judge verdict. Neither the answer key nor the judge cache is on GitHub. Return the filled workbook (or CSV) to Spandan, privately. Spandan has the key, and runs the conversion and kappa steps at the end of `README_WP9.md`.

**How to label:** one sitting, about 3–4 hours.
- Judge each remediation claim by claim, against only the facts and passages shown with it.
- Use `faithful`, `minor_unsupported` or `major_unsupported`.
- Add a one-line note for every label that is not `faithful`.
- Skip nothing.

**After labelling:** save the filled sheet as `wp/wp-9/wp9_judge_labels.csv`. Then, from `backend/` with `DATABASE_URL` set as in the WP-8 runbook, run:

```
python manage.py judge_validation_kappa --labels ../wp/wp-9/wp9_judge_labels.csv --key ../research_data/runs/judge_validation/judge_validation_key.json
```

- It refuses a sheet with any blank or misspelt label, and names the row.
- It writes `judge_validation_kappa.md` beside the key: Cohen's kappa, weighted kappa, the confusion matrix, every disagreement and File C §3.4.1's decision.
- This pipeline was dry-run on 9 Oct against the real key with throwaway labels, and works. The dry run's outputs were deleted.

**Then commit three things:**
1. the labels;
2. the kappa report;
3. `research_data/runs/judge_cache.jsonl`, copied to `wp/wp-8/runs/`; it is safe to publish once labelling is over.

## Order from here

1. ~~Phase 12, commit 7~~: done (§12.19). `v0.12.0` is not moved; commit 7 ships in `v0.13.0`.
2. ~~Phase 13~~: closed at `v0.13.0` (decisions §13.14-13.15).
3. ~~WP-8~~: complete (9 Oct).
4. **WP-9:** Spandan labels the 50-item packet; then kappa.
5. **Phase 14**, then S1 and S3.
