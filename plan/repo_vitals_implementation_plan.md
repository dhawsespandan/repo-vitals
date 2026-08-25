# RepoVitals — Technical Implementation Plan (File A)

**Status of this document.** Files A, B, and C together supersede and replace every earlier project document (the v5 proposal, the schema/normalization notes, the risk-engine spec, the formula-generation methodology docs). Those files are discarded; nothing in them is needed again. Where memory of them conflicts with these three files, these files win. File A is the only guide for the codebase; File B (`repo_vitals_parallel_work_plan.md`) is the teammate's non-code work; File C (`repo_vitals_research_plan.md`) begins only after A and B complete.

**What RepoVitals is (standalone context).** A web application where a developer logs in with GitHub, registers repositories they own or can write to, and gets a deterministic 0–100 dependency-health score per repository (Node.js/npm and Python/PyPI), with a drill-down explaining exactly which dependencies are risky and why. On demand, an LLM agent produces remediation reports: a repo-wide triage summary (no retrieval) and per-dependency plans grounded in the package's own changelog/README via RAG, shown beside the retrieved source text with citations. The system additionally carries research instrumentation — permanent history tables, full agent traces, a corpus builder, a historical backfill engine, and experiment harnesses — so that three studies (S1 scoring validation, S2 stochastic risk modelling, S3 grounding quality across ecosystems; defined in File C) need **zero further engineering** once this plan completes.

**Executed by:** the developer (solo). Nothing here depends on any other person except the explicit File B gates (§7).

---

## 0. How to use this document

Work phases 1–14 in order. Each phase is a vertical slice ending in something deployed and demoable to a mentor, a git tag, and acceptance criteria. Do not start phase N+1 before phase N's acceptance passes (exception: §9 notes Phase 11's flexibility). Suggested commit sequences are guides — split further if useful, but every commit stays green (lint + tests).

Phases 1–10 build the product. Phases 11–13 build research infrastructure. Phase 14 packages replication. After Phase 14, the only remaining work in the whole project is File B's outstanding runs and File C.

---

## 1. Locked decisions (do not relitigate mid-build)

| # | Decision | Reason |
|---|----------|--------|
| D1 | Ecosystems: **npm + PyPI**, both fully live against one shared pipeline | S3's research axis is npm-vs-PyPI; the adapter-soundness claim requires two structurally different ecosystems |
| D2 | PyPI **does** carry a deprecation signal: per-release `yanked`/`yanked_reason` (PEP 592) + trove classifier `Development Status :: 7 - Inactive`. The npm/PyPI asymmetry is **information content** (npm deprecation text often names a successor; PyPI's is terse/empty), not signal absence | Verified against the PyPI JSON API; this framing is S3's independent variable |
| D3 | Tier-1 formula = 4 signals (deprecation, CVSS severity, CVE count, staleness). `versions_behind_*` is collected/stored as a research covariate + UI display but is **not** a formula term. EPSS is a 5th signal collected behind a feature flag, excluded from the formula unless a weights file enables it | Keeps the AHP matrix at 4×4; EPSS stays available for Tier-2 variants |
| D4 | Scoring is two-level: per-occurrence score (§5.2) + repository roll-up via **rank-decayed penalty aggregation** (§5.3). No plain mean anywhere | A mean lets 500 clean deps mask 3 critical ones; worst-only ignores breadth |
| D5 | Weights live in versioned YAML (`weights/`). `v1` = informal pairwise pass (WP-1). `v2` = AHP + entropy validated (WP-3…WP-6). Swapping versions requires zero code change. Every stored score row is tagged `scoring_formula_version` | Unblocks the build; keeps score provenance auditable |
| D6 | **Signals are persisted raw; scoring is a pure function over stored signals.** Stored history scores are used only for product display; research analysis always **recomputes** scores from stored signals under an explicitly chosen weights version. History rows are never mutated by re-scoring — re-scored panels are materialized to files | Makes weight revisions free, retroactive, and non-destructive |
| D7 | Embeddings via **fastembed** (ONNX, `all-MiniLM-L6-v2`); never sentence-transformers/torch | Torch alone (~700 MB installed) exceeds Render's 512 MB tier; fastembed ≈ 50 MB, same model |
| D8 | **Three database contexts.** Dev = local Docker Postgres. Prod = Supabase free (product data + cohort live scans only). **Research = a separate local Docker Postgres on the teammate's machine** holding corpus + backfill data. Backfill volume (~1,000 repos × 60 months × ~40 occurrences ≈ 2–4 M `dependency_history` rows) would blow Supabase's 500 MB and hammer prod — it never touches Supabase | Found on verification pass; without this the research data has nowhere legal to live |
| D9 | Research tables (`scan_history`, `dependency_history`, `agent_execution_traces`) never cascade on any trigger (not rescan, not repo/user deletion); identifying fields denormalized; rows tagged `data_source ∈ {live_scan, backfill}`. Privacy requests handled by manual anonymization pass, never cascade logic | They exist for retrospective research; joins back to live rows must never be assumed |
| D10 | Backfill and corpus commands write **only** research tables in the **research DB**, never operational tables, never prod | Keeps product state clean and prod small |
| D11 | Generator LLM = Groq (`GROQ_MODEL`, default `llama-3.3-70b-versatile`), temperature 0, JSON mode. Judge LLM = **different provider** (Gemini free tier, `JUDGE_MODEL`) | Determinism for a trust tool; self-judging is a known reviewer attack |
| D12 | S1 validation reference: **deps.dev OpenSSF Scorecard score** as the independent reference; OSV severity rollup computed alongside as the conventional-but-circular reference with the circularity stated (OSV feeds 2 of 4 formula signals) | Honest convergent validity instead of validating against our own inputs |
| D13 | Internal issue/discussion-search utility: **management command only.** No URL route, no serializer, no UI, never imported by request-handling code. Public issue text is open to any account with no review gate — higher prompt-injection exposure than changelogs (which require a merged PR to alter) — so it must be unreachable from any user-triggered path until a threat-model extension explicitly promotes it | Enables S3's condition D without touching the live threat model |
| D14 | Corpus ≈ 1,000 repos (≈500/500 npm/PyPI), stratified partitioned GitHub search, seeded, dedup-verified, stale cells deliberately oversampled with recorded sampling weights. Backfill: monthly snapshots × 60 months | Transition events are rare; statistical power for S2/S3 comes from scale + stratification |
| D15 | S3 labelled set: 150 items (75/75 npm/PyPI), ground truth auto-extracted (no manual labelling), stratified by case type `cve_fix` vs `deprecation_replacement`. The automated faithfulness judge is validated against a 50-item human-labelled subset (WP-9) | The case-type stratification controls the confound that npm and PyPI contribute different case mixes |
| D16 | Everything runs on free tiers; §8 is the constraint register. A change that violates §8 is wrong by definition | Hard project constraint |
| D17 | The scan pipeline records everything the research needs **at scan time** (raw signals, publish dates, CVE publication dates, deprecation text verbatim) so no study ever requires retrofitting instrumentation | Cheap now, impossible later |

---

## 2. Architecture

Five layers: React/Vite client (Vercel) → Django + DRF application layer (Render; scanner, scoring, agent orchestration, in-process background threads — no Celery/Redis) → AI/retrieval layer (fastembed + embedded Chroma + Groq) → PostgreSQL (per D8) → external free services (GitHub REST, npm registry, PyPI JSON API, OSV.dev, deps.dev, NVD optional, FIRST.org EPSS optional, Gemini judge).

One Gunicorn worker (`gthread`) hosts everything including the embedding model — a single copy in memory. Background work = fire-and-forget threads with explicit DB-connection hygiene. The frontend reaches the backend exclusively through a Vercel rewrite (`/api/* → Render`), making all API calls same-site in the browser so one session cookie (`HttpOnly; Secure; SameSite=Lax`) works with no CORS/CSRF special-casing and no JWT machinery.

Authentication is two separate systems: GitHub owns identity (OAuth code exchange; the resulting token is stored encrypted, decrypted only transiently in-process for API calls, and never reaches the browser); RepoVitals owns its own session via Django server-side sessions. The OAuth token has `repo` scope because GitHub OAuth Apps offer no read-only private scope — the enforced mitigation is that backend code **never issues a write call** (grep-audited in Phase 9). A GitHub-App migration for true read-only scope is explicitly out of scope (§12).

---

## 3. Monorepo layout

One GitHub repository: `repo-vitals`.

```
repo-vitals/
├── README.md · LICENSE · .gitignore
├── .github/workflows/
│   ├── ci.yml                  # ruff+pytest / tsc+vitest+build on push
│   └── keepalive.yml           # cron */10min: GET /api/health/  (Render awake + Supabase active)
├── docs/
│   ├── adapter_soundness.md    # Phase 6 evidence artifact
│   ├── demo_script.md          # Phase 14
│   └── decisions.md            # running ADR log (seeded with §1)
├── backend/
│   ├── manage.py · requirements.txt · requirements-dev.txt · pytest.ini
│   ├── gunicorn.conf.py        # workers=1, worker_class="gthread", threads=8, timeout=300
│   ├── .env.example
│   ├── docker-compose.yml      # dev postgres:16  +  research postgres:16 (profile: research)
│   ├── config/  settings/{base,dev,prod}.py · urls.py · wsgi.py
│   ├── weights/ weights_v0_equal.yaml · weights_v1.yaml · weights_v2.yaml
│   └── apps/
│       ├── common/             # authz mixin, allowlisted HTTP client, errors, logging
│       ├── accounts/           # user model, OAuth, token crypto, session views
│       ├── repositories/       # registration, pre-scan validation, projects
│       ├── scanning/
│       │   ├── adapters/       # base.py, npm.py, pypi.py, registry_clients.py
│       │   ├── osv.py · scanner.py · background.py · retention.py
│       ├── scoring/
│       │   ├── signals.py · normalize.py · engine.py · weights.py
│       │   └── management/commands/rescore.py
│       ├── reports/
│       │   ├── llm/            # groq client (temp 0, json mode) + prompts/
│       │   ├── rag/            # fetch_docs, chunker, embeddings, chroma_store, retriever
│       │   ├── agent/          # LangGraph graph + nodes (PER_DEPENDENCY)
│       │   ├── services.py · views.py
│       └── research/           # never imported by request-handling code (except the history endpoint helper)
│           ├── corpus.py · backfill.py · issue_search.py
│           ├── validation/     # ahp.py entropy.py reference.py agree.py sensitivity.py anchors.py report.py
│           ├── experiment/     # groundtruth.py conditions.py runner.py judge.py metrics.py judge_validation.py
│           └── management/commands/
│               build_corpus.py backfill.py backfill_validate.py validate_formula.py
│               extract_ground_truth.py run_experiment.py analyze_experiment.py
│               judge_validation_packet.py judge_validation_kappa.py
│               cleanup_chroma.py export_research_data.py smoke_memory.py scan_anchors.py
├── frontend/
│   ├── package.json · vite.config.ts · tailwind.config.js · tsconfig.json · index.html
│   ├── vercel.json             # rewrites /api/(.*) → <RENDER_URL>/api/$1
│   └── src/
│       ├── api/client.ts       # same-origin /api, credentials:"include", typed {code,message} errors
│       ├── auth/               # AuthContext, ProtectedRoute, LogoutConfirm, backNavGuard
│       ├── hooks/usePolling.ts
│       ├── pages/              # Login, Dashboard, RepoDetail, ProjectsPage
│       ├── components/         # RepoCard ScoreBadge AddRepoForm DependencyTable WhyFlaggedPanel
│       │                       # ReportPanel CitationPane TrendChart ConfirmDialog EcosystemChip StatusPill
│       └── types/
├── notebooks/                  # Phase 14: 13_1_analysis · 13_2_markov_hazard · 13_3_validation
└── research_data/              # git-ignored except .gitkeep and small manifests
    ├── corpus/ · runs/ · validation_report/ · exports/ · deliverables/
```

---

## 4. Environments, deployment, conventions

### 4.1 Environments

| | Dev (developer machine) | Prod | Research (teammate machine) |
|---|---|---|---|
| Backend | `runserver` | Render free Web Service, root `backend/` | repo checkout, commands only |
| Frontend | Vite dev server (proxy `/api`→localhost:8000) | Vercel Hobby, root `frontend/` | — |
| DB | Docker `postgres:16` | Supabase free (500 MB) | Docker `postgres:16` (compose profile `research`) |
| Chroma | `backend/.chroma/` | Render ephemeral disk (fine: per-scan collections rebuild on demand) | local dir (experiment runs) |
| OAuth app | dev app (localhost callback) | prod app (Render callback) | — |
| Data | disposable | product + cohort live scans | corpus + backfill (D8) |

The developer also loads the WP-5 research-DB dump locally when building Phases 12–13 (§7), so dev work on harnesses runs against real corpus data without touching the teammate's machine.

### 4.2 Deployment mechanics (Phase 1, then automatic)

Render: build `pip install -r requirements.txt`; pre-deploy `python manage.py migrate`; start `gunicorn config.wsgi -c gunicorn.conf.py`; auto-deploy on push to `main`. Vercel: auto-deploys `frontend/`. Keepalive cron every 10 min keeps Render awake (cold start ≈ 50 s otherwise) and counts as Supabase activity (free projects pause after ~7 idle days). Render free = 750 instance-hours/month ⇒ exactly **one** always-on service; never add a second.

### 4.3 Git conventions

Solo → commit to `main`, every commit green. Conventional commits `feat|fix|chore|test|docs|refactor(scope): message`. One tag per phase `v0.1.0…v0.14.0`, then `v1.0.0`, only after acceptance passes. Migration policy: never edit an applied migration; research tables are additive-only forever.

### 4.4 Testing strategy

Backend: pytest + factory_boy; all external HTTP mocked via `responses` with a `tests/fixtures/` library of recorded real payloads (GitHub tree/contents/readme, npm doc, PyPI doc, OSV batch + vuln details, deps.dev). LLM calls mocked with a fake client returning canned JSON. Golden-repo fixtures: tiny npm repo, PyPI repo, mixed monorepo, one with unassessable specifiers. Two standing suites grow every phase: **BOLA suite** (every resource endpoint × foreign user → 404) and **determinism suite** (same inputs → identical score/output). Frontend: vitest + RTL for auth guard, polling, confirm dialogs — light; the backend carries correctness. CI runs everything on every push.

### 4.5 Definition of done (every phase)

1. Acceptance criteria pass **on prod**, not just dev. 2. CI green; new logic tested; BOLA/determinism suites extended if surface grew. 3. `.env.example` + §6 updated if config changed. 4. `docs/decisions.md` appended if a §1 decision was refined. 5. Tag pushed; mentor demo executable from the phase's script.

---

## 5. Core specifications

### 5.1 Data model — complete schema (12 tables)

Conventions: PK = UUID `gen_random_uuid()` unless noted; `created_at TIMESTAMPTZ DEFAULT now()`; FK cascade rules explicit; Django models with `db_table` set to these names.

**`app_users`** — identity is GitHub's; no passwords.

| Column | Type | Notes |
|---|---|---|
| user_id | UUID PK | |
| github_user_id | BIGINT | NOT NULL, UNIQUE — survives username changes |
| github_username | TEXT | NOT NULL, UNIQUE |
| display_name / email / avatar_url | TEXT | NULL |
| encrypted_github_token | TEXT | NOT NULL — Fernet ciphertext, never plaintext, never logged, never to browser |
| token_scopes | TEXT | NULL |
| last_login_at | TIMESTAMPTZ | NULL |
| created_at / updated_at | TIMESTAMPTZ | now() |

**`repositories`**

| Column | Type | Notes |
|---|---|---|
| repository_id | UUID PK | |
| user_id | UUID FK→app_users | ON DELETE CASCADE |
| github_repo_id | BIGINT | NOT NULL |
| owner / name / full_name / html_url | TEXT | NOT NULL |
| default_branch | TEXT | NULL |
| visibility | TEXT | CHECK IN ('public','private') |
| access_level | TEXT | CHECK IN ('owner','write','collaborator') |
| project_id | UUID FK→projects | NULL, ON DELETE SET NULL (Phase 10) |
| registered_at / updated_at | TIMESTAMPTZ | |

Constraints: `UNIQUE(user_id, github_repo_id)`, `UNIQUE(user_id, owner, name)` — duplicates are per-user, so different users can each track a shared repo.

**`scan_runs`** — operational; only the latest completed scan per repo survives (retention, §5.7).

| Column | Type | Notes |
|---|---|---|
| scan_id | UUID PK | |
| repository_id | UUID FK→repositories | CASCADE |
| triggered_by_user_id | UUID FK→app_users | CASCADE |
| trigger_type | TEXT | CHECK IN ('initial','manual') |
| status | TEXT | CHECK IN ('queued','running','completed','failed'), DEFAULT 'queued' |
| risk_score | NUMERIC(5,2) | NULL until completed; CHECK 0–100 |
| classification | TEXT | NULL; CHECK IN ('safe','medium','high_alert') |
| scoring_formula_version | TEXT | NOT NULL |
| error_message | TEXT | NULL |
| started_at / completed_at | TIMESTAMPTZ | NULL |
| created_at | TIMESTAMPTZ | |

**`manifest_files`**

| Column | Type | Notes |
|---|---|---|
| manifest_id | UUID PK; scan_id UUID FK→scan_runs CASCADE | |
| ecosystem | TEXT | CHECK IN ('npm','pypi') |
| manifest_path | TEXT | e.g. `frontend/package.json`; UNIQUE(scan_id, manifest_path) |
| lockfile_path | TEXT NULL; parser_name TEXT; created_at | |

**`packages`** — identity only, no volatile metadata cached.

| package_id UUID PK | ecosystem TEXT | package_name TEXT | registry_url TEXT NULL | created_at |
|---|---|---|---|---|

Constraint: `UNIQUE(ecosystem, package_name)`.

**`dependency_occurrences`** — one row per package per manifest per scan; duplicates across manifests are independent rows (each is an independent installation needing its own remediation).

| Column | Type | Notes |
|---|---|---|
| dependency_id | UUID PK | |
| manifest_id | UUID FK→manifest_files | CASCADE |
| package_id | UUID FK→packages | RESTRICT |
| dependency_group | TEXT | CHECK IN ('runtime','development','optional','peer','build','unknown'), DEFAULT 'runtime' |
| declared_specifier | TEXT | what the project asked for |
| resolved_version | TEXT NULL | lockfile-resolved where available |
| resolution | TEXT NULL | CHECK IN ('lockfile','pinned','range_latest_approx') — provenance of the version used for signals |
| latest_version | TEXT NULL; latest_release_at TIMESTAMPTZ NULL | registry state at scan time |
| staleness_days | INT NULL | days since package's latest release; NULL = unknown |
| versions_behind_major/minor/patch | INT DEFAULT 0, CHECK ≥0 | research covariate + display; not a formula term (D3) |
| is_deprecated | BOOL DEFAULT false | npm: version `deprecated`; PyPI: resolved release yanked OR classifier `Development Status :: 7 - Inactive` (D2) |
| deprecation_reason | TEXT NULL | verbatim registry text (S3's information-content variable — never normalized) |
| is_unassessable | BOOL DEFAULT false; unassessable_reason TEXT NULL | `file:`/`link:`/`workspace:`/git-URL/`dynamic_setup_py` — excluded from scoring, never silently dropped |
| vulnerability_count | INT DEFAULT 0, CHECK ≥0 | |
| highest_severity | TEXT NULL | CHECK IN ('low','medium','high','critical','unknown') |
| cvss_max | NUMERIC(3,1) NULL | max CVSS among current CVEs |
| cvss_reduced_confidence | BOOL DEFAULT false | true when the 5.0 placeholder was used (§5.2) |
| risk_component_score | NUMERIC(5,2) NULL | CHECK 0–100 |
| is_flagged | BOOL DEFAULT false | rule in §5.2 |
| created_at | TIMESTAMPTZ | |

**`dependency_vulnerabilities`**

| Column | Type | Notes |
|---|---|---|
| vulnerability_id UUID PK; dependency_id FK→dependency_occurrences CASCADE | | UNIQUE(dependency_id, osv_id) |
| osv_id TEXT NOT NULL; cve_id TEXT NULL | | |
| severity TEXT NULL | CHECK as above | |
| cvss_score NUMERIC(3,1) NULL | | |
| published_at TIMESTAMPTZ NULL | | disclosure date — backfill's as-of filter needs this (D17) |
| summary / affected_range / fixed_version / source_url | TEXT NULL | fixed_version feeds S3 ground truth |
| epss_score NUMERIC(6,5) NULL | | Phase 12, flag-gated |

**`reports`** — cached LLM outputs; UI always reads stored rows, never live responses.

| Column | Type | Notes |
|---|---|---|
| report_id UUID PK; scan_id FK→scan_runs CASCADE; dependency_id FK→dependency_occurrences CASCADE NULL | | |
| report_type | TEXT | CHECK IN ('combined','per_dependency'); CHECK (combined ⇔ dependency_id IS NULL) |
| status | TEXT | CHECK IN ('queued','running','completed','failed') |
| summary_text TEXT NULL; fixes_json JSONB NULL; citations_json JSONB NULL; retrieved_chunks_json JSONB NULL | | fixes schema §5.8 |
| grounding_confidence | TEXT NULL | CHECK IN ('sufficient','low') |
| project_context_json | JSONB NULL | sibling-notice lines + disclaimer flag (Phase 10) |
| model_name TEXT NULL; error_message TEXT NULL; generated_at TIMESTAMPTZ NULL; created_at/updated_at | | |

Partial uniques: one `combined` per scan; one `per_dependency` per (scan_id, dependency_id).

**`scan_history`** — permanent, research. **No FKs at all**; never cascades; denormalized snapshots.

| Column | Type | Notes |
|---|---|---|
| scan_history_id | UUID PK | |
| source_scan_id | UUID NULL | traceability only, no FK |
| github_user_id BIGINT; github_username TEXT; github_repo_id BIGINT; repo_full_name TEXT | | snapshots |
| ecosystems | TEXT | e.g. `npm` / `npm,pypi` |
| risk_score NUMERIC(5,2) NOT NULL; classification TEXT NOT NULL | | CHECKs as above |
| dependency_count INT; flagged_dependency_count INT | | ≥0 |
| scoring_formula_version | TEXT NOT NULL | |
| data_source | TEXT | CHECK IN ('live_scan','backfill'), DEFAULT 'live_scan' |
| snapshot_date | DATE NULL | backfill grid month-end; NULL for live |
| sampling_weight | NUMERIC NULL | corpus stratification weight (backfill rows) |
| scanned_at | TIMESTAMPTZ | |

Indexes: (github_repo_id, snapshot_date), (data_source).

**`dependency_history`** — permanent; one row per occurrence per completed scan/snapshot **including clean and unassessable occurrences** (hazard models need at-risk denominators, not just bad rows). FK only to its own permanent parent.

| Column | Type | Notes |
|---|---|---|
| dependency_history_id UUID PK; scan_history_id FK→scan_history ON DELETE RESTRICT | | |
| ecosystem TEXT; package_name TEXT; manifest_path TEXT; dependency_group TEXT | | |
| declared_specifier TEXT NULL; resolved_version TEXT NULL; resolution TEXT NULL; latest_version TEXT NULL | | |
| staleness_days INT NULL; versions_behind_major/minor/patch INT | | |
| is_deprecated BOOL; deprecation_reason TEXT NULL | | verbatim |
| vulnerability_count INT; highest_severity TEXT NULL; cvss_max NUMERIC(3,1) NULL | | |
| is_unassessable BOOL DEFAULT false | | |
| risk_component_score NUMERIC(5,2) NULL | | as computed then; research recomputes from signals per D6 |
| recorded_at | TIMESTAMPTZ | |

Indexes: (scan_history_id), (package_name, ecosystem).

**`agent_execution_traces`** — permanent; no FKs; survives rescans and deletions; S3's raw data.

| Column | Type | Notes |
|---|---|---|
| trace_id UUID PK; source_report_id UUID NULL; source_scan_id UUID NULL | | snapshots, no FK |
| github_user_id BIGINT; repo_full_name TEXT | | |
| ecosystem TEXT; package_name TEXT; resolved_version TEXT NULL | | ecosystem denormalized so S3 groups from this table alone |
| branch_taken TEXT | | `reason_available` / `no_reason` |
| retrieval_query TEXT NULL | | |
| retrieved_chunks_json JSONB NOT NULL | | ALL retrieved chunks with similarity scores, not only cited ones |
| generation_json JSONB NOT NULL | | final output + prompt/model metadata |
| grounding_confidence TEXT | CHECK sufficient/low | |
| model_name TEXT NULL; created_at | | |

**`projects`**

| project_id UUID PK | user_id FK→app_users CASCADE | name TEXT | created_at |
|---|---|---|---|

Membership = `repositories.project_id`. The ≥2-member rule and same-owner rule are enforced in the service layer at creation; a non-empty `project_id` therefore implies same-user siblings exist by construction.

### 5.2 Occurrence scoring (binding)

```
occurrence_score = 100 − 100 · ( w_dep·P_dep + w_sev·S_cvss + w_cnt·S_count + w_stl·S_stale )      Σw = 1 (per ecosystem)
P_dep   = 1 if is_deprecated else 0
S_cvss  = cvss_max / 10          # missing CVSS for a known CVE: OSV → NVD fallback → 5.0 placeholder + cvss_reduced_confidence=true
S_count = min(cve_count, 10) / 10
S_stale = min(staleness_days, 1095) / 1095
```

Missing-value policy: staleness unknown (no publish history) → term excluded, its weight redistributed proportionally across remaining signals for that occurrence. Zero CVEs = informative zero, not missing. EPSS appended as a fifth term only when the active weights file sets `epss.enabled`.

Flag rule (fixed, score-independent): `is_flagged = is_deprecated OR vulnerability_count > 0 OR staleness_days ≥ 730`. Unassessable occurrences are never flagged or scored and are excluded from all denominators; they render in their own UI list with reasons.

### 5.3 Repository roll-up: rank-decayed penalty aggregation (binding)

```
penalties  = sorted([100 − occurrence_score for each assessable occurrence], desc)[:max_terms]
repo_score = clamp( 100 − Σ_{k≥0} penalties[k] · decay^k , 0, 100 )        # defaults: decay 0.5, max_terms 20
classify: ≥80 Safe · 50–79 Medium · <50 High-Alert
```

Properties (state verbatim in any write-up): the worst occurrence dominates (k=0 undecayed); each further bad occurrence adds real but geometrically diminishing penalty, so breadth counts without mean-dilution — 500 clean dependencies cannot mask 3 critical ones because clean rows contribute 0 rather than diluting a denominator; monotone (a new bad dependency never raises the score); duplicate occurrences across manifests count independently by construction; bounded (Σ decay^k = 2 ⇒ max deduction 2× the worst penalty, then clamped); explainable (top contributors surfaced in UI). `decay`, `max_terms`, and the 80/50 thresholds are calibration parameters swept in WP-6's sensitivity analysis.

### 5.4 Weights YAML schema (every version)

```yaml
version: v1                       # tag written into every score row
derivation: informal-pairwise     # v2: ahp-entropy-validated
normalization: { cve_count_cap: 10, staleness_cap_days: 1095 }
flag_rule:     { stale_flag_days: 730 }
thresholds:    { safe_min: 80, medium_min: 50 }
rollup:        { decay: 0.5, max_terms: 20 }
weights:
  npm:  { deprecation: 0.00, severity: 0.00, count: 0.00, staleness: 0.00 }   # WP-1 / WP-6 fill
  pypi: { deprecation: 0.00, severity: 0.00, count: 0.00, staleness: 0.00 }
epss: { enabled: false, weight: 0.0 }
```

Loader validates: per-ecosystem weights sum to 1 (±0.001), caps positive, thresholds ordered. Active version = `WEIGHTS_VERSION` env.

### 5.5 API surface (complete; built up over phases; every resource route behind `OwnedQuerySetMixin`)

```
GET  /api/health/
GET  /api/auth/github/login/ | /callback/         (Phase 1)
GET  /api/auth/session/       POST /api/auth/logout/
POST /api/repositories/                            (2: validate + register)
GET  /api/repositories/       DELETE /api/repositories/{id}/
POST /api/repositories/{id}/scan/                  (3: 202 | 409 in-progress | 409 confirm-required after Phase 9)
GET  /api/repositories/{id}/scan-status/
GET  /api/scans/{id}/         GET /api/scans/{id}/dependencies/?flagged=&page=
GET  /api/dependencies/{id}/                       (5: signal breakdown)
POST /api/scans/{id}/reports/combined/             (7)      GET /api/reports/{id}/
POST /api/dependencies/{id}/report/                (8)
GET  /api/reports/{id}/download/?fmt=md|json       (9)
GET  /api/repositories/{id}/history/               (10: live rows only)
POST/GET/DELETE /api/projects/…                    (10)
```

### 5.6 Pre-scan validation (Phase 2; binding messages)

Four ordered checks before any registration or scan: (1) reachability — `GET /repos/{owner}/{repo}` with the requesting user's own token; (2) eligibility — `permissions.push OR permissions.admin` (read-only public repos and fork-and-PR-only workflows are excluded: the user must be able to act on findings); (3) per-user duplicate; (4) full-tree manifest presence — `GET /repos/{o}/{r}/git/trees/{default_branch}?recursive=1`, matched against adapter patterns anywhere in the tree (root-only checks silently miss split-by-functionality repos; the API's `truncated:true` on ~100k+ entry trees is an accepted, documented limitation).

| Outcome | HTTP | `code` | Message |
|---|---|---|---|
| not found / inaccessible | 404 | `repo_inaccessible` | "We couldn't access this repository. Check the link, or make sure it's public." |
| read-only / fork-and-PR only | 403 | `no_write_access` | "You need write or collaborator access on this repository to monitor it here." |
| duplicate (same user) | 200 | `already_registered` | body carries existing repo id → FE redirects |
| no supported manifest anywhere | 422 | `ecosystem_unsupported` | "This repository's dependency ecosystem isn't supported yet. We currently support Node.js/npm projects." → Phase 6 updates to "…Node.js/npm and Python/PyPI projects." |
| empty repository | 422 | `repo_empty` | "This repository appears to be empty — there's nothing to scan." |
| GitHub rate-limited | 503 | `github_rate_limited` | "We're temporarily unable to check this repository. Please try again in a few minutes." |

SSRF discipline: the pasted URL is parsed to `owner/repo` and discarded; every outbound call is constructed server-side against the `api.github.com` allowlist in `common/http.py` — the single choke point all outbound HTTP in the entire project must pass through.

### 5.7 Retention (binding)

On scan completion: write `scan_history` + `dependency_history` rows (all occurrences) → then delete the repo's prior completed `scan_runs` cascade (manifests, occurrences, vulnerabilities, reports). Only the latest scan's operational detail exists at any time. `scan_history`, `dependency_history`, `agent_execution_traces` are never deleted by any trigger (D9). Rescan while the current scan has reports requires explicit confirmation (Phase 9) because the cascade destroys generated reports.

### 5.8 Report content schema (binding)

One generation produces one payload serving both downloads (no second LLM call):

```json
{ "summary_md": "...",
  "fixes": [ { "package": "", "manifest_path": "", "ecosystem": "npm|pypi",
               "current_version": "", "fix_type": "upgrade|replace|remove|investigate",
               "target_version": null, "replacement_package": null,
               "cves": [""], "severity": "", "priority": 1 } ] }
```

PER_DEPENDENCY additionally stores citations (chunk ids), all retrieved chunks, and the grounding-confidence flag. The JSON download is a machine-parseable task handoff for external coding agents; RepoVitals itself only ever suggests fixes, never applies them (no write calls, ever).

### 5.9 PER_DEPENDENCY agent graph (binding; single pass, no loops, no retries)

`load_context → ensure_corpus (lazy: fetch changelog/README, chunk, embed into per-scan Chroma collection on this dependency's first request only) → frame_query (branch on deprecation_reason presence: replacement/migration framing quoting the reason, vs upgrade/breaking-changes framing; branch recorded) → retrieve (k=5, filtered by dependency + resolved version) → assess_grounding (deterministic, no LLM: top-1 similarity ≥ GROUNDING_MIN_SIM=0.30 AND total retrieved chars ≥ GROUNDING_MIN_CHARS=400) → generate (exactly one Groq call, temp 0; retrieved chunks framed as reference data, never instructions; cite chunk ids; if low confidence: instructed to state insufficient information rather than guess) → persist (report + full trace) → cleanup (delete this dependency's chunks — everything of value now lives in Postgres)`.

Chroma discipline: `get_or_create_collection` (creation-race safe); per-scan `threading.Lock` serializes chunk writes (embedded Chroma is SQLite-backed — limited concurrent-write support); the **resolved** version string is used both at write-tag time and read-filter time (a manifest-range string on one side causes silent empty retrieval → false low-confidence). COMBINED bypasses this graph entirely: one LLM call over stored structured signals, no retrieval — deliberately a lighter triage surface so the grounded-generation thesis stays concentrated in PER_DEPENDENCY.

Cost is bounded by construction: single pass, fixed tool set, one generation per request, cache-first serving.

---

## 6. Configuration registry

| Env var | From | Notes |
|---|---|---|
| DJANGO_SECRET_KEY / DJANGO_SETTINGS_MODULE / ALLOWED_HOSTS / DATABASE_URL | 1 | research machine's DATABASE_URL points at the research Postgres (D8) |
| TOKEN_ENCRYPTION_KEY | 1 | Fernet; rotation invalidates stored tokens (users re-login) |
| GITHUB_OAUTH_CLIENT_ID / SECRET | 1 | separate dev + prod apps |
| FRONTEND_URL | 1 | OAuth redirect + CSRF trusted origin |
| GITHUB_API_PAT | 11 | research commands only; never used for user-facing scans |
| GROQ_API_KEY / GROQ_MODEL | 7 | default `llama-3.3-70b-versatile`, temp 0 |
| CHROMA_DIR / EMBED_MODEL | 8 | default `all-MiniLM-L6-v2` via fastembed |
| GROUNDING_MIN_SIM / GROUNDING_MIN_CHARS | 8 | defaults 0.30 / 400 |
| WEIGHTS_VERSION | 4 | active weights file |
| EPSS_ENABLED / NVD_API_KEY | 12 | optional |
| GEMINI_API_KEY / JUDGE_MODEL | 13 | judge provider ≠ generator provider (D11) |

**Credentials (provided by the developer's own accounts; all free):** Phase 1 → GitHub OAuth apps (dev + prod), Supabase URL, Render + Vercel. Phase 7 → Groq key. Phase 11 → GitHub PAT (`public_repo`). Phase 13 → Gemini key. Optional → NVD key. Keys pasted into working sessions are treated as rotatable and rotated at project end.

---

## 7. File B gates (the only cross-file dependencies)

| Gate | Deliverable | Consumed at | Fallback if late |
|---|---|---|---|
| WP-1 | Tier-1 weight vectors + method note | Phase 4 acceptance | ship `weights_v0_equal` (0.25×4), swap on arrival — zero code change |
| WP-2 | Anchor set CSV | Phase 12 validation run | none (blocks Phase 12 acceptance only) |
| WP-3 | AHP matrices (2 independent + reconciled) | Phase 12 weights-v2 computation | none |
| WP-4 | Corpus manifest + strata report | Phase 12 inputs | requires Phase 11 code first |
| WP-5 | Backfill completion report **+ research-DB dump file** | Phase 12/13 dev inputs (developer loads dump locally) | overnight, resumable |
| WP-6 | Validation sign-off → `weights_v2.yaml` | **Phase 12 acceptance** | code-complete may tag `v0.12.0-rc`; final tag waits |
| WP-7 | Cohort registered + monthly rescans + consent recorded | starts right after Phase 6 deploys | lead-time critical — start immediately |
| WP-8 | S3 full runs (A/B/C × 150) | Phase 14 acceptance | pilot (20 items) is Phase 13's own acceptance |
| WP-9 | 50-item judge-validation labels | Phase 14 acceptance | |
| WP-10 | Backfill-vs-prospective agreement report | not a phase gate; pre-S2-drafting (File C) | time-gated: ≥3 monthly WP-7 waves |

---

## 8. Free-tier constraint register

| Constraint | Limit | Design answer |
|---|---|---|
| Render RAM | 512 MB | fastembed not torch (D7); 1 worker; memory smoke test Phase 1, re-run Phase 8 with Chroma loaded |
| Render sleep / Supabase pause | 15 min / ~7 days | keepalive cron (Phase 1) |
| Render instance-hours | 750/mo | exactly one always-on service |
| Render request timeout | ~100 s | scans + generations always background threads + polling, never inline |
| Supabase storage | 500 MB | prod holds product + cohort data only; corpus/backfill live in the research DB (D8); manifests on disk, not Postgres |
| GitHub API | 5,000/hr/token | user scans on user tokens; research on PAT; shared client honors `X-RateLimit-*`, backs off, checkpoints |
| GitHub Search API | 30 req/min; 1,000 results/query hard cap | corpus builder partitions the query space and paces (Phase 11) |
| OSV / npm / PyPI / deps.dev | free, unauthenticated | OSV batched ≤100/batch; in-run caches; no TTL cache layer at this scale (deliberate deferral, §12) |
| Groq free tier | strict RPM/TPD | pacing + checkpoints; S3 full runs span days by design |
| Gemini free tier | RPM/day caps | judge calls cached by (item, condition, judge-version); resumable |
| Teammate machine (research) | disk/CPU | research DB + corpus ≈ 2–5 GB disk; fastembed is CPU-friendly; all runs resumable |

---

## 9. Phase index

| Phase | Title | Mentor demo | Tag | Gates |
|---|---|---|---|---|
| 1 | Foundations: auth walking skeleton, deployed | GitHub login on live URL | v0.1.0 | — |
| 2 | Registration + pre-scan validation | paste URL → registered or specific rejection | v0.2.0 | — |
| 3 | Scanner + npm adapter + background scans | dependency table after background scan | v0.3.0 | — |
| 4 | Scoring engine + weights v1 | 0–100 score + classification badge | v0.4.0 | WP-1 |
| 5 | Drill-down: why flagged | per-signal contribution breakdown | v0.5.0 | — |
| 6 | PyPI adapter (soundness proof) | Python repo through unchanged pipeline | v0.6.0 | — |
| 7 | COMBINED report (first LLM call) | repo-wide triage, cached | v0.7.0 | Groq key |
| 8 | PER_DEPENDENCY RAG agent | cited remediation + retrieved chunks side-by-side | v0.8.0 | — |
| 9 | Guards, downloads, hardening | rescan confirm, MD/JSON downloads, BOLA suite | v0.9.0 | — |
| 10 | Projects + trends | grouped repos, trend chart, sibling notice | v0.10.0 | — |
| 11 | Research I: corpus + backfill engines | 5-year reconstructed risk curve, one real repo | v0.11.0 | PAT |
| 12 | Research II: S1 harness + weights v2 | validation report: AHP vs entropy, correlation, sensitivity | v0.12.0 | WP-2…6 |
| 13 | Research III: S3 harness + judge | pilot 3-condition comparison table | v0.13.0 | Gemini key |
| 14 | Replication package + v1.0 | 10-min seminar walkthrough | v1.0.0 | WP-8, WP-9 |

**Ordering flexibility:** Phase 11 depends only on Phases 1–6 (adapters + scoring), not on 7–10. If the teammate's WP-4/WP-5 lead time matters more than product-feature cadence, pull Phase 11 forward to run right after Phase 6. Phases 12–13 stay after 11 (and 13 after 8, which supplies the agent).

---

## 10. Phases

### Phase 1 — Foundations: repo, auth, walking skeleton, deployed

**Objective.** A logged-in user sees their GitHub identity on an empty dashboard at the production URL. CI, deploys, and keepalive exist from day one.

**Backend.** Scaffold `config/` (split settings, django-environ, `DATABASE_URL`); dev Postgres via compose. Custom `accounts.User` (§5.1). Token crypto: Fernet `encrypt_token/decrypt_token`; decrypt only transiently in-process; never serialized, logged, or sent to the browser. GitHub OAuth via django-allauth with `SOCIALACCOUNT_STORE_TOKENS=False`; capture the access token in the login signal, encrypt into `encrypted_github_token`, record scopes, update profile + `last_login_at`. Session cookie `HttpOnly; Secure; SameSite=Lax`; `CSRF_TRUSTED_ORIGINS=[FRONTEND_URL]`. Views: health (DB round-trip), session, logout; OAuth callback → `FRONTEND_URL/dashboard`. `gunicorn.conf.py` per §3 (gthread is required for the mixed request+background-thread pattern; the default sync worker is not designed for it).

**Frontend.** Vite + React + TS + Tailwind + router; `api/client.ts`; AuthContext bootstrapping from session endpoint; ProtectedRoute; Login page; Dashboard skeleton. **Back-navigation guard:** while authenticated, popstate toward `/login` opens a logout-confirmation dialog; the login page renders only after explicit confirm (which logs out); cancel restores the current entry. Back-navigation alone can never log a user out or expose the login screen.

**Infra.** Repo; `ci.yml`; Render + Vercel wired to `main`; `vercel.json` rewrite; `keepalive.yml`; `.env.example`; README quickstart.

**Memory smoke test (now, not later).** `smoke_memory` command: exercise login plus a synthetic thread doing a registry fetch + one fastembed embedding; record worker RSS from Render logs into `docs/decisions.md`. This is a genuine feasibility question on a 512 MB tier — answer it in week one.

**Commits.** 1 `chore(repo): scaffold monorepo, gitignore, license, readme` · 2 `feat(backend): django project, split settings, health endpoint, docker postgres` · 3 `feat(backend): custom user model with encrypted github token storage` · 4 `feat(backend): github oauth login/callback/session/logout` · 5 `feat(frontend): vite react ts tailwind scaffold, api client, router` · 6 `feat(frontend): auth context, login, protected dashboard, logout + back-nav confirm` · 7 `chore(ci): lint and test workflows` · 8 `chore(deploy): render + vercel + api rewrite proxy + keepalive cron` · 9 `test(auth): session lifecycle, token encryption roundtrip, smoke_memory`

**Acceptance.** Prod URL: login → identity shown; refresh persists; logout works; back-gesture triggers confirm, cancel keeps session. Token stored as ciphertext (shell-verified roundtrip); no token substring in logs. Keepalive history shows health 200s. CI green. RSS recorded, comfortably < 512 MB.

**Mentor demo.** Login on the live URL → avatar/name → refresh → works on their phone too.

### Phase 2 — Repository registration + pre-scan validation

**Objective.** Paste a GitHub URL → registered, or rejected with the exact §5.6 message — before any scan work or quota is spent on an ineligible repo.

**Backend.** `Repository` model + constraints (§5.1). `common/http.py` — the single outbound client: allowlist (api.github.com now; registries in Phase 3), timeouts, retry/backoff, rate-limit awareness. `repositories/validation.py` — the four ordered checks (§5.6); empty tree → `repo_empty`; `truncated:true` → proceed with returned entries. Endpoints: register (validation envelope in response), list, delete (cascades operational data only — history survives by design). `common/authz.py::OwnedQuerySetMixin` introduced now and used by every subsequent resource view. Store `github_repo_id, default_branch, visibility, access_level` from validation responses.

**Frontend.** AddRepoForm (server re-parses authoritatively); per-code error rendering incl. redirect-to-existing; RepoCard grid; delete with ConfirmDialog.

**Commits.** 1 `feat(backend): repository model with ownership + duplicate constraints` · 2 `feat(backend): allowlisted outbound http client with retry/backoff` · 3 `feat(backend): pre-scan validation with four ordered checks` · 4 `feat(backend): register/list/delete endpoints + owned-queryset authz mixin` · 5 `feat(frontend): add-repo form with outcome messaging, repo cards, delete confirm` · 6 `test(repositories): validation outcome matrix, nested-manifest tree, BOLA baseline`

**Acceptance.** Every §5.6 row reproduced (fixtures + live spot-checks: own repo OK; unwritable big public repo → `no_write_access`; docs-only repo → `ecosystem_unsupported`; resubmit → redirect). Nested-manifest-only repo passes. BOLA: foreign repo id → 404.

**Mentor demo.** Four URLs pasted live → one registers, two reject with specific reasons, one redirects as duplicate.

### Phase 3 — Scanner core, npm adapter, background scans

**Objective.** Registration auto-triggers a background scan; dashboard shows pending → scanning → done; detail lists every dependency from every manifest in the tree with resolved versions and CVE counts. No scoring yet.

**Backend.**
- Models: `ScanRun`, `ManifestFile`, `Package`, `DependencyOccurrence`, `DependencyVulnerability` (§5.1).
- `adapters/base.py`: `DependencyAdapter` — `manifest_patterns()`, `parse(manifest_bytes, lockfile_bytes|None) → list[DepSpec]`, `registry_client()`. `DepSpec`: name, declared_specifier, group, resolved_version|None, resolution, is_unassessable(+reason).
- `adapters/npm.py`: package.json groups (dependencies/dev/optional/peer); lockfile v2/v3 `packages` map → resolved version preferred over ranges (a manifest range is what's *allowed*, not what's *installed*); non-registry specifiers (`file:`, `link:`, `workspace:`, `git+…`, `github:…`, URLs) → unassessable with reason.
- npm registry client: `GET registry.npmjs.org/{name}` → latest, per-version `deprecated` text, `time` map → `latest_release_at`, `staleness_days`, `versions_behind_*` (semver distance). In-run dict cache per scan; no TTL layer (deliberate §12 deferral).
- `osv.py`: `POST /v1/querybatch` (ecosystem `npm`, chunks ≤100) → unique vuln details fetched once each (in-run cache) → CVE id, severity bucket, `cvss_score` (parsed from CVSS vector where present), **`published_at`**, affected/fixed ranges, source URL.
- `scanner.py`: re-list tree at scan time → fetch matched manifests + sibling lockfiles (contents API; size caps; parse inside try/except; nothing fetched is ever executed or eval'd) → parse per adapter → pool occurrences tagged with manifest path (duplicates kept as independent rows) → enrich → persist all raw signals (D6/D17).
- `background.py`: thread wrapper with `close_old_connections()` at start and end (Django connections are not thread-safe to share); per-repo in-process `threading.Lock` + DB status check → concurrent trigger 409 `scan_in_progress`; status transitions with timestamps + `error_message`.
- Trigger on registration (fire-and-forget after 201) + manual `POST /scan/`. Endpoints per §5.5.

**Frontend.** StatusPill + `usePolling` (3 s while active; stops on terminal; resumes on tab focus). RepoDetail v1: manifest summary, DependencyTable (name, path chip, group, declared→resolved, latest, CVE badge, deprecated badge, unassessable badge), scanning skeleton, failed state with retry.

**Commits.** 1 `feat(backend): scan/manifest/package/occurrence/vulnerability models` · 2 `feat(backend): dependency adapter interface + npm parser with lockfile preference` · 3 `feat(backend): npm registry client with staleness + versions-behind` · 4 `feat(backend): batched osv client with cvss + published-at extraction` · 5 `feat(backend): scan orchestrator pooling multi-manifest occurrences, raw signal persistence` · 6 `feat(backend): background thread runner with connection hygiene + scan lock` · 7 `feat(backend): scan trigger/status/detail/dependencies endpoints` · 8 `feat(frontend): status polling, dependency table v1` · 9 `test(scanning): golden npm repo, monorepo pooling, unassessable specifiers, lock contention`

**Acceptance.** Real small npm repo completes < 2 min on prod; nested-manifest repo shows rows from every manifest with path tags; lockfile beats range (fixture proves divergence); `git+`/`file:` under unassessable with reasons; double-click → exactly one ScanRun; registration returns < 2 s with the scan running behind.

**Mentor demo.** Register live → watch the pill → open detail → point at a dependency found in a *nested* folder → point at an unassessable row ("'can't assess' instead of silently miscounting").

### Phase 4 — Scoring engine + weights v1 `GATE: WP-1`

**Objective.** Every scan produces a deterministic score + classification per §5.2–§5.4; history rows start accumulating.

**Backend.** `scoring/` pure functions (no I/O in engine/normalize); `weights.py` loader + validation + version registry. Scan-completion pipeline: score each assessable occurrence (per-ecosystem vector) → flag rule → roll-up → `scan_runs` fields. History writes before retention: one `scan_history` row + `dependency_history` rows for **all** occurrences (incl. clean + unassessable), `data_source='live_scan'`, formula version. Then `retention.py` (§5.7). `rescore` command: recompute from stored signals under any named weights version → **materialized output file** (never mutates history rows, D6). Ship `weights_v0_equal.yaml`; adopt `weights_v1.yaml` the day WP-1 lands (values + method paragraph into `docs/decisions.md`).

**Frontend.** ScoreBadge (number + class color) on cards + detail header; top-3 contributors strip (package + points deducted); scanned-at timestamp.

**Commits.** 1 `feat(scoring): normalization with caps + missing-value redistribution` · 2 `feat(scoring): occurrence scoring, flag rule, rank-decayed rollup, classifier` · 3 `feat(scoring): versioned weights yaml loader + v0-equal bootstrap` · 4 `feat(scanning): score-on-completion, history writes, prior-scan retention` · 5 `feat(backend): rescore command materializing panels from stored signals` · 6 `feat(frontend): score badge + top-contributors strip` · 7 `test(scoring): golden exact scores, monotonicity, boundaries, no-dilution property` · 8 `chore(weights): adopt weights_v1 from WP-1` *(when delivered)*

**Acceptance.** Golden fixtures reproduce hand-computed scores exactly. Properties: adding a CVE never raises any score; adding 200 clean deps to a 3-critical fixture moves the repo score < 1 point. Anchor sanity: a repo pinning old `request` classifies Medium or worse. Rescan of unchanged repo → identical score. Every completed scan → exactly one history row + N dependency rows, version-tagged. Prior scan's operational rows gone after a new scan; history intact.

**Mentor demo.** Two contrasting repos → Safe vs High-Alert → open the bad one → "the score is these three packages; here's the arithmetic."

### Phase 5 — Drill-down: why every flag exists

**Objective.** Every flagged dependency explains itself — signal by signal, with exact point contributions and the CVE list. This page is the product's credibility.

**Backend.** `GET /api/dependencies/{id}/`: per-signal `{raw, normalized, weight, points_deducted}` recomputed live via the pure functions from stored signals (single source of truth); nested vulnerabilities (id, severity, cvss, summary, affected→fixed, link); deprecation reason verbatim; versions-behind; resolution provenance. Scan summary counts (flagged/clean/unassessable).

**Frontend.** RepoDetail v2: tabs Flagged / All / Unassessable; expandable rows → WhyFlaggedPanel (contribution bars with points, CVE chips + links, deprecation quote, "resolved from lockfile" vs "approximated against latest" tag); Run Scan button wired to server lock state; empty states.

**Commits.** 1 `feat(backend): dependency breakdown endpoint with contribution arithmetic` · 2 `feat(backend): scan summary counts` · 3 `feat(frontend): tabs + why-flagged panel` · 4 `feat(frontend): run-scan button states` · 5 `test(api): contributions sum to total deduction; BOLA on dependency route`

**Acceptance.** Contributions sum (±0.1) to the occurrence's deduction; every on-screen number traceable to a stored signal; unassessable rows show reasons and are absent from score math; panel is screenshot-quality for the report.

**Mentor demo.** Walk one signal raw → normalized → weight → points. "Nothing here is an LLM opinion — this is the auditable half."

### Phase 6 — PyPI adapter: the soundness proof

**Objective.** A Python repository flows through the **unchanged** scanner, scoring engine, and (later) agent. The phase diff is itself research evidence.

**Backend.** `adapters/pypi.py` — all parsing static, nothing executed: `requirements*.txt` (`==` → pinned; ranges → declared), `pyproject.toml` (PEP 621 `[project.dependencies]` + poetry sections), `Pipfile`/`Pipfile.lock` (lock wins), `poetry.lock` (wins), `setup.py` via `ast` literal extraction only — dynamic constructs → unassessable `dynamic_setup_py` (documented gap, not a miscount). Resolution precedence: lockfile > pinned > range (`range_latest_approx`: signals computed against latest, provenance-tagged). PyPI JSON client: `pypi.org/pypi/{name}/json` → releases + upload times (staleness, versions-behind via PEP 440 ordering), per-release `yanked`/`yanked_reason`, classifiers. **Deprecation composite (D2):** resolved release yanked OR `Development Status :: 7 - Inactive` → deprecated; reason = yanked_reason or classifier, stored verbatim however terse (that asymmetry is S3's variable). OSV ecosystem `PyPI`. Validation patterns + message extended to both ecosystems. Mixed-ecosystem repos: all manifests pooled into one scan, one roll-up, per-ecosystem weight vectors per occurrence.

**Guardrail.** This phase may not modify `scanner.py`, `scoring/engine.py`, `scoring/normalize.py`, or anything under `reports/`. Produce `docs/adapter_soundness.md`: the phase's `git diff --stat`, touched-path list, untouched-core assertion.

**Frontend.** EcosystemChip (npm/pypi/mixed); `dynamic_setup_py` reason rendering.

**Commits.** 1 `feat(adapters): pypi parsers (requirements, pyproject, pipfile, poetry.lock, setup.py-ast)` · 2 `feat(adapters): pypi registry client with yanked+classifier deprecation composite` · 3 `feat(scanning): pypi osv ecosystem + validation patterns/messages` · 4 `feat(frontend): ecosystem chips` · 5 `docs: adapter_soundness evidence` · 6 `test(adapters): five formats, precedence, yanked composite, mixed-repo pooling`

**Acceptance.** Old-pinned-Django repo registers/scans/scores; poetry repo resolves from lock; mixed monorepo → one pooled score, both chips; yanked-release dependency shows deprecated with (possibly empty) verbatim reason; `adapter_soundness.md` shows zero core-path changes.

**Mentor demo.** Python repo → same flow, same badge, same drill-down → show the diff doc: "second ecosystem, zero core changes — a design claim turned into evidence." *(WP-7 recruiting starts today.)*

### Phase 7 — COMBINED report: first LLM call `needs: Groq key`

**Objective.** One click → repo-wide prioritized triage from already-persisted signals (no retrieval — deliberately the lighter surface), cached so the LLM runs exactly once per scan.

**Backend.** `Report` model (§5.1). `llm/groq_client.py`: temp 0, JSON mode, timeout, one retry on transient 5xx/429; call metadata recorded. Combined prompt: input = structured signal rows only (no fetched text ⇒ injection surface ≈ 0; system prompt still frames input as data). Output validated against §5.8 (pydantic; one repair-retry on schema violation). `services.py`: cache-or-generate on `(scan, 'combined')` — hit serves stored row; miss → per-key in-process generation lock → background thread → polling. UI always reads stored rows. Endpoints: POST (200 cached | 202 | 409 generating), GET.

**Frontend.** Reports tab: Generate → generating (poll) → summary markdown + prioritized fixes table; cached banner with `generated_at`; "regenerate requires a rescan" hint; failed state.

**Commits.** 1 `feat(reports): report model with type constraints + partial uniques` · 2 `feat(reports): groq client + combined prompt/schema validation` · 3 `feat(reports): cache-or-generate with per-key lock + background generation` · 4 `feat(reports): combined endpoints with polling` · 5 `feat(frontend): reports tab, fixes table, cached indicator` · 6 `test(reports): cache hit = zero llm calls; concurrent lock; schema repair`

**Acceptance.** Second click serves instantly with a **zero-LLM-call assertion**; double-click → one generation; every fix references a real scanned row (validator cross-checks); rescan → fresh scan, empty reports, history intact.

**Mentor demo.** Generate on a messy repo → prioritized list → click again: instant, cached. "We never re-bill the LLM for the same scan."

### Phase 8 — PER_DEPENDENCY RAG agent: the thesis feature

**Objective.** For one flagged dependency: fetch its changelog/README, run the §5.9 graph, generate a cited plan, show retrieved source **beside** the answer, persist the full trace permanently.

**Backend.** `rag/fetch_docs.py`: package → repo URL (registry metadata) → parse owner/repo (same SSRF discipline) → try `CHANGELOG.md|CHANGELOG|CHANGES.md|HISTORY.md` at root (contents API, 500 KB cap) → fallback `GET /repos/{o}/{r}/readme`; record source refs (path + sha); unresolvable repo → graph proceeds to the honest insufficient-information path. Chunker (heading-aware, ~1,200 chars, 200 overlap, stable chunk ids); fastembed singleton; `chroma_store.py` per §5.9. `agent/graph.py`: LangGraph nodes exactly per §5.9. Persistence: report row + `agent_execution_traces` row (all chunks + scores, branch, query, generation + model meta) — trace decoupled from the reports cascade so it survives rescans. Cleanup deletes the dependency's chunks. Endpoints on the shared cache/lock/polling pattern keyed `(scan,'per_dependency',dependency)`.

**Frontend.** "Generate remediation" on flagged rows → ReportPanel drawer: summary, fixes, low-confidence banner; **CitationPane**: retrieved chunks side-by-side, cited chunks highlighted, source path + similarity shown.

**Commits.** 1 `feat(rag): changelog/readme fetcher with source refs + caps` · 2 `feat(rag): chunker + fastembed + per-scan chroma store with write lock` · 3 `feat(agent): langgraph single-pass graph with deprecation branch + deterministic grounding check` · 4 `feat(agent): grounded generation with citations + insufficient-information path` · 5 `feat(agent): report + permanent trace persistence, chunk cleanup` · 6 `feat(reports): per-dependency endpoints` · 7 `feat(frontend): remediation drawer + citation pane + confidence banner` · 8 `test(agent): branch selection, grounding thresholds, trace completeness, cleanup, determinism` · 9 `chore: re-run memory smoke with chroma + fastembed loaded, record RSS`

**Acceptance.** Deprecated-with-successor package (e.g. `request`) → replacement-framed cited plan quoting changelog text; unresolvable-repo package → insufficient-information report, still fully traced; trace survives a rescan (cascade test); Chroma chunk count for the dependency = 0 after persist; repeat request → byte-identical output; RSS re-recorded < 512 MB.

**Mentor demo.** Generate on a deprecated package → read the plan, then the right-hand pane: "every claim checkable against the exact retrieved text — and when retrieval is weak it says 'insufficient information' instead of inventing."

### Phase 9 — Retention guards, downloads, hardening

**Objective.** Destructive edges guarded, reports exportable, security audited end-to-end.

**Backend.** Rescan confirm: `POST /scan/` when the latest scan has ≥1 report → 409 `confirm_required` + `{reports_count}`; proceeds with `{confirm:true}` (value-based guard — no cooldown timers). Downloads: `fmt=md` (templated summary + fixes + citations + confidence note) | `fmt=json` (§5.8 fixes payload); filenames `repovitals_{repo}_{type}_{scan}.{md|json}`. `cleanup_chroma`: drop collections whose scan is gone or whose reports all persisted. Hardening sweep: BOLA suite completed across every route; DRF throttles on auth + generation endpoints; structured logging (request id, user id, scan id) with **assertions that no token/secret appears in logs**; grep-audit that no GitHub write call exists anywhere; admin read-only for research tables; error taxonomy appended to `docs/decisions.md`.

**Frontend.** Rescan ConfirmDialog: "This scan has N generated report(s); rescanning will clear them and require new LLM calls to regenerate — continue?"; download buttons; polish pass (skeletons, empty states, toasts).

**Commits.** 1 `feat(scanning): rescan confirmation guarded by report count` · 2 `feat(reports): markdown + json downloads` · 3 `feat(research): cleanup_chroma orphan sweep` · 4 `chore(security): full bola suite, throttles, structured logging, no-write-call audit` · 5 `feat(frontend): rescan confirm dialog, downloads, states polish` · 6 `test(guards): confirm matrix, download auth, cleanup idempotency`

**Acceptance.** Rescan with reports blocks until confirmed, then old reports gone, history + traces intact; JSON validates against §5.8; BOLA: every route × foreign user → 404, no exceptions; logs clean.

**Mentor demo.** Download both formats ("the JSON is a task list for a coding agent — we suggest, never apply") → attempt rescan → the guard explains what it would destroy.

### Phase 10 — Projects + trends

**Objective.** Group sibling repos, surface the one verifiable cross-repo signal plus an honest scope disclaimer, and chart accumulated history.

**Backend.** `Project` model; creation requires ≥2 repo ids, all owned by the requester (cross-user membership structurally impossible — otherwise the sibling notice would leak another user's private dependency list). Delete semantics: deleting a repo in a multi-repo project → 409 `project_cascade_confirm` + counts; confirm deletes **all** member repos (normal operational cascades) + the project row (a project cannot shrink to one member); history/traces persist. Report context at generation time for project members: computed sibling shared-dependency lines (same package in a sibling's latest scan, same-owner data only) + a static one-sentence disclaimer that integration-level risks (API contracts, shared data formats, auth/session behavior, timing) exist and are not assessed — stored into `project_context_json`; independent repos get neither. History endpoint: `data_source='live_scan'` rows only (backfill must never pollute the product chart).

**Frontend.** ProjectsPage; dashboard grouping; TrendChart (score line, classification band coloring, formula-version change markers); project-aware delete ConfirmDialog ("This repo is part of Project X with N other repo(s); deleting it will remove all N+1 repos in this project — continue?"); reports render sibling notices + the quiet disclaimer.

**Commits.** 1 `feat(projects): model + owned-membership creation rules` · 2 `feat(projects): cascade delete-with-confirm semantics` · 3 `feat(reports): sibling shared-dependency notice + scope disclaimer` · 4 `feat(backend): scan history endpoint (live rows only)` · 5 `feat(frontend): projects page, grouped dashboard, trend chart, cascade confirm` · 6 `test(projects): ownership, cascade matrix, sibling-notice correctness, history filtering`

**Acceptance.** Cannot create a project with a foreign or single repo; delete-one → confirm → all members + project gone, history intact; sibling notice appears exactly when warranted; trend chart shows movement across rescans; zero backfill rows in it.

**Mentor demo.** Group 3 repos → a report that names the shared risky package in the sibling — and in the same breath states what it *cannot* see. "Honest scope is a feature."

### Phase 11 — Research I: corpus builder + backfill engine `needs: PAT` `enables: WP-4, WP-5, WP-10`

**Objective.** The two engines that create S1/S2's dataset: a reproducible ~1,000-repo sampling frame, and monthly reconstructed risk history over 5 years. Code here; execution is File B. **All commands here run against the research DB (D8) and never write operational tables (D10).**

**Backend (`research/`).**
- `build_corpus` (D14): config-YAML grid — language {JS/TS, Python} × stars {5–20, 21–50, 51–200, 201–1000, 1000+} × pushed {<6 mo, 6–18, 18–48, >48 mo} × created-year bands; qualifiers `fork:false archived:false`. Enumerate each cell's `total_count`; auto-split star bands while > 1,000 (Search API hard cap); seeded random sample per cell with **deliberate oversampling of stale cells**, sampling weights recorded per admitted repo; paced ≤ 30 search req/min. Verification per candidate: one tree call → supported manifest present; ≥1 registry-resolvable dependency; **dependency-set hash dedup** (sorted dependency names) against the admitted set — the automated near-duplicate/boilerplate control; not-fork/not-archived via qualifiers. ~50% admission expected; oversample candidates. Outputs: `corpus_manifest.json` (full_name, github id, cell, sampling weight, manifest paths + blob shas, checks, seed, grid config, timestamp), manifest blobs archived under `research_data/corpus/`, `strata_report.md`. Checkpointed, resumable.
- `backfill` (D10/D14): per repo — commit history per manifest path (paginated) → blob per distinct sha → parse via the same adapters → monthly grid (60 months or since repo creation): manifest state = last change ≤ month-end → **as-of signal reconstruction**: one OSV package-level query per package (all vulns, cached), affected-version matching + `published_at ≤ snapshot` filtering done offline per month; staleness/versions-behind from registry publish dates ≤ snapshot (one registry doc per package, reused across months); **deprecation/yanked treated as time-invariant (known-now)** — registries don't timestamp it; recorded limitation: S2's primary datable event is CVE disclosure. Score under the active weights → write `scan_history` + `dependency_history` rows only (`data_source='backfill'`, `snapshot_date`, `sampling_weight`, formula version; all occurrences incl. clean). Checkpoint JSONL per repo; `--resume`; `--repo owner/name` single mode; rate-budget guard.
- `backfill_validate` (WP-10): input = cohort tracker + a **live-scan export file from prod** (produced by `export_research_data`, handed over by the developer); compares backfill-reconstructed recent months vs actual live scans: score-delta distribution, classification agreement (Cohen's kappa), per-signal diff attribution → md report. This is what turns backfill from shortcut into validated method.
- `plot_history`: score-over-time PNG for one repo (demo artifact).

**Commits.** 1 `feat(research): partitioned sampling frame with auto-split, seeding, stale oversampling` · 2 `feat(research): candidate verification with dep-set-hash dedup + manifest snapshotting` · 3 `feat(research): backfill manifest-history walk + as-of signal reconstruction` · 4 `feat(research): backfill monthly scoring into research tables with data_source + sampling weights` · 5 `feat(research): backfill_validate agreement report + plot_history` · 6 `test(research): grid splitting, dedup, as-of cve filtering, resume, no-operational-writes assertion`

**Acceptance.** 20-repo pilot corpus end-to-end with sane strata report; single-repo 5-year backfill < 5 min with a plausible curve — verify one cliff by hand against a real CVE's OSV `published` date; kill −9 mid-run → `--resume` completes without duplicate rows; zero writes to operational tables (asserted); product trend endpoint still shows only live rows.

**Mentor demo.** Live single-repo backfill → the 5-year curve → point at a cliff: "that's the CVE's disclosure date. Three months of project time, five years of data — and WP-10 validates the reconstruction against reality."

### Phase 12 — Research II: S1 validation harness + weights v2 `GATES: WP-2…WP-6` `optional: NVD key`

**Objective.** Everything S1 needs to go from AHP matrices to a validated `weights_v2.yaml`, at corpus scale (n≈1,000) with the anchor set as sanity floor. Code-complete first (against the WP-5 dump loaded locally); acceptance lands on WP-6 sign-off.

**Backend (`research/validation/`).**
- `ahp.py`: matrix CSV → principal eigenvector, λ_max, CI, CR (Random Index table n=3–7: 0.58, 0.90, 1.12, 1.24, 1.32); **reject CR ≥ 0.10 with a report naming the most-inconsistent judgment triads** (actionable revisit); reconciliation helper: cell-wise divergence report between two matrices + geometric-mean merge.
- `entropy.py`: Shannon-entropy weights from the corpus's normalized signal matrix (backfill `dependency_history`); comparison vs AHP vector (cosine similarity + rank order). At n≈1,000 the variance estimates behind entropy weights are stable — the whole reason the cross-check is run at corpus scale rather than n=40.
- `reference.py`: deps.dev client → OpenSSF Scorecard score per corpus repo (independent reference, D12; ~1,000 calls, free); OSV severity rollup computed alongside with its circularity stated in the output.
- `agree.py`: Pearson + Spearman vs both references (with CIs); 3-class confusion + Cohen's kappa (reference bucketed by tertiles; bucketing-choice sensitivity reported).
- `sensitivity.py`: ±10–20% per-weight perturbation (renormalized), **both** vectors, plus `rollup.decay`, `max_terms`, and thresholds ±5 → bucket-flip counts/rates.
- `anchors.py` + `scan_anchors` command: research-side current-state scan of the WP-2 CSV (fetch manifests with PAT → signals → score; **no product registration**) → assert known-bad anchors ≥ Medium; outlier report.
- `report.py` → `research_data/validation_report/` (report.md + correlation scatter, weight-comparison chart, sensitivity table, confusion matrices as PNG/CSV). `validate_formula` orchestrates end-to-end.
- EPSS (flag-gated, D3): FIRST.org client (batch by CVE id) filling `epss_score`; formula-inert unless a weights file enables it.
- On WP-6 sign-off: commit `weights_v2.yaml`, set `WEIGHTS_VERSION=v2` (prod scans now score under v2; per-row version tags keep mixed-era analysis clean); `rescore --weights v2` materializes the re-scored corpus panel to `research_data/exports/` — **no history-row mutation** (D6).

**Commits.** 1 `feat(validation): ahp eigenvector + consistency ratio with inconsistency-triad report` · 2 `feat(validation): entropy weights from corpus + ahp comparison` · 3 `feat(validation): deps.dev independent reference + osv rollup reference` · 4 `feat(validation): correlation, kappa, confusion, dual-vector sensitivity incl. rollup + thresholds` · 5 `feat(validation): anchor research-side scans + report generator + validate_formula orchestrator` · 6 `feat(scoring): epss client + flag-gated collection` · 7 `chore(weights): weights_v2 adoption + materialized corpus rescore` *(post WP-6)* · 8 `test(validation): textbook ahp fixture, cr gate, entropy on synthetic data, flip counting`

**Acceptance.** `ahp.py` reproduces a textbook AHP example exactly; CR gate demonstrably blocks an inconsistent matrix and names the worst triads; `validate_formula` runs end-to-end on the WP-5 data in one command; anchors pass; v1-vs-v2 spot-check: same stored signals differ only per weight deltas; corpus rescore completes fully offline (network assertion).

**Mentor demo.** Open `validation_report/`: "subjective weights (AHP, CR passing) vs objective weights (entropy from 1,000 repos); classifications survive ±20% perturbation at N% flip rate; correlation against an *independent* reference, not our own inputs. This folder is study S1's results section, generated by one command."

### Phase 13 — Research III: S3 experiment harness `needs: Gemini key` `enables: WP-8, WP-9`

**Objective.** The full S3 apparatus: automated ground truth, three conditions (+ one internal), deterministic correctness metric, cross-provider judge with a human-validation loop, checkpointed runners, analysis tables. After this phase S3 is data collection + analysis only.

**Backend (`research/experiment/`).**
- `groundtruth.py` (D15): over corpus (research DB) + cohort flagged dependencies — `cve_fix` cases: target = minimum fixed version > resolved, from OSV ranges; `deprecation_replacement` cases: successor parsed from deprecation text ("use X instead", "replaced by X", "migrate to X"), **registry-verified to exist**; unextractable → dropped with the rate reported (an honest denominator). `extract_ground_truth` → `labelled_set.jsonl`; stratified sampler: 150 items, 75/75 npm/PyPI, case-type quotas recorded (PyPI's replacement stratum will be thin — that asymmetry is itself a finding, and the cve_fix stratum is the controlled head-to-head).
- `conditions.py`: **A** no-retrieval (same task prompt, no chunks); **B** changelog-RAG, fixed framing (no branch); **C** full branching agent (= the production graph code). **D (internal, D13):** issue/discussion retrieval via `issue_search.py` (GitHub search → same chunk/embed/retrieve path), management-command-only, provably unreachable via HTTP (route-table test). **The runner drives the same graph components against experiment items without any operational scan** — Chroma collection keyed by run id, context built from `labelled_set` signals, so corpus items don't need product registrations.
- `runner.py` (`run_experiment --condition A|B|C|D --items … --resume`): per item stores generation, retrieved chunks, branch, timings, model ids → `research_data/runs/{run_id}/items.jsonl`; checkpointed; Groq/Gemini pacing with clean stop at daily caps (multi-day runs are normal).
- `metrics.py`: **correctness = deterministic, no LLM** — recommended version satisfies the ground-truth fixed range (PEP 440 / semver) or replacement name matches; **faithfulness** = Gemini judge, claim-level rubric → {faithful, minor_unsupported, major_unsupported}, cached by (item, condition, judge-version); **retrieval precision@k** = judge chunk-relevance (B/C/D).
- `judge_validation_packet` (WP-9): stratified 50 generations, judge verdicts hidden, rubric attached; `judge_validation_kappa`: labels in → Cohen's kappa + disagreement listing.
- `analyze_experiment`: tables (correctness / faithfulness / precision@k) × condition × ecosystem × case-type; paired tests (McNemar for binary correctness, Wilcoxon signed-rank for ordinal faithfulness) → md/csv. Null results render as first-class outputs — the harness has no thumb on the scale.

**Commits.** 1 `feat(experiment): ground-truth extraction with registry-verified successors + stratified sampler` · 2 `feat(experiment): conditions A/B/C + internal command-only condition D` · 3 `feat(experiment): scan-independent graph driver keyed by run id` · 4 `feat(experiment): checkpointed paced runner` · 5 `feat(experiment): deterministic correctness + gemini judge with caching + precision@k` · 6 `feat(experiment): judge validation packet + kappa ingest` · 7 `feat(experiment): analysis tables with paired stats` · 8 `test(experiment): version-satisfaction matrix, successor parsing, resume, judge cache, stratification, route-unreachability of D`

**Acceptance.** Extraction coverage rate reported over a corpus sample and yields ≥150 candidates (shortfall flagged early, sampler documents it); **pilot: 20 items × A/B/C end-to-end** with pacing; resumable after a mid-run kill; judge cache hits on re-run; analysis renders from the pilot; D runs from the command line and is unreachable via HTTP; correctness fixture matrix passes.

**Mentor demo.** The pilot table: same 20 dependencies, three pipelines, correctness + faithfulness side by side, split by ecosystem. "The full run is 150 items and a few days of free-tier pacing — the machinery is done."

### Phase 14 — Replication package, final hardening, v1.0 `GATES: WP-8, WP-9`

**Objective.** A stranger can reproduce the system and studies; seminars run from a script; the repo is `v1.0.0`.

**Work.**
- `export_research_data`: parquet/CSV dumps — `exports/scan_history.parquet`, `exports/dependency_history.parquet`, `exports/agent_traces.parquet`, `exports/live_scans_cohort.parquet` (prod), plus corpus manifest, weights files, run outputs; File B deliverables archived under `research_data/deliverables/` as received. These filenames are the interface File C consumes.
- `notebooks/`: `13_1_analysis` (runs → condition tables, paired tests), `13_2_markov_hazard` (transition matrix from backfill panel; hazard scaffold over dependency covariates; WP-10 section), `13_3_validation` (renders Phase 12 report data). Scaffolded and runnable against the exports.
- `REPLICATION.md`: pinned versions (Python/Node + lockfiles committed; `GROQ_MODEL`/`JUDGE_MODEL` ids; embed model), seeds, corpus grid config + timestamp, weights lineage v0→v1→v2, run ids, regeneration instructions for every table/figure, and the limitations that must travel with the data (deprecation time-invariance; judge kappa; PyPI weight lineage; reconstruction caveat).
- Final sweeps: dependency freeze; security checklist re-run (§11); prod smoke checklist; README (fresh clone → running dev env < 30 min); `docs/demo_script.md` — 10-minute flow: login → register live → score → drill-down → PyPI proof → cited remediation → trend → backfill curve → validation report → pilot table. Tag `v1.0.0`.

**Commits.** 1 `feat(research): export_research_data dumps` · 2 `feat(notebooks): S1/S2/S3 analysis scaffolds over exports` · 3 `docs: replication.md with pins, seeds, lineage, limitations` · 4 `chore: dependency freeze, security re-sweep, prod smoke checklist` · 5 `docs: readme + 10-minute demo script` · 6 `chore(release): v1.0.0`

**Acceptance.** Fresh clone → dev env < 30 min from README alone; exports regenerate every notebook table; demo script runs on prod without improvisation; WP-8 outputs + WP-9 kappa present; all 15 tags exist.

**Handoff state — the plan's whole point:** remaining work is exclusively File B's outstanding runs and File C. Zero further engineering.

---

## 11. Security checklist → phase map

| Risk | Built | Verified |
|---|---|---|
| SSRF via repo URL | 2 | allowlist client is the only outbound path; parse-then-discard; tests |
| BOLA (direct API access to others' resources) | 2→9 | structural mixin + suite covering every route by Phase 9 |
| OAuth token exposure | 1 | Fernet at rest; transient decrypt; log assertions; **no write call anywhere** (grep-audit Phase 9); DB dump alone yields ciphertext |
| Rate-limit exhaustion | 3, 11 | batching, backoff, background-only scans, research checkpointing |
| Duplicate/concurrent scans & generations | 3, 7, 8 | per-resource server-side locks + disabled UI |
| Manifest parsing abuse | 3, 6 | size caps, try/except, nothing fetched ever executed (setup.py AST-only) |
| Monorepo blind spots | 2, 3 | recursive full-tree search in validation and scan |
| Git Trees truncation | 2 | accepted, documented (demo scale never hits ~100k entries) |
| Prompt injection via retrieved text | 7, 8 | retrieved content framed as reference data, never instructions; agent has no write action; issue-search never user-reachable (D13, route test) |
| Chroma version-tag mismatch / concurrent writes | 8 | resolved-version discipline both sides; get_or_create; per-scan write lock |
| Non-determinism in a trust tool | 4, 7, 8 | temp 0 + rule-based scoring + determinism suite |
| Research tables outliving deletions | 4 | by design (D9); manual anonymization path documented |
| Unbounded agent cost | 8 | single pass, fixed tools, one generation — bounded by construction |
| Research data volume vs prod | 11 | research DB separation (D8); no-operational-writes assertion |

## 12. Out-of-scope guard (do not build)

Confidence-retry loop; live issue-search branch (D stays command-only pending an explicit threat-model extension and S3 results); TTL registry/document caching; code-aware remediation (call-site analysis); package-level embedding cache; dashboard sort/filter; auto-PRs or any write to user repos; webhooks/continuous scanning; Celery/Redis; GitHub-App migration; repo-picker dropdown UI. All deliberately deferred. Note ideas in `docs/decisions.md` instead of building them.

## 13. What comes after

When Phase 14 tags `v1.0.0` and File B's WP-8/WP-9 are in: open File C. It consumes exactly the artifacts named in Phase 14's export list and File B's deliverable registry, and defines the three studies end-to-end through submission.
