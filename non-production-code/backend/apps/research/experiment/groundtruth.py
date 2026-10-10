"""S3's labelled set: flagged corpus dependencies with an answer a program can check.

§10 Phase 13 (D15): "over the corpus's flagged dependencies (research DB) —
`cve_fix` cases: target = minimum fixed version > resolved, from OSV ranges;
`deprecation_replacement` cases: successor parsed from deprecation text ("use X
instead", "replaced by X", "migrate to X"), **registry-verified to exist**;
unextractable -> dropped with the rate reported (an honest denominator)."

**No one labels anything.** The answer to "what should this dependency become"
is extracted from data the field already publishes — OSV's affected ranges and
the registry's own deprecation sentence — so the correctness metric needs no
human and no model (File C §3.3), and every item can say exactly where its
answer came from.

**A `cve_fix` answer is a set of versions, not one version.** OSV describes
each advisory as intervals: introduced at one version, fixed (or last affected,
or limited) at another. The item stores those intervals for every advisory
affecting the resolved version, and the correctness check asks whether a
recommended version escapes *all* of them. `target_version` — the smallest
version that does — is recorded for the report and for the reader, but a
recommendation of any later safe version is correct too; marking 4.17.21
correct and 4.17.22 wrong would be measuring the model's taste in minimums.
The target is found by taking the largest per-advisory fix and, while that
version is itself inside some advisory's interval, moving up to that
interval's fix — so a fix that a later advisory re-opens is not mistaken for
an answer. An advisory with no fix for the resolved version makes the item
unanswerable, and it is dropped with that reason.

The advisories in scope are the ones OSV returns for the *resolved* version —
the flagged ones, which are also the ones TARGET shows the model. An advisory
that only affects some later version is not part of the item: a recommended
upgrade can therefore be "correct" here and still carry a different, unflagged
advisory. That is File A's definition ("minimum fixed version > resolved"),
stated so nobody reads more into the metric than it measures.

**A successor is accepted only if it exists.** "Use X instead" parsed out of
free text produces candidates that are English words ("use native fetch
instead"), APIs ("use the URLSearchParams API instead") and the package's own
name; each is filtered and then looked up in the ecosystem's registry through
the same client the scanner uses. npm has refused new upper-case names since
2017, so an npm candidate must be lower case. File A names three phrasings;
four more that say the same thing are recognised, and every item records which
pattern matched, so the analysis can restrict to File A's three.

**The TARGET block is the production one.** Each item carries the TARGET dict
the production graph's `load_context` would build for the same dependency —
same keys, same advisory selection, same `fixed_version` derivation through
`osv.build_vulnerability` — so condition C is the production agent answering
the production prompt (`test_experiment_groundtruth.py` pins the key set to
`load_context`'s, so the two cannot drift). One consequence belongs in S3's
threats-to-validity and is recorded in `docs/decisions.md` §13: TARGET carries
the measured facts the answers are extracted from — an advisory's fixed
version, the registry's deprecation sentence — so correctness partly measures
whether a pipeline *uses* what it was given.
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.common import http
from apps.research.models import DataSource, DependencyHistory
from apps.scanning import adapters, osv
from apps.scanning.adapters import pep440, semver
from apps.scoring.engine import flag_reasons
from apps.scoring.normalize import Signals
from apps.scoring.weights import WeightSet, active_weights

logger = logging.getLogger(__name__)

CVE_FIX = "cve_fix"
DEPRECATION_REPLACEMENT = "deprecation_replacement"
CASE_TYPES: tuple[str, ...] = (CVE_FIX, DEPRECATION_REPLACEMENT)
ECOSYSTEMS: tuple[str, ...] = ("npm", "pypi")

#: §10 Phase 13 / D15: 150 items, 75 per ecosystem.
DEFAULT_SIZE = 150

#: `graph.MAX_ADVISORIES`: advisories carried into TARGET, worst first.
MAX_ADVISORIES = 5

# Reasons an item is dropped. A closed set, because the extraction report
# counts them and S3's selection-bias paragraph (File C L6) quotes them.
DROP_NO_ADVISORIES = "no_advisories_now"
DROP_NOT_AFFECTED = "resolved_version_not_affected"
DROP_NO_FIX = "no_fixed_version"
DROP_UNPARSEABLE = "unparseable_range"
DROP_NO_SUCCESSOR = "no_successor_in_text"
DROP_NOT_IN_REGISTRY = "successor_not_in_registry"
DROP_REGISTRY_UNAVAILABLE = "registry_unavailable"
DROP_OSV_UNAVAILABLE = "osv_unavailable"

# ── successor parsing ──────────────────────────────────────────────────────

_NAME = r"[`'\"]?(?P<name>@?[A-Za-z0-9][A-Za-z0-9._~/-]*[A-Za-z0-9])[`'\"]?"
_KIND = r"(?:\s+(?:package|module|library|lib|instead))?"

#: `(pattern id, regex)`, in the order they are tried. The first three are
#: File A's own wording.
SUCCESSOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "use_x_instead",
        re.compile(
            rf"\buse\s+(?:the\s+)?{_NAME}(?:\s+(?:package|module|library))?\s+instead\b",
            re.I,
        ),
    ),
    (
        "replaced_by_x",
        re.compile(rf"\breplaced\s+(?:by|with)\s+(?:the\s+)?{_NAME}{_KIND}", re.I),
    ),
    ("migrate_to_x", re.compile(rf"\bmigrate\s+to\s+(?:the\s+)?{_NAME}{_KIND}", re.I)),
    (
        "superseded_by_x",
        re.compile(rf"\bsuperseded\s+by\s+(?:the\s+)?{_NAME}{_KIND}", re.I),
    ),
    (
        "in_favor_of_x",
        re.compile(rf"\bin\s+favou?r\s+of\s+(?:the\s+)?{_NAME}{_KIND}", re.I),
    ),
    ("renamed_to_x", re.compile(rf"\brenamed\s+to\s+(?:the\s+)?{_NAME}{_KIND}", re.I)),
    ("moved_to_x", re.compile(rf"\bmoved\s+to\s+(?:the\s+)?{_NAME}{_KIND}", re.I)),
)
FILE_A_PATTERNS = frozenset({"use_x_instead", "replaced_by_x", "migrate_to_x"})

#: Words that the patterns capture and no registry lookup should be trusted on:
#: several are real npm package names ("a", "native", "fetch"), which is the
#: point — a registry hit on "native" verifies nothing.
STOPWORDS = frozenset(
    {
        "a", "an", "the", "this", "that", "it", "its", "another", "other", "others",
        "native", "built-in", "builtin", "standard", "stdlib", "node", "nodejs",
        "npm", "pypi", "python", "python3", "version", "versions", "latest", "new",
        "newer", "official", "something", "alternative", "alternatives", "instead",
        "them", "these", "those", "modern", "es6", "es2015", "js", "javascript",
        "fetch", "github", "http", "https", "www", "v1", "v2", "v3", "v4", "v5",
        "v6", "v7", "v8", "core", "one", "our", "your", "their", "upstream",
    }
)  # fmt: skip


def normalize_name(ecosystem: str, name: str) -> str:
    return pep440.normalize_name(name) if ecosystem == "pypi" else name.strip().lower()


def successor_candidates(
    reason: str, ecosystem: str, package: str
) -> list[tuple[str, str]]:
    """`(name, pattern id)` for each plausible successor named in `reason`, in order."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    own = normalize_name(ecosystem, package)
    for pattern_id, pattern in SUCCESSOR_PATTERNS:
        for match in pattern.finditer(reason or ""):
            name = match.group("name").rstrip("./-_~")
            if "/" in name and not name.startswith("@"):
                continue  # a path or a URL fragment, not a package
            if name.lower() in STOPWORDS or len(name) < 2:
                continue
            if ecosystem == "npm" and name != name.lower():
                continue  # npm refuses new upper-case names
            if re.fullmatch(r"v?\d[\d.]*", name):
                continue  # "migrate to 5.0" is an upgrade, not a replacement
            key = normalize_name(ecosystem, name)
            if key == own or key in seen:
                continue
            seen.add(key)
            found.append((name, pattern_id))
    return found


# ── OSV ranges and the version set they leave ──────────────────────────────

#: OSV writes "the beginning of time" as `introduced: "0"`.
_BEGINNING = frozenset({"0", ""})


def version_key(ecosystem: str, text: str | None):
    """A comparable key for one version in the ecosystem's grammar, or None."""
    if text is None:
        return None
    parse = pep440.parse if ecosystem == "pypi" else semver.parse
    parsed = parse(text.strip().lstrip("vV") if ecosystem == "npm" else text.strip())
    return parsed.sort_key() if parsed is not None else None


@dataclass(frozen=True)
class Interval:
    """One affected range: from `introduced`, up to `fixed`/`limit` (exclusive)
    or `last_affected` (inclusive), or open-ended."""

    introduced: str | None = None
    fixed: str | None = None
    last_affected: str | None = None
    limit: str | None = None

    def contains(self, ecosystem: str, version: str) -> bool | None:
        """None when a bound cannot be read in the ecosystem's grammar."""
        key = version_key(ecosystem, version)
        if key is None:
            return None
        if self.introduced not in _BEGINNING and self.introduced is not None:
            low = version_key(ecosystem, self.introduced)
            if low is None:
                return None
            if key < low:
                return False
        for bound, inclusive in (
            (self.fixed, False),
            (self.limit, False),
            (self.last_affected, True),
        ):
            if bound is None:
                continue
            high = version_key(ecosystem, bound)
            if high is None:
                return None
            if key > high or (key == high and not inclusive):
                return False
        return True

    def as_json(self) -> dict:
        return {
            key: value
            for key, value in (
                ("introduced", self.introduced),
                ("fixed", self.fixed),
                ("last_affected", self.last_affected),
                ("limit", self.limit),
            )
            if value is not None
        }

    @classmethod
    def from_json(cls, data: dict) -> Interval:
        return cls(
            **{
                key: data.get(key)
                for key in ("introduced", "fixed", "last_affected", "limit")
            }
        )


def intervals_from_events(events: list) -> list[Interval]:
    """OSV's ordered event list -> intervals. An unmatched `introduced` is open."""
    found: list[Interval] = []
    start: str | None = None
    open_ = False
    for event in events or []:
        if not isinstance(event, dict):
            continue
        if "introduced" in event:
            start, open_ = str(event["introduced"]), True
        elif open_ and "fixed" in event:
            found.append(Interval(introduced=start, fixed=str(event["fixed"])))
            open_ = False
        elif open_ and "last_affected" in event:
            found.append(
                Interval(introduced=start, last_affected=str(event["last_affected"]))
            )
            open_ = False
        elif open_ and "limit" in event:
            found.append(Interval(introduced=start, limit=str(event["limit"])))
            open_ = False
    if open_:
        found.append(Interval(introduced=start))
    return found


@dataclass(frozen=True)
class AdvisoryRanges:
    osv_id: str
    cve_id: str | None
    intervals: tuple[Interval, ...]
    versions: tuple[str, ...]

    def affects(self, ecosystem: str, version: str) -> bool | None:
        if version in self.versions:
            return True
        verdicts = [interval.contains(ecosystem, version) for interval in self.intervals]
        if any(verdict is True for verdict in verdicts):
            return True
        if any(verdict is None for verdict in verdicts):
            return None
        return False

    def as_json(self) -> dict:
        return {
            "osv_id": self.osv_id,
            "cve_id": self.cve_id,
            "intervals": [interval.as_json() for interval in self.intervals],
            "versions": list(self.versions),
        }

    @classmethod
    def from_json(cls, data: dict) -> AdvisoryRanges:
        return cls(
            osv_id=str(data.get("osv_id") or ""),
            cve_id=data.get("cve_id"),
            intervals=tuple(
                Interval.from_json(entry) for entry in data.get("intervals") or []
            ),
            versions=tuple(data.get("versions") or ()),
        )


def advisory_ranges(
    document: dict, ecosystem: str, package: str
) -> AdvisoryRanges | None:
    """This advisory's ranges for this package, or None if it names it nowhere."""
    if document.get("withdrawn"):
        return None
    own = normalize_name(ecosystem, package)
    intervals: list[Interval] = []
    versions: list[str] = []
    for affected in document.get("affected") or []:
        if not isinstance(affected, dict):
            continue
        named = (affected.get("package") or {}).get("name") or ""
        if normalize_name(ecosystem, str(named)) != own:
            continue
        for entry in affected.get("ranges") or []:
            if isinstance(entry, dict) and entry.get("type") in ("SEMVER", "ECOSYSTEM"):
                intervals.extend(intervals_from_events(entry.get("events")))
        versions.extend(
            str(v) for v in affected.get("versions") or [] if isinstance(v, str)
        )
    if not intervals and not versions:
        return None
    return AdvisoryRanges(
        osv_id=str(document.get("id") or ""),
        cve_id=osv._cve_id(document),
        intervals=tuple(intervals),
        versions=tuple(dict.fromkeys(versions)),
    )


def is_safe_version(
    ecosystem: str, version: str, resolved: str, advisories: list[AdvisoryRanges]
) -> bool | None:
    """Is `version` an upgrade from `resolved` that escapes every advisory?

    None when the version, or a bound it must be compared with, cannot be read
    in the ecosystem's grammar — an unreadable recommendation is not correct,
    and the caller decides how to count it.
    """
    key = version_key(ecosystem, version)
    base = version_key(ecosystem, resolved)
    if key is None or base is None:
        return None
    if key <= base:
        return False
    for advisory in advisories:
        verdict = advisory.affects(ecosystem, version)
        if verdict is None:
            return None
        if verdict:
            return False
    return True


def answer_given(item: dict) -> bool:
    """Does TARGET hand every condition a value that, copied, is scored correct?

    decisions §13.2 and §13.13. For `cve_fix`, true when some advisory's
    `fixed_version` in TARGET is itself a safe upgrade under the item's ground
    truth; false when every one shown is still affected by another advisory, or
    none is readable — the items where the right version has to be worked out.
    For `deprecation_replacement`, true when the deprecation sentence TARGET
    carries names the successor, which by construction it always does.
    """
    target = item.get("target") or {}
    ecosystem = item["ecosystem"]
    truth = item.get("ground_truth") or {}
    if item["case_type"] == CVE_FIX:
        advisories = [
            AdvisoryRanges.from_json(entry) for entry in truth.get("advisories") or []
        ]
        return any(
            is_safe_version(
                ecosystem,
                str(shown["fixed_version"]),
                item["resolved_version"],
                advisories,
            )
            is True
            for shown in target.get("advisories") or []
            if shown.get("fixed_version")
        )
    if item["case_type"] == DEPRECATION_REPLACEMENT:
        named = {
            normalize_name(ecosystem, name)
            for name, _ in successor_candidates(
                target.get("deprecation_reason") or "", ecosystem, item["package"]
            )
        }
        return truth.get("successor_normalized") in named
    raise ValueError(f"unknown case type {item['case_type']!r}")


def minimum_fix(
    ecosystem: str, resolved: str, advisories: list[AdvisoryRanges]
) -> tuple[str | None, str | None]:
    """`(target, None)` or `(None, drop reason)` for a set of advisories."""
    relevant = []
    for advisory in advisories:
        verdict = advisory.affects(ecosystem, resolved)
        if verdict is None:
            return None, DROP_UNPARSEABLE
        if verdict:
            relevant.append(advisory)
    if not relevant:
        return None, DROP_NOT_AFFECTED

    def fix_covering(version: str) -> tuple[str | None, bool]:
        """The fix of the interval that contains `version`; (None, True) if unfixed.

        An advisory's ranges are read before its enumerated `versions`: OSV's
        PyPI advisories list every affected release *and* give the ranges with
        their fixes, so a listed version says "affected", not "unfixed". Only a
        version listed and covered by no range has no known fix (decisions
        §13.14: checking the list first dropped 771 of 783 PyPI items).
        """
        for advisory in relevant:
            for interval in advisory.intervals:
                inside = interval.contains(ecosystem, version)
                if inside is None:
                    raise ValueError(DROP_UNPARSEABLE)
                if inside:
                    return (interval.fixed, interval.fixed is None)
            if version in advisory.versions:
                return None, True
        return None, False

    candidate = resolved
    try:
        for _ in range(64):  # each step strictly increases the version
            fix, unfixed = fix_covering(candidate)
            if unfixed:
                return None, DROP_NO_FIX
            if fix is None:
                break
            candidate = fix
        else:  # pragma: no cover - would need 64 chained re-openings
            return None, DROP_NO_FIX
    except ValueError:
        return None, DROP_UNPARSEABLE
    if candidate == resolved:
        return None, DROP_NOT_AFFECTED
    return candidate, None


# ── the corpus's flagged dependencies ──────────────────────────────────────


@dataclass
class Candidate:
    """One flagged (ecosystem, package, resolved version), pooled across the corpus."""

    ecosystem: str
    package: str
    resolved_version: str
    declared_specifier: str | None
    resolution: str | None
    latest_version: str | None
    dependency_group: str
    manifest_path: str
    versions_behind: dict
    is_deprecated: bool
    deprecation_reason: str | None
    vulnerability_count: int
    highest_severity: str | None
    cvss_max: object
    staleness_days: int | None
    repositories: set = field(default_factory=set)
    occurrences: int = 0

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            self.ecosystem,
            normalize_name(self.ecosystem, self.package),
            self.resolved_version,
        )


def corpus_candidates(snapshot_date: date) -> list[Candidate]:
    """Every flagged, assessable occurrence of the snapshot, pooled by package+version.

    Flagged here means the two clauses an S3 case can come from: deprecated, or
    vulnerable. Staleness alone has no "correct remediation" to extract.
    """
    rows = (
        DependencyHistory.objects.filter(
            scan_history__data_source=DataSource.CORPUS_SCAN.value,
            scan_history__snapshot_date=snapshot_date,
            is_unassessable=False,
        )
        .exclude(resolved_version=None)
        .filter(models_q_flagged())
        .order_by("ecosystem", "package_name", "resolved_version", "manifest_path")
        .values(
            "scan_history_id",
            "ecosystem",
            "package_name",
            "resolved_version",
            "declared_specifier",
            "resolution",
            "latest_version",
            "dependency_group",
            "manifest_path",
            "versions_behind_major",
            "versions_behind_minor",
            "versions_behind_patch",
            "is_deprecated",
            "deprecation_reason",
            "vulnerability_count",
            "highest_severity",
            "cvss_max",
            "staleness_days",
        )
    )
    pooled: dict[tuple[str, str, str], Candidate] = {}
    for row in rows.iterator(chunk_size=2000):
        candidate = Candidate(
            ecosystem=row["ecosystem"],
            package=row["package_name"],
            resolved_version=row["resolved_version"],
            declared_specifier=row["declared_specifier"],
            resolution=row["resolution"],
            latest_version=row["latest_version"],
            dependency_group=row["dependency_group"],
            manifest_path=row["manifest_path"],
            versions_behind={
                "major": row["versions_behind_major"],
                "minor": row["versions_behind_minor"],
                "patch": row["versions_behind_patch"],
            },
            is_deprecated=row["is_deprecated"],
            deprecation_reason=row["deprecation_reason"],
            vulnerability_count=row["vulnerability_count"],
            highest_severity=row["highest_severity"],
            cvss_max=row["cvss_max"],
            staleness_days=row["staleness_days"],
        )
        existing = pooled.setdefault(candidate.key, candidate)
        existing.repositories.add(str(row["scan_history_id"]))
        existing.occurrences += 1
    return list(pooled.values())


def models_q_flagged():
    from django.db.models import Q

    return Q(is_deprecated=True) | Q(vulnerability_count__gt=0)


# ── items ──────────────────────────────────────────────────────────────────


def item_id(ecosystem: str, package: str, version: str, case_type: str) -> str:
    digest = hashlib.sha256(
        f"{ecosystem}|{normalize_name(ecosystem, package)}|{version}|{case_type}".encode()
    ).hexdigest()
    return f"S3-{digest[:10]}"


def build_target(
    candidate: Candidate, documents: list[dict], weights: WeightSet
) -> tuple[dict, list[dict]]:
    """TARGET and the §5.8 cross-check rows, in `graph.load_context`'s shape."""
    built = {}
    for document in documents:
        vulnerability = osv.build_vulnerability(document, candidate.package)
        if vulnerability.osv_id and vulnerability.osv_id not in built:
            built[vulnerability.osv_id] = vulnerability
    advisories = sorted(
        built.values(), key=lambda v: (-float(v.cvss_score or 0), v.osv_id)
    )[:MAX_ADVISORIES]
    signals = Signals(
        is_deprecated=candidate.is_deprecated,
        vulnerability_count=candidate.vulnerability_count,
        cvss_max=Decimal(candidate.cvss_max) if candidate.cvss_max is not None else None,
        staleness_days=candidate.staleness_days,
    )
    target = {
        "package": candidate.package,
        "ecosystem": candidate.ecosystem,
        "manifest_path": candidate.manifest_path,
        "group": candidate.dependency_group,
        "declared_specifier": candidate.declared_specifier,
        "current_version": candidate.resolved_version,
        "version_source": candidate.resolution,
        "latest_version": candidate.latest_version,
        "versions_behind": dict(candidate.versions_behind),
        "deprecated": candidate.is_deprecated,
        "advisory_count": candidate.vulnerability_count,
        "highest_severity": candidate.highest_severity,
        "flag_reasons": list(flag_reasons(signals, weights)),
        "advisories": [
            {
                "osv_id": v.osv_id,
                "cve_id": v.cve_id,
                "severity": v.severity,
                "cvss": float(v.cvss_score) if v.cvss_score is not None else None,
                "fixed_version": v.fixed_version,
            }
            for v in advisories
        ],
    }
    if candidate.staleness_days is not None:
        target["days_since_release"] = candidate.staleness_days
    if candidate.is_deprecated and candidate.deprecation_reason is not None:
        target["deprecation_reason"] = candidate.deprecation_reason
    cves = list(dict.fromkeys(v.cve_id or v.osv_id for v in advisories))
    rows = [
        {
            "package": candidate.package,
            "ecosystem": candidate.ecosystem,
            "manifest_path": candidate.manifest_path,
            "current_version": candidate.resolved_version,
            "highest_severity": candidate.highest_severity,
            "cves": cves,
        }
    ]
    return target, rows


@dataclass
class Extraction:
    items: list[dict]
    #: `{(ecosystem, case_type): {"candidates": n, "extracted": n, reason: n, ...}}`
    coverage: dict
    candidates: int


def extract(
    candidates: list[Candidate],
    *,
    snapshot_date: date,
    osv_client: osv.OsvClient | None = None,
    weights: WeightSet | None = None,
    progress=None,
) -> Extraction:
    """Every candidate, tried for both case types; dropped ones counted by reason."""
    weights = weights or active_weights()
    client = osv_client or osv.OsvClient()
    coverage: dict = defaultdict(lambda: defaultdict(int))
    items: list[dict] = []

    # OSV, batched per ecosystem: one querybatch call per hundred candidates.
    advisory_ids: dict[tuple[str, str, str], list[str]] = {}
    osv_failed: set[str] = set()
    for ecosystem in ECOSYSTEMS:
        wanted = [
            c
            for c in candidates
            if c.ecosystem == ecosystem and c.vulnerability_count > 0
        ]
        if not wanted:
            continue
        try:
            found = client.query_batch(
                ecosystem, [(c.package, c.resolved_version) for c in wanted]
            )
        except (http.UpstreamError, ValueError):
            logger.warning(
                "OSV querybatch failed for %s; those candidates are dropped.", ecosystem
            )
            osv_failed.add(ecosystem)
            continue
        for candidate in wanted:
            advisory_ids[candidate.key] = found.get(
                (candidate.package, candidate.resolved_version), []
            )

    registries: dict[str, object] = {}
    verified: dict[tuple[str, str], str] = {}

    for index, candidate in enumerate(candidates, 1):
        documents = [
            document
            for document in (
                client.document(i) for i in advisory_ids.get(candidate.key, [])
            )
            if isinstance(document, dict)
        ]
        target, rows = build_target(candidate, documents, weights)
        base = {
            "ecosystem": candidate.ecosystem,
            "package": candidate.package,
            "resolved_version": candidate.resolved_version,
            "target": target,
            "context_rows": rows,
            "corpus": {
                "snapshot_date": snapshot_date.isoformat(),
                "repositories": len(candidate.repositories),
                "occurrences": candidate.occurrences,
            },
        }

        if candidate.vulnerability_count > 0:
            cell = coverage[(candidate.ecosystem, CVE_FIX)]
            cell["candidates"] += 1
            if candidate.ecosystem in osv_failed:
                cell[DROP_OSV_UNAVAILABLE] += 1
            elif not documents:
                cell[DROP_NO_ADVISORIES] += 1
            else:
                ranges = [
                    found
                    for found in (
                        advisory_ranges(d, candidate.ecosystem, candidate.package)
                        for d in documents
                    )
                    if found is not None
                ]
                target_version, reason = minimum_fix(
                    candidate.ecosystem, candidate.resolved_version, ranges
                )
                if reason:
                    cell[reason] += 1
                else:
                    cell["extracted"] += 1
                    items.append(
                        {
                            "item_id": item_id(
                                candidate.ecosystem,
                                candidate.package,
                                candidate.resolved_version,
                                CVE_FIX,
                            ),
                            "case_type": CVE_FIX,
                            **base,
                            "ground_truth": {
                                "target_version": target_version,
                                "advisories": [
                                    r.as_json()
                                    for r in ranges
                                    if r.affects(
                                        candidate.ecosystem, candidate.resolved_version
                                    )
                                ],
                            },
                        }
                    )

        if candidate.is_deprecated:
            cell = coverage[(candidate.ecosystem, DEPRECATION_REPLACEMENT)]
            cell["candidates"] += 1
            names = successor_candidates(
                candidate.deprecation_reason or "", candidate.ecosystem, candidate.package
            )
            if not names:
                cell[DROP_NO_SUCCESSOR] += 1
            else:
                registry = registries.get(candidate.ecosystem)
                if registry is None:
                    registry = adapters.get_adapter(candidate.ecosystem).registry_client()
                    registries[candidate.ecosystem] = registry
                chosen = None
                outcome = DROP_NOT_IN_REGISTRY
                for name, pattern_id in names:
                    key = (candidate.ecosystem, normalize_name(candidate.ecosystem, name))
                    status = verified.get(key)
                    if status is None:
                        facts = registry.facts(name, None)
                        status = (
                            "unavailable"
                            if facts.unavailable
                            else "missing"
                            if facts.not_found
                            else "exists"
                        )
                        verified[key] = status
                    if status == "exists":
                        chosen = (name, pattern_id)
                        break
                    if status == "unavailable":
                        outcome = DROP_REGISTRY_UNAVAILABLE
                if chosen is None:
                    cell[outcome] += 1
                else:
                    cell["extracted"] += 1
                    items.append(
                        {
                            "item_id": item_id(
                                candidate.ecosystem,
                                candidate.package,
                                candidate.resolved_version,
                                DEPRECATION_REPLACEMENT,
                            ),
                            "case_type": DEPRECATION_REPLACEMENT,
                            **base,
                            "ground_truth": {
                                "successor": chosen[0],
                                "successor_normalized": normalize_name(
                                    candidate.ecosystem, chosen[0]
                                ),
                                "pattern": chosen[1],
                                "file_a_pattern": chosen[1] in FILE_A_PATTERNS,
                                "reason": candidate.deprecation_reason,
                                "other_candidates": [
                                    name for name, _ in names if name != chosen[0]
                                ],
                            },
                        }
                    )
        if progress is not None and (index % 100 == 0 or index == len(candidates)):
            progress(f"extracted from {index}/{len(candidates)} candidates")

    items.sort(key=lambda entry: entry["item_id"])
    return Extraction(
        items=items,
        coverage={key: dict(value) for key, value in coverage.items()},
        candidates=len(candidates),
    )


# ── the stratified sample ──────────────────────────────────────────────────


@dataclass
class Quota:
    ecosystem: str
    case_type: str
    available: int
    target: int
    taken: int

    @property
    def shortfall(self) -> int:
        return max(0, self.target - self.taken)


def stratified_sample(
    items: list[dict],
    *,
    size: int = DEFAULT_SIZE,
    replacement_share: float = 0.5,
    seed: int = 42,
) -> tuple[list[dict], list[Quota]]:
    """Half the set per ecosystem; within each, the replacement share asked for.

    A stratum that cannot fill its share hands the remainder to the other case
    type of the same ecosystem, and the shortfall is recorded rather than
    smoothed over: PyPI's replacement stratum is expected to be thin (File C
    L7), and that asymmetry is a finding the quotas have to show.
    """
    per_ecosystem = size // len(ECOSYSTEMS)
    rng = random.Random(seed)  # noqa: S311 - sampling, not crypto
    selected: list[dict] = []
    quotas: list[Quota] = []
    for ecosystem in ECOSYSTEMS:
        pools = {
            case: sorted(
                (
                    i
                    for i in items
                    if i["ecosystem"] == ecosystem and i["case_type"] == case
                ),
                key=lambda entry: entry["item_id"],
            )
            for case in CASE_TYPES
        }
        for pool in pools.values():
            rng.shuffle(pool)
        wanted_replacement = round(per_ecosystem * replacement_share)
        targets = {
            DEPRECATION_REPLACEMENT: wanted_replacement,
            CVE_FIX: per_ecosystem - wanted_replacement,
        }
        taken = {case: min(targets[case], len(pools[case])) for case in CASE_TYPES}
        # Hand an unfilled share to the other case type of the same ecosystem.
        for case, other in (
            (DEPRECATION_REPLACEMENT, CVE_FIX),
            (CVE_FIX, DEPRECATION_REPLACEMENT),
        ):
            spare = targets[case] - taken[case]
            if spare > 0:
                taken[other] = min(len(pools[other]), taken[other] + spare)
        for case in CASE_TYPES:
            selected.extend(pools[case][: taken[case]])
            quotas.append(
                Quota(
                    ecosystem=ecosystem,
                    case_type=case,
                    available=len(pools[case]),
                    target=targets[case],
                    taken=taken[case],
                )
            )
    selected.sort(
        key=lambda entry: (entry["ecosystem"], entry["case_type"], entry["item_id"])
    )
    return selected, quotas


# ── the extraction report ──────────────────────────────────────────────────


def extraction_report(
    extraction: Extraction,
    quotas: list[Quota] | None,
    *,
    snapshot_date: date,
    size: int,
    sampled_from: int | None = None,
) -> str:
    """What was tried, what was kept, and why the rest was dropped (File C L6)."""
    lines = [
        "# S3 ground-truth extraction report",
        "",
        "Generated by `manage.py extract_ground_truth` (§10 Phase 13, D15). "
        f"Corpus snapshot `{snapshot_date.isoformat()}`.",
        "",
        f"- Flagged (package, version) candidates examined: {extraction.candidates}"
        + (
            f" — a seeded sample of {sampled_from}, so the rates below are an "
            f"estimate and no labelled set was written"
            if sampled_from is not None
            else ""
        ),
        f"- Items extracted: {len(extraction.items)}",
        "",
        "## Coverage, and the honest denominator",
        "",
        "| Ecosystem | Case type | Candidates | Extracted | Rate | Dropped, by reason |",
        "|---|---|---|---|---|---|",
    ]
    for ecosystem in ECOSYSTEMS:
        for case in CASE_TYPES:
            cell = extraction.coverage.get((ecosystem, case), {})
            candidates = cell.get("candidates", 0)
            extracted = cell.get("extracted", 0)
            reasons = ", ".join(
                f"{reason} {count}"
                for reason, count in sorted(cell.items())
                if reason not in ("candidates", "extracted")
            )
            rate = f"{extracted / candidates:.0%}" if candidates else "-"
            lines.append(
                f"| {ecosystem} | {case} | {candidates} | {extracted} | {rate} | {reasons or '-'} |"
            )
    given = Counter(
        (item["ecosystem"], item["case_type"])
        for item in extraction.items
        if answer_given(item)
    )
    totals = Counter((item["ecosystem"], item["case_type"]) for item in extraction.items)
    lines += [
        "",
        "## Items whose answer TARGET already shows (decisions §13.13)",
        "",
        "| Ecosystem | Case type | Extracted | Answer given | Answer not given |",
        "|---|---|---|---|---|",
    ]
    for ecosystem in ECOSYSTEMS:
        for case in CASE_TYPES:
            total = totals[(ecosystem, case)]
            lines.append(
                f"| {ecosystem} | {case} | {total} | {given[(ecosystem, case)]} | "
                f"{total - given[(ecosystem, case)]} |"
            )
    lines += [
        "",
        "Correctness on the answer-not-given items is reported as its own table, the",
        "comparison where retrieval has something to add.",
    ]
    if len(extraction.items) < size:
        lines += [
            "",
            f"**SHORTFALL: {len(extraction.items)} items extracted, fewer than the "
            f"{size} the labelled set needs.** Flag this before WP-8 (§10 Phase 13's "
            f"acceptance asks for at least {size} candidates).",
        ]
    if quotas is not None:
        lines += [
            "",
            "## The stratified sample",
            "",
            "| Ecosystem | Case type | Available | Quota | Taken | Shortfall |",
            "|---|---|---|---|---|---|",
        ]
        for quota in quotas:
            lines.append(
                f"| {quota.ecosystem} | {quota.case_type} | {quota.available} | "
                f"{quota.target} | {quota.taken} | {quota.shortfall or '-'} |"
            )
        lines += [
            "",
            "A stratum short of its quota hands the rest to the other case type of",
            "the same ecosystem. PyPI's replacement stratum is expected to be thin —",
            "its deprecation text rarely names a successor (D2) — and that asymmetry",
            "is itself a finding (File C L7). The cve_fix stratum is the controlled",
            "ecosystem head-to-head.",
        ]
    lines += [
        "",
        "## What this set cannot support",
        "",
        "- **Selection** (File C L6): only automatable cases are here; the dropped",
        "  ones above are not missing at random.",
        "- **Case mix** (L7): npm and PyPI contribute different shares of each case",
        "  type; compare ecosystems within a case type.",
        "- **The answer is in TARGET** (decisions §13.2): the fixed version and the",
        "  deprecation sentence the ground truth is extracted from are measurements",
        "  the production prompt shows every condition. The table above counts the",
        "  items where copying them is enough.",
        "",
    ]
    return "\n".join(lines)
