Hi Astha, I've reviewed everything you pushed on 24 Sep (WP-2, 3, 4, 5, 6, 8, 9) against Files A, B and C, the live GitHub repos, and the actual code the tools run.

**Short version: none of it can be accepted yet.** WP-2 and WP-3 contain real work, but both have to be redone. WP-4, 5, 6, 8 and 9 are empty templates (every result is FILL_IN or PENDING), so there's nothing to accept there yet. Details, exact fixes, and what I'll check when you resubmit are below. This all ends up in the black book and gets questioned at the viva, so every number and every sentence has to be something we actually checked.

---

**PRIORITY ORDER**

1. **WP-4, then WP-5, start now.** Phase 12 can't start without them. The tools are ready (Phase 11 is released).
2. **WP-2 rebuild and WP-3 redo:** do these in parallel while WP-4/5 are running. Both are needed before WP-6.
3. **WP-6:** only after I push the Phase 12 code and tell you to go.
4. **WP-8 and WP-9:** only after Phase 13 code exists. Don't prepare anything for them yet.

WP-1 is already accepted. It's in wp/wp-1, and the product uses those exact numbers.

---

**HOW TO SUBMIT (applies to every WP)**

- **Please don't push to main any more.** Every push to main redeploys the live site. And commits titled "Add WP-6 implementation" record work as done that hasn't been done. I'll remove the template files already there.
- **Send each finished deliverable here as a zip:** WPx_YYYYMMDD.zip (a resubmission is WPx_YYYYMMDD_v2.zip). This is File B's handoff rule. I'll commit accepted versions to wp/. Never edit something after sending it; send a new version instead.
- **Only send finished work.** No templates, no FILL_IN, no PENDING.
- **Every factual claim must be something you checked**: dates, counts, versions, "archived", "not pushed since". If something is an estimate, write "approx." or "expected".
- **Never paste the .env or the GitHub token into this chat.**
- **Acceptance is a written "WP-x accepted" from me in this chat.** Until then, the WP is open.

---

**WP-2: REBUILD NEEDED**

I checked every row against GitHub.

**Problem 1. None of the 5 known anchors works.** These are the pass/fail cases, so this blocks WP-6.
- nicedoc/nicedoc.io: the repo doesn't exist (404).
- TalAter/UpUp (lodash@3.10.1): lodash isn't in its package.json at all (0 dependencies, 12 devDependencies, none of them lodash). It only appears as an indirect dependency. RepoVitals reads only the dependencies declared in manifests, so it will never see this.
- strongloop/loopback (moment@2.24.0): moment isn't declared anywhere in its 60 dependencies.
- omab/django-social-auth (django@1.8.x): it declares django>=1.2.5, a range with no lockfile. RepoVitals checks an unlocked range against the package's latest release, so it scores current Django, not 1.8.
- pinax/pinax (django@1.4.x): its requirements.txt contains mkdocs, github3.py, semver and tabulate. It's a documentation repo with no Django in it.

**Problem 2. Four repos don't exist (404):** nicedoc/nicedoc.io, Unitech/pm2-gui, Pylons/repoze.bfg, lincolnloop/django-geoip. All four are in the risky bucket, which drops it to 11 (minimum is 15).

**Problem 3. has_lockfile is wrong on 14 of the 36 repos that exist.**
- Says true, but there's no lockfile: express, eslint, httpx, fastapi, pydantic, loopback, kraken-js, assemble, passport-local, grunt, np.
- Says false, but there is one: UpUp, Modernizr, django-allauth.

**Problem 4. approx_dep_count is wrong by up to 5x,** so the "100+ dependencies" rule fails. Declared counts: koa 23 (you wrote 105), assemble 29 (140), mocha 54 (115), loopback 60 (110), kraken-js 30 (62), UpUp 12 (22). Only prettier, react, next.js and nest plausibly have 100+, and File B needs at least 5.

**Problem 5. Several why_this_bucket sentences are false,** judged by GitHub's last-push date (the same "pushed:" filter File B tells you to use):
- UpUp was pushed 2026-09-09 (you wrote "not since 2017").
- yeoman/yo was pushed 2026-08 (you wrote "2021").
- kraken-js was pushed 2025-08 (you wrote "2019").
- passport-local was pushed 2024-02 (you wrote "2021").
- assemble was pushed 2022-02 (you wrote "2020").
- django-social-auth is not archived (you wrote "Archived 2016").

**Problem 6. Method.** File B asks you to open each repo's package.json / requirements.txt and skim it before writing the row. The errors above look like rows written from memory. Please rebuild every row from the actual files, and tell me how you checked.

**Rules for the resubmission**

1. **40–50 rows.** Healthy 15–20, risky 15–20, in_between 10–15. (File B's "30–50" can't hold together with the bucket minimums, which add up to 40.) Aim for about 45 so one dead repo doesn't break a minimum.
2. **At least 7 known anchors** (File B's minimum is 5; the extras are spares). Each known anchor must meet ALL of these:
   - a) The repo exists. Prefer ARCHIVED repos: they can't change between now and WP-6.
   - b) The anchor package is a DIRECT dependency in a manifest: package.json, requirements*.txt, pyproject.toml, Pipfile or setup.py. An indirect dependency doesn't count.
   - c) The bad version is locked in one of two ways. Either it's pinned exactly in the manifest (npm "2.88.2", Python ==1.4.22), or a lockfile RepoVitals reads sits beside that manifest and records it: package-lock.json or npm-shrinkwrap.json (beside package.json), poetry.lock (beside pyproject.toml), or Pipfile.lock (beside Pipfile). RepoVitals ignores yarn.lock, pnpm-lock.yaml, uv.lock and pdm.lock, so a version locked only in those does NOT count. A range like ^2.0.0 or >=1.2 with no readable lockfile does NOT count.
   - d) The version is bad in a way RepoVitals can see: marked deprecated on the registry (npmjs.com shows a "deprecated" message), yanked on PyPI, or with a known vulnerability affecting that exact version on osv.dev. A package that's merely "old" or "legacy" doesn't qualify. For example, moment is not deprecated on npm.
   - e) In why_this_bucket, write the manifest path, the exact declared version text, and the evidence. Example: package.json: "request": "2.88.2"; npm marks request deprecated.
   - f) Use anchor_package in the form name@exact-version.
3. **has_lockfile = true only for a lockfile RepoVitals reads** (the list in 2c). If a repo has yarn.lock or pnpm-lock.yaml, put false and mention it in why_this_bucket.
4. **approx_dep_count = the number of dependencies declared across the repo's manifests, counted from the files.** RepoVitals reads every manifest in the repo, shallowest first, up to 50. That includes examples/ and test fixture folders; it skips only node_modules, vendor, bower_components, site-packages and venv folders. Keep that in mind for "healthy" repos too: a big monorepo with an examples/ folder full of old projects isn't healthy from the tool's point of view.
5. **At least 5 repos with 100+ declared dependencies,** by that count.
6. **ecosystem = the ecosystem of the repo's manifests.** django/django and django-allauth also contain npm manifests; say so in why_this_bucket.
7. **why_this_bucket: one sentence, and every fact in it checked.** No unverifiable claims like "all 240 deps current".
8. **Keep the exact 8-column header:** repo_url, ecosystem, bucket_seeded, is_known_anchor, anchor_package, approx_dep_count, has_lockfile, why_this_bucket. Values: healthy / risky / in_between; true / false. No extra columns, no comment lines.
9. **File B's anchoring rule still applies.** Checking the registry and osv.dev for the anchor package is required. Running RepoVitals on the repos, or asking me for their scores, is not allowed.

**What I'll check:** every row against live GitHub, as I did this time. Every known anchor's manifest line and version, plus its registry/OSV evidence. Lockfiles, dependency counts, bucket counts, and the push/archive claims.

---

**WP-3: REDO NEEDED (the two judgments weren't independent)**

This is the headline methodology claim of the S1 paper and of the black book. The examiners will probe it first.

**Problem 1.** Matrix A is the WP-1 starting matrix, cell for cell (2, 3, 4, 2, 3, 2). Its reasons are WP-1's per-cell reasons, reworded. Calling it a "knowledge-informed independent review" doesn't make it an independent judgment. It's the starting matrix resubmitted.

**Problem 2.** Matrix B, as delivered, can't be the blind submission the notes describe. Its comments quote Judge A's values and reasoning ("DIVERGES from A (A=4)", "agreed with Judge 1's reasoning"). Someone filling blind couldn't write that. Also, "Judge B had no prior knowledge of the WP-1 seed" is not true: I was in the WP-1 session.

**Problem 3. The consistency numbers are wrong** (I recomputed them). Correct values:
- A: λmax = 4.031, CI = 0.0103, CR = 0.0115 (the notes say 4.035 / 0.0117 / 0.013). The footnote calling this "rounding" is wrong; the λmax itself is off.
- B: λmax = 4.154, CR = 0.057. B's weight vector is 0.338 / 0.401 / 0.143 / 0.119 (the notes say 0.336 / 0.397 / 0.146 / 0.122).
- Reconciled: λmax = 4.077, CR = 0.028. The reconciled weight vector (0.40 / 0.34 / 0.15 / 0.11) is correct.

**Problem 4.** "The consistency tool was run": the plan's tool doesn't exist yet (it's Phase 12). Tell me what was actually used.

**Problem 5. The resolution text contradicts the result.** For Deprecation vs Staleness, the notes argue "closer to 3". For Severity vs Count, they conclude "Judge A's reading (2) is defensible". Both then take the plain average of the two judges (2.83) anyway. That text goes nearly word-for-word into the paper, so it has to describe what actually happened.

**Problem 6. The notes make a wrong claim about how the formula behaves:** that a strong deprecation weight "classifies a deprecated package as High and a 4-year-silent one only as Medium".
- In the real formula (File A §5.2–5.3) with WP-1's weights, a repo whose only problem is one deprecated dependency scores 54 (Medium).
- A repo whose only problem is one fully stale dependency scores 90 (Safe).
- Classification is per repository, not per package.

**Problem 7.** The notes state things about the corpus ("CVSS 7–8 with counts 3–6 is the typical case", "stale packages far more common than deprecated") before WP-5 has produced any data. Remove them, or label them as expectations.

**Problem 8. The PyPI paragraph contradicts itself.**
- It says 0.401 is "more weight" than 0.46. It isn't.
- It says the cut was "re-evaluated rather than mechanically inherited", but it's exactly the same absolute cut as WP-1: 0.14 taken off deprecation.
- WP-1 split that 0.14 equally, 0.07 each. This splits it 0.09 to severity and 0.05 to staleness, with no reason given.

**Problem 9.** weights_v2_draft.yaml isn't a WP-3 deliverable (File B lists four files). It also says "ahp-entropy-validated", which is false until WP-6. Drop it. The v2 weights file gets produced at WP-6.

**Procedure for the redo**

1. **Each judge fills a BLANK copy of File B's template,** with neither the WP-1 files, the old Matrix A nor any other matrix open. You're Judge A; I'm Judge B, and I'll fill mine myself. Write your reasoning for each cell in your own notes, not in the CSV.
2. **Fill the upper triangle only. Leave the lower triangle empty, exactly as the template shows;** the tool computes exact reciprocals. (The 0.333 / 0.500 values in the delivered files aren't exact reciprocals.) Use Saaty values: 1–9, or 1/2 … 1/9 when the column signal is the more important one.
3. **Each matrix file is ONLY the 5-line CSV:** header plus 4 rows. No comment lines, no derived weights, no comparisons with the other judge. Name, date and reasoning go in the session notes.
4. **Independence record:** we agree a time, and both post our matrix files in this chat at that time. Neither opens the other's before both are posted. The Teams timestamps are our evidence.
5. **I'll run the consistency check (File B step 2)** and send you λmax, CI and CR. If a matrix is at 0.10 or above, I'll also send the most inconsistent triads. Re-think only those cells.
6. **Reconciliation call:** discuss the cells where we differ by MORE than 2 steps on the scale (…1/3, 1/2, 1, 2, 3…), per File B. Either agree a re-judged value (record old and new values and why), or accept the geometric mean. The reconciled matrix is the geometric mean of the two judges for every cell, except any cell re-judged in the call. It must also have CR below 0.10.
7. **EPSS decision:** record it again (deferring it is fine).

**Session notes (wp3_session_notes.md) must contain:**
- date and the two judges;
- what each judge had seen beforehand (we've both seen the WP-1 starting matrix; say so honestly);
- how independence was ensured (the posting protocol and its timestamps);
- λmax, CI and CR for all three matrices, from the check I send you;
- every cell that differs by more than 2 steps, both positions, and how it was resolved. If it was resolved by the geometric mean, say exactly that;
- the EPSS decision;
- 3–5 sentences on the two most debated cells;
- the PyPI v2 rule stated explicitly (how much deprecation weight is removed and how it's split, with the reason). The PyPI vector is still "same session, reasoned redistribution" (File C limitation L4); keep that sentence.

Nothing in the notes about formula behaviour unless it's worked out from File A §5.2–5.3. Nothing about corpus composition until WP-5 exists.

**What I'll check:** the posting timestamps, the CSV format, CR/λmax recomputed independently, reciprocity, the geometric-mean arithmetic, and that the notes match what happened.

---

**WP-4: CORPUS BUILD (do this first)**

Your template files can't be used. The stratum table in your strata_report.md is invented and doesn't match the real sampling grid: 3 languages × 5 star bands (5–20, 21–50, 51–200, 201–1000, 1000+) × last-push bands, defined in backend/corpus_frame.yaml. The tool writes its own strata_report.md with the checklist already computed. Delete the templates.

**One-time setup** (from the repo's backend/ folder):
1. git pull (to get the latest code).
2. pip install -r requirements.txt -r requirements-research.txt
3. In backend/.env, set:
   DATABASE_URL=postgres://repovitals:repovitals@localhost:5433/repovitals_research
   Port 5433 is the research database. The default in .env.example (5432) is the dev database; the corpus must not go there.
4. **I'll send you a NEW GitHub token privately** (the old one is revoked). Put it in .env as GITHUB_API_PAT. Don't post it here.
5. Start the research database:
   docker compose --profile research up -d
6. Create the tables once, on the empty research database:
   python manage.py migrate
   File B leaves this step out. scan_corpus can't write without it.

**Run** (from backend/):
```
python manage.py build_corpus --seed 42 --target 1000 --config corpus_frame.yaml
```
- Use corpus_frame.yaml, NOT corpus_frame_pilot.yaml.
- **It takes 2–3 hours, not 1.** It has to enumerate the whole 240-cell grid first.
- If it's interrupted, rerun the same command with --resume added.
- Output: research_data/corpus/ at the repo root (corpus_manifest.json, strata_report.md and the archived manifest files).
- **After WP-5 has started, never run build_corpus again.** Rebuilding changes the corpus.

**Review (File B checklist).** The strata_report.md the tool writes computes these; confirm each one:
- total admitted 900–1,100;
- npm/PyPI split within 45/55;
- NO empty stratum cell, especially the stale cells (an empty one means flag it; don't accept);
- admission rate 40–60%;
- dedup discards above 0;
- seed, timestamp and grid config present.

**Deliverable:** zip the whole research_data/corpus/ folder, unedited, plus wp4_signoff.md. The sign-off is 5 lines: the date and duration of the run, any interruptions, the actual value of each checklist item, and anything flagged.

**What I'll check:** the generated files are unedited and consistent with each other, and every checklist value is re-read from them.

---

**WP-5: CORPUS SCAN (right after WP-4)**

1. **Pick the snapshot date once** (the date you start, e.g. 2026-09-26) and pass the SAME value on every run, including every resume:
```
python manage.py scan_corpus --snapshot-date 2026-09-26 --resume
```
   - If you leave --snapshot-date out, it defaults to today's date in UTC, which changes at 05:30 IST. A run that continues past that, or is resumed the next day, silently splits the corpus across two dates.
   - Leave out --corpus. The default path is correct; File B's "research_data/corpus/…" path is wrong when run from backend/.
   - The first lines it prints must say "Database: repovitals_research". If they say anything else, stop immediately.
   - Takes 2–3 hours. It may pause itself near GitHub's hourly limit (normal). If it stops, rerun the exact same command.
2. **Completion report:** research_data/corpus/scan_corpus_report.md.
3. **Charts: run them yourself** (my laptop can't render them):
```
python manage.py corpus_report --snapshot-date 2026-09-26
```
   This writes score_histogram.png, flagged_rate_by_stratum.png and corpus_report.md beside the manifest.
4. **Count check. Paste the output of both queries in your sign-off:**
```
docker exec repovitals-research-db psql -U repovitals -d repovitals_research -c "SELECT data_source, snapshot_date, count(*) FROM scan_history GROUP BY 1,2;"
docker exec repovitals-research-db psql -U repovitals -d repovitals_research -c "SELECT count(*) FROM dependency_history;"
```
   The first must show exactly ONE row: corpus_scan, your date, and a count close to the admitted total.
5. **Database dump.** Use these exact commands. File B's "-U postgres" fails, because the database user is repovitals. And don't use ">" redirection: on Windows PowerShell it corrupts binary files.
```
docker exec repovitals-research-db pg_dump -U repovitals -Fc -f /tmp/wp5_research_db.dump repovitals_research
docker cp repovitals-research-db:/tmp/wp5_research_db.dump ./wp5_research_db.dump
docker exec repovitals-research-db pg_restore -l /tmp/wp5_research_db.dump
```
   The last command must list the scan_history and dependency_history tables.

**Review (File B checklist):**
- at least 95% of repos completed (a handful of deleted/renamed ones is normal; 50+ failures means flag it);
- the scored-occurrence count is within the report's own expected range;
- the histogram spreads across the score range (almost everything in one class means flag it);
- the unassessable rate is reported and not dominant.

**Deliverable:**
- a zip with scan_corpus_report.md, the three corpus_report outputs, and wp5_signoff.md. The sign-off is 5 lines plus the pasted query output: snapshot date, weights version, completed/failed counts, occurrence and unassessable counts, dump size, anything flagged.
- The dump goes separately, as a OneDrive link here (it's too big for the zip).

**What I'll check:** I restore the dump, re-run the counts, confirm there's a single snapshot date, and compare against your report.

---

**WP-6: WAIT FOR PHASE 12**

It needs the validate_formula tool, which doesn't exist yet. Delete the template. It hard-codes the old (invalid) anchors and the old AHP weights, both of which will change. When I say go, write the sign-off from the real validation_report/report.md. It must walk all six File B checks with the real numbers, and the sensitivity check must cover BOTH ±10% and ±20% for BOTH weight vectors (your template only had ±10%).

---

**WP-8 and WP-9: WAIT FOR PHASE 13**

Delete both templates.
- WP-8: the midnight-UTC rule, the developer-assigned run ids and the analyze_experiment flag formats were guesses about tools that don't exist yet. The real commands will come with Phase 13.
- WP-9: the ITEM-001…050 ids must come from the packet I generate. Made-up ids or PENDING labels will break the kappa calculation. Your labelling guide itself matches File B Appendix C; keep it for when the packet arrives.

---

Order recap: setup → WP-4 → WP-5, and in parallel the WP-2 rebuild and the WP-3 redo (let's fix a time for the matrix posting). Send each one as it's finished; don't batch them. Thanks. I know this is a lot, but these files become the methodology chapter, so it's worth getting right once.
