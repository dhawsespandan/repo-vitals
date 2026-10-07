# WP review: status and required updates (7 Oct 2026)

This file is the single source of truth for what each work package still needs. It replaces the 24 Sep review and the 7 Oct status note, which remain in git history.

**Where we should be by now:** WP-1 to WP-6.
**Where we are:** only WP-1 is accepted.

**Rules for every WP:**
- Each `wp/wp-N` folder holds only validated material.
- Submit finished work as `WPx_YYYYMMDD.zip` in Teams (a resubmission is `_v2`). Don't push to `main`.
- A WP counts as accepted only when the reviewer writes "WP-x accepted" in the chat.
- Every fact in a deliverable must be something you checked; label estimates "approx." or "expected".
- Each deliverable is done by the WP owner and states who did it. AI tools may help you understand a step, but must not produce runs, judgments or data. If an AI tool drafted something you then verified, say so in the note.

| WP | Status | Blocked by |
|---|---|---|
| WP-1 | **Accepted** | none |
| WP-2 | Partial: 11 of 40–50 rows | Astha (needs ~1 day) |
| WP-3 | Not started (PR #3 not accepted) | Both judges: post at an agreed time |
| WP-4 | Not run | Astha's laptop (2–3 h) |
| WP-5 | Not run | WP-4, then 2–3 h |
| WP-6 | Can't start yet | Phase 12 code push (Spandan) + WP-2 to WP-5 accepted |
| WP-8 | Not due | Phase 13 code + its pilot (needs WP-5) |
| WP-9 | Not due | WP-8 |

---

## WP-1: Tier-1 weights. ACCEPTED

`wp-1/`: `wp1_tier1_weights.yaml` and `wp1_method_note.md`. The product uses exactly these values (`backend/weights/weights_v1.yaml`).

- **Updates needed:** none.
- **Report-stage note only:** the PyPI paragraph says the "Inactive" classifier is "rarely applied in practice". Before that sentence goes into the black book, either give a number with its source or soften the wording.

---

## WP-2: Anchor set. PARTIAL, not accepted

`wp-2/` holds:
- `WP2_20261006.zip`, as received, with its files extracted:
  - `wp2_anchor_set.csv` (11 rows)
  - `wp2_verification_note.md`
- `wp2_verification_worksheet.md`, which covers 46 candidate repos.

**What's already correct:** all 11 rows are valid known anchors. Each was checked through RepoVitals' own manifest readers at the linked commit:
- it's a direct dependency;
- it resolves to the stated version through an exact pin or a lockfile RepoVitals reads;
- that version is listed on osv.dev or deprecated on npm.

The `why_this_bucket` facts in these rows check out, and they use GitHub's "pushed" date. `googleapis/oauth2client` is correctly marked as a spare: its pin lives only in `samples/`.

**Updates needed:**
1. **Complete the set to 40–50 rows:**
   - healthy 15–20;
   - risky 15–20 (currently 11, all known anchors);
   - in_between 10–15.

   The worksheet already has verified candidates for every bucket.
2. **At least 5 repos with 100+ declared dependencies.** Currently 1 (atom/atom). The worksheet has eslint, prettier, sentry, flux, react-sketchapp, create-react-app and next.js.
3. **Ecosystems roughly 60/40** across the final set, whichever way round.
4. **Choose every bucket yourself.** The worksheet's buckets are an AI draft. Confirm or change each one, and don't run RepoVitals on any of these repos or ask for their scores (File B's rule against anchoring on the formula's output).
5. **Every new row follows the same rules as the 11:**
   - The repo exists.
   - `has_lockfile = true` only for `package-lock.json`, `npm-shrinkwrap.json`, `poetry.lock` or `Pipfile.lock` next to a manifest. `yarn.lock`, `pnpm-lock.yaml` and `uv.lock` count as false.
   - `approx_dep_count` is counted from the manifests.
   - `why_this_bucket` is one sentence of checked facts, using GitHub's "pushed" date.
6. **Extend `wp2_verification_note.md`** to say:
   - who did the checking;
   - that the bucket choices are yours;
   - that no scoring was run.
7. **Keep the 8-column header exactly.** Values must be `healthy` / `risky` / `in_between` and `true` / `false`; no extra columns, no comment lines.

**Acceptance check:** every row is re-verified against GitHub, the registry and osv.dev, plus the bucket counts, the 100+ count and the ecosystem split.

---

## WP-3: AHP matrices. NOT STARTED

`wp-3/`: `wp3_matrix_blank.csv` (File B's template).

**PR #3** (`wp3_matrix_updated.csv`, committed by anindita1807) is **not accepted**:
- It was posted on GitHub on its own, instead of at an agreed time alongside Judge B's matrix, so there's no record that the two were made independently.
- The committer isn't the named Judge A.
- The filename is wrong.

Judge B hasn't seen it and won't before posting his own. A further finding about it will be given after that. Its commits stay on GitHub at `refs/pull/3/head`.

**Updates needed (the full redo):**
1. **Each judge fills a blank copy of the template, alone.** Don't open the WP-1 files, the 24 Sep matrices or anyone else's matrix while filling. Judge A is Astha; Judge B is Spandan.
2. **Upper triangle only; leave the lower triangle blank.** Use Saaty values 1–9, or 1/2 … 1/9.
3. **Each file is only the 5-line CSV:** header plus 4 rows. No comment lines, no weights, no comparisons. Names: `wp3_matrix_A.csv` and `wp3_matrix_B.csv`.
4. **Post both files in Teams at one agreed time.** Neither judge opens the other's file before both are posted. The Teams timestamps are the independence record.
5. **Spandan runs the consistency check** and sends back λmax, CI and CR. If CR is 0.10 or more, he also sends the most inconsistent triads, and only those cells are re-judged.
6. **Reconciliation call:**
   - Discuss the cells where the judges differ by more than 2 scale steps.
   - Either re-judge a cell (record the old value, the new value and why) or take the geometric mean.
   - The reconciled matrix, `wp3_matrix_reconciled.csv`, must also have CR below 0.10.
7. **`wp3_session_notes.md` must contain:**
   - the date, and each judge;
   - what each judge had seen beforehand (both have seen the WP-1 starting matrix: say so);
   - the posting protocol and its timestamps;
   - λmax, CI and CR for all three matrices;
   - each divergent cell, with both positions and how it was resolved ("geometric mean" if that's what happened);
   - the EPSS decision;
   - 3–5 sentences on the two most debated cells;
   - the PyPI v2 rule stated explicitly: how much weight is removed from deprecation, how it's split, and why. Keep the File C limitation L4 sentence.

   Leave out:
   - claims about how the formula behaves, unless worked out from File A §5.2–5.3;
   - claims about what the corpus contains, until WP-5 exists.
8. **No v2 weights file in WP-3.** It's produced at WP-6.

---

## WP-4: Corpus build. NOT RUN

`wp-4/`: `wp4_wp5_runbook.md`, with the exact setup and commands (verified).

**Updates needed:** run it on your own laptop, section 0 then section 1. In short:
1. Create your own GitHub token with no scopes ticked.
2. Point `DATABASE_URL` at the research database on port 5433.
3. Run `migrate` once.
4. Run:
   ```
   build_corpus --seed 42 --target 1000 --config corpus_frame.yaml
   ```
   It takes 2–3 hours; use `--resume` if it's interrupted. Never run it again once WP-5 has started.

**Deliverable:** the unedited `research_data/corpus/` folder plus a 5-line `wp4_signoff.md`. Fill in every checklist value from the generated `strata_report.md`:
- 900–1,100 admitted;
- npm/PyPI split within 45/55;
- no empty stratum cell;
- admission rate 40–60%;
- dedup discards above 0;
- seed, timestamp and config present.

**Acceptance check:** the files are unedited and every value is re-read from them.

---

## WP-5: Corpus scan. NOT RUN

Runbook section 2. Run it right after WP-4.

**Updates needed:**
1. Run:
   ```
   scan_corpus --snapshot-date YYYY-MM-DD --resume
   ```
   Use the same date on every run. The first lines printed must say `Database: repovitals_research`.
2. Run `corpus_report` with the same date.
3. Run the two count queries. The first must show exactly one row for your date.
4. Make the dump with `-U repovitals` via `docker cp`. Don't use `-U postgres`, and don't use `>` redirection.
5. Run `pg_restore -l` and check it lists `scan_history` and `dependency_history`.

**Deliverable:**
- `scan_corpus_report.md`;
- the three `corpus_report` outputs;
- `wp5_signoff.md` with the pasted query output.

Pass criteria:
- at least 95% of repos completed;
- the occurrence count is within the report's own expected range;
- the score histogram spreads across the range;
- the unassessable rate is not dominant.

The dump goes separately, as a OneDrive link.

**Acceptance check:** the dump is restored, the counts are re-run, and there is a single snapshot date.

---

## WP-6: Formula validation sign-off. BLOCKED

Needs:
- the Phase 12 code pushed (Spandan);
- WP-2, WP-3, WP-4 and WP-5 accepted.

**Updates needed when unblocked:**
1. Run `validate_formula` with the accepted WP-3 reconciled matrix and the accepted WP-2 file.
2. Write `wp6_signoff.md` from the real `validation_report/report.md`, walking all six File B checks with real numbers.
3. The anchors table comes from the final WP-2.
4. The sensitivity check covers both ±10% and ±20%, for both the AHP and entropy vectors.
5. Any known anchor scoring Safe is an automatic fail.

---

## WP-8: S3 experiment runs. NOT DUE

Waits for the Phase 13 code and its 20-item pilot, which needs WP-5's corpus. The commands come with Phase 13; don't prepare anything before then.

## WP-9: Judge-validation labels. NOT DUE

`wp-9/`: `wp9_labelling_guide.md` (matches File B Appendix C). The item ids come only from the packet generated after WP-8; don't create the labels file before then.

---

## Order from here

1. **Astha:** setup → WP-4 → WP-5. This is the critical path for both Phase 12 and Phase 13.
2. **In parallel:**
   - Astha completes WP-2 (~1 day);
   - both judges agree a posting time for WP-3.
3. **Spandan:** push the Phase 12 code so WP-6 can run once WP-2 to WP-5 are accepted.
