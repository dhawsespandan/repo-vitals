# RepoVitals — project context

This branch holds everything about RepoVitals that the running product does not
need: the plans that governed the build, the engineering decision log, the
research (corpus, studies, work packages and their raw data), the submission
material, and the code that never ships (tests, research instruments,
development tooling).

| Branch | Holds | Changes |
|---|---|---|
| [`main`](https://github.com/dhawsespandan/repo-vitals/tree/main) | only what the deployed services run | final, frozen |
| `context` (this one) | everything else | new work lands here; no deployment watches it |

Live app: <https://repo-vitals-lilac.vercel.app>

---

## Layout

```
plan/                  the governing plans (read these first)
engineering/           how the product was built and checked
research/
  REPLICATION.md       how to reproduce S1 and S3
  notebooks/           the two analysis notebooks
  work-packages/       WP-1 … WP-9: deliverables, sign-offs, raw run records
submission/            black book, poster, video, paper
non-production-code/   tests, research instruments, dev tooling (overlay on main)
```

### `plan/`

| File | What it is |
|---|---|
| `repo_vitals_implementation_plan.md` | **File A** — the build: 14 phases, schema, API, scoring spec, locked decisions D1–D17 |
| `repo_vitals_parallel_work_plan.md` | **File B** — the work packages that ran beside the build |
| `repo_vitals_research_plan.md` | **File C** — the two studies, S1 and S3; §2.5 and §3.5 are the paper skeletons, §9 lists what each study still needs |
| `wireframe.html` | the visual reference for the UI (File A wins where the two differ) |

### `engineering/`

| File | What it is |
|---|---|
| `decisions.md` | every design decision, defect and acceptance run, by phase (§1.x … §14.x). Code comments on `main` cite it as `docs/decisions.md §N` |
| `adapter_soundness.md` | the evidence that npm and PyPI go through one pipeline |
| `demo_script.md` | the ten-minute walkthrough of the live app, with fallbacks |
| `prod_smoke_checklist.md` | the post-deploy check of production |
| `development_readme.md` | the README of the full development tree: quickstart, checks, dependency locks, research commands |

### `research/`

`REPLICATION.md` is the replication manual: pins, seeds, weights lineage, the
command behind every table, and the limitations that travel with the data.
`notebooks/13_3_validation.ipynb` regenerates S1's tables and
`notebooks/13_1_analysis.ipynb` S3's, from the export alone.

`work-packages/` holds one folder per work package of File B.
`wp-review/WP_review.md` is their status and `RAW_DATA.md` indexes every
`raw/` folder.

| WP | Deliverable |
|---|---|
| `wp-1` | Tier-1 weights from an informal pairwise pass (weights `v1`) |
| `wp-2` | the anchor set: 49 repositories, each checked against its live manifests |
| `wp-3` | the full AHP judgement behind weights `v2` |
| `wp-4` | corpus construction: 914 repositories sampled on a 240-stratum frame |
| `wp-5` | the corpus scan (29,494 dependency occurrences) and the research database dump |
| `wp-6` | the formula validation report and its sign-off (S1) |
| `wp-8` | S3's experiment: 450 generations over conditions A, B, C, judged |
| `wp-9` | 50 human labels checking S3's automated judge (Cohen's kappa 0.134: not validated) |

WP-7 was retired with the longitudinal study, so there is no `wp-7`.

### `submission/`

The academic deliverables. See [`submission/README.md`](submission/README.md).

### `non-production-code/`

Code that belongs to the project but not to the deployed build: the backend and
frontend test suites, the research commands and harnesses, the dev and research
dependency locks, and the CI workflow. Every file keeps the path it has in the
full tree. See [`non-production-code/README.md`](non-production-code/README.md).

---

## Paths in documents written before the split

The repository was split into `main` and `context` on 2026-10-11. Everything
written before that keeps its original paths in its text, so `docs/decisions.md
§11.29` or `wp/wp-5/wp5_signoff.md` is read through this table. Each file was
moved with `git mv`, so `git log --follow <new path>` shows its whole history.

| Written as | Now on `context` at |
|---|---|
| `plan/…` | `plan/…` (unchanged) |
| `docs/…` | `engineering/…` |
| `README.md` (before the split) | `engineering/development_readme.md` |
| `REPLICATION.md` | `research/REPLICATION.md` |
| `notebooks/…` | `research/notebooks/…` |
| `wp/…` | `research/work-packages/…` |
| `report.docx` | `submission/black-book/black_book_draft_2026-10-06.docx` |
| `backend/tests/…`, research commands, dev configuration, frontend tests, `.github/workflows/ci.yml` | `non-production-code/<same path>` |
| `backend/…`, `frontend/…` (the product) | branch `main`, same path |

## Running the code

The tests, the research commands and the notebooks import the product's own
code, which lives on `main`. The simplest way to run any of them is the full
development tree as it stood at the split, commit **`cb6609b`** — it is in
`main`'s history, and every path in `REPLICATION.md` and the older documents is
valid there:

```bash
git worktree add ../repo-vitals-full cb6609b
```

From there, `engineering/development_readme.md` (that tree's `README.md`) has
the setup and `research/REPLICATION.md` (its `REPLICATION.md`) the studies.

## Byte-exact files

`.gitattributes` stores `research/work-packages/wp-8/**/*.jsonl` and every
`research/work-packages/*/raw/**` file exactly as written, with no line-ending
conversion: `labelled_set.jsonl`'s sha256 names every S3 run, and the raw
records are copies of the research machine's files. Do not re-save them in an
editor that rewrites line endings.

## Licence

MIT — see [LICENSE](LICENSE).
