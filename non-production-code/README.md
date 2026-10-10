# Non-production code

Code that belongs to RepoVitals but is not part of the deployed build. `main`
carries only what Render and Vercel run; everything below was in the same
repository until the split and is kept here at **the path it had in the full
tree**, so this folder is an overlay on `main`.

| Path | What it is |
|---|---|
| `backend/tests/` | the backend suite (pytest), including the BOLA suite (every resource endpoint, requested by a foreign user, must 404) and the determinism suite |
| `backend/apps/research/corpus.py`, `corpus_scan.py`, `github.py`, `charts.py` | the corpus builder and scanner (Phase 11) |
| `backend/apps/research/validation/` | S1's validation harness: AHP, entropy, anchors, sensitivity, agreement (Phase 12) |
| `backend/apps/research/experiment/`, `issue_search.py` | S3's experiment harness: conditions, runner, judge, metrics, judge validation (Phase 13) |
| `backend/apps/research/export.py`, `replication.py`, `guards.py` | the replication export (Phase 14) and the guard that keeps research commands off operational tables |
| `backend/apps/research/management/commands/` | the twelve research commands: `build_corpus`, `scan_corpus`, `corpus_report`, `validate_formula`, `scan_anchors`, `ahp_check`, `extract_ground_truth`, `run_experiment`, `analyze_experiment`, `judge_validation_packet`, `judge_validation_kappa`, `export_research_data` |
| `backend/config/settings/test.py`, `offline.py` | settings for the test suite, and for the notebooks (no database) |
| `backend/corpus_frame.yaml`, `corpus_frame_pilot.yaml` | the corpus sampling frame and its small pilot |
| `backend/requirements*.in`, `requirements-dev.txt`, `requirements-research.txt`, `requirements-notebooks.txt` | where each dependency is declared and why, and the dev / research / notebook locks (`main` keeps the runtime lock `requirements.txt`) |
| `backend/pyproject.toml`, `backend/pytest.ini` | ruff and pytest configuration |
| `backend/docker-compose.yml` | the local development Postgres and the separate research Postgres |
| `backend/.env.example` | the full environment template, research-only variables included (`main` carries the production subset) |
| `frontend/src/**/*.test.ts(x)`, `frontend/src/test/` | the frontend suite (Vitest and Testing Library) |
| `.github/workflows/ci.yml` | the CI workflow: ruff, migrations check and pytest on Postgres 16; tsc, Vitest and the production build. Inert here: GitHub runs workflows only from the repository root |

## Running it

The full development tree at the split is commit `cb6609b`, and it is the
easiest way to run anything here:

```bash
git worktree add ../repo-vitals-full cb6609b
```

Alternatively, copy this folder over a checkout of `main`:

```bash
cp -r non-production-code/. ../repo-vitals-main/
```

That restores the code exactly (including `backend/.env.example`'s full form),
but the research data is not at the paths the commands expect: it is under
`research/work-packages/` on this branch and was under `wp/` in the full tree.
For the studies, use `cb6609b`.
