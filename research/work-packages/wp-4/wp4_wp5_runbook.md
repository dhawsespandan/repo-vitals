# WP-4 and WP-5: runbook for your laptop

These are the commands from the 2026-09-24 review, with the reviewer's later correction about the token. Nothing in this folder is a result.

The corpus, the counts, the charts and the dump must all come from your own runs. If a command fails, send the reviewer the **last 30 lines** of its output.

All commands are run from `backend/` unless stated otherwise.

## 0. One-time setup

1. `git pull`
2. `pip install -r requirements.txt -r requirements-research.txt`
3. **Create your own GitHub token.** The reviewer will not send one.
   - Go to GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)** → Generate new token (classic).
   - Tick **no scopes at all**. Set an expiry that covers the rest of the project.
4. In `backend/.env`, set:
   ```
   DATABASE_URL=postgres://repovitals:repovitals@localhost:5433/repovitals_research
   GITHUB_API_PAT=<your token>
   ```
   - Port **5433** is the research database. 5432 is the dev database; the corpus must not go there.
   - Never post `.env` or the token in a chat, and never commit them. `.gitignore` already excludes `.env`.
5. Start Docker Desktop, then run `docker compose --profile research up -d`
6. Run `python manage.py migrate` once, on the empty research database. File B leaves this step out.

**Pre-flight check.** This prints the database name and whether a token is set, without showing the token:

```
python manage.py shell -c "from django.conf import settings as s; print(s.DATABASES['default']['NAME'], s.DATABASES['default']['PORT'], 'PAT set:', bool(s.GITHUB_API_PAT))"
```

It must print `repovitals_research 5433 PAT set: True`.

## 1. WP-4: build the corpus (2–3 hours)

```
python manage.py build_corpus --seed 42 --target 1000 --config corpus_frame.yaml
```

- Use `corpus_frame.yaml`, **not** `corpus_frame_pilot.yaml`.
- If the run is interrupted, rerun the same command with `--resume` added.
- Write down the start time, end time and any interruptions. You will need them for the sign-off.
- The output goes to `research_data/corpus/` at the repo root: `corpus_manifest.json`, `strata_report.md` and the archived manifests.
- Once WP-5 has started, **never run build_corpus again.**

**Checklist.** Read each value from the generated `strata_report.md` and do not edit the file:

- [ ] Total admitted is between 900 and 1,100.
- [ ] The npm/PyPI split is within 45/55.
- [ ] No stratum cell is empty, especially the stale cells. An empty cell means flag it; do not accept it.
- [ ] The admission rate is 40–60%.
- [ ] Dedup discards are above 0.
- [ ] The seed, timestamp and grid config are present.

**Deliverable.** Zip the whole `research_data/corpus/` folder unedited, plus `wp4_signoff.md`, as `WP4_YYYYMMDD.zip`.

The sign-off is 5 lines:

1. The date and duration of the run.
2. Any interruptions.
3. The actual value of each checklist item.
4. Anything flagged.

## 2. WP-5: scan the corpus (2–3 hours)

1. **Pick the snapshot date once.** Use the date you start, and pass the same value on every run and every resume:
   ```
   python manage.py scan_corpus --snapshot-date YYYY-MM-DD --resume
   ```
   - The first lines it prints must say `Database: repovitals_research`. If they say anything else, **stop immediately**.
   - Leave out `--corpus`; the default path is correct.
   - The run may pause near GitHub's hourly limit, which is normal. If it stops, rerun the exact same command.
2. The completion report is written to `research_data/corpus/scan_corpus_report.md`.
3. Generate the charts:
   ```
   python manage.py corpus_report --snapshot-date YYYY-MM-DD
   ```
   This writes `score_histogram.png`, `flagged_rate_by_stratum.png` and `corpus_report.md`.
4. Run the count check and paste both outputs into the sign-off:
   ```
   docker exec repovitals-research-db psql -U repovitals -d repovitals_research -c "SELECT data_source, snapshot_date, count(*) FROM scan_history GROUP BY 1,2;"
   docker exec repovitals-research-db psql -U repovitals -d repovitals_research -c "SELECT count(*) FROM dependency_history;"
   ```
   The first must show exactly one row: `corpus_scan`, your date, and a count close to the admitted total.
5. Create the dump. Use `-U repovitals`, not `-U postgres`, and don't use `>` redirection, which corrupts binary files on PowerShell:
   ```
   docker exec repovitals-research-db pg_dump -U repovitals -Fc -f /tmp/wp5_research_db.dump repovitals_research
   docker cp repovitals-research-db:/tmp/wp5_research_db.dump ./wp5_research_db.dump
   docker exec repovitals-research-db pg_restore -l /tmp/wp5_research_db.dump
   ```
   The last command must list `scan_history` and `dependency_history`.

**Checklist:**

- [ ] At least 95% of repos completed. 50 or more failures means flag it.
- [ ] The scored-occurrence count is within the report's own expected range.
- [ ] The histogram spreads across the score range. Almost everything in one class means flag it.
- [ ] The unassessable rate is reported and is not dominant.

**Deliverable.** A zip named `WP5_YYYYMMDD.zip` containing `scan_corpus_report.md`, the three `corpus_report` outputs and `wp5_signoff.md`.

The sign-off is 5 lines plus the pasted query output:

1. The snapshot date.
2. The weights version.
3. The completed and failed counts.
4. The occurrence and unassessable counts.
5. The dump size, and anything flagged.

The dump itself goes separately, as a OneDrive link. (Superseded: it is committed as `wp/wp-5/wp5_research_db.dump` since `cabf0d9`.)
