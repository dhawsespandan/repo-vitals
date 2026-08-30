"""The npm adapter — `package.json`, and the lockfile that overrules it.

**The central rule: a lockfile beats a range.** `"express": "^4.17.1"` states
what the project *allows*; `package-lock.json` states what it *installs*. Only
the second can be checked against an advisory database — a range is not a
thing OSV can answer questions about, and treating it as one would mean either
querying a version nobody runs or, worse, reporting a repository clean because
the newest version in its allowed range happens to be patched while the
version actually installed is not. So resolution runs lockfile → pinned →
`range_latest_approx`, and the provenance travels with the version (§5.1) so
the UI can say which of the three it is looking at.

**Non-registry specifiers are unassessable, not absent.** `file:../shared`,
`link:`, `workspace:*`, `git+https://…`, `github:owner/repo` and bare URLs all
name something the npm registry has never heard of: no release history, no
deprecation flag, no advisories. Each becomes a row with a reason rather than
a silent omission — the difference between "we checked 40 dependencies and
skipped 3" and "we checked 43", which is the difference between a tool worth
trusting and one that is not.

Nothing here executes. `package.json` and `package-lock.json` are JSON, read
with `json.loads` into plain data; no `npm` binary is invoked, no install is
performed, and no lifecycle script is ever seen, let alone run (§11).
"""

from __future__ import annotations

import json
import logging
import re

from apps.scanning.models import DependencyGroup, Ecosystem, Resolution

from . import semver
from .base import DependencyAdapter, DepSpec, ManifestParseError, register

logger = logging.getLogger(__name__)

#: `package.json`'s dependency blocks, mapped onto §5.1's groups. Order fixes
#: precedence when the same package appears in two blocks: npm installs the
#: runtime copy, so runtime wins, and a `devDependencies` duplicate does not
#: produce a second occurrence for the same manifest.
DEPENDENCY_BLOCKS: tuple[tuple[str, str], ...] = (
    ("dependencies", DependencyGroup.RUNTIME.value),
    ("devDependencies", DependencyGroup.DEVELOPMENT.value),
    ("optionalDependencies", DependencyGroup.OPTIONAL.value),
    ("peerDependencies", DependencyGroup.PEER.value),
)

#: Reasons, one per specifier family. They reach the UI verbatim, so they name
#: the *specifier form* rather than restating that something went wrong.
REASON_FILE = "file_specifier"
REASON_LINK = "link_specifier"
REASON_WORKSPACE = "workspace_specifier"
REASON_GIT = "git_specifier"
REASON_GITHUB = "github_specifier"
REASON_URL = "url_specifier"
REASON_ALIAS = "alias_specifier"
REASON_NOT_IN_REGISTRY = "not_in_registry"

_GIT_PREFIXES = ("git:", "git+", "ssh://", "git@")
_URL_PREFIXES = ("http://", "https://")

# `owner/repo`, `owner/repo#semver:^1.0.0`, `owner/repo#branch`. Deliberately
# anchored and narrow so it cannot swallow a scoped package name, which npm
# writes as `@scope/name` and which always carries the leading `@`.
_GITHUB_SHORTHAND_RE = re.compile(r"^[\w.-]+/[\w.-]+(?:#.+)?$")

# npm's own package-name rules, enough to reject a key that is not one.
_PACKAGE_NAME_RE = re.compile(r"^(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*$", re.IGNORECASE)


def classify_specifier(specifier: str) -> str | None:
    """The unassessable reason for a specifier, or None if the registry has it.

    Ordered most-specific first: `git+https://` is a git specifier, not a URL,
    and `github:owner/repo` is a GitHub specifier rather than the bare
    shorthand, even though both end up equally unassessable. The distinction is
    kept because the reason is shown to a person, and a wrong-but-adjacent
    label reads as carelessness.
    """
    value = (specifier or "").strip()
    if not value:
        return None

    lowered = value.lower()
    if lowered.startswith("file:"):
        return REASON_FILE
    if lowered.startswith("link:"):
        return REASON_LINK
    if lowered.startswith("workspace:"):
        return REASON_WORKSPACE
    if lowered.startswith(_GIT_PREFIXES):
        return REASON_GIT
    if lowered.startswith("github:"):
        return REASON_GITHUB
    if lowered.startswith(_URL_PREFIXES):
        return REASON_URL
    if lowered.startswith("npm:"):
        # `npm:other-package@^1` installs a different package under a local
        # name. It *is* a registry package, so this is a documented gap rather
        # than a true impossibility: resolving it means re-deriving npm's alias
        # grammar (which has to handle `npm:@scope/pkg@1.2.3`), and a wrong
        # answer here silently attributes one package's advisories to another.
        # Saying "can't assess" is the cheaper mistake. See decisions §3.3.
        return REASON_ALIAS
    if _GITHUB_SHORTHAND_RE.match(value) and not value.startswith("@"):
        return REASON_GITHUB
    return None


def _resolve_from_lockfile(lock: dict, name: str) -> str | None:
    """The version a v2/v3 lockfile installs for a top-level `name`.

    The `packages` map is keyed by install path. The hoisted copy at
    `node_modules/<name>` is the one a top-level dependency resolves to; a
    nested `.../node_modules/<name>` is only reached when a *transitive*
    dependency needed a different version, so it is a fallback, not the
    answer. `link: true` entries point at a workspace directory and carry no
    version of their own — those are already unassessable by specifier.

    Falls back to the v1 `dependencies` map, which real repositories still
    carry: npm 6 lockfiles are common in projects that have not been touched
    in years, which is exactly the population this product is about.
    """
    packages = lock.get("packages")
    if isinstance(packages, dict):
        entry = packages.get(f"node_modules/{name}")
        if isinstance(entry, dict) and not entry.get("link"):
            version = entry.get("version")
            if isinstance(version, str) and version:
                return version

        suffix = f"/node_modules/{name}"
        nested = [
            value.get("version")
            for key, value in packages.items()
            if key.endswith(suffix)
            and isinstance(value, dict)
            and not value.get("link")
            and isinstance(value.get("version"), str)
        ]
        if nested:
            # Deterministic: a repeat scan of an unchanged repository must
            # produce an identical row (§4.4's determinism suite).
            return sorted(nested)[0]

    legacy = lock.get("dependencies")
    if isinstance(legacy, dict):
        entry = legacy.get(name)
        if isinstance(entry, dict):
            version = entry.get("version")
            # v1 records git dependencies here too, as a URL rather than a
            # version. Those are unassessable by specifier already; guarding
            # keeps a URL out of the `resolved_version` column regardless.
            if isinstance(version, str) and semver.parse(version) is not None:
                return version

    return None


def _load_json(raw: bytes, what: str) -> dict:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestParseError(f"{what} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ManifestParseError(f"{what} is not a JSON object.")
    return document


class NpmAdapter(DependencyAdapter):
    ecosystem = Ecosystem.NPM.value
    parser_name = "npm/package.json@1"

    def manifest_patterns(self) -> frozenset[str]:
        return frozenset({"package.json"})

    def lockfile_names(self, manifest_path: str) -> tuple[str, ...]:
        # `npm-shrinkwrap.json` outranks `package-lock.json` where both exist:
        # npm itself prefers it, and it is the one published with the package.
        # yarn and pnpm lockfiles are absent by design — neither is JSON, and
        # a half-understood parse is worse than an honest range approximation
        # (decisions §3.4).
        return ("npm-shrinkwrap.json", "package-lock.json")

    def parse(
        self, manifest_bytes: bytes, lockfile_bytes: bytes | None = None
    ) -> list[DepSpec]:
        manifest = _load_json(manifest_bytes, "package.json")

        lock: dict = {}
        if lockfile_bytes:
            try:
                lock = _load_json(lockfile_bytes, "lockfile")
            except ManifestParseError:
                # A broken lockfile costs resolution precision, not the whole
                # manifest: every row simply falls back to the range path.
                logger.warning("Lockfile could not be parsed; resolving from ranges.")

        specs: list[DepSpec] = []
        seen: set[str] = set()

        for block, group in DEPENDENCY_BLOCKS:
            declared = manifest.get(block)
            if not isinstance(declared, dict):
                continue

            for name, specifier in declared.items():
                if not isinstance(name, str) or not _PACKAGE_NAME_RE.match(name):
                    continue
                if name in seen:
                    # Same package in two blocks — npm installs one copy, so
                    # this is one occurrence, in the first (highest-priority)
                    # group it appeared in.
                    continue
                seen.add(name)

                specifier_text = specifier if isinstance(specifier, str) else ""

                reason = classify_specifier(specifier_text)
                if reason is not None:
                    specs.append(
                        DepSpec.unassessable(name, specifier_text, reason, group)
                    )
                    continue

                locked = _resolve_from_lockfile(lock, name) if lock else None
                if locked:
                    specs.append(
                        DepSpec(
                            name=name,
                            declared_specifier=specifier_text,
                            group=group,
                            resolved_version=locked,
                            resolution=Resolution.LOCKFILE.value,
                        )
                    )
                    continue

                pinned = semver.exact_version(specifier_text)
                if pinned:
                    specs.append(
                        DepSpec(
                            name=name,
                            declared_specifier=specifier_text,
                            group=group,
                            resolved_version=pinned,
                            resolution=Resolution.PINNED.value,
                        )
                    )
                    continue

                # A range with no lockfile. The scanner asks the registry for
                # the latest release and tags the row `range_latest_approx`.
                specs.append(
                    DepSpec(name=name, declared_specifier=specifier_text, group=group)
                )

        return specs

    def registry_client(self):
        from .registry_clients import NpmRegistryClient

        return NpmRegistryClient()


npm_adapter = register(NpmAdapter())
