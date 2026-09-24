# WP-8 Experiment Run Log

**Study:** S3 — Retrieval grounding across ecosystems  
**Labelled set:** `labelled_set.jsonl` (150 items: 75 npm / 75 PyPI; frozen before first run)  
**Conditions:** A (no retrieval), B (changelog RAG), C (branching agent), D (broader retrieval — only if developer instructs)  
**Constraint:** **Never two conditions simultaneously** — rate budget is shared; run one condition to completion before starting the next.  
**Command pattern:** `python manage.py run_experiment --condition <X> --items labelled_set.jsonl --resume`  
**Analysis command:** `python manage.py analyze_experiment --runs <run_ids>` — **confirm exact flag format with developer before Phase 13 is done** (may be space-separated ids, a comma-separated string, or a single run id per condition depending on implementation)  
**Rate-cap resumption rule:** If the command stops at a daily Groq/Gemini cap, **do NOT attempt to resume the same calendar day**. Wait until midnight UTC and rerun the same command unchanged — checkpointing means no work is lost.  
**Run ID assignment:** Confirm with developer whether run IDs are assigned as CLI flags before the command runs or returned on first invocation. Update the pre-run checklist accordingly.  
**Depends on:** Phase 13 code with pilot passed; research DB up (`docker compose --profile research up -d`)

---

## Pre-run checklist

- [ ] `labelled_set.jsonl` confirmed frozen (developer sign-off received: FILL_IN date)
- [ ] Item count confirmed: 150 (75 npm / 75 PyPI)
- [ ] Research DB is running (`docker compose --profile research up -d`)
- [ ] Condition A run_id to use: FILL_IN (assigned by developer)
- [ ] Condition B run_id to use: FILL_IN
- [ ] Condition C run_id to use: FILL_IN
- [ ] Condition D run_id to use (if instructed): FILL_IN / N/A

---

## Condition A — No retrieval (LLM only)

**Command:** `python manage.py run_experiment --condition A --items labelled_set.jsonl --resume`

| Date | Session start | Session end | Items completed (cumulative) | Failures | Notes |
|---|---|---|---|---|---|
| FILL_IN | FILL_IN | FILL_IN | FILL_IN / 150 | FILL_IN | e.g. rate limit pause at item N |

**Condition A final status:** PENDING  
**Items completed:** FILL_IN / 150  
**Failures (retried):** FILL_IN  
**Run ID:** FILL_IN

---

## Condition B — Single-source RAG (changelog text)

**Command:** `python manage.py run_experiment --condition B --items labelled_set.jsonl --resume`  
**Start only after Condition A reaches 150/150.**

| Date | Session start | Session end | Items completed (cumulative) | Failures | Notes |
|---|---|---|---|---|---|
| FILL_IN | FILL_IN | FILL_IN | FILL_IN / 150 | FILL_IN | |

**Condition B final status:** PENDING  
**Items completed:** FILL_IN / 150  
**Failures (retried):** FILL_IN  
**Run ID:** FILL_IN

---

## Condition C — Full branching agent

**Command:** `python manage.py run_experiment --condition C --items labelled_set.jsonl --resume`  
**Start only after Condition B reaches 150/150.**

| Date | Session start | Session end | Items completed (cumulative) | Failures | Notes |
|---|---|---|---|---|---|
| FILL_IN | FILL_IN | FILL_IN | FILL_IN / 150 | FILL_IN | |

**Condition C final status:** PENDING  
**Items completed:** FILL_IN / 150  
**Failures (retried):** FILL_IN  
**Run ID:** FILL_IN

---

## Condition D — Broader retrieval (if instructed)

**Developer instruction received?** YES / NO  
**Command (if yes):** `python manage.py run_experiment --condition D --items labelled_set.jsonl --resume`  
**Start only after Condition C reaches 150/150.**

| Date | Session start | Session end | Items completed (cumulative) | Failures | Notes |
|---|---|---|---|---|---|
| FILL_IN | FILL_IN | FILL_IN | FILL_IN / 150 | FILL_IN | |

**Condition D final status:** PENDING / N/A  
**Items completed:** FILL_IN / 150  
**Failures (retried):** FILL_IN  
**Run ID:** FILL_IN

---

## Analysis run

**Command:** `python manage.py analyze_experiment --runs <A_run_id> <B_run_id> <C_run_id> [<D_run_id>]`  
**Date run:** FILL_IN  
**Tables rendered correctly?** YES / NO  
**Notes:** FILL_IN

---

## Completion checklist (before handoff)

- [ ] Condition A: 150 / 150 items completed; failures < 5 and retried
- [ ] Condition B: 150 / 150 items completed; failures < 5 and retried
- [ ] Condition C: 150 / 150 items completed; failures < 5 and retried
- [ ] Condition D: 150 / 150 items completed; failures < 5 and retried (or N/A)
- [ ] All condition × ecosystem cells populated in the analysis tables
- [ ] `runs/` folder present and non-empty
- [ ] Analysis tables confirmed rendering

**Important:** Do not interpret results. Whether C beats A is the paper's job. A null result is reported exactly as enthusiastically as a positive one.

---

## Anomalies log

> Record any unexpected behaviour (command crashes not recovered by --resume, suspiciously high failure counts, empty ecosystem cells).

FILL_IN_AFTER_RUNS (if none, write "None")

---

## Handoff

- [ ] `runs/` folder zipped into `WP8_YYYYMMDD.zip`
- [ ] This run log (with all cells filled) included in zip
- [ ] Sent to developer
