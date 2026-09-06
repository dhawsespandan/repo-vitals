"""The PyPI adapter -- five manifest formats, one contract, nothing executed.

The npm adapter had one file to read. Python has five, because Python never
agreed on one: `requirements.txt` is a pip invocation transcript,
`pyproject.toml` is two competing schemas in one file (PEP 621 and poetry's),
`Pipfile` is pipenv's, and `setup.py` is a *program*. Each is read here, and
the same three answers come out -- name, declared specifier, resolved version
with its provenance -- so that `scanner.py` and the scoring engine cannot tell
which of the five it is looking at. That indistinguishability is the phase's
whole claim (`docs/adapter_soundness.md`).

**`setup.py` is read, never run.** It is the one manifest in this project that
is executable code, and running it is how a scanner becomes a remote code
execution service: `setup.py` executes with the privileges of whoever installs,
and a repository under scan is by definition somebody else's input. So it is
parsed with `ast` and read for *literals* only. Where a literal is not what is
there -- `install_requires=parse_requirements("reqs.txt")` -- the answer is
`dynamic_setup_py`, an unassessable row naming the expression we declined to
evaluate. §11's "manifest parsing abuse" row is satisfied by construction: the
only thing this module does with Python source is walk a syntax tree.

**Resolution precedence is lockfile > pinned > range**, exactly npm's, for
exactly npm's reason: `django>=3.2` is what the project *allows*, and only what
it installs can be asked about in an advisory database. `poetry.lock` and
`Pipfile.lock` are the two Python lockfiles that state an installed version
unambiguously, and both win over the manifest that names them.

**Names are normalized (PEP 503) and specifiers are not.** `Django`,
`django` and `DJANGO` are one project to PyPI, to OSV and therefore to the
`packages` table; the declared specifier stays exactly as the repository wrote
it, because it is what the reader will see in their own file.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import tomllib

from apps.scanning.models import DependencyGroup, Ecosystem, Resolution

from . import pep440
from .base import DependencyAdapter, DepSpec, ManifestParseError, register

logger = logging.getLogger(__name__)

# ── manifest kinds ─────────────────────────────────────────────────────────
# The adapter is bound to one of these per path (`for_path`), because the five
# formats cannot be told apart from their bytes -- `django==2.2` parses as a
# requirement line *and* as a Python comparison expression, so `setup.py` and
# `requirements.txt` are genuinely ambiguous by content.

KIND_REQUIREMENTS = "requirements"
KIND_PYPROJECT = "pyproject"
KIND_PIPFILE = "pipfile"
KIND_SETUP_PY = "setup_py"

#: The basenames that are always a manifest. The requirements *family* is not
#: fully enumerable here -- `requirements-dev.txt` and `requirements/prod.txt`
#: are conventions rather than standards -- so `PypiAdapter.owns` carries that
#: rule and this set carries the names that never vary.
FIXED_MANIFESTS: frozenset[str] = frozenset(
    {"requirements.txt", "pyproject.toml", "Pipfile", "setup.py"}
)

# `requirements.txt`, `requirements-dev.txt`, `requirements_test.txt`,
# `dev-requirements.txt`. Anchored, and `.txt` is mandatory: a bare
# `requirements` directory entry or a `requirements.in` (pip-tools' *source*,
# whose output is the `.txt` beside it) would otherwise be read twice.
_REQUIREMENTS_BASENAME_RE = re.compile(
    r"^(?:requirements[-_.][\w.-]*|[\w.-]*[-_.]requirements|requirements)\.txt$",
    re.IGNORECASE,
)

#: Filename stems that mark a requirements file as development dependencies.
#: A convention, not a standard, so the match is on whole `-`/`_` separated
#: tokens: `requirements-dev.txt` is development and `requirements-devops.txt`
#: is not. The group is display only -- §5.2 scores every group identically --
#: so the cost of the rule being wrong is a mislabelled row, never a mis-score.
_DEV_TOKENS = frozenset({"dev", "development", "test", "tests", "testing"})

# ── unassessable reasons ───────────────────────────────────────────────────
# One per specifier family, named for the *form* rather than for the failure,
# because they reach the UI verbatim (the npm adapter's reasons work the same
# way).

REASON_VCS = "vcs_specifier"
REASON_URL = "url_specifier"
REASON_LOCAL_PATH = "local_path_specifier"
#: §10 Phase 6: "dynamic constructs -> unassessable `dynamic_setup_py`
#: (documented gap, not a miscount)".
REASON_DYNAMIC_SETUP = "dynamic_setup_py"

_VCS_SCHEMES = ("git+", "hg+", "svn+", "bzr+", "git:", "git@")
_URL_SCHEMES = ("http://", "https://")

#: The synthetic package name a `dynamic_setup_py` row carries.
#:
#: A row needs a package (`dependency_occurrences.package_id` is NOT NULL), and
#: a dynamic `install_requires` names none -- that is the whole point of the
#: reason. The marker is deliberately not a legal PyPI project name (PEP 503
#: names cannot contain `:`), so it can never collide with a real package, and
#: it reads as what it is beside the manifest path on the same row.
DYNAMIC_SETUP_PACKAGE = "setup.py:{keyword}"

#: PEP 508's name/extras/specifier shape. Markers and URL references are split
#: off before this runs, so `rest` is a version specifier or nothing.
_REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*"
    r"(?:\[(?P<extras>[^\]]*)\])?\s*"
    r"(?P<rest>.*)$"
)

#: A comment runs to end of line. Anchored to a line start or whitespace so a
#: `#egg=` fragment inside a URL survives to be recognised as a VCS specifier.
_COMMENT_RE = re.compile(r"(^|\s)#.*$")

_EGG_FRAGMENT_RE = re.compile(r"[#&]egg=(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)")

#: `-e <target>`, in the four spellings pip accepts.
_EDITABLE_RE = re.compile(r"^(?:-e|--editable)\s*=?\s*", re.IGNORECASE)

#: pip options that introduce no dependency of their own. `-r`/`-c` name
#: another file, which the scanner reaches on its own if it is in the tree --
#: following the reference here would parse it twice.
_PIP_OPTION_PREFIXES = (
    "-r",
    "--requirement",
    "-c",
    "--constraint",
    "-i",
    "--index-url",
    "--extra-index-url",
    "--no-index",
    "-f",
    "--find-links",
    "--no-binary",
    "--only-binary",
    "--prefer-binary",
    "--require-hashes",
    "--pre",
    "--trusted-host",
    "--use-feature",
    "--no-deps",
)


def classify_reference(value: str) -> str | None:
    """The unassessable reason for a dependency reference, or None.

    Ordered most-specific first, as the npm adapter's equivalent is:
    `git+https://` is a VCS reference rather than a URL, even though both end
    up equally unassessable, because the label is shown to a person.
    """
    candidate = (value or "").strip()
    if not candidate:
        return None

    lowered = candidate.lower()
    if lowered.startswith(_VCS_SCHEMES):
        return REASON_VCS
    if lowered.startswith(_URL_SCHEMES):
        return REASON_URL
    if lowered.startswith(("file:", "./", "../", ".\\", "/")) or candidate in {".", ".."}:
        return REASON_LOCAL_PATH
    return None


def _group_for_requirements_file(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    tokens = {token.lower() for token in re.split(r"[-_.]+", stem) if token}
    if tokens & _DEV_TOKENS:
        return DependencyGroup.DEVELOPMENT.value
    return DependencyGroup.RUNTIME.value


def _kind_for_path(path: str) -> str:
    basename = path.rsplit("/", 1)[-1]
    if basename == "pyproject.toml":
        return KIND_PYPROJECT
    if basename == "Pipfile":
        return KIND_PIPFILE
    if basename == "setup.py":
        return KIND_SETUP_PY
    return KIND_REQUIREMENTS


def _load_toml(raw: bytes, what: str) -> dict:
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ManifestParseError(f"{what} is not valid TOML: {exc}") from exc


def _load_json(raw: bytes, what: str) -> dict:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestParseError(f"{what} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ManifestParseError(f"{what} is not a JSON object.")
    return document


# ── lockfiles ──────────────────────────────────────────────────────────────


def resolve_poetry_lock(raw: bytes | None) -> dict[str, str]:
    """`{normalized name: version}` from a `poetry.lock`.

    A broken lockfile costs resolution precision, not the manifest: every row
    simply falls back to the range path, exactly as `npm.py` does.
    """
    if not raw:
        return {}
    try:
        document = _load_toml(raw, "poetry.lock")
    except ManifestParseError:
        logger.warning("poetry.lock could not be parsed; resolving from ranges.")
        return {}

    resolved: dict[str, str] = {}
    for entry in document.get("package") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        version = entry.get("version")
        if isinstance(name, str) and isinstance(version, str) and version:
            resolved[pep440.normalize_name(name)] = version
    return resolved


def resolve_pipfile_lock(raw: bytes | None) -> dict[str, str]:
    """`{normalized name: version}` from a `Pipfile.lock`.

    Both sections are read into one map: `develop` entries resolve the
    `[dev-packages]` the `Pipfile` declares, and the group each package belongs
    to is already the manifest's answer rather than the lockfile's.
    """
    if not raw:
        return {}
    try:
        document = _load_json(raw, "Pipfile.lock")
    except ManifestParseError:
        logger.warning("Pipfile.lock could not be parsed; resolving from ranges.")
        return {}

    resolved: dict[str, str] = {}
    for section in ("default", "develop"):
        entries = document.get(section)
        if not isinstance(entries, dict):
            continue
        for name, entry in entries.items():
            if not isinstance(name, str) or not isinstance(entry, dict):
                continue
            # pipenv writes the pin as a specifier, `"version": "==2.2.0"`.
            pinned = pep440.exact_version(str(entry.get("version") or ""))
            if pinned:
                resolved.setdefault(pep440.normalize_name(name), pinned)
    return resolved


# ── requirements.txt ───────────────────────────────────────────────────────


def logical_lines(text: str) -> list[str]:
    """Requirement lines, with continuations joined and comments removed.

    Hash pins are dropped here rather than in the parser: `--hash=` tokens are
    appended to an ordinary requirement (usually across continuation lines), so
    by the time a line is whole they are trailing noise on a line that is
    otherwise exactly what PEP 508 describes.
    """
    joined: list[str] = []
    buffer = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.endswith("\\"):
            buffer += line[:-1].rstrip() + " "
            continue
        buffer += line
        joined.append(buffer)
        buffer = ""
    if buffer:
        joined.append(buffer)

    lines: list[str] = []
    for entry in joined:
        without_comment = _COMMENT_RE.sub("", entry).strip()
        if not without_comment:
            continue
        tokens = [
            token for token in without_comment.split() if not token.startswith("--hash")
        ]
        cleaned = " ".join(tokens).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def parse_requirement(line: str) -> DepSpec | None:
    """One requirement line as a `DepSpec`, or None when it declares nothing.

    None is for lines that are genuinely not a dependency -- a pip option, an
    index URL, or `-e .`, which installs the repository into itself and is not
    one of its dependencies. Everything that *is* a dependency comes back, and
    the ones no registry can describe come back unassessable rather than
    missing: a shorter, tidier table with three rows silently gone is the
    failure this product exists to avoid.
    """
    candidate = line.strip()
    if not candidate:
        return None

    editable = False
    if _EDITABLE_RE.match(candidate):
        editable = True
        candidate = _EDITABLE_RE.sub("", candidate, count=1).strip()
    elif candidate.startswith("-"):
        if candidate.lower().startswith(_PIP_OPTION_PREFIXES):
            return None
        # An unrecognised option is still an option, not a package: pip's
        # surface grows, and guessing that `--some-new-flag` names a
        # distribution would invent a row out of a flag.
        logger.info("Ignoring an unrecognised pip option in a requirements file.")
        return None

    # An environment marker restricts *when* a dependency is installed, never
    # which one it is; the package and its specifier are the same either way.
    requirement = candidate.split(";", 1)[0].strip()
    if not requirement:
        return None

    reason = classify_reference(requirement)
    if reason is not None:
        # A VCS or URL reference names its distribution only if it carries an
        # `#egg=` fragment. Without one there is no name to record, and a row
        # invented from a URL path would be a package that does not exist.
        egg = _EGG_FRAGMENT_RE.search(requirement)
        if egg is None:
            if editable:
                # `-e .` and `-e ./src`: the project installing itself.
                logger.info("Skipping a self-referential editable install.")
            else:
                logger.info("Skipping a dependency reference that names no package.")
            return None
        return DepSpec.unassessable(
            pep440.normalize_name(egg.group("name")), requirement, reason
        )

    match = _REQUIREMENT_RE.match(requirement)
    if match is None:
        return None

    name = pep440.normalize_name(match.group("name"))
    rest = (match.group("rest") or "").strip()

    if rest.startswith("@"):
        # PEP 508's direct reference: `package @ https://.../pkg.whl`. The
        # reference is what is recorded, not the whole line, so this row reads
        # the same way an `-e git+...` one does.
        target = rest[1:].strip()
        return DepSpec.unassessable(
            name, target, classify_reference(target) or REASON_URL
        )

    return _spec_from_specifier(name, rest)


def _spec_from_specifier(
    name: str, specifier: str, group: str = DependencyGroup.RUNTIME.value
) -> DepSpec:
    """A `DepSpec` resolved as far as the specifier alone allows.

    `==2.2.0` pins; anything else is a range, and the scanner will assess it
    against the registry's latest release with `range_latest_approx` recorded
    beside it so the weaker claim is visible.
    """
    pinned = pep440.exact_version(specifier)
    if pinned:
        return DepSpec(
            name=name,
            declared_specifier=specifier,
            group=group,
            resolved_version=pinned,
            resolution=Resolution.PINNED.value,
        )
    return DepSpec(name=name, declared_specifier=specifier, group=group)


# ── pyproject.toml ─────────────────────────────────────────────────────────


def _poetry_spec(name: str, constraint: object, group: str) -> DepSpec | None:
    """One `[tool.poetry.*]` entry, whose value has four shapes in the wild.

    A string is a constraint. A table is a constraint plus options -- or, when
    it carries `git`, `path` or `url`, a reference to something the registry
    has never published. A list is one package constrained differently per
    environment, which pins nothing on its own; the registry path handles it.
    """
    if isinstance(constraint, str):
        return _spec_from_specifier(name, constraint, group)

    if isinstance(constraint, dict):
        for key, reason in (
            ("git", REASON_VCS),
            ("url", REASON_URL),
            ("path", REASON_LOCAL_PATH),
        ):
            if constraint.get(key):
                return DepSpec.unassessable(
                    name, f"{key} = {constraint[key]}", reason, group
                )
        version = constraint.get("version")
        return _spec_from_specifier(
            name, version if isinstance(version, str) else "", group
        )

    if isinstance(constraint, list):
        # Multiple constraints, each for a different marker. None of them pins
        # this install on its own, so the declared text records all of them and
        # resolution falls to the lockfile or the registry.
        parts = [
            entry.get("version")
            for entry in constraint
            if isinstance(entry, dict) and isinstance(entry.get("version"), str)
        ]
        return DepSpec(name=name, declared_specifier=" || ".join(parts), group=group)

    return None


def _parse_pyproject(manifest_bytes: bytes) -> list[DepSpec]:
    """PEP 621 and poetry, both, from the one file that may carry either.

    Both schemas are read rather than one being chosen, because a real
    `pyproject.toml` may carry a PEP 621 `[project]` table *and* a
    `[tool.poetry.group.dev.dependencies]` block -- poetry has supported the
    standard table since 1.5 while keeping its own groups. Reading only the
    first would drop every dev dependency in such a project silently.
    """
    document = _load_toml(manifest_bytes, "pyproject.toml")
    specs: list[DepSpec] = []
    seen: set[str] = set()

    def add(spec: DepSpec | None) -> None:
        if spec is None or not spec.name or spec.name in seen:
            return
        seen.add(spec.name)
        specs.append(spec)

    project = document.get("project")
    if isinstance(project, dict):
        for entry in project.get("dependencies") or []:
            if isinstance(entry, str):
                add(parse_requirement(entry))

        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for entries in optional.values():
                for entry in entries or []:
                    if isinstance(entry, str):
                        spec = parse_requirement(entry)
                        if spec is not None:
                            add(_regrouped(spec, DependencyGroup.OPTIONAL.value))

    poetry = ((document.get("tool") or {}).get("poetry")) or {}
    if isinstance(poetry, dict):
        sections: list[tuple[dict, str]] = [
            (poetry.get("dependencies") or {}, DependencyGroup.RUNTIME.value),
            (poetry.get("dev-dependencies") or {}, DependencyGroup.DEVELOPMENT.value),
        ]
        for group_body in (poetry.get("group") or {}).values():
            if isinstance(group_body, dict):
                sections.append(
                    (
                        group_body.get("dependencies") or {},
                        DependencyGroup.DEVELOPMENT.value,
                    )
                )

        for section, group in sections:
            if not isinstance(section, dict):
                continue
            for raw_name, constraint in section.items():
                if not isinstance(raw_name, str) or raw_name.lower() == "python":
                    # `python = "^3.11"` constrains the interpreter, which is
                    # not a distribution and has no registry entry.
                    continue
                add(_poetry_spec(pep440.normalize_name(raw_name), constraint, group))

    return specs


def _regrouped(spec: DepSpec, group: str) -> DepSpec:
    """The same spec in a different dependency group."""
    if spec.group == group:
        return spec
    return DepSpec(
        name=spec.name,
        declared_specifier=spec.declared_specifier,
        group=group,
        resolved_version=spec.resolved_version,
        resolution=spec.resolution,
        is_unassessable=spec.is_unassessable,
        unassessable_reason=spec.unassessable_reason,
    )


# ── Pipfile ────────────────────────────────────────────────────────────────


def _pipfile_spec(name: str, constraint: object, group: str) -> DepSpec | None:
    """One `[packages]` entry. `"*"` means "any version", which pins nothing."""
    if isinstance(constraint, str):
        # `"*"` is stored as written rather than blanked: it is what the file
        # says, and `exact_version` already reads it as the range it is.
        return _spec_from_specifier(name, constraint, group)

    if isinstance(constraint, dict):
        for key, reason in (
            ("git", REASON_VCS),
            ("file", REASON_URL),
            ("path", REASON_LOCAL_PATH),
        ):
            if constraint.get(key):
                return DepSpec.unassessable(
                    name, f"{key} = {constraint[key]}", reason, group
                )
        version = constraint.get("version")
        return _spec_from_specifier(
            name, version if isinstance(version, str) else "", group
        )

    return None


def _parse_pipfile(manifest_bytes: bytes) -> list[DepSpec]:
    document = _load_toml(manifest_bytes, "Pipfile")
    specs: list[DepSpec] = []
    seen: set[str] = set()

    for section_name, group in (
        ("packages", DependencyGroup.RUNTIME.value),
        ("dev-packages", DependencyGroup.DEVELOPMENT.value),
    ):
        section = document.get(section_name)
        if not isinstance(section, dict):
            continue
        for raw_name, constraint in section.items():
            if not isinstance(raw_name, str):
                continue
            name = pep440.normalize_name(raw_name)
            if name in seen:
                # pipenv installs one copy; `[packages]` is read first, so the
                # runtime declaration wins exactly as npm's `dependencies` does.
                continue
            spec = _pipfile_spec(name, constraint, group)
            if spec is not None:
                seen.add(name)
                specs.append(spec)

    return specs


# ── setup.py ───────────────────────────────────────────────────────────────

#: `setup()` keywords that declare dependencies, and the group each maps onto.
_SETUP_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("install_requires", DependencyGroup.RUNTIME.value),
    ("setup_requires", DependencyGroup.BUILD.value),
    ("tests_require", DependencyGroup.DEVELOPMENT.value),
    ("extras_require", DependencyGroup.OPTIONAL.value),
)


def _module_literals(tree: ast.Module) -> dict[str, object]:
    """Top-level `NAME = <literal>` bindings, evaluated as data.

    `install_requires=REQUIREMENTS` with `REQUIREMENTS = [...]` above it is the
    most common shape a real `setup.py` takes that is not a plain literal, and
    it is entirely static -- resolving it here is the difference between
    reading a project's dependencies and declaring them unassessable.

    `ast.literal_eval` only ever builds constants, tuples, lists, dicts and
    sets. It calls nothing, imports nothing and reads no attribute, so a
    hostile `setup.py` gets no more out of this than a friendly one does.
    """
    bindings: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                bindings[target.id] = ast.literal_eval(node.value)
            except (ValueError, SyntaxError, TypeError):
                continue
    return bindings


def _resolve_literal(node: ast.AST, bindings: dict[str, object]) -> object | None:
    """The value of a `setup()` argument, if it can be had without running it."""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        pass
    if isinstance(node, ast.Name) and node.id in bindings:
        return bindings[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_literal(node.left, bindings)
        right = _resolve_literal(node.right, bindings)
        if isinstance(left, list) and isinstance(right, list):
            return [*left, *right]
    return None


def _find_setup_call(tree: ast.Module) -> ast.Call | None:
    """The `setup(...)` call, wherever in the file it sits.

    `ast.walk` rather than a scan of the top level: the call is routinely
    inside `if __name__ == "__main__":`, and a top-level-only search would read
    those files as declaring nothing at all.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if name == "setup":
            return node
    return None


def _requirement_strings(value: object, keyword: str) -> tuple[list[str], bool]:
    """Requirement strings from a resolved argument, and whether any were lost.

    `extras_require` is a dict of lists; the other three are lists. A non-string
    element is a construct we did not evaluate, and the second return value
    says so -- silently keeping the strings and dropping the rest is the
    miscount this whole module is arranged to avoid.
    """
    if keyword == "extras_require":
        if not isinstance(value, dict):
            return ([], True)
        entries: list[object] = []
        for group_entries in value.values():
            if isinstance(group_entries, list | tuple):
                entries.extend(group_entries)
            else:
                return ([], True)
    elif isinstance(value, list | tuple):
        entries = list(value)
    else:
        return ([], True)

    strings = [entry for entry in entries if isinstance(entry, str)]
    return (strings, len(strings) != len(entries))


def _parse_setup_py(manifest_bytes: bytes) -> list[DepSpec]:
    try:
        tree = ast.parse(manifest_bytes)
    except (SyntaxError, ValueError) as exc:
        raise ManifestParseError(f"setup.py is not parseable Python: {exc}") from exc

    call = _find_setup_call(tree)
    if call is None:
        # A `setup.py` that never calls `setup()` -- a shim, or a file that
        # only defines helpers. It declares nothing, which is an answer.
        return []

    bindings = _module_literals(tree)
    arguments = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg}

    specs: list[DepSpec] = []
    seen: set[str] = set()
    for keyword, group in _SETUP_KEYWORDS:
        node = arguments.get(keyword)
        if node is None:
            continue

        resolved = _resolve_literal(node, bindings)
        strings, incomplete = (
            ([], True) if resolved is None else _requirement_strings(resolved, keyword)
        )

        for entry in strings:
            spec = parse_requirement(entry)
            if spec is None or spec.name in seen:
                continue
            seen.add(spec.name)
            specs.append(_regrouped(spec, group))

        if incomplete:
            # The documented gap, stated on the page rather than in a log.
            specs.append(
                DepSpec.unassessable(
                    DYNAMIC_SETUP_PACKAGE.format(keyword=keyword),
                    _source_excerpt(node, manifest_bytes),
                    REASON_DYNAMIC_SETUP,
                    group,
                )
            )

    return specs


#: How much of a dynamic expression is quoted back. Long enough to recognise
#: the construct, short enough that a `declared_specifier` column stays a
#: column.
MAX_EXCERPT_CHARS = 120


def _source_excerpt(node: ast.AST, manifest_bytes: bytes) -> str:
    """The source text of the expression we declined to evaluate.

    Quoted rather than described, for the same reason the deprecation reason is
    stored verbatim: the reader is being told what their own file says, and a
    paraphrase turns a citation into our assertion.
    """
    try:
        source = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    segment = ast.get_source_segment(source, node) or ""
    segment = " ".join(segment.split())
    if len(segment) > MAX_EXCERPT_CHARS:
        segment = segment[: MAX_EXCERPT_CHARS - 3] + "..."
    return segment


# ── the adapter ────────────────────────────────────────────────────────────


class PypiAdapter(DependencyAdapter):
    """One instance per manifest path, produced by `for_path`.

    The registered singleton carries no kind and exists to answer the registry
    and ownership questions -- `manifest_patterns`, `owns`, `registry_client` --
    which are the same for all five formats.
    """

    ecosystem = Ecosystem.PYPI.value

    def __init__(self, kind: str = "", manifest_path: str = "") -> None:
        self.kind = kind
        self.manifest_path = manifest_path
        # Recorded on `manifest_files.parser_name`, so a stored row says which
        # of the five parsers read it -- the column exists for exactly that,
        # and "pypi" alone would answer a narrower question than it was asked.
        self.parser_name = f"pypi/{kind}@1" if kind else "pypi@1"

    def manifest_patterns(self) -> frozenset[str]:
        return FIXED_MANIFESTS

    def owns(self, path: str) -> bool:
        basename = path.rsplit("/", 1)[-1]
        if basename in FIXED_MANIFESTS:
            return True
        if _REQUIREMENTS_BASENAME_RE.match(basename):
            return True
        # `requirements/base.txt`, `requirements/prod.txt` -- the split layout
        # every large Django project seems to arrive at. Narrow on purpose: the
        # directory must be named `requirements`, so an ordinary `docs/*.txt`
        # is untouched.
        parent = path.rsplit("/", 2)[-2] if "/" in path else ""
        return parent.lower() == "requirements" and basename.lower().endswith(".txt")

    def for_path(self, path: str) -> PypiAdapter:
        return PypiAdapter(kind=_kind_for_path(path), manifest_path=path)

    def lockfile_names(self, manifest_path: str) -> tuple[str, ...]:
        """The sibling that states what is installed, per manifest kind.

        `requirements.txt` has none by design: it *is* the resolved list when
        `pip-compile` produced it, and an ordinary hand-written one has nothing
        beside it that resolves it. `uv.lock` and `pdm.lock` are absent for
        `npm.py`'s reason about yarn and pnpm -- a half-understood parse is
        worse than an honest range approximation.
        """
        basename = manifest_path.rsplit("/", 1)[-1]
        if basename == "pyproject.toml":
            return ("poetry.lock",)
        if basename == "Pipfile":
            return ("Pipfile.lock",)
        return ()

    def parse(
        self, manifest_bytes: bytes, lockfile_bytes: bytes | None = None
    ) -> list[DepSpec]:
        if self.kind == KIND_PYPROJECT:
            specs = _parse_pyproject(manifest_bytes)
            locked = resolve_poetry_lock(lockfile_bytes)
        elif self.kind == KIND_PIPFILE:
            specs = _parse_pipfile(manifest_bytes)
            locked = resolve_pipfile_lock(lockfile_bytes)
        elif self.kind == KIND_SETUP_PY:
            specs = _parse_setup_py(manifest_bytes)
            locked = {}
        elif self.kind == KIND_REQUIREMENTS:
            specs = self._parse_requirements(manifest_bytes)
            locked = {}
        else:
            raise ValueError(
                "PypiAdapter.parse needs a path-bound adapter; use for_path()."
            )

        return [self._apply_lockfile(spec, locked) for spec in specs]

    def _parse_requirements(self, manifest_bytes: bytes) -> list[DepSpec]:
        try:
            text = manifest_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManifestParseError("Requirements file is not UTF-8.") from exc

        group = _group_for_requirements_file(self.manifest_path)
        specs: list[DepSpec] = []
        seen: set[str] = set()
        for line in logical_lines(text):
            spec = parse_requirement(line)
            if spec is None or spec.name in seen:
                continue
            seen.add(spec.name)
            specs.append(_regrouped(spec, group))
        return specs

    @staticmethod
    def _apply_lockfile(spec: DepSpec, locked: dict[str, str]) -> DepSpec:
        """The lockfile's version, where there is one, beating the manifest's.

        Never applied to an unassessable row: a `git+` reference resolves to a
        commit, not to a release, and a lockfile version standing in for one
        would attribute a published package's advisories to source we cannot
        identify.
        """
        if spec.is_unassessable or not locked:
            return spec
        version = locked.get(spec.name)
        if not version:
            return spec
        return DepSpec(
            name=spec.name,
            declared_specifier=spec.declared_specifier,
            group=spec.group,
            resolved_version=version,
            resolution=Resolution.LOCKFILE.value,
        )

    def registry_client(self):
        from .registry_clients import PypiRegistryClient

        return PypiRegistryClient()


pypi_adapter = register(PypiAdapter())
