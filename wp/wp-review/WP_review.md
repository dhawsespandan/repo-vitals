# WP review: status and required updates (8 Oct 2026)

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
| WP-6 | Unblocked: needs the Phase 12 code pushed, then one run | none yet |
| WP-8 | Not due | |
| WP-9 | Not due | |

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

**Still to do by hand:** upload `research_data/exports/wp5_research_db.dump` to OneDrive. It is research data and is not committed.

---

## WP-6: Formula validation sign-off. UNBLOCKED

**Needs:**
- the Phase 12 code, which is on Spandan's local `main` and not yet pushed (`v0.12.0-rc`). It must be rebased onto this branch's history first.
- WP-2 to WP-5, which are now complete. The research database is on this machine: Docker `repovitals-research-db`, port 5433. It can also be recreated from the dump.

**When it runs:**
1. Run the harness on the research database:
   ```
   validate_formula --ahp ../wp/wp-3/wp3_matrix_final.csv --anchors ../wp/wp-2/wp2_anchor_set.csv --pypi-shift "deprecation=-0.0816,severity=+0.0408,staleness=+0.0408"
   ```
2. Write `wp6_signoff.md` from the real `validation_report/report.md`, walking all six of File B's checks with real numbers. The AHP-vs-entropy check carries more weight than File B assumed (see WP-3).
   Check 1 must state that the matrix is a single judgment, so there was no reconciliation (WP-3's final decision).
3. The sensitivity check covers ±10% and ±20%, for both the AHP and the entropy vectors.
4. Any known anchor scoring Safe is an automatic fail.

## WP-8: S3 experiment runs. NOT DUE

Waits for the Phase 13 code and its 20-item pilot. The pilot needs WP-5's corpus, which now exists.

## WP-9: Judge-validation labels. NOT DUE

`wp-9/`: `wp9_labelling_guide.md` (matches File B Appendix C). The item IDs come only from the packet generated after WP-8.

---

## Order from here

1. **Phase 12:** rebase local `main` onto this history, re-verify it, then push.
2. **WP-6:** run it, and sign off or bounce.
3. **Phase 13**, then WP-8 and WP-9.
