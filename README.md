# RepoVitals

Dependency-health scoring for GitHub repositories, with remediation grounded in
each package's own documentation.

**Live: <https://repo-vitals-lilac.vercel.app>**

Sign in with GitHub and register a repository. RepoVitals reads every npm and
PyPI manifest in it and scores the repository 0–100 from four signals per
dependency — deprecation, vulnerability severity, CVE count and release
staleness — with a drill-down showing which packages cost points and why. The
score is deterministic: no language model touches it. On request, an agent
writes remediation: a repository-wide triage report, and per-dependency plans
grounded in the package's changelog and README, shown beside the retrieved
text with citations. RepoVitals only reads; it never writes to a repository.

This branch holds exactly what the deployed services run, and it is final: the
deployment runs its latest commit. The project's plans, research, documentation
and tests are on the [`context`](https://github.com/dhawsespandan/repo-vitals/tree/context)
branch.

---

## Deployment

```
Browser
   │
   ▼
Vercel ── frontend/ ── React + TypeScript SPA (static build)
   │        /api/* is rewritten to Render, so the browser only ever talks to
   │        one origin: one session cookie, no CORS
   ▼
Render ── backend/ ── Django + DRF under gunicorn (1 worker, 8 threads)
   │        scans and report generation run in background threads
   ├──────► GitHub REST · npm registry · PyPI · OSV.dev · Groq (LLM)
   ▼
Supabase ── PostgreSQL
```

| Part | Host | Configuration |
|---|---|---|
| Frontend | Vercel (Hobby) | root directory `frontend/`; framework Vite; build `npm run build`; output `dist/`. `frontend/vercel.json` rewrites `/api/*` to `https://repo-vitals.onrender.com/api/*` and every other path to `index.html` |
| Backend | Render (free web service) | root directory `backend/`; build `pip install -r requirements.txt`; pre-deploy `python manage.py migrate`; start `gunicorn config.wsgi -c gunicorn.conf.py` |
| Database | Supabase (free PostgreSQL) | reached through `DATABASE_URL` over TLS (`config/settings/prod.py`) |
| Sign-in | GitHub OAuth App | callback URL `https://repo-vitals-lilac.vercel.app/api/auth/github/callback/` — the frontend's origin, not Render's, because the OAuth round trip has to stay on the origin that holds the session cookie |

`backend/requirements.txt` is a frozen lock of every runtime dependency (one
file for Python 3.11–3.14); `frontend/package-lock.json` is the frontend's.

### Backend environment (Render)

`backend/.env.example` documents each variable.

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` (`wsgi.py` defaults to it; `manage.py`, which runs the pre-deploy migration, does not) |
| `DJANGO_SECRET_KEY` | a long random string |
| `ALLOWED_HOSTS` | the Render service's host name |
| `DATABASE_URL` | the Supabase connection string |
| `TOKEN_ENCRYPTION_KEY` | a Fernet key; encrypts the GitHub tokens stored at rest. Rotating it invalidates them, so users sign in again |
| `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` | the production OAuth App |
| `FRONTEND_URL` | `https://repo-vitals-lilac.vercel.app` (post-login redirect and CSRF trusted origin) |
| `WEIGHTS_VERSION` | `v2` — which file in `backend/weights/` scores every scan |
| `GROQ_API_KEY`, `GROQ_MODEL` | report generation (`openai/gpt-oss-120b`). Without a key, the report endpoints answer "not configured" and everything else works |

`CHROMA_DIR`, `EMBED_MODEL`, `GROUNDING_MIN_SIM`, `GROUNDING_MIN_CHARS`,
`EPSS_ENABLED` and `LOG_LEVEL` have working defaults and are left unset.

### Staying awake on free tiers

| Problem | What handles it |
|---|---|
| Render's free instance sleeps after 15 idle minutes; the next request waits ~50 s | an external pinger (cron-job.org) sends `HEAD /api/health/` every 10 minutes from 06:00 to 24:00 IST — 18 h a day, which fits Render's 750 free instance-hours a month |
| Supabase pauses a free project after about 7 idle days | `.github/workflows/keepalive.yml` calls `/api/health/`, which runs a real `SELECT 1`; GitHub runs it every few hours. It reads the URL from the repository variable `RENDER_HEALTH_URL` |

### Checking and redeploying

<https://repo-vitals-lilac.vercel.app/api/health/> answers
`{"status": "ok", "database": "ok"}` when the frontend, the rewrite, the backend
and the database are all up. Allow about 50 s if the backend was asleep.

To rebuild without a commit: Render dashboard → the service → **Manual Deploy**;
Vercel dashboard → the project → Deployments → **Redeploy**.

---

## What is in this branch

```
backend/
  apps/            accounts · common · repositories · scanning · scoring · reports
                   research (only its permanent tables: scan history, agent traces)
  config/          settings (base, dev, prod), urls, wsgi
  weights/         the scoring weight vectors; WEIGHTS_VERSION picks one
  manage.py  gunicorn.conf.py  requirements.txt  .env.example
frontend/
  src/             the single-page app
  index.html  package.json  package-lock.json  vite.config.ts  vercel.json
  tsconfig.json  tailwind.config.js  postcss.config.js
.github/workflows/keepalive.yml
```

Comments in the code cite design decisions as `docs/decisions.md §N`; that
log is on the `context` branch at `engineering/decisions.md`.

## Licence

MIT — see [LICENSE](LICENSE).
