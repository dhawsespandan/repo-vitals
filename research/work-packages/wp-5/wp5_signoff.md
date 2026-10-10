# WP-5 sign-off: corpus scan

**Run**
- **Command:** `scan_corpus --snapshot-date 2026-10-07 --resume`
- **Machine:** Spandan's
- **Database:** research Postgres on port 5433. The first lines printed `Database: repovitals_research`.
- **Time:** 2026-10-07 23:16 → 2026-10-08 00:58 UTC, about 1 h 42 min.
- **Interruptions:** none. 426 REST calls, 0 search calls, 0 rate-limit pauses.

**The five lines File B asks for:**

1. **Snapshot date:** 2026-10-07 on every row. It is the same date as the WP-4 run, and was given explicitly.
2. **Weights version:** `v1` on every row. The formula version on all 914 `scan_history` rows is `v1`.
3. **Completed / failed:** 914 of 914 scanned (100%), 0 failed.
4. **Occurrences / unassessable:**

   | | Occurrences | Unassessable |
   |---|---|---|
   | npm | 20,254 | 373 |
   | PyPI | 9,240 | 318 |
   | **Total** | **29,494** | **691 (2.3%)** |

   Flagged: 9,894 (33.5%).
5. **Dump:** `research_data/exports/wp5_research_db.dump`, 1,548,412 bytes.
   - sha256 `82602febee9edecdea657773be420f0a8ba568b1bd19db18823e60206550276f`
   - `pg_restore -l` lists `scan_history` and `dependency_history`.
   - It was restored into a scratch database: the same 914 / 29,494 rows and the same total score (42,161.55). The scratch database was then dropped.

The dump is committed as `wp/wp-5/wp5_research_db.dump` (since `cabf0d9`, same sha256); `REPLICATION.md` §3 restores it from there.

**Checklist:**

| Check | Result |
|---|---|
| At least 95% of repos completed | **pass**: 914/914, 0 failures |
| Occurrence count within the expected range | **pass, and checked more strictly than a range** (below) |
| The histogram spreads across the score range | **pass**: `score_histogram.png` uses the whole 0–100 range in both ecosystems; see the class table below |
| Unassessable rate reported and not dominant | **pass**: 2.3% |

**How the occurrence count was checked.** Neither File B (≈40,000) nor the completion report gives a usable range; File B's figure was an a-priori estimate. Instead, for every repository, the distinct (ecosystem, package) names the scan wrote were compared with the `dependency_count` WP-4's builder recorded from the same manifest bytes. They agree for **914 of 914**.

The occurrence total, 29,494, is larger than the builder's 22,114 distinct names because a package declared in several manifests is one occurrence per manifest.

**Classes:**

| Ecosystem | Safe | Medium | High alert |
|---|---|---|---|
| npm | 136 | 38 | 301 |
| PyPI | 134 | 103 | 165 |
| npm + PyPI | 3 | 2 | 32 |
| **Total** | **273 (30%)** | **143 (16%)** | **498 (54%)** |

165 repositories score exactly 0.00, where §5.3's clamp holds them.

**Flagged: the npm skew.** npm leans toward High alert, with a thin Medium band (38). That matches the dependency-count confound in decisions §11.27: npm repos declare more dependencies, and the roll-up sums them. It is not a reason to reject the data, but S1 must control for dependency count before comparing ecosystems.

**Interruptions and corrections:**
- **One repository rescanned.** WP-4's machine went down at 03:07 IST, mid-run. Two archived manifest blobs written at that moment were zero-filled, though their size was recorded: a write-cache loss.
  - All 2,542 archived blobs were then verified against their git SHAs. Those 2 were the only bad ones, both from one admitted repo, `jeonghwan-kim/lecture-frontend-dev-env`.
  - They were re-fetched by SHA (content-addressed, so the bytes are identical) and verified. The archive now checks every blob against its SHA on write and on read (decisions §11.30, commit `20ad659`).
  - The repo's 26 rows were deleted, and it was rescanned with `--repo`. It now has 38 occurrences, with the score unchanged at 0.00 (high_alert).
  - `scan_corpus_report_rescan_one_repo.md` is that run's report. `scan_corpus_report.md` is the main run's, unedited.
  - All counts above are from the database after the rescan.
- **The stratum chart was fixed.** `corpus_report`'s flagged-rate chart and its "strata" count were keyed by split cell, giving 575 "strata" for a frame of 240. They now group by stratum (`charts.py`, decisions §11.30, commit `20ad659`), and the figures here are from the fixed version.

**Pasted query output:**

```
$ docker exec repovitals-research-db psql -U repovitals -d repovitals_research -c "SELECT data_source, snapshot_date, count(*) FROM scan_history GROUP BY 1,2;"
 data_source | snapshot_date | count
-------------+---------------+-------
 corpus_scan | 2026-10-07    |   914
(1 row)

$ docker exec repovitals-research-db psql -U repovitals -d repovitals_research -c "SELECT count(*) FROM dependency_history;"
 count
-------
 29494
(1 row)
```

**Zero writes to the product's tables.** The research database's operational tables are all empty: `scan_runs`, `repositories`, `dependency_occurrences`, `packages`, `reports`, `app_users` and `agent_execution_traces`. Only `scan_history` and `dependency_history` hold rows.
