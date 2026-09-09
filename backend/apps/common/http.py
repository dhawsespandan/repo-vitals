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

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# Hosts this application is permitted to reach. Phase 12 adds deps.dev, and
# Phase 13 adds the judge provider. Adding a host here is a deliberate,
# reviewable act — the list is the whole SSRF defence, so a host goes in when
# the phase that calls it lands and not a phase earlier.
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "api.github.com",
        "registry.npmjs.org",
        # Phase 6. The PyPI JSON API is served from the site host rather than
        # from a separate `api.` name, so this one entry admits the package
        # documents and nothing else: `_check_host` matches the host exactly,
        # and every URL is still built server-side from a constant.
        "pypi.org",
        "api.osv.dev",
        # Phase 7. The generator LLM (D11). Reached only by
        # `apps.reports.llm.groq_client`, whose URL is a module constant.
        "api.groq.com",
    }
)

# (connect, read). Kept short: a slow upstream must not hold a worker thread.
DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 15.0)

MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5
#: Default ceiling on a response body. Generous for the GitHub and OSV
#: documents this project reads (a large blob is ~6 MB base64), and low enough
#: that a runaway response cannot exhaust the 512 MB tier (§8). Callers with a
#: different budget pass their own; `None` disables the cap entirely and should
#: be reserved for responses whose size is already known.
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
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


class UpstreamTooLarge(UpstreamError):
    """The response body exceeded the caller's cap.

    Separate from `UpstreamUnavailable` because it is not a failure to answer
    — the upstream answered fine, at a size this tier cannot hold. Callers
    that have a smaller representation available (the npm registry's
    abbreviated packument) catch this and ask for that instead, which is a
    degraded answer rather than no answer.
    """


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


def _read_capped(response: requests.Response, max_bytes: int | None) -> bytes:
    """Pull the body, refusing it the moment it exceeds `max_bytes`.

    The cap exists because this process is the whole service (§2: one gunicorn
    worker, 8 threads, 512 MB — §8). An npm packument for a long-lived package
    is not a hypothetical edge: `typescript` is ~15 MB on the wire and ~73 MB
    once parsed into Python objects. Three concurrent scans of ordinary
    repositories can therefore allocate more transient memory than the whole
    tier allows, and the process that dies takes every other user's request
    with it — an OOM is not scoped to the scan that caused it.

    `Content-Length` is checked first when the upstream sends one, which turns
    the common case into zero transferred bytes. It cannot be relied on alone:
    Cloudflare fronts several of these hosts with `Transfer-Encoding: chunked`
    and no length at all (the same property that broke the keepalive pinger,
    `docs/decisions.md` §1.17), so the running total is what actually enforces
    the cap.
    """
    if max_bytes is None:
        return response.content

    declared = response.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                response.close()
                raise UpstreamTooLarge(
                    f"Upstream declared {declared} bytes, over the {max_bytes} cap."
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            response.close()
            raise UpstreamTooLarge(f"Upstream body exceeded the {max_bytes} byte cap.")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_json(response: requests.Response, max_bytes: int | None = None) -> Any:
    body = _read_capped(response, max_bytes)
    try:
        return json.loads(body)
    except ValueError as exc:
        raise UpstreamUnavailable(
            f"Upstream returned {response.status_code} with a non-JSON body."
        ) from exc


def _backoff(attempt: int) -> float:
    return BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))


def _follow(
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    json_body: Any | None,
    timeout: tuple[float, float],
) -> requests.Response:
    """Send one request, following redirects by hand so every hop is host-checked."""
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        _check_host(current)
        response = _session().request(
            method,
            current,
            headers=headers,
            params=params,
            json=json_body,
            timeout=timeout,
            allow_redirects=False,
            # The body is pulled in chunks by `_read_capped` so an oversized
            # one can be refused mid-transfer rather than after it is already
            # resident. Without this, `requests` has buffered the whole thing
            # before any cap could look at it.
            stream=True,
        )
        if response.status_code not in (301, 302, 303, 307, 308):
            return response

        # A redirect's own body is never read, so the connection has to be
        # released explicitly or it is held until garbage collection.
        response.close()

        location = response.headers.get("Location")
        if not location:
            raise UpstreamUnavailable("Redirect response carried no Location header.")
        # Renamed repositories legitimately 301 here. The host is re-checked on
        # every hop precisely because a redirect target is upstream-controlled.
        current = urljoin(current, location)
        # Query parameters are part of the original URL; the redirect target
        # carries its own, so they are not re-appended.
        params = None
        if response.status_code == 303:
            # 303 means "go and GET this instead"; carrying the body forward
            # would re-send it somewhere that did not ask for it.
            method, json_body = "GET", None

    raise UpstreamUnavailable("Too many redirects.")


def _request_json(
    method: str,
    url: str,
    *,
    token: str | None,
    params: dict[str, Any] | None,
    json_body: Any | None,
    accept: str,
    timeout: tuple[float, float],
    retries: int,
    max_bytes: int | None,
) -> UpstreamResponse:
    """The shared body of `get_json` and `post_json`.

    Retry policy is deliberately identical for both. That is safe here only
    because the one POST this project makes — OSV's `querybatch` — is a
    read-only query that happens to need a request body; a retried POST is
    otherwise a duplicate-side-effect bug waiting to happen. If a
    state-changing POST is ever added, it needs `retries=0` and a comment
    saying why.
    """
    headers = {"Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    path = urlparse(url).path
    attempt = 0

    while True:
        try:
            response = _follow(method, url, headers, params, json_body, timeout)
        except requests.RequestException as exc:
            if attempt < retries:
                attempt += 1
                _sleep(_backoff(attempt))
                continue
            logger.warning(
                "Outbound %s %s failed after %d attempts.", method, path, attempt + 1
            )
            raise UpstreamUnavailable(
                f"Could not reach {urlparse(url).hostname}."
            ) from exc

        if _is_rate_limited(response):
            wait = _retry_after(response)
            if wait is not None and wait <= MAX_RETRY_AFTER_SECONDS and attempt < retries:
                attempt += 1
                _sleep(wait)
                continue
            logger.warning("Outbound %s %s hit an upstream rate limit.", method, path)
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
            data=_parse_json(response, max_bytes),
        )


def get_json(
    url: str,
    *,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    accept: str = "application/vnd.github+json",
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
) -> UpstreamResponse:
    """GET a JSON document from an allowlisted host.

    `url` must be built by the caller from a module-level constant — never
    from user input. A pasted repository URL is parsed to `owner/repo` and
    discarded long before it reaches this function (§5.6).

    Returns only on 2xx; every other outcome raises the matching
    `UpstreamError` subclass.
    """
    return _request_json(
        "GET",
        url,
        token=token,
        params=params,
        json_body=None,
        accept=accept,
        timeout=timeout,
        retries=retries,
        max_bytes=max_bytes,
    )


def post_json(
    url: str,
    body: Any,
    *,
    token: str | None = None,
    accept: str = "application/json",
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
) -> UpstreamResponse:
    """POST a JSON body to an allowlisted host and read a JSON answer.

    Added in Phase 3 for OSV's `querybatch` (§10), which is the reason this
    project needs a POST at all: asking about 100 packages in one call instead
    of 100 calls is the difference between a scan that fits a free tier and one
    that does not (§8). The same allowlist, redirect and retry rules apply — a
    second outbound path with its own rules is exactly what `common/http.py`
    exists to prevent.
    """
    return _request_json(
        "POST",
        url,
        token=token,
        params=None,
        json_body=body,
        accept=accept,
        timeout=timeout,
        retries=retries,
        max_bytes=max_bytes,
    )
