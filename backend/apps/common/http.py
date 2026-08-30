"""The single outbound HTTP client. Every external call in the project goes
through here — there is no second one (§10 Phase 2, §12).

Three jobs, none of which are optional:

**Allowlist (SSRF).** §5.6's threat is a pasted repository URL steering an
outbound request somewhere it shouldn't go. The defence is structural rather
than validating: callers pass a URL this module has built from a constant
base, and `_check_host` refuses any host outside `ALLOWED_HOSTS` — including
one arrived at by *redirect*, which is why redirects are followed manually
here instead of by `requests`. An open redirect on an allowlisted host would
otherwise walk straight past the check.

**Timeouts and retry.** A free-tier worker has eight threads (§3); one call
hanging on a dead socket costs an eighth of the service. Connect and read
timeouts are always set, and transient failures (connection errors, timeouts,
5xx) are retried with exponential backoff. 4xx is never retried: it is an
answer, not a failure.

**Rate-limit awareness.** GitHub signals its primary limit as 403/429 with
`x-ratelimit-remaining: 0` and its secondary limit with `Retry-After` (§8:
5,000/hr/token). Both surface as `UpstreamRateLimited` so callers can map it
to the §5.6 `github_rate_limited` outcome rather than showing a generic error.

Nothing here logs headers: the caller's OAuth token travels in one.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# Hosts this application is permitted to reach. Phase 6 adds pypi.org, Phase 12
# adds deps.dev, and Phases 7/13 add the LLM providers. Adding a host here is a
# deliberate, reviewable act — the list is the whole SSRF defence, so a host
# goes in when the phase that calls it lands and not a phase earlier.
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "api.github.com",
        "registry.npmjs.org",
        "api.osv.dev",
    }
)

# (connect, read). Kept short: a slow upstream must not hold a worker thread.
DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 15.0)

MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5
MAX_REDIRECTS = 3
# A rate-limit reset an hour away is not something to sleep on inside a
# request; past this the call fails fast and the user is asked to retry.
MAX_RETRY_AFTER_SECONDS = 5.0

USER_AGENT = "RepoVitals/0.2 (+https://github.com/dhawsespandan/repo-vitals)"


class UpstreamError(Exception):
    """Base class for every failure reaching an external service."""


class DisallowedHost(UpstreamError):
    """A URL outside `ALLOWED_HOSTS` was requested. Always a bug or an attack."""


class UpstreamNotFound(UpstreamError):
    """404 — the resource does not exist, or the token cannot see it."""


class UpstreamUnauthorized(UpstreamError):
    """401 — the credential itself is bad (GitHub: "Bad credentials").

    Distinct from 403 because the remedy is different in kind: no amount of
    waiting or retrying fixes a revoked or expired token, only a fresh login.
    """


class UpstreamForbidden(UpstreamError):
    """403 that is not a rate limit."""


class UpstreamConflict(UpstreamError):
    """409 — GitHub uses this for an empty (commitless) repository."""


class UpstreamRateLimited(UpstreamError):
    """Primary or secondary rate limit hit."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamUnavailable(UpstreamError):
    """Transport failure or 5xx that outlived the retry budget."""


@dataclass(frozen=True)
class UpstreamResponse:
    status_code: int
    headers: dict[str, str]
    data: Any


_local = threading.local()


def _session() -> requests.Session:
    """One pooled session per thread.

    Scans run in background threads (§2) and `requests.Session` is not
    documented as thread-safe, so the pool is thread-local rather than shared.
    """
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        _local.session = session
    return session


def _sleep(seconds: float) -> None:
    """Indirection so tests can exercise the retry paths without real delays."""
    time.sleep(seconds)


def _check_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise DisallowedHost(f"Refusing a non-HTTPS outbound URL: {parsed.scheme!r}.")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise DisallowedHost(
            f"Host {parsed.hostname!r} is not in the outbound allowlist."
        )


def _retry_after(response: requests.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        # The HTTP-date form. It is not parsed here: callers treat "rate
        # limited, unknown wait" exactly as they treat any other rate limit.
        return None


def _is_rate_limited(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    remaining = response.headers.get("x-ratelimit-remaining")
    if remaining is not None and remaining.strip() == "0":
        return True
    # Secondary limits come back as a 403 carrying Retry-After rather than a
    # remaining counter.
    return response.headers.get("Retry-After") is not None


def _parse_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailable(
            f"Upstream returned {response.status_code} with a non-JSON body."
        ) from exc


def _backoff(attempt: int) -> float:
    return BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))


def _follow(
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    timeout: tuple[float, float],
) -> requests.Response:
    """GET `url`, following redirects by hand so every hop is host-checked."""
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        _check_host(current)
        response = _session().get(
            current,
            headers=headers,
            params=params,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.status_code not in (301, 302, 303, 307, 308):
            return response

        location = response.headers.get("Location")
        if not location:
            raise UpstreamUnavailable("Redirect response carried no Location header.")
        # Renamed repositories legitimately 301 here. The host is re-checked on
        # every hop precisely because a redirect target is upstream-controlled.
        current = urljoin(current, location)
        # Query parameters are part of the original URL; the redirect target
        # carries its own, so they are not re-appended.
        params = None

    raise UpstreamUnavailable("Too many redirects.")


def get_json(
    url: str,
    *,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    accept: str = "application/vnd.github+json",
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
) -> UpstreamResponse:
    """GET a JSON document from an allowlisted host.

    `url` must be built by the caller from a module-level constant — never
    from user input. A pasted repository URL is parsed to `owner/repo` and
    discarded long before it reaches this function (§5.6).

    Returns only on 2xx; every other outcome raises the matching
    `UpstreamError` subclass.
    """
    headers = {"Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    path = urlparse(url).path
    attempt = 0

    while True:
        try:
            response = _follow(url, headers, params, timeout)
        except requests.RequestException as exc:
            if attempt < retries:
                attempt += 1
                _sleep(_backoff(attempt))
                continue
            logger.warning("Outbound GET %s failed after %d attempts.", path, attempt + 1)
            raise UpstreamUnavailable(
                f"Could not reach {urlparse(url).hostname}."
            ) from exc

        if _is_rate_limited(response):
            wait = _retry_after(response)
            if wait is not None and wait <= MAX_RETRY_AFTER_SECONDS and attempt < retries:
                attempt += 1
                _sleep(wait)
                continue
            logger.warning("Outbound GET %s hit an upstream rate limit.", path)
            raise UpstreamRateLimited("Upstream rate limit reached.", retry_after=wait)

        if response.status_code >= 500:
            if attempt < retries:
                attempt += 1
                _sleep(_backoff(attempt))
                continue
            raise UpstreamUnavailable(
                f"Upstream returned {response.status_code} after {attempt + 1} attempts."
            )

        if response.status_code == 401:
            raise UpstreamUnauthorized(f"Upstream returned 401 for {path}.")
        if response.status_code == 404:
            raise UpstreamNotFound(f"Upstream returned 404 for {path}.")
        if response.status_code == 409:
            raise UpstreamConflict(f"Upstream returned 409 for {path}.")
        if response.status_code == 403:
            raise UpstreamForbidden(f"Upstream returned 403 for {path}.")
        if response.status_code >= 400:
            raise UpstreamUnavailable(
                f"Upstream returned {response.status_code} for {path}."
            )

        return UpstreamResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            data=_parse_json(response),
        )
