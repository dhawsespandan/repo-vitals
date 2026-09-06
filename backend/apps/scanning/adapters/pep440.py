"""Just enough PEP 440 to order PyPI releases and measure distance.

The sibling of `semver.py`, and deliberately a sibling rather than a
generalisation of it. The two grammars agree on almost nothing: PEP 440 has an
epoch (`1!2.0`), an unbounded release tuple (`1.2.3.4`), post-releases
(`2.9.0.post0`), dev releases, and a local segment; SemVer has exactly three
components and a dotted prerelease list with its own comparison rules. A single
function serving both would have to decide, for every input, which grammar it
was reading -- and would answer wrongly for the versions that look like both.
`semver.py` says as much where it names this module.

Same three jobs as its sibling, no more: parse a version, order versions, count
how many releases separate two of them. Range *satisfaction* is absent here for
the same reason it is absent there -- resolution comes from a lockfile or a pin,
never from re-deriving what a package manager would have installed.

One thing here has no SemVer counterpart: `normalize_name`. PEP 503 says
`Zope.Interface`, `zope-interface` and `zope_interface` are one project, and
every consumer of this adapter needs them to be one row -- the `packages` table
(UNIQUE(ecosystem, package_name)), the in-run registry cache, and OSV, which
answers only to the normalized spelling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# PEP 440's own appendix grammar, minus the leading/trailing whitespace
# tolerance being folded into the strip below.
_VERSION_RE = re.compile(
    r"""^
    v?
    (?:(?P<epoch>[0-9]+)!)?
    (?P<release>[0-9]+(?:\.[0-9]+)*)
    (?:[-_.]?(?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)[-_.]?(?P<pre_n>[0-9]+)?)?
    (?:
        -(?P<post_n1>[0-9]+)
        |
        [-_.]?(?P<post_l>post|rev|r)[-_.]?(?P<post_n2>[0-9]+)?
    )?
    (?P<dev>[-_.]?dev(?P<dev_n>[0-9]+)?)?
    (?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?
    $""",
    re.VERBOSE | re.IGNORECASE,
)

#: PEP 440 spells one thing several ways. Normalizing them means `1.0a1`,
#: `1.0.alpha1` and `1.0-ALPHA-1` sort as the one release they are.
_PRE_LETTERS = {
    "alpha": "a",
    "a": "a",
    "beta": "b",
    "b": "b",
    "c": "rc",
    "pre": "rc",
    "preview": "rc",
    "rc": "rc",
}

_NAME_SEPARATORS = re.compile(r"[-_.]+")


@dataclass(frozen=True, order=False)
class Version:
    """One PEP 440 version, parsed into its comparable parts.

    `local` is kept because it is part of the string a registry published, and
    dropped from `sort_key` because PEP 440 orders local versions only against
    each other -- exactly as SemVer ignores build metadata (`semver.Version`
    does not even retain it).
    """

    epoch: int
    release: tuple[int, ...]
    pre: tuple[str, int] | None = None
    post: int | None = None
    dev: int | None = None
    local: str | None = None

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None or self.dev is not None

    def sort_key(self) -> tuple:
        """Ordering key, per PEP 440's comparison rules.

        Three of the four segments need a sentinel for "absent", and which way
        each absence sorts is the whole subtlety:

          * a final release outranks its own prereleases (`1.0` > `1.0rc1`),
            so an absent `pre` sorts *high* --
          * except for a version that is only a dev release (`1.0.dev1`), which
            precedes every prerelease of the same number, so its absent `pre`
            sorts *low*;
          * an absent `post` sorts low (`2.0` < `2.0.post1`);
          * an absent `dev` sorts high (`1.0.dev1` < `1.0`).

        Each sentinel is a same-shaped tuple whose first element decides, so no
        comparison ever reaches a `str` against an `int`.
        """
        # Trailing zeros are not significant: `1.2` and `1.2.0` are one version.
        release = tuple(self.release)
        while len(release) > 1 and release[-1] == 0:
            release = release[:-1]

        if self.pre is not None:
            pre_key: tuple = (0, self.pre[0], self.pre[1])
        elif self.post is None and self.dev is not None:
            pre_key = (-1, "", 0)
        else:
            pre_key = (1, "", 0)

        post_key = (0, self.post) if self.post is not None else (-1, 0)
        dev_key = (0, self.dev) if self.dev is not None else (1, 0)

        return (self.epoch, release, pre_key, post_key, dev_key)


def parse(raw: str | None) -> Version | None:
    """Parse a PEP 440 version, or None if it is not one.

    None rather than an exception, for the same reason `semver.parse` returns
    None: PyPI carries versions that predate the standard, and an unreadable
    version is a missing measurement rather than a scan to abort.
    """
    if not raw:
        return None
    match = _VERSION_RE.match(raw.strip())
    if match is None:
        return None

    pre: tuple[str, int] | None = None
    if match.group("pre_l"):
        pre = (
            _PRE_LETTERS[match.group("pre_l").lower()],
            int(match.group("pre_n") or 0),
        )

    post: int | None = None
    if match.group("post_n1") is not None:
        # The `-1` shorthand form, which means `.post1`.
        post = int(match.group("post_n1"))
    elif match.group("post_l"):
        post = int(match.group("post_n2") or 0)

    # `dev` rather than `dev_n`: a bare `1.0.dev` is a dev release with an
    # implicit 0, and the number group alone cannot tell that from no dev
    # segment at all.
    dev = int(match.group("dev_n") or 0) if match.group("dev") is not None else None

    return Version(
        epoch=int(match.group("epoch") or 0),
        release=tuple(int(part) for part in match.group("release").split(".")),
        pre=pre,
        post=post,
        dev=dev,
        local=match.group("local"),
    )


def normalize_name(name: str) -> str:
    """PEP 503's canonical spelling of a project name.

    `Zope.Interface` and `zope_interface` are the same project, and PyPI, OSV
    and this application's own `packages` table all have to agree on which
    spelling that is. Normalizing at parse time rather than at each call site
    is what stops one manifest's `Django` and another's `django` becoming two
    packages with two independent registry lookups and two sets of advisories.
    """
    return _NAME_SEPARATORS.sub("-", (name or "").strip()).lower()


def is_exact(specifier: str) -> bool:
    """True when a specifier names exactly one version."""
    return exact_version(specifier) is not None


def exact_version(specifier: str) -> str | None:
    """The single version a specifier pins, as the registry spells it.

    `==1.2.3` and `===1.2.3` pin. `>=1.2`, `~=1.2`, `==1.2.*` and a
    comma-separated clause list do not -- each describes what is *allowed*,
    which is a different claim from what is installed.

    The returned string is the specifier's own text, not a normalized form: it
    becomes the version this scan asks PyPI and OSV about, and both answer to
    the spelling that was published.
    """
    candidate = (specifier or "").strip()
    if not candidate or "," in candidate:
        return None

    if candidate.startswith("==="):
        candidate = candidate[3:].strip()
    elif candidate.startswith("=="):
        candidate = candidate[2:].strip()
    else:
        return None

    if candidate.endswith(".*") or "*" in candidate:
        # `==1.2.*` is a range wearing an equals sign.
        return None
    return candidate if parse(candidate) is not None else None


def latest_of(versions: list[str]) -> str | None:
    """The highest stable release; falls back to prereleases only if that is all."""
    parsed = [(raw, parse(raw)) for raw in versions]
    usable = [(raw, version) for raw, version in parsed if version is not None]
    if not usable:
        return None
    stable = [(raw, version) for raw, version in usable if not version.is_prerelease]
    pool = stable or usable
    return max(pool, key=lambda pair: pair[1].sort_key())[0]


def versions_behind(resolved: str | None, released: list[str]) -> tuple[int, int, int]:
    """How many published releases sit ahead of `resolved`, by level.

    The same definition as `semver.versions_behind` -- distinct release numbers
    above the resolved one, sliced by level -- reached through a different
    grammar. PEP 440's release tuple has no fixed length, so `major`, `minor`
    and `patch` are its first three components with the missing ones read as
    zero: `2.9` is `(2, 9, 0)`, which is what a reader comparing it to `2.9.1`
    means by it.

    Prereleases are excluded throughout, and post-releases are counted as the
    release they follow -- `2.9.0.post0` is not a fourth release number, so it
    contributes nothing a reader would call "one patch behind".
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

    def triple(version: Version) -> tuple[int, int, int]:
        padded = (*version.release, 0, 0, 0)
        return (padded[0], padded[1], padded[2])

    here = triple(current)
    others = [triple(version) for version in stable]

    majors = {other[0] for other in others if other[0] > here[0]}
    minors = {other[1] for other in others if other[0] == here[0] and other[1] > here[1]}
    patches = {
        other[2]
        for other in others
        if other[0] == here[0] and other[1] == here[1] and other[2] > here[2]
    }

    return (len(majors), len(minors), len(patches))
