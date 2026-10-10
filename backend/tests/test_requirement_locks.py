"""The dependency freeze (§10 Phase 14): the locks say what the sources declare.

`requirements*.in` are edited by hand and carry each dependency's reason;
`requirements*.txt` are compiled from them with `uv pip compile --universal`
and are what Render, CI and the research machine install. Nothing but this
test stops the two drifting apart — an edit to a `.in` range that nobody
recompiled, or a hand-edited pin — so it checks the relationship directly:

* every requirement a source declares is pinned in its lock, and the pin
  satisfies the declared range;
* every lock pins the same version of a package as every other lock (they
  are compiled against the dev lock for exactly this);
* each lock names the command that regenerates it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

BACKEND = Path(__file__).resolve().parent.parent
LOCKS = (
    "requirements",
    "requirements-research",
    "requirements-notebooks",
    "requirements-dev",
)

_PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^\s;]+)(?:\s*;\s*(?P<marker>[^#]+?))?\s*(?:#.*)?$"
)


def declared(name: str) -> list[Requirement]:
    """Every requirement in a source and the sources it includes."""
    found = []
    for line in (BACKEND / f"{name}.in").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            found.extend(declared(line[3:].strip().removesuffix(".in")))
            continue
        found.append(Requirement(line))
    return found


def pinned(name: str) -> dict[str, list[tuple[Version, Marker | None]]]:
    pins: dict[str, list[tuple[Version, Marker | None]]] = {}
    for line in (BACKEND / f"{name}.txt").read_text(encoding="utf-8").splitlines():
        match = _PIN.match(line.strip())
        if match is None:
            continue
        marker = Marker(match["marker"]) if match["marker"] else None
        pins.setdefault(canonicalize_name(match["name"]), []).append(
            (Version(match["version"]), marker)
        )
    return pins


@pytest.mark.parametrize("name", LOCKS)
def test_every_declared_requirement_is_pinned_inside_its_range(name):
    pins = pinned(name)
    assert pins, f"{name}.txt pins nothing"
    for requirement in declared(name):
        key = canonicalize_name(requirement.name)
        assert key in pins, f"{requirement.name} is declared in {name}.in but not locked"
        for version, _ in pins[key]:
            assert requirement.specifier.contains(version, prereleases=True), (
                f"{name}.txt pins {requirement.name}=={version}, outside "
                f"{requirement.specifier} — recompile the locks (requirements.in's header)"
            )


def test_the_locks_agree_with_each_other():
    """Same versions everywhere. Markers may differ — a package needed on one
    platform by the runtime set can be needed more widely by the dev set — but
    a version the dev lock does not pin is a version CI never tested."""
    reference = {
        package: {str(version) for version, _ in versions}
        for package, versions in pinned("requirements-dev").items()
    }
    for name in LOCKS:
        for package, versions in pinned(name).items():
            assert package in reference, (
                f"{package} is in {name}.txt but not the dev lock"
            )
            assert {str(version) for version, _ in versions} <= reference[package], (
                package
            )


@pytest.mark.parametrize("name", LOCKS)
def test_each_lock_names_its_command(name):
    text = (BACKEND / f"{name}.txt").read_text(encoding="utf-8")
    assert f"uv pip compile {name}.in" in text.splitlines()[1]
    assert "--universal" in text.splitlines()[1]
