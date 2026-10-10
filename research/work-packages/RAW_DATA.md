# Raw run records (archived 2026-10-10, completed 2026-10-11)

`research_data/` is git-ignored: only manifests are versioned there. Its whole
content, which existed only on the research machine, is copied into
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
| `wp-8/raw/runs/judge_cache.jsonl` | The judge's verdicts on all 450 WP-8 generations (rubric v1, Gemini Flash-Lite) | Regenerates WP-8's faithfulness tables; about two days of free-tier judge quota to rebuild |
| `wp-9/raw/runs/judge_validation/` | WP-9's answer key, kappa report, packet and template; `attempt1_packet_hid_measured_fields/` holds attempt 1's key, labels, workbook, packet and kappa report | WP-9's kappa (0.134) and attempt 1's invalidation (decisions §13.16-13.17) |
| `wp-5/raw/corpus/blobs/` | The 2,542 manifest and lockfile blobs the corpus scan read, named by git blob SHA | The exact inputs of every corpus score (verified against their SHAs in `wp5_signoff.md`) |
| `wp-6/raw/validation_report/anchors/blobs/` | The 465 manifest blobs behind WP-6's anchor scan | The exact inputs of `anchor_scan.json` |
| `wp-4/raw/pilot_2026-09-17/blobs/` | The 26 manifest blobs of Phase 11's pilot | Phase 11 acceptance inputs |
| `wp-8/raw/runs/_docs/`, `runs/pilot/_docs/`, `runs/pilot_D/_docs/` | The changelogs, READMEs and issues retrieved for S3's generations (one JSON per package: repository, path, SHA, text) | Re-running generation or retrieval against the same documents; condition D's issue text |

One operator note in `wp4_build_corpus.log` was reworded to "after the working
session ended"; every other file is byte-identical to the original.

## Notes on what was added on 2026-10-11

- **The judge files were published before File C §3.7's decision**, at the
  owner's decision (2026-10-11), so GitHub holds every copy of the research
  data. `REPLICATION.md` §9 had withheld them to keep a fresh 50 blind. If
  §3.7's option 1 is taken, the fresh 50 must be labelled by someone who has
  not opened `wp-8/raw/runs/judge_cache.jsonl` or `wp-9/raw/runs/judge_validation/`
  (as well as decisions §13.16-13.17), and S3 must state that these files were
  public while the labelling took place.
- **The blobs and `_docs` files are other people's repository contents**,
  archived for reproducibility under their original licences. Each one is
  identified by its source repository and git SHA. Some contain author email
  addresses that the projects publish in their own manifests.
- A secret-pattern scan (API keys, tokens, credentials in URLs) found nothing
  in any archived file.

## What is not archived

- `backend/.env` and `backend/.env.team`: API keys. They must never be in a
  public repository. Rotate them at project end.
- Local SQLite test databases, `backend/.chroma/` and `frontend/dist/`:
  build and test artifacts, regenerated by the commands that made them.
- The unedited original of `wp4_build_corpus.log` (see above).
