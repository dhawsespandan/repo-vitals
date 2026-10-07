# WP-5 Sign-off Note

**Deliverable:** corpus scan completion report + `wp5_research_db.dump` + this sign-off  
**Command run:** `python manage.py scan_corpus --corpus research_data/corpus/corpus_manifest.json --resume`  
**DB dump command:** `docker exec repovitals-research-db pg_dump -U postgres -Fc repovitals_research > wp5_research_db.dump`  
**Depends on:** WP-4 complete and `corpus_manifest.json` in place  
**Date run (start):** FILL_IN_AFTER_RUN  
**Date run (end / completion):** FILL_IN_AFTER_RUN (~2–3 h wall clock expected; crashes safe — rerun same command)

---

## Checklist outcomes

> Fill in each item after the command completes and you have reviewed the completion report.  
> Ask the developer for the `corpus_report` charts before signing.

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | ≥ 95 % of corpus repos completed successfully | PASS / FAIL | Completed: FILL_IN / FILL_IN total |
| 2 | Number of failures ≤ 5 % of total (deleted / renamed repos normal; > 50 failures is not) | PASS / FAIL | Failures: FILL_IN |
| 3 | Scored-occurrence count within the report's own expected range | PASS / FAIL | Actual: FILL_IN; expected: FILL_IN |
| 4 | Score distribution spreads across the full range (not bunched in one class) — eyeball chart | PASS / FAIL | Notes: FILL_IN |
| 5 | Unassessable-occurrence rate reported and not dominant | PASS / FAIL | Unassessable rate: FILL_IN % |
| 6 | DB dump file produced and non-zero size | PASS / FAIL | Dump size: FILL_IN MB |

**Overall sign-off:** PENDING (complete after run)

---

## Interruptions / resume log

> Record each time the command was interrupted and restarted (normal behaviour near GitHub hourly limit).

| Date | Interrupted at | Resumed at | Reason |
|---|---|---|---|
| FILL_IN | FILL_IN repos completed | FILL_IN | rate limit / sleep / manual stop |

---

## Flags / anomalies

> List any items outside expected ranges. If none, write "None."

FILL_IN_AFTER_RUN

---

## Handoff note to developer

> Once signed off, zip as WP5_YYYYMMDD.zip containing this file and the completion report (not the dump — send dump separately due to size).

- [ ] Completion report saved
- [ ] `wp5_research_db.dump` produced and verified non-zero
- [ ] Dump sent to developer via agreed channel (not email; too large)
- [ ] Developer confirmed receipt and restored to local dev research DB
- [ ] Zipped note + report as `WP5_YYYYMMDD.zip` and sent
