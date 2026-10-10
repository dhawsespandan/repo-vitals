# Repo Vitals

Deterministic dependency-health scoring for the repositories you actually own,
with grounded remediation you can check.

Sign in with GitHub, register a repository, and Repo Vitals scores its
dependencies 0–100 (Node.js/npm and Python/PyPI) from four signals —
deprecation, vulnerability severity, CVE count, release staleness — with a
drill-down showing exactly which packages are risky and why. **No LLM touches
the number.** On demand, an agent then writes remediation: a repo-wide triage
summary, and per-dependency plans grounded in the package's own changelog and
README via RAG, shown beside the retrieved source text with citations.

Repo Vitals never writes to your code. It has no PR-creation path and no
auto-fix; the export is a handoff, not a commit.

---

## Status

**v1.0.0 — complete.** All fourteen phases of the implementation plan are
built, deployed and accepted:

- **The product** (Phases 1–10): GitHub sign-in; registration with four
  pre-scan checks; background scans of every npm and PyPI manifest in the
  tree; the 0–100 score with a per-signal drill-down; a repo-wide triage
  report and per-dependency remediation grounded in the package's own
  changelog and README, shown beside the retrieved text with citations;
  rescan guards, Markdown/JSON downloads, projects and score trends.
- **The research instruments** (Phases 11–13): a 914-repository corpus sampled
  on a documented frame and scored by the product's own code; the S1
  validation harness, which produced the signed `v2` weights; and the S3
  experiment harness, whose 450 generations are run and analysed.
- **The replication package** (Phase 14): `export_research_data`, two
  notebooks that regenerate both studies' signed tables from the export
  alone, frozen dependencies, and [`REPLICATION.md`](REPLICATION.md).

What remains is the papers (`plan/repo_vitals_research_plan.md`), and one
methodology decision before S3's faithfulness results can be used: the
automated judge is not validated (Cohen's kappa 0.134 against human labels;
`docs/decisions.md` §13.17).

| Document | What it is for |
|---|---|
| [`REPLICATION.md`](REPLICATION.md) | reproducing the studies: pins, seeds, weights lineage, every table's regeneration command, limitations |
| [`docs/demo_script.md`](docs/demo_script.md) | the ten-minute walkthrough, with fallbacks |
| [`docs/prod_smoke_checklist.md`](docs/prod_smoke_checklist.md) | what to check after every deploy |
| [`docs/decisions.md`](docs/decisions.md) | every design decision made during the build, by phase |
| [`docs/adapter_soundness.md`](docs/adapter_soundness.md) | the evidence that npm and PyPI go through one pipeline |
| [`plan/`](plan/) | the governing plans: implementation (File A), work packages (File B), research (File C), and the wireframe |
| [`wp/`](wp/) | the signed work-package deliverables, with `wp/wp-review/WP_review.md` as their status |

---

## Architecture

```
React/Vite SPA (Vercel)
        │   every call is /api/* — rewritten to Render, so the browser is
        │   always same-origin: one session cookie, no CORS, no JWTs
        ▼
Django + DRF (Render, one gthread worker)
        │   scanner · scoring · agent orchestration
        │   background work = in-process threads, no Celery/Redis
        ├────────────► fastembed + embedded Chroma + Groq
        ▼
PostgreSQL (Supabase in prod; Docker locally; a separate research DB)
        ▲
        └──── GitHub REST · npm registry · PyPI JSON · OSV.dev · deps.dev
```

Everything runs on free tiers, which is a design constraint rather than a
compromise: it is why embeddings use fastembed's ONNX runtime instead of
torch, why there is exactly one always-on service, and why long work happens in
background threads behind a polling endpoint instead of an inline request.

GitHub owns identity; Repo Vitals owns the session. The OAuth access token is
Fernet-encrypted at rest, decrypted only transiently in-process, and never
reaches the browser.

---

## Quickstart

From a fresh clone to a running development environment in under thirty
minutes, most of it package installation.

**Prerequisites:** Python 3.12 or later (3.11 for byte-exact research
output — see `REPLICATION.md` §5), Node 20 or later, Docker, Git.

### 1. Database

```bash
cd backend && docker compose up -d db
```

### 2. GitHub OAuth app

Create a **development** OAuth app at
<https://github.com/settings/developers>:

- Homepage URL: `http://localhost:5173`
- Authorization callback URL: `http://localhost:5173/api/auth/github/callback/`

The callback URL points at the **frontend's** origin, not the backend's —
`/api/*` is proxied there (Vite locally, the Vercel rewrite in prod), and the
whole OAuth round trip has to stay on one browser-visible origin for the
session holding OAuth state to survive GitHub's redirect back.

Keep a separate app for production — never share one between environments.
(Skip this step if you only want to run the checks: the suite needs no
credentials.)

### 3. Backend

```bash
cd backend
python -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` is a frozen lockfile (see *Dependencies* below), so you
get exactly the versions CI tests.

Copy `.env.example` to `.env` and fill in the four blanks: the two OAuth
values from step 2, and two keys generated with

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"                         # DJANGO_SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # TOKEN_ENCRYPTION_KEY
```

`GROQ_API_KEY` is optional: without it everything works except generating
reports, which answer "not configured".

Then migrate and run:

```bash
python manage.py migrate && python manage.py runserver
```

### 4. Frontend

```bash
cd frontend && npm ci && npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to
`localhost:8000`, so the browser sees one origin exactly as it does in
production.

---

## Checks

```bash
cd backend && ruff check . && ruff format --check . && pytest
```

```bash
cd frontend && npm run typecheck && npm test && npm run build
```

The backend suite needs the `db` container from step 1 and no credentials or
network: every external service is replaced at its edge. CI runs both on every
push. Two suites grew with every phase: a **BOLA suite** (every resource
endpoint, requested by a foreign user, must 404) and a **determinism suite**
(identical inputs, identical score). The backend suite also executes both
analysis notebooks end to end against an export built by the real commands.

### Memory smoke test

The 512 MB production tier has to hold Django, a connection pool, background
scan threads and — from Phase 8 — an embedding model. That question is
answered in week one rather than week twenty:

```bash
cd backend && python manage.py smoke_memory
```

Record the production figure in `docs/decisions.md` §1.13.

---

## Dependencies

Python dependencies are declared, with the reason for each, in
`backend/requirements*.in`, and **installed from the compiled lockfiles**
`backend/requirements*.txt` — `requirements.txt` is the runtime set Render
installs, `requirements-dev.txt` adds the research, notebook and test tools.
The locks are universal (one file for Python 3.11–3.14) and pin one version of
everything across all four. To change a dependency, edit the `.in` file and
recompile with the four `uv pip compile` commands in `requirements.in`'s
header; `tests/test_requirement_locks.py` fails if a pin falls outside its
declared range or the locks disagree. The frontend's lock is
`frontend/package-lock.json`; install with `npm ci`.

---

## Research

The research commands run against a separate research database (D8), never
the product's, and never write an operational table (D10). In the order the
studies used them:

| Command | Produces |
|---|---|
| `build_corpus`, `scan_corpus`, `corpus_report` | the sampled corpus, its scan, its descriptive figures (Phase 11) |
| `validate_formula`, `scan_anchors`, `ahp_check`, `rescore` | S1's validation report and the `v2` weights (Phase 12) |
| `extract_ground_truth`, `run_experiment`, `analyze_experiment`, `judge_validation_packet`, `judge_validation_kappa` | S3's labelled set, runs, tables and judge validation (Phase 13) |
| `export_research_data` | the replication export File C reads (Phase 14) |

To regenerate the studies' results from what is committed — restore WP-5's
database dump, export, run `notebooks/13_3_validation.ipynb` (S1) and
`notebooks/13_1_analysis.ipynb` (S3) — follow
[`REPLICATION.md`](REPLICATION.md) §3. It needs Docker and no API key.

---

## Deployment

| | Service | Notes |
|---|---|---|
| Frontend | Vercel Hobby, root `frontend/` | `vercel.json` rewrites `/api/(.*)` to the Render service — update the host after the first deploy |
| Backend | Render free web service, root `backend/` | build `pip install -r requirements.txt` (the frozen lock); pre-deploy `python manage.py migrate`; start `gunicorn config.wsgi -c gunicorn.conf.py` |
| Database | Supabase free | 500 MB; product data only — corpus data lives in a separate local research database |
| Keepalive | `.github/workflows/keepalive.yml` | asks for every 10 min, actually runs every 2–11 h; **set the `RENDER_HEALTH_URL` repository variable** or every run fails |

The keepalive cron is load-bearing, not hygiene: Render free services sleep
after ~15 minutes (≈50 s cold start) and Supabase pauses free projects after
about 7 idle days. `/api/health/` performs a real query, so each ping counts
as both web-service traffic and database activity.

**It only actually solves the Supabase half.** GitHub throttles scheduled
workflows heavily — the measured gap between successful runs is 2–11 hours
(mean ~5.75 h), not 10 minutes. That is comfortably inside Supabase's ~7-day
window but far outside Render's 15-minute sleep timer. To keep the backend
genuinely warm (worth it before a demo), point a free external pinger such
as UptimeRobot or cron-job.org at the same `/api/health/` URL. See
`docs/decisions.md` §1.17.

If the Actions tab looks mostly red, check the dates: every keepalive run
before 2026-08-27 failed because `RENDER_HEALTH_URL` had not been set yet.
All runs since are green.

---

## Repository layout

```
backend/        Django + DRF — config/, apps/{common,accounts,...,research}, weights/, tests/
frontend/       Vite + React + TS — api/, auth/, pages/, components/, styles/
docs/           decision log, demo script, smoke checklist, adapter soundness
plan/           the governing plan documents and the wireframe
notebooks/      13_3_validation (S1) and 13_1_analysis (S3), run against the export
wp/             the signed work-package deliverables
research_data/  git-ignored: the research machine's working files and the export
REPLICATION.md  how to reproduce the studies
```

## Licence

MIT — see [LICENSE](LICENSE).
