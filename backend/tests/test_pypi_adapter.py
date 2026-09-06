"""The PyPI adapter -- five formats, one contract, and nothing executed.

The npm adapter's suite was written around the two mistakes that still look
like a working product: resolving a range against the registry's newest
release, and dropping the specifiers no registry can describe. Both apply here
unchanged, so both are tested here again against Python's own grammars.

Two failures are specific to this ecosystem and get their own attention:

* **`setup.py` is a program.** A parser that imports or executes it to read
  `install_requires` turns every scan into arbitrary code execution on behalf
  of whoever wrote the repository. `test_a_setup_py_is_never_executed` is the
  assertion that would fail if that ever changed, and it is deliberately not
  subtle: the fixture writes a file, and the test asserts the file does not
  exist.
* **PyPI names are case- and separator-insensitive.** `Django` in one manifest
  and `django` in another are one project to PyPI, to OSV and to the
  `packages` table's unique constraint. A parser that kept the spellings apart
  would ask the registry twice, attribute one project's advisories to two rows,
  and count one dependency as two in §5.3's roll-up.
"""

from __future__ import annotations

import pathlib

import pytest

from apps.scanning import adapters
from apps.scanning.adapters import pep440, pypi
from apps.scanning.adapters.base import ManifestParseError
from apps.scanning.models import DependencyGroup, Ecosystem, Resolution

MANIFESTS = pathlib.Path(__file__).parent / "fixtures" / "manifests"


def fixture(name: str) -> bytes:
    return (MANIFESTS / name).read_bytes()


def by_name(specs) -> dict:
    return {spec.name: spec for spec in specs}


def parse(path: str, manifest: str, lockfile: str | None = None):
    """Parse a fixture through the adapter the scanner would have chosen."""
    adapter = adapters.adapter_for_path(path)
    assert adapter is not None, path
    return adapter.parse(fixture(manifest), fixture(lockfile) if lockfile else None)


class TestManifestOwnership:
    """Which files this adapter claims -- the question §5.6 asks first."""

    @pytest.mark.parametrize(
        "path",
        [
            "requirements.txt",
            "requirements-dev.txt",
            "requirements_test.txt",
            "dev-requirements.txt",
            "requirements/prod.txt",
            "backend/requirements/base.txt",
            "pyproject.toml",
            "Pipfile",
            "setup.py",
            "service/api/setup.py",
        ],
    )
    def test_a_python_manifest_is_claimed_wherever_it_sits(self, path):
        adapter = adapters.adapter_for_path(path)

        assert adapter is not None
        assert adapter.ecosystem == Ecosystem.PYPI.value

    @pytest.mark.parametrize(
        "path",
        [
            # pip-tools' *source*; the `.txt` it compiles to sits beside it and
            # is the one that states resolved versions.
            "requirements.in",
            "docs/notes.txt",
            "CHANGELOG.txt",
            # Lockfiles are reached through their manifest, never on their own:
            # claiming them here would parse every dependency twice.
            "poetry.lock",
            "Pipfile.lock",
        ],
    )
    def test_a_file_that_is_not_a_manifest_is_not_claimed(self, path):
        assert adapters.adapter_for_path(path) is None

    def test_a_vendored_python_package_is_not_a_manifest(self):
        """A checked-in virtualenv is other people's packages, not ours (§2.3)."""
        assert adapters.adapter_for_path(".venv/lib/site-packages/six/setup.py") is None

    def test_npm_still_owns_its_own_manifest(self):
        """The seam holds in both directions -- Phase 6 took nothing from npm."""
        adapter = adapters.adapter_for_path("package.json")

        assert adapter is not None
        assert adapter.ecosystem == Ecosystem.NPM.value
        assert adapter.parser_name == "npm/package.json@1"

    @pytest.mark.parametrize(
        ("path", "parser_name"),
        [
            ("requirements.txt", "pypi/requirements@1"),
            ("service/pyproject.toml", "pypi/pyproject@1"),
            ("Pipfile", "pypi/pipfile@1"),
            ("legacy/setup.py", "pypi/setup_py@1"),
        ],
    )
    def test_the_stored_row_says_which_of_the_five_parsers_read_it(
        self, path, parser_name
    ):
        """`manifest_files.parser_name` exists to answer exactly this."""
        assert adapters.adapter_for_path(path).parser_name == parser_name

    def test_the_lockfile_a_manifest_inherits_is_its_own_kind(self):
        assert adapters.adapter_for_path("pyproject.toml").lockfile_names(
            "pyproject.toml"
        ) == ("poetry.lock",)
        assert adapters.adapter_for_path("Pipfile").lockfile_names("Pipfile") == (
            "Pipfile.lock",
        )
        # A requirements file has no sibling that resolves it. Inventing one
        # would attach a lockfile's versions to a manifest that never named it.
        assert (
            adapters.adapter_for_path("requirements.txt").lockfile_names(
                "requirements.txt"
            )
            == ()
        )


class TestRequirementsFile:
    def test_a_pin_resolves_and_a_range_does_not(self):
        specs = by_name(parse("requirements.txt", "pypi_requirements.txt"))

        assert specs["django"].resolved_version == "2.2"
        assert specs["django"].resolution == Resolution.PINNED.value
        # `>=2.0` is what the project *allows*. The scanner will assess it
        # against the registry's latest and tag it `range_latest_approx`.
        assert specs["flask"].resolved_version is None
        assert specs["flask"].resolution is None

    def test_extras_markers_comments_and_hashes_do_not_hide_a_dependency(self):
        """One line carrying every decoration pip allows still reads as one row."""
        specs = by_name(parse("requirements.txt", "pypi_requirements.txt"))

        # `requests[security]==2.31.0 ; python_version >= "3.8"`
        assert specs["requests"].resolved_version == "2.31.0"
        # `urllib3==1.25` continued onto a `--hash=` line.
        assert specs["urllib3"].resolved_version == "1.25"
        # `oauth2client  # no constraint at all`
        assert specs["oauth2client"].declared_specifier == ""
        assert specs["oauth2client"].resolved_version is None

    def test_every_unassessable_reference_is_a_row_with_a_reason(self):
        """Not an omission. A shorter table with three rows silently gone is
        indistinguishable, from the outside, from a repository with fewer
        dependencies."""
        specs = by_name(parse("requirements.txt", "pypi_requirements.txt"))

        assert specs["widget"].is_unassessable
        assert specs["widget"].unassessable_reason == pypi.REASON_VCS
        assert specs["widget"].declared_specifier.startswith("git+https://")

        assert specs["local-thing"].is_unassessable
        assert specs["local-thing"].unassessable_reason == pypi.REASON_LOCAL_PATH

    def test_pip_options_and_self_installs_declare_nothing(self):
        """`-r`, `--index-url` and `-e .` are not dependencies.

        `-r constraints.txt` names another file, which the scanner reaches on
        its own if it is in the tree; `-e .` installs the repository into
        itself. Recording either as a package would invent a row out of pip
        mechanics.
        """
        names = {spec.name for spec in parse("requirements.txt", "pypi_requirements.txt")}

        assert names == {
            "django",
            "flask",
            "requests",
            "urllib3",
            "oauth2client",
            "widget",
            "local-thing",
        }

    def test_the_filename_decides_the_dependency_group(self):
        runtime = by_name(parse("requirements.txt", "pypi_requirements.txt"))
        development = by_name(parse("requirements-dev.txt", "pypi_requirements_dev.txt"))

        assert runtime["django"].group == DependencyGroup.RUNTIME.value
        assert development["flask"].group == DependencyGroup.DEVELOPMENT.value

    def test_a_whole_word_is_what_marks_a_file_as_development(self):
        """`requirements-devops.txt` is not development dependencies."""
        adapter = adapters.adapter_for_path("requirements-devops.txt")

        specs = adapter.parse(b"Flask==3.0.0\n")

        assert specs[0].group == DependencyGroup.RUNTIME.value


class TestPyprojectToml:
    def test_both_schemas_in_one_file_are_read(self):
        """PEP 621 `[project]` and poetry's own tables coexist in real files.

        Reading only the first would drop every poetry-declared dependency
        silently -- the shape of failure this suite exists to catch.
        """
        specs = by_name(parse("service/pyproject.toml", "pypi_pyproject.toml"))

        assert specs["django"].declared_specifier == ">=4.2"  # PEP 621
        assert specs["urllib3"].declared_specifier == "^1.26"  # poetry

    def test_the_python_constraint_is_not_a_dependency(self):
        """`python = "^3.11"` constrains the interpreter, which PyPI has no
        entry for. A row for it would be permanently `not_in_registry`."""
        names = {
            spec.name for spec in parse("service/pyproject.toml", "pypi_pyproject.toml")
        }

        assert "python" not in names

    def test_optional_and_group_dependencies_carry_their_group(self):
        specs = by_name(parse("service/pyproject.toml", "pypi_pyproject.toml"))

        assert specs["flask"].group == DependencyGroup.OPTIONAL.value

    def test_one_package_declared_twice_is_one_occurrence(self):
        """`Flask` is in `[project.optional-dependencies]` and in poetry's dev
        group. One install, one row -- npm's rule for a package appearing in
        two blocks, reached through a different file format."""
        specs = parse("service/pyproject.toml", "pypi_pyproject.toml")

        assert [spec.name for spec in specs].count("flask") == 1

    def test_a_git_or_path_dependency_is_unassessable(self):
        specs = by_name(parse("service/pyproject.toml", "pypi_pyproject.toml"))

        assert specs["widget"].unassessable_reason == pypi.REASON_VCS
        assert specs["shared"].unassessable_reason == pypi.REASON_LOCAL_PATH

    def test_the_lockfile_beats_the_range(self):
        """The rule the whole scanner turns on, in PyPI's spelling.

        `Django>=4.2` permits the latest release; `poetry.lock` installs
        4.2.12, which PyPI has yanked. A scanner resolving the range against
        the registry would report this repository clean, and nothing on screen
        would look wrong.
        """
        specs = by_name(
            parse("service/pyproject.toml", "pypi_pyproject.toml", "pypi_poetry.lock")
        )

        assert specs["django"].resolved_version == "4.2.12"
        assert specs["django"].resolution == Resolution.LOCKFILE.value
        assert specs["django"].declared_specifier == ">=4.2"

    def test_the_lockfile_matches_on_the_normalized_name(self):
        """`poetry.lock` writes `Flask`; the manifest writes `Flask` too, and
        both become `flask`. A case-sensitive match would leave this row
        approximated against the newest release instead."""
        specs = by_name(
            parse("service/pyproject.toml", "pypi_pyproject.toml", "pypi_poetry.lock")
        )

        assert specs["flask"].resolved_version == "3.0.0"
        assert specs["flask"].resolution == Resolution.LOCKFILE.value

    def test_a_lockfile_never_resolves_an_unassessable_row(self):
        """A `git+` reference resolves to a commit, not to a release.

        Letting a lockfile version stand in for one would attribute a published
        package's advisories to source we cannot identify.
        """
        specs = by_name(
            parse("service/pyproject.toml", "pypi_pyproject.toml", "pypi_poetry.lock")
        )

        assert specs["widget"].is_unassessable
        assert specs["widget"].resolved_version is None

    def test_a_broken_lockfile_costs_precision_not_the_manifest(self):
        adapter = adapters.adapter_for_path("pyproject.toml")

        specs = by_name(adapter.parse(fixture("pypi_pyproject.toml"), b"not toml {["))

        assert specs["django"].resolved_version is None
        assert len(specs) == 7

    def test_a_manifest_that_is_not_toml_raises(self):
        adapter = adapters.adapter_for_path("pyproject.toml")

        with pytest.raises(ManifestParseError):
            adapter.parse(b"[project\nname =")


class TestPipfile:
    def test_packages_and_dev_packages_carry_their_groups(self):
        specs = by_name(parse("Pipfile", "pypi_pipfile.toml"))

        assert specs["django"].group == DependencyGroup.RUNTIME.value
        assert specs["flask"].group == DependencyGroup.DEVELOPMENT.value

    def test_a_star_constraint_is_recorded_as_written(self):
        """`flask = "*"` pins nothing, and the row says so rather than showing
        an empty cell that reads as "we did not look"."""
        specs = by_name(parse("Pipfile", "pypi_pipfile.toml"))

        assert specs["flask"].declared_specifier == "*"
        assert specs["flask"].resolved_version is None

    def test_the_lock_resolves_both_sections(self):
        specs = by_name(parse("Pipfile", "pypi_pipfile.toml", "pypi_pipfile_lock.json"))

        assert specs["django"].resolved_version == "2.2.28"
        assert specs["django"].resolution == Resolution.LOCKFILE.value
        # `develop` resolves the `[dev-packages]` entry.
        assert specs["flask"].resolved_version == "3.0.0"

    def test_a_git_entry_in_the_lock_resolves_nothing(self):
        """pipenv records a `ref` for VCS entries, not a version. The row stays
        unassessable rather than acquiring a version it does not have."""
        specs = by_name(parse("Pipfile", "pypi_pipfile.toml", "pypi_pipfile_lock.json"))

        assert specs["widget"].is_unassessable
        assert specs["widget"].resolved_version is None


class TestSetupPy:
    def test_a_setup_py_is_never_executed(self, tmp_path, monkeypatch):
        """The assertion this whole module is arranged around.

        `setup.py` runs with the privileges of whoever installs the package,
        and a repository under scan is somebody else's input. The fixture below
        writes a file on import *and* on call; parsing it must produce neither.
        """
        monkeypatch.chdir(tmp_path)
        source = (
            "import pathlib\n"
            "from setuptools import setup\n"
            "pathlib.Path('executed-on-import').write_text('x')\n"
            "def side_effect():\n"
            "    pathlib.Path('executed-on-call').write_text('x')\n"
            "    return ['requests']\n"
            "setup(name='hostile', install_requires=side_effect())\n"
        )

        adapters.adapter_for_path("setup.py").parse(source.encode())

        assert not (tmp_path / "executed-on-import").exists()
        assert not (tmp_path / "executed-on-call").exists()

    def test_a_module_level_list_is_resolved(self):
        """`install_requires=REQUIREMENTS` is the commonest non-literal shape a
        real `setup.py` takes, and it is entirely static."""
        specs = by_name(parse("legacy/setup.py", "pypi_setup_py.txt"))

        assert specs["django"].resolved_version == "2.2"
        assert specs["django"].resolution == Resolution.PINNED.value
        assert specs["oauth2client"].declared_specifier == ""

    def test_each_setup_keyword_maps_onto_its_group(self):
        specs = by_name(parse("legacy/setup.py", "pypi_setup_py.txt"))

        assert specs["django"].group == DependencyGroup.RUNTIME.value
        assert specs["flask"].group == DependencyGroup.DEVELOPMENT.value

    def test_a_dynamic_argument_becomes_a_row_naming_what_was_not_read(self):
        """§10 Phase 6: a documented gap, not a miscount.

        `extras_require=read_extra()` cannot be answered without running the
        function. The row says so, quotes the expression, and is excluded from
        every score denominator (§5.2) -- which is a different claim from the
        extras not existing.
        """
        specs = by_name(parse("legacy/setup.py", "pypi_setup_py.txt"))
        dynamic = specs["setup.py:extras_require"]

        assert dynamic.is_unassessable
        assert dynamic.unassessable_reason == pypi.REASON_DYNAMIC_SETUP
        assert dynamic.declared_specifier == "read_extra()"

    def test_the_marker_name_can_never_collide_with_a_real_package(self):
        """The row needs a package name and the manifest supplies none.

        `dependency_occurrences.package_id` is NOT NULL, so a `dynamic_setup_py`
        row has to carry *some* name. It carries one no real dependency can
        have: PEP 503 project names admit only letters, digits, `-`, `_` and
        `.`, so a colon makes this marker unreachable through the parser that
        produces every other name -- it can never merge with a genuine
        `packages` row.
        """
        name = pypi.DYNAMIC_SETUP_PACKAGE.format(keyword="install_requires")

        assert ":" in name
        assert pypi.parse_requirement(name).name != name

    def test_a_setup_call_inside_main_is_still_found(self):
        """The idiom half of PyPI's long tail uses. A top-level-only search
        would read those files as declaring nothing at all."""
        source = (
            "from setuptools import setup\n"
            "if __name__ == '__main__':\n"
            "    setup(name='x', install_requires=['Flask>=3.0'])\n"
        )

        specs = adapters.adapter_for_path("setup.py").parse(source.encode())

        assert [spec.name for spec in specs] == ["flask"]

    def test_a_setup_py_that_declares_nothing_is_an_answer(self):
        """The modern shim: `setup()` with the metadata in `pyproject.toml`."""
        source = "from setuptools import setup\nsetup()\n"

        assert adapters.adapter_for_path("setup.py").parse(source.encode()) == []

    def test_unparseable_python_raises_rather_than_reporting_no_dependencies(self):
        """`ManifestParseError` makes the scanner count the manifest as skipped.
        Returning `[]` would claim the file declares nothing, which is a
        different and untrue statement."""
        with pytest.raises(ManifestParseError):
            adapters.adapter_for_path("setup.py").parse(b"def broken(:\n")


class TestNameNormalization:
    def test_one_project_spelled_three_ways_is_one_package(self):
        """PEP 503. `packages` is UNIQUE(ecosystem, package_name), so three
        spellings would otherwise be three registry lookups, three sets of
        advisories, and three independent terms in §5.3's roll-up."""
        adapter = adapters.adapter_for_path("requirements.txt")

        specs = adapter.parse(b"Zope.Interface==5.4.0\nzope_interface\nZOPE-INTERFACE\n")

        assert [spec.name for spec in specs] == ["zope-interface"]

    def test_the_declared_specifier_keeps_the_repositorys_own_spelling(self):
        """The name is canonicalised because three systems have to agree on it.
        The specifier is not, because it is what the reader will see in their
        own file."""
        adapter = adapters.adapter_for_path("requirements.txt")

        specs = adapter.parse(b'Django == 2.2 ; python_version < "3.9"\n')

        assert specs[0].name == "django"
        assert specs[0].declared_specifier == "== 2.2"


class TestPep440:
    """Ordering, distance and pinning -- `semver.py`'s three jobs, PyPI's grammar."""

    def test_releases_order_the_way_pep_440_says(self):
        ordered = [
            "1.0.dev1",
            "1.0a1",
            "1.0b2",
            "1.0rc1",
            "1.0",
            "1.0.post1",
            "1.0.1",
            "2.0",
        ]

        shuffled = sorted(ordered, key=lambda raw: pep440.parse(raw).sort_key())

        assert shuffled == ordered

    def test_trailing_zeros_are_not_a_different_release(self):
        assert pep440.parse("1.2").sort_key() == pep440.parse("1.2.0").sort_key()

    def test_an_epoch_outranks_everything_without_one(self):
        assert pep440.parse("1!0.1").sort_key() > pep440.parse("99.0").sort_key()

    @pytest.mark.parametrize(
        ("specifier", "expected"),
        [
            ("==2.2.0", "2.2.0"),
            ("== 2.2", "2.2"),
            ("===1.0", "1.0"),
            (">=1.0", None),
            ("~=1.4", None),
            # A range wearing an equals sign.
            ("==1.2.*", None),
            (">=1.0,<2.0", None),
            ("", None),
        ],
    )
    def test_only_a_single_equality_clause_pins(self, specifier, expected):
        assert pep440.exact_version(specifier) == expected

    def test_versions_behind_counts_releases_not_arithmetic(self):
        """`semver.versions_behind`'s definition, reached through PEP 440.

        Against a latest of 5.0, `2.2` is three majors behind by *published
        releases* (3, 4, 5), and two patches behind within 2.2 -- a package
        that never shipped a 2.2.5 left nobody behind one.
        """
        released = ["2.2", "2.2.1", "2.2.28", "3.2.25", "4.2.11", "5.0"]

        assert pep440.versions_behind("2.2", released) == (3, 0, 2)

    def test_a_prerelease_is_not_something_to_be_behind(self):
        assert pep440.latest_of(["1.9", "2.0rc1"]) == "1.9"
        # Unless it is all there is.
        assert pep440.latest_of(["2.0b1", "2.0rc1"]) == "2.0rc1"

    def test_an_unreadable_version_is_a_missing_measurement(self):
        """Not an error to abort a scan over -- PyPI carries versions that
        predate the standard."""
        assert pep440.parse("not-a-version") is None
        assert pep440.versions_behind("not-a-version", ["1.0"]) == (0, 0, 0)
