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

### 2.6 GitHub's `size` is not evidence a repository is empty

Found on prod during Phase 5's acceptance run, on the very first fixture
repository built for it. A repo with `package.json` and `package-lock.json`
committed on `main` was rejected at validation with §5.6's `repo_empty` —
"This repository appears to be empty — there's nothing to scan."

Querying the GitHub API for the same repository, six minutes after the push:

```
size:           0
default_branch: 'main'
pushed_at:      2026-09-06T05:24:06Z
```

The guard read:

```python
if not default_branch or repo.get("size") == 0:
```

with a comment claiming `size == 0` was "the same state reported differently,
and catching it here saves a doomed tree call". That claim was the error.
`size` is the repository's size in **kilobytes**, rounded, written by a
background job that lags a push. A small repository reports 0 for a while
after it is populated, and a very small one can report it indefinitely. It is
a metric about bytes; emptiness is a statement about commits.

Worse than being wrong, the shortcut made the rejection **unfalsifiable**: it
skipped the tree call, so the one piece of evidence that would have settled the
question was never fetched. The check saved a request by declining to look.

The two authoritative signals were already in the function and are now the
only ones consulted — a missing `default_branch`, and GitHub's own 409 on the
tree call. Both keep the tests they already had, and neither moved.

**The population this hurt is the one the product is demoed on.** A small, new
repository created to try the thing out is exactly the case that reports
`size: 0`; the older, larger repositories already registered had grown past a
kilobyte and sailed through. Both outcomes sitting beyond this check —
`ecosystem_unsupported` and a successful registration — were reachable only by
getting past it, so a whole branch of §5.6's matrix was unreachable for the
repositories most likely to be pointed at it first.

**Why no test caught it.** Every §5.6 outcome has one, and they all pass. They
are built on a recorded `repo_public.json` fixture — a real payload from a real
repository, which is to say a repository large enough to report a non-zero
size. The fixture encoded an incidental property of the recording as though it
were a property of all repositories. The regression test now pins a populated
repository reporting `size: 0`; run against the old guard it fails with the
same `ApiError` the browser showed.

This is a Phase 2 rule fixed during Phase 5, and `v0.2.0` is already tagged.
Recorded here rather than under Phase 5 because §5.6 is where the rule lives —
and it is the clearest argument in the project so far for §4.5's insistence
that acceptance passes *on prod*: no amount of green CI on recorded fixtures
was going to produce a repository whose size had not been computed yet.

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

### 3.19 "Hasn't been scanned yet", on a repository that had

Found on prod during the Phase 6 acceptance run, in Phase 3 code. Not a
Phase 6 regression -- this phase added a chip and one boolean to
`RepoDetail.tsx` -- but a real defect, measured and fixed before `v0.6.0` on
§2.6's precedent.

The detail page makes two calls in sequence. `GET /api/repositories/{id}/`
answers first and carries `latestScan` and `latestCompletedScanId`;
`GET /api/scans/{id}/` answers second and carries the results. Everything
between them is a state the page has to render, and it rendered this:

```
0ms      (blank)
2985ms   "Loading this repository..."
5976ms   "This repository hasn't been scanned yet."   <- + Run the first scan
8982ms   the real page
```

Three seconds, timed on Render's free tier against `rv-accept-pypi`. During
them the header pill read **Scanned**, the metric row read **LAST SCAN
never**, and the body offered a primary button to run a first scan -- on a
repository whose completed scan the page was, at that moment, downloading.

**Two lines, one mistake made twice.** `lastScanLabel` fell through to
`return "never"` whenever the scan *detail* was null, and the render branch
tested `!scan` without asking whether a completed scan existed. Both conflated
"we have not measured this repository" with "we have not finished loading what
we measured". The value that separates them was already in state:
`latestCompletedScanId` non-null with `scan === null` means loading, not
absent.

**Why it mattered more than a wrong word.** The button under the sentence
starts a scan, and §5.7's retention deletes the scan it replaces on
completion. Today that costs a redundant scan and some free-tier quota. From
Phase 7 the cascade also destroys the cached `combined` report for that scan --
an LLM call already paid for -- which is exactly the destruction Phase 9's
rescan-confirmation guard exists to prevent, reached here by a button the user
was invited to press.

The fix says "Loading this scan's results..." and reports the last scan as
`—`. The em dash rather than a word, because the four metrics beside it
already say `—` while the detail loads; a fifth reading "never" is not a
quieter version of the same statement but a different and false one. That is
§2.5's rule about placement, applied to a row of five siblings.

**This is the second time this exact sentence has been wrong.** Phase 3 found
"Last scan: never" beside a failure message from four minutes ago, and fixed
it by reading the metric from the newest scan rather than the completed one.
That fix was right and incomplete: it never asked what the function should say
when there *is* a completed scan whose detail has not arrived. A null check
was left returning the same false answer by a different route.

**The reason no test saw it.** `stubFetch` answered both calls in the same
tick, so the window did not exist in jsdom -- not "was not asserted", *did not
exist*. Every state between the two responses was unreachable by construction.
The harness now takes `scanDelayMs`, the three regression tests run inside the
window, and all three fail against the previous build.

The general lesson, and it is not about this page: **a test harness that
answers every request instantly deletes the states a real one produces.**
Sequential fetches have a gap; a mock without latency has none, and whatever
the product renders in that gap is untested by construction rather than by
oversight. Anywhere the UI makes call B only after call A resolves, the
interval is a state, and it needs a slow mock to exist at all.

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

§3's tree lists `apps/research/` with corpus, validation and experiment modules
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
these same tables heavily from the corpus code that already lives there.

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

### 5.12 A 404 that answered with Django's sentence about the ORM

Found on prod during this phase's acceptance run, while checking §11's BOLA
rule. Requesting an unknown dependency id returned the right status and the
right code, and this message:

```json
{"code": "not_found", "message": "No DependencyOccurrence matches the given query."}
```

The security property held — 404, empty body, no package name — so the check
passed. The wording is the finding.

**The curated message already existed and was unreachable.**
`_STATUS_DEFAULTS` in `apps/common/errors.py` has carried
`"We couldn't find that."` for 404 since Phase 1. The handler overwrote it
with DRF's `detail` whenever one was present, and for `get_object_or_404`
that detail is Django's auto-generated string. So the default was dead code in
exactly the case it was written for — a defence that had never once fired.

**A person reads this one.** It would be tempting to file it as cosmetic: who
types a UUID into an address bar? But `WhyFlaggedPanel` renders the message
verbatim, and the route is reachable with nothing broken at all:

1. A detail page is open in a tab.
2. A rescan completes somewhere else — another tab, another device.
3. Retention (§5.7) deletes the previous scan's occurrences.
4. The first tab is not polling, because polling stops on a terminal state, so
   it still holds rows from the scan that has been replaced.
5. Expanding one of them requests a `dependency_id` that no longer exists.

The reader gets a sentence about the ORM where the arithmetic belongs. That is
the same family as §2.5 and §2.6 — correct behaviour, worded or placed so the
person it reaches cannot act on it — and the third time in this project that a
message was written for whoever wrote the code rather than whoever hit it.

**The fix is two changes, because the status and the wording are different
problems.** The handler keeps the curated message for 404 and discards DRF's
detail; the panel branches on 404 and says what actually happened.

Scoping the handler change to 404 rather than to every status was checked
rather than assumed: every deliberate 404 in this codebase goes through
`ApiError`, which returns before this branch, and there is no hand-raised
`NotFound` or `Http404` anywhere under `apps/`. The only 404s reaching the
override are therefore auto-generated, and the curated default is strictly
better. Other statuses keep DRF's detail, which is usually deliberate — a
throttle's wait time, a permission class's own reason.

`"We couldn't find that."` would have been an improvement and still not
something a reader can act on, so the panel does not stop there. A 404 says
the scan behind these results has been replaced, and a Reload control sits
beside it. Every other failure keeps the backend's wording and gets no button,
because reloading does not fix a 500 — an offered remedy that cannot work is
worse than none, which is the lesson the revoked-token message left behind in
Phase 2.

**A note on the tag.** This fix and §2.6's landed after the commits `v0.5.0`
would otherwise mark, and the acceptance run was performed against a
deployment that includes both. `v0.5.0` therefore points at the fixed head
rather than at the phase's last feature commit — the tag records what passed,
not what was written first.


## Phase 6 — PyPI adapter: the soundness proof

The phase's headline evidence lives in `docs/adapter_soundness.md`: the diff,
the touched-path list, and the untouched-core assertion. What follows is the
reasoning behind the choices that diff does not explain on its face.

### 6.1 The adapter is bound to a path, because the bytes cannot say which parser to use

`DependencyAdapter.parse` receives manifest bytes and an optional lockfile, and
no path. npm never needed one: it has a single manifest, `package.json`, so
whatever arrives is that. PyPI has five formats and the signature does not say
which arrived.

Three ways out, and two of them are worse.

**Sniff the content.** It nearly works. `pyproject.toml` and `Pipfile` are both
TOML but never carry each other's tables, so those two separate cleanly. The
pair that does not separate is `setup.py` and `requirements.txt`: `django==2.2`
is a valid requirement line *and* a valid Python comparison expression, and
`ast.parse` accepts a whole requirements file without complaint. Distinguishing
them means looking for a `setup()` call — which is the very thing that may be
dynamic, so the sniffer would guess on exactly the files where guessing wrong
changes the answer.

**Add a path parameter to `parse`.** Honest and obvious, and it changes the
base class, `npm.py` *and* `scanner.py` — the one file §10 Phase 6's guardrail
names first. The phase's whole claim would have been weaker for the sake of a
slightly more legible signature.

**Bind the path when the adapter is chosen.** `adapter_for_path` already
resolves a path to an adapter; it now returns `adapter.for_path(path)`, which
is `self` for every ecosystem but PyPI. `scanner.py` goes on calling
`plan.adapter.parse(manifest_bytes, lockfile_bytes)`, unchanged and unaware.

The third one also paid for something unrelated. A path-bound instance knows
which of the five formats it is, so `parser_name` became
`pypi/requirements@1`, `pypi/pyproject@1`, `pypi/setup_py@1` and so on.
`manifest_files.parser_name` exists so a stored row says which code read it,
and until now PyPI would have answered that question with one word for five
different parsers.

The second hook, `owns(path)`, is a smaller story with the same shape:
requirements files are a *convention*, not a standard, and a fixed set of
basenames could not express "`requirements.txt`, or `requirements-*.txt`, or
anything `.txt` in a directory called `requirements`".

### 6.2 `setup.py` is read with `ast` and never executed

Every other manifest in this project is data. `setup.py` is a program, and it
is the one file where the difference is not academic: it runs with the
privileges of whoever installs the package, and a repository under scan is by
definition somebody else's input. A scanner that imported it to read
`install_requires` would be a remote code execution service with a dependency
table attached.

So it is parsed to a syntax tree and read for literals. `ast.literal_eval`
builds constants, tuples, lists, dicts and sets and does nothing else — no
call, no import, no attribute access — so a hostile `setup.py` gets exactly
what a friendly one gets.

Two refinements were worth making inside that constraint.

**Module-level bindings are resolved.** `install_requires=REQUIREMENTS` with
`REQUIREMENTS = [...]` above it is the commonest shape a real `setup.py` takes
that is not a bare literal, and it is entirely static. Walking the top-level
assignments and `literal_eval`-ing each one turns a large slice of the long
tail from "unassessable" into a real answer, at no cost to the rule above.

**The `setup()` call is found anywhere in the file**, not only at the top
level, because a great many of these files put it inside
`if __name__ == "__main__":`. A top-level-only search would have read those as
declaring nothing at all — which is the silent-miscount failure, wearing a
different hat.

`test_a_setup_py_is_never_executed` is deliberately unsubtle about all of this:
the fixture writes a file on import *and* on call, and the test asserts neither
file exists.

### 6.3 A dynamic argument becomes a row, and the row needs a name it cannot have

§10 Phase 6 asks for `dynamic_setup_py` as an unassessable reason — "a
documented gap, not a miscount". Writing it exposed a small collision with the
schema: `dependency_occurrences.package_id` is NOT NULL, and a dynamic
`install_requires` names no package. That is the entire point of the reason.

Raising `ManifestParseError` instead was tempting and wrong. It would mark the
manifest *skipped*, and the notice a skipped manifest produces says "too large,
unreadable, or past the per-scan limit" — three explanations, none of them
this one, for a file that was read perfectly well.

So the row carries a synthetic name: `setup.py:<keyword>`. A colon is not legal
in a PEP 503 project name, so the marker can never merge with a genuine
`packages` row, and it can never be produced by the parser that produces every
other name. The `declared_specifier` quotes the expression we declined to
evaluate — `read_extra()` — rather than describing it, for the same reason a
deprecation reason is stored verbatim: the reader is being told what their own
file says.

One consequence reaches the UI and had to be handled there. The generic
sentence — "This dependency could not be assessed (`dynamic_setup_py`)" — is
actively misleading, because there is no package called
`setup.py:extras_require` and a reader taking the row at face value would go
looking for one on PyPI. So the panel branches: it says that `setup.py` builds
its list when the package is installed, that RepoVitals reads it without
running it, and quotes the line.

### 6.4 PyPI's deprecation is a composite, and its two halves are different claims

D2 fixed this before the phase started; implementing it made the asymmetry
concrete. npm has one field: a per-version `deprecated` string. PyPI has
neither the field nor the concept, and two things that carry the sentence:

* **A yanked release (PEP 592).** A claim about *this version* — the maintainer
  withdrew it, usually within hours, and the reason often names the CVE or the
  regression it was withdrawn for. Django 4.2.12's is *"Release files have
  Windows end-of-line characters and are missing executable bits."*; requests
  2.32.0's names a CVE mitigation conflict.
* **The trove classifier `Development Status :: 7 - Inactive`.** A claim about
  the *project* — nobody is maintaining any version of it. `oauth2client` has
  said so since 2018.

Either sets `is_deprecated`, because both mean "do not depend on this". The
reason follows D2 literally (`yanked_reason or classifier`), so a yank with no
stated reason falls through to the classifier where there is one and stays an
empty string where there is not. That empty string is a real answer — the exact
analogue of npm's `"deprecated": true`, which is a deprecation carrying no
text rather than the absence of one — and it survives to the UI as such,
because the information content of this text is S3's independent variable.

Two smaller rulings inside the composite:

**A release is yanked only when every one of its files is**, which is pip's
own rule. A release with one withdrawn wheel and a good sdist is still
installable, and flagging it would put a dependency in front of a reader that
needs no action.

**The yank is read from the resolved version, not the latest.** Django 4.2.12
is yanked; 4.2.11 and the current release are not. Which one the lockfile
installed is what decides — the same reading `NpmRegistryClient` gives the
per-version `deprecated` field, and the same reason.

### 6.5 One cap, no abbreviated fallback, and the measurement that decided it

npm's registry client has two size caps and a fallback path, because a
packument is unbounded: `vite` is 38.9 MB on the wire and 79.3 MB parsed
(§3.14). The obvious move was to mirror that structure for PyPI. Measuring
first said not to.

PyPI documents, recorded 2026-09-06:

| package | wire | parsed peak | releases |
|---|---|---|---|
| numpy | 3.45 MB | 14.90 MB | 150 |
| boto3 | 3.12 MB | 10.60 MB | 2,113 |
| setuptools | 1.12 MB | ~4 MB | 625 |
| django | 0.59 MB | 2.02 MB | 442 |
| requests | 0.18 MB | 0.80 MB | 163 |

The parsed-to-wire ratio is npm's, 3 to 4x. The absolute sizes are an order of
magnitude smaller, and the reason is structural rather than incidental: PyPI
publishes release *files* carrying a handful of scalars each, where an npm
packument embeds every version's entire `package.json`. Even boto3, with
2,113 releases, is a third of what `vite` costs.

So one 8 MiB cap covers the ecosystem with headroom, and a second fetch path
existing only to be untested was not worth adding. Past the cap the row is
recorded `registry_unavailable` — unassessable, never clean — and the rest of
the scan proceeds. `scanner.py` already fails the whole scan only when *every*
lookup came back that way, which is the right line: one giant package is a fact
about that package, and a registry answering nothing is a fact about the
afternoon.

### 6.6 Names are normalized, specifiers are not

PEP 503 says `Zope.Interface`, `zope-interface` and `zope_interface` are one
project. Three systems in this application have to agree on which spelling that
is — `packages` is `UNIQUE(ecosystem, package_name)`, the in-run registry cache
is keyed by name, and OSV answers only to the normalized form — so the
normalization happens once, in the parser, and everything downstream sees one
name.

Left un-normalized, `Django` in one manifest and `django` in another would be
two `packages` rows, two registry lookups against the user's own bandwidth, two
independent sets of advisories, and two independent terms in §5.3's roll-up for
one dependency. The last of those is the expensive one: the roll-up counts
distinct occurrences on purpose, so a spelling difference would inflate a
repository's penalty.

The declared specifier is deliberately *not* normalized. It is what the reader
will see in their own file, and `== 2.2` with a space is what they wrote.

### 6.7 A sentence that passed every assertion and read wrong on the page

The `dynamic_setup_py` panel text is assembled from two halves: a branch that
explains the specific situation, and a shared tail that states the consequence
(§5.2 excluded this row from the score). The branch was written as two
sentences, the second beginning "So the packages...", and the tail begins "so
§5.2 excluded it". The page rendered:

> ...RepoVitals reads setup.py without running it**. So** the packages behind
> this line were never named to us**, so** §5.2 excluded it from the score...

-- two connectives doing one job, in the middle of the one sentence on the
page whose whole purpose is to be read carefully.

Every assertion passed. They checked that the notice contained "without running
it", that it contained the quoted expression, and that the shared half still
said "excluded it from the score" — three substrings, all present, in a
sentence no one had read end to end. This is the sixth defect in this project
of exactly that family (§2.5, §2.6, §4.7, §4.11, §5.10, §5.12): correct code,
worded or placed so the reader cannot use it, invisible to every test that
asserts a mechanism.

The regression test now asserts the **whole** `textContent` of the notice
rather than substrings of it, which is the only form of the assertion that
could have failed. Run against the previous build, it does.

The general rule this adds to the two already in `MEMORY.md`: **when a
user-facing sentence is assembled from more than one source, assert the
finished sentence.** Substring assertions cannot see a join, and a join is
where assembled prose breaks.

### 6.8 What the phase found in the code it was forbidden to change: nothing

The guardrail exists to make the soundness claim falsifiable, so the honest
report is what it cost. It cost nothing — no point in the phase was there a
change to `scanner.py`, `scoring/`, `models.py` or the API that would have been
the right fix and had to be worked around instead.

Three things carried the phase, and all three were decisions made earlier
against a PyPI that did not exist yet:

* **The schema had `ecosystem TEXT CHECK IN ('npm','pypi')` from Phase 3**
  (D1), so the phase needed no migration at all.
* **Validation asked `adapter_for_path` rather than keeping its own filename
  list** (§2.3), so it learned five new manifest formats without a line of its
  own.
* **Both weights files already carried a `pypi:` vector** (§4.8), and
  `for_ecosystem` raises rather than falling back to npm's — so a missing one
  would have been a loud failure rather than a silent mis-score. It was not
  missing.

The mixed-repository case is where this is most visible: one scan, one
rank-decayed roll-up, npm rows scored under `{dep .46, sev .28, cnt .16,
stl .10}` and PyPI rows under `{dep .32, sev .35, cnt .16, stl .17}`, with no
branch anywhere on an ecosystem name. `signals.py` reads
`occurrence.manifest.ecosystem` and hands it to `weights.for_ecosystem`; that
is Phase 4 code, over a Phase 3 schema, running against an ecosystem neither of
them had ever seen.

### 6.9 Documented gaps

Named here rather than discovered later. Each is a case where an honest "we did
not read this" was chosen over a guess:

* **`uv.lock` and `pdm.lock` are not read.** `npm.py`'s reasoning about yarn
  and pnpm applies unchanged (§3.4): a half-understood lockfile parse is worse
  than an honest range approximation, because it produces confident wrong
  versions rather than visibly weaker ones. A `pyproject.toml` managed by
  either tool resolves as `range_latest_approx`, which the UI labels
  "approximated".
* **PEP 735 `[dependency-groups]` is not read.** Newer than the two schemas the
  plan names, and rarer; the same treatment as the two lockfiles above.
* **A `setup.py` whose `install_requires` cannot be resolved from literals or
  module-level bindings** yields one `dynamic_setup_py` row per keyword rather
  than a package list. §6.3.
* **A repository declaring the same dependency in both `requirements.txt` and
  `pyproject.toml` counts it twice.** This is §5.1's rule, not an oversight —
  duplicates across manifests are independent rows, because each is an
  independent installation needing its own remediation — but it lands harder on
  Python than on npm, where two manifests declaring one package usually means
  two real installs. A reader seeing `django` twice on a Python repository is
  seeing two declarations, and the manifest path on each row says which.
* **`-e .` and bare local paths are skipped, not recorded.** A project
  installing itself is not one of its own dependencies. An editable install
  that *does* name a distribution (`-e git+https://…#egg=widget`) is recorded
  unassessable with its reason, like every other reference no registry can
  describe.


## Phase 7 — COMBINED report: the first LLM call

The phase adds one model call to a product that has so far only measured
things, and almost every decision below is about keeping the boundary between
the two visible. §5.9 already draws it — COMBINED bypasses the retrieval graph
entirely, "deliberately a lighter triage surface so the grounded-generation
thesis stays concentrated in PER_DEPENDENCY" — and the work here was making
that sentence true in the data, in the prompt, in the schema and on the page,
rather than only in the plan.

### 7.1 The model is never the source of a fact we already measured

§5.8 gives a fix ten fields. Seven are decisions — which dependency, upgrade or
replace, to what version or what package, in what order. Three are
measurements: `current_version`, `cves` and `severity`. The scanner already
knows all three, to the row.

The prompt therefore asks for the seven and fills in the three from the matched
scan row, discarding whatever the model said about them. The emitted payload is
still exactly §5.8's, so a download and a database row conform to the spec
whatever the answer contained.

This is the same rule as §5.1's raw/derived split and §5.1's recomputed
breakdown, applied to a new source of values: one source of truth per number.
It buys three things. A shorter prompt, so more of the budget is signal. A
whole class of on-screen wrongness that becomes unreachable rather than
unlikely — no amount of prompting stops a model from writing `4.17.15` where
the lockfile says `4.17.19`, and no test would catch it because the number is
plausible. And a page where the claim "every number here traces to a stored
signal", which Phase 5 established for the drill-down, survives contact with a
generative surface.

The one thing on the panel the model wrote is the summary paragraph, and the
panel says so.

### 7.2 No upstream prose reaches the prompt, which makes an approximate claim exact

§10 Phase 7 says the input is "structured signal rows only (no fetched text =>
injection surface ~ 0)". Taken literally that excludes two fields this project
stores and would like to send: OSV's advisory `summary`, and the deprecation
reason — npm's deprecation message or PyPI's `yanked_reason`, stored verbatim
however terse because that asymmetry is S3's variable.

Both are useful. The deprecation message is often where a successor is named
("use axios instead"), which is exactly what a triage list wants. Both are also
text written by a package author and publishable by a stranger: anyone can
publish a package whose deprecation message is a paragraph of instructions
addressed to a language model.

So neither is sent. What goes is versions, day counts, CVSS numbers,
severities, OSV and CVE identifiers, booleans, enum values and manifest paths.
The claim in the plan stops being approximate and becomes a property a test
asserts — `test_no_upstream_prose_reaches_the_prompt` sends a scan whose
deprecation reason is a sentence and checks the sentence is absent while the
boolean is present.

What is left is honest rather than zero. Package names and manifest paths are
strings, and a repository's own tree can contain a path chosen to read like an
instruction. That is a user acting on their own report; the system prompt
frames the block as data and forbids following anything inside it; and §7.3's
cross-check bounds the worst outcome to a fix naming a row that was already in
the scan.

Phase 8 does quote changelog and README text — under retrieval discipline,
beside the source it came from, with a grounding check in front of it. A
quoted sentence belongs there, not here.

### 7.3 A fix that names a package this scan never found is not a shorter list, it is a wrong one

The acceptance criterion is "every fix references a real scanned row (validator
cross-checks)", and the reason it is a criterion rather than a nicety is what
an invented row looks like on the page: identical to a real one. A reader has
no way to tell `left-pad@1.3.0 · package.json` from the three rows above it,
and the whole product is an argument that its numbers are checkable.

So every fix is matched against the rows the prompt was built from, on
(ecosystem, package, manifest_path). The name is matched case-insensitively —
npm names are lowercase by rule and PyPI's are case-insensitive under PEP 503,
so a title-cased name is not a different package — and the path exactly, because
`Src/package.json` and `src/package.json` are two files.

The repair policy has three steps and each one is a different judgment:

1. **A schema violation or an invented row buys one repair call**, carrying a
   plain account of what was wrong. §10 Phase 7 allows exactly one.
2. **After that, invented rows are dropped rather than argued with.** A model
   that reinvents a package after being told which one it invented is not going
   to be talked round by a third call, and a shorter list of real dependencies
   beats a plausible list containing packages this repository does not have.
3. **Unless every fix was invented, in which case the generation fails.** A
   summary paragraph above an empty fixes list, on a repository with three
   flagged dependencies, reads as "nothing to do here". That is §4.7 and §5.10's
   shape exactly — correct output whose scope is missing — and a visible failure
   with a Try again beside it is better than a confident silence.

A repository with nothing flagged may legitimately produce no fixes; the guard
is on inventing, not on emptiness.

### 7.4 The retry budget is spent in the client, because the transport's is the wrong one

`common/http.py` says in as many words that its retry policy is safe only
because the one POST it carries is OSV's read-only `querybatch`, and that a
state-changing POST needs `retries=0` plus a comment saying why.

A Groq call is that POST. It is metered, and a read timeout can mean "the
provider generated an answer and we did not hear it" — a retry then bills a
second generation for one click. So the transport retries nothing and
`groq_client` retries once, on a 5xx or a 429, which is what §10 Phase 7
specifies.

The whole budget, stated once so it can be checked: one logical call, plus one
repair call if the answer violates §5.8, each of which may be re-sent once.
Four HTTP requests worst case, two accepted generations worst case.
`LlmCall.requests` carries the count out so a test asserts the first number
rather than a docstring claiming it.

### 7.5 The cache is three layers, and a failed report is not one of them

The layers are `apps.scanning.background`'s, unchanged: the in-process lock
closes the millisecond race a status check cannot, the row's own status makes
the answer correct across processes, and §5.1's partial unique refuses whatever
got past both. An `IntegrityError` on that unique is caught and answered with
the row that won.

Two things differ from a scan, and both follow from what is being protected.

**A failed report is retried in place.** A failed scan leaves nothing worth
keeping and a rescan is cheap. A failed report is one unlucky HTTP call away
from a rescan that would destroy the scan's results under §5.7 — trading a
measurement for a report is the wrong way round. A `completed` report is never
regenerated: that is the cache, and Phase 9's confirmation exists precisely
because clearing it is destructive.

**A generation presumed dead is presumed dead in five minutes, not fifteen.**
A scan's fifteen accommodates a slow upstream tree walk; a generation is
bounded by its own 60 s read timeout and a four-request ceiling. A killed
worker must not strand the button behind its own 409 for a quarter of an hour.

### 7.6 A missing key is a deployment fault and is answered as one

`GROQ_API_KEY` unset is a valid configuration: every phase before this one runs
without it and CI has none. The request path therefore checks before writing
anything and answers 503 `reports_unavailable`, rather than creating a report
row, failing it, and inviting the reader to retry something that cannot
succeed.

The message does not name the setting. Which environment variable is missing is
a log line for whoever deployed it, not an explanation owed to the person who
pressed a button.

### 7.7 API additions to §5.5

Two routes, exactly as §5.5 specifies:

```
POST /api/scans/{id}/reports/combined/   200 cached | 202 started | 409 generating
GET  /api/reports/{id}/
```

Plus one addition, to an existing payload rather than as a new route:
`GET /api/scans/{id}/` grows `combinedReport` — `{id, status, generatedAt}` or
null.

It is an addition because the alternative is worse. The only endpoint that
answers "does this scan have a report?" is the POST that *generates* one, so a
page that asked on load would bill a model call for opening a tab. Three fields
rather than the report itself: §5.5 gives the body its own route, and a scan
payload carrying a whole generation would make the detail page pay for
something nobody has asked to see.

Two response details worth recording. The 409 carries `reportId`, so a client
whose request lost the race polls the winner instead of guessing. And `fixes`
is served in §5.8's own snake_case while every other field on the surface is
camelCase — deliberate, because §5.8 is binding and is *also* Phase 9's
`?fmt=json` download: one payload serving both, per §5.8's own sentence.
Renaming the keys for the browser would give the panel one shape and the
download another, free to drift.

### 7.8 A Reports tab, because File A says so — and what that overruled

§10 Phase 7 is explicit: "Reports tab: Generate → generating (poll) → summary
markdown + prioritized fixes **table**". The surface shipped first as a
right-hand drawer with fix *cards*, following the wireframe's `combinedOpen`
artboard, and was rebuilt as a tab with a table when that was noticed.

The argument for the drawer was not bad, and it is worth recording because it
lost. The three tabs already on the page — Flagged, All, Unassessable — are
three views of one partition, and the sentence beneath them says so: flagged +
clean + unassessable is every dependency exactly once. A fourth tab sits in
that row looking like a fourth slice of the same set, and a report is not a
slice of the dependency list, it is a reading of it.

What settles it is authority, not taste. §2 of this project's own charter makes
File A "the only guide for the codebase", and File A's text never mentions
`wireframe.html` at all — the wireframe's binding status was an assumption
carried in from elsewhere, and it does not outrank the document that does
govern. Where the two disagree on structure, File A wins.

Two smaller things fell out of the same reading, and both are improvements:

* **The tab carries no count.** Flagged, All and Unassessable each show how
  many rows they hold; Reports shows nothing, because it counts nothing. That
  keeps the partition sentence honest — it still describes three views of one
  set — while §10's fourth tab sits beside them.
* **The component could not have kept its name.** §10 Phase 8 reserves
  `ReportPanel` for the per-dependency *drawer*, so a Phase 7 combined-report
  component called `ReportPanel` would have collided with the next phase. It is
  `ReportsTab` now, which is also what §10 Phase 7's own commit list calls the
  work: `feat(frontend): reports tab, fixes table, cached indicator`.

The lesson is narrower than "follow the plan". It is that a deviation argued on
the merits still needs to name which document it is deviating *from*, and check
that document actually outranks the one being followed. §7.8 originally cited a
binding specification that File A does not cite.

### 7.9 A fixed overlay inside an animated element is not fixed

Found on the combined-report drawer, which §7.8 has since replaced with a tab.
The drawer is gone; the defect it exposed is not, and it is the reason
`ConfirmDialog` and `AddRepoDialog` are portalled today (§7.9.1). Recorded
here in the terms it was found in.

The drawer was first rendered inside `<main>`, and in a real browser it was
clipped at the top, sat 58 px short of the right edge, and scrolled with the
page. Every jsdom assertion passed, because jsdom has no layout.

The cause is one line of Phase 1 styling. `<main>` carries
`animation: dsup .3s ease both`; `dsup`'s 100% keyframe is `transform: none`,
and `animation-fill-mode: both` holds that keyframe as an *animated value*
forever. An animated `transform` computes to a matrix, never to the keyword
`none` — measured as `matrix(1, 0, 0, 1, 0, 0)` long after the animation
finished. A transformed element is the containing block for every
`position: fixed` descendant, so `inset: 0` resolved to `<main>`'s box (1180 x
954 at top -31) instead of the viewport.

The fix was a `createPortal` to `document.body` inside the drawer component
itself, rather than moving the element up one level in `RepoDetail`. Both work;
the portal is better for the same reason `OwnedQuerySetMixin` beats a
permission check in each view. Moving the call site fixes that one call site
and leaves the next caller to rediscover the defect; the portal makes a
component viewport-relative wherever anyone mounts it, and an overlay is
viewport-relative by definition. It also keeps `<main>` untouched, so the
diff on that file is the change and not a re-indentation of it.

The corrected geometry was re-measured in the browser before the drawer was
retired: backdrop 0,0 x viewport, panel 480 wide, flush right, full height, no
overflow at 1280 or at the narrowest width the pane allows.

The general rule this leaves: `position: fixed` means "relative to the
viewport" only while no ancestor carries a transform, a filter, a
`backdrop-filter`, `perspective`, `contain`, or a `will-change` naming one of
them. An overlay that depends on that should not depend on where it is
mounted.

### 7.9.1 The same defect in Dashboard's two dialogs, and what it actually looked like

`Dashboard` renders `AddRepoDialog` and `ConfirmDialog` inside its own animated
`<main>`, so both carried the defect above. It was noted when §7.9 was written
and left alone as Phase 2 code out of Phase 7's scope; it is fixed here.

Measured first, because the severity was not obvious. At 1280x900 the dashboard
fits the viewport and the damage is mild: both backdrops resolve to `<main>`'s
box — 50, 58.8, 1180 x 825.85 rather than 0,0 x 1280x900 — so the dim overlay
leaves a 50 px gutter down each side and an undimmed strip under the nav, and
the dialog sits about 22 px below the optical centre. Easy to miss.

The real case is a page that scrolls. At 1000x520, scrolled to the bottom of a
1071 px dashboard, the confirmation's backdrop starts at **top -481** and the
dialog itself at **top -72.6** with a height of 184 — so 39% of it, including
the title asking which repository you are about to stop monitoring, is above
the top of the screen. The buttons are reachable and the question is not
visible. That is the shape this project keeps finding: not a crash, a correct
component placed so the reader draws a conclusion it does not support.

The fix is `createPortal` in `ConfirmDialog` and `AddRepoDialog` themselves,
not a fragment at the Dashboard call site — the same choice as §7.9 and for
the same reason. It costs nothing extra and it fixes `LogoutFlow`'s
`ConfirmDialog` too, which sits outside any `<main>` today and would have
acquired the bug the first time anyone moved it. `Dashboard.tsx` is not touched
at all, so there is no re-indentation in the diff.

Re-measured after: both backdrops 0,0 x viewport, `dialogFullyOnScreen` true,
and a centre offset of exactly 0 while the page is scrolled to its end.

A full audit followed, at runtime rather than by grep, because "does this
element establish a containing block" is a computed-style question. Every
element on the signed-in pages that creates one was enumerated with its fixed
descendants: `<nav>` (`backdrop-filter: blur(8px)`), each page's `<main>`
(`dsup`), and the ScoreBadge ring's `<circle>` elements (a rotation transform).
All three now report zero fixed descendants, and the only `position: fixed`
rules in the codebase were `.dialog-backdrop` and the combined-report drawer's
inline one — all of them portalled themselves. (The drawer has since become a
tab, §7.8, so `.dialog-backdrop` is the only one left.) `dsspin` and the unused `dsbar` also
animate `transform`, but neither is applied to an element with descendants.

### 7.10 What the tab has to say about itself

§5.9 makes COMBINED the ungrounded half of the product, and a reader who does
not know that will weigh it exactly like the cited per-dependency plan Phase 8
produces. The distinction is not visible in the output — a prioritized list of
real packages with real CVE ids looks equally authoritative either way — so it
is stated on the tab, in the wireframe's own quiet paragraph: one model call
over signals already stored, no source documents retrieved, and the cited
surface is elsewhere.

Above the summary sits §10 Phase 7's "cached banner with `generated_at`",
carrying the "regenerate requires a rescan" hint it belongs with: it names the
model that wrote the report, says the answer is stored against this scan, and
says a fresh one needs a new scan. That banner is doing two jobs — it is the
cache made visible, and it is the warning Phase 9's rescan confirmation will
act on.

The summary is the only model-written string on the page. It is rendered by a
small paragraph-and-bullet reader that unwraps `**` and backticks and never
touches `dangerouslySetInnerHTML` — a renderer that turned this text into HTML
would be a renderer that could be talked into producing a link. Each fix's
action sentence is assembled from the structured fix instead, because §5.8 has
no field for per-fix prose and inventing one would put an unvalidated sentence
beside a validated row. Per §6.7, `fixAction` is exported and its finished
sentences are asserted whole rather than by substring — and now that the fixes
are a table, the CVE list has a column of its own rather than a clause tacked
onto that sentence.

### 7.11 Two seams that were not seams

Both were found by tests behaving oddly rather than failing, which is the
§3.13 family again.

`generate(scan, *, complete=complete_json)` binds the client at import. Every
production caller omits the argument, so patching the module attribute changed
nothing about the path under test — a test that believed it had stubbed the
model was reaching the live endpoint. The default is resolved inside the
function now.

`from apps.scanning.background import spawn` did the same to the suite's
`no_background_threads` fixture, which patches `background.spawn`. The
double-click test spawned a real thread that deadlocked SQLite. `background` is
imported as a module.

Neither is a Python subtlety worth a paragraph on its own. What they share is
the shape: a test that passes while doing something entirely different from
what it claims to do.

### 7.12 The model D11 names no longer exists

The first live call this project ever made returned 404. Not a bug in the
client: Groq had decommissioned `llama-3.3-70b-versatile`, which §6's
configuration registry and D11 both name as the default. Asking the account's
`/openai/v1/models` for what it can actually reach returned no Llama chat model
at all — the general-purpose options were `openai/gpt-oss-120b`,
`openai/gpt-oss-20b` and two Qwen 27Bs, alongside Whisper, prompt-guard and TTS
models that are not chat models.

The code default is now `openai/gpt-oss-120b`. That satisfies what D11 actually
requires — a Groq-hosted generator at temperature 0 in JSON mode — and D11's
substance is the *provider* and the determinism settings, not the checkpoint:
the reason the judge in Phase 13 must be Gemini is that self-judging is a
reviewer attack, and that argument is unaffected by which Groq model generates.
`plan/` is not edited here; §6's table names a model that no longer exists and
that is the plan's to correct.

Two things follow, and the second is the more important one.

**A retired model is now its own failure.** Groq answers 404, which arrived as
`UpstreamNotFound`, which nothing mapped — so the report failed with "Something
went wrong while writing this report" and a traceback logged as an unexpected
error. The reader was told nothing and the operator was told the wrong thing.
`LlmModelUnavailable` now carries it: the user still sees the deployment-fault
message, because which model is configured is not their problem, and the log
line names the model, which is the one fact whoever fixes it needs. It is not
retried — a retired model stays retired.

**Models are retired on a rolling schedule, so this will happen again.**
`.env.example` says so and points at Groq's model list. Any redeploy after a
long gap should check it before assuming a failed report is a code fault.

The generation was then verified end to end against the live provider, which is
the first time any of Phase 7 ran outside a mock. On the seeded
`checkout-service` fixture — lodash 4.17.19 with CVE-2021-23337, a deprecated
request 2.88.2, a stale moment 2.24.0 — one request produced three fixes, all
naming real scanned rows, with `current_version`, `cves` and `severity` matching
the stored signals exactly because §7.1 copies them rather than reading them
back from the answer. The second request served the stored row with no call, so
the phase's headline claim holds against the real provider and not only against
a fake.

One detail is worth keeping, because it is §7.2's trade-off made visible.
`request` came back as `investigate` with no replacement named — not as
`replace` with "axios". That is correct: the prompt carries `deprecated: true`
and deliberately not npm's deprecation message, so the model had no successor to
name and declined to invent one. The successor suggestion is exactly what
Phase 8 recovers, quoting the changelog beside the claim.

### 7.13 Advisories are not CVEs, and the first live report said so out loud

The first COMBINED report generated on production read:

> Fixes CVE-2026-25645, CVE-2024-47081, CVE-2024-47081, CVE-2026-25645.

Every identifier real, the sentence nonsense. `rv-accept-mixed`'s PyPI
`requests` carries four OSV advisories covering two underlying vulnerabilities
— `PYSEC-2026-2275` and `GHSA-gc5v-m9x4-r6x2` both for CVE-2026-25645,
`GHSA-9hjg-9r4m-mvj7` and `PYSEC-2026-1872` both for CVE-2024-47081. OSV
returning several records for one vulnerability is the normal case rather than
an edge, and `UNIQUE(dependency_id, osv_id)` admits them all, correctly: they
*are* different advisories. `_row` then mapped advisories straight to `cve_id`
with no dedup, and §5.8's `cves` inherited the duplicates — so Phase 9's JSON
download would have carried them too.

Deduplicated at the source, order-preserving, so the worst-CVSS identifier
still leads. The advisory *count* is untouched: four advisories is the true
number and `advisory_count` still says four, because that is what the drill-down
shows and what the scanner measured. The two facts are different and the fix
keeps them different.

Why no test caught it: every fixture in the suite gave each advisory its own
CVE, which is the shape a hand-written fixture naturally takes. The real world
produced the collision on the first try. There is now a test built from the
exact prod rows.

This is §6.7's family again — a sentence assembled from correct parts that no
assertion reads end to end — and it is the first time the project has hit it in
generated output rather than in template prose. The general lesson stands
unchanged: **assert the finished sentence, and read it once with your own
eyes.**

The same conflation was in the dependency table's finding chip, which said
"4 CVEs" about four advisories over two CVEs, and in the login page's specimen
row that mirrors it. Both now say "advisories".

Two details of that choice are worth recording, because the obvious fix is the
wrong one.

**The number did not change, only the word.** A chip counting *distinct CVEs*
would read "2" above a WhyFlaggedPanel that says "4 advisories, counted as 4" —
§5.2's count signal scores advisories, so the panel is explaining the number
the formula used. A chip that disagreed with the arithmetic one click below it
is §4.11's defect wearing a different label. "Advisories" is both the truthful
word and the one that keeps the two surfaces consistent; every other place in
the UI that counts these already said it.

**The wireframe says "CVEs", and this departs from it.** That is a departure
from the wireframe's *word*, not its design — the chip keeps its position,
severity colour and CVSS suffix. The wireframe's sample data gives every
advisory its own CVE, so it never had to distinguish the two, and a binding
visual specification does not settle a question about data it did not model.

---

## Phase 8 — PER_DEPENDENCY RAG agent: the thesis feature

§5.9 specifies this phase more tightly than any other: eight named nodes, two
named thresholds, a named chunk size and three paragraphs of discipline about
the vector store. Most of what follows is therefore not "what we chose" but
"what the spec's sentences turn into once they are code", and where a decision
was genuinely open it is marked as such.

### 8.1 The registry's repository URL is mined, never requested

§10 Phase 8 opens the chain with "package -> repo URL (registry metadata) ->
parse owner/repo (**same SSRF discipline**)". That parenthesis is the whole
design of `rag/fetch_docs.py`.

A registry's `repository` field is text a package author typed. It arrives here
as a string that may say anything: a GitLab URL, an internal host, a
`file:///`, a URL with credentials in it, or `https://github.com@evil.test/o/r`
— which reads as `github.com` to anything that looks at `netloc` instead of
`hostname`. **Nothing in this module ever requests that string.** It is parsed
for an `owner/repo` pair, both halves are matched against
`^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`, and the request that goes out is built
from the `GITHUB_API` constant and those two segments. `_github_repo` returns a
pair rather than a URL so that there is no code path in which the input string
could become a request.

That is the same structure §5.6 uses for a pasted repository URL, and the tests
are shaped the same way: eleven strings that must fail to parse, asserted
against the parser rather than against the network, because the claim is that
the network is never reached rather than that it refuses.

Six spellings are accepted because the two registries genuinely serve all of
them: `https://…`, `git+https://…`, `git://…`, `git@github.com:o/r.git`,
npm's `github:o/r` shorthand, and a bare `o/r`.

### 8.2 An empty-handed retrieval is a result, not an error

§5.9's graph has no retries and no loops, so every failure in retrieval has to
resolve to something the next node can carry. `FetchResult` therefore always
returns, and `reason` names which of five things happened:
`no_repository_url`, `not_github`, `repository_unreachable`,
`documents_too_large`, `no_documents`.

The five are a closed set because the *trace* groups on them. "We could not
find the changelog" and "the changelog said nothing relevant" are different
findings about a package, and S3 needs to tell them apart; collapsing both into
"low confidence" would throw away the distinction at the point it was measured.

`repository_unreachable` is worth its own value for the same reason: a rate
limit clears on its own and a missing changelog does not, so the two are not
one condition. They are accumulated on a `_RepoReader` instance rather than a
module-level flag — five or six requests contribute to one verdict, and a
module-level flag would be shared by every generation thread in the worker, so
the first per-dependency report to hit a rate limit would make every concurrent
one claim the same thing.

### 8.3 Chunk ids are content digests, because a trace outlives its collection

§5.9 asks for "stable chunk ids" and §10's acceptance asks for byte-identical
output on a repeat request. Both are the same requirement seen from two ends.

A positional id (`chunk-7`) is not stable: it changes when the document above
it changes. A random id is not stable at all. The id here is
`sha256(blob_sha + path + text)[:12]`, so the same bytes produce the same id on
any machine, in any process, forever — and two chunks with the same id are the
same text from the same file, which makes `add_chunks` idempotent and lets
`ensure_corpus` be re-entered safely after a generation failed halfway.

Twelve hex characters rather than a full digest, and that is a decision about
the *model*: it is asked to copy these back as citations, and every character
is a chance to mistype one. 48 bits over the ~120 chunks one dependency can
have is a collision probability far below the rate at which anything else in
this pipeline is wrong. The blob sha is inside the digest because the trace's
claim is that a citation names *the bytes that were read* — the same release
notes in a rewritten file are not the same chunk.

### 8.4 The store converts distance to similarity at its own boundary

§5.9 names `GROUNDING_MIN_SIM=0.30`, and Chroma returns a *distance*. The two
are opposite senses of one measurement, so a comparison that read the wrong one
would pass exactly the retrievals it should refuse — silently, with no error
anywhere.

The collection is therefore created with `hnsw:space = cosine` (the default is
squared L2, which is unbounded above and would make a 0.30 threshold
meaningless), and `chroma_store.query` converts `1 - distance` to a similarity
in [0, 1] before anything else sees it. One conversion, at one boundary,
clamped — a cosine distance can come back a hair outside its range and a
similarity of 1.0000000002 printed beside a chunk reads as a bug.

Everything downstream — the grounding check, the stored report, the trace, the
citation pane — handles similarities only. The word "distance" does not appear
in any of them, and that is enforced by there being no way to obtain one.

### 8.5 `version_tag` exists because §5.9 says this bug is silent

§5.9 spends a sentence on it: "the **resolved** version string is used both at
write-tag time and read-filter time (a manifest-range string on one side causes
silent empty retrieval -> false low-confidence)".

A row whose `resolution` is `range_latest_approx` has a `declared_specifier` of
`^4.17.0` and a `resolved_version` of `4.17.21`. Tag with one, filter with the
other, and the query matches nothing: no exception, no warning, an empty result
that the grounding check then reports as low confidence. The product would say
"there is not enough source material to answer this" about a package whose
changelog it had just downloaded and embedded.

`version_tag()` is the single function both sides call, so the two cannot
disagree, and it maps `None` to `""` rather than omitting the key — a metadata
key that is absent on write and filtered on read is the same silent miss by
another route, and Chroma's `where` cannot express "missing".

There is a test for it, and the test's shape is the point: it asserts an
**empty list**, which is what this defect looks like from the outside.

### 8.6 The dependency row carries its report state, for §7.7's reason

§7.7 added `combinedReport` to the scan payload because the only route that
answers "does this scan have a report?" is the POST that *generates* one — so a
page that asked on load would bill a model call for opening a tab.

Phase 8 has the same problem one level down and answers it the same way:
`DependencyOccurrenceSerializer` grows `report` — `{id, status, generatedAt}`,
never the body. Three consequences, all of them the point:

* the drawer opens on a stored plan with **one GET and no POST**;
* the button can read "Remediation" on a row that has one and "Remediate" on a
  row that does not, so the control says whether pressing it spends anything;
* the whole table's worth of that costs **one query**, via a `Prefetch` with
  `to_attr` and an `only()` — a per-dependency report carries every retrieved
  chunk in full, and fetching those to render a status pill would pull the
  corpus of every report on the page across the wire.

`to_attr` rather than a plain prefetch so the serializer can tell "prefetched
and empty" from "not prefetched", which is the difference between reading a
list and issuing a query on a route that renders up to 300 rows.

### 8.7 A dependency the scan did not flag has nothing to remediate

`POST /api/dependencies/{id}/report/` refuses two kinds of row with 409
`dependency_not_reportable`.

The unassessable row is the easy half: §5.2 never measured it, so a remediation
plan for it would be built on nothing at all.

The **clean** row is the decision worth recording, because a model would
happily produce something for it and what it produced would read like advice
about a dependency that has no problem. §10 Phase 8 puts the control on flagged
rows; the rule is stated in `services.py` where it can be tested, and the
button agrees with it. An endpoint whose contract is "whatever the button
sends" is an endpoint with no contract.

### 8.8 The graph is linear, and the branch lives inside a node

§5.9 lists eight nodes and says "single pass, no loops, no retries". It also
puts the deprecation branch *inside* `frame_query`: the decision changes the
question that is asked, not the sequence of steps taken.

Modelling that as two nodes with a conditional edge would draw better and would
be a deviation from the binding spec for the sake of the drawing. The LangGraph
node ids are §5.9's names exactly, so a reader holding File A can follow a
trace through the code without a translation table, and the branch is recorded
in the state and stored on the trace — which is what makes it analysable, since
S3 groups on `branch_taken` and not on a graph shape.

Cost is bounded by construction rather than by a budget: one generation is one
Groq call, there is no loop that could make it two, and no tool the model can
ask to have run. `persist` comes before `cleanup` for the same reason history
is written before retention deletes (§5.7) — if cleanup fails the cost is a
stale index Phase 9's sweep collects, where the reverse order would destroy the
evidence for an answer that had just been given.

### 8.9 Every heavy import is inside the function that needs it

Measured on this machine, `manage.py smoke_memory`:

| step | RSS |
|---|---|
| baseline (Django loaded) | 73.3 MB |
| after a request cycle | 76.3 MB |
| after a background scan thread | 80.6 MB |
| after the fastembed model loads | 228.9 MB |
| after one embedding | 232.9 MB |
| **after `langgraph` compiles a graph** | **250.4 MB** |
| **after a Chroma write + query** | **281.5 MB** |

So Phase 8's two new libraries cost ~49 MB on top of the embedding model's
~150 MB, against a 512 MB tier (§8). Phase 1 measured the same command at
274.5 MB on Render itself (§1.13), which puts the projected production peak
around 320 MB — comfortable, and worth re-reading from a Render shell before
the tag.

> **That conclusion was wrong, and the table above is the evidence of how.**
> The first per-dependency generation on production was killed: "Ran out of
> memory (used over 512MB)". Every number here is a *settled* RSS measured
> between steps, the embedding step embedded one short sentence rather than a
> changelog, and the real peak for the real workload was 403 MB before the
> platform's own overhead. **§8.15 has the corrected measurements and the fix.**
> The reasoning in the rest of this section about lazy imports still holds and
> is what keeps the idle worker at 80.6 MB.

The number that matters more is the one this table does not show. **A web
worker that has never generated a per-dependency report holds none of it.**
`chromadb`, `langgraph` and `fastembed` are imported inside the functions that
use them — `chroma_store._get_client`, `graph.build_graph`,
`embeddings.load_model` — so the resting footprint of a worker serving the
dashboard is the 80.6 MB row, and the 281.5 MB row is what one background
generation thread costs while it runs. Moving any of those three imports to
module scope would turn a peak into a floor.

The embedding model is a process-wide singleton behind a lock, and the lock is
not decoration: two generations starting together would otherwise each build
their own ~150 MB model, which on this tier is not a slowdown but an OOM that
kills the worker for every user.

### 8.10 An invented citation is dropped; an invented package is not

Both are the model naming something that does not exist, and they are answered
differently on purpose.

A fix naming a package this repository does not have is an instruction a reader
may act on, and §7.3's argument is that a plausible wrong row is the most
damaging thing this surface can print. It gets one repair retry and then fails
the generation.

A citation naming a chunk that was never retrieved **cannot render anything**:
the pane displays retrieved chunks and highlights the cited ones, so an
unresolvable id highlights nothing. Dropping it costs the reader a highlight;
failing the generation over it would cost them the answer.

That asymmetry is why citation resolution is forgiving in the one direction it
can safely be: an id is matched case-insensitively, stripped of brackets, and
accepted on an unambiguous prefix of eight or more characters. A model that
truncated a 12-hex id has not cited a different chunk, and the prefix rule can
only ever resolve to something that *was* retrieved.

### 8.11 The trace is decoupled from the reports cascade, and that is a schema fact

§10 Phase 8: "trace decoupled from the reports cascade so it survives rescans".
`agent_execution_traces` lives in `apps/research/` with `scan_history` and
`dependency_history`, and like them it has **no foreign key out of the app**.

The trace table is the sharpest case for that rule. The `reports` row it
records *does* cascade with its scan under §5.7, so an FK there would delete
S3's raw data every time a user pressed Rescan. `source_report_id` and
`source_scan_id` are plain UUID columns, and by the time most of these are read
both rows they name are gone. There is a cascade test that asserts exactly
that: generate, rescan, report gone, trace intact, both ids now dangling.

`retrieved_chunks_json` stores **every** chunk retrieved, not only the cited
ones, because §5.1 says so and because the difference is what makes the dataset
able to measure retrieval quality rather than the model's citation manners. A
chunk that scored 0.31 and was ignored is evidence; a chunk that was never
written down is not.

### 8.12 The low-confidence path still calls the model

§5.9 says `generate` is "exactly one Groq call" and, separately, that a
low-confidence run is "instructed to state insufficient information rather than
guess". The second is an instruction about the *content*, not an instruction to
skip the call, and the difference matters.

The scan has measured real things about a flagged dependency — advisories, a
fixed version an advisory names, a deprecation flag. A page that refused to say
any of them because a changelog could not be found would be withholding
information it has. So the ungrounded system prompt permits the model to
restate measurements and forbids it to describe migration steps, breaking
changes, replacement APIs, or what a release contains.

One detail that is easy to get wrong: on the low path the retrieved chunks are
**not** put in front of the model. They are still recorded in the trace and
still shown in the pane — the study needs what was retrieved and rejected, and
the reader needs to see why the answer is short — but a prompt that says "you
have insufficient information" above five quoted passages is asking to be
disbelieved.

### 8.13 API additions to §5.5

One route, exactly as §5.5 specifies:

```
POST /api/dependencies/{id}/report/   200 cached | 202 started | 409 busy
```

Plus one field on an existing payload rather than a route of its own:
`GET /api/scans/{id}/dependencies/` and `GET /api/dependencies/{id}/` grow
`report` — `{id, status, generatedAt}` or null (§8.6).

`GET /api/reports/{id}/` grows three fields that are null on every combined
row: `citations`, `retrievedChunks` and `groundingConfidence`. All three travel
with the answer rather than behind a route of their own, because the citation
pane is not a detail view of the report — it is the evidence the report is read
*against*, and a surface that could render the claim before the evidence
arrived would be rendering an uncheckable claim, however briefly.

The 409 body carries `reportId` for the same reason Phase 7's does, and the
status-code mapping is shared by both POSTs (`views._report_response`) so the
two cannot drift.

### 8.14 What the live run found that the suites could not

The suites were green — 618 backend, 157 frontend — before any of this was
looked at in a browser. Three defects came out of the first real run, and the
third is the most interesting thing in the phase.

**The pane told the reader the number meant its own opposite.** The citation
summary read "Similarity is cosine distance to the question the agent searched
with". §8.4 exists precisely because those are opposite senses, and the
sentence on screen — the one explaining the evidence — named the wrong one. A
reader taking it literally would read 0.74 as "far away". Every substring
assertion around it passed; nothing had read the sentence.

**One banner sentence covered two different findings.** §5.9's gate fails when
retrieval found nothing *and* when what it found was too weak, and the banner
said "did not find documentation close enough to the question" in both cases.
On the nothing-retrieved path that is wrong — there was nothing to be close to
— and it contradicted the pane one column to its right, which was explaining
that the repository may not publish a changelog at all. The banner now branches
on `chunks.length`, and the two sentences agree.

**Retrieval can clear §5.9's gate and the answer still cite nothing.** This one
was only visible because the run was live. Generating against a real `django`
row: its repository publishes no `CHANGELOG.md` under any name we try, so the
fetcher fell back to `README.rst`, and three passages of Django's README
cleared the gate at 0.51 similarity over 2,573 characters while saying nothing
whatever about the yanked release the question was about. The model behaved
correctly and cited none of them, and said so in its summary.

The *page* then showed a plan with no caveat on it, because the only caveat it
had was keyed on the grounding flag.

The gap is real and it is not a threshold-tuning problem. §5.9's check measures
whether retrieval **found** something; a citation count measures whether the
answer **used** it. This phase's claim is "every claim checkable against the
exact retrieved text", and an uncited answer is not checkable. So there is a
third banner: *Nothing cited* — retrieval found N passages, the plan rests on
none of them, read it as built from the scan's own measurements. §5.9's
threshold is untouched, because it is doing its job correctly; what was missing
was the page saying what the threshold does not cover.

**A fourth question for any confidence flag: does the flag measure the thing
the reader is about to rely on?** "We retrieved something relevant" and "the
answer is grounded in it" are two claims, and a surface that reports only the
first will eventually show an ungrounded answer under a clean bill of health.

One non-defect is worth recording so the next person does not chase it. In the
browser pane the drawer appeared frozen on "Reading the changelog…" long after
the server had finished, and eleven GETs had been made for a report that was
already `completed`. The cause is the pane, not the product: it reports
`document.hidden === true` permanently, and `usePolling` stops scheduling ticks
while the document is hidden (by design — a backgrounded tab must not poll a
sleeping Render instance all night). Overriding `document.hidden` and
dispatching `visibilitychange` made the generating -> completed transition work
first time. The same override is needed for any future check of a polled
surface in that pane. Recognising a familiar shape is not the same as
establishing a cause (§5.11), so this was confirmed by changing one thing and
re-running rather than by assuming.

### 8.15 The free tier killed the worker, and the instrument that was meant to catch it was measuring the wrong number

Phase 8's first generation on production — `request@2.88.2` in
`rv-accept-monorepo`, which is the case §10's acceptance names — took the
instance down. Render's event log is unambiguous:

> **Instance failed: cr82h — Ran out of memory (used over 512MB) while running
> your code.**

The application log shows why it left no traceback: fastembed logs "Loading
embedding model", the five model files download from HuggingFace, one more
request is served, and then the process simply stops and Render starts a new
one. An OOM kill is delivered by the kernel, so nothing in Python gets to say
anything about it. The report row was left on `running`, which `expire_stale`
reaped five minutes later into "This report stopped before it finished" with a
Try again beside it — the recovery path behaved exactly as designed, and retrying
would have killed the worker again.

**Why §8.9 missed it.** Two faults, and the second is worse than the first.

*`smoke_memory` measured settled RSS, not peak.* It marked RSS **between**
steps, so it reported the footprint after each step had finished allocating. A
memory cap does not act on settled footprint; it acts on the highest instant.
Sampling RSS on a background thread every 5 ms through the same sequence gives
403 MB where the marks said 281.5 MB — a 122 MB spike that happened between two
marks with nothing watching.

*And the workload was not the workload.* The embedding step embedded one short
sentence. What `ensure_corpus` actually does is embed every chunk of a
changelog, and forty 1,200-character chunks is an ordinary one. One sentence
allocates almost nothing, so even a correct sampler would have reported a
comfortable number for a sequence that dies.

**Where the memory went**, on the same 40-chunk corpus:

| configuration | peak | settled after embedding |
|---|---|---|
| ONNX defaults, one batch of 40 — *what was deployed* | **403.0 MB** | 374.6 MB |
| `enable_cpu_mem_arena=False`, `threads=1` | 334.4 MB | 247.0 MB |
| both, plus batches of 8 | **266.9 MB** | 245.9 MB |
| both, plus batches of 4 | 257.3 MB | 246.7 MB |

Two independent levers, and they fix different things.

**ONNX Runtime's CPU memory arena is the larger one.** It reserves a block far
bigger than a 22 MB MiniLM needs and then keeps it for the life of the process:
127 MB of the resting footprint of a worker that has generated once and may
never generate again. `fastembed` 0.8 exposes it (`EXPOSED_SESSION_OPTIONS`), so
turning it off is a constructor argument rather than a fork. `threads=1` goes
with it — this process has one gunicorn worker and generation already runs off
the request path, so intra-op parallelism inside one embedding buys latency
nobody is waiting on and costs a thread pool's worth of allocators.

**Batching is the second.** Forty chunks in one `embed` call allocates ~160 MB
transiently. Eight at a time caps that at ~20 MB for identical total work.
Eight rather than four because the two are within 10 MB of each other and eight
is half the ORT invocations.

Neither lever changes a vector. The same text produces the same embedding with
the arena off and in any batch size, which is asserted rather than assumed —
§10's determinism acceptance would otherwise be in question, and "we made it
fit by changing the answers" is not a fix.

After both, the corrected `smoke_memory` — now sampling peak, now embedding a
real corpus, now going through `rag.embeddings` so it measures the
configuration production loads rather than one of its own — reports **279.3 MB
peak** locally. That leaves ~233 MB for the platform delta (Render runs Python
3.14 where this machine runs 3.11, under gunicorn with eight threads, in a
worker that has already served requests). The configuration that died had only
109 MB of room for the same delta.

One further guard that is cheap and not strictly required by the measurements:
embedding is serialized across threads by a module-level lock. Two generations
embedding at once would stack their transients, and on this tier the one thing
the process must never do is exceed 512 MB. Generation is already a background
thread, so the cost is latency on a second concurrent report rather than a
blocked request.

**The lesson is about instruments, not about memory.** §8.9's table was not a
lie; every number in it was real, and the conclusion drawn from it was still
wrong, because the numbers answered a different question from the one being
asked. A measurement that is accurate about the wrong quantity is more
dangerous than no measurement, because it ends the investigation. §8 of File A
named this risk and asked for exactly this command to be re-run in Phase 8 —
the control existed, was run, and passed. What it needed was to be run **on
production**, which is what §10's acceptance says and the one step that could
not be skipped.

So: **a verdict reads the number the failure mode acts on.** `smoke_memory`
prints both columns now and gates on the peak, and its 80%-of-budget warning
would have fired at 403 MB had it been applied to the right one.

### 8.16 What the production acceptance run established, and the one criterion it did not

After §8.15's fix, two generations ran on production against the acceptance
fixtures with `/api/health/` polled every five seconds throughout. Neither took
the instance down, where the unbounded configuration had killed it on its first
attempt.

One bonus observation from the wreckage of that first attempt: the report row it
stranded on `running` was reaped five minutes later by `expire_stale` into "This
report stopped before it finished. Please generate it again", with a Try again
beside it, and the retry then succeeded. That path had only ever been exercised
by a unit test; an OOM kill is the condition it was written for and it behaved
exactly as designed.

**`request@2.88.2`** (`rv-accept-monorepo`) — retrieved five chunks of the real
`CHANGELOG.md`, cited one, `grounding: sufficient`, one Groq call,
`openai/gpt-oss-120b`. The repeat request answered 200 with a byte-identical
body and an unchanged `generated_at`, which is §10's determinism criterion in
its observable form.

And it came back `fix_type: investigate`, `replacement_package: null` — **not**
the "replacement-framed cited plan" §10's acceptance names for this package.
That is worth being precise about, because the code did what it should.

`request`'s changelog is 69 KB, reverse-chronological, and was chunked whole —
nothing was truncated, which was the first thing suspected and the wrong answer.
The five nearest chunks to the query scored 0.5596, 0.5564, 0.5502, 0.5338 and
0.5329, and all five are release notes from 2014-2015: lists of PR links and
terse bug fixes. The spread across ~60 chunks is about two hundredths. The model
read them and said so in its own summary: "The changelog excerpts (e.g. v2.54.0)
only list bug fixes and do not mention a successor or migration guide, so the
documentation provides no direct replacement recommendation."

It is right. `request`'s changelog never names a successor. npm's deprecation
message points at **issue #3142**, and issue and discussion retrieval is
condition D of S3 — D13, deliberately management-command-only and provably
unreachable over HTTP, which is to say explicitly not Phase 8. So §10's example
was chosen on the assumption that this package's changelog carries its own
migration advice, and it does not. §7.12 recorded the same shape one phase
earlier and concluded "recovering that suggestion, with a citation, is Phase 8's
job". Phase 8 recovered the changelog, with a citation, and the suggestion was
never in it.

That is a finding about where the information lives, which is the thing S3
exists to measure, rather than a defect to fix here.

**The harder half of the same observation.** Those similarities are the real
result: **0.55 against a 0.30 threshold, for passages that answer nothing.**
§5.9's gate measures whether retrieval found text of the right *kind* — this is
a changelog, the query is about a package — and at that it succeeded. It cannot
measure whether the text bears on the question, because a cosine similarity
between an embedded question and an embedded paragraph is not an entailment
check. Homogeneous corpora are where that gap is widest: sixty chunks of
near-identical release notes are all equally close to everything.

§8.14's banner catches the case where the model cites nothing. It cannot catch
this one, where the model cites a passage that does not support the claim, and
nothing short of a second model judging the first could. What stands in for it
here is the generation's own prose, and on this run that prose was honest
without being asked twice. That is not a guarantee, and it should not be
presented as one.

**`left-pad@1.3.0`** (`rv-accept-mixed`) — the nearest available case to §10's
"unresolvable repo". Its repository has no changelog under any name the fetcher
tries, so retrieval fell back to `README.md` and returned three short passages
at 0.44, 0.34 and 0.32. `grounding: sufficient` on the thresholds, **zero
citations**, and §8.14's *Nothing cited* banner rendered above the summary with
all three passages listed as Retrieved in the pane. The fix came back
`fix_type: replace` with `replacement_package: null`, which is correct: the
registry's deprecation reason is "use String.prototype.padStart()", and a
language built-in is not a package.

So the honest scoreboard for §10's six acceptance criteria:

| criterion | where it stands |
|---|---|
| deprecated-with-successor -> replacement-framed cited plan | cited plan from real changelog text, yes; replacement framing, no, for the reason above |
| unresolvable repo -> insufficient information, fully traced | no fixture package lacks a repository URL; suite-verified, and `left-pad` reached the same answer through the README fallback |
| trace survives a rescan | suite-verified; `agent_execution_traces` has no HTTP surface until Phase 10 and the free tier has no shell |
| Chroma chunk count 0 after persist | suite-verified against a real embedded Chroma |
| repeat request -> byte-identical output | **passes on production** |
| RSS re-recorded < 512 MB | the failure, now fixed; demonstrated by two generations with health at 200 throughout, but **no number recorded from the instance** - Render's free tier has no shell |

Three of those are verifiable only in the suite on this tier, and saying so is
better than implying a prod run covered them. The two that could be checked on
production were checked there.

---

## Phase 9 — Retention guards, downloads, hardening

### 9.1 The rescan guard is on value, not on time

§10 Phase 9 asks for a confirmation "when the latest scan has >=1 report", and
adds the constraint that decides the implementation: **"value-based guard — no
cooldown timers."**

The distinction is not stylistic. A cooldown refuses a rescan for being *soon*,
which is the wrong quantity twice over: it refuses a cheap rescan of a
repository that has generated nothing, and it permits an expensive one a minute
later. What a rescan actually destroys is the scan's reports (§5.7 deletes the
prior scan and everything cascading from it, this table included), and
regenerating one is a fresh model call. So the guard asks how much would be
lost, refuses only when the answer is more than nothing, and refuses it once.

`reports_at_risk` lives in `apps/scanning/retention.py` rather than in the view,
because it is the price of that module's rule rather than a separate feature —
the same file that documents why the cascade exists is the file that can say
what it costs.

Two decisions are inside the query.

**It counts every scan of the repository, not "the latest scan".** Normally
those are the same set: retention leaves one scan standing. Not always — a scan
that *fails* prunes nothing, so a repository can hold a completed scan with two
reports plus a newer failed one. "The latest scan" answers zero there, about a
rescan that is about to destroy two reports.

**It counts only completed reports.** A queued row holds nothing; a failed one
holds an error message. "This scan has 1 generated report" is a false sentence
about a generation that failed, and the number is what the dialog claims it is:
the count of answers that exist.

### 9.2 `1 == True`, and a guard that accepted a value nobody had agreed meant yes

The first version of `_confirmed` read:

```python
_CONFIRMATIONS = (True, "true", "True")
...
return value in _CONFIRMATIONS
```

which accepts `confirm: 1`. Python's `in` compares with `==`, `True` is an
`int` subclass, and `1 == True`. A client sending an integer — a stale
serializer, a form library coercing a checkbox, anything at all — would have
destroyed generated reports on the strength of a value this codebase had never
defined as consent.

It is `value is True` plus an explicit string comparison now. The parametrized
test that found it covers `false`, `0`, `1`, `"yes"`, `"on"`, `"maybe"`, `None`
and `""`, and it was written before the fix.

The general shape is worth stating because the same file argues *against*
strictness forty lines earlier. `_boolean_param` deliberately reads `1`, `yes`
and `on` as true, because a query-string filter that guessed wrong shows the
wrong rows and the reader can see that it did. A confirmation that guesses
wrong destroys work and the reader finds out later. **The right amount of
leniency is a function of what being wrong costs**, which is also why
`?fmt=MD ` is accepted on the download route and `confirm: 1` is not.

### 9.3 Two downloads, one stored row, and one sentence rendered twice

§5.8 is binding on this: "One generation produces one payload serving both
downloads (no second LLM call)." Both formats are re-renderings of columns that
were written once and validated then, so a download of a report generated three
weeks ago costs a SELECT.

The split between them is by *reader*, not by fidelity:

* **Markdown is for a person**, and must stand alone. A file read in a
  downloads folder has no citation pane beside it and no banner above it, so the
  confidence note, the fixes and the cited passages all travel inside the
  document.
* **JSON is §5.8's "machine-parseable task handoff for external coding
  agents"**, so `summary_md` and `fixes` are the stored values in §5.8's own
  snake_case, unrewritten — the same argument `apps/reports/serializers.py`
  makes for passing `fixes` through to the browser unchanged. Everything above
  them is provenance: repository, scan, scoring formula version, grounding
  verdict. An agent handed a bare fixes array knows what to do and not *to
  what*.

Citations in the JSON carry their source path, sha, similarity and text rather
than only a chunk id, because a chunk id is a content digest and means nothing
outside this product. The detail route already returns every retrieved chunk in
full, so this exposes nothing new; it makes the file checkable by whoever
receives it.

**One deliberate duplication.** The fix sentence ("Upgrade to 4.17.21",
"Replace — this package is no longer maintained") is assembled from §5.8's
structured fields in two places: `download._fix_action` and
`frontend/src/components/ReportsTab.tsx::fixAction`. Neither generates it —
§5.8 has no field for per-fix prose, and inventing one would put an unvalidated
sentence beside a validated row (§7.1). Two renderings of one set of structured
facts, worded for two media, is not the drift risk §6.7 warns about: that one is
about a *single* sentence assembled from two sources, where the join is
invisible. Here each rendering is whole, and each is asserted whole.

### 9.4 The caveat has to be inside the file

§8.14 and §8.16 record the shape this product keeps rediscovering: a plan that
reads authoritative with the caveat somewhere else, or nowhere. The drawer
learned it against a real `django` row — retrieval cleared §5.9's gate at 0.51,
the model cited none of it, and the page showed a remediation plan with no
caveat on it, because the only caveat it had was keyed on the grounding flag.

A downloaded file is that failure with the banner removed by construction. So
`download.confidence_note` branches over the same two stored facts the drawer
branches on, and emits one of four paragraphs:

| what happened | what the file says |
|---|---|
| combined report | "Not grounded, by design" — §5.9 keeps COMBINED out of the retrieval graph, so this is a property of the surface rather than a disappointment |
| low confidence, nothing retrieved | "No source material" — a statement about the *package*: its documentation could not be found at all |
| low confidence, weak passages | "Not enough source material" — a statement about *retrieval*: documentation was found and did not bear on the question |
| gate cleared, nothing cited | "Nothing cited" — §8.14's case, and the one a reader cannot detect for themselves |

When the plan cited nothing, the retrieved passages are printed anyway, under a
heading that says so. A caveat claiming that passages were found and none
supported the answer, with the passages withheld, is a caveat the reader cannot
check.

The wording differs from the drawer's deliberately — a file is read without the
pane to point at — and that is a second rendering over one rule, as in §9.3.

### 9.5 Structured logging, and why a thread does not inherit a request

§10 asks for "structured logging (request id, user id, scan id)". The problem it
solves is specific: one gunicorn worker, eight threads, plus background scan and
generation threads, all writing to one stream (§3). A `WARNING` about a rate
limit and an `INFO` about a failed report are interleaved with everybody else's,
and nothing in the line says whose request or which scan produced it. Render's
free tier has no log search beyond the browser's find-in-page, so correlation is
by timestamp, and timestamps collide.

The transport is `contextvars`, and the property that makes it right is one most
people meet as a surprise: **a `threading.Thread` starts with an empty context,
not a copy of its parent's.** A scan thread therefore cannot inherit the request
id of whoever pressed the button — which is the correct answer, because it is no
longer serving that request and will outlive the response by minutes.
`background.spawn` binds `scan_id` explicitly instead, in the same place it does
its connection hygiene, because establishing a thread's context is exactly that
kind of concern.

Two smaller decisions:

* **An inbound `X-Request-ID` is ignored.** Honouring it is a common convenience
  and puts a client-controlled string into every log line the request writes; a
  newline in it forges an entry. There is no tracing system upstream of this
  service whose id would be worth adopting.
* **The context renders as one preformatted field**, empty outside a request.
  A format string with three placeholders cannot omit them conditionally, and
  `[- - -]` on every library message at startup is how structured logging
  becomes noise nobody reads.

The filter order in `settings.LOGGING` is load-bearing: `request_context` runs
before `redact_secrets` because the formatter references the attribute the first
one sets, and a formatter referencing a missing attribute raises *inside*
logging — where the symptom is the line silently not appearing.

### 9.6 What the throttles bound, and what they must not

§10 asks for "DRF throttles on auth + generation endpoints". Scoped, at
20/min for generation and 60/min for auth.

**It is not a spend limit.** The cache already bills a generation at most once
per `(scan, dependency)`, forever (§7.5). What the throttle bounds is the
*request rate* on the two routes that can reach a model at all — the 200-cached
path is cheap but not free, and it is reachable in a loop by anyone with a
session cookie. Both generation routes share one scope, because they share one
wallet: two scopes would hand an abuser two budgets for the same resource.

**The read routes are deliberately unthrottled**, and there is no default
throttle class. The product's own polling loops are the heaviest callers of
those routes — a report panel polls `GET /api/reports/{id}/` every few seconds
while a generation runs — so a blanket throttle would eventually throttle the
product rather than an abuser.

`auth` is 60/min rather than something tighter because `/api/auth/session/` is
reachable unauthenticated, which means DRF keys the bucket on the client IP, and
one office behind one NAT is one bucket. The OAuth entry and callback are not
throttled and cannot be here: they are allauth views wired outside DRF's
dispatch.

**The trap, which is the part worth keeping.** `override_settings(REST_FRAMEWORK=...)`
does not reach these rates, and fails silently. DRF binds
`SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES` as a
*class attribute at import time*; `api_settings.reload()` on `setting_changed`
rebinds the settings object and leaves the class attribute pointing at the
original dict. Measured directly while writing these tests: with `generation`
overridden to "3/min", the class still read "20/min" and five POSTs produced no
429 at all. A throttle test written that way runs at the production rate and
asserts nothing — §8.15's shape exactly, a control that was run and could not
have failed. The suite patches the dict the throttle actually reads.

Throttles stay **on** in the test suite, with the cache cleared per test, for
the same reason: a rate limit that exists only in production is a rate limit
nobody has run.

### 9.7 There is no admin, which is the stronger form of the requirement

§10 Phase 9 lists "admin read-only for research tables". This codebase has no
Django admin at all, and after building one and reading what it would cost, that
is where it stayed.

The requirement exists to stop one thing: the permanent tables (D9 —
`scan_history`, `dependency_history`, `agent_execution_traces`, never deleted by
any trigger) being mutated through an admin. `apps/research/models.py` already
defends them against *cascades* structurally, by having no foreign key anything
can reach. An admin with its usual powers would be the one path left — a change
form, a delete button, and a "delete selected" action over the study's raw data.

A read-only `ModelAdmin` was written, and then found to be unusable. `User`
extends `AbstractBaseUser` with no `is_staff` and no `has_perm`, because GitHub
owns identity and nobody in this product has a usable password (§2).
`AdminSite.has_permission` reads `is_active and is_staff` and raises
`AttributeError` for any authenticated user; every `ModelAdmin` permission check
calls `has_perm`. Making it work means adding `PermissionsMixin` — two join
tables beyond §5.1's twelve — plus a password login to a product whose entire
identity story is that it has none. `apps/research/admin.py` cannot even be
*imported* without the app installed: `admin.site` resolves through
`apps.get_app_config("admin")`.

So the ModelAdmin was deleted and four assertions stand in its place
(`tests/test_hardening.py`), each of which fails the moment the reasoning above
stops holding: the admin app is not installed; no route reaches the research
tables; the `User` model has neither `is_staff` nor `has_perm` and arrives with
an unusable password; and no relation anywhere in the project points at a
permanent table.

If a later phase wants the admin, this section is the thing to re-read first.

### 9.8 "No write call anywhere", checked three ways

§11 lists the OAuth token risk with the mitigation "**no write call anywhere**
(grep-audit Phase 9)". The scope is `repo` because GitHub OAuth Apps offer no
read-only private scope; a token with it can push commits and open pull requests
in every repository its owner can write to. What makes holding one safe is a
single claim, and a grep only answers it about today.

`tests/test_no_write_calls.py` checks it three ways, none sufficient alone:

1. **Structural.** `common/http.py` now refuses a non-GET to a read-only host
   (`api.github.com`), per hop, before the socket is opened. This is the only
   check that binds code nobody has written yet. Per *hop* matters: 307 and 308
   preserve the method, so an open redirect on an allowlisted host could
   otherwise land a POST on GitHub having passed a check made once on the
   original URL. `api.osv.dev` and `api.groq.com` are not read-only hosts
   because both need a POST to ask a question, and neither changes anything at
   the far end.
2. **Topological.** `requests` is imported in exactly one module, so there is no
   second client whose rules the audit does not know.
3. **Textual.** The grep §11 asks for, narrowed to the modules that build GitHub
   URLs at all: none posts, and none names a write verb.

**The audit's first version was wrong, and the way it was wrong is the point.**
It listed "write endpoints" by path — `/pulls`, `/git/refs`, `/git/blobs` — and
flagged `apps/scanning/scanner.py` on its first run. That was a fault in the
test: `GET /repos/{o}/{r}/git/blobs/{sha}` is how every manifest in this product
is *read*. Almost every GitHub endpoint answers both a read and a write
depending on the verb, so a list of paths cannot express the rule. The verb can.

### 9.9 The audit found a second outbound path, in the instrument

`smoke_memory` fetched `https://registry.npmjs.org/left-pad` through a bare
`urllib.request` — no allowlist, no size cap, no retry policy — in the step that
exists to reproduce "a background thread shaped like a Phase 3 scan worker".
§5.6 calls `common/http.py` "the single choke point all outbound HTTP in the
entire project must pass through", and this was a second one.

It is routed through the client now, which fixes two things at once. The SSRF
discipline becomes true again as stated. And the measurement becomes honest in
§8.15's sense: a real worker holds `requests` and a pooled session, so a smoke
test that avoided them was measuring the footprint of a process production never
runs. That is a smaller error than §8.15's — the delta is a library that was
already imported elsewhere — but it is the same error.

### 9.10 The BOLA suite's coverage guard is the part that lasts

§11 says BOLA is verified by a "structural mixin + suite covering **every
route** by Phase 9". Every phase so far added cases for the routes it
introduced, which is the right habit and a weaker claim: a per-phase suite
covers every route somebody remembered.

`test_every_id_route_is_covered` reads `config.urls`, finds every top-level
pattern that takes a resource id, and fails if one is missing from the suite's
table. A Phase 10 route added without a BOLA case turns this red at the commit
that adds it. It was run against a table missing `report-download` before
landing, and failed there — a guard that cannot fail is decoration (§3.13).

Every case asserts **both halves**: a foreign id 404s, *and* the same request
from the owner does not. Without the second, the suite passes identically
against a typo in the URL, a route that no longer exists, or a view that 404s
for everyone. The owner's half asserts "not 404" rather than "200", because
several of these legitimately answer something else for reasons that are not
about ownership — `scan-combined-report` answers 503 where CI has no
`GROQ_API_KEY`, and `repository-scan` answers 409 `confirm_required`, since the
fixture graph holds a generated report and §9.1 refuses to destroy one silently.

### 9.11 API additions to §5.5

One new route and one new answer on an existing one.

```
GET  /api/reports/{id}/download/?fmt=md|json      200 | 400 | 409 | 404
POST /api/repositories/{id}/scan/                 + 409 confirm_required
```

`?fmt` has no default. §10 names both formats and no default, and choosing one
for a caller who did not say is the same invention `_boolean_param` refuses when
asked what `?flagged=maybe` means. Only a *completed* report can be downloaded:
a queued row has no content and a failed one has an error message, and answering
either with an empty document hands the reader a file that looks like an answer.

The 409's body carries `reportsCount` in camelCase, like every other `extra` on
this surface (§7.7, §8.13). §10 writes it `reports_count`; that is the plan
naming a quantity, not specifying a wire format, and one convention across the
API is what keeps the client from having two to remember.

Two implementation notes that are invisible until they bite:

* **`DownloadRenderer` matches any `Accept` header.** The route is followed by a
  *browser*, and DRF negotiates against `DEFAULT_RENDERER_CLASSES`, which is
  JSON alone. Every browser in practice sends `*/*;q=0.8` somewhere in a
  navigation header, so it works — on a wildcard nobody promised. A client that
  tightened its header would get a 406 instead of a file. `JSONRenderer` stays
  first in the list so an `ApiError` on this route still renders in the standard
  envelope.
* **Table cells escape `|`.** A pipe in a manifest path ends the cell early and
  shifts every column after it. The table still renders — with the wrong values
  under the wrong headings, which is the failure mode this product exists to
  avoid.

### 9.12 Error taxonomy

Every `code` this API can return, what it means, and what the reader can do
about it. The frontend branches on `code` and never on message text (§5.6), so
this table is the contract; the messages are free to be reworded and the codes
are not.

| `code` | HTTP | Where | What it means, and what follows |
|---|---|---|---|
| `repo_inaccessible` | 404 | register, scan | GitHub cannot see it with this user's token. Check the URL, or make it public. |
| `no_write_access` | 403 | register | Read-only or fork-and-PR access. §5.6 requires write: the user must be able to act on findings. |
| `private_repo_not_owned` | 403 | register | A private repository belonging to someone else. |
| `already_registered` | **200** | register | Not an error. The body carries the existing repository id and the frontend redirects to it (§2.5). |
| `ecosystem_unsupported` | 422 | register | No npm or PyPI manifest anywhere in the tree. |
| `repo_empty` | 422 | register | No commits. |
| `github_rate_limited` | 503 | register, scan | Upstream limit. Retrying later works; retrying now does not. |
| `github_unavailable` | 503 | register, scan | GitHub is failing or unreachable. Transient by assumption. |
| `github_reauth_required` | 401 | register, scan | The stored token was revoked or expired. **Only a fresh login fixes it** — §2's lesson: a revoked token reported as a temporary outage advises a retry that can never succeed. |
| `scan_in_progress` | 409 | scan | A scan is already running. Not a failure: the client re-reads the status instead of showing one. Body carries `scanId`. |
| `confirm_required` | 409 | scan | **Phase 9.** This repository holds generated reports a rescan would destroy. Body carries `reportsCount`; re-send with `{"confirm": true}`. |
| `scan_not_reportable` | 409 | generate | The scan never completed, so there is nothing to report on. |
| `dependency_not_reportable` | 409 | generate | The occurrence is clean or unassessable — nothing to remediate (§8.7). The UI cannot reach this; the endpoint states the rule anyway. |
| `report_generating` | 409 | generate | Someone else's request got there first. Not a failure: body carries `reportId` to poll. |
| `reports_unavailable` | 503 | generate | Deployment fault — no generator configured. Not the reader's problem, and the log line carries which setting (§7.6). |
| `report_not_downloadable` | 409 | download | **Phase 9.** The report has not finished. |
| `invalid_format` | 400 | download | **Phase 9.** `fmt` was missing or unrecognised. No default is guessed. |
| `throttled` | 429 | auth, generate | **Phase 9.** DRF's own code and detail, kept because the detail names the wait — the one actionable thing a throttled caller can be told. |
| `not_found` | 404 | every resource route | Either it does not exist or it belongs to someone else, and the answer is deliberately the same (§11 BOLA): a 403 on a foreign id confirms the id exists. |
| `not_authenticated` | 403 | every resource route | No session. 403 rather than 401 because DRF answers 401 only when an auth class advertises a `WWW-Authenticate` scheme, and a session cookie does not. |
| `server_error` | 500 | anywhere | A bug. The traceback stays in the logs; the reader gets one sentence. |

Three families, and the shape is deliberate: **4xx the reader can act on**
(fix the URL, get access, confirm), **409 the client can act on without
bothering the reader** (`scan_in_progress`, `report_generating` — both carry the
id to poll), and **503 nobody can act on now** (upstream or deployment), which
is the only family whose advice is "try again later".

### 9.13 What the browser check found

The two new surfaces are overlays, and jsdom has no layout — §7.9 and §7.9.1 are
what that costs. Both were measured in a real browser against a seeded
repository, at 1000x520 scrolled to the bottom, which is the viewport that
turned Phase 7's "cosmetic" defect into 39% of a dialog above the top of the
screen.

The dialog and the toast both sat fully inside the viewport, with the backdrop
covering it and the toast's Dismiss button reachable. Both downloads were
fetched end to end through the dev proxy: correct content types, the specified
filenames, `Cache-Control: private, no-store`, and the per-dependency markdown
carrying its cited passage.

One defect, and it is §6.7's family again. The toast read *"The 2 reports on the
previous scan will be cleared when it finishes"* — where "it" can attach to
either scan, and the one it grammatically prefers is the wrong one. It names the
new scan now. Every substring assertion would have passed; reading the finished
sentence is what caught it.

And one note for the next local check: **a JS-written session cookie cannot
overwrite the HttpOnly one the server has already set** — the browser refuses
silently, and the page bounces to `/login` looking like a broken session. The
seed script pins its session key and repository id so a re-seed keeps working
with the cookie the browser is already holding.

### 9.14 A stored plan advertised as an absent one

The production acceptance run opened the remediation drawer on `left-pad` in
`rv-accept-mixed` — a row whose own button read **"View remediation"**, because
the list route had told it a completed plan exists (§8.6) — and the drawer
rendered **"Generate remediation"** for a couple of hundred milliseconds before
the plan appeared.

It is §3.19 exactly, one surface along. The drawer reads the stored row when it
opens; until that GET resolves, `report` is null, and the render fell through to
`EmptyState`. Every assertion in `reportPanel.test.tsx` passed, because the
harness answered the row and the report in the same tick — **the window did not
exist in jsdom**, so whatever rendered there was untested by construction rather
than by oversight.

What kept it cheap is luck rather than design: pressing the button in that
window POSTs, the cache answers 200, and no model runs. The reader was still
told something false about their own data, and told it in the one place the
product's claim is "the answer is already on disk".

`OpeningState` is deliberately not `GeneratingState`. Nothing is being
generated and no model is running, so the panel does not say one is — the two
spinners carry different claims and a surface that conflated them would be
describing a model call that never happened.

**The durable half is the harness.** §3.19's note says a mock without latency
deletes the state between request and response; that was written about the scan
routes, and `stubFetch` grew `scanDelayMs` for them. The report route needed the
same thing and did not have it. It has `reportDelayMs` now, and both regression
tests were run against the unfixed component first and fail there.

### 9.15 What the production acceptance run established

Against `rv-accept-mixed`, whose current scan carried Phase 7's combined report
and Phase 8's `left-pad` plan — two real generations, so the guard had something
real to refuse and the downloads had real content to render.

| §10 Phase 9 criterion | where it stands |
|---|---|
| rescan with reports **blocks** until confirmed | **passes on production** — one POST, 409, no scan started; the dialog reads "This scan has 2 generated reports" and the count is right |
| ...**then old reports gone, history + traces intact** | suite-verified end to end; **not executed on production** — see below |
| JSON validates against §5.8 | **passes on production** — the downloaded file's three fixes each carry exactly §5.8's ten keys, no more and no fewer |
| BOLA: every route x foreign user -> 404 | suite-only on this tier: it needs a second GitHub account |
| logs clean | suite-only on this tier: Render's free plan has no shell and no log export |

Both downloads were taken as real files through the browser, not fetched in
JavaScript: `repovitals_rv-accept-mixed_combined_<scan>.md` (1,746 bytes) and
`.json` (2,144 bytes), plus the per-dependency plan (2,576 bytes), all with
§10's filename shape.

The per-dependency markdown is the one worth reading. It carries §9.4's
**"Nothing cited"** paragraph — the §8.14 case, on real output — followed by
`## Sources retrieved (none cited)` and all three README passages in full at
0.4379, 0.34 and 0.32. A reader holding that file alone can check the claim the
caveat makes, which is the whole argument of §9.4.

**Why the destructive half was not executed.** Confirming the rescan would
delete both reports — the artifacts Phase 7's and Phase 8's acceptance runs
produced, which the mentor demo opens — and regenerating them costs two model
calls and would not reproduce the same text. The observable half of the guard
(it refuses, it names the count, it starts nothing) is what production can show
that the suite cannot; the cascade itself is the same `finalize` path
`test_rescan_guard.py` walks end to end, asserting the reports gone and
`scan_history` + `dependency_history` intact, with the trace's survival covered
by §8.11's own test. Running it on production would trade two demo artifacts for
a second look at code the suite already pins.

One defect found, fixed inside the tag (§9.14), and re-verified on production
after redeploy: the drawer now opens straight onto the stored plan.
