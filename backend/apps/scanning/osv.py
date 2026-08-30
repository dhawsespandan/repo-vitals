"""OSV.dev — the vulnerability half of the scan.

Two endpoints, in a fixed shape (§10 Phase 3):

  1. `POST /v1/querybatch` with up to 100 `(ecosystem, name, version)` queries.
     It answers with **ids only** — no severity, no CVSS, no dates.
  2. `GET /v1/vulns/{id}` for each distinct id, once, cached for the run.

The two-step shape is not an inefficiency to route around; it is what makes
the free tier work (§8). A repository with 300 dependencies and 12 distinct
advisories costs 3 batch calls and 12 detail calls, not 300. The in-run cache
is what makes "distinct" real: the same advisory reached from four manifests
is fetched once.

**CVSS is computed from the vector, not read from a field.** OSV publishes
severity as a CVSS *vector string* (`CVSS:3.1/AV:N/AC:L/...`), and the numeric
base score is arithmetic over it. §5.2 needs a number, and §5.2's fallback
chain — OSV, then NVD, then a 5.0 placeholder with `cvss_reduced_confidence`
— only ever reaches its second step if the first is genuinely tried. Deriving
the score here means the placeholder is reserved for advisories that really
carry no severity at all, which is a much smaller set than "advisories whose
score is not a plain number in the JSON".

Everything is stored as observed. `published_at` in particular is D17's
"cheap now, impossible later": the backfill engine's as-of filter needs to
know when an advisory was *disclosed*, and an advisory edited two years from
now will not tell you what it said today.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from apps.common import http

from .models import Severity

logger = logging.getLogger(__name__)

OSV_API = "https://api.osv.dev"
#: OSV documents its batch limit at 1,000 queries; §10 fixes ours at 100. The
#: smaller number keeps one failed call cheap to retry and keeps the response
#: small enough to parse without thinking about it on a 512 MB box (§8).
BATCH_SIZE = 100
#: A batch of 100 is a real amount of work for the upstream; the read timeout
#: is raised over the default accordingly. Scans are background threads, so a
#: slow read costs scan latency, not a held request (§2).
OSV_TIMEOUT: tuple[float, float] = (5.0, 30.0)

#: CVSS v3.1 §5: the qualitative rating scale. A 0.0 base score is "None",
#: which is not one of §5.1's buckets — it is stored as `low`, the closest
#: truthful bucket, and the exact 0.0 survives in `cvss_score` regardless.
_CVSS_BUCKETS: tuple[tuple[float, str], ...] = (
    (9.0, Severity.CRITICAL.value),
    (7.0, Severity.HIGH.value),
    (4.0, Severity.MEDIUM.value),
    (0.0, Severity.LOW.value),
)

_SEVERITY_WORDS: dict[str, str] = {
    "CRITICAL": Severity.CRITICAL.value,
    "HIGH": Severity.HIGH.value,
    "MODERATE": Severity.MEDIUM.value,  # GitHub advisories say MODERATE
    "MEDIUM": Severity.MEDIUM.value,
    "LOW": Severity.LOW.value,
}


@dataclass(frozen=True)
class Vulnerability:
    """One advisory as OSV describes it, for one affected package version."""

    osv_id: str
    cve_id: str | None = None
    severity: str | None = None
    cvss_score: float | None = None
    published_at: datetime | None = None
    summary: str | None = None
    affected_range: str | None = None
    fixed_version: str | None = None
    source_url: str | None = None


# ── CVSS v3 base score ─────────────────────────────────────────────────────
# The specification's own arithmetic (CVSS v3.1 §8.1), transcribed. It is here
# rather than pulled from a package because it is thirty lines of closed-form
# formula against a published test vector set, and because a scoring tool that
# cannot show its own arithmetic has a credibility problem (§10 Phase 5 is
# built entirely on being able to show it).

_WEIGHTS: dict[str, dict[str, float]] = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "PR": {"N": 0.85, "L": 0.62, "H": 0.27},  # replaced below when scope changed
    "UI": {"N": 0.85, "R": 0.62},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
    "I": {"H": 0.56, "L": 0.22, "N": 0.0},
    "A": {"H": 0.56, "L": 0.22, "N": 0.0},
}
_PR_SCOPE_CHANGED: dict[str, float] = {"N": 0.85, "L": 0.68, "H": 0.5}


def _round_up(value: float) -> float:
    """CVSS v3.1's `Roundup`: to one decimal, always upward (§8.1 Appendix A).

    Implemented on the integer representation exactly as the specification
    prescribes, because plain `math.ceil(value * 10) / 10` rounds 0.1 * 3 up to
    0.4 on some inputs — the float representation is a hair over the boundary
    and the specification's own note calls this out.
    """
    integer = round(value * 100000)
    if integer % 10000 == 0:
        return integer / 100000.0
    return (integer // 10000 + 1) / 10.0


def cvss_v3_base_score(vector: str) -> float | None:
    """The base score of a CVSS v3.0/v3.1 vector string, or None if unusable.

    Returns None rather than raising: an unparseable vector is a missing
    measurement, and §5.2 already has a policy for a missing CVSS. Guessing
    here would put an invented number into a column the whole product's
    credibility rests on.
    """
    parts = (vector or "").strip().split("/")
    if not parts or not parts[0].upper().startswith("CVSS:3"):
        return None

    metrics: dict[str, str] = {}
    for part in parts[1:]:
        key, _, value = part.partition(":")
        if key and value:
            metrics[key.upper()] = value.upper()

    required = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")
    if any(key not in metrics for key in required):
        return None

    scope_changed = metrics["S"] == "C"

    try:
        privileges = (
            _PR_SCOPE_CHANGED[metrics["PR"]]
            if scope_changed
            else _WEIGHTS["PR"][metrics["PR"]]
        )
        exploitability = (
            8.22
            * _WEIGHTS["AV"][metrics["AV"]]
            * _WEIGHTS["AC"][metrics["AC"]]
            * privileges
            * _WEIGHTS["UI"][metrics["UI"]]
        )
        impact_base = 1 - (
            (1 - _WEIGHTS["C"][metrics["C"]])
            * (1 - _WEIGHTS["I"][metrics["I"]])
            * (1 - _WEIGHTS["A"][metrics["A"]])
        )
    except KeyError:
        return None

    if scope_changed:
        impact = 7.52 * (impact_base - 0.029) - 3.25 * (impact_base - 0.02) ** 15
    else:
        impact = 6.42 * impact_base

    if impact <= 0:
        return 0.0

    raw = min((1.08 if scope_changed else 1.0) * (impact + exploitability), 10.0)
    return _round_up(raw)


def severity_bucket(score: float | None) -> str | None:
    if score is None:
        return None
    for threshold, bucket in _CVSS_BUCKETS:
        if score >= threshold:
            return bucket
    return None


def _parse_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _cve_id(document: dict) -> str | None:
    aliases = document.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.upper().startswith("CVE-"):
                return alias
    identifier = document.get("id")
    if isinstance(identifier, str) and identifier.upper().startswith("CVE-"):
        return identifier
    return None


def _best_cvss(document: dict) -> float | None:
    """The highest CVSS v3 base score across every vector the advisory carries.

    Advisories sometimes publish several (a v3.1 and a v4.0, or one per
    affected product). The maximum is taken deliberately: §5.2 feeds `cvss_max`
    into the score, and under-reading a severity is the failure mode that
    matters for a tool whose job is to warn.
    """
    scores: list[float] = []
    for block in (
        document.get("severity"),
        *(
            affected.get("severity")
            for affected in document.get("affected", [])
            if isinstance(affected, dict)
        ),
    ):
        if not isinstance(block, list):
            continue
        for entry in block:
            if not isinstance(entry, dict):
                continue
            score = cvss_v3_base_score(str(entry.get("score") or ""))
            if score is not None:
                scores.append(score)
    return max(scores) if scores else None


def _declared_severity(document: dict) -> str | None:
    """The publisher's own severity word, where they wrote one.

    Preferred over the bucket derived from CVSS because it is a statement by
    the people who analysed the vulnerability, not an inference from a number.
    Where both exist they nearly always agree, and both are stored — the
    numeric `cvss_score` is what §5.2's formula actually consumes, so a
    disagreement changes the label the user reads and never the arithmetic.
    """
    specific = document.get("database_specific")
    if isinstance(specific, dict):
        word = specific.get("severity")
        if isinstance(word, str) and word.upper() in _SEVERITY_WORDS:
            return _SEVERITY_WORDS[word.upper()]
    return None


def _affected_summary(document: dict, package_name: str) -> tuple[str | None, str | None]:
    """`(affected_range, fixed_version)` for one package, as OSV states them.

    OSV describes affected versions as events along a range: `introduced` at
    some version, `fixed` at another (or `last_affected`, when the maintainer
    never shipped a fix). The pair is rendered as text rather than parsed into
    a model — S3's ground truth needs "the fix was to move to X" (§5.8), and
    the range is shown to a person, so a faithful string beats a lossy
    structure.
    """
    for affected in document.get("affected", []):
        if not isinstance(affected, dict):
            continue
        package = affected.get("package")
        if isinstance(package, dict) and package.get("name") != package_name:
            continue

        introduced: str | None = None
        fixed: str | None = None
        last_affected: str | None = None
        for entry in affected.get("ranges", []):
            if not isinstance(entry, dict):
                continue
            for event in entry.get("events", []):
                if not isinstance(event, dict):
                    continue
                introduced = event.get("introduced", introduced)
                fixed = event.get("fixed", fixed)
                last_affected = event.get("last_affected", last_affected)

        parts: list[str] = []
        if introduced is not None:
            # OSV writes the beginning-of-time introduction as "0".
            parts.append(f">={introduced}" if introduced != "0" else ">=0")
        if fixed:
            parts.append(f"<{fixed}")
        elif last_affected:
            parts.append(f"<={last_affected}")

        return (" ".join(parts) or None, fixed or None)

    return (None, None)


def _source_url(document: dict) -> str:
    for reference in document.get("references", []):
        if not isinstance(reference, dict):
            continue
        if reference.get("type") in ("ADVISORY", "WEB") and reference.get("url"):
            return str(reference["url"])
    return f"https://osv.dev/vulnerability/{document.get('id', '')}"


class OsvClient:
    """Batched OSV queries with an in-run detail cache."""

    def __init__(self) -> None:
        # Raw documents, not built rows: the affected-range summary depends on
        # which package is asking, so caching the document lets the same
        # advisory serve four packages from one fetch.
        self._documents: dict[str, dict | None] = {}

    def query_batch(
        self, ecosystem: str, targets: list[tuple[str, str]]
    ) -> dict[tuple[str, str], list[str]]:
        """Advisory ids for each `(package_name, version)`, in ≤100-sized calls.

        The key is the pair, not the name: two manifests pinning two different
        versions of the same package have genuinely different answers, and
        collapsing them would report one manifest's vulnerabilities against the
        other's version.
        """
        ids: dict[tuple[str, str], list[str]] = {}
        unique = sorted(set(targets))

        for start in range(0, len(unique), BATCH_SIZE):
            chunk = unique[start : start + BATCH_SIZE]
            payload = {
                "queries": [
                    {
                        "package": {"name": name, "ecosystem": _osv_ecosystem(ecosystem)},
                        "version": version,
                    }
                    for name, version in chunk
                ]
            }
            try:
                response = http.post_json(
                    f"{OSV_API}/v1/querybatch", payload, timeout=OSV_TIMEOUT
                )
            except http.UpstreamError:
                logger.warning("OSV querybatch failed for a chunk of %d.", len(chunk))
                raise

            results = (
                response.data.get("results") if isinstance(response.data, dict) else None
            )
            if not isinstance(results, list):
                raise ValueError("OSV querybatch returned an unexpected shape.")

            # OSV answers positionally: results[i] belongs to queries[i]. An
            # advisory-free package is an empty object, not an omission, so a
            # length mismatch means the answer cannot be trusted at all.
            if len(results) != len(chunk):
                raise ValueError(
                    f"OSV querybatch returned {len(results)} results "
                    f"for {len(chunk)} queries."
                )

            for target, result in zip(chunk, results, strict=True):
                vulns = result.get("vulns") if isinstance(result, dict) else None
                found = [
                    entry["id"]
                    for entry in (vulns or [])
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str)
                ]
                if found:
                    ids[target] = found

        return ids

    def detail(self, osv_id: str, package_name: str) -> Vulnerability | None:
        """One advisory, fetched at most once per run.

        `package_name` is not part of the cache key: the same advisory reached
        from a different package is the same document, and the per-package
        affected range is read out of it rather than refetched.
        """
        if osv_id not in self._documents:
            self._documents[osv_id] = self._fetch(osv_id)

        document = self._documents[osv_id]
        if document is None:
            return None
        return build_vulnerability(document, package_name)

    def _fetch(self, osv_id: str) -> dict | None:
        try:
            response = http.get_json(
                f"{OSV_API}/v1/vulns/{osv_id}",
                accept="application/json",
                timeout=OSV_TIMEOUT,
            )
        except http.UpstreamNotFound:
            # querybatch named an id the detail endpoint does not have. Rare,
            # and not a reason to fail a scan: the count still records that
            # *something* was found.
            logger.warning("OSV had no detail for an advisory id it returned.")
            return None
        except http.UpstreamError:
            logger.warning("OSV vulnerability detail lookup failed.")
            return None

        return response.data if isinstance(response.data, dict) else None


def build_vulnerability(document: dict, package_name: str = "") -> Vulnerability:
    """Turn one OSV document into the row §5.1 stores. Pure; no I/O."""
    cvss = _best_cvss(document)
    affected_range, fixed = _affected_summary(document, package_name)
    return Vulnerability(
        osv_id=str(document.get("id") or ""),
        cve_id=_cve_id(document),
        severity=_declared_severity(document)
        or severity_bucket(cvss)
        or Severity.UNKNOWN.value,
        cvss_score=cvss,
        published_at=_parse_timestamp(document.get("published")),
        summary=document.get("summary") or document.get("details") or None,
        affected_range=affected_range,
        fixed_version=fixed,
        source_url=_source_url(document),
    )


def _osv_ecosystem(ecosystem: str) -> str:
    """OSV's spelling of an ecosystem name (`npm`, `PyPI`) — theirs, not ours."""
    return {"npm": "npm", "pypi": "PyPI"}[ecosystem]
