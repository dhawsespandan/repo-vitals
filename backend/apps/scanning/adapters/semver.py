"""Just enough SemVer to order npm releases and measure distance.

Not a dependency, because the two things needed here are small and the
alternatives are not: a full SemVer library brings range *satisfaction*
(`^1.2 ∩ >=1.4 <2`), which this project deliberately does not do — resolution
comes from the lockfile or not at all (§10 Phase 3), never from re-deriving
what a package manager would have installed. Guessing at range resolution is
precisely the "silently miscounting" failure the product exists to avoid.

So: parse a version, order versions, and count how many releases separate two
of them. Phase 6 adds the PEP 440 equivalent for PyPI alongside this, rather
than trying to make one function serve both grammars.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# https://semver.org's own suggested grammar, minus the build metadata's
# influence on ordering (SemVer §10: build metadata is ignored when comparing).
_SEMVER_RE = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True, order=False)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def sort_key(self) -> tuple:
        """Ordering key. A prerelease sorts *below* its own release (SemVer §11).

        Identifiers compare numerically when numeric and lexically otherwise,
        with numeric ranking lower; a longer identifier list wins a tie. The
        `(0, int)` / `(1, str)` pairs encode that without a custom comparator.
        """
        if not self.prerelease:
            # Every release outranks every prerelease of the same triple.
            return (self.major, self.minor, self.patch, 1, ())
        parts: list[tuple[int, object]] = []
        for identifier in self.prerelease:
            if identifier.isdigit():
                parts.append((0, int(identifier)))
            else:
                parts.append((1, identifier))
        return (self.major, self.minor, self.patch, 0, tuple(parts))


def parse(raw: str | None) -> Version | None:
    """Parse a SemVer string, or None if it is not one.

    Returning None rather than raising is deliberate: registries do carry
    versions that predate SemVer (`1.0`, `2011.06.28`), and an unparseable
    version is a missing measurement, not an error to abort a scan over.
    """
    if not raw:
        return None
    match = _SEMVER_RE.match(raw.strip())
    if match is None:
        return None
    prerelease = match.group("prerelease")
    return Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=tuple(prerelease.split(".")) if prerelease else (),
    )


def is_exact(specifier: str) -> bool:
    """True when a declared specifier names exactly one version.

    `1.2.3` and `=1.2.3` pin. `^1.2.3`, `~1.2.3`, `>=1.2.3`, `*`, `latest` and
    `1.2.x` do not — they describe what is *allowed*, which is a different
    claim from what is installed.
    """
    candidate = (specifier or "").strip()
    if candidate.startswith("="):
        candidate = candidate[1:].strip()
    return parse(candidate) is not None


def exact_version(specifier: str) -> str | None:
    """The pinned version a specifier names, normalized of `=` and `v`."""
    candidate = (specifier or "").strip()
    if candidate.startswith("="):
        candidate = candidate[1:].strip()
    if candidate.startswith("v"):
        candidate = candidate[1:]
    return candidate if parse(candidate) is not None else None


def latest_of(versions: list[str]) -> str | None:
    """The highest stable release; falls back to prereleases only if that is all.

    Used when a registry omits `dist-tags.latest`, which real package documents
    occasionally do.
    """
    parsed = [(raw, parse(raw)) for raw in versions]
    usable = [(raw, ver) for raw, ver in parsed if ver is not None]
    if not usable:
        return None
    stable = [(raw, ver) for raw, ver in usable if not ver.is_prerelease]
    pool = stable or usable
    return max(pool, key=lambda pair: pair[1].sort_key())[0]


def versions_behind(
    resolved: str | None, released: list[str]
) -> tuple[int, int, int]:
    """How many published releases sit ahead of `resolved`, by level.

    Counting *releases*, not arithmetic on the version numbers themselves. The
    difference matters: `1.0.0` against a latest of `5.0.0` is "four majors
    behind" either way, but `2.0.0` against `2.11.0` is eleven minor releases
    behind by subtraction and only as many as were actually published by this
    count — and a package that skipped `2.4` never shipped a `2.4` for anyone
    to be behind. §5.1 stores this as a research covariate and a UI display,
    never as a formula term (D3), so precision here costs nothing and a
    misleading number would be carried into the research.

    Levels are independent slices of the same release list:
      * major — distinct major numbers released above `resolved`'s
      * minor — distinct (major, minor) pairs released above it *within*
        `resolved`'s major
      * patch — releases above it within `resolved`'s (major, minor)

    Prereleases are excluded throughout: being "behind" a `3.0.0-beta.1` is
    not a meaningful claim about a project that tracks stable releases.
    """
    current = parse(resolved)
    if current is None:
        return (0, 0, 0)

    stable = [
        version
        for version in (parse(raw) for raw in released)
        if version is not None and not version.is_prerelease
    ]
    if not stable:
        return (0, 0, 0)

    majors = {v.major for v in stable if v.major > current.major}

    minors = {
        v.minor
        for v in stable
        if v.major == current.major and v.minor > current.minor
    }

    patches = {
        v.patch
        for v in stable
        if v.major == current.major
        and v.minor == current.minor
        and v.patch > current.patch
    }

    return (len(majors), len(minors), len(patches))
