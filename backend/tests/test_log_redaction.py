"""§11 verification for OAuth token exposure: no token substring in logs."""

import logging

import pytest

from apps.accounts.crypto import encrypt_token
from apps.common.logging import REDACTED, RedactSecretsFilter, redact


@pytest.mark.parametrize(
    "secret",
    [
        "gho_abcdefghijklmnopqrstuvwxyz0123456789",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_11ABCDEFG0abcdefghijklmnop_qrstuvwxyz0123456789",
    ],
)
def test_github_tokens_are_scrubbed(secret):
    scrubbed = redact(f"calling GitHub with {secret} for user 1")

    assert secret not in scrubbed
    assert REDACTED in scrubbed


def test_fernet_ciphertext_is_scrubbed():
    ciphertext = encrypt_token("gho_" + "a" * 36)

    assert ciphertext not in redact(f"row dump: {ciphertext}")


def test_filter_rewrites_the_record(caplog):
    logger = logging.getLogger("repovitals.test.redaction")
    logger.addFilter(RedactSecretsFilter())
    secret = "gho_" + "b" * 36

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info("token=%s", secret)

    assert secret not in caplog.text
    assert REDACTED in caplog.text


def test_ordinary_messages_are_untouched():
    message = "scan completed for acme/checkout-service in 4.1s"

    assert redact(message) == message
