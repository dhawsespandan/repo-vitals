"""Fernet encryption for the stored GitHub access token.

The token is written to `app_users.encrypted_github_token` as ciphertext and
decrypted only transiently, in-process, immediately before an outbound GitHub
call. It is never serialized to a response, never logged, and never reaches the
browser (§2, §11). A database dump on its own therefore yields ciphertext.

Rotating `TOKEN_ENCRYPTION_KEY` invalidates every stored token; users simply
sign in again (§6).
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import SimpleLazyObject


class TokenDecryptionError(Exception):
    """Stored ciphertext could not be decrypted (usually: key was rotated)."""


def _build_fernet() -> Fernet:
    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured("TOKEN_ENCRYPTION_KEY is not set.")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "TOKEN_ENCRYPTION_KEY must be a url-safe base64-encoded 32-byte key. "
            "Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ) from exc


_fernet: Fernet = SimpleLazyObject(_build_fernet)  # type: ignore[assignment]


def encrypt_token(plaintext: str) -> str:
    """Encrypt a GitHub access token for storage. Empty input stays empty."""
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored token. The result must never leave the process."""
    if not ciphertext:
        return ""
    try:
        return _fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise TokenDecryptionError(
            "Stored GitHub token could not be decrypted; the user must sign in again."
        ) from exc
