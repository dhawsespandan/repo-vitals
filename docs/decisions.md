# Decision log

A running ADR log, seeded with the locked decisions D1–D17 from the
implementation plan (`plan/repo_vitals_implementation_plan.md` §1). Those are
not restated here — read them there. This file records **refinements made
during the build**: choices the plan left open, places where an implementation
detail turned out to matter, and ideas deliberately *not* built (§12 says to
note them here rather than build them).

Append, never rewrite. One entry per decision, newest phase last.

---

## Phase 1 — Foundations

### 1.1 `AbstractBaseUser`, not a bare model

**Context.** §5.1 specifies `app_users` with no password column — identity is
GitHub's.

**Decision.** `accounts.User` still subclasses Django's `AbstractBaseUser`.

**Why.** Django's session machinery calls `get_session_auth_hash()`, which
`AbstractBaseUser` provides and which is derived from the password field. A
model without it would need that plumbing reimplemented by hand for no gain.
The inherited `password` column exists and is always set unusable; no code path
can set one. `AbstractBaseUser.last_login` is re-declared onto the spec's
`last_login_at` column so there is exactly one "last sign-in" field rather than
a Django one and a spec one side by side.

`django.contrib.admin` is deliberately **not** installed: it would need a
password-based login path into a product that has none.

### 1.2 UUID primary keys default in Python, not in Postgres

**Context.** §5.1 says PKs are `UUID gen_random_uuid()`.

**Decision.** `models.UUIDField(primary_key=True, default=uuid.uuid4)`.

**Why.** Identical semantics for every write that goes through the ORM, with
no dependency on a database function. Research tooling that bulk-loads rows
outside the ORM (Phase 11) can still call `gen_random_uuid()` server-side.

### 1.3 The OAuth routes are wired explicitly, not by `include(allauth.urls)`

**Decision.** `config/urls.py` mounts allauth's `OAuth2LoginView` and
`OAuth2CallbackView` at the two paths §5.5 specifies, and includes nothing
else from allauth.

**Why.** Two reasons. The callback path §5.5 specifies is
`/api/auth/github/callback/`, whereas `include(allauth.urls)` produces
`.../login/callback/`. And allauth's URLconf brings a signup form, password
reset, email management and logout pages — a whole HTML surface for flows this
product does not have. Wiring the two views by hand keeps the URLconf equal to
the API surface.

The url **names** (`github_login`, `github_callback`) must not change: allauth
reverses `github_callback` to build the `redirect_uri` it sends to GitHub.

### 1.4 Granted OAuth scopes are captured off the token response

**Decision.** `RepoVitalsGitHubOAuth2Adapter.parse_token()` carries GitHub's
`scope` string through to the login signal on the in-memory token object.

**Why.** §5.1 stores `token_scopes`, but allauth's base `parse_token()` keeps
only the access token and drops the rest of the response. GitHub can grant
fewer scopes than were requested; recording what we actually hold is what lets
a later phase say "this repository needs the `repo` scope, which you did not
grant" instead of returning a mystifying 404.

### 1.5 Log redaction is a filter, not a convention

**Decision.** `apps/common/logging.py::RedactSecretsFilter` is attached to the
console handler and scrubs GitHub token shapes and Fernet ciphertext from every
record.

**Why.** §11 lists "no token substring in logs" as a Phase 1 verification.
Relying on every future call site to remember is not a control. The filter is,
and it is covered by `tests/test_log_redaction.py`.

### 1.6 The session endpoint returns 200 for anonymous visitors

**Decision.** `GET /api/auth/session/` answers `{"authenticated": false,
"user": null}` with HTTP 200 rather than 401.

**Why.** The SPA calls it once on every cold load to decide which screen to
render. "Nobody is signed in" is a normal answer to that question, not a
failure; modelling it as a 401 makes every signed-out page load look like an
error in the console and in the client's error handling.

### 1.7 Back-navigation guard: a routing rule, not a `popstate` listener

**Context.** Phase 1 requires that back-navigation can never log a user out or
expose the login screen.

**Decision.** The `/login` route refuses to render for an authenticated user.
It redirects to the last in-app path, carrying a router-state flag that opens
the sign-out confirmation. The login screen renders only once the session is
actually gone — which happens only on explicit confirm.

**Why.** The obvious implementation — listen for `popstate`, then
`history.pushState` back — leaves React Router's idea of the location out of
step with the address bar, and still lets the login screen paint for a frame.
Making it a rule about what a route may render covers the back gesture, a typed
URL and a restored tab with one mechanism, and it is testable without
simulating browser history.

### 1.8 Tailwind v3 with `tailwind.config.js`

**Decision.** Tailwind 3.4 rather than v4's CSS-first configuration.

**Why.** §3's file layout names `tailwind.config.js`. The look comes from
`frontend/src/styles/industry.css` — lifted verbatim from the approved
wireframe, which is the binding visual spec — and Tailwind is only a utility
layer over it, so there is nothing to gain from the newer configuration model
and a plan-layout mismatch to lose. `industry.css` is imported *after*
`index.css` in `main.tsx` so its rules win over Tailwind's preflight reset;
an `@import` inside `index.css` cannot achieve that, because CSS requires
imports to precede other rules.

### 1.9 fastembed is installed from Phase 1, unused until Phase 8

**Decision.** `fastembed` is in `requirements.txt` now.

**Why.** The memory smoke test (§10 Phase 1) exists to answer a real 512 MB
feasibility question in week one, and it can only answer it by loading the
model the production worker will actually hold. `manage.py smoke_memory
--skip-embedding` degrades gracefully when it is absent.

### 1.10 Not built (§12 watch-list)

Noted, deliberately absent, do not add without an explicit decision here:
CORS middleware and JWTs (the Vercel rewrite makes every call same-site);
`django.contrib.admin`; a TTL cache in front of any registry; any outbound
HTTP client other than the one `common/http.py` will introduce in Phase 2.

### 1.12 Repo registration is restricted to the user's own namespace or public repos — binding for Phase 2

**Context.** GitHub OAuth Apps grant the `repo` scope as all-or-nothing: the
resulting token can technically reach every repository the account can see,
including ones owned by an organization the user belongs to (e.g. an
employer). There is no OAuth scope that filters by ownership, and per-repo
consent only exists on GitHub's separate "GitHub App" mechanism, which §12
already defers as future work.

**Decision.** Phase 2's pre-scan validation (§5.6) gets one additional
ordered check, run alongside the existing four: reject registration if the
repository is private **and** its owner is not the authenticated user's own
account (`repository.owner.login != user.github_username`). Public repos and
repos in the user's personal namespace pass; anything owned by an
organization — regardless of whether the token can technically reach it — is
rejected before any scan work or GitHub quota is spent on it.

**Why.** The token's technical reach can't be narrowed at the GitHub layer,
but Repo Vitals' own behavior can be. This guarantees the application itself
never calls the API for, stores data about, or scans an organization-owned
repository, which is what actually matters for a user whose account is also a
member of an employer's org. It costs one extra condition in a validation
function Phase 2 already needs to write — not a separate effort.

**Operationally verified today:** during OAuth authorization, GitHub shows a
separate "Organization access" row per org the account belongs to, each with
its own Grant/Request button, independent of the main "Authorize" action.
Declining to click an org's Request button means GitHub never notifies that
org or its admins — confirmed live against two real orgs on the developer's
account. This Phase 2 rule is the code-level backstop for the case where an
org's OAuth restrictions are off and access would otherwise be silent.

### 1.13 Memory smoke test result — the feasibility question is answered

`manage.py smoke_memory` records worker RSS at four points plus the peak.
Run on the real Render free instance (512 MB) by temporarily appending it to
the build command (Shell access requires the paid Starter plan, so this was
the only way to reach the live container) and reading the output from the
deploy log.

| Environment | Date | Baseline | After request | After thread | After model load | After embedding | Peak |
|---|---|---|---|---|---|---|---|
| Render free (prod) | 2026-08-27 | 70.2 MB | 84.1 MB | 86.3 MB | 270.7 MB | 274.5 MB | **274.5 MB / 512 MB (54%)** |

**Verdict: comfortably within budget.** The jump from 86.3 MB to 270.7 MB —
loading the fastembed ONNX model — is D7's whole justification, and it costs
~185 MB, not the 700 MB+ torch would have. There is ~237 MB of headroom left
for everything Phases 3–9 add (connection pool growth, Chroma, request
handling under load), which is enough margin that memory is not expected to
be a blocker again before Phase 8 re-verifies with Chroma loaded (§8).

**Bug found and fixed by this run.** The "request cycle" step used Django's
test `Client()`, which defaults to `Host: testserver` — prod's strict
`ALLOWED_HOSTS` correctly rejected that with a 400 before the view ever ran,
so that step measured almost nothing. Fixed by pointing the test client's
`SERVER_NAME` at whatever host `ALLOWED_HOSTS` actually accepts. Did not
warrant a second production run: the measurement that step was missing is
small relative to the embedding step that dominates the peak.

### 1.14 GitHub's OAuth callback must be built from FRONTEND_URL, not the request

**Context.** Production login testing (backend on Render, frontend on
Vercel, `/api/*` proxied between them per §2) failed with allauth's callback
view reporting a bare `error="unknown"`, no exception. The cause: allauth's
default `get_callback_url()` builds the redirect URI GitHub is sent from
`request.build_absolute_uri()` — i.e. the backend's own real hostname
(`repo-vitals.onrender.com`). Login was initiated through the Vercel-proxied
`/api/auth/github/login/`, so the browser scoped the session cookie holding
the OAuth `state` to the Vercel domain. GitHub's redirect back then landed
the browser directly on the Render domain — a different origin entirely, no
shared cookie possible regardless of `SameSite` — so the stashed state could
never be found on the way back.

Locally this went unnoticed: Vite's dev proxy (with `changeOrigin: false`)
and the dev backend both resolve to the hostname `localhost` (only the port
differs, and cookies are not port-scoped per RFC 6265), so the cookie stayed
visible across the whole round trip by coincidence, not by design.

**Decision.** `RepoVitalsGitHubOAuth2Adapter.get_callback_url()` (§`apps/accounts/oauth.py`)
is overridden to build the callback URL from `settings.FRONTEND_URL` plus the
reversed callback path, ignoring the request's own host entirely. This keeps
the whole OAuth round trip — login, GitHub, and the return — on one
browser-visible origin, exactly as §2 already intends for every other API
call. The registered "Authorization callback URL" on **both** GitHub OAuth
Apps (dev and prod) must point at the **frontend's** origin
(`http://localhost:5173/api/auth/github/callback/` and
`https://<vercel-app>.vercel.app/api/auth/github/callback/`), not the
backend's — `.env.example` and the README were updated to match.

**Why.** This is the architecturally correct fix, not a workaround: §2's
same-site design is what lets the whole app run without CORS or JWTs, and
this closes the one gap where that design wasn't actually being honored — the
external redirect leg was quietly falling back to a different-origin URL.
Also fixed alongside: the adapter's error hook (`authentication_error`) was
using the wrong, non-existent allauth API (`respond_error`/
`get_error_redirect` are not real hooks) and silently swallowed every OAuth
failure into allauth's own generic HTML page instead of the SPA's login
screen; it now raises `ImmediateHttpResponse` — the documented mechanism —
and logs the real `error`/`exception` allauth passes, which is what surfaced
this bug's true cause instead of a dead end.

**Follow-up (same day): §1.14's adapter fix alone was incomplete.** Deployed,
verified against the real `SOCIALACCOUNT_PROVIDERS["github"]["APPS"]` config,
and the *login* endpoint (`/api/auth/github/login/`) still sent GitHub the
backend's own hostname — the callback-URL bug was still live for the one
request a real browser hits first.

**Root cause.** allauth's callback view and its login view build the
redirect URL through two entirely different code paths, and only one of them
goes through the adapter class wired in `urls.py`:

- `OAuth2CallbackView` is instantiated directly with
  `RepoVitalsGitHubOAuth2Adapter` (`OAuth2CallbackView.adapter_view(...)`),
  so `get_callback_url()` was correctly overridden there.
- `OAuth2LoginView` delegates to `provider.redirect_from_request()`, and the
  *provider* — `GitHubProvider`, from allauth's own `github/provider.py` —
  hardcodes `oauth2_adapter_class = GitHubOAuth2Adapter` (the stock class).
  Nothing about registering our adapter on the login view reaches this;
  the provider instantiates its own hardcoded adapter class independently.

So the earlier fix was real and necessary but not sufficient: an
adapter-level unit test asserting `get_callback_url()`'s return value passed
cleanly, while the actual `/api/auth/github/login/` endpoint remained broken
— the unit test exercised a code path a real request doesn't take.

**Decision.** Added `RepoVitalsGitHubProvider(GitHubProvider)` with
`oauth2_adapter_class = RepoVitalsGitHubOAuth2Adapter`, registered via
allauth's own documented override point:
`SOCIALACCOUNT_PROVIDERS["github"]["provider_class"]` (see
`allauth/socialaccount/providers/registry.py::ProviderRegistry.load()`,
which reads exactly this key before falling back to a provider module's
default `provider_classes` list). No new Django app or URL wiring needed —
this is the sanctioned extension point for exactly this situation.

**Test added at the right altitude.** `test_login_redirect_sends_github_a_frontend_scoped_callback`
hits the real `/api/auth/github/login/` endpoint through the test client and
asserts on the `Location` header, rather than calling `get_callback_url()`
directly — that is the level at which the bug was invisible to the previous
test. Verified locally end-to-end before pushing:
`redirect_uri=https%3A%2F%2Frepo-vitals-lilac.vercel.app%2F...`, not the
backend's `onrender.com` host.

**Why this is worth stating plainly:** a fix that is correct in isolation
(the adapter override) can still leave a system broken if it doesn't cover
every code path that consumes the thing being fixed. The lesson generalizes
past OAuth — test the entry point a real client hits, not just the unit
that seems like "the" place a value is computed.

### 1.15 The back-navigation guard needs a `pageshow` listener too

**Context.** Production testing of the (now-fixed) OAuth flow: after
signing in, pressing the browser's Back button landed directly on the raw
login screen — no sign-out confirmation, the exact case §10 Phase 1
requires the guard to prevent.

**Root cause.** The guard (§1.7) is a routing rule: the `/login` route
refuses to render for an authenticated user and redirects with a
confirm-logout flag. That rule only runs when React re-executes on a route
change. But the OAuth round trip is several full-page redirects (this app →
GitHub → the callback → `/dashboard`), not in-app route transitions — so
the browser's actual back-stack holds a *pre-login* `/login` page load as a
distinct history entry. Pressing Back can restore that entry straight from
the browser's back-forward cache: the frozen page reappears with **no
JavaScript re-execution at all**, including the session check the guard's
redirect logic depends on. The rule was never wrong; it simply never got a
chance to run.

**Decision.** `AuthContext` listens for the `pageshow` event and, when
`event.persisted` is true — the standard, cross-browser signal that a page
came from bfcache rather than a fresh load — forces `status` back to
`"loading"` and re-runs the session check. Routing back through `"loading"`
matters: it prevents the stale frozen page from flashing before the fresh
check resolves.

**Verification.** `frontend/src/auth/auth.test.tsx` dispatches a synthetic
`pageshow` event with `persisted: true` against a page that started
`signed-out`, while the stubbed session endpoint now reports `signed-in`
(modelling "the real session changed while this page was frozen") and
asserts the stale UI is replaced. A companion test confirms an *ordinary*
`pageshow` (`persisted: false`) triggers no extra check. Real
back-forward-cache restoration was not reproduced in the local automation —
that needs a genuine browser back-gesture — so this was verified by the
user's actual back button in production after deploying the fix.

**Why this is worth stating plainly, again:** this is the same shape of
lesson as §1.14 — a component that is correct in isolation (the routing
rule) can still fail if a browser mechanism bypasses the assumption it
relies on (that React re-runs on every "page"). bfcache is exactly this kind
of easy-to-miss mechanism for any client-side auth guard.

### 1.16 `smoke_memory` lives in `accounts`, not `research` — §3 layout deviation

**Context.** §3's monorepo layout lists `smoke_memory.py` under
`apps/research/management/commands/`. It currently lives in
`apps/accounts/management/commands/`.

**Decision.** Leave it in `accounts` for now; move it to `research` when
that app is actually created in Phase 11.

**Why.** `apps/research/` does not exist until Phase 11, and §3 describes it
as "never imported by request-handling code". Creating the whole package in
Phase 1 to host one command would mean carrying an otherwise-empty app in
`INSTALLED_APPS` for ten phases, which is worse than a documented
one-command deviation. The command is also genuinely not research code in
Phase 1 — it exists to answer a deployment feasibility question about the
production worker (§1.13), which is an operations concern, and it exercises
the login path that `accounts` owns.

**How to apply:** when Phase 11 creates `apps/research/`, move this command
there and delete this note. Until then, `manage.py smoke_memory` is the
command's stable public name regardless of which app hosts it, so nothing
downstream depends on the location.

### 1.17 The keepalive cron does not keep Render awake — only Supabase alive

**Context.** §4.2 and §8 both treat one `*/10` GitHub Actions cron as the
answer to two separate free-tier timers: Render's 15-minute sleep and
Supabase's ~7-day pause. Phase 1's acceptance criterion ("keepalive history
shows health 200s") passes — every run since the workflow was correctly
configured has succeeded.

**Read the run history with this caveat.** Of the 46 runs on record
(2026-08-25 → 2026-08-30), **34 are failures and 12 are successes** — the
Actions tab is roughly three-quarters red, which looks alarming and isn't.
Every failure predates `2026-08-27T03:23Z`; the first success is
`2026-08-27T10:01Z` and all 12 runs since are green. The cause is mundane:
the workflow hard-fails by design when the `RENDER_HEALTH_URL` repository
variable is unset (see its own guard clause), and that variable did not
exist until the backend was first deployed on 2026-08-27. The red band is
the pre-deployment period, not a fault in the workflow.

**The stated cadence is not real.** GitHub heavily throttles scheduled
workflows; `*/10` is a request, not a guarantee. Measured 2026-08-30:

| Sample | n | min gap | max gap | mean gap |
|---|---|---|---|---|
| Successful runs (post-deployment, the meaningful set) | 12 | 2.05 h | 10.86 h | 5.75 h |
| All 46 runs (mixes in the pre-deployment failures) | 46 | 0.33 h | 10.86 h | 2.31 h |

**Cite the first row, not the second.** The all-runs range dips to 20
minutes only because GitHub scheduled a freshly-created repository more
generously during the period when every run was failing anyway; those ticks
did not ping anything. The honest figure for what the keepalive actually
achieves is **2–11 hours between successful pings, averaging ~5.75 h**.

If anything the wider spread strengthens the conclusion: the cadence is not
merely slow, it is *unpredictable* across two orders of magnitude, so it
cannot be relied on in either direction — not to keep a service warm, and
not to be counted on as a heartbeat with any particular period.

**Consequence, split by purpose:**

| Timer | Window | Actual cadence | Result |
|---|---|---|---|
| Supabase pause | ~7 days | 2–11 h | **solved** — comfortably inside |
| Render sleep | 15 min | 2–11 h | **not solved** — asleep most of every gap |

So a first click on the live URL still pays the ~50 s cold start, which is
precisely the mentor-demo failure §4.2 wanted to avoid. The plan's §8 answer
for the Render row is, in practice, not satisfied by this mechanism.

**Decision.** Keep the workflow — it genuinely solves the Supabase half and
costs nothing — and record honestly that it does not solve the Render half.
Keeping Render awake needs an off-GitHub pinger (UptimeRobot, cron-job.org,
or similar free service) aimed at the same `/api/health/` URL. That is a
hosting-account action rather than a code change, so it is **outstanding
work for the developer**, not something this repository can assert.

**Rejected alternatives**, both of which would look like fixes and aren't:
lowering the cron interval (GitHub throttles regardless of what is asked
for), and having the job sleep-and-repeat inside a single run (burns Actions
minutes to impersonate a service purpose-built for this, and still stops
whenever the run ends).

**Free-tier note — corrected 2026-08-30.** An earlier version of this section
said 24/7 was comfortably within budget, citing "~730 hours in a month". That
understates it. Checked against Render's own free-tier documentation:

* the allowance is **750 instance-hours per calendar month per _workspace_**,
  not per service;
* hours are consumed only while a service is running — a spun-down service
  costs nothing;
* exhausting the allowance **suspends every free service in the workspace
  until the 1st of the next month**.

A 31-day month is 744 hours, so always-on leaves a **6-hour margin (0.8%)**,
and it only holds while this workspace hosts exactly one service. Render's
docs do not specify whether a deploy briefly runs two instances, whether
restarts count, or how hours are rounded, and they reserve the right to
restart a free service at any time. So the margin rests on undocumented
accounting, and the failure mode is a month-long outage.

**Decision: ping on a 06:00–24:00 window, not 24/7.** 18 h/day × 31 = 558
hours, a 192-hour margin that absorbs deploys and any upstream surprise
without needing to be thought about again. The 00:00–06:00 hours it gives up
are ones the commit history shows no activity in, so nothing is lost. It also
avoids permanently reserving the whole workspace for this one project.

The constraint is therefore **both** the scheduler and the budget — the
scheduler is why GitHub Actions cannot do this job, and the budget is why the
replacement is windowed rather than continuous.

**Two setup traps, both hit on the first attempt (2026-08-30).**

*Timezone.* cron-job.org schedules in **UTC** unless the job's own time zone
is changed (it is on the job's ADVANCED tab, not next to the schedule). Left
at UTC, `*/10 6-23 * * *` runs 11:30–05:29 IST — it sleeps through the 10:00
hour, which the commit history shows is the single busiest working hour of
the day. Set the job's time zone to **Asia/Kolkata** and confirm the label
under "Next executions" stops saying `(UTC)`.

*"Failed (output too large)".* Every scheduled GET failed with this, against
a 31-byte JSON body. The size is not the issue: Render fronts the service
with Cloudflare, which returns `Transfer-Encoding: chunked` and **no
`Content-Length`** — verified true regardless of `Accept`, `Accept-Encoding`
or user agent, so it is not DRF content negotiation and not a bot challenge.
A fetcher enforcing a response cap cannot pre-check an undeclared length and
aborts. The endpoint already advertises `allow: GET, HEAD, OPTIONS`, and
Django routes HEAD to the same handler, so **HEAD** still executes the
`SELECT 1` (Supabase activity preserved, 503-on-DB-failure preserved) while
returning no body for the cap to trip on. Worth knowing because the job had
"disable after too many failures" enabled: left alone it would have switched
itself off within a day or two and quietly restored the cold starts.

**After v1.0 this should get narrower, not wider.** A finished project is
opened for a demo or a review a handful of times a month; 558 hours of warmth
to serve that is poor value, and the consequence of a suspension is worst
exactly when the project is being evaluated. Narrowing the window further, or
retiring the pinger and warming the service by hand before a demo, is the
right end state.

---

## Phase 2 — Registration + pre-scan validation

### 2.1 Three outcome codes §5.6 does not list

§5.6 fixes six outcomes and calls their messages binding. Three situations
the implementation actually hits are not among them.

**`github_unavailable` (503).** §5.6 gives exactly one 503, `github_rate_limited`.
But a connection failure, a DNS problem, or a GitHub 5xx is not a rate limit.
Reusing the rate-limit code for them would mislead anyone reading logs or
metrics — "we are being throttled" is a very different operational story from
"GitHub is down" — and the difference matters as soon as Phase 3 starts
scanning on a quota budget. The **user-facing message is deliberately
identical** to `github_rate_limited`'s, because "try again in a few minutes"
is the right advice either way. So the diagnosis splits; the experience does
not.

**`private_repo_not_owned` (403).** §1.12 adds a fifth check — reject a
private repository whose owner is not the authenticated user — but §5.6's
table predates it and has no row for the outcome. The two existing 403/404
codes would both misdescribe it: `no_write_access` tells the user to go get
write access, which does not help (the rule holds regardless of their
permissions), and `repo_inaccessible` would be a plain lie about a repository
we can see perfectly well. It gets its own code and a message that states the
actual rule.

**`github_reauth_required` (401).** Found by running the finished phase
against a revoked token rather than by reading the spec. GitHub answers 401
"Bad credentials", which fell through to `github_unavailable` and told the
user to *try again in a few minutes* — advice that can never come true,
because retrying does not un-revoke a token. It is also not a rare path:
tokens die when the user removes the OAuth app, when GitHub expires them, and
whenever `TOKEN_ENCRYPTION_KEY` is rotated (§6 already anticipates that last
one with "users simply re-login"). The message now says the only thing that
actually works — sign out and sign in again — and `common/http.py` gained a
matching `UpstreamUnauthorized`, never retried, because no number of retries
fixes a credential.

**Why this is safe to do:** the frontend branches on `code`, never on message
text (§5.6, `types/index.ts`), so adding codes is additive. The six specified
codes and messages are reproduced verbatim.

### 2.2 The ownership check runs *before* the write-access check

§1.12 says its rule runs "alongside the existing four" without fixing a
position. Position turns out to be observable: a private organization
repository that the user *can* push to fails both check 3 (ownership) and
would pass check 4 (eligibility) — while a private org repo they cannot push
to fails both. Whichever runs first is the reason the user sees.

Ownership goes first. "We don't monitor other people's private repositories"
is a statement about what the product will do at all; "you need write access"
is an invitation to go and obtain write access, which in this case would
change nothing. The check that refuses outright has to be the one that
speaks, or the message sends the user off to do pointless work.

### 2.3 Manifest matching skips vendored directories

§5.6 requires matching adapter patterns *anywhere* in the recursive tree,
precisely so that split-by-functionality repositories are not missed. Taken
literally, that also matches `node_modules/**/package.json` — and a repository
with a checked-in `node_modules` would qualify as an npm project on the
strength of its vendored dependencies alone, even if it has no manifest of
its own.

Path segments naming a vendor directory (currently just `node_modules`) are
skipped. This is narrower than it looks: it excludes only manifests *inside*
such a directory, never the repository's own.

`SUPPORTED_MANIFESTS` lives in `repositories/validation.py` for now. Phase 3
introduces `scanning/adapters/` and owns the pattern registry from then on;
Phase 6 adds the PyPI filenames and, per §5.6, updates the
`ecosystem_unsupported` message to name both ecosystems.

### 2.4 Four deviations from the wireframe's register flow

`plan/wireframe.html` is the binding visual specification, so departures from
it are recorded rather than assumed.

**The "Try: eligible / unsupported / read-only / not found" chips are gone.**
They exist so someone opening the wireframe with no backend can trigger each
validation branch; they paste fabricated URLs (`github.com/ghost/missing-repo`)
that a real server can only reject. Keeping them would ship a demo device as a
product feature.

**The submit button says "Register", not "Register & scan".** Registration does
not scan until Phase 3. The wireframe is drawn against the finished product;
promising a scan the build cannot yet perform is the one change that would
make the button lie. Phase 3 restores the wireframe's label along with the
behaviour.

**Client-side validation is not reproduced.** The wireframe validates the URL
as you type, from a regex over the string. §10 Phase 2 says the server
re-parses authoritatively and §5.6 owns every message, so the field accepts
anything non-empty and the outcome comes from the API. The tone (green /
amber / red) is chosen from the returned `code`, never from the message text.
An unrecognised code renders as an error, so a code added server-side can
never appear as reassuring green.

**A duplicate is answered in the dialog, then goes to the existing card.**
§5.6's duplicate outcome says the frontend redirects to the existing
repository. There is no per-repository route until Phase 5, so the nearest
honest equivalent is to bring the row to the user. See §2.5 — the first
attempt at this was wrong in a way that only showed up on prod.

### 2.5 A duplicate has to answer where the user is looking

Reported from the first live run on prod: registering an already-registered
repository produced **no visible message at all**. Correctly, no second card
appeared — but from the user's seat the dialog simply vanished, which reads as
the form swallowing the input.

**It was not a logic bug, which is what made it easy to ship.** The duplicate
payload was recognised, `onDuplicate` ran, and the notice was set — the proof
is that a *mis*-recognised duplicate would have taken the `onRegistered` path
and added a second card, which did not happen. The message was in the DOM the
whole time. It was just placed near the top of the page, above the card grid,
while the user was scrolled down among their cards. The dialog closed, the
answer rendered off-screen, and the highlight expired after four seconds.

The frontend test passed because it asserted the dialog had closed, that only
one card existed, and that the card was highlighted — everything except
whether a human could *see* the answer. jsdom has no viewport, so "rendered
somewhere in the document" and "visible to the user" are the same thing there
and only the same thing there.

**The design error underneath:** five of the six §5.6 outcomes answer inside
the dialog. The duplicate was the only one that closed the dialog and put its
answer somewhere else. Consistency of *where the answer appears* matters more
than the wording of any individual message — an answer in an unexpected place
is functionally no answer.

**Now:** the duplicate renders in the dialog like every other outcome, in an
accent tone (it is neither a success nor a failure), and the primary button
becomes "Show me" — which closes the dialog, highlights the row, and scrolls
it into view. The scroll is the part that makes §5.6's "redirect" mean
anything before Phase 5 supplies a real route. It runs on a `setTimeout`
rather than `requestAnimationFrame` because browsers throttle frame callbacks
in undisplayed tabs, and this must not depend on frames ticking.

---

## Phase 3 — Scanner core, npm adapter, background scans

### 3.1 `WEIGHTS_VERSION` arrives a phase early, defaulting to `unscored`

§5.1 makes `scan_runs.scoring_formula_version` NOT NULL, and §6 lists
`WEIGHTS_VERSION` against Phase 4. Phase 3 creates the table and writes rows,
so it needs a value a phase before the config register expects one.

The options were to pick Phase 4's bootstrap tag (`v0_equal`) now, or to say
what is actually true. A Phase 3 scan runs no formula: `risk_score` and
`classification` are NULL, and `risk_component_score` is NULL on every
occurrence. Tagging those rows `v0_equal` would claim a formula produced them
— the sort of small untruth that becomes a real problem when the research
recomputes scores from stored signals under an explicitly chosen weights
version (D6) and finds rows attributed to a version that never touched them.

So the default is the literal string `unscored`, and Phase 4 changes the
default when `weights_v0_equal.yaml` ships. `.env.example` carries it with the
same explanation.

### 3.2 Layout additions to §3

Two files §3's tree does not list:

* **`scanning/adapters/semver.py`** — SemVer parsing, ordering and release
  distance. Not a dependency, because the two things needed here are small and
  a SemVer library's main offering is range *satisfaction* (`^1.2 ∩ >=1.4 <2`),
  which this project deliberately does not do: resolution comes from a lockfile
  or it does not happen (§10 Phase 3). Re-deriving what a package manager
  *would* have installed is exactly the guess the product exists to avoid.
  Phase 6 adds a PEP 440 equivalent beside it rather than making one function
  serve two grammars.
* **`scanning/serializers.py`** — every other app has one; §3's tree simply
  does not enumerate serializer modules for any app.

`retention.py` is named in §3 under `scanning/` and is **not** written here.
§5.7's retention deletes the prior completed scan *after* the history rows are
written, and history writes are Phase 4's. Shipping the delete first would
destroy scans with nowhere permanent for them to have gone.

### 3.3 `npm:` aliases are a documented gap, not a resolved specifier

`"my-lodash": "npm:lodash@^4"` installs a registry package under a local name.
Unlike `file:` or `git+`, it *is* assessable in principle — the registry knows
`lodash` perfectly well.

It is recorded unassessable anyway, with reason `alias_specifier`. Resolving it
means re-deriving npm's alias grammar, including `npm:@scope/pkg@1.2.3` where
the version separator is the *second* `@` and the first is part of the name.
Getting that wrong does not fail loudly: it silently attributes one package's
advisories and deprecation to another, which is worse than any number of
honest "can't assess" rows. Same shape as Phase 6's `dynamic_setup_py` (§10),
which the plan already treats as a documented gap rather than a miscount.

Worth revisiting if real repositories turn out to use aliases often. Recorded
here rather than built (§12).

### 3.4 Only npm's own lockfiles are read

`package-lock.json` and `npm-shrinkwrap.json` are JSON and are parsed.
`yarn.lock` is a bespoke format and `pnpm-lock.yaml` is YAML, which would mean
a new dependency and a new parser each.

Neither is read, so a yarn-only or pnpm-only repository resolves every row
through `range_latest_approx` — a *degraded* answer that says so on every row
(the provenance chip in the dependency table), not a wrong one. That asymmetry
is acceptable where a half-understood lockfile parse would not be: a lockfile
misread produces confident, specific, wrong versions.

Adding pnpm later costs one YAML dependency and one parser; adding yarn costs
a hand-written grammar. Neither is in Phase 3's scope.

*Superseded in part by §3.15.* This entry framed lockfile coverage as a
question of file *format*, and missed the case that actually bites: an npm
workspaces monorepo whose one lockfile sits at the root while its members
have none.

### 3.5 The three ways a scan can fail, and why they differ

A scan meets three kinds of bad news, and treating them alike would be wrong
in three different directions.

**One package the registry has never published** → that occurrence becomes
unassessable with `not_in_registry`. It is a fact about the package, it is
stable, and the row stays visible with its reason.

**The registry answering nothing at all** → the whole scan fails. Marking every
row unassessable would write a permanent claim about the packages out of a
temporary fact about the network, and the next scan would silently disagree
with this one for no reason a reader could see. The rule is deliberately
all-or-nothing rather than a percentage threshold: every lookup failing is
unambiguous evidence about the registry, where "sixty percent failed" is a
number someone would have to defend.

**OSV unreachable** → the whole scan fails, always. This one has no
one-package variant, because a missing batch answer is *indistinguishable from
"no advisories"*. Recording a partial OSV result would report a repository
clean because the vulnerability database was down, which is the single worst
output this product could produce.

### 3.6 A scan can die without finishing, so `running` has an expiry

Render restarts free instances at will (§8), and a killed process leaves a row
saying `running` with nobody running it. The per-repository lock is
in-process, so a restart also forgets it. Without a rule, that repository is
wedged behind a 409 permanently.

Any active scan older than fifteen minutes is presumed dead: it stops blocking
new work, and it is marked failed with a message saying to run it again. The
expiry runs on the **read** path as well as the trigger path — one `UPDATE`
that normally matches nothing — so the page repairs itself instead of spinning
until someone thinks to press Run scan. Fifteen minutes against an acceptance
target of under two (§10 Phase 3) is wide enough that a slow upstream is never
mistaken for a crash.

### 3.7 A guard on manifest count, and two size caps

Three limits, none of them in the plan, all of them answering §11's
"rate-limit exhaustion" row and §8's memory budget:

* **`MAX_MANIFESTS = 50`**, shallowest paths first. A repository at this
  product's scale has single figures; a tree with fifty-plus is generated or
  vendored in a way `VENDOR_DIRS` did not catch, and scanning all of it spends
  the user's GitHub quota discovering that. Sorting by depth keeps the
  repository's own root manifests ahead of anything deeply nested when the cut
  falls.
* **`MAX_MANIFEST_BYTES = 1 MiB`** — anything larger is not a `package.json`.
* **`MAX_LOCKFILE_BYTES = 6 MiB`** — lockfiles legitimately reach megabytes.
  Past the cap the manifest still scans; its rows fall back to
  `range_latest_approx` and `manifest_files.lockfile_path` is left NULL, which
  is what tells a reader why.

Both size checks run against the size the **tree** already reported, before
any fetch, so an oversized file costs nothing. What none of the three did was
*tell anyone* — see §3.16.

Blobs are read from `GET /git/blobs/{sha}` rather than the contents API. The
tree hands over the sha and the size together, and the blob endpoint's ceiling
accommodates real lockfiles where the contents API's 1 MB does not.

### 3.8 CVSS is computed from the vector, not read from a field

OSV publishes severity as a CVSS **vector string**; §5.2 needs a number.
`osv.py` transcribes the CVSS v3.1 base-score arithmetic (§8.1) and is checked
against the specification's own published worked examples.

This matters beyond tidiness. §5.2's fallback chain is OSV → NVD → a 5.0
placeholder flagged `cvss_reduced_confidence`, and it only ever reaches its
second step if the first is genuinely tried. Deriving the score here keeps the
placeholder for advisories that really carry no severity, which is a far
smaller set than "advisories whose score is not a plain number in the JSON".
Phase 5's whole purpose is to show this arithmetic to a reader, so it had
better be the specification's arithmetic.

Where an advisory also carries the publisher's own severity word
(`database_specific.severity`, which GitHub advisories do), **that** is what
`severity` stores — it is a statement by the people who analysed the
vulnerability rather than an inference from a number. Both are stored, and
§5.2's formula consumes `cvss_score`, so a disagreement changes the label a
user reads and never the arithmetic.

### 3.9 `versions_behind_*` counts releases, not version arithmetic

§5.1 stores three counters and D3 keeps them out of the formula, so they exist
for the research and the UI alone. Two readings were available: subtract the
version components, or count the releases that actually shipped between the
resolved version and the latest.

Counting releases. `2.0.0` against a latest of `2.11.0` is "eleven minor
versions behind" by subtraction, but if the package skipped `2.4` there was
never a `2.4` for anyone to be behind. The levels are independent slices of
the same release list — majors above this one, minors above it *within* this
major, patches above it within this minor — and prereleases are excluded
throughout, because being "behind" a `3.0.0-beta.1` is not a claim about a
project that tracks stable releases.

Costless to get right, and a misleading number here would be carried straight
into the research as a covariate.

### 3.10 Two API-surface additions to §5.5

**`GET /api/repositories/{id}/`** — a method on a route §5.5 already lists for
`DELETE`. The detail page has to render for someone who typed the URL or
refreshed the tab; without it the only way to learn a repository's name is to
fetch the whole list and filter in the browser. It answers with the same
serializer the list does.

**`scan-status` answers two fields, not one.** `scan` is the newest scan
whatever its status; `latestCompletedScanId` is the last scan that produced
results. They are two different questions and they diverge exactly when it
matters: while a rescan runs, the pill must say "Scanning…" and the dependency
table must keep showing the previous, still-true results. Collapsing them into
one field is how a UI ends up either showing a finished table under a spinner
or blanking the table the moment a rescan starts.

### 3.11 A foreign scan id is a 404 on the dependencies route, not an empty page

`OwnedQuerySetMixin` on the occurrence queryset already leaks nothing — a
foreign scan's rows are simply not in the set. But it would answer a foreign
id exactly as it answers a genuinely empty scan, and every other route on this
surface answers 404. The route therefore resolves the scan through an
owner-scoped queryset first.

The reason is the standing BOLA suite (§11, extended every phase): it should
be able to assert one rule across every route, not a rule plus a table of
exceptions. An exception that leaks nothing today is one refactor away from
leaking a count.

### 3.12 Lock contention is tested by observation, not by racing threads

The rule is that the "is a scan already running?" check and the row insert both
happen inside the per-repository lock — the window between them is exactly what
a double-click fits through. The obvious test races two threads and asserts one
wins.

It is asserted by observation instead: the test watches whether the lock is
held during the check and during the insert. Two reasons. A race test passes
whenever the timing happens to be kind, and this property is either true of the
code or it is not. And it cannot run on SQLite at all — pytest's test
transaction holds the database's single write lock, so a second thread's write
blocks until the test ends. Since the local signal is SQLite (Docker does not
start reliably on the dev machine, §1 notes) a race test here would be
permanently skipped exactly where it is most often run.

The lock *dictionary's* own race — two threads reaching an unseen repository at
once and each creating their own lock, which is no lock at all — is tested with
real threads, because that one needs no database.

### 3.13 Two bugs a green suite could not see

The Phase 2 post-mortem (§2.5) said a passing frontend test is evidence the
code ran, not that the product works, and that a local browser check is cheap
enough to do before calling a phase done. Doing it found two.

**`usePolling` ran two overlapping loops.** The guard was a single `cancelled`
boolean ref. When the effect re-ran — React StrictMode's double mount in
development, or `enabled` flipping in production — the cleanup set it true and
the new run set it straight back to false; a request already in flight from
the *old* run then resolved, read `false`, and scheduled its own timer. Two
chains polling the same endpoint, and another with every subsequent re-run.

Every assertion about polling still passed, because every one of them was
about *behaviour* — does it stop on a terminal state, does it pause when
hidden — and both chains behaved correctly. The defect was in the *count*, and
nothing on screen shows a request count. It was found by counting scan-status
requests in the browser: four in eight seconds against a three-second
interval. The fix is an incrementing run token, which a later run cannot
reset. `usePolling.test.tsx` pins it, and was run against the old
implementation to confirm it actually fails there — a regression test that
does not fail on the regression is decoration.

**"Last scan: never" sat directly beside a failure message from four minutes
ago.** The metric read from the completed scan, which for a repository whose
only scan failed is null. The other three metrics in that row describe the
results and are rightly blank; this one describes the repository, and a
repository whose scan failed has emphatically been scanned. It now reads "in
progress", "failed 4 min ago", or a timestamp.

Neither was a logic error, which is the pattern §2.5 already named: correct
code, placed or worded so a reader draws the wrong conclusion.

### 3.14 An unbounded packument is an outage, not a slow scan

`common/http.py` read whatever arrived. That is fine against GitHub and OSV,
whose documents are bounded by what a repository contains, and not fine
against an npm packument, which grows without limit as a package accumulates
releases. Measured against the live registry — wire size, then resident cost
once `json.loads` has built the Python objects, which runs 3 to 4 times the
first:

| package | full | parsed | abbreviated | parsed |
|---|---|---|---|---|
| `vite` | 38.9 MB | **79.3 MB** | 2.3 MB | 5.5 MB |
| `typescript` | 15.6 MB | 53.2 MB | 8.7 MB | 24.6 MB |
| `@types/node` | 11.1 MB | 41.0 MB | 2.3 MB | 3.2 MB |
| `react` | 6.9 MB | 22.6 MB | 2.9 MB | 5.2 MB |
| `express` | 0.8 MB | 2.6 MB | 0.3 MB | 0.0 MB |

§1.13 measured the worker at 274.5 MB of 512 MB, leaving ~237 MB. One `vite`
lookup costs a third of that on its own — and `vite` is a dependency of the
first repository ever scanned on prod, so this was not a tail risk. The blast
radius is the point: an OOM kills the gunicorn worker, which is the whole
service (§2), so one unlucky scan takes down every other user's request.
Phase 8 puts an embedding model in the same process.

**Two caps, because one is wrong.** The first attempt used a single 4 MiB
ceiling and looked fine until it was run against real packages: `typescript`
became permanently *unassessable*, because its abbreviated form is still
8.7 MB, and `react` lost its staleness for no gain. So: 8 MiB on the full
document, which admits `react`, `express`, `axios`, `eslint` and the long
tail whole; 16 MiB on the abbreviated one, which is not laxity but the
minimum that keeps one of npm's most common dev dependencies readable.

**The degradation self-targets, which is what makes it acceptable.** A
packument only grows past 8 MiB by accumulating thousands of releases, and
that is what an *actively maintained* package looks like — so the staleness
being dropped is the one that would have read near zero anyway. A package
that stopped shipping stops growing, stays under the cap, and keeps the
signal in the only case where it carries information. §5.2's missing-value
policy does the rest: the term is excluded and its weight redistributed.

The abbreviated document's top-level `modified` is deliberately **not** used
as a staleness substitute. It moves when metadata is edited — a deprecation
being added is enough — so reading it as a release date would report an
abandoned package as freshly maintained. §5.1 asks for "days since the
package's latest release"; an honest unknown beats a confident wrong number.

`UpstreamTooLarge` is its own exception class rather than an
`UpstreamUnavailable`, because it is not a failure to answer: the upstream
answered fine, at a size this tier cannot hold. Callers with a smaller
representation available catch it and ask for that instead.

### 3.15 Workspace members inherit the root lockfile — but only when declared

§3.4 recorded that yarn and pnpm lockfiles are not read. It did not cover the
case that actually bites, because it is not about the lockfile *format*: an
npm **workspaces** monorepo has exactly one lockfile, at the root, by design.
The sibling-only rule meant every workspace member fell to
`range_latest_approx` and was checked against the registry's newest release
rather than what it installs.

That is the exact failure `npm.py` opens by naming, and it is invisible from
outside — the rows look perfectly well-formed, with a resolved version and a
provenance chip. Sabotaging the fix against the new fixture shows the cost:
the member resolves to the patched `lodash` 4.17.21 with **0 CVEs** instead
of the installed 4.17.19 with **2**. The repository reports clean.

**Inheritance is declared, never inferred from proximity.** A manifest adopts
an ancestor's lockfile only when that ancestor's own `workspaces` globs match
the member's path relative to it, nearest declaring ancestor first. The
fixture keeps an `examples/demo` outside the globs precisely to pin the other
half of the rule: borrowing a lockfile that never described you invents
resolutions, which is what the sibling-only rule got right and stays right.

Reading `workspaces` is npm's business, so it is an adapter hook
(`workspace_globs`) rather than scanner logic — Phase 6's soundness claim
only holds if ecosystem-specific concepts stay behind that seam. The glob
matcher is hand-written because `fnmatch`'s `*` matches `/` too, which would
let `packages/*` swallow `packages/a/nested/deep`.

`run_scan` became two passes as a consequence: read every manifest, then
decide lockfiles and parse. Whether a manifest inherits depends on what its
ancestor *says*, which cannot be known until the ancestor's bytes are in
hand. The second pass caches lockfile blobs by sha, which matters here in a
way it did not before — ten members pointing at one multi-megabyte root lock
is one fetch, not ten.

### 3.16 A skipped manifest now leaves a trace

Four paths drop a manifest without a `manifest_files` row: over
`MAX_MANIFEST_BYTES`, an undecodable blob, a parse failure, and
`MAX_MANIFESTS` truncation. Each logged a warning. Meanwhile the detail page
said "pooled across N manifests · each occurrence counted independently" with
complete confidence.

That is the silent miscount this product defines itself against, and it has
the same shape as both §3.13 bugs: correct code, placed so the reader draws a
conclusion the system never supported. A log line is not an answer to a
person looking at a table.

`scan_runs.skipped_manifest_count` is not in §5.1 and was added anyway. A
count is the smallest thing that closes it, it is operational only — it
cascades with the scan and never reaches the research tables — and it is
written in the same transaction as the rows it qualifies, because a count
claiming two manifests were missed next to a table that silently has them
would be worse than no count. The detail page renders it as a notice
immediately under the header line it qualifies, not somewhere else on the
page (§2.5's lesson).

### 3.17 `?flagged=false` returned everything

The filter tested only for truthy values, so an explicit `false` fell through
to *no filter* — the opposite of what it asks for, and silent about it.
Harmless in Phase 3, where nothing sets `is_flagged`; Phase 5's Flagged /
All / Unassessable tabs are the caller that would have found out the hard
way.

Three states now, not two. An unrecognised value filters nothing rather than
defaulting to `False`: guessing that `?flagged=maybe` means "show me the
unflagged ones" would be inventing an answer to a question nobody asked.

### 3.18 The detail page loads every dependency page

§10 Phase 3's objective is that the detail page "lists every dependency from
every manifest in the tree". It loaded the first 50 and captioned the rest
away, which is honest but not the objective.

The client now walks the paginator to the end — in sequence, not in
parallel, because completeness is the point and a burst of twenty concurrent
requests at a sleeping Render instance is a worse trade than an extra second.
Capped at 20 pages (1,000 rows) so it remains a bound rather than an
unbounded loop, and the caption still reports the server's own total, so a
table that *did* hit the cap cannot claim to be complete.

Phase 5's tabs will likely revisit this: filtering server-side is cheaper
than fetching everything and hiding most of it. Recorded here so that when
they land, the reason this is a full fetch is on the record rather than
rediscovered.

---

## Phase 4 — Scoring engine + weights v1

### 4.1 Rounding is part of the formula, not of the display

§5.2 gives the arithmetic and says nothing about precision, so there were two
defensible readings: compute at full precision and round only for the screen,
or round each term as it is produced and sum the rounded values.

The first is what a numerical library would do, and it is wrong here. This
product's whole claim is that the score is checkable — the mentor demo is
"open the bad one, the score is these three packages, here's the arithmetic".
Under full internal precision, a reader adding up the four term contributions
Phase 5 renders would land a hundredth or two away from the penalty on the
badge, and a page whose own working disagrees with its own answer has taught
the reader not to trust either.

So every term is quantized to two decimals (`ROUND_HALF_UP`) before it is
summed, the occurrence penalties fed into the roll-up are the two-decimal
values that were *stored*, and each decayed contribution is quantized before
being added to the deduction. The arithmetic a reader can do by hand is the
arithmetic that produced the number.

It also makes D6 exact rather than approximate. Research recomputing a
repository score from `dependency_history` gets the same value the product
displayed, not one within a rounding tolerance — so an agreement check between
a stored score and a recomputed one is an equality test with no epsilon in it.

Monotonicity survives: rounding each term independently is monotone in each
signal, so a sum of rounded terms is still non-decreasing in every input.
`test_scoring_engine.py` asserts it rather than assuming it.

A related trap, found only by running `rescore` and reading the CSV: the
clamp's bounds carry no decimals, so a repository that deducted nothing came
back as `Decimal("100")` while every other row said `100.00`. Invisible in the
database — `NUMERIC(5,2)` normalizes it — and visible in every artifact
rendered straight from the engine. Both scores are now quantized after the
clamp, and the test asserts the *string*, since `Decimal("100") ==
Decimal("100.00")` is true and no equality assertion could have caught it.

### 4.2 The CVSS placeholder is a derived flag, not a stored signal

§5.2 says a known CVE with no CVSS anywhere is scored at 5.0 with
`cvss_reduced_confidence` set. §5.1 puts that column on
`dependency_occurrences`, beside `cvss_max`, which reads as though the scanner
should write the 5.0 in.

It does not. D6 divides the schema into raw signals and derived values, and an
imputed severity is derived by definition — it is the formula's answer to a
missing measurement, not a measurement. So `cvss_max` stays NULL, which is the
truth about what OSV reported, and the scoring engine writes
`cvss_reduced_confidence = true` on the rows where its own placeholder was
used. Research recomputing from `dependency_history` sees the same NULL and
applies the same rule, so the imputation is reproducible rather than baked in.

§5.2 puts an NVD lookup between OSV and the placeholder. `NVD_API_KEY` is a
Phase 12 knob (§6), so until then the chain is OSV to placeholder, and the
flag marks every row it touched. Phase 12 inserts the NVD step ahead of the
placeholder without changing anything else.

### 4.3 EPSS, if ever enabled, is funded from inside the vector

§5.4's schema has four per-ecosystem weights summing to 1 and an `epss` block
outside them; §5.2 says EPSS is "appended as a fifth term" when enabled. Read
literally, an enabled EPSS weight of 0.1 makes the total 1.1, so a maximally
bad occurrence could be penalised 110 points and the 0-100 bound the product
states everywhere would be false.

The loader therefore validates that the four weights plus `epss.weight` (when
enabled) sum to 1 within ±0.001, and refuses a non-zero `epss.weight` while
EPSS is disabled — a weight that is not applied is a claim the formula does
not make. §5.4's own example (`enabled: false, weight: 0.0`) passes unchanged,
and Phase 12 gets a shape that cannot break the bound.

The engine already handles an enabled-but-unmeasured EPSS term through §5.2's
missing-value policy: no value, no term, weight redistributed. So an
EPSS-enabled weights file scores correctly against occurrences scanned before
EPSS enrichment existed, rather than treating them as if exploitation were
impossible.

### 4.4 The history tables live in `apps/research/`

§3's tree lists `apps/research/` with corpus, backfill and validation modules
and no `models.py`, and lists `apps/scanning/` without one either — the layout
omits standard Django files throughout, so it does not settle where
`scan_history` and `dependency_history` belong.

They are in `apps/research/`, for three reasons. §3's own parenthetical —
research code is "never imported by request-handling code (except the history
endpoint helper)" — only makes sense if research owns something the Phase 10
history endpoint reads. D9's rule that these tables never cascade on any
trigger becomes an app boundary rather than a comment: there is no foreign key
out of the app, so no cascade can reach in, and the way one would get added by
accident (an FK to `repositories`) is not available. And Phases 11-13 write
these same tables heavily from corpus and backfill code that already lives
there.

Two files §3 does not list: `apps/research/models.py` and
`apps/research/history.py`. `apps/scanning/retention.py` is listed and is
where §5.7's second half lives.

### 4.5 Retention deletes prior scans of any status, not only completed ones

§5.7 says to delete "the repo's prior *completed* `scan_runs` cascade". Taken
literally, failed scans accumulate for ever on a repository someone retried a
dozen times — invisible, because nothing in the UI reads a failed scan once a
newer one exists, but unbounded on a 500 MB free tier (§8).

`prune_prior_scans` deletes every scan of the repository except the one just
completed. A superseded failure is operational detail too: its `error_message`
describes a run a later scan has since answered. The rule §5.7 actually states
— only the latest scan's operational detail survives — is served better by the
wider deletion than by the narrower one.

The scan being kept is excluded by primary key rather than by status, so the
completion pipeline (which calls this before marking the scan `completed`)
cannot delete the run it just finished. Retention still runs only on
completion, so a failed scan can never delete the completed one whose results
the page is displaying.

### 4.6 Scoring failure fails the scan

The completion pipeline is three steps: score, record to history, retire the
previous scan. Any of them can raise, and the question was which failures
should sink the scan.

All of them. A scan that measured a repository but could not score it has no
number to show, and a `completed` row with a null `risk_score` renders as a
blank badge with no explanation — the silent-miscount shape §3.13 and §3.16
are both about. A visible failure with a Try again beside it is strictly
better. History failure is likewise fatal: D17's whole argument is that the
research data cannot be reconstructed later, so a scan that could not be
recorded is not a scan that should be reported as fine.

Scoring commits in its own transaction; history and retention share one. The
split is deliberate — scoring only rewrites derived columns on rows that
already exist, so it is safe committed alone, and if the write-then-delete
pair fails, the scan is marked failed with its signals scored and its previous
scan intact. That is a recoverable state, and rolling the score back too would
lose the diagnosis and buy nothing.

### 4.7 A repository where nothing is assessable scores 100, and has to say so

§5.2 excludes unassessable occurrences from every denominator, and §5.3 rolls
up over assessable ones. A repository whose dependencies are all `file:` paths
or git URLs therefore has no penalties, deducts nothing, and scores 100 —
Safe, with a full green ring.

That is the specification's arithmetic and the code follows it. It is also,
presented bare, exactly the kind of claim this product exists not to make: a
reader sees a green 100 and concludes the repository was checked and is clean.

The answer is not to invent a different score. It is to never let the number
appear without its scope. The card's counts line says "2 deps · none
assessable" instead of the arithmetic-requiring "0 flagged · 2 deps · 2
unassessable", and the detail page's strip says outright that nothing could be
assessed, above "0 of 2 dependencies assessed". Found by seeding the case and
looking at the page, not by a test — jsdom would have reported the same green
100 as a pass.

The same pass turned up a second one: the dashboard's "Avg score" tile still
read "scoring lands in Phase 4" while three cards behind it showed scores. It
now shows the mean of the scored repositories, with how many went into it and
which weights version. A plain mean is right *here* and forbidden inside the
formula (§5.3) — this averages one already-rolled-up number per repository to
summarise a list, where the formula's ban is on averaging occurrence scores in
a way that lets clean dependencies dilute critical ones.

### 4.8 Weights v1 — WP-1's vectors, adopted as delivered

WP-1 landed 2026-08-26 with two vectors and a method note:

| Signal | npm | PyPI |
|---|---|---|
| deprecation | 0.46 | 0.32 |
| severity | 0.28 | 0.35 |
| count | 0.16 | 0.16 |
| staleness | 0.10 | 0.17 |

Derived by an informal pairwise (Saaty) pass over a pre-filled seed matrix,
eigenvector-normalised. Each of the six npm judgments was reviewed
cell-by-cell and retained unmodified; the npm eigenvector's top entry is
truncated (0.4673 to 0.46) so the published vector sums to exactly 1.00, which
is why §5.4's ±0.001 tolerance is load-bearing rather than decorative.

The PyPI vector is not an independent elicitation. It is npm's, reasoned down
by roughly 30% on deprecation and redistributed to severity and staleness, on
the D2 argument that PyPI's deprecation signals (per-release yanking, the
rarely-applied `Development Status :: 7 - Inactive` classifier) carry less
information than npm's free-text deprecation message. The redistribution
inverts the ecosystem's top two signals — severity 0.35 now outranks
deprecation 0.32 — which is intentional, and it moves count below staleness on
PyPI while count outranks staleness on npm. WP-1 records that as a consequence
of staleness gaining mass, not a reassessment of count.

Two caveats belong with the numbers wherever they are quoted, because both are
easy to lose in a write-up:

* The Consistency Ratio of 0.0115 is **inherited from the seed matrix, not
  earned from independent judgment** — a CR that low is the signature of a
  generated ratio scale rather than a contested human assessment. And CR is a
  coherence check on the judgments, never a correctness check on the weights.
* The vectors were produced in a single joint session, with no independent
  judges and no reconciliation step. WP-3's two independent AHP matrices, the
  entropy cross-check, and WP-6's validation are what turn this into `v2`.
  Correctness is that study's answer, not this file's.

`weights/weights_v1.yaml` is the deliverable copied verbatim, comments
included, under a provenance header — paraphrasing it into something tidier
would separate the numbers from the reasoning that produced them. A test
asserts the shipped copy still parses identical to
`wp/wp-1/wp1_tier1_weights.yaml`, so the paper and the product cannot drift.

`weights_v0_equal.yaml` (0.25 x 4) ships alongside it and stays in the
registry permanently. §7 lists it as the fallback if WP-1 were late; its
lasting job is to be the naive baseline WP-6's sensitivity analysis measures
the elicited weights against.

### 4.9 `rescore` writes files and nothing else

D6 has two halves and the second is the one with teeth: scoring is a pure
function over stored signals, **and history rows are never mutated by
re-scoring**. A command that rewrote `risk_component_score` under `v2` would
destroy the record of what the product actually told a user in March, and two
research runs under different versions would overwrite each other.

So `manage.py rescore --weights <version> --out <prefix>` opens no write
transaction at all. It emits `_occurrences.csv`, `_repositories.csv`, and a
`_manifest.json` recording the weights, the filters, the row counts, how many
repository scores differ from what was stored, and a note stating in the
artifact itself that nothing was written — so a panel found on disk a year
later cannot be mistaken for something the product served. Both CSVs carry
`stored_*` columns beside the recomputed ones, so the effect of a revision is
readable without a join.

It is management-command-only: no route, no serializer, never imported by
request-handling code, the same discipline D13 puts around issue search.

### 4.10 API additions to §5.5

`GET /api/scans/{id}/` gains `topContributors` — at most three occurrences,
worst first, each with its raw penalty and its rank-decayed points. Not a new
route, so §5.5's surface is unchanged.

It is computed server-side even though the detail page already holds every
dependency row and could sum them itself. §5.3's rank decay *is* the
definition of the score; a second implementation of it in TypeScript would be
a second definition, free to drift from the one that produced the number on
the badge beside it.

`GET /api/scans/{id}/dependencies/` gains `cvssReducedConfidence` per row (see
§4.2). Phase 5's breakdown panel needs it; it is exposed now because the
column is written now.

### 4.11 The strip states the whole equation, including the part it omits

The contributors strip shows three rows. §5.3's decay makes the tail small but
not zero, so on a repository with four penalised dependencies the three points
shown summed to 76.59 while the badge had deducted 76.60. Correct, and one
hundredth short of adding up — which is worse than showing no working at all,
because a reader who checks and finds it off has learned the page cannot be
trusted.

The strip now closes the equation — `100 - 76.60 = 23.40` — and, where the top
three do not account for all of it, names the remainder: "76.59 from the 3
above, 0.01 from the rest". Found by seeding a repository and adding the
numbers up by hand; no assertion in either suite was looking at the sum.
---

## Phase 5 — Drill-down: why every flag exists

### 5.1 The breakdown is recomputed, never stored

§10 Phase 5 says the per-signal contributions are "recomputed live via the
pure functions from stored signals", and the temptation to store them instead
is real: four numbers per occurrence, written once at scan time, read back by
a serializer that does no arithmetic at all.

D6 is why not. The score is defined as a pure function of stored signals under
a named weights version, so per-term columns would be a second copy of
something already derivable — free to disagree with the `risk_component_score`
beside them the first time anything touched one and not the other. There is
also no schema for them: §5.1 has no per-term table, and inventing one would
be adding derived state to a schema whose whole organising principle is that
derived state is recomputed.

The cost is one `score_occurrence` call per request, over four numbers already
loaded on the row. The benefit is that a research rescore three years from now
runs the same code path over the same signals and cannot get a different
answer than the product showed.

### 5.2 Four decimals on screen, and the identity that needs none

The panel invites a reader to multiply `weight x normalized x 100` and find
the points beside it. That only works if the two factors are printed to enough
precision, and printing them to *too much* is its own failure — a normalized
term reported to fifteen digits is noise presented as measurement.

Only one of the four terms is ever inexact. Deprecation is 0 or 1, severity is
a tenth, count is a tenth; `min(days, 1095)/1095` is the only non-terminating
one, and an effective weight is inexact only when §5.2's redistribution has
divided one. At four decimals the reader's own product lands within 0.005 of
the printed points, which after §4.1's quantization is the same number.

The identity the page actually rests on needs no precision argument at all.
§4.1 quantizes each term *before* summing, so the points column adds to the
deduction exactly, and `100 - deduction` is the score exactly. Both are printed
rather than implied — §4.11 is the record of what happens when working does not
visibly close — and `test_dependency_api.py` asserts them to the hundredth
rather than to the ±0.1 §10 allows, because slack the pipeline does not need
is slack a dropped term could hide in.

### 5.3 A scan is explained under the weights that scored it

`active_weights()` answers "what would we score with today". That is the right
question when scoring and the wrong one when explaining.

D6 says history is never mutated, so a deployment that moves `WEIGHTS_VERSION`
forward does not rescore what is already on disk. Explaining one of those scans
under the new file would print a breakdown that does not add up to the score on
its own badge — the exact failure the panel exists to prevent, introduced by
the panel. So `weights_for_scan()` loads `scan_runs.scoring_formula_version`,
and the endpoint's arithmetic is the arithmetic that produced the stored
number.

Where that version's file cannot be loaded at all — retired from the
repository, or a Phase 3 row still tagged `unscored` — it falls back to the
active file and the response carries `matchesStoredScore: false`. The panel
then says so in as many words rather than choosing silently between two
numbers that disagree.

### 5.4 The flag rule keeps one definition, and now names its clauses

The panel has to answer *why* a row is flagged, not just that it is. The
cheapest version reads the row's other fields in TypeScript and infers the
clauses — and would be a second copy of §5.2's rule, free to disagree with the
boolean beside it the day `stale_flag_days` moves.

So `flag_reasons()` in `engine.py` evaluates the disjunction and returns the
clauses that fired, and `is_flagged()` became its emptiness test. One
evaluation, one definition, and the codes travel to the browser the way §5.6's
outcome codes do: the frontend phrases them, and a reworded sentence cannot
change what the backend asserted.

### 5.5 The bar is arithmetic, not decoration

The wireframe draws each signal as a bar. What the bar *measures* it does not
say, and the two obvious readings differ sharply.

Filling to the normalized value alone draws a saturated staleness term worth
0.10 exactly as long as a saturated deprecation term worth 0.46 — visually
equal, four times apart in what they cost. So each track is instead as wide as
the signal's share of the formula (its effective weight) and the fill is how
much of that share the signal actually spent. Filled lengths across the four
rows are then in the same proportion as the points column, and the empty
remainder is headroom the signal had and did not use.

Measured on a real page during the browser check: fills of 356/212/25/77 px
against points of 46.00/27.44/3.20/10.00 — one scale to within a pixel, so the
drawing and the arithmetic say the same thing.

### 5.6 `cleanCount` is measured, not subtracted

The three tabs need three counts, and two were already annotated. The third is
`dependencyCount - flaggedCount - unassessableCount` and was still added as its
own query.

Two reasons. The subtraction *assumes* the partition rather than measuring it,
and the partition holds only because §5.2 never flags an unassessable
occurrence — an invariant that lives in the backend and could move there
without the browser hearing about it. And "not flagged" is not the same
statement as "clean": subtracting flagged from the total would report "we
checked this and it is fine" about a row nobody could check, which is §4.7's
defect wearing a smaller hat. Each count now comes from the same predicate its
tab filters on, so a tab's label and its contents are defined by one query.

### 5.7 The tabs open on Flagged, and the empty state is built from what was assessed

Flagged is the default even when nothing is flagged. Switching to All on a
clean repository would put the answer in a different place depending on what
the answer was, and consistency of placement is the lesson §3.13 was written
about.

That makes the empty Flagged state load-bearing. "No dependencies flagged"
reads as "we checked everything and it is clean", which on a repository where
nothing could be assessed is a conclusion the scan does not support — §4.7 one
level down. So the sentence is assembled from `cleanCount` and
`unassessableCount`: nothing assessable says so and offers the tab that lists
the reasons; a clean repository with unassessable rows names them and states
that the score does not cover them; and only a repository with nothing it
could not check is told it is clear.

Tab labels carry the server's counts while the rows come from what the browser
loaded, so each tab says "Showing N of M" when those differ. A label reading
"Flagged (12)" over ten rows would be §4.11 again.

### 5.8 Why? sits on every row, not only the flagged ones

The panel is named for flags and the control is not. Putting it only on flagged
rows would make "no explanation available" and "nothing to explain" look
identical, and the two most interesting questions a reader brings to this page
are about the other kinds of row: why is this one *not* flagged, and what
exactly could we not assess?

An unassessable row answers with no arithmetic at all — `scoring: null`, and
the sentence that §5.2 excluded it from the score and from every denominator,
so it neither raised nor lowered the repository's number and nothing here is a
claim that it is safe. A row of zeroes would have said the opposite.

Rows open one at a time. Each open fetches its own breakdown, the panel is tall
enough that two push the second off-screen, and an accordion bounds the request
count.

### 5.9 API additions to §5.5

`GET /api/dependencies/{id}/` is the route §5.5 already reserved for this
phase; it takes the occurrence id directly because that is what a table row
has. It carries the list route's fields plus three things that route
deliberately omits — the per-signal arithmetic, the nested advisories verbatim
from OSV, and the manifest provenance including the lockfile path that makes
"from lockfile" a checkable claim rather than an assertion.

`GET /api/scans/{id}/` gains `cleanCount` (§5.6). Not a new route, so §5.5's
surface is otherwise unchanged.

The normalization caps travel inside the scoring block rather than being
hard-coded in the browser. §5.4 owns those bounds, and a UI phrasing "3 of 10
CVEs" from its own constant would go on saying 10 the day a weights file said
15.

### 5.10 The strip has to close over the clamp too

Found on a seeded page during the browser check, by adding the numbers up.

On a repository bad enough to bottom out, the contributors strip printed three
values summing to 124.84 directly beside `100 - 100.00 = 0.00`, and said
nothing. §5.3's roll-up clamps the score at 0, so the deduction the badge can
report is capped at 100 while the decayed penalties carried on past it. §4.11
had already fixed the case where the shown points fall *short* of the
deduction; nobody had asked what happens when they exceed it.

The strip now names the overshoot — "the 3 above come to 124.84 on their own; a
score cannot fall below 0, so only 100.00 of it could be deducted". The test
for the condition is exact rather than a heuristic: without the clamp, three of
N decayed penalties can never exceed their own sum, so `shown > deducted` can
only mean the clamp fired.

Same pass, smaller: a signal that cost nothing rendered as `-0.00`, a minus
sign in front of a quantity that was never subtracted. Zero points now print
unsigned.

### 5.11 Two requests per panel were React, and that was checked rather than assumed

Counting requests in the browser — the habit §3.13 left behind — showed two
GETs per panel opened where the jsdom test counted one.

The suspicion was `React.StrictMode` in `main.tsx`, which mounts, unmounts and
remounts every component in development so that effects missing a cleanup are
exposed. Suspicion is not evidence, so it was removed from the running dev
server and the count repeated: exactly one request per panel, restored
afterwards. It is React's development double mount and it is not in the
production build.

What the test added for it pins is the part that is ours. Under a double mount
the effect makes one request per mount and no more, and the `live` flag means
the discarded mount's response cannot overwrite the surviving one's — which is
the actual hazard, and the one a request count alone would not have shown.
