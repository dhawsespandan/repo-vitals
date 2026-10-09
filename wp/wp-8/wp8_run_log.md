# WP-8 run log: S3 experiment runs

**Operator:** Spandan.
**Code:** `v0.13.0` (`4000e92`).
**Item set:** the frozen `labelled_set.jsonl`, sha256 `75246f3b…a9eb`, with 150 items:
- npm: 37 `cve_fix` and 38 `deprecation_replacement`;
- PyPI: 75 `cve_fix`.

**Models:**
- Generator: `openai/gpt-oss-120b` on Groq, temperature 0, paced at one generation every 45 s.
- Judge: `gemini-3.5-flash-lite`, the same model throughout.

**Runs:** `A_75246f3b_openai-gpt-oss-120b`, `B_…` and `C_…`, under `runs/` here. Condition D was not run. It is internal, and File B runs it only on instruction.

## Completion

| Condition | Completed | Failed | Judged | Dates |
|---|---|---|---|---|
| A (no retrieval) | 150/150 | 0 | 150 | 2026-10-09 02:15–04:10 IST |
| B (changelog retrieval) | 150/150 | 0 | 150 | 2026-10-09 04:10–06:00 IST |
| C (production agent) | 150/150 | 0 | 150 | 2026-10-09 06:00 IST to 19:49 IST, paused 09:13–19:47 |

**File B checklist:**

| Check | Result |
|---|---|
| Each condition 150/150 | pass |
| Failures under 5 per condition | pass: 0, so there was nothing to retry |
| Every condition × ecosystem cell populated | pass |

PyPI × `deprecation_replacement` is empty by construction: the corpus has no PyPI successor items, as `README.md` and File C L7 note. The tables are in `runs/analysis/tables.md`, with one CSV per table.

## How the generation was divided

Groq's and Gemini's free tiers cap each account per day, and no paid tier was possible. Generation was therefore divided among four team members' own free-tier accounts.
- Only one key was used at a time. Conditions never ran in parallel.
- When a member's daily cap stopped a run, the next member's key continued the same condition with `--resume`.
- The model, prompts, temperature and pacing were identical throughout. Which key served a call changes nothing in the output.

The launcher's ledger is below, by member, with keys never recorded.

| Groq account | Generations | Where |
|---|---|---|
| member1 | 168 | all of A (150); B item 1; C 107→117, 131→132, 135→138, 147→150 |
| member2 | 100 | B 1→89; C 117→124, 132→134, 138→141 |
| member3 | 92 | B 89→150; C 0→19, 124→129, 134→135, 141→147 |
| member4 | 90 | C 19→107, 129→131 |
| **Total** | **450** | |

**Judging.**
- Inline judging used member1's Gemini key for A and C, and member2's for B.
- The rest was judged by `analyze_experiment --judge` passes over each member's Gemini key in turn.
- Verdicts are cached by model, not by key, so every verdict is the same model's.

## Interruptions

1. **02:15–07:33 IST, first session.** A and B completed, and C reached 107. It stopped when all four Groq keys hit their daily cap; the stop was clean, by design.
2. **07:33, 07:58 and 08:58 IST, relaunches.** Groq's free daily quota frees up **gradually**, not all at once at midnight, so each relaunch got a few more items: C reached 131, then 135, then 147.
3. **09:13–19:47 IST, paused.** The laptop was shut down. Every finished item was already on disk. The research database container stopped with the machine and was restarted.
4. **19:47 IST, last relaunch.** It finished C's last 3 items and ran the final judging pass.

There were no duplicates: each run's `items.jsonl` holds exactly 150 distinct items.

## Anomalies (recorded, not interpreted)

- **Inline judging stopped early in B,** on member2's Gemini key, after about 12 items. The cause wasn't separated: it could have been that key's quota or Gemini's 503 "high demand". Generation carried on, as designed, and B was fully judged by the later passes.
- **One B npm item has no precision@k verdict.** Precision is over 70 npm items, where 71 retrieved something. Every faithfulness verdict is present: 150/150 per condition.
- **Empty retrieval:** 4 npm and 3 PyPI items retrieved nothing under B, and the same under C.
- **PyPI retrieval is mostly READMEs** (decisions §13.14 (4)). Retrieval was left unchanged for WP-8, so condition C stays the production agent. It is a threat to validity for S3's PyPI arm and for RQ3.
- **C is mechanically healthy:** 0 errors, and every item was routed through the production agent's branches. 106 items took the `no_reason` branch and 44 the `reason_available` branch, out of 150.
- **The judge cache is held back** from this folder until WP-9's labels are in. It holds per-item verdicts, and the WP-9 labeller must label blind.

No result is interpreted here (File B: "Do not interpret results").
