"""S3's conditions (§10 Phase 13 commit 2), and D13's fence around condition D.

The conditions are checked for the one property the study design needs from
them: each pair differs in exactly the thing its research question is about.
"""

from __future__ import annotations

import pathlib
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from apps.common import http
from apps.reports.llm.prompts import FIXED_FRAMING, build_per_dependency_user_prompt
from apps.research import issue_search
from apps.research.experiment import conditions
from apps.research.github import ResearchClient

TARGET = {
    "package": "request",
    "ecosystem": "npm",
    "manifest_path": "package.json",
    "current_version": "2.88.2",
    "latest_version": "2.88.2",
    "deprecated": True,
    "deprecation_reason": "request has been deprecated, see issue 3142",
    "advisories": [],
}

VULNERABLE = {
    "package": "lodash",
    "ecosystem": "npm",
    "manifest_path": "package.json",
    "current_version": "4.17.19",
    "latest_version": "4.17.21",
    "deprecated": False,
    "advisories": [{"osv_id": "GHSA-1", "fixed_version": "4.17.21"}],
}


@pytest.fixture(autouse=True)
def quiet_network(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)


class TestTheFourConditions:
    def test_each_pair_differs_in_one_thing(self):
        a, b, c, d = (conditions.get(name) for name in "ABCD")
        # RQ1: A vs B — only retrieval.
        assert (a.branching, a.gate) == (b.branching, b.gate) == (False, False)
        assert not a.retrieval and b.retrieval
        # RQ2: B vs C — framing and gate, same sources.
        assert b.sources == c.sources == (conditions.CHANGELOG,)
        assert not b.branching and c.branching
        assert not b.gate and c.gate
        # RQ4: C vs D — only what was indexed.
        assert (c.branching, c.gate) == (d.branching, d.gate)
        assert d.sources == (conditions.CHANGELOG, conditions.ISSUES)
        assert d.internal and not c.internal

    def test_an_unknown_condition_is_refused(self):
        with pytest.raises(conditions.UnknownCondition, match="A, B, C, D"):
            conditions.get("E")
        assert conditions.get("c").name == "C"

    def test_c_and_d_frame_with_the_production_branch(self):
        branch, query = conditions.frame(conditions.get("C"), TARGET)
        assert branch == "reason_available"
        assert "request has been deprecated" in query
        branch, query = conditions.frame(conditions.get("D"), VULNERABLE)
        assert branch == "no_reason"
        assert "4.17.21" in query

    def test_a_and_b_frame_every_item_the_same_way(self):
        for target in (TARGET, VULNERABLE):
            for name in "AB":
                branch, query = conditions.frame(conditions.get(name), target)
                assert branch == FIXED_FRAMING
                assert query == conditions.fixed_query(target)

    def test_only_c_and_d_consult_the_gate(self, settings):
        settings.GROUNDING_MIN_SIM = 0.30
        settings.GROUNDING_MIN_CHARS = 400
        empty = {"retrieved": [], "context": {"package_name": "x"}}
        strong = {
            "retrieved": [{"similarity": 0.8, "text": "x" * 500}],
            "context": {"package_name": "x"},
        }
        for name in "AB":
            assert conditions.grounding_for(conditions.get(name), empty) == "sufficient"
        assert conditions.grounding_for(conditions.get("C"), empty) == "low"
        assert conditions.grounding_for(conditions.get("C"), strong) == "sufficient"


class TestTheFixedFramingTask:
    def test_it_is_true_of_a_deprecated_dependency(self):
        prompt = build_per_dependency_user_prompt(
            target=TARGET, chunks=[], query="q", branch=FIXED_FRAMING
        )
        assert "not deprecated" not in prompt
        assert prompt.startswith("This dependency is flagged by the scan.")

    def test_the_production_branches_are_unchanged(self):
        no_reason = build_per_dependency_user_prompt(
            target=VULNERABLE, chunks=[], query="q", branch="no_reason"
        )
        reason = build_per_dependency_user_prompt(
            target=TARGET, chunks=[], query="q", branch="reason_available"
        )
        assert no_reason.startswith("This dependency is flagged but not deprecated.")
        assert reason.startswith("This dependency is marked deprecated by its registry.")


# ── condition D's issue search ─────────────────────────────────────────────

SEARCH_URL = "https://api.github.com/search/issues"


class TestIssueSearch:
    @responses.activate
    def test_issues_become_source_documents_and_prs_do_not(self, settings):
        settings.GITHUB_API_PAT = "ghp_research_token"
        responses.add(
            responses.GET,
            SEARCH_URL,
            json={
                "items": [
                    {"number": 3142, "title": "Request's past, present and future",
                     "body": "request is deprecated. Consider got or axios.",
                     "updated_at": "2020-02-11T00:00:00Z"},
                    {"number": 7, "title": "a PR", "body": "x", "pull_request": {}},
                    {"number": 8, "title": "", "body": ""},
                ]
            },
            headers={"x-ratelimit-remaining": "29", "x-ratelimit-reset": "0"},
        )  # fmt: skip
        client = ResearchClient.from_settings()

        docs = issue_search.fetch_issues(client, "request/request")

        assert [doc.path for doc in docs] == ["issues/3142"]
        assert docs[0].kind == "issue"
        assert docs[0].text.startswith("# Request's past, present and future")
        query = parse_qs(urlparse(responses.calls[0].request.url).query)["q"][0]
        assert query.startswith("repo:request/request is:issue deprecated OR")
        # Counted against the search allowance, not the REST one.
        assert client.search_calls == 1
        assert client.search_budget.remaining == 29
        assert client.rest_calls == 0

    def test_a_name_that_is_not_owner_slash_repo_searches_nothing(self, settings):
        settings.GITHUB_API_PAT = "ghp_research_token"
        assert issue_search.fetch_issues(ResearchClient.from_settings(), "nope") == []
        assert issue_search.fetch_issues(ResearchClient.from_settings(), None) == []

    @responses.activate
    def test_a_failed_search_is_an_empty_result(self, settings):
        settings.GITHUB_API_PAT = "ghp_research_token"
        responses.add(responses.GET, SEARCH_URL, status=500)
        assert issue_search.fetch_issues(ResearchClient.from_settings(), "a/b") == []

    def test_text_is_capped(self):
        assert issue_search.MAX_ISSUE_CHARS == 20_000


def test_issue_search_is_unreachable_from_any_request_path():
    """D13: "never imported by request-handling code". By import graph."""
    import apps.reports.views
    import apps.repositories.views
    import apps.scanning.views

    for module in (apps.scanning.views, apps.repositories.views, apps.reports.views):
        names = {getattr(value, "__module__", "") for value in vars(module).values()}
        assert not any(
            name.startswith(("apps.research.issue_search", "apps.research.experiment"))
            for name in names
        ), module.__name__


def test_issue_search_is_imported_only_by_the_experiment():
    """D13 by source: the only modules naming it are the experiment's own."""
    backend = pathlib.Path(__file__).resolve().parent.parent
    importers = sorted(
        str(path.relative_to(backend)).replace("\\", "/")
        for path in (backend / "apps").rglob("*.py")
        if "issue_search" in path.read_text(encoding="utf-8")
        and path.name != "issue_search.py"
    )
    assert all(path.startswith("apps/research/") for path in importers), importers


def test_no_route_reaches_condition_d():
    """D13 against the URL table: no pattern's view lives in the research app."""
    from django.urls import get_resolver

    def walk(patterns):
        for entry in patterns:
            if hasattr(entry, "url_patterns"):
                yield from walk(entry.url_patterns)
            else:
                yield entry

    for entry in walk(get_resolver().url_patterns):
        callback = getattr(entry, "callback", None)
        module = getattr(getattr(callback, "view_class", callback), "__module__", "")
        assert not module.startswith(
            ("apps.research.experiment", "apps.research.issue_search")
        )
        assert "issue" not in str(entry.pattern)
