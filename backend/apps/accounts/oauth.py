"""GitHub OAuth2 adapter.

allauth's base `parse_token()` keeps only the access token and drops the rest
of GitHub's token response, but §5.1 stores `token_scopes` — GitHub can grant
fewer scopes than were requested, and knowing which ones we actually hold is
what lets later phases fail loudly instead of mysteriously 404-ing on private
repositories. So the granted scope string is carried on the in-memory token
object through to the login signal.
"""

from __future__ import annotations

from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter

SCOPES_ATTR = "repovitals_granted_scopes"


class RepoVitalsGitHubOAuth2Adapter(GitHubOAuth2Adapter):
    provider_id = "github"

    def parse_token(self, data):
        token = super().parse_token(data)
        setattr(token, SCOPES_ATTR, data.get("scope", "") or "")
        return token
