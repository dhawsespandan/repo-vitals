"""The generator LLM (D11: Groq, temperature 0, JSON mode).

One function, `complete_json`, and everything it does is in service of a single
property: **a generation is reproducible and its cost is countable.**

* **Temperature 0 and JSON mode.** D11's reason is that this is a trust tool.
  A remediation list that changes wording between two loads of the same page
  invites the reader to wonder which one was true, and §10 Phase 8's
  determinism suite asserts byte-identical output for identical input.
* **The single outbound choke point.** The call goes through
  `apps.common.http`, like every other external request in this project (§5.6).
  That module owns the allowlist, the redirect discipline and the body cap;
  a second HTTP path with its own rules is exactly what it exists to prevent.
* **Exactly one retry, and it is spent here rather than in the transport.**
  `common/http.py` says in as many words that its retry policy is safe only
  because the one POST it carries is a read-only query, and that a
  state-changing POST needs `retries=0` plus a comment saying why. This is that
  POST: a Groq call is metered, and a read timeout can mean "the provider
  generated an answer and we did not hear it". So the transport retries
  nothing, and this module retries once on a transient failure — a bounded,
  countable two requests per logical call rather than the transport's silent
  three multiplied by whatever the caller is doing.

Nothing here validates the *content* of the answer. That is `schema.py`'s job,
and the separation matters: this module's contract is "a JSON document came
back from the model we asked", which is a transport claim. Whether the document
means anything is a question about §5.8.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from django.conf import settings

from apps.common.http import (
    UpstreamRateLimited,
    UpstreamUnauthorized,
    UpstreamUnavailable,
    post_json,
)

logger = logging.getLogger(__name__)

#: Groq speaks the OpenAI chat-completions dialect. The URL is a module
#: constant and is never assembled from anything a user supplied (§5.6).
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

#: (connect, read). The read half is far longer than `common/http.py`'s default
#: 15 s because a 70B model writing a few hundred tokens legitimately takes
#: tens of seconds. Affordable only because generation runs on a background
#: thread (§2) and never inside a request — Render's ~100 s request ceiling is
#: not in play here.
LLM_TIMEOUT: tuple[float, float] = (5.0, 60.0)

#: Enough for a summary paragraph plus a couple of dozen fixes, and low enough
#: that a runaway generation cannot spend the free tier's daily token budget in
#: one request (§8). A generation that hits it is failed rather than truncated:
#: half a JSON document is not a shorter report, it is an unparseable one.
MAX_OUTPUT_TOKENS = 3000

#: One retry, per §10 Phase 7. See the module docstring for why it lives here.
MAX_TRANSIENT_RETRIES = 1


class LlmError(Exception):
    """Base class for every failure to obtain a generation."""


class LlmNotConfigured(LlmError):
    """No `GROQ_API_KEY`. A deployment fault, not a user's or a model's."""


class LlmRefused(LlmError):
    """The credential was rejected. No amount of retrying fixes it."""


class LlmUnavailable(LlmError):
    """Transport failure, 5xx or rate limit that outlived the one retry."""


class LlmTruncated(LlmError):
    """The model stopped at the output cap mid-document.

    Named separately from a parse failure because the cause and the remedy are
    different: the answer was not malformed, it was cut off, and the fix is a
    smaller request rather than a better prompt.
    """


@dataclass(frozen=True)
class LlmCall:
    """One completed generation, with the metadata §10 Phase 7 asks be recorded."""

    #: The message content, still a raw string. Parsing is the caller's.
    content: str
    #: The model the provider says answered, which is not always the model we
    #: asked for (aliases, deprecations, silent substitutions). Stored on the
    #: report row, because a report is evidence about one model.
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    #: HTTP requests actually made, so "one generation billed once" is a thing
    #: a test can assert rather than a thing the docstring claims.
    requests: int


def is_configured() -> bool:
    """Whether a generation could be attempted at all."""
    return bool(getattr(settings, "GROQ_API_KEY", ""))


def active_model() -> str:
    return getattr(settings, "GROQ_MODEL", "") or ""


def complete_json(
    system_prompt: str,
    user_prompt: str,
    *,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
) -> LlmCall:
    """Ask the model for one JSON document. Raises `LlmError` on every failure.

    `response_format={"type": "json_object"}` is the provider's JSON mode: it
    constrains decoding so the answer is syntactically valid JSON. It does not
    constrain the answer's *shape* — that is §5.8's schema, checked afterwards
    — and the provider requires the word JSON to appear in the prompt, which
    the caller's prompt satisfies by printing the schema it wants.
    """
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        raise LlmNotConfigured("GROQ_API_KEY is not set.")

    body = {
        "model": active_model(),
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            response = post_json(
                GROQ_CHAT_URL,
                body,
                token=api_key,
                timeout=LLM_TIMEOUT,
                # The transport retries nothing: this POST is metered, so every
                # repeat has to be a decision made here where it can be counted.
                retries=0,
            )
        except UpstreamUnauthorized as exc:
            raise LlmRefused("The generator API key was rejected.") from exc
        except (UpstreamUnavailable, UpstreamRateLimited) as exc:
            if attempt <= MAX_TRANSIENT_RETRIES:
                logger.info("Generator call failed transiently; retrying once.")
                continue
            raise LlmUnavailable("The generator service did not answer.") from exc

        break

    latency_ms = int((time.monotonic() - started) * 1000)
    data = response.data if isinstance(response.data, dict) else {}
    choices = data.get("choices") or []
    if not choices:
        raise LlmUnavailable("The generator returned no choices.")

    choice = choices[0] or {}
    if choice.get("finish_reason") == "length":
        raise LlmTruncated(
            f"The generation was cut off at the {max_output_tokens}-token cap."
        )

    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise LlmUnavailable("The generator returned an empty message.")

    usage = data.get("usage") or {}
    return LlmCall(
        content=content,
        # Falls back to what we asked for rather than to an empty string: a
        # report row with no model name is worse than one naming the model we
        # requested, and the provider omitting `model` is not a failure.
        model=str(data.get("model") or active_model()),
        prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
        completion_tokens=_int_or_none(usage.get("completion_tokens")),
        latency_ms=latency_ms,
        requests=attempt,
    )


def parse_content(content: str) -> dict:
    """The message body as an object. Raises `LlmError` when it is not one.

    JSON mode makes this almost always succeed, and "almost always" is the
    reason it is checked: a provider that answers with a bare array or a string
    would otherwise reach the schema as a type error several frames away from
    the thing that produced it.
    """
    try:
        payload = json.loads(content)
    except ValueError as exc:
        raise LlmUnavailable("The generator's answer was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise LlmUnavailable("The generator's answer was not a JSON object.")
    return payload


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None
