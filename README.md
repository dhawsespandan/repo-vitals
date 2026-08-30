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

**Phase 1 of 14 — foundations.** GitHub sign-in, session lifecycle, an empty
dashboard, CI, and deploys, all live. Registration lands in Phase 2, scanning
in Phase 3, scores in Phase 4.

The build is planned end to end in [`plan/`](plan/):

| File | What it governs |
|---|---|
| `repo_vitals_implementation_plan.md` | **the only guide for this codebase** — 14 phases, schema, API surface, scoring specs |
| `repo_vitals_parallel_work_plan.md` | non-code work running alongside (weight elicitation, corpus, cohort) |
| `repo_vitals_research_plan.md` | the three studies, which begin only after the other two complete |
| `wireframe.html` | the binding visual specification |

Design decisions made during the build are logged in
[`docs/decisions.md`](docs/decisions.md).

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

Prerequisites: Python 3.12+, Node 20+, Docker.

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

### 3. Backend

```bash
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` and fill in the four blanks. Generate the two
keys with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then migrate and run:

```bash
cd backend && python manage.py migrate && python manage.py runserver
```

### 4. Frontend

```bash
cd frontend && npm install && npm run dev
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

CI runs both on every push. Two suites grow with every phase: a **BOLA suite**
(every resource endpoint, requested by a foreign user, must 404) and a
**determinism suite** (identical inputs, identical score).

### Memory smoke test

The 512 MB production tier has to hold Django, a connection pool, background
scan threads and — from Phase 8 — an embedding model. That question is
answered in week one rather than week twenty:

```bash
cd backend && python manage.py smoke_memory
```

Record the production figure in `docs/decisions.md` §1.13.

---

## Deployment

| | Service | Notes |
|---|---|---|
| Frontend | Vercel Hobby, root `frontend/` | `vercel.json` rewrites `/api/(.*)` to the Render service — update the host after the first deploy |
| Backend | Render free web service, root `backend/` | build `pip install -r requirements.txt`; pre-deploy `python manage.py migrate`; start `gunicorn config.wsgi -c gunicorn.conf.py` |
| Database | Supabase free | 500 MB; product and cohort data only |
| Keepalive | `.github/workflows/keepalive.yml` | asks for every 10 min, actually runs every 2–11 h; set the `RENDER_HEALTH_URL` repository variable |

The keepalive cron is load-bearing, not hygiene: Render free services sleep
after ~15 minutes (≈50 s cold start) and Supabase pauses free projects after
about 7 idle days. `/api/health/` performs a real query, so each ping counts
as both web-service traffic and database activity.

**It only actually solves the Supabase half.** GitHub throttles scheduled
workflows heavily — the measured gap here is 2–11 hours, not 10 minutes,
which is comfortably inside Supabase's ~7-day window but far outside
Render's 15-minute sleep timer. To keep the backend genuinely warm (worth it
before a demo), point a free external pinger such as UptimeRobot or
cron-job.org at the same `/api/health/` URL. See `docs/decisions.md` §1.17.

---

## Repository layout

```
backend/     Django + DRF — config/, apps/{common,accounts,...}, weights/, tests/
frontend/    Vite + React + TS — api/, auth/, pages/, components/, styles/
docs/        decision log, and the artifacts later phases produce
plan/        the governing plan documents and the wireframe
notebooks/   analysis notebooks (Phase 14)
research_data/  git-ignored except manifests
```

## Licence

MIT — see [LICENSE](LICENSE).
