# WP-4 Sign-off Note

**Deliverable:** `corpus_manifest.json` + `strata_report.md`  
**Command run:** `python manage.py build_corpus --seed 42 --target 1000 --config corpus_frame.yaml`  
**Date run:** FILL_IN_AFTER_RUN  
**Run duration (wall clock):** FILL_IN_AFTER_RUN (~1 h expected)

---

## Checklist outcomes

> Fill in each item after the command completes and you have reviewed the outputs.

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | Total admitted in range 900–1 100 | PASS / FAIL | Actual count: FILL_IN |
| 2 | npm / PyPI ecosystem split within 45 / 55 range | PASS / FAIL | Actual split: FILL_IN / FILL_IN |
| 3 | No stratum cell is zero (especially stale and very-stale cells) | PASS / FAIL | Any zero cells: FILL_IN |
| 4 | Admission rate 40–60 % | PASS / FAIL | Actual rate: FILL_IN % |
| 5 | Dedup discard count > 0 | PASS / FAIL | Discard count: FILL_IN |
| 6 | Seed, timestamp, grid config hash present in report | PASS / FAIL | — |

**Overall sign-off:** PENDING (complete after run)

---

## Flags / anomalies

> List any items that were flagged (outside acceptance ranges). If none, write "None."

FILL_IN_AFTER_RUN

---

## Handoff note to developer

> Once signed off, zip as WP4_YYYYMMDD.zip containing corpus_manifest.json, strata_report.md, and this file.

- [ ] Zipped as `WP4_YYYYMMDD.zip`
- [ ] Sent to developer
- [ ] Developer confirmed receipt and loaded into `research_data/corpus/`
