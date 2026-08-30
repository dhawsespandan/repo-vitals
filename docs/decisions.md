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
any fetch, so an oversized file costs nothing.

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
