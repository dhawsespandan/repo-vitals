"""The scan-independent driver (§10 Phase 13 commit 3).

Real here, as in `test_agent_graph.py`: the chunker, the embedded Chroma store
(in a temporary directory), the production framing, gate, prompts, generation
and schema validation. Stubbed: the document fetch, the embedding model and the
LLM — the embedder by angle, so a similarity is a number the test chooses.
"""

from __future__ import annotations

import math

import pytest

from apps.reports.agent import graph
from apps.reports.llm.groq_client import LlmCall, LlmUnavailable
from apps.reports.llm.prompts import GROUNDED_SYSTEM_PROMPT, UNGROUNDED_SYSTEM_PROMPT
from apps.reports.models import Report
from apps.reports.rag import chroma_store, fetch_docs
from apps.research.experiment import conditions, driver
from apps.research.guards import no_operational_writes
from apps.research.models import AgentExecutionTrace
from apps.scanning.models import DependencyOccurrence, ScanRun
from tests.test_agent_graph import CHANGELOG

ITEM = {
    "item_id": "S3-test000001",
    "case_type": "cve_fix",
    "ecosystem": "npm",
    "package": "express",
    "resolved_version": "3.1.0",
    "target": {
        "package": "express",
        "ecosystem": "npm",
        "manifest_path": "package.json",
        "group": "runtime",
        "declared_specifier": "^3.0.0",
        "current_version": "3.1.0",
        "version_source": "lockfile",
        "latest_version": "4.0.0",
        "versions_behind": {"major": 1, "minor": 0, "patch": 0},
        "deprecated": False,
        "advisory_count": 1,
        "highest_severity": "high",
        "flag_reasons": ["vulnerable"],
        "advisories": [
            {"osv_id": "GHSA-1", "cve_id": "CVE-2026-0001", "severity": "high",
             "cvss": 7.5, "fixed_version": "3.1.2"}
        ],
        "days_since_release": 30,
    },
    "context_rows": [
        {"package": "express", "ecosystem": "npm", "manifest_path": "package.json",
         "current_version": "3.1.0", "highest_severity": "high", "cves": ["CVE-2026-0001"]}
    ],
    "ground_truth": {"target_version": "3.1.2", "advisories": []},
}  # fmt: skip

ANSWER = (
    '{"summary_md": "Upgrade to 3.1.2.", "fixes": [{"package": "express", '
    '"manifest_path": "package.json", "ecosystem": "npm", "fix_type": "upgrade", '
    '"target_version": "3.1.2", "replacement_package": null, "priority": 1}], '
    '"citations": []}'
)


class Model:
    def __init__(self, *contents: str) -> None:
        self.contents = list(contents) or [ANSWER]
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str) -> LlmCall:
        self.calls.append((system_prompt, user_prompt))
        content = self.contents[min(len(self.calls) - 1, len(self.contents) - 1)]
        return LlmCall(content, "test-model", 10, 10, 5, 1)


def unit(angle: float) -> list[float]:
    return [math.cos(angle), math.sin(angle)]


@pytest.fixture
def store(tmp_path, settings, monkeypatch):
    """Real Chroma; stubbed fetch and embedder. Returns the fetch-call log."""
    settings.CHROMA_DIR = str(tmp_path / "chroma")
    chroma_store.reset_for_tests()
    fetched: list[str] = []

    def fake_fetch(*, ecosystem, package_name, token, registry_client=None):
        fetched.append(package_name)
        return fetch_docs.FetchResult(
            docs=(fetch_docs.SourceDoc("changelog", "CHANGELOG.md", "blob1", CHANGELOG),),
            repo_full_name="expressjs/express",
        )

    monkeypatch.setattr(driver.fetch_docs, "fetch_for", fake_fetch)
    angles = {"query": 0.0}
    monkeypatch.setattr(
        driver.embeddings,
        "embed",
        lambda texts: [unit(angles["query"] if len(texts) == 1 else 0.0) for _ in texts],
    )
    yield {"fetched": fetched, "angles": angles}
    chroma_store.reset_for_tests()


def run(name: str, tmp_path, model=None, **kwargs) -> driver.ItemResult:
    return driver.run_item(
        ITEM,
        conditions.get(name),
        run_id=f"{name}_test",
        complete=model or Model(),
        cache=driver.DocsCache(tmp_path / "runs"),
        **kwargs,
    )


@pytest.mark.django_db
class TestEachCondition:
    def test_a_retrieves_nothing_and_takes_the_grounded_prompt(self, tmp_path, store):
        model = Model()
        result = run("A", tmp_path, model)
        assert result.status == "ok"
        assert store["fetched"] == []
        assert result.retrieved == []
        system, user = model.calls[0]
        assert system == GROUNDED_SYSTEM_PROMPT
        assert "No passages were retrieved" in user
        assert user.startswith("This dependency is flagged by the scan.")
        assert result.branch == "fixed"

    def test_b_always_shows_its_passages_even_when_they_are_weak(self, tmp_path, store):
        store["angles"]["query"] = math.radians(85)  # similarity ~0.09, far under 0.30
        model = Model()
        result = run("B", tmp_path, model)
        assert result.grounding == "sufficient"  # no gate
        assert len(result.retrieved) > 0
        assert result.shown_chunk_ids == [c["chunk_id"] for c in result.retrieved]
        assert model.calls[0][0] == GROUNDED_SYSTEM_PROMPT
        assert "BEGIN SOURCE\n[1] id:" in model.calls[0][1]

    def test_c_lets_the_production_gate_decide(self, tmp_path, store):
        store["angles"]["query"] = math.radians(85)
        model = Model()
        result = run("C", tmp_path, model)
        assert result.branch == "no_reason"
        assert result.grounding == "low"
        assert result.retrieved  # recorded: what was retrieved and rejected
        assert result.shown_chunk_ids == []
        assert model.calls[0][0] == UNGROUNDED_SYSTEM_PROMPT

    def test_c_grounded_when_retrieval_is_close(self, tmp_path, store):
        result = run("C", tmp_path)
        assert result.grounding == "sufficient"
        assert result.shown_chunk_ids

    def test_d_indexes_issues_beside_the_changelog(self, tmp_path, store, monkeypatch):
        monkeypatch.setattr(
            driver.issue_search,
            "fetch_issues",
            lambda client, repo: [
                fetch_docs.SourceDoc(
                    "issue", "issues/9", "issue-9-x", "# Migrate\n\n" + "words " * 80
                )
            ],
        )
        result = run("D", tmp_path, issue_client=object())
        assert result.corpus["issues"]["count"] == 1
        assert {s["kind"] for s in result.corpus["sources"]} == {"changelog", "issue"}


@pytest.mark.django_db
class TestTheDriversDiscipline:
    def test_conditions_share_one_copy_of_the_documents(self, tmp_path, store):
        """Paired design: B, C and D must read the same text, days apart."""
        run("B", tmp_path)
        run("C", tmp_path)
        assert store["fetched"] == ["express"]

    def test_the_store_is_empty_after_each_item(self, tmp_path, store):
        run("C", tmp_path)
        assert (
            chroma_store.count_for(
                scan_id=driver.run_uuid("C_test"),
                ecosystem="npm",
                package_name="express",
                resolved_version="3.1.0",
            )
            == 0
        )

    def test_no_operational_row_is_written(self, tmp_path, store):
        """D10, at the cursor: the driver runs inside the guard, and writes
        neither the report nor the trace `graph.run` would have."""
        with no_operational_writes():
            for name in "ABC":
                run(name, tmp_path)
        assert ScanRun.objects.count() == 0
        assert DependencyOccurrence.objects.count() == 0
        assert Report.objects.count() == 0
        assert AgentExecutionTrace.objects.count() == 0

    def test_an_unusable_payload_is_a_failed_item_not_a_crash(self, tmp_path, store):
        result = run("A", tmp_path, Model('{"nonsense": true}'))
        assert result.status == "failed"
        assert result.error

    def test_a_provider_that_does_not_answer_is_the_runners_problem(
        self, tmp_path, store
    ):
        def down(system, user):
            raise LlmUnavailable("down")

        with pytest.raises(LlmUnavailable):
            run("A", tmp_path, down)

    def test_the_collection_is_named_for_the_run(self):
        assert driver.run_uuid("C_abc") == driver.run_uuid("C_abc")
        assert driver.run_uuid("C_abc") != driver.run_uuid("B_abc")

    def test_generation_is_the_graphs_own(self):
        """C is the production code, called: the driver has no generate of its own."""
        assert driver.graph.generate is graph.generate
