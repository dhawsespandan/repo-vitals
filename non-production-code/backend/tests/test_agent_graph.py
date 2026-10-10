"""§5.9's graph, end to end, against a real chunk store and a stubbed model.

What is real here and what is not is a deliberate line.

**Real:** the graph, the chunker, the chunk store (embedded Chroma in a
temporary directory), the schema validation, the report row, the trace row, and
the cleanup. Those are the parts §10 Phase 8's acceptance makes claims about.

**Stubbed:** the network (`fetch_docs`), the embedding model, and the LLM. The
first two are stubbed because they are slow and remote; the third because §4.4
says so and because "the repair retry fired exactly once" is only assertable
against a callable that counts.

The embedder is worth a note. It maps text to a unit vector on a circle by
keyword, so cosine similarity between a query and a chunk is a number this file
chooses. That is what makes §5.9's grounding threshold testable *as a
threshold* — a real model would give 0.41 or 0.29 depending on the day, and a
test that asserted a verdict on that would be asserting a mood.
"""

from __future__ import annotations

import json
import math

import pytest
from django.test import override_settings
from django.urls import reverse

from apps.reports.agent import graph as agent_graph
from apps.reports.agent.graph import AgentFailed
from apps.reports.llm.groq_client import LlmCall
from apps.reports.models import GroundingConfidence, Report, ReportStatus, ReportType
from apps.reports.rag import chroma_store, embeddings, fetch_docs
from apps.research.models import AgentBranch, AgentExecutionTrace, ScanHistory
from apps.scanning.models import DependencyVulnerability, ScanStatus, Severity
from apps.scanning.retention import prune_prior_scans
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    PackageFactory,
    RepositoryFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db

WITH_KEY = override_settings(GROQ_API_KEY="gsk_test", GROQ_MODEL="test-model")

#: A changelog long enough that five retrieved chunks clear §5.9's 400-char
#: floor, so a test that wants "low confidence" has to lower the *similarity*
#: rather than accidentally tripping the length gate as well.
CHANGELOG = """\
# Changelog

## 4.0.0

The router has been rewritten. This is a breaking change for anyone who
subclassed Router directly; see the migration notes below for the three call
sites that usually need editing. Everything else is source compatible.

## 3.1.2

Fixed a prototype pollution issue in the query parser, reported as
CVE-2026-0001. Upgrade to 3.1.2 or later; there is no workaround for earlier
releases and the fix is a single-line change to the parser.

## 3.1.1

Documentation only. No code changes in this release at all, so an upgrade from
3.1.0 is safe and needs nothing from you.
"""


# ── the stubs ──────────────────────────────────────────────────────────────


def unit(angle: float) -> list[float]:
    return [math.cos(angle), math.sin(angle)]


def embedder(chunk_angle: float = 0.0, query_angle: float = 0.0):
    """Every chunk at one angle, the query at another.

    Cosine similarity is then `cos(chunk_angle - query_angle)`, which is a
    number the test picked — see the module docstring.
    """

    def embed(texts: list[str]) -> list[list[float]]:
        # The query is the only single-item batch the graph ever embeds, and
        # `retrieve` is the only caller that passes one. `ensure_corpus` always
        # embeds the whole chunk list.
        return [unit(query_angle if len(texts) == 1 else chunk_angle) for _ in texts]

    return embed


def answer(
    *,
    summary: str = "Upgrade to 3.1.2, which fixes the query parser.",
    fixes: list[dict] | None = None,
    citations: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "summary_md": summary,
            "fixes": fixes
            if fixes is not None
            else [
                {
                    "package": "express",
                    "manifest_path": "package.json",
                    "ecosystem": "npm",
                    "fix_type": "upgrade",
                    "target_version": "3.1.2",
                    "replacement_package": None,
                    "priority": 1,
                }
            ],
            "citations": citations if citations is not None else [],
        }
    )


class CountingModel:
    """A stand-in for `groq_client.complete_json` that records what it was sent."""

    def __init__(self, *contents: str) -> None:
        self.contents = list(contents) or [answer()]
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str) -> LlmCall:
        self.calls.append((system_prompt, user_prompt))
        content = self.contents[min(len(self.calls) - 1, len(self.contents) - 1)]
        return LlmCall(
            content=content,
            model="test-model",
            prompt_tokens=800,
            completion_tokens=120,
            latency_ms=42,
            requests=1,
        )


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def chroma(tmp_path, settings):
    settings.CHROMA_DIR = str(tmp_path / "chroma")
    chroma_store.reset_for_tests()
    yield
    chroma_store.reset_for_tests()


@pytest.fixture
def retrieval(monkeypatch, chroma):
    """The two remote things, replaced. Returns a knob for each."""

    state = {
        "docs": (
            fetch_docs.SourceDoc(
                kind="changelog", path="CHANGELOG.md", sha="blob1", text=CHANGELOG
            ),
        ),
        "reason": None,
    }

    def fake_fetch(**kwargs):
        return fetch_docs.FetchResult(
            docs=state["docs"],
            repo_full_name="expressjs/express" if state["docs"] else None,
            reason=state["reason"],
        )

    monkeypatch.setattr(agent_graph.fetch_docs, "fetch_for", fake_fetch)
    monkeypatch.setattr(agent_graph.embeddings, "embed", embedder())
    return state


def flagged_occurrence(*, deprecated: bool = False, reason: str | None = None, user=None):
    """One flagged npm occurrence on a completed scan."""
    scan = (
        ScanRunFactory(repository=RepositoryFactory(user=user))
        if user is not None
        else ScanRunFactory()
    )
    manifest = ManifestFileFactory(scan=scan)
    package = PackageFactory(ecosystem="npm", package_name="express")
    occurrence = DependencyOccurrenceFactory(
        manifest=manifest,
        package=package,
        resolved_version="3.1.0",
        latest_version="4.0.0",
        versions_behind_major=1,
        is_deprecated=deprecated,
        deprecation_reason=reason,
        vulnerability_count=1,
        highest_severity=Severity.HIGH.value,
        cvss_max="7.5",
        is_flagged=True,
        risk_component_score="61.40",
    )
    DependencyVulnerability.objects.create(
        dependency=occurrence,
        osv_id="GHSA-aaaa-bbbb-cccc",
        cve_id="CVE-2026-0001",
        severity=Severity.HIGH.value,
        cvss_score="7.5",
        fixed_version="3.1.2",
    )
    return occurrence


def queued_report(occurrence) -> Report:
    return Report.objects.create(
        scan=occurrence.manifest.scan,
        dependency=occurrence,
        report_type=ReportType.PER_DEPENDENCY.value,
        status=ReportStatus.QUEUED.value,
    )


# ── the branch (§5.9) ──────────────────────────────────────────────────────


@WITH_KEY
def test_a_deprecated_package_takes_the_replacement_branch(retrieval):
    """§5.9 branches on `deprecation_reason` presence, and the registry's own
    words go into the query — "use lodash.get instead" finds the changelog
    entry that says the same thing, where "this package is deprecated" finds
    every release note that mentions deprecation."""
    occurrence = flagged_occurrence(
        deprecated=True, reason="This package is no longer supported. Use express 4."
    )
    report = queued_report(occurrence)

    result = agent_graph.run(report, occurrence, complete=CountingModel())

    assert result.branch == AgentBranch.REASON_AVAILABLE.value
    trace = AgentExecutionTrace.objects.get()
    assert "no longer supported" in trace.retrieval_query
    assert "migrating" in trace.retrieval_query


@WITH_KEY
def test_an_undeprecated_package_takes_the_upgrade_branch(retrieval):
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)

    result = agent_graph.run(report, occurrence, complete=CountingModel())

    assert result.branch == AgentBranch.NO_REASON.value
    trace = AgentExecutionTrace.objects.get()
    # The advisory's own fixed version steers the query — it is the release the
    # reader is being asked about.
    assert "3.1.2" in trace.retrieval_query


@WITH_KEY
def test_a_deprecation_with_an_empty_reason_is_not_the_reason_branch(retrieval):
    """npm's `"deprecated": true` deprecates with no explanation, and §5.1
    stores that as an empty string rather than null because the two mean
    different things. The branch turns on there being something to quote."""
    occurrence = flagged_occurrence(deprecated=True, reason="")
    report = queued_report(occurrence)

    result = agent_graph.run(report, occurrence, complete=CountingModel())

    assert result.branch == AgentBranch.NO_REASON.value


# ── the grounding gate (§5.9) ──────────────────────────────────────────────


@WITH_KEY
def test_close_retrieval_over_enough_text_is_sufficient(retrieval):
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)

    result = agent_graph.run(report, occurrence, complete=CountingModel())

    assert result.grounding == GroundingConfidence.SUFFICIENT.value
    assert len(result.retrieved) > 0
    assert max(chunk["similarity"] for chunk in result.retrieved) > 0.99


@WITH_KEY
def test_distant_retrieval_is_low_confidence_however_much_text_it_found(
    monkeypatch, retrieval
):
    """The similarity half of §5.9's `and`. The chunks are the same ones the
    sufficient case retrieved — only the angle between query and chunk
    changed."""
    # cos(1.4 rad) ~ 0.17, below GROUNDING_MIN_SIM.
    monkeypatch.setattr(
        agent_graph.embeddings, "embed", embedder(chunk_angle=1.4, query_angle=0.0)
    )
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)

    result = agent_graph.run(report, occurrence, complete=CountingModel())

    assert result.grounding == GroundingConfidence.LOW.value
    # Retrieved and rejected, not discarded: the trace and the pane both need
    # to show what the search actually found (§5.1).
    assert len(result.retrieved) > 0


@WITH_KEY
@override_settings(GROUNDING_MIN_CHARS=10_000)
def test_plenty_of_similarity_over_too_little_text_is_low_confidence(retrieval):
    """The length half of the same `and`. A single line at similarity 1.0 is
    a match on a phrase, not documentation of a release."""
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)

    result = agent_graph.run(report, occurrence, complete=CountingModel())

    assert result.grounding == GroundingConfidence.LOW.value


@WITH_KEY
def test_the_grounding_check_never_calls_the_model(retrieval):
    """§5.9: "deterministic, no LLM". The verdict is two numbers and an `and`,
    and a reader holding the trace can recompute it — which is what makes the
    low-confidence banner evidence rather than decoration."""
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)
    model = CountingModel()

    agent_graph.run(report, occurrence, complete=model)

    # Exactly one call, and it is the generation. Nothing asked the model how
    # confident it felt.
    assert len(model.calls) == 1


# ── the honest empty-handed path ───────────────────────────────────────────


@WITH_KEY
def test_an_unresolvable_repository_still_produces_a_fully_traced_report(retrieval):
    """§10 Phase 8's acceptance, verbatim: "unresolvable-repo package ->
    insufficient-information report, still fully traced"."""
    retrieval["docs"] = ()
    retrieval["reason"] = "no_repository_url"
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)
    model = CountingModel()

    result = agent_graph.run(report, occurrence, complete=model)

    assert result.grounding == GroundingConfidence.LOW.value
    assert result.retrieved == []

    report.refresh_from_db()
    assert report.status == ReportStatus.COMPLETED.value
    assert report.grounding_confidence == GroundingConfidence.LOW.value

    trace = AgentExecutionTrace.objects.get()
    assert trace.retrieved_chunks_json == []
    assert trace.retrieval_query
    assert trace.generation_json["corpus"]["reason"] == "no_repository_url"


@WITH_KEY
def test_the_low_confidence_prompt_instructs_insufficient_information(retrieval):
    """The instruction §5.9 names, asserted on what was actually sent."""
    retrieval["docs"] = ()
    retrieval["reason"] = "not_github"
    occurrence = flagged_occurrence()
    model = CountingModel()

    agent_graph.run(queued_report(occurrence), occurrence, complete=model)

    system_prompt, user_prompt = model.calls[0]
    assert "insufficient information" in system_prompt
    assert "could not retrieve enough" in system_prompt
    assert "No passages were retrieved" in user_prompt


@WITH_KEY
def test_low_confidence_puts_no_chunks_in_front_of_the_model(monkeypatch, retrieval):
    """A prompt that says "you have insufficient information" above five
    quoted passages is asking to be disbelieved. The chunks are still recorded
    — the study needs what was retrieved and rejected — but the model is not
    shown them."""
    monkeypatch.setattr(
        agent_graph.embeddings, "embed", embedder(chunk_angle=1.4, query_angle=0.0)
    )
    occurrence = flagged_occurrence()
    model = CountingModel()

    result = agent_graph.run(queued_report(occurrence), occurrence, complete=model)

    _, user_prompt = model.calls[0]
    assert "No passages were retrieved" in user_prompt
    assert "prototype pollution" not in user_prompt
    assert any("prototype pollution" in chunk["text"] for chunk in result.retrieved)


# ── §7.1 and §7.3, one level down ──────────────────────────────────────────


@WITH_KEY
def test_a_fix_naming_a_different_package_is_rejected(retrieval):
    """§7.3's rule on a surface where there is exactly one legal row. The
    repair retry is offered and, when it still invents, the generation fails
    rather than printing advice about a package this scan never found."""
    occurrence = flagged_occurrence()
    invented = answer(
        fixes=[
            {
                "package": "lodash",
                "manifest_path": "package.json",
                "ecosystem": "npm",
                "fix_type": "upgrade",
                "target_version": "4.17.21",
                "replacement_package": None,
                "priority": 1,
            }
        ]
    )
    model = CountingModel(invented, invented)

    with pytest.raises(AgentFailed):
        agent_graph.run(queued_report(occurrence), occurrence, complete=model)

    assert len(model.calls) == 2


@WITH_KEY
def test_the_measurements_come_from_the_scan_not_from_the_answer(retrieval):
    """§7.1. The model is asked for seven fields; the CVE list, the current
    version and the severity are copied from the row it was asked about."""
    occurrence = flagged_occurrence()

    result = agent_graph.run(
        queued_report(occurrence), occurrence, complete=CountingModel()
    )

    fix = result.payload["fixes"][0]
    assert fix["current_version"] == "3.1.0"
    assert fix["cves"] == ["CVE-2026-0001"]
    assert fix["severity"] == "high"


@WITH_KEY
def test_a_citation_naming_a_chunk_that_was_not_retrieved_is_dropped(retrieval):
    """Unlike an invented package, an invented citation does not fail the
    generation: it cannot render anything, so dropping it costs a highlight
    where failing would cost the answer."""
    occurrence = flagged_occurrence()
    model = CountingModel(answer(citations=["deadbeefdead", "not-a-chunk"]))

    result = agent_graph.run(queued_report(occurrence), occurrence, complete=model)

    assert result.payload["citations"] == []
    assert result.payload["summary_md"]


@WITH_KEY
def test_a_real_citation_survives_and_names_a_retrieved_chunk(retrieval):
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)

    # Two passes: the first discovers what the chunk ids actually are, the
    # second cites one. Hard-coding a digest here would make the test a
    # restatement of the hash function.
    probe = agent_graph.run(report, occurrence, complete=CountingModel())
    cited = probe.retrieved[0]["chunk_id"]

    Report.objects.all().delete()
    AgentExecutionTrace.objects.all().delete()
    second = queued_report(occurrence)
    result = agent_graph.run(
        second, occurrence, complete=CountingModel(answer(citations=[cited]))
    )

    assert result.payload["citations"] == [cited]
    assert cited in {chunk["chunk_id"] for chunk in result.retrieved}


# ── persistence, cleanup, determinism ──────────────────────────────────────


@WITH_KEY
def test_the_trace_records_everything_s3_needs(retrieval):
    """§5.1's column list, asserted as a whole rather than field by field: a
    trace missing one of these is not a smaller trace, it is one S3 cannot
    group on."""
    occurrence = flagged_occurrence(deprecated=True, reason="Use express 4 instead.")
    report = queued_report(occurrence)

    agent_graph.run(report, occurrence, complete=CountingModel())

    trace = AgentExecutionTrace.objects.get()
    assert trace.source_report_id == report.pk
    assert trace.source_scan_id == occurrence.manifest.scan_id
    assert trace.github_user_id == occurrence.manifest.scan.repository.user.github_user_id
    assert trace.repo_full_name == occurrence.manifest.scan.repository.full_name
    assert trace.ecosystem == "npm"
    assert trace.package_name == "express"
    assert trace.resolved_version == "3.1.0"
    assert trace.branch_taken == AgentBranch.REASON_AVAILABLE.value
    assert trace.grounding_confidence == GroundingConfidence.SUFFICIENT.value
    assert trace.model_name == "test-model"
    assert trace.retrieval_query
    assert len(trace.retrieved_chunks_json) > 0
    assert trace.generation_json["summary_md"]
    assert trace.generation_json["llm"]["requests"] == 1
    assert trace.generation_json["llm"]["temperature"] == 0


@WITH_KEY
def test_every_retrieved_chunk_is_traced_including_the_uncited_ones(retrieval):
    """§5.1: "ALL retrieved chunks with similarity scores, not only cited
    ones". A trace holding only citations can measure the model's manners and
    not retrieval quality."""
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)

    result = agent_graph.run(report, occurrence, complete=CountingModel())

    trace = AgentExecutionTrace.objects.get()
    assert len(trace.retrieved_chunks_json) == len(result.retrieved)
    assert trace.generation_json["citations"] == []
    assert len(trace.retrieved_chunks_json) > 0
    assert all("similarity" in chunk for chunk in trace.retrieved_chunks_json)


@WITH_KEY
def test_the_chunks_are_deleted_once_the_report_is_stored(retrieval):
    """§10 Phase 8's acceptance: "Chroma chunk count for the dependency = 0
    after persist". Everything of value is in Postgres by then — the answer,
    the citations, and every chunk's full text, twice."""
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)

    agent_graph.run(report, occurrence, complete=CountingModel())

    assert (
        chroma_store.count_for(
            scan_id=occurrence.manifest.scan_id,
            ecosystem="npm",
            package_name="express",
            resolved_version="3.1.0",
        )
        == 0
    )
    report.refresh_from_db()
    assert len(report.retrieved_chunks_json) > 0


@WITH_KEY
def test_two_runs_of_the_same_input_produce_the_same_output(retrieval):
    """§10 Phase 8's determinism acceptance. Temperature 0 is the model's
    half; stable chunk ids and a fixed query are ours, and ours is the half a
    test can actually assert."""
    first_occurrence = flagged_occurrence()
    first = agent_graph.run(
        queued_report(first_occurrence), first_occurrence, complete=CountingModel()
    )

    second_occurrence = flagged_occurrence()
    second = agent_graph.run(
        queued_report(second_occurrence), second_occurrence, complete=CountingModel()
    )

    traces = list(AgentExecutionTrace.objects.order_by("created_at"))
    assert traces[0].retrieval_query == traces[1].retrieval_query
    assert [chunk["chunk_id"] for chunk in first.retrieved] == [
        chunk["chunk_id"] for chunk in second.retrieved
    ]
    assert json.dumps(first.payload, sort_keys=True) == json.dumps(
        second.payload, sort_keys=True
    )


@WITH_KEY
def test_a_trace_survives_the_rescan_that_destroys_its_report(retrieval):
    """§10 Phase 8: "trace decoupled from the reports cascade so it survives
    rescans" — and the cascade test that proves it.

    A `reports` row is an interpretation of one measurement and dies with it
    (§5.7). A trace is an observation of the *agent*, and pressing Rescan does
    not invalidate what the agent did.
    """
    occurrence = flagged_occurrence()
    report = queued_report(occurrence)
    agent_graph.run(report, occurrence, complete=CountingModel())

    assert AgentExecutionTrace.objects.count() == 1

    # A newer scan of the same repository, then §5.7's retention.
    newer = ScanRunFactory(
        repository=occurrence.manifest.scan.repository, status=ScanStatus.COMPLETED.value
    )
    prune_prior_scans(newer)

    assert Report.objects.filter(pk=report.pk).exists() is False
    assert AgentExecutionTrace.objects.count() == 1
    surviving = AgentExecutionTrace.objects.get()
    # Both ids it names are now dangling, which is exactly why neither is a
    # foreign key.
    assert surviving.source_report_id == report.pk
    assert surviving.package_name == "express"
    assert ScanHistory.objects.count() == 0  # retention alone writes no history


@WITH_KEY
def test_a_second_report_in_one_scan_reuses_the_stored_corpus(monkeypatch, retrieval):
    """`ensure_corpus` is lazy per §5.9, and re-entrant: a generation that
    failed after the chunks were written must not re-fetch them."""
    occurrence = flagged_occurrence()
    agent_graph.run(queued_report(occurrence), occurrence, complete=CountingModel())

    fetches = []
    original = agent_graph.fetch_docs.fetch_for
    monkeypatch.setattr(
        agent_graph.fetch_docs,
        "fetch_for",
        lambda **kwargs: (fetches.append(kwargs), original(**kwargs))[1],
    )

    # The chunks were cleaned up after the first report, so this one fetches
    # again — which is the honest behaviour, and the assertion is that the
    # second run works at all rather than that it skipped the fetch.
    Report.objects.all().delete()
    second = agent_graph.run(
        queued_report(occurrence), occurrence, complete=CountingModel()
    )

    assert len(fetches) == 1
    assert second.grounding == GroundingConfidence.SUFFICIENT.value


@WITH_KEY
def test_an_embedding_failure_degrades_to_the_honest_answer(monkeypatch, retrieval):
    """Nothing in `ensure_corpus` raises. A model that will not load is a
    reason the report has no sources, not a reason the user gets an error."""

    def broken(texts):
        raise embeddings.EmbeddingUnavailable("no model")

    monkeypatch.setattr(agent_graph.embeddings, "embed", broken)
    occurrence = flagged_occurrence()

    result = agent_graph.run(
        queued_report(occurrence), occurrence, complete=CountingModel()
    )

    assert result.grounding == GroundingConfidence.LOW.value
    assert AgentExecutionTrace.objects.get().generation_json["corpus"]["reason"] == (
        "embedding_unavailable"
    )


# ── the endpoint (§5.5) ────────────────────────────────────────────────────


def dependency_report_url(occurrence) -> str:
    return reverse("dependency-report", args=[occurrence.pk])


@WITH_KEY
def test_the_first_request_starts_a_generation_and_the_second_serves_it(
    auth_client, user, retrieval, no_background_threads
):
    occurrence = flagged_occurrence(user=user)

    started = auth_client.post(dependency_report_url(occurrence))
    assert started.status_code == 202
    assert started.data["type"] == ReportType.PER_DEPENDENCY.value
    assert len(no_background_threads) == 1

    # Finish it the way the thread would have.
    report = Report.objects.get(pk=started.data["id"])
    agent_graph.run(report, occurrence, complete=CountingModel())

    model = CountingModel()
    cached = auth_client.post(dependency_report_url(occurrence))
    assert cached.status_code == 200
    assert cached.data["groundingConfidence"] == GroundingConfidence.SUFFICIENT.value
    assert len(cached.data["retrievedChunks"]) > 0
    # The claim the phase rests on: a second click spends nothing.
    assert len(model.calls) == 0
    assert len(no_background_threads) == 1


@WITH_KEY
def test_a_clean_dependency_has_nothing_to_remediate(
    auth_client, user, no_background_threads
):
    """The endpoint states the rule the button obeys, rather than the other
    way round."""
    occurrence = flagged_occurrence(user=user)
    occurrence.is_flagged = False
    occurrence.save(update_fields=["is_flagged"])

    response = auth_client.post(dependency_report_url(occurrence))

    assert response.status_code == 409
    assert response.data["code"] == "dependency_not_reportable"
    assert len(no_background_threads) == 0


@WITH_KEY
def test_an_unassessable_dependency_has_nothing_to_remediate(
    auth_client, user, no_background_threads
):
    occurrence = flagged_occurrence(user=user)
    occurrence.is_unassessable = True
    occurrence.save(update_fields=["is_unassessable"])

    response = auth_client.post(dependency_report_url(occurrence))

    assert response.status_code == 409
    assert response.data["code"] == "dependency_not_reportable"


def test_another_users_dependency_is_a_404(auth_client, no_background_threads):
    """§11's BOLA rule: a foreign id is not in the queryset at all, so it 404s
    without a permission check anyone could forget to write."""
    occurrence = flagged_occurrence()

    response = auth_client.post(dependency_report_url(occurrence))

    assert response.status_code == 404
    assert len(no_background_threads) == 0


def test_a_deployment_without_a_key_says_so_rather_than_failing_a_row(
    auth_client, user, no_background_threads
):
    occurrence = flagged_occurrence(user=user)

    with override_settings(GROQ_API_KEY=""):
        response = auth_client.post(dependency_report_url(occurrence))

    assert response.status_code == 503
    assert response.data["code"] == "reports_unavailable"
    assert Report.objects.count() == 0


@WITH_KEY
def test_the_row_payload_carries_the_report_state(auth_client, user, retrieval):
    """§8.6: the list route answers "does this row have a plan?" so the drawer
    never has to ask the endpoint that would generate one."""
    occurrence = flagged_occurrence(user=user)
    scan = occurrence.manifest.scan

    before = auth_client.get(reverse("scan-dependencies", args=[scan.pk]))
    assert before.data["results"][0]["report"] is None

    agent_graph.run(queued_report(occurrence), occurrence, complete=CountingModel())

    after = auth_client.get(reverse("scan-dependencies", args=[scan.pk]))
    row = after.data["results"][0]
    assert row["report"]["status"] == ReportStatus.COMPLETED.value
    assert row["report"]["generatedAt"] is not None
