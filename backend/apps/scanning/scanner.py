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

**Four seams are public, for Phase 11 and nothing else.** `tree_url`,
`blob_url` and `decode_blob` say how this project addresses and unwraps GitHub
content; `enrich_from_registries`, `enrich_from_osv` and `derive_signals` are
the measurement itself, from a parsed `DepSpec` through to the columns §5.1
stores. §10 Phase 11 makes identity with the product the point of the corpus
engine -- "it is what lets S1 claim the corpus measures the shipped formula
rather than a research reimplementation of it" -- and identity claimed by two
copies of the same logic is not identity. So `apps.research.corpus_scan` calls
these, and they are exported rather than reimplemented. Both enrichment
functions take an optional cache so a thousand-repository run can hold one
across repositories; passed nothing they behave exactly as they did when they
were private to `run_scan`.
"""

from __future__ import annotations

import base64
import binascii
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
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


def tree_url(owner: str, name: str, branch: str) -> str:
    """The recursive-tree URL for one branch.

    Public because Phase 11's corpus builder addresses the same endpoint for
    repositories nobody has registered, and a second string built somewhere
    else is a second place for the quoting to be wrong.
    """
    return (
        f"{GITHUB_API}/repos/{quote(owner)}/{quote(name)}"
        f"/git/trees/{quote(branch, safe='')}"
    )


def blob_url(owner: str, name: str, sha: str) -> str:
    """The blob URL for one object sha (see `_fetch_blob` for why not contents)."""
    return f"{GITHUB_API}/repos/{quote(owner)}/{quote(name)}/git/blobs/{quote(sha)}"


def decode_blob(document: dict, cap: int) -> bytes | None:
    """Unwrap GitHub's blob envelope, or None if it is unusable or too large.

    Split out from the fetch so Phase 11 can reuse the unwrapping while
    watching the response headers for its rate budget — the caller there needs
    the whole `UpstreamResponse`, which `_fetch_blob` deliberately does not
    return.
    """
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


def _fetch_tree(scan: ScanRun, token: str) -> list[dict]:
    repository = scan.repository
    branch = repository.default_branch or ""
    if not branch:
        raise ScanFailed("This repository has no default branch to scan.")

    url = tree_url(repository.owner, repository.name, branch)
    try:
        response = http.get_json(url, token=token, params={"recursive": "1"})
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
    try:
        response = http.get_json(
            blob_url(repository.owner, repository.name, sha), token=token
        )
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

    return decode_blob(response.data if isinstance(response.data, dict) else {}, cap)


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


def tree_manifest_paths(tree: list[dict]) -> list[str]:
    """Every manifest path in the tree, before `MAX_MANIFESTS` trims it.

    Kept separate from `plan_manifests` so the scan can report how many
    manifests it did not look at, rather than only how many it read.
    """
    return [
        entry["path"]
        for entry in tree
        if isinstance(entry, dict)
        and entry.get("type") == "blob"
        and isinstance(entry.get("path"), str)
        and adapters.adapter_for_path(entry["path"]) is not None
    ]


def adopt_workspace_lockfiles(
    plans: list[ManifestPlan], sources: dict[str, bytes]
) -> None:
    """Let workspace members inherit the lockfile of the root that declares them.

    A sibling-only rule is right for an unrelated nested project — `examples/`
    or a vendored sample has nothing to do with the root's lockfile, and
    borrowing it would invent resolutions. It is wrong for an npm *workspaces*
    monorepo, which by design has exactly one lockfile, at the root, describing
    every member's install. Under the sibling rule every workspace package
    falls to `range_latest_approx` and gets checked against the registry's
    newest release instead of what it actually installs — precisely the
    failure `npm.py` opens by naming, and invisible from the outside because
    the rows look perfectly well-formed.

    The distinction is not guessed at. A manifest inherits only when an
    ancestor manifest *declares* it: the ancestor's `workspaces` globs have to
    match the member's path relative to that ancestor. The nearest declaring
    ancestor wins, so nested workspace roots behave.
    """
    by_directory = {plan.directory: plan for plan in plans}

    for plan in plans:
        if plan.lockfile_sha:
            continue

        directory = plan.directory
        if not directory:
            continue

        ancestor_dir = directory
        while ancestor_dir:
            ancestor_dir = ancestor_dir.rpartition("/")[0]
            ancestor = by_directory.get(ancestor_dir)
            if ancestor is None or not ancestor.lockfile_sha:
                continue

            ancestor_bytes = sources.get(ancestor.path)
            if ancestor_bytes is None:
                continue

            relative = directory[len(ancestor_dir) :].lstrip("/")
            if adapters.matches_workspace_globs(
                ancestor.adapter.workspace_globs(ancestor_bytes), relative
            ):
                plan.lockfile_path = ancestor.lockfile_path
                plan.lockfile_sha = ancestor.lockfile_sha
                plan.lockfile_size = ancestor.lockfile_size
                break


# ── enrichment ─────────────────────────────────────────────────────────────


#: One registry answer, keyed by everything that can change it. The ecosystem
#: is part of the key because `requests` is a real package in both of them.
FactsKey = tuple[str, str, str | None]


def enrich_from_registries(
    pool: list[PooledOccurrence],
    memo: dict[FactsKey, adapters.PackageFacts] | None = None,
) -> None:
    """Ask each ecosystem's registry about every assessable occurrence.

    A single package the registry has never heard of becomes unassessable — a
    fact about that package. A registry that answered nothing at all fails the
    whole scan instead: recording "unassessable" for every row would write a
    permanent claim about the packages out of a temporary fact about the
    network.

    `memo` defaults to a fresh dict per call, which is the per-scan cache
    `registry_clients.py` argues for at length: a scan is one self-consistent
    observation of the registry, and a cache outliving it would raise a
    staleness question the product has no answer to. Phase 11's corpus run
    passes one in across every repository deliberately — D14 makes that run a
    *cross-section as of a single date*, so observing `lodash` once for the
    whole run is the more faithful measurement as well as the cheaper one
    (§8: the registries are free but not infinite, and `lodash` appears in
    hundreds of the thousand repositories).
    """
    by_ecosystem: dict[str, list[PooledOccurrence]] = defaultdict(list)
    for occurrence in pool:
        if not occurrence.spec.is_unassessable:
            by_ecosystem[occurrence.ecosystem].append(occurrence)

    if memo is None:
        memo = {}

    for ecosystem, occurrences in by_ecosystem.items():
        client = adapters.get_adapter(ecosystem).registry_client()
        attempted = 0
        unavailable = 0

        for occurrence in occurrences:
            key: FactsKey = (
                ecosystem,
                occurrence.spec.name,
                occurrence.spec.resolved_version,
            )
            if key not in memo:
                attempted += 1
                memo[key] = client.facts(key[1], key[2])
                if memo[key].unavailable:
                    unavailable += 1
            occurrence.facts = memo[key]

        if attempted and unavailable == attempted:
            raise ScanFailed(
                "We couldn't reach the package registry while scanning. "
                "Please try again in a few minutes."
            )


def enrich_from_osv(
    pool: list[PooledOccurrence], client: osv.OsvClient | None = None
) -> None:
    """Batch every `(package, version)` pair to OSV, then fetch each advisory once.

    `client` defaults to a fresh one, whose document cache then lives exactly
    as long as the scan. Phase 11 hands one in for the whole corpus run for
    the reason `enrich_from_registries` gives about its memo — and here the
    saving is larger, because one advisory is reached from every repository
    that pins the affected version.
    """
    by_ecosystem: dict[str, list[PooledOccurrence]] = defaultdict(list)
    for occurrence in pool:
        if occurrence.spec.is_unassessable or occurrence.facts is None:
            continue
        if occurrence.facts.not_found or occurrence.facts.unavailable:
            continue
        if occurrence.assessed_version:
            by_ecosystem[occurrence.ecosystem].append(occurrence)

    # One client for the whole call rather than one per ecosystem. OSV ids are
    # globally unique, so a mixed monorepo's two ecosystems can share the
    # document cache safely; previously they each built their own and an
    # advisory reachable from both was fetched twice.
    shared = client or osv.OsvClient()

    for ecosystem, occurrences in by_ecosystem.items():
        targets = [
            (occurrence.spec.name, occurrence.assessed_version or "")
            for occurrence in occurrences
        ]
        try:
            found = shared.query_batch(ecosystem, targets)
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
                detail = shared.detail(osv_id, occurrence.spec.name)
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


@dataclass(frozen=True)
class OccurrenceSignals:
    """Every column §5.1 records about one occurrence, before any row exists.

    The measurement, separated from where it is stored. A live scan writes
    these onto a `dependency_occurrences` row; Phase 11's corpus run writes
    the subset §5.1 keeps into `dependency_history` directly, with no
    operational row anywhere (D10). Two writers, one derivation — which is the
    whole of §10 Phase 11's "same adapters" claim, made structural.

    The four field names the formula reads — `is_deprecated`,
    `vulnerability_count`, `cvss_max`, `staleness_days` — are §5.1's, not
    coincidentally: `apps.scoring.signals.signals_for` is duck-typed over
    exactly those, so this record scores through the shipped engine without
    being persisted first.

    `cvss_max` is a `Decimal` here though OSV hands back a float, because the
    column is `NUMERIC(3,1)` and a corpus score computed from `6.1` must equal
    the product score computed from a row that went through Postgres and came
    back as `Decimal("6.1")`.
    """

    dependency_group: str
    declared_specifier: str | None
    is_unassessable: bool = False
    unassessable_reason: str | None = None
    resolved_version: str | None = None
    resolution: str | None = None
    latest_version: str | None = None
    latest_release_at: object | None = None  # datetime | None
    staleness_days: int | None = None
    versions_behind_major: int = 0
    versions_behind_minor: int = 0
    versions_behind_patch: int = 0
    is_deprecated: bool = False
    deprecation_reason: str | None = None
    vulnerability_count: int = 0
    highest_severity: str | None = None
    cvss_max: Decimal | None = None


#: The CVSS column's precision (§5.1: `NUMERIC(3,1)`).
CVSS_QUANTUM = Decimal("0.1")


def derive_signals(pooled: PooledOccurrence) -> OccurrenceSignals:
    """What one enriched occurrence measured — §5.1's columns, no database.

    The three unassessable exits are ordered by what they claim, worst-founded
    first: the adapter said the specifier names nothing a registry can
    describe; the registry could not be reached; the registry has never heard
    of the package. Only the last of them keeps a version, because only it
    read one.
    """
    spec = pooled.spec
    facts = pooled.facts

    base = {
        "dependency_group": spec.group,
        "declared_specifier": spec.declared_specifier,
    }

    if spec.is_unassessable:
        return OccurrenceSignals(
            **base, is_unassessable=True, unassessable_reason=spec.unassessable_reason
        )

    if facts is None or facts.unavailable:
        return OccurrenceSignals(
            **base,
            is_unassessable=True,
            unassessable_reason=REASON_REGISTRY_UNAVAILABLE,
        )

    if facts.not_found:
        return OccurrenceSignals(
            **base,
            is_unassessable=True,
            unassessable_reason=REASON_NOT_IN_REGISTRY,
            resolved_version=spec.resolved_version,
            resolution=spec.resolution,
        )

    highest_severity: str | None = None
    cvss_max: Decimal | None = None
    if pooled.vulnerabilities:
        highest_severity = max(
            (vuln.severity or Severity.UNKNOWN.value for vuln in pooled.vulnerabilities),
            key=lambda severity: SEVERITY_RANK.get(severity, 0),
        )
        scores = [
            vuln.cvss_score
            for vuln in pooled.vulnerabilities
            if vuln.cvss_score is not None
        ]
        if scores:
            # `str` first: `Decimal(6.1)` is 6.0999999999999996 and quantizing
            # that is a rounding decision made on binary noise.
            cvss_max = Decimal(str(max(scores))).quantize(CVSS_QUANTUM)

    return OccurrenceSignals(
        **base,
        resolved_version=pooled.assessed_version,
        resolution=spec.resolution or Resolution.RANGE_LATEST_APPROX.value,
        latest_version=facts.latest_version,
        latest_release_at=facts.latest_release_at,
        staleness_days=facts.staleness_days,
        versions_behind_major=facts.versions_behind_major,
        versions_behind_minor=facts.versions_behind_minor,
        versions_behind_patch=facts.versions_behind_patch,
        is_deprecated=facts.is_deprecated,
        deprecation_reason=facts.deprecation_reason,
        vulnerability_count=len(pooled.vulnerabilities),
        highest_severity=highest_severity,
        cvss_max=cvss_max,
    )


def _build_occurrence(
    pooled: PooledOccurrence, package: Package, manifest: ManifestFile
) -> DependencyOccurrence:
    signals = derive_signals(pooled)
    return DependencyOccurrence(
        manifest=manifest,
        package=package,
        **{
            field: getattr(signals, field)
            for field in OccurrenceSignals.__dataclass_fields__
        },
    )


def _persist(
    scan: ScanRun,
    plans: list[ManifestPlan],
    pool: list[PooledOccurrence],
    skipped: int = 0,
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

        # In the same transaction as the rows it qualifies: a count claiming
        # two manifests were missed, next to a table that silently has them,
        # would be worse than no count.
        if scan.skipped_manifest_count != skipped:
            scan.skipped_manifest_count = skipped
            scan.save(update_fields=["skipped_manifest_count"])


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

    # Pass one: read every manifest. Nothing is resolved yet, because whether a
    # manifest inherits an ancestor's lockfile depends on what that ancestor
    # *says* — and that cannot be known until its bytes are in hand.
    sources: dict[str, bytes] = {}
    skipped = 0
    for plan in plans:
        if plan.size > MAX_MANIFEST_BYTES:
            logger.warning("Skipping an oversized manifest during a scan.")
            skipped += 1
            continue

        manifest_bytes = _fetch_blob(scan, token, plan.sha, MAX_MANIFEST_BYTES)
        if manifest_bytes is None:
            skipped += 1
            continue
        sources[plan.path] = manifest_bytes

    skipped += max(0, len(tree_manifest_paths(tree)) - len(plans))

    adopt_workspace_lockfiles(plans, sources)

    # Pass two: fetch each lockfile once and parse. The cache matters here in a
    # way it did not before — a workspaces monorepo points every member at the
    # same root lockfile, and without it a ten-package repo would fetch a
    # multi-megabyte file ten times.
    lockfiles: dict[str, bytes | None] = {}
    read: list[ManifestPlan] = []
    pool: list[PooledOccurrence] = []
    for plan in plans:
        manifest_bytes = sources.get(plan.path)
        if manifest_bytes is None:
            continue

        lockfile_bytes = None
        if plan.lockfile_sha and plan.lockfile_size <= MAX_LOCKFILE_BYTES:
            if plan.lockfile_sha not in lockfiles:
                lockfiles[plan.lockfile_sha] = _fetch_blob(
                    scan, token, plan.lockfile_sha, MAX_LOCKFILE_BYTES
                )
            lockfile_bytes = lockfiles[plan.lockfile_sha]
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
            skipped += 1
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

    enrich_from_registries(pool)
    enrich_from_osv(pool)
    _persist(scan, read, pool, skipped)

    logger.info(
        "Scan %s recorded %d occurrences across %d manifests (%d skipped).",
        scan.pk,
        len(pool),
        len(read),
        skipped,
    )
