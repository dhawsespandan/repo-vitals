"""`app_users` — §5.1.

Identity is GitHub's; RepoVitals stores no passwords. `AbstractBaseUser` is
still the base class because Django's session machinery depends on its
`get_session_auth_hash()`; the inherited `password` column exists but is always
set unusable. `last_login` is re-declared onto the spec's `last_login_at`
column so there is exactly one "when did they last sign in" field.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """No password-based creation paths — users only ever arrive via OAuth."""

    use_in_migrations = True

    def create_user(self, github_user_id: int, github_username: str, **extra):
        if not github_user_id:
            raise ValueError("github_user_id is required.")
        if not github_username:
            raise ValueError("github_username is required.")
        user = self.model(
            github_user_id=github_user_id, github_username=github_username, **extra
        )
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, username: str):
        return self.get(github_username=username)


class User(AbstractBaseUser):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Survives username changes — GitHub usernames are re-assignable, ids are not.
    github_user_id = models.BigIntegerField(unique=True)
    github_username = models.TextField(unique=True)

    display_name = models.TextField(blank=True, default="")
    email = models.EmailField(blank=True, default="")
    avatar_url = models.TextField(blank=True, default="")

    # Fernet ciphertext. Blank only in the instant between allauth creating the
    # row and the login signal writing the token; never plaintext, never
    # logged, never sent to the browser.
    encrypted_github_token = models.TextField(blank=True, default="")
    token_scopes = models.TextField(blank=True, default="")

    # Overrides AbstractBaseUser.last_login so the column matches §5.1 and
    # Django's own `update_last_login` receiver keeps it current for free.
    last_login = models.DateTimeField(null=True, blank=True, db_column="last_login_at")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "github_username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["github_user_id"]

    class Meta:
        db_table = "app_users"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.github_username

    @property
    def last_login_at(self):
        """§5.1 spells this field `last_login_at`; Django spells it `last_login`."""
        return self.last_login

    def get_github_token(self) -> str:
        """Decrypt the stored token. In-process use only — never serialize this."""
        from .crypto import decrypt_token

        return decrypt_token(self.encrypted_github_token)

    def set_github_token(self, plaintext: str) -> None:
        from .crypto import encrypt_token

        self.encrypted_github_token = encrypt_token(plaintext)
