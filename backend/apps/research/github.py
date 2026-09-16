"""GitHub as the research commands see it — the PAT, the pacing, the budget.

Separate from `apps.scanning.scanner`'s access for one reason that is not
style: the credential. A live scan spends the *user's* OAuth token on a
repository they registered. A corpus run spends `GITHUB_API_PAT` (§6) on a
thousand strangers' public repositories, under two limits the product has
never had to think about (§8):

  - **the Search API's 30 requests/minute**, an order of magnitude tighter
    than the REST limit and enforced per minute rather than per hour, so it
    needs pacing rather than backoff;
  - **1,000 results per query, hard**, which is why `corpus.py` splits its
    star bands until each cell fits under it rather than paging past it.

Everything still goes through `apps.common.http`: the allowlist is the SSRF
choke point (§5.6) and `api.github.com` is already on it, so nothing here
widens the outbound surface. `READ_ONLY_HOSTS` covers these calls too — the
PAT is asked for `public_repo` scope, and a GET is the only method that could
be sent to GitHub from anywhere in this codebase (§11).

**The PAT is never reachable from a request.** `D13`'s discipline, applied to
a credential: nothing outside `apps/research/` reads `GITHUB_API_PAT`, there
is no view that could, and `tests/test_hardening.py` asserts it. A research
token with a thousand repositories of quota on it must not be spendable by an
HTTP request.

**The budget is read from the response, not counted locally.** GitHub's
`x-ratelimit-remaining` is the truth — a retried call, a conditional request
and a search call all cost differently, and a local counter would drift over a
three-hour run in whichever direction is least convenient.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from django.conf import settings

from apps.common import http
from apps.scanning.scanner import GITHUB_API, blob_url, decode_blob, tree_url

logger = logging.getLogger(__name__)

SEARCH_API = f"{GITHUB_API}/search/repositories"

#: §8: the Search API allows 30 requests/minute for an authenticated caller.
#: Expressed as a minimum interval rather than a bucket, because a bucket
#: drained in ten seconds earns a 403 that costs more than the wait it saved.
SEARCH_MIN_INTERVAL_SECONDS = 60.0 / 30.0

#: Leave this much of the hourly REST budget unspent before pausing. A corpus
#: repository costs one tree call plus one blob call per manifest, so stopping
#: at zero would strand a repository half-read and leave `--resume` to redo it.
REST_RESERVE = 50

#: Never sleep longer than this in one wait, so a run that is pausing says so
#: repeatedly rather than appearing to hang for an hour.
MAX_SLEEP_SLICE_SECONDS = 60.0


class ResearchCredentialMissing(Exception):
    """`GITHUB_API_PAT` is unset. Every command in this app needs it (§6)."""


class RateBudgetExhausted(Exception):
    """The hourly budget is gone and the caller asked not to wait for it."""


def research_token() -> str:
    """The research PAT, or a refusal that names the variable and the scope."""
    token = getattr(settings, "GITHUB_API_PAT", "") or ""
    if not token:
        raise ResearchCredentialMissing(
            "GITHUB_API_PAT is not set. Phase 11's commands read public "
            "repositories with a personal access token (§6); create one with "
            "the `public_repo` scope and put it in backend/.env."
        )
    return token


def _sleep(seconds: float) -> None:
    """Indirection so tests exercise pacing and pausing without real delays."""
    time.sleep(seconds)


@dataclass
class Pacer:
    """A floor on the interval between calls, measured from the last one.

    Not a rate limiter: it cannot make a caller slower than it already is, and
    it does not smooth bursts retroactively. It exists so that a loop issuing
    search calls as fast as the network allows issues them at 30/minute
    instead, which is the whole of §8's "paces ≤ 30 search req/min".
    """

    min_interval: float
    _last: float = field(default=0.0, repr=False)

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if self._last and elapsed < self.min_interval:
            _sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


@dataclass
class RateBudget:
    """What GitHub last said about the caller's remaining hourly quota.

    `remaining` is None until the first answer arrives — unknown, which is not
    the same as exhausted, so nothing pauses on it.
    """

    reserve: int = REST_RESERVE
    remaining: int | None = None
    reset_at: float | None = None
    #: Set when a pause has happened, so a completion report can say the run
    #: was rate-limited rather than slow.
    pauses: int = 0
    waited_seconds: float = 0.0

    def observe(self, headers: dict[str, str]) -> None:
        raw_remaining = headers.get("x-ratelimit-remaining") or headers.get(
            "X-RateLimit-Remaining"
        )
        raw_reset = headers.get("x-ratelimit-reset") or headers.get("X-RateLimit-Reset")
        if raw_remaining is not None:
            try:
                self.remaining = int(raw_remaining)
            except ValueError:
                pass
        if raw_reset is not None:
            try:
                self.reset_at = float(raw_reset)
            except ValueError:
                pass

    @property
    def is_low(self) -> bool:
        return self.remaining is not None and self.remaining <= self.reserve

    def pause_if_low(self, *, wait: bool = True) -> None:
        """Sleep until the window resets, or refuse to start work that cannot finish.

        WP-5 tells the teammate a pause here is normal. It is also the only
        honest thing to do: the alternative is to keep calling, collect 403s,
        and record a hundred repositories as failed for a reason that has
        nothing to do with them.
        """
        if not self.is_low:
            return
        if not wait:
            raise RateBudgetExhausted(
                f"GitHub's hourly budget is down to {self.remaining}; stopping "
                f"rather than spending the reserve. Re-run with --resume."
            )

        remaining_wait = max(0.0, (self.reset_at or 0.0) - time.time()) + 1.0
        self.pauses += 1
        logger.info(
            "GitHub budget at %s; pausing %.0fs for the window to reset.",
            self.remaining,
            remaining_wait,
        )
        while remaining_wait > 0:
            slice_seconds = min(remaining_wait, MAX_SLEEP_SLICE_SECONDS)
            _sleep(slice_seconds)
            self.waited_seconds += slice_seconds
            remaining_wait -= slice_seconds
        # The window has rolled; the next answer will say by how much.
        self.remaining = None


@dataclass
class ResearchClient:
    """One credential, one budget, one pacer, for a whole command run.

    Held as an object rather than passed as four arguments because the budget
    is stateful across every call a run makes — that is the point of it — and
    because `--repo owner/name` and a thousand-repository sweep must share
    exactly one of each.
    """

    token: str
    budget: RateBudget = field(default_factory=RateBudget)
    search_pacer: Pacer = field(
        default_factory=lambda: Pacer(SEARCH_MIN_INTERVAL_SECONDS)
    )
    #: Set False by `--no-wait`, so an unattended overnight run pauses and a
    #: foreground smoke run stops instead of sleeping for fifty minutes.
    wait_for_reset: bool = True
    #: Counted for the completion report, not for the limit itself.
    search_calls: int = 0
    rest_calls: int = 0

    @classmethod
    def from_settings(cls, **kwargs) -> ResearchClient:
        return cls(token=research_token(), **kwargs)

    def _get(self, url: str, **kwargs) -> http.UpstreamResponse:
        response = http.get_json(url, token=self.token, **kwargs)
        self.budget.observe(response.headers)
        return response

    def search_repositories(
        self, query: str, *, page: int = 1, per_page: int = 100, sort: str, order: str
    ) -> dict:
        """One page of `/search/repositories`, paced to §8's 30/minute.

        The Search API has its own budget (30/min) and reports it in the same
        headers as the REST one, so the budget object is deliberately *not*
        updated from a search answer: mixing the two would have a search call's
        `remaining: 12` pause a run whose REST budget is untouched.
        """
        self.search_pacer.wait()
        self.search_calls += 1
        response = http.get_json(
            SEARCH_API,
            token=self.token,
            params={
                "q": query,
                "page": page,
                "per_page": per_page,
                "sort": sort,
                "order": order,
            },
        )
        return response.data if isinstance(response.data, dict) else {}

    def repository(self, owner: str, name: str) -> dict:
        self.budget.pause_if_low(wait=self.wait_for_reset)
        self.rest_calls += 1
        response = self._get(f"{GITHUB_API}/repos/{owner}/{name}")
        return response.data if isinstance(response.data, dict) else {}

    def tree(self, owner: str, name: str, branch: str) -> list[dict]:
        """The recursive tree, through the same URL builder a live scan uses."""
        self.budget.pause_if_low(wait=self.wait_for_reset)
        self.rest_calls += 1
        response = self._get(tree_url(owner, name, branch), params={"recursive": "1"})
        data = response.data if isinstance(response.data, dict) else {}
        tree = data.get("tree")
        return tree if isinstance(tree, list) else []

    def blob(self, owner: str, name: str, sha: str, cap: int) -> bytes | None:
        """One blob by sha, unwrapped by `scanner.decode_blob`.

        Returns None where the live scanner would: an encoding it cannot
        inline, undecodable base64, or a body over `cap`. A corpus run treats
        that the same way a scan does — the manifest is skipped and counted,
        not guessed at.
        """
        self.budget.pause_if_low(wait=self.wait_for_reset)
        self.rest_calls += 1
        try:
            response = self._get(blob_url(owner, name, sha))
        except http.UpstreamRateLimited:
            # The budget headers said there was room and there was not — a
            # secondary limit. Treat it as the primary one: pause, then let the
            # caller retry the repository on the next resume.
            self.budget.remaining = 0
            self.budget.pause_if_low(wait=self.wait_for_reset)
            raise
        document = response.data if isinstance(response.data, dict) else {}
        return decode_blob(document, cap)
