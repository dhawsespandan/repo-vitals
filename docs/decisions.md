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
