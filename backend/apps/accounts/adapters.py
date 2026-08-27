"""allauth adapters.

Two jobs: (1) populate the §5.1 identity columns at creation time, because
`github_user_id` is NOT NULL and allauth's default `populate_user` knows
nothing about it; (2) keep every redirect pointing at the SPA rather than at
allauth's own (uninstalled) HTML pages.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpResponseRedirect

logger = logging.getLogger(__name__)


class RepoVitalsAccountAdapter(DefaultAccountAdapter):
    """There is no local signup; GitHub is the only way in."""

    def is_open_for_signup(self, request) -> bool:
        return False

    def get_login_redirect_url(self, request) -> str:
        return f"{settings.FRONTEND_URL}/dashboard"

    def get_logout_redirect_url(self, request) -> str:
        return f"{settings.FRONTEND_URL}/login"


class GitHubSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin) -> bool:
        # Signing in with GitHub *is* signing up. Auto-signup, no forms.
        return True

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        extra = sociallogin.account.extra_data or {}

        github_user_id = extra.get("id")
        if github_user_id is not None:
            user.github_user_id = int(github_user_id)
        user.github_username = extra.get("login") or ""
        user.display_name = extra.get("name") or ""
        user.email = extra.get("email") or data.get("email") or ""
        user.avatar_url = extra.get("avatar_url") or ""
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        # No password path exists for this model; make that explicit at rest.
        if user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user

    def on_authentication_error(
        self,
        request,
        provider,
        error=None,
        exception=None,
        extra_context=None,
    ) -> None:
        """The real allauth hook (§10 Phase 1: back-nav guard's counterpart —
        a failed login must land the user back on the SPA's login screen with
        an explainable code, not allauth's own bare HTML page).

        Left unhandled, allauth renders a generic "Third-Party Login Failure"
        template with a 401 status and the underlying cause is discarded —
        the earlier version of this method made exactly that mistake: it set
        an attribute nothing ever read and returned None, so this branch was
        dead code disguised as a redirect. Raising ImmediateHttpResponse is
        the actual, documented way to short-circuit allauth's view.
        """
        logger.warning(
            "GitHub OAuth authentication_error: error=%r exception=%r extra=%r",
            error,
            exception,
            extra_context,
        )
        query = urlencode({"error": "github_oauth_failed"})
        raise ImmediateHttpResponse(
            HttpResponseRedirect(f"{settings.FRONTEND_URL}/login?{query}")
        )
