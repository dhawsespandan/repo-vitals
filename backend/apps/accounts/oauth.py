"""GitHub OAuth2 adapter and provider overrides.

allauth's base `parse_token()` keeps only the access token and drops the rest
of GitHub's token response, but §5.1 stores `token_scopes` — GitHub can grant
fewer scopes than were requested, and knowing which ones we actually hold is
what lets later phases fail loudly instead of mysteriously 404-ing on private
repositories. So the granted scope string is carried on the in-memory token
object through to the login signal.

Two override points are needed to fix the callback URL (see
`get_callback_url` below), not one — the login step and the callback step
build/consume it through entirely different allauth code paths:

  * The **callback** view (`OAuth2CallbackView`) is instantiated directly
    with our adapter class in `config/urls.py`
    (`OAuth2CallbackView.adapter_view(RepoVitalsGitHubOAuth2Adapter)`), so it
    uses `RepoVitalsGitHubOAuth2Adapter` automatically.
  * The **login** step does not: `OAuth2LoginView` delegates to
    `provider.redirect_from_request()`, and the provider — `GitHubProvider`,
    from allauth's own `github/provider.py` — hardcodes its own
    `oauth2_adapter_class = GitHubOAuth2Adapter` (the *stock* class, not
    ours). Passing our adapter to the login view's `adapter_view()` call
    never reaches that path at all, so the redirect_uri GitHub actually
    receives at login time was still being built by the stock adapter's
    `request.build_absolute_uri()` — reproducing this file's whole bug even
    after the callback-side fix landed.

  `RepoVitalsGitHubProvider` below closes that second path, via allauth's own
  documented override point: `SOCIALACCOUNT_PROVIDERS["github"]["provider_class"]`
  (see `allauth/socialaccount/providers/registry.py::ProviderRegistry.load()`).
"""

from __future__ import annotations

from allauth.socialaccount.providers.github.provider import GitHubProvider
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from django.conf import settings
from django.urls import reverse

SCOPES_ATTR = "repovitals_granted_scopes"


class RepoVitalsGitHubOAuth2Adapter(GitHubOAuth2Adapter):
    provider_id = "github"

    def parse_token(self, data):
        token = super().parse_token(data)
        setattr(token, SCOPES_ATTR, data.get("scope", "") or "")
        return token

    def get_callback_url(self, request, app):
        """Build the callback URL from FRONTEND_URL, not from this request.

        §2's whole premise is that the browser only ever talks to one origin
        — the frontend, with /api/* transparently proxied to the backend
        (Vercel rewrite in prod, Vite's dev proxy locally) — so a single
        session cookie works with no CORS. That holds for ordinary fetch
        calls, but the base implementation instead calls
        `request.build_absolute_uri()`, which reflects Django's own real
        hostname (e.g. the Render service), not the origin the browser
        believes it's on.

        GitHub's redirect back from the OAuth dance is a real, top-level
        browser navigation to whatever `redirect_uri` was sent — it cannot
        go through the frontend's proxy unless that URL *is* the frontend's
        own domain. Building it from the backend's own host instead sends the
        browser to a different domain than the one holding the session
        cookie that was stashed at login time, so the OAuth `state` can never
        be found on the way back (allauth reports this as a bare
        `error="unknown"`, with no exception — this is what that meant).

        Building the callback URL from FRONTEND_URL keeps the entire OAuth
        round trip — login, GitHub, and the return — on one origin, exactly
        as intended. The registered "Authorization callback URL" on the
        GitHub OAuth App must match this: the frontend's own origin plus this
        path, not the backend's.
        """
        path = reverse(f"{self.provider_id}_callback")
        return f"{settings.FRONTEND_URL.rstrip('/')}{path}"


class RepoVitalsGitHubProvider(GitHubProvider):
    """Routes the login-initiation redirect through our adapter too.

    Registered via `SOCIALACCOUNT_PROVIDERS["github"]["provider_class"]`
    (§6, `config/settings/base.py`) — see this module's top-level docstring
    for why the callback-view adapter override alone isn't enough.
    """

    oauth2_adapter_class = RepoVitalsGitHubOAuth2Adapter
