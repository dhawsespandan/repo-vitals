# Raw run records (archived 2026-10-10)

`research_data/` is git-ignored: only manifests are versioned there. The
records below existed only on the research machine. They are copied into
`wp/wp-N/raw/`, next to the work package they support, so that the corpus
build, the corpus scan, WP-6 and WP-8 can be audited and written up from a
fresh clone. Each `raw/` folder mirrors `research_data/`'s layout:
copy `wp/wp-N/raw/<path>` back to `research_data/<path>` to restore a file.
They are stored byte for byte (`.gitattributes`: `wp/*/raw/** -text`).

The research database itself (Docker `repovitals-research-db`) needs nothing
new: on 2026-10-10 every table in it matched `wp/wp-5/wp5_research_db.dump`
row for row (914 `scan_history`, 29,494 `dependency_history`; a per-table
checksum over a scratch restore of the dump). Restore it with `REPLICATION.md` §3.

## What is here

| Path | What it is | Why keep it |
|---|---|---|
| `wp-4/raw/corpus/.checkpoint/candidates.jsonl` | All 1,343 candidates `build_corpus` examined, with each verification outcome | The 914/1,343 admission rate (npm 83%, PyPI 57%) and the sampling weights' denominator. GitHub search results cannot be re-fetched as of 2026-10-07 |
| `wp-4/raw/corpus/.checkpoint/cells.jsonl`, `run.jsonl` | The 1,326 search cells after splitting, and the run's seed / target / run date | The frame enumeration behind `strata_report.md` |
| `wp-4/raw/logs/wp4_build_corpus.log` | The final WP-4 run's log, including its resume | Run timings and the resume record |
| `wp-4/raw/logs/wp4_attempt1_*` | Attempt 1 (374 candidates examined), run before the allocation fix `a5ba223` | Evidence for the per-slice allocation defect (decisions §11.29) |
| `wp-4/raw/pilot_2026-09-17/` | Phase 11's live pilot: manifest, strata and scan reports, checkpoints | Phase 11 acceptance (decisions §11.26) |
| `wp-5/raw/exports/corpus_2026-10-07_v1_*` | The corpus panel under `v1`: 914 repositories, 29,494 occurrences, CSV + manifest | S1 analysis without a database |
| `wp-5/raw/exports/corpus_2026-10-07_v2_*` | The same panel rescored under `v2` (`rescore --weights v2 --out`, `REPLICATION.md` §4) | S1 analysis under `v2`; 816 of 914 repository scores differ from the stored `v1` ones |
| `wp-5/raw/corpus/scan_checkpoint.jsonl` | Checkpoint of the one-repository rescan after `20ad659` (decisions §11.30) | Matches `wp-5/scan_corpus_report_rescan_one_repo.md` |
| `wp-5/raw/logs/wp5_scan_corpus.log` | The full WP-5 scan log | Per-repository timings and outcomes |
| `wp-5/raw/logs/pytest_final.log` | The backend suite on 2026-10-08, at `20ad659` (997 passed) | Test evidence |
| `wp-6/raw/logs/wp6_validate_formula.log` | The 23-minute `validate_formula` run | WP-6 run record |
| `wp-8/raw/runs/ground_truth/ground_truth_candidates.jsonl` | The 1,420 items `extract_ground_truth` extracted from 2,044 flagged candidates; `labelled_set.jsonl`'s 150 were sampled from these | S3's sampling frame. Built from live OSV and registry data, so it cannot be rebuilt later |
| `wp-8/raw/runs/ground_truth_attempt1_listed_versions_bug/` | The first extraction, which dropped 771 of 783 PyPI items | Evidence for the PyPI listed-versions defect (decisions §13.14, fixed `d1602ef`) |
| `wp-8/raw/runs/pilot/*/items.jsonl`, `pilot/judge_cache.jsonl` | The pilot's traces (20 items × A/B/C) and its judge verdicts | `wp-8/pilot/` already holds the pilot's tables; these are the traces behind them |
| `wp-8/raw/runs/pilot_D/` | Condition D's pilot (2 items) | The only run of condition D so far (File C §9.3, RQ4) |
| `wp-8/raw/runs/pilot_attempt1_tpm_and_judge_503/` | The first pilot, stopped by Groq's tokens-per-minute limit and Gemini 503s | Evidence for the free-tier pacing findings (decisions §13.14) |
| `wp-8/raw/logs/` | Logs of both extractions, both pilots, the A/B/C runs, the analysis, and the key ledger (member names only, no keys) | The source of `wp8_run_log.md` |
| `wp-8/raw/wp8_run_all.ps1` | The launcher that ran A → B → C over the members' keys | Method record; it reads keys from `backend/.env.team` at run time and holds none |
| `wp-9/raw/logs/pytest_wp9fix.log` | The backend suite after the packet fix `a42d2ad` (1,340 passed, 3 skipped) | Test evidence |

One operator note in `wp4_build_corpus.log` was reworded to "after the working
session ended"; every other file is byte-identical to the original.

## What stays on the research machine, and why

- **Withheld under `REPLICATION.md` §9 until File C §3.7's judge decision:**
  `research_data/runs/judge_cache.jsonl` (all 450 generations' judge
  verdicts), `runs/judge_validation/judge_validation_key.json`,
  `judge_validation_kappa.md`, and the `attempt1_packet_hid_measured_fields/`
  folder (attempt 1's key, labels, workbook and kappa report). Publishing them
  would unblind a fresh 50 if option 1 is chosen. Publish them once the choice
  is made.
- **Other people's repository contents**, re-fetchable by their recorded SHAs
  (`REPLICATION.md` §9): the archived manifest blobs (`corpus/blobs/`,
  `pilot_2026-09-17/blobs/`, `validation_report/anchors/blobs/`) and the
  retrieved changelogs, READMEs and issues behind S3's generations
  (`runs/_docs/`, `runs/pilot/_docs/`, `runs/pilot_D/_docs/`). The passages
  each generation actually saw are already in the traces in `wp-8/runs/`.

Keep a private backup of both groups (for example, a zip of `research_data/`
on a cloud drive). The judge cache cost about two days of free-tier judge
quota to produce.
