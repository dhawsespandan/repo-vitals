"""§11 "OAuth token exposure": ciphertext at rest, transient decrypt, no leaks."""

import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.test import override_settings

from apps.accounts.crypto import (
    TokenDecryptionError,
    decrypt_token,
    encrypt_token,
)
from apps.accounts.models import User

PLAINTEXT = "gho_abcdefghijklmnopqrstuvwxyz0123456789"


def test_encrypt_decrypt_roundtrip():
    ciphertext = encrypt_token(PLAINTEXT)

    assert ciphertext != PLAINTEXT
    assert PLAINTEXT not in ciphertext
    assert decrypt_token(ciphertext) == PLAINTEXT


def test_ciphertext_is_non_deterministic():
    """Fernet embeds a random IV; two encryptions of one token must differ."""
    assert encrypt_token(PLAINTEXT) != encrypt_token(PLAINTEXT)


def test_empty_token_is_passed_through():
    assert encrypt_token("") == ""
    assert decrypt_token("") == ""


def test_decrypt_with_a_rotated_key_fails_loudly():
    """§6: rotating TOKEN_ENCRYPTION_KEY invalidates stored tokens."""
    ciphertext = encrypt_token(PLAINTEXT)

    with override_settings(TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode()):
        # SimpleLazyObject caches the Fernet built from the original key, so
        # exercise the builder directly rather than the module-level instance.
        from apps.accounts import crypto

        rotated = crypto._build_fernet()
        with pytest.raises(InvalidToken):
            rotated.decrypt(ciphertext.encode())

    assert decrypt_token(ciphertext) == PLAINTEXT


@pytest.mark.django_db
def test_stored_column_holds_ciphertext_not_the_token(user):
    """A database dump on its own must yield ciphertext (§11)."""
    user.set_github_token(PLAINTEXT)
    user.save(update_fields=["encrypted_github_token"])

    raw = User.objects.values_list("encrypted_github_token", flat=True).get(pk=user.pk)

    assert raw != PLAINTEXT
    assert PLAINTEXT not in raw
    assert raw.startswith("gAAAAA")  # Fernet version byte
    assert User.objects.get(pk=user.pk).get_github_token() == PLAINTEXT


@pytest.mark.django_db
def test_token_is_never_serialized_to_the_browser(user):
    from apps.accounts.serializers import UserSerializer

    data = UserSerializer(user).data

    assert "encrypted_github_token" not in data
    assert "token_scopes" not in data
    assert PLAINTEXT not in str(data)


def test_decrypting_garbage_raises_the_typed_error():
    with pytest.raises(TokenDecryptionError):
        decrypt_token("not-a-fernet-token")
