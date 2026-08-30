"""The scan orchestrator — tree to stored signals, one repository at a time.

The shape §10 Phase 3 fixes:

    re-list the tree  →  fetch each manifest and its sibling lockfile
      →  parse per adapter  →  pool occurrences tagged with their manifest path
      →  enrich from the registry and OSV  →  persist every raw signal

Four things about it are load-bearing rather than incidental.

**The tree is re-listed at scan time.** Registration validated a tree that may
be weeks old (§5.6). Scanning what was there then, rather than what is there
now, would report on a repository that no longer exists — and a rescan whose
whole purpose is to notice change would be structurally unable to.

**Occurrences are pooled, not deduplicated.** `lodash` in three manifests is
three rows carrying three manifest paths. They are three installations, each
needing its own remediation, and §5.3's roll-up is built to count them
independently. Collapsing them would understate a monorepo by construction.

**Every raw signal is persisted, even when nothing consumes it yet.** D6 and
D17: `versions_behind_*` is not a formula term (D3) and `published_at` is not
displayed anywhere, but the research needs both, and neither can be
reconstructed after the fact. Recording them costs a column; not recording
them costs a study.

**Nothing fetched is ever executed.** Manifests and lockfiles arrive as bytes,
are size-capped before they are decoded, and are handed to a parser that only
ever calls `json.loads` (§11 "manifest parsing abuse"). A parse failure is
caught per manifest: one malformed `package.json` in a twelve-manifest
monorepo must not cost the other eleven their scan.
"""

from __future__ import annotations

import base64
import binascii
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import quote

from django.db import transaction

from apps.common import http

from . import adapters, osv
from .models import (
    SEVERITY_RANK,
    DependencyOccurrence,
    DependencyVulnerability,
    ManifestFile,
    Package,
    Resolution,
    ScanRun,
    Severity,
)

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

#: A `package.json` is kilobytes. Anything at this size is not a manifest, and
#: decoding it would spend the free tier's memory on a file no parser wants.
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
#: Lockfiles legitimately reach several megabytes on a large project — they
#: enumerate the whole transitive tree — so the cap is separate and larger.
#: Past it, the manifest still scans; its rows simply fall back to
#: `range_latest_approx`, which is a degraded answer rather than no answer.
MAX_LOCKFILE_BYTES = 6 * 1024 * 1024
#: A guard, not a policy. Real repositories in this product's population have
#: single figures of manifests; a tree with more than this is either generated
#: or vendored in a way `VENDOR_DIRS` did not catch, and scanning all of it
#: would spend the user's GitHub quota discovering that. Shallow paths are
#: kept first, so the repository's own manifests survive the cut.
MAX_MANIFESTS = 50

#: Reason recorded when the registry has never published a declared package.
REASON_NOT_IN_REGISTRY = "not_in_registry"
#: Reason recorded when the registry could not be reached for one package.
#: Distinct from the above: this is a fact about the scan, not the package.
REASON_REGISTRY_UNAVAILABLE = "registry_unavailable"


class ScanFailed(Exception):
    """A scan that cannot produce an answer, with text fit to show a user.

    Raised only where the failure has a remedy worth stating. Anything else
    propagates as itself and the background runner records a generic message —
    an internal error should never reach the browser wearing a specific
    explanation it does not have.
    """


@dataclass
class ManifestPlan:
    """One manifest found in the tree, with the lockfile that sits beside it."""

    adapter: adapters.DependencyAdapter
    path: str
    sha: str
    size: int
    lockfile_path: str | None = None
    lockfile_sha: str | None = None
    lockfile_size: int = 0

    @property
    def directory(self) -> str:
        head, _, _ = self.path.rpartition("/")
        return head


@dataclass
class PooledOccurrence:
    """A `DepSpec` that remembers which manifest it came from.

    It holds the *plan*, not a database row: no `manifest_files` row exists
    until `_persist`, so that a scan which fails during enrichment leaves
    nothing behind — a manifest row with no dependencies under it reads as "we
    scanned this and it declares nothing", which is a different and untrue
    claim.
    """

    plan: ManifestPlan
    ecosystem: str
    spec: adapters.DepSpec
    #: Filled during enrichment; None while unresolved or unassessable.
    facts: adapters.PackageFacts | None = None
    vulnerabilities: list[osv.Vulnerability] = field(default_factory=list)

    @property
    def assessed_version(self) -> str | None:
        if self.facts is not None and self.facts.assessed_version:
            return self.facts.assessed_version
        return self.spec.resolved_version


# ── GitHub source access ───────────────────────────────────────────────────
# Every URL is built here from `GITHUB_API` and values GitHub itself returned
# at registration. Nothing user-typed reaches an outbound call (§5.6).


def _fetch_tree(scan: ScanRun, token: str) -> list[dict]:
    repository = scan.repository
    branch = repository.default_branch or ""
    if not branch:
        raise ScanFailed("This repository has no default branch to scan.")

    path = (
        f"/repos/{quote(repository.owner)}/{quote(repository.name)}"
        f"/git/trees/{quote(branch, safe='')}"
    )
    try:
        response = http.get_json(
            f"{GITHUB_API}{path}", token=token, params={"recursive": "1"}
        )
    except http.UpstreamUnauthorized as exc:
        raise ScanFailed(
            "Your GitHub sign-in is no longer valid. Sign out and sign in "
            "again, then run the scan."
        ) from exc
    except (http.UpstreamNotFound, http.UpstreamForbidden) as exc:
        raise ScanFailed(
            "We can no longer reach this repository on GitHub. It may have "
            "been renamed, made private, or had access removed."
        ) from exc
    except http.UpstreamRateLimited as exc:
        raise ScanFailed(
            "GitHub rate-limited this scan. Please try again in a few minutes."
        ) from exc
    except http.UpstreamError as exc:
        raise ScanFailed(
            "We couldn't reach GitHub to read this repository. Please try again shortly."
        ) from exc

    data = response.data if isinstance(response.data, dict) else {}
    if data.get("truncated"):
        # §5.6 accepts this: a ~100k-entry tree is far outside this product's
        # demonstrated scale, and walking the tree directory by directory would
        # spend the user's whole rate-limit budget on the rare case.
        logger.info(
            "Tree for %s was truncated; scanning the returned entries.",
            scan.repository_id,
        )

    tree = data.get("tree")
    return tree if isinstance(tree, list) else []


def _fetch_blob(scan: ScanRun, token: str, sha: str, cap: int) -> bytes | None:
    """One blob by sha, or None if it is too large or undecodable.

    The blob endpoint rather than the contents endpoint: the tree already
    supplied the sha and the size, so the size can be checked *before* the
    fetch, and the blob API's 100 MB ceiling accommodates real lockfiles where
    the contents API's 1 MB does not.
    """
    repository = scan.repository
    path = (
        f"/repos/{quote(repository.owner)}/{quote(repository.name)}"
        f"/git/blobs/{quote(sha)}"
    )
    try:
        response = http.get_json(f"{GITHUB_API}{path}", token=token)
    except http.UpstreamRateLimited as exc:
        # Not a per-file problem: the budget is gone, so every remaining fetch
        # in this scan would fail too. Stopping now leaves a clear message
        # instead of a scan that silently read three manifests out of nine.
        raise ScanFailed(
            "GitHub rate-limited this scan. Please try again in a few minutes."
        ) from exc
    except http.UpstreamError:
        logger.warning("Could not read a blob during a scan.")
        return None

    document = response.data if isinstance(response.data, dict) else {}
    if document.get("encoding") != "base64":
        # GitHub reports `"encoding": "none"` for blobs it will not inline.
        logger.warning("Blob returned an unusable encoding; skipping it.")
        return None

    try:
        raw = base64.b64decode(document.get("content") or "")
    except (binascii.Error, ValueError):
        logger.warning("Blob content was not decodable base64; skipping it.")
        return None

    if len(raw) > cap:
        return None
    return raw


# ── planning ───────────────────────────────────────────────────────────────


def plan_manifests(tree: list[dict]) -> list[ManifestPlan]:
    """Match the tree against every registered adapter, shallowest paths first.

    Vendored directories are excluded by `adapters.adapter_for_path`, so a
    checked-in `node_modules` cannot contribute manifests (§2.3).
    """
    blobs = {
        entry["path"]: entry
        for entry in tree
        if isinstance(entry, dict)
        and entry.get("type") == "blob"
        and isinstance(entry.get("path"), str)
    }

    plans: list[ManifestPlan] = []
    for path, entry in blobs.items():
        adapter = adapters.adapter_for_path(path)
        if adapter is None:
            continue

        plan = ManifestPlan(
            adapter=adapter,
            path=path,
            sha=str(entry.get("sha") or ""),
            size=int(entry.get("size") or 0),
        )

        directory = plan.directory
        for lockfile_name in adapter.lockfile_names(path):
            candidate = f"{directory}/{lockfile_name}" if directory else lockfile_name
            sibling = blobs.get(candidate)
            if sibling is not None:
                plan.lockfile_path = candidate
                plan.lockfile_sha = str(sibling.get("sha") or "")
                plan.lockfile_size = int(sibling.get("size") or 0)
                break

        plans.append(plan)

    # Depth first, then alphabetically: deterministic, and it keeps the
    # repository's own root manifests ahead of anything deeply nested when
    # MAX_MANIFESTS has to cut.
    plans.sort(key=lambda plan: (plan.path.count("/"), plan.path))
    if len(plans) > MAX_MANIFESTS:
        logger.warning(
            "Tree contained %d manifests; scanning the %d shallowest.",
            len(plans),
            MAX_MANIFESTS,
        )
        plans = plans[:MAX_MANIFESTS]
    return plans


# ── enrichment ─────────────────────────────────────────────────────────────


def _enrich_from_registries(pool: list[PooledOccurrence]) -> None:
    """Ask each ecosystem's registry about every assessable occurrence.

    A single package the registry has never heard of becomes unassessable — a
    fact about that package. A registry that answered nothing at all fails the
    whole scan instead: recording "unassessable" for every row would write a
    permanent claim about the packages out of a temporary fact about the
    network.
    """
    by_ecosystem: dict[str, list[PooledOccurrence]] = defaultdict(list)
    for occurrence in pool:
        if not occurrence.spec.is_unassessable:
            by_ecosystem[occurrence.ecosystem].append(occurrence)

    for ecosystem, occurrences in by_ecosystem.items():
        client = adapters.get_adapter(ecosystem).registry_client()
        memo: dict[tuple[str, str | None], adapters.PackageFacts] = {}
        attempted = 0
        unavailable = 0

        for occurrence in occurrences:
            key = (occurrence.spec.name, occurrence.spec.resolved_version)
            if key not in memo:
                attempted += 1
                memo[key] = client.facts(*key)
                if memo[key].unavailable:
                    unavailable += 1
            occurrence.facts = memo[key]

        if attempted and unavailable == attempted:
            raise ScanFailed(
                "We couldn't reach the package registry while scanning. "
                "Please try again in a few minutes."
            )


def _enrich_from_osv(pool: list[PooledOccurrence]) -> None:
    """Batch every `(package, version)` pair to OSV, then fetch each advisory once."""
    by_ecosystem: dict[str, list[PooledOccurrence]] = defaultdict(list)
    for occurrence in pool:
        if occurrence.spec.is_unassessable or occurrence.facts is None:
            continue
        if occurrence.facts.not_found or occurrence.facts.unavailable:
            continue
        if occurrence.assessed_version:
            by_ecosystem[occurrence.ecosystem].append(occurrence)

    for ecosystem, occurrences in by_ecosystem.items():
        client = osv.OsvClient()
        targets = [
            (occurrence.spec.name, occurrence.assessed_version or "")
            for occurrence in occurrences
        ]
        try:
            found = client.query_batch(ecosystem, targets)
        except (http.UpstreamError, ValueError) as exc:
            # Unlike a registry outage, this one is all-or-nothing by nature:
            # a missing batch answer is indistinguishable from "no advisories",
            # and reporting a repository clean because OSV was down is the
            # single worst thing this product could do.
            raise ScanFailed(
                "We couldn't reach the vulnerability database while scanning. "
                "Please try again in a few minutes."
            ) from exc

        for occurrence in occurrences:
            key = (occurrence.spec.name, occurrence.assessed_version or "")
            for osv_id in found.get(key, []):
                detail = client.detail(osv_id, occurrence.spec.name)
                if detail is not None:
                    occurrence.vulnerabilities.append(detail)


# ── persistence ────────────────────────────────────────────────────────────


def _package_for(ecosystem: str, name: str, registry_url: str | None) -> Package:
    package, created = Package.objects.get_or_create(
        ecosystem=ecosystem,
        package_name=name,
        defaults={"registry_url": registry_url},
    )
    if not created and registry_url and not package.registry_url:
        package.registry_url = registry_url
        package.save(update_fields=["registry_url"])
    return package


def _build_occurrence(
    pooled: PooledOccurrence, package: Package, manifest: ManifestFile
) -> DependencyOccurrence:
    spec = pooled.spec
    facts = pooled.facts

    occurrence = DependencyOccurrence(
        manifest=manifest,
        package=package,
        dependency_group=spec.group,
        declared_specifier=spec.declared_specifier,
    )

    if spec.is_unassessable:
        occurrence.is_unassessable = True
        occurrence.unassessable_reason = spec.unassessable_reason
        return occurrence

    if facts is None or facts.unavailable:
        occurrence.is_unassessable = True
        occurrence.unassessable_reason = REASON_REGISTRY_UNAVAILABLE
        return occurrence

    if facts.not_found:
        occurrence.is_unassessable = True
        occurrence.unassessable_reason = REASON_NOT_IN_REGISTRY
        occurrence.resolved_version = spec.resolved_version
        occurrence.resolution = spec.resolution
        return occurrence

    occurrence.resolved_version = pooled.assessed_version
    occurrence.resolution = spec.resolution or Resolution.RANGE_LATEST_APPROX.value
    occurrence.latest_version = facts.latest_version
    occurrence.latest_release_at = facts.latest_release_at
    occurrence.staleness_days = facts.staleness_days
    occurrence.versions_behind_major = facts.versions_behind_major
    occurrence.versions_behind_minor = facts.versions_behind_minor
    occurrence.versions_behind_patch = facts.versions_behind_patch
    occurrence.is_deprecated = facts.is_deprecated
    occurrence.deprecation_reason = facts.deprecation_reason

    occurrence.vulnerability_count = len(pooled.vulnerabilities)
    if pooled.vulnerabilities:
        occurrence.highest_severity = max(
            (vuln.severity or Severity.UNKNOWN.value for vuln in pooled.vulnerabilities),
            key=lambda severity: SEVERITY_RANK.get(severity, 0),
        )
        scores = [
            vuln.cvss_score
            for vuln in pooled.vulnerabilities
            if vuln.cvss_score is not None
        ]
        occurrence.cvss_max = max(scores) if scores else None

    return occurrence


def _persist(
    scan: ScanRun, plans: list[ManifestPlan], pool: list[PooledOccurrence]
) -> None:
    """Write the manifests, occurrences and advisories in one transaction.

    All-or-nothing on purpose: a half-written scan would show a dependency
    table missing exactly the rows whose write failed, which reads as a clean
    repository rather than as a broken scan.
    """
    packages: dict[tuple[str, str], Package] = {}
    occurrences: list[DependencyOccurrence] = []

    with transaction.atomic():
        manifests = {
            plan.path: ManifestFile.objects.create(
                scan=scan,
                ecosystem=plan.adapter.ecosystem,
                manifest_path=plan.path,
                lockfile_path=plan.lockfile_path,
                parser_name=plan.adapter.parser_name,
            )
            for plan in plans
        }

        for pooled in pool:
            key = (pooled.ecosystem, pooled.spec.name)
            if key not in packages:
                registry_url = pooled.facts.registry_url if pooled.facts else None
                packages[key] = _package_for(*key, registry_url)
            occurrences.append(
                _build_occurrence(pooled, packages[key], manifests[pooled.plan.path])
            )

        DependencyOccurrence.objects.bulk_create(occurrences)

        vulnerabilities: list[DependencyVulnerability] = []
        for pooled, occurrence in zip(pool, occurrences, strict=True):
            seen: set[str] = set()
            for vuln in pooled.vulnerabilities:
                # UNIQUE(dependency_id, osv_id): OSV can name the same advisory
                # twice for one version through overlapping affected ranges.
                if not vuln.osv_id or vuln.osv_id in seen:
                    continue
                seen.add(vuln.osv_id)
                vulnerabilities.append(
                    DependencyVulnerability(
                        dependency=occurrence,
                        osv_id=vuln.osv_id,
                        cve_id=vuln.cve_id,
                        severity=vuln.severity,
                        cvss_score=vuln.cvss_score,
                        published_at=vuln.published_at,
                        summary=vuln.summary,
                        affected_range=vuln.affected_range,
                        fixed_version=vuln.fixed_version,
                        source_url=vuln.source_url,
                    )
                )
        DependencyVulnerability.objects.bulk_create(vulnerabilities)


# ── entry point ────────────────────────────────────────────────────────────


def run_scan(scan: ScanRun) -> None:
    """Scan one repository, writing every signal it observed.

    Raises `ScanFailed` with user-facing text where the failure has a remedy;
    anything else propagates for the background runner to record generically.
    Status transitions and timestamps belong to the runner, not here — this
    function's whole job is the measurement.
    """
    token = scan.triggered_by.get_github_token()
    if not token:
        raise ScanFailed(
            "Your GitHub sign-in is no longer valid. Sign out and sign in "
            "again, then run the scan."
        )

    tree = _fetch_tree(scan, token)
    plans = plan_manifests(tree)
    if not plans:
        # The repository had a manifest at registration and does not now.
        raise ScanFailed(
            "We couldn't find a dependency manifest in this repository's "
            "default branch. It may have moved or been removed since you "
            "registered it."
        )

    read: list[ManifestPlan] = []
    pool: list[PooledOccurrence] = []
    for plan in plans:
        if plan.size > MAX_MANIFEST_BYTES:
            logger.warning("Skipping an oversized manifest during a scan.")
            continue

        manifest_bytes = _fetch_blob(scan, token, plan.sha, MAX_MANIFEST_BYTES)
        if manifest_bytes is None:
            continue

        lockfile_bytes = None
        if plan.lockfile_sha and plan.lockfile_size <= MAX_LOCKFILE_BYTES:
            lockfile_bytes = _fetch_blob(
                scan, token, plan.lockfile_sha, MAX_LOCKFILE_BYTES
            )
        if lockfile_bytes is None:
            # No lockfile, or one too large or unreadable. The column is
            # cleared because it is the reason this manifest's rows will say
            # `range_latest_approx`, and claiming a lockfile we never read
            # would make that provenance a lie.
            plan.lockfile_path = None

        try:
            specs = plan.adapter.parse(manifest_bytes, lockfile_bytes)
        except adapters.ManifestParseError:
            logger.warning("A manifest could not be parsed; skipping it.")
            continue

        # A manifest declaring nothing still gets a row: "we read this and it
        # declares no dependencies" is an answer, and leaving the file
        # unaccounted for is not.
        read.append(plan)
        pool.extend(
            PooledOccurrence(plan=plan, ecosystem=plan.adapter.ecosystem, spec=spec)
            for spec in specs
        )

    if not read:
        raise ScanFailed(
            "We found this repository's manifests but could not read any of "
            "them. Please try again shortly."
        )

    _enrich_from_registries(pool)
    _enrich_from_osv(pool)
    _persist(scan, read, pool)

    logger.info(
        "Scan %s recorded %d occurrences across %d manifests.",
        scan.pk,
        len(pool),
        len(read),
    )
