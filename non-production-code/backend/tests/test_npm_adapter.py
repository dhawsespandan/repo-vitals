"""The npm adapter — parsing, resolution precedence, and unassessable rows.

These are the tests that would catch a silent miscount. Two of them exist
specifically because passing them the *other* way still looks like a working
product: a scanner that resolves ranges against the registry's latest release
reports a repository clean when the version it actually installs is
vulnerable, and a scanner that drops `file:` dependencies shows a shorter,
tidier table with no indication that anything is missing.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from apps.scanning.adapters import npm, semver
from apps.scanning.adapters.base import ManifestParseError
from apps.scanning.models import DependencyGroup, Resolution

MANIFESTS = pathlib.Path(__file__).parent / "fixtures" / "manifests"


def fixture(name: str) -> bytes:
    return (MANIFESTS / name).read_bytes()


def by_name(specs) -> dict:
    return {spec.name: spec for spec in specs}


class TestResolutionPrecedence:
    """§10 Phase 3: "a manifest range is what's *allowed*, not what's installed"."""

    def test_the_lockfile_beats_the_range_even_when_they_diverge(self):
        specs = by_name(
            npm.npm_adapter.parse(
                fixture("root_package.json"), fixture("root_package_lock.json")
            )
        )

        # The manifest allows anything from 4.16.0 up; the registry's newest
        # 4.x is 4.19.2. The lockfile says 4.17.1 and the lockfile is right.
        assert specs["express"].resolved_version == "4.17.1"
        assert specs["express"].resolution == Resolution.LOCKFILE.value
        assert specs["express"].declared_specifier == "^4.16.0"

    def test_the_divergence_is_what_makes_the_finding_visible(self):
        """The fixture is built so a range-only reading reports nothing.

        `^4.17.0` permits 4.17.21, which is neither deprecated nor vulnerable.
        The lockfile pins 4.17.19, which is both. If this assertion ever flips,
        the product has started scanning a version nobody runs.
        """
        specs = by_name(
            npm.npm_adapter.parse(
                fixture("root_package.json"), fixture("root_package_lock.json")
            )
        )

        assert specs["lodash"].resolved_version == "4.17.19"
        assert specs["lodash"].resolved_version != "4.17.21"

    def test_an_exact_specifier_is_pinned_when_there_is_no_lockfile(self):
        specs = by_name(npm.npm_adapter.parse(fixture("root_package.json")))

        assert specs["left-pad"].resolved_version == "1.3.0"
        assert specs["left-pad"].resolution == Resolution.PINNED.value

    def test_a_range_with_no_lockfile_is_left_for_the_registry(self):
        specs = by_name(npm.npm_adapter.parse(fixture("api_package.json")))

        assert specs["react"].resolved_version is None
        assert specs["react"].resolution is None
        assert specs["react"].needs_registry_resolution

    def test_a_nested_lockfile_entry_resolves_a_top_level_dependency(self):
        """Only as a fallback: the hoisted copy wins where both exist."""
        manifest = json.dumps({"dependencies": {"react": "^18.0.0"}}).encode()

        specs = by_name(
            npm.npm_adapter.parse(manifest, fixture("root_package_lock.json"))
        )

        assert specs["react"].resolved_version == "18.2.0"
        assert specs["react"].resolution == Resolution.LOCKFILE.value

    def test_a_v1_lockfile_still_resolves(self):
        """npm 6 lockfiles are common in exactly the repositories this is about."""
        specs = by_name(
            npm.npm_adapter.parse(
                fixture("root_package.json"), fixture("legacy_package_lock.json")
            )
        )

        assert specs["express"].resolved_version == "4.16.0"
        assert specs["express"].resolution == Resolution.LOCKFILE.value

    def test_an_unreadable_lockfile_degrades_to_ranges_rather_than_failing(self):
        specs = by_name(
            npm.npm_adapter.parse(fixture("root_package.json"), b"{ this is not json")
        )

        assert specs["express"].resolved_version is None
        assert specs["left-pad"].resolution == Resolution.PINNED.value


class TestUnassessableSpecifiers:
    """Every non-registry specifier family becomes a row with a reason."""

    @pytest.mark.parametrize(
        ("name", "reason"),
        [
            ("local-path", npm.REASON_FILE),
            ("linked", npm.REASON_LINK),
            ("in-workspace", npm.REASON_WORKSPACE),
            ("from-git", npm.REASON_GIT),
            ("from-github-prefix", npm.REASON_GITHUB),
            ("from-github-shorthand", npm.REASON_GITHUB),
            ("from-url", npm.REASON_URL),
            ("aliased", npm.REASON_ALIAS),
        ],
    )
    def test_each_specifier_family_is_named(self, name, reason):
        specs = by_name(npm.npm_adapter.parse(fixture("unassessable_package.json")))

        assert specs[name].is_unassessable
        assert specs[name].unassessable_reason == reason

    def test_they_are_present_rather_than_dropped(self):
        """The whole point: 40 checked and 8 skipped, never 48 checked."""
        specs = npm.npm_adapter.parse(fixture("unassessable_package.json"))

        assert len(specs) == 9
        assert sum(1 for spec in specs if spec.is_unassessable) == 8
        assert sum(1 for spec in specs if not spec.is_unassessable) == 1

    def test_the_declared_specifier_survives_verbatim(self):
        specs = by_name(npm.npm_adapter.parse(fixture("unassessable_package.json")))

        assert specs["from-git"].declared_specifier == (
            "git+ssh://git@github.com/acme/thing.git"
        )

    def test_a_scoped_package_is_not_mistaken_for_a_github_shorthand(self):
        """`@scope/name` and `owner/repo` are the same shape but for the `@`."""
        manifest = json.dumps({"dependencies": {"@scope/pkg": "^1.0.0"}}).encode()

        specs = by_name(npm.npm_adapter.parse(manifest))

        assert not specs["@scope/pkg"].is_unassessable


class TestGroupsAndDuplicates:
    def test_dev_dependencies_carry_their_group(self):
        specs = by_name(npm.npm_adapter.parse(fixture("root_package.json")))

        assert specs["typescript"].group == DependencyGroup.DEVELOPMENT.value
        assert specs["express"].group == DependencyGroup.RUNTIME.value

    def test_one_package_in_two_blocks_is_one_occurrence(self):
        """npm installs one copy; two rows would double-count one installation."""
        specs = npm.npm_adapter.parse(fixture("root_package.json"))

        assert [spec.name for spec in specs].count("express") == 1

    def test_peer_and_optional_blocks_map_to_their_groups(self):
        manifest = json.dumps(
            {
                "peerDependencies": {"react": ">=17"},
                "optionalDependencies": {"fsevents": "^2"},
            }
        ).encode()

        specs = by_name(npm.npm_adapter.parse(manifest))

        assert specs["react"].group == DependencyGroup.PEER.value
        assert specs["fsevents"].group == DependencyGroup.OPTIONAL.value


class TestParseFailures:
    def test_a_non_json_manifest_raises_rather_than_returning_nothing(self):
        """The scanner catches this per manifest; returning [] would look clean."""
        with pytest.raises(ManifestParseError):
            npm.npm_adapter.parse(b"not json at all")

    def test_a_json_array_is_not_a_manifest(self):
        with pytest.raises(ManifestParseError):
            npm.npm_adapter.parse(b'["express"]')

    def test_a_manifest_with_no_dependency_blocks_yields_nothing(self):
        assert npm.npm_adapter.parse(b'{"name": "empty"}') == []


class TestSemver:
    @pytest.mark.parametrize(
        ("specifier", "expected"),
        [
            ("1.2.3", True),
            ("=1.2.3", True),
            ("v1.2.3", True),
            ("^1.2.3", False),
            ("~1.2.3", False),
            (">=1.2.3", False),
            ("1.2.x", False),
            ("*", False),
            ("latest", False),
        ],
    )
    def test_only_an_exact_version_counts_as_pinned(self, specifier, expected):
        assert semver.is_exact(specifier) is expected

    def test_versions_behind_counts_releases_not_arithmetic(self):
        """A package that skipped 2.4 never shipped a 2.4 to be behind."""
        released = ["2.0.0", "2.1.0", "2.5.0", "2.5.1", "3.0.0", "4.0.0"]

        assert semver.versions_behind("2.0.0", released) == (2, 2, 0)

    def test_prereleases_never_count_as_being_behind(self):
        assert semver.versions_behind("1.0.0", ["1.0.0", "2.0.0-beta.1"]) == (0, 0, 0)

    def test_an_unparseable_version_is_zero_rather_than_a_guess(self):
        assert semver.versions_behind("not-a-version", ["1.0.0", "2.0.0"]) == (0, 0, 0)

    def test_latest_of_prefers_a_stable_release_over_a_newer_prerelease(self):
        assert semver.latest_of(["1.9.3", "2.0.0-rc.1", "1.0.0"]) == "1.9.3"

    def test_latest_of_falls_back_to_prereleases_when_that_is_all_there_is(self):
        assert semver.latest_of(["2.0.0-rc.1", "2.0.0-rc.2"]) == "2.0.0-rc.2"


class TestWorkspaceGlobs:
    """`workspaces` is npm's, so reading it lives behind the adapter seam.

    Phase 6's soundness proof says a PyPI repository flows through an unchanged
    scanner; that only holds if ecosystem-specific concepts like this one stay
    on this side of the interface.
    """

    def test_an_array_of_globs_is_read(self):
        manifest = json.dumps({"workspaces": ["packages/*", "tools/*"]}).encode()

        assert npm.npm_adapter.workspace_globs(manifest) == ("packages/*", "tools/*")

    def test_the_object_form_is_read_too(self):
        """The shape yarn popularised; both appear in the wild."""
        manifest = json.dumps({"workspaces": {"packages": ["libs/*"]}}).encode()

        assert npm.npm_adapter.workspace_globs(manifest) == ("libs/*",)

    def test_a_manifest_without_workspaces_declares_none(self):
        assert npm.npm_adapter.workspace_globs(b'{"name": "plain"}') == ()

    def test_unreadable_bytes_declare_none_rather_than_raising(self):
        assert npm.npm_adapter.workspace_globs(b"{ not json") == ()


class TestGlobMatching:
    @pytest.mark.parametrize(
        ("globs", "directory", "expected"),
        [
            (("packages/*",), "packages/ui", True),
            # `*` stops at a separator, which is why fnmatch is not used: it
            # would claim the root lockfile resolves a deeply nested package.
            (("packages/*",), "packages/ui/nested", False),
            (("packages/**",), "packages/ui/nested", True),
            (("services/api",), "services/api", True),
            (("services/api",), "services/worker", False),
            (("packages/*",), "examples/demo", False),
            (("packages/*", "!packages/private"), "packages/private", False),
            (("packages/*", "!packages/private"), "packages/public", True),
            (("packages/*",), "", False),
            ((), "packages/ui", False),
        ],
    )
    def test_membership(self, globs, directory, expected):
        from apps.scanning.adapters.base import matches_workspace_globs

        assert matches_workspace_globs(globs, directory) is expected
