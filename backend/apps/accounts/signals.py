"""Login-time capture of the GitHub access token.

`SOCIALACCOUNT_STORE_TOKENS = False` means allauth deliberately never writes the
token to its own `SocialToken` table — the one and only stored copy is the
Fernet ciphertext in `app_users.encrypted_github_token`, written here.

This receiver also refreshes the identity columns on every sign-in, which is
what makes `github_user_id` (not the username) the durable key: a user who
renames themselves on GitHub keeps the same row and simply gets a new
`github_username`.
"""

from __future__ import annotations

import logging

from allauth.account.signals import user_logged_in
from django.db import IntegrityError
from django.dispatch import receiver

from .oauth import SCOPES_ATTR

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def capture_github_credentials(sender, request, user, **kwargs) -> None:
    sociallogin = kwargs.get("sociallogin")
    if sociallogin is None:
        return  # a non-social login path; nothing to capture

    extra = sociallogin.account.extra_data or {}
    updated: list[str] = []

    def assign(field: str, value) -> None:
        if value not in (None, "") and getattr(user, field) != value:
            setattr(user, field, value)
            updated.append(field)

    github_user_id = extra.get("id")
    if github_user_id is not None:
        assign("github_user_id", int(github_user_id))
    assign("github_username", extra.get("login"))
    assign("display_name", extra.get("name"))
    assign("email", extra.get("email"))
    assign("avatar_url", extra.get("avatar_url"))

    token = getattr(sociallogin, "token", None)
    if token is not None and getattr(token, "token", ""):
        user.set_github_token(token.token)
        updated.append("encrypted_github_token")
        scopes = getattr(token, SCOPES_ATTR, "")
        assign("token_scopes", scopes)
    else:
        # Not fatal for the session, but every repository call in later phases
        # needs this token; surface it rather than failing opaquely at scan time.
        logger.warning(
            "GitHub login for user %s carried no access token; "
            "repository access will fail until they sign in again.",
            user.pk,
        )

    if not updated:
        return

    updated.append("updated_at")
    try:
        user.save(update_fields=updated)
    except IntegrityError:
        # A GitHub username was recycled onto a different account before the
        # previous holder signed in again. Identity is the id, not the name —
        # keep the session and leave the stale name for the next login.
        logger.warning(
            "Could not update identity fields for user %s: username conflict.",
            user.pk,
        )
        user.refresh_from_db()
        user.set_github_token(token.token if token else "")
        user.save(update_fields=["encrypted_github_token", "updated_at"])
