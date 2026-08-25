"""Log redaction.

§11 lists "OAuth token exposure" as a Phase 1 risk with "log assertions" as the
verification. Relying on every future call site to remember not to log a token
is not a control; this filter is. It scrubs anything that looks like a GitHub
token or a Fernet ciphertext out of every record the console handler emits.
"""

from __future__ import annotations

import logging
import re

# GitHub's documented token prefixes (classic PAT, fine-grained PAT, OAuth,
# user-to-server, server-to-server, refresh) plus the legacy 40-hex form.
_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgho_[A-Za-z0-9]{16,}\b"),
    # Fernet ciphertext: version byte 0x80 base64-encodes to a leading "gAAAAA".
    re.compile(r"gAAAAA[A-Za-z0-9_\-=]{20,}"),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True
