"""The two references S1's scores are compared against (D12, RQ2).

§10 Phase 12: "deps.dev client -> OpenSSF Scorecard score per corpus repo
(independent reference, D12; ~1,000 calls, free); OSV severity rollup computed
alongside with its circularity stated in the output."

**deps.dev's Scorecard is the independent one, and it measures something
else.** Scorecard rates a repository's security *practices* — branch
protection, code review, pinned dependencies, maintained-ness — and none of
its inputs is a dependency's deprecation, CVE count or release age. That is
what makes it independent, and also why File C expects only a moderate
correlation (H2: Spearman rho in [0.3, 0.6]) and frames the result as convergent
validity rather than accuracy (limitation L2). The sentence saying so travels
with every number this module produces.

**The OSV roll-up is not independent, and says so beside its number.** OSV
supplies two of the formula's four signals, so a formula score correlating
with an OSV severity roll-up is partly a formula correlating with itself (File
C limitation L1). It is computed anyway because it is the reference the field
conventionally reaches for, and a reviewer will ask for it; the caveat is
`OSV_CAVEAT`, and the report prints it adjacent to the number rather than in a
footnote.

**The client is cached on disk and paced.** A thousand calls is a few minutes,
and WP-6 may well run `validate_formula` more than once; every answer that is a
fact about the project (a score, no scorecard, no such project) is appended to
a JSONL cache beside the report and never fetched again. A failure to reach
deps.dev is a fact about the afternoon and is not cached, so the next run
retries it. Everything goes through `apps.common.http`, and `api.deps.dev`
joins its allowlist in this commit, as that module's header said it would.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from apps.common import http
from apps.research.corpus import append_jsonl, read_jsonl
from apps.scoring.normalize import CVSS_PLACEHOLDER

from .panel import PanelRepository

logger = logging.getLogger(__name__)

DEPS_DEV_API = "https://api.deps.dev/v3"
CACHE_FILENAME = "depsdev_cache.jsonl"

#: deps.dev publishes no rate limit for its v3 API. A fifth of a second between
#: calls keeps a thousand-repository run to a few minutes and keeps this
#: harness from being the reason one gets published.
PACE_SECONDS = 0.2
DEPS_DEV_TIMEOUT: tuple[float, float] = (5.0, 20.0)

STATUS_OK = "ok"
STATUS_NO_SCORECARD = "no_scorecard"
STATUS_NOT_FOUND = "not_found"
STATUS_UNAVAILABLE = "unavailable"

#: Answers that describe the project rather than the network; only these are
#: cached.
CACHEABLE = frozenset({STATUS_OK, STATUS_NO_SCORECARD, STATUS_NOT_FOUND})

#: The same character class `reports.rag.fetch_docs` enforces before it builds
#: a GitHub URL. The names come from the research database rather than from a
#: user, but a URL is built from them, and that is reason enough.
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

SCORECARD_CAVEAT = (
    "OpenSSF Scorecard (via deps.dev) rates a repository's security practices, "
    "not its dependencies' risk: an independent but different construct (File C "
    "L2). A moderate positive correlation is the expected result (H2: Spearman "
    "rho between 0.3 and 0.6); it is evidence of convergent validity, not of "
    "accuracy."
)

OSV_CAVEAT = (
    "Circular reference: OSV supplies two of the formula's four signals "
    "(severity and count), so agreement with an OSV severity roll-up is partly "
    "the formula agreeing with its own inputs (File C L1). Reported beside the "
    "independent reference, never instead of it."
)


@dataclass(frozen=True)
class ScorecardReading:
    """What deps.dev said about one repository, and when."""

    full_name: str
    status: str
    score: float | None = None
    scorecard_date: str | None = None
    scorecard_version: str | None = None
    checks: int = 0
    fetched_at: str = ""


class DepsDevClient:
    """`GET /v3/projects/github.com%2F{owner}%2F{name}`, paced."""

    def __init__(self, *, pace_seconds: float = PACE_SECONDS) -> None:
        self.pace_seconds = pace_seconds
        self.calls = 0
        self._last = 0.0

    def _wait(self) -> None:
        if not self.pace_seconds:
            return
        elapsed = time.monotonic() - self._last
        if self._last and elapsed < self.pace_seconds:
            _sleep(self.pace_seconds - elapsed)
        self._last = time.monotonic()

    def project(self, full_name: str) -> ScorecardReading:
        now = datetime.now(UTC).isoformat()
        owner, _, name = full_name.partition("/")
        if not (_SEGMENT.match(owner) and _SEGMENT.match(name)):
            logger.warning("Not a GitHub owner/name pair; not asking deps.dev.")
            return ScorecardReading(full_name, STATUS_NOT_FOUND, fetched_at=now)

        # deps.dev keys projects in lower case; the whole key is one path
        # segment, so its slashes are encoded.
        key = quote(f"github.com/{owner}/{name}".lower(), safe="")
        self._wait()
        self.calls += 1
        try:
            response = http.get_json(
                f"{DEPS_DEV_API}/projects/{key}",
                accept="application/json",
                timeout=DEPS_DEV_TIMEOUT,
            )
        except http.UpstreamNotFound:
            return ScorecardReading(full_name, STATUS_NOT_FOUND, fetched_at=now)
        except http.UpstreamError:
            logger.info("deps.dev did not answer for one project.")
            return ScorecardReading(full_name, STATUS_UNAVAILABLE, fetched_at=now)

        document = response.data if isinstance(response.data, dict) else {}
        scorecard = document.get("scorecard")
        if not isinstance(scorecard, dict):
            return ScorecardReading(full_name, STATUS_NO_SCORECARD, fetched_at=now)
        score = scorecard.get("overallScore")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            return ScorecardReading(full_name, STATUS_NO_SCORECARD, fetched_at=now)
        version = scorecard.get("scorecard")
        checks = scorecard.get("checks")
        return ScorecardReading(
            full_name=full_name,
            status=STATUS_OK,
            score=float(score),
            scorecard_date=str(scorecard.get("date") or "") or None,
            scorecard_version=str(version.get("version") or "") or None
            if isinstance(version, dict)
            else None,
            checks=len(checks) if isinstance(checks, list) else 0,
            fetched_at=now,
        )


def _sleep(seconds: float) -> None:
    """Indirection so tests run the pacing without the wait."""
    time.sleep(seconds)


def fetch_scorecards(
    full_names: list[str],
    cache_path: Path,
    client: DepsDevClient | None = None,
    *,
    progress=None,
) -> dict[str, ScorecardReading]:
    """A reading for every repository: from the cache, else from deps.dev.

    The latest cached line per repository wins, so a project that gained a
    scorecard can be refreshed by deleting the cache file without anything
    else changing.
    """
    client = client or DepsDevClient()
    readings: dict[str, ScorecardReading] = {}
    for row in read_jsonl(cache_path):
        if row.get("status") in CACHEABLE and row.get("full_name"):
            readings[row["full_name"]] = ScorecardReading(
                **{key: row.get(key) for key in ScorecardReading.__dataclass_fields__}
            )

    wanted = [name for name in dict.fromkeys(full_names) if name not in readings]
    for index, full_name in enumerate(wanted, 1):
        reading = client.project(full_name)
        readings[full_name] = reading
        if reading.status in CACHEABLE:
            append_jsonl(cache_path, asdict(reading))
        if progress is not None and (index % 50 == 0 or index == len(wanted)):
            progress(f"deps.dev: {index}/{len(wanted)} looked up")
    return {name: readings[name] for name in full_names if name in readings}


# ── the circular reference ─────────────────────────────────────────────────


def osv_rollup(repository: PanelRepository) -> float:
    """The worst CVSS among a repository's assessable occurrences; 0 if none.

    The roll-up a scanner dashboard would show — "the worst advisory in this
    repository" — computed from the same stored signals the formula reads,
    which is precisely its circularity. An advisory with no score counts at
    §5.2's 5.0 placeholder, as it does in the formula.
    """
    worst = Decimal(0)
    for occurrence in repository.occurrences:
        if occurrence.is_unassessable or occurrence.signals.vulnerability_count <= 0:
            continue
        severity = occurrence.signals.cvss_max
        if severity is None:
            severity = CVSS_PLACEHOLDER
        worst = max(worst, Decimal(severity))
    return float(worst)


def osv_health(repository: PanelRepository) -> float:
    """`10 - osv_rollup`: higher is healthier, the direction the formula's score runs.

    Oriented so that every reference correlation in the report is expected to
    be *positive*; a reader comparing two numbers should not have to remember
    that one of them is supposed to be negative.
    """
    return 10.0 - osv_rollup(repository)
