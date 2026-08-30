"""The adapter contract every ecosystem implements — §10 Phase 3.

Phase 6 is the soundness proof: a PyPI repository must flow through an
*unchanged* scanner and an unchanged scoring engine, with the phase's own diff
as the evidence. That claim is only worth making if the seam is real, so this
module is deliberately the only place that knows an ecosystem exists at all.
Everything downstream — `scanner.py`, the scoring engine, the API, the UI —
works in terms of `DepSpec` and never in terms of npm or PyPI.

An adapter's job stops at *reading*. It answers three questions:

  - which files in a repository tree belong to me (`manifest_patterns`),
  - what does this manifest declare (`parse`),
  - who do I ask about those packages (`registry_client`).

It never fetches the manifest itself (the scanner owns GitHub access and its
quota), never scores, and never executes anything it has read. §11's "manifest
parsing abuse" row is satisfied structurally: `parse` receives bytes and
returns dataclasses, so there is no code path in which repository content
could become code.

**Unassessable is a first-class answer.** A `file:`, `git+https:` or
`workspace:` specifier names something no registry can describe — there is no
version to compare and no advisory database to query. The product's stated
philosophy is to say so rather than quietly drop the row or, worse, count it
as clean. `DepSpec.unassessable()` is how an adapter says "I read this, I
understood it, and it cannot be assessed", with the reason travelling all the
way to the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from apps.scanning.models import DependencyGroup, Ecosystem, Resolution

#: Directory names whose contents are vendored copies of other people's
#: packages, not the repository's own declarations. §5.6 requires matching
#: manifests *anywhere* in the tree so that split-by-functionality repos are
#: not missed; taken literally that also matches a checked-in
#: `node_modules/**/package.json`, which would make any repository with
#: vendored dependencies look like an npm project on the strength of its
#: vendor directory alone (see `docs/decisions.md` §2.3).
VENDOR_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "bower_components",
        "vendor",
        "site-packages",
        ".venv",
        "venv",
    }
)


@dataclass(frozen=True)
class DepSpec:
    """One dependency as an adapter read it. No registry data, no scoring.

    `resolved_version` is what the signals will be computed *against*, and
    `resolution` says where it came from. The two travel together because a
    version without its provenance invites a false reading: "4.17.1" resolved
    from a lockfile is what the project installs, while "4.17.1" approximated
    from the registry's latest release is what it *would* install today.
    """

    name: str
    declared_specifier: str
    group: str = DependencyGroup.RUNTIME.value
    #: None when the adapter could not resolve a version at parse time; the
    #: scanner then falls back to the registry's latest release and records
    #: `range_latest_approx`.
    resolved_version: str | None = None
    resolution: str | None = None
    is_unassessable: bool = False
    unassessable_reason: str | None = None

    @classmethod
    def unassessable(
        cls,
        name: str,
        declared_specifier: str,
        reason: str,
        group: str = DependencyGroup.RUNTIME.value,
    ) -> DepSpec:
        """A dependency that was read successfully and cannot be assessed.

        Distinct from a parse failure, which loses the row entirely: this one
        is counted, displayed with its reason, and excluded from every score
        denominator (§5.2).
        """
        return cls(
            name=name,
            declared_specifier=declared_specifier,
            group=group,
            is_unassessable=True,
            unassessable_reason=reason,
        )

    @property
    def needs_registry_resolution(self) -> bool:
        return not self.is_unassessable and self.resolved_version is None


@dataclass(frozen=True)
class PackageFacts:
    """What a registry says about one package, at one moment.

    Every field is a raw observation. Nothing here is normalized, bucketed or
    scored — D6 requires that the stored signals be exactly what was seen, so
    that a weights revision can be applied retroactively without a rescan.
    """

    name: str
    latest_version: str | None = None
    latest_release_at: object | None = None  # datetime | None
    staleness_days: int | None = None
    versions_behind_major: int = 0
    versions_behind_minor: int = 0
    versions_behind_patch: int = 0
    is_deprecated: bool = False
    #: Verbatim registry text. Empty string and None mean different things: the
    #: former is a deprecation with no explanation, which is itself S3 data.
    deprecation_reason: str | None = None
    registry_url: str | None = None
    #: Set when the package name is not in the registry at all — a typo, a
    #: private package, or an unpublished one. The occurrence survives as
    #: unassessable rather than silently scoring as clean.
    not_found: bool = False


class ManifestParseError(Exception):
    """The manifest could not be understood. The scanner records and continues.

    One malformed `package.json` in a twelve-manifest monorepo must not cost
    the other eleven their scan.
    """


class DependencyAdapter(ABC):
    """One ecosystem's reader. Stateless; instantiated once per process."""

    #: Value from `models.Ecosystem`.
    ecosystem: str
    #: Written to `manifest_files.parser_name`, so a stored row says which
    #: code read it. Version it when parsing behaviour changes materially.
    parser_name: str

    @abstractmethod
    def manifest_patterns(self) -> frozenset[str]:
        """Basenames that identify a manifest this adapter owns."""

    def lockfile_names(self, manifest_path: str) -> tuple[str, ...]:
        """Sibling filenames that may resolve this manifest's ranges.

        Ordered by preference — the first one found in the tree wins. Returns
        empty for ecosystems with no lockfile concept.
        """
        return ()

    @abstractmethod
    def parse(
        self, manifest_bytes: bytes, lockfile_bytes: bytes | None = None
    ) -> list[DepSpec]:
        """Read one manifest (and its lockfile, when there is one).

        Raises `ManifestParseError` if the file is not what it claims to be.
        Never executes, evaluates or imports anything it reads.
        """

    @abstractmethod
    def registry_client(self):
        """The client that answers `PackageFacts` for this ecosystem."""


_ADAPTERS: dict[str, DependencyAdapter] = {}


def register(adapter: DependencyAdapter) -> DependencyAdapter:
    _ADAPTERS[adapter.ecosystem] = adapter
    return adapter


def get_adapter(ecosystem: str) -> DependencyAdapter:
    return _ADAPTERS[ecosystem]


def all_adapters() -> tuple[DependencyAdapter, ...]:
    return tuple(_ADAPTERS[key] for key in sorted(_ADAPTERS))


def supported_manifest_names() -> frozenset[str]:
    """Every manifest basename any registered adapter claims.

    §5.6's `ecosystem_unsupported` check is exactly "does the tree contain one
    of these", so pre-scan validation reads it from here rather than keeping a
    second list that could drift out of step with what the scanner can
    actually parse.
    """
    names: set[str] = set()
    for adapter in _ADAPTERS.values():
        names |= adapter.manifest_patterns()
    return frozenset(names)


def adapter_for_path(path: str) -> DependencyAdapter | None:
    """The adapter owning `path`, or None — including None for vendored paths."""
    segments = path.split("/")
    if VENDOR_DIRS.intersection(segments[:-1]):
        return None
    basename = segments[-1]
    for adapter in _ADAPTERS.values():
        if basename in adapter.manifest_patterns():
            return adapter
    return None


def supported_ecosystems() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


__all__ = [
    "VENDOR_DIRS",
    "DepSpec",
    "DependencyAdapter",
    "DependencyGroup",
    "Ecosystem",
    "ManifestParseError",
    "PackageFacts",
    "Resolution",
    "adapter_for_path",
    "all_adapters",
    "get_adapter",
    "register",
    "supported_ecosystems",
    "supported_manifest_names",
]
