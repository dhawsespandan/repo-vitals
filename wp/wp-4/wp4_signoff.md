# WP-4 sign-off: corpus build

**Run and outputs**
- **Run:** `build_corpus --seed 42 --target 1000 --config corpus_frame.yaml`
- **Machine:** Spandan's
- **Run date:** 2026-10-07 (UTC)
- **Outputs:**
  - `research_data/corpus/corpus_manifest.json` (byte-identical copy committed here as `corpus_manifest.json`)
  - `research_data/corpus/strata_report.md` (copied here, unedited)
  - the archived manifest blobs under `research_data/corpus/blobs/` (local only; about 9 MB)

**Duration and interruptions:**
- **Wall clock:** 18:42 → 23:15 UTC, about 4.5 h.
  - Enumeration: 1 h 10 min, 1,326 cells.
  - Verification: about 2 h (attempt 2).
- **Attempt 1 was stopped deliberately** 40 minutes into verification. Replaying its allocation showed 104 of the 240 strata would get nothing. The fix is decisions §11.29 (commit `a5ba223`).
- **Attempt 2** resumed from attempt 1's enumeration with the candidate checkpoint cleared. It was interrupted twice (the session ended, then the operator stopped it) and resumed with `--resume` both times. The run date stayed 2026-10-07, from the checkpoint.
- Attempt 1's log and candidates are kept in `research_data/logs/`.

**Checklist, read from the unedited strata report:**

| Check | Value | Result |
|---|---|---|
| Total admitted | 914 (target 1000) | pass (900–1,100) |
| Ecosystem split | npm 486 (53%) / PyPI 428 (47%) | pass (within 45/55) |
| No stratum empty, especially stale | 0 of 240 populated strata have no admitted repository; per stratum min 1, median 4, max 11 | pass |
| Empty / empty stale cells | 0 / 0 | pass |
| Admission rate | 68% (914 of 1,343) | **outside 40–60%: flagged and explained below** |
| Dedup discards | 4 | pass (above 0) |
| Seed, timestamp, grid config present | seed 42, generated 2026-10-07T23:15:00Z, grid in the manifest | pass |

**Admitted by band:**

| Pushed | Count |
|---|---|
| lt6 | 146 |
| 6-18 | 147 |
| 18-48 | 279 |
| gt48 | 342 |

| Created | Count |
|---|---|
| ≤2015 | 230 |
| 2016-18 | 225 |
| 2019-21 | 230 |
| 2022+ | 229 |

| Stars | Count |
|---|---|
| 5-20 | 158 |
| 21-50 | 183 |
| 51-200 | 178 |
| 201-1000 | 201 |
| 1000+ | 194 |

**Flagged: the admission rate.**

The 68% is npm-driven: npm admitted 486 of 586 (83%), PyPI 428 of 757 (57%). `language:JavaScript` and `language:TypeScript` repos almost always ship a `package.json`. Python repos often ship no requirements file: 285 of PyPI's 329 rejections are `no_supported_manifest`.

**It is not a verification bug.**
- All three reachable rejection paths fire:
  - `no_supported_manifest`: 370;
  - `no_declared_dependencies`: 55;
  - `duplicate_dependency_set`: 4.
- 12 candidates were re-checked directly against the GitHub tree, without RepoVitals' code, and all 12 match what the builder recorded:
  - 6 admitted repos each have a manifest;
  - 4 `no_supported_manifest` repos have none;
  - 2 `no_declared_dependencies` repos have only a `setup.py`, which RepoVitals never executes.
- No duplicate repository or repository id; every admitted row carries a sampling weight and passes all five checks.

File B's "~50%" was an a-priori estimate made before any run.

**Also noted (not failures):**
- **307 of 1,326 cells are still over the 1,000-result cap at the deepest split.** Each is sampled from its first 1,000 results by star order. The report's "What this frame cannot say" covers it, and the weights under-count those cells rather than overstate them.
- **82 cells did not fill their allocation.** They ran out of admissible candidates within File B's 2.5× draw, which is why the total is 914, not 1,000.
