"""§11's grep audit: no GitHub write call exists anywhere.

The OAuth scope is `repo` because GitHub OAuth Apps offer no read-only private
scope (§5.6, and the comment on `SOCIALACCOUNT_PROVIDERS`). A token with that
scope can create branches, push commits and open pull requests in every
repository its owner can write to. What makes it safe to hold is a single
claim: **this backend never writes.** §11 lists the verification as
"grep-audit Phase 9", and §12 puts "auto-PRs or any write to user repos" under
do-not-build.

This file is that audit, run on every commit rather than once by hand, and it
checks the claim three ways because a grep alone answers only about today:

1. **Structural.** `common/http.py` refuses a non-GET to a read-only host, per
   hop, before the socket opens. This is the only check that binds code nobody
   has written yet.
2. **Topological.** There is exactly one outbound HTTP path. `requests` is
   imported in one module, so there is no second client to audit.
3. **Textual.** The grep §11 actually asks for, narrowed to the modules that
   build GitHub URLs at all: none of them posts, and none of them so much as
   names a write verb.

None of the three is sufficient alone. The structural check cannot see a second
HTTP library; the topological check cannot see a POST through the sanctioned
one; the textual check cannot see a URL assembled at runtime.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import responses

from apps.common import http

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SOURCE_DIRS = (BACKEND / "apps", BACKEND / "config")

#: Where the one HTTP client lives. Every other module reaches the network
#: through it or not at all.
CLIENT = BACKEND / "apps" / "common" / "http.py"


def source_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for directory in SOURCE_DIRS:
        files.extend(
            path
            for path in directory.rglob("*.py")
            if "migrations" not in path.parts and "__pycache__" not in path.parts
        )
    assert len(files) > 30, "the audit found almost no source files — check the paths"
    return files


# ── 1. Structural: the client itself refuses ────────────────────────────────


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_write_to_github_is_refused_before_the_socket_opens(method):
    """Not "no code does this" but "this cannot be done"."""
    with pytest.raises(http.WriteCallRefused):
        http._check_method(method, "https://api.github.com/repos/o/r/pulls")


def test_reads_are_unaffected():
    http._check_method("GET", "https://api.github.com/repos/o/r")
    http._check_method("HEAD", "https://api.github.com/repos/o/r")


def test_the_hosts_that_need_a_post_still_get_one():
    """OSV's `querybatch` and Groq's completion are POSTs that write nothing.

    The rule is per host rather than per method for exactly this reason: a
    blanket "no POST anywhere" would break the batching that makes a scan fit
    inside a free tier's rate budget (§8).
    """
    http._check_method("POST", "https://api.osv.dev/v1/querybatch")
    http._check_method("POST", "https://api.groq.com/openai/v1/chat/completions")


def test_a_redirect_cannot_smuggle_a_write_through():
    """The check runs per hop, so an allowlisted host cannot redirect into one.

    307 preserves the method. Without a per-hop check, a POST to OSV that was
    redirected to `api.github.com` would arrive there as a POST, having passed
    a method check made once on a URL that was fine.
    """
    with responses.RequestsMock() as mock:
        mock.add(
            responses.POST,
            "https://api.osv.dev/v1/querybatch",
            status=307,
            headers={"Location": "https://api.github.com/repos/o/r/pulls"},
        )

        with pytest.raises(http.WriteCallRefused):
            http.post_json("https://api.osv.dev/v1/querybatch", {"queries": []})


def test_the_client_exposes_no_write_helper():
    """There is no `put_json`, `patch_json` or `delete_json` to call.

    A write helper that existed "for later" is a write helper somebody uses.
    """
    assert not [
        name
        for name in dir(http)
        if any(name.startswith(verb) for verb in ("put_", "patch_", "delete_"))
    ]


# ── 2. Topological: one client, no second path ──────────────────────────────


def test_requests_is_imported_in_exactly_one_module():
    """§5.6's "single choke point all outbound HTTP must pass through".

    If this fails, the other checks in this file have stopped covering the code
    — there is a second way out of the process and the audit does not know its
    rules.
    """
    importers = [
        path.relative_to(BACKEND).as_posix()
        for path in source_files()
        if re.search(
            r"^\s*(import requests|from requests)", path.read_text(encoding="utf-8"), re.M
        )
    ]

    assert importers == ["apps/common/http.py"]


@pytest.mark.parametrize(
    "library",
    ["httpx", "urllib.request", "aiohttp", "http.client", "urllib3"],
)
def test_no_second_http_library_is_used(library):
    offenders = [
        path.relative_to(BACKEND).as_posix()
        for path in source_files()
        if re.search(
            rf"^\s*(import {re.escape(library)}|from {re.escape(library)})",
            path.read_text(encoding="utf-8"),
            re.M,
        )
    ]

    assert not offenders, f"{library} is reachable from {offenders}"


# ── 3. Textual: the grep §11 asks for ───────────────────────────────────────


def github_modules() -> list[pathlib.Path]:
    """Every module that builds a URL against the GitHub API.

    This is the set the audit is actually about. A write to GitHub has to start
    with a GitHub URL, so whatever these files do with the URLs they build is
    the whole question.
    """
    modules = [
        path
        for path in source_files()
        if path != CLIENT and "api.github.com" in path.read_text(encoding="utf-8")
    ]
    assert modules, "no module builds a GitHub URL — the audit is looking at nothing"
    return modules


def test_no_module_that_builds_a_github_url_ever_posts():
    """The grep, aimed at the thing that matters.

    An earlier version of this test listed "write endpoints" by path —
    `/pulls`, `/git/refs`, `/git/blobs` — and flagged `apps/scanning/scanner.py`
    on its first run. That was a fault in the test, not in the scanner:
    `GET /repos/{o}/{r}/git/blobs/{sha}` is how every manifest in this product
    is *read*. Almost every GitHub endpoint answers both a read and a write
    depending on the verb, so a list of paths cannot express the rule. The verb
    can, and `post_json` is the only way to reach one from here.
    """
    offenders = [
        path.relative_to(BACKEND).as_posix()
        for path in github_modules()
        if re.search(r"post_json\s*\(", path.read_text(encoding="utf-8"))
    ]

    assert not offenders, f"a GitHub-facing module posts: {offenders}"


def test_no_module_names_a_write_verb_against_github():
    """Belt and braces for a call that did not go through `post_json` at all.

    Bare method strings in a GitHub-facing module are how a future write would
    most plausibly start — a new helper, a direct `_follow`, a session call
    somebody added without reading this file.
    """
    offenders: list[str] = []
    for path in github_modules():
        text = path.read_text(encoding="utf-8")
        for verb in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"', "'POST'", "'PUT'"):
            if verb in text:
                offenders.append(f"{path.relative_to(BACKEND).as_posix()}: {verb}")

    assert not offenders, f"write verbs in GitHub-facing modules: {offenders}"


def test_the_only_post_call_sites_are_the_two_that_need_one():
    """`post_json` has exactly two callers, and neither talks to GitHub.

    A new caller is not forbidden — Phase 13's judge provider will be a third —
    but it has to be added here deliberately, which is the moment somebody
    reads what it is posting and to whom.
    """
    callers = sorted(
        path.relative_to(BACKEND).as_posix()
        for path in source_files()
        if path != CLIENT
        and re.search(r"\bpost_json\s*\(", path.read_text(encoding="utf-8"))
    )

    assert callers == ["apps/reports/llm/groq_client.py", "apps/scanning/osv.py"]


def test_the_read_only_list_still_names_github():
    """The audit above is worth nothing if the host ever leaves this set."""
    assert "api.github.com" in http.READ_ONLY_HOSTS
    assert http.READ_ONLY_METHODS == frozenset({"GET", "HEAD"})
