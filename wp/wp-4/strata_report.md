# WP-4 Strata Report

> **SCAFFOLD** — replace this entire file with the actual output of:
> ```
> python manage.py build_corpus --seed 42 --target 1000 --config corpus_frame.yaml
> ```
> The command writes `strata_report.md` alongside `corpus_manifest.json`.  
> The sections below show the expected structure and the acceptance criteria you must verify.

---

## Run metadata

| Field | Value |
|---|---|
| Seed | 42 |
| Target | 1 000 |
| Timestamp | FILL_IN |
| Config hash | FILL_IN |
| Command | `python manage.py build_corpus --seed 42 --target 1000 --config corpus_frame.yaml` |

---

## Admission summary

| Metric | Value | Acceptance criterion |
|---|---|---|
| Total candidates sampled | FILL_IN | — |
| Total admitted | FILL_IN | **900–1 100** |
| Admission rate | FILL_IN % | **40–60 %** (< 40 % → flag as possible verification bug) |
| Dedup discards | FILL_IN | **> 0** (zero over 1 000+ candidates is suspicious) |
| npm admitted | FILL_IN | — |
| PyPI admitted | FILL_IN | — |
| npm / PyPI split | FILL_IN / FILL_IN | **45 / 55 range each way** |

---

## Stratum grid

Replace the table below with the actual per-cell counts. **No cell may be zero**, especially the stale/very-stale cells — they carry the research weight for S1.

| Stratum | npm count | PyPI count | Acceptance |
|---|---|---|---|
| Active (pushed ≤ 180 days) | FILL_IN | FILL_IN | must be > 0 |
| Moderate (181–730 days) | FILL_IN | FILL_IN | must be > 0 |
| Stale (731–1 095 days) | FILL_IN | FILL_IN | **must be > 0** |
| Very stale (> 1 095 days) | FILL_IN | FILL_IN | **must be > 0** |
| Stars ≥ 5, < 50 | FILL_IN | FILL_IN | must be > 0 |
| Stars ≥ 50, < 500 | FILL_IN | FILL_IN | must be > 0 |
| Stars ≥ 500 | FILL_IN | FILL_IN | must be > 0 |

---

## Sampling weight record

Record the oversampling weights applied to stale cells (required for weighted population estimates in File C §1.3):

| Stratum | Sampling weight |
|---|---|
| Active | FILL_IN |
| Moderate | FILL_IN |
| Stale | FILL_IN |
| Very stale | FILL_IN |

---

## Reproducibility fields (must be present for acceptance)

- [ ] Seed recorded: 42
- [ ] Timestamp recorded: FILL_IN
- [ ] Grid config hash recorded: FILL_IN
- [ ] Dedup method described: FILL_IN
