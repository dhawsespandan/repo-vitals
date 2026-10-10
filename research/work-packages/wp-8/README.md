# WP-8: S3 experiment runs

**Status: ready to start.** Phase 13 is closed (`v0.13.0`), its 20-item pilot passed, and the labelled set below is frozen. The overall status is in `../wp-review/WP_review.md`.

## The frozen labelled set

`labelled_set.jsonl` in this folder is the set WP-8 runs on. It was extracted on 2026-10-08 from WP-5's snapshot (2026-10-07) by `extract_ground_truth --snapshot-date 2026-10-07`, seed 42.

- **sha256** `75246f3b462c31e9ff77aabc0fdddc182967d639e51334932f6542bacfcba9eb`
- **150 items:**
  - npm: 37 `cve_fix` and 38 `deprecation_replacement`;
  - PyPI: 75 `cve_fix` and 0 `deprecation_replacement`.
- **No PyPI replacement items exist.** None of the corpus's 34 deprecated PyPI packages names a successor in its deprecation text. So PyPI's half is all `cve_fix`. File A expected this stratum to be thin, and the gap is a finding (File C L7), not a fault.
- `extraction_report.md` gives the honest denominator: 1,420 items extracted from 2,044 flagged candidates, with drop counts by reason. It also counts the items whose answer TARGET already shows (decisions §13.13).
- `labelled_set_meta.json` records the quotas and the coverage per stratum.

The runner reads the same file from `research_data/runs/ground_truth/labelled_set.jsonl`, the default location. Its sha256 must equal the one above. **Never re-run `extract_ground_truth --overwrite` once a WP-8 run has started.**

## Before the first run

From `backend/`, with the research database up (`docker start repovitals-research-db`):

1. `backend/.env` needs these keys:
   - `GROQ_API_KEY`, with `GROQ_MODEL=openai/gpt-oss-120b`;
   - `GEMINI_API_KEY`, the judge;
   - `GITHUB_API_PAT`, a token with **no scopes**, used by B and C to fetch changelogs.
2. The judge defaults to `gemini-3.5-flash-lite`. The free tier allows it 500 requests a day and 15 a minute; every 3.x Flash model gets only 20 a day (decisions §13.14). WP-8 needs about 750 judge calls: one per item for A, two for B and C. So judging spans **two days**: when the quota runs out, judging stops and generation carries on, and `analyze_experiment --judge` finishes the rest the next day. Quotas reset at midnight Pacific time. Check the model with one real call before starting. **Keep it fixed for all of WP-8**: the judge cache is keyed by model, so a change of model means re-judging everything.

## The runs (File B WP-8)

One condition at a time, never two together: they share one free-tier budget.

```
python manage.py run_experiment --condition A --items labelled_set.jsonl --resume
python manage.py run_experiment --condition B --items labelled_set.jsonl --resume
python manage.py run_experiment --condition C --items labelled_set.jsonl --resume
```

- **Pace.** One generation every 45 s, which keeps a run under Groq's 8,000 tokens a minute. 150 items take about two hours per condition, plus judging.
- **A missed answer** waits out the minute and asks the same item again.
- **A stop.** A run stops cleanly when the provider stops answering twice. Every finished item is saved; run the same command later and it continues.
- **Failures.** Re-run them with `--retry-failed` (File B: fewer than 5 per condition).
- **Judging** happens inline. If the judge stops for the session, generation carries on; judge the rest afterwards with `analyze_experiment --judge`.
- **Run ids** are `{condition}_75246f3b_openai-gpt-oss-120b`.

## Afterwards

```
python manage.py analyze_experiment --runs A_75246f3b_openai-gpt-oss-120b B_75246f3b_openai-gpt-oss-120b C_75246f3b_openai-gpt-oss-120b --judge
```

This writes `research_data/runs/analysis/tables.md` and one CSV per table.

**Review checklist (File B):**
- each condition reports 150/150 completed;
- failures are under 5 per condition, and retried;
- every condition × ecosystem cell is populated.

**Expected empty:** PyPI × `deprecation_replacement`. The set has none, so that cell is empty by construction. **Do not interpret results**: a null is reported as fully as anything else.

**Deliverable:** the three `runs/` folders plus `wp8_run_log.md` in this folder. The log records dates, interruptions, completion counts and anomalies.

## One decision to take before the first run

The pilot found that PyPI packages mostly retrieve their README rather than a changelog. Precision@k is 0.000 on every PyPI pilot item, and decisions §13.14 (4) gives the measured causes. Widening the changelog search would change the production agent, and with it condition C. **Do it before WP-8 starts, or not until it ends, never in between.** If WP-8 starts as things are, the README-only retrieval is a threat to validity that S3 reports for its PyPI arm.

## The pilot

Phase 13's acceptance pilot ran 20 items from this set through A, B and C, on 2026-10-08. It used its own item file (`pilot/pilot_items.jsonl`), so its run ids (`*_0b2da4cc_*`) differ from WP-8's, and its outputs are kept apart in `research_data/runs/pilot/`. The tables and the run manifests are in `pilot/` here; decisions §13.14 has the results.

The pilot's numbers are a smoke test. Do not read them as results.
