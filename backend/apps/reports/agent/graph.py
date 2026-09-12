"""§5.9's agent graph: eight nodes, one pass, no loops, no retries.

    load_context -> ensure_corpus -> frame_query -> retrieve
                 -> assess_grounding -> generate -> persist -> cleanup

The node names are §5.9's own and are not a naming convention — they are the
specification, and the LangGraph node ids match them exactly so that a reader
holding File A can follow a trace through the code without a translation table.

**Why a linear graph rather than a branching one.** §5.9 says "single pass, no
loops, no retries" and puts the branch *inside* `frame_query`: the deprecation
decision changes the question that is asked, not the sequence of steps taken.
Modelling it as two nodes with a conditional edge would read better on a
diagram and would be a deviation from the binding spec for the sake of the
diagram. The branch is recorded in the state and stored on the trace, which is
what makes it analysable — S3 groups on `branch_taken`, not on a graph shape.

**Why cost is bounded by construction, not by a budget.** One generation is one
Groq call. There is no loop that could make it two, no retry that could make it
three, and no tool the model can ask to have run. `ensure_corpus` is lazy and
idempotent: the second report for the same dependency in the same scan finds
the chunks already there and fetches nothing. Everything expensive happens
before the model is called, which is also why a failure in retrieval degrades
to a cheaper answer rather than to no answer.

**Why `persist` comes before `cleanup`.** The chunks are deleted only after the
report and the trace are committed. If cleanup fails, the cost is a stale index
Phase 9's sweep will collect; if the order were reversed, a failure between
them would destroy the evidence for an answer that had just been given.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, TypedDict

from django.conf import settings
from django.utils import timezone

from apps.research.models import AgentBranch, AgentExecutionTrace
from apps.scanning.models import DependencyOccurrence
from apps.scoring.engine import flag_reasons
from apps.scoring.signals import signals_for, weights_for_scan

from ..llm.groq_client import LlmCall, active_model, complete_json, parse_content
from ..llm.prompts import (
    GROUNDED_SYSTEM_PROMPT,
    UNGROUNDED_SYSTEM_PROMPT,
    build_per_dependency_user_prompt,
)
from ..models import GroundingConfidence, Report, ReportStatus
from ..rag import chroma_store, chunker, embeddings, fetch_docs
from ..schema import PayloadInvalid, drop_unmatched_grounded, validate_grounded

logger = logging.getLogger(__name__)

#: Advisories carried into the prompt, worst first. The same reasoning as
#: `combined.MAX_ADVISORIES_PER_ROW`, and the same number.
MAX_ADVISORIES = 5


class AgentFailed(Exception):
    """The graph could not produce a valid §5.8 payload.

    Distinct from an `LlmError`: the model answered, and what it answered could
    not be used. `services` maps both to text a reader can act on.
    """


class AgentState(TypedDict, total=False):
    """What flows between the nodes.

    Plain values only — no ORM objects beyond the two the graph was handed, and
    nothing that would have to be serialized if a checkpointer were ever added.
    """

    report_id: Any
    occurrence: Any
    complete: Any

    target: dict
    context: dict

    corpus: dict
    branch: str
    query: str
    retrieved: list[dict]
    grounding: str
    generation: dict
    requests: int
    model_name: str
    trace_id: Any


@dataclass(frozen=True)
class AgentResult:
    """What `run` hands back to the service that started it."""

    payload: dict
    grounding: str
    branch: str
    retrieved: list[dict]
    model_name: str
    requests: int
    trace_id: Any


# ── nodes ──────────────────────────────────────────────────────────────────


def load_context(state: AgentState) -> dict:
    """Everything the scan already knows about this occurrence.

    The same discipline as `combined.build_input`: measurements only, read from
    stored signals, with one deliberate exception. `deprecation_reason` is
    upstream prose and it is included here — it is the registry's own sentence
    about why the package should not be used, it is the input the whole branch
    turns on, and §5.9 asks the framing to quote it. It is the only free text
    in TARGET, the prompt frames the block as data, and the citation pane shows
    the reader the same sentence.
    """
    occurrence: DependencyOccurrence = state["occurrence"]
    scan = occurrence.manifest.scan
    weights = weights_for_scan(scan)

    advisories = sorted(
        occurrence.vulnerabilities.all(),
        key=lambda vulnerability: (
            -float(vulnerability.cvss_score or 0),
            vulnerability.osv_id,
        ),
    )[:MAX_ADVISORIES]

    target = {
        "package": occurrence.package.package_name,
        "ecosystem": occurrence.manifest.ecosystem,
        "manifest_path": occurrence.manifest.manifest_path,
        "group": occurrence.dependency_group,
        "declared_specifier": occurrence.declared_specifier,
        "current_version": occurrence.resolved_version,
        "version_source": occurrence.resolution,
        "latest_version": occurrence.latest_version,
        "versions_behind": {
            "major": occurrence.versions_behind_major,
            "minor": occurrence.versions_behind_minor,
            "patch": occurrence.versions_behind_patch,
        },
        "deprecated": occurrence.is_deprecated,
        "advisory_count": occurrence.vulnerability_count,
        "highest_severity": occurrence.highest_severity,
        "flag_reasons": list(flag_reasons(signals_for(occurrence), weights)),
        "advisories": [
            {
                "osv_id": vulnerability.osv_id,
                "cve_id": vulnerability.cve_id,
                "severity": vulnerability.severity,
                "cvss": float(vulnerability.cvss_score)
                if vulnerability.cvss_score is not None
                else None,
                "fixed_version": vulnerability.fixed_version,
            }
            for vulnerability in advisories
        ],
    }
    if occurrence.staleness_days is not None:
        target["days_since_release"] = occurrence.staleness_days
    if occurrence.is_deprecated and occurrence.deprecation_reason is not None:
        target["deprecation_reason"] = occurrence.deprecation_reason

    # §7.13: advisories and CVEs are not one to one, so this is deduplicated at
    # the point it is built rather than wherever it is next used.
    cves = list(
        dict.fromkeys(
            vulnerability.cve_id or vulnerability.osv_id for vulnerability in advisories
        )
    )

    return {
        "target": target,
        "context": {
            "scan_id": scan.pk,
            "repository_id": scan.repository_id,
            "repo_full_name": scan.repository.full_name,
            "github_user_id": scan.repository.user.github_user_id,
            "ecosystem": occurrence.manifest.ecosystem,
            "package_name": occurrence.package.package_name,
            "resolved_version": occurrence.resolved_version,
            # The §5.8 row the generated fix is cross-checked against. A list
            # of one: this surface is about one occurrence, and a fix naming
            # any other row is the §7.3 failure.
            "rows": [
                {
                    "package": occurrence.package.package_name,
                    "ecosystem": occurrence.manifest.ecosystem,
                    "manifest_path": occurrence.manifest.manifest_path,
                    "current_version": occurrence.resolved_version,
                    "highest_severity": occurrence.highest_severity,
                    "cves": cves,
                }
            ],
        },
    }


def ensure_corpus(state: AgentState) -> dict:
    """Fetch, chunk and embed this dependency's documentation — once.

    §5.9: "lazy: fetch changelog/README, chunk, embed into per-scan Chroma
    collection on this dependency's first request only". The laziness is not an
    optimisation, it is what keeps the store's size proportional to what people
    actually asked about rather than to what was scanned.

    Every failure here is a *result*. A package with no repository, a
    repository that 404s, an embedding model that will not load — all of them
    leave `chunks: 0` and a reason, and the graph carries on to an answer that
    says so. Nothing in this node raises.
    """
    context = state["context"]
    token = _token_for(state["occurrence"])

    try:
        existing = chroma_store.count_for(
            scan_id=context["scan_id"],
            ecosystem=context["ecosystem"],
            package_name=context["package_name"],
            resolved_version=context["resolved_version"],
        )
    except Exception:
        logger.exception("The chunk store could not be read.")
        return {"corpus": {"chunks": 0, "reason": "store_unavailable", "sources": []}}

    if existing:
        # A previous request for this dependency in this scan already built the
        # corpus and failed after `ensure_corpus` — or two requests raced. The
        # chunks are content-addressed, so what is there is what would be
        # written again.
        logger.info(
            "Reusing %d stored chunk(s) for %s.", existing, context["package_name"]
        )
        return {
            "corpus": {"chunks": existing, "reason": None, "sources": [], "reused": True}
        }

    fetched = fetch_docs.fetch_for(
        ecosystem=context["ecosystem"],
        package_name=context["package_name"],
        token=token,
    )
    if not fetched.found:
        logger.info(
            "No documentation retrieved for %s: %s",
            context["package_name"],
            fetched.reason,
        )
        return {
            "corpus": {
                "chunks": 0,
                "reason": fetched.reason,
                "sources": [],
                "repo_full_name": fetched.repo_full_name,
            }
        }

    chunks = []
    for document in fetched.docs:
        chunks.extend(
            chunker.chunk_document(
                document.text,
                source_path=document.path,
                source_sha=document.sha,
                source_kind=document.kind,
            )
        )

    if not chunks:
        return {
            "corpus": {
                "chunks": 0,
                "reason": "no_documents",
                "sources": [],
                "repo_full_name": fetched.repo_full_name,
            }
        }

    try:
        vectors = embeddings.embed([chunk.text for chunk in chunks])
        written = chroma_store.add_chunks(
            scan_id=context["scan_id"],
            ecosystem=context["ecosystem"],
            package_name=context["package_name"],
            resolved_version=context["resolved_version"],
            chunks=chunks,
            vectors=vectors,
        )
    except embeddings.EmbeddingUnavailable:
        logger.exception("Embedding failed; answering from signals alone.")
        return {"corpus": {"chunks": 0, "reason": "embedding_unavailable", "sources": []}}
    except Exception:
        logger.exception("Writing chunks failed; answering from signals alone.")
        return {"corpus": {"chunks": 0, "reason": "store_unavailable", "sources": []}}

    return {
        "corpus": {
            "chunks": written,
            "reason": None,
            "repo_full_name": fetched.repo_full_name,
            "sources": [
                {"path": document.path, "sha": document.sha, "kind": document.kind}
                for document in fetched.docs
            ],
        }
    }


def frame_query(state: AgentState) -> dict:
    """The question retrieval is run with, and §5.9's branch.

    "branch on `deprecation_reason` presence: replacement/migration framing
    quoting the reason, vs upgrade/breaking-changes framing; branch recorded".

    The reason is quoted into the query rather than summarized, because the
    retrieval is a similarity search and the registry's own wording is the best
    available description of what to look for: "use lodash.get instead" finds
    the changelog entry that says the same thing, where "this package is
    deprecated" finds every release note that mentions deprecation.
    """
    target = state["target"]
    reason = (target.get("deprecation_reason") or "").strip()

    if reason:
        branch = AgentBranch.REASON_AVAILABLE.value
        query = (
            f"{target['package']} is deprecated: {reason}. "
            "What replaces it, and what does migrating involve?"
        )
    else:
        branch = AgentBranch.NO_REASON.value
        fixed = _first_fixed_version(target)
        if fixed:
            query = (
                f"{target['package']} security fix in version {fixed}: "
                "what changed, and what breaks when upgrading to it?"
            )
        else:
            query = (
                f"{target['package']} upgrading from "
                f"{target.get('current_version') or 'an older release'} to "
                f"{target.get('latest_version') or 'the latest release'}: "
                "breaking changes and migration notes."
            )

    # Truncated for the same reason the chunks are: a deprecation message can
    # be a paragraph, and a query far longer than a chunk embeds to something
    # that matches nothing in particular.
    return {"branch": branch, "query": query[:600]}


def retrieve(state: AgentState) -> dict:
    """§5.9's `k=5`, filtered to this dependency at this resolved version.

    The filter lives in `chroma_store`; what matters here is that the same
    `resolved_version` that tagged the chunks is the one passed back in. Both
    sides read it from `context`, which is the single source §5.9 asks for.
    """
    context = state["context"]
    if not state.get("corpus", {}).get("chunks"):
        return {"retrieved": []}

    try:
        vector = embeddings.embed([state["query"]])[0]
        found = chroma_store.query(
            scan_id=context["scan_id"],
            ecosystem=context["ecosystem"],
            package_name=context["package_name"],
            resolved_version=context["resolved_version"],
            vector=vector,
            k=chroma_store.DEFAULT_K,
        )
    except Exception:
        logger.exception("Retrieval failed; answering from signals alone.")
        return {"retrieved": []}

    return {"retrieved": [chunk.as_json() for chunk in found]}


def assess_grounding(state: AgentState) -> dict:
    """§5.9's gate, and there is no model anywhere in it.

    "deterministic, no LLM: top-1 similarity >= GROUNDING_MIN_SIM=0.30 AND
    total retrieved chars >= GROUNDING_MIN_CHARS=400".

    Deterministic because it is the claim the product makes about itself. A
    model asked "are you confident?" answers with the same fluency it answers
    everything else, and a confidence flag produced that way would be a
    generated sentence wearing a boolean's clothes. Two numbers and an `and`
    can be recomputed from the stored trace by anyone who doubts them, which is
    what makes the low-confidence banner evidence rather than decoration.
    """
    retrieved = state.get("retrieved") or []
    if not retrieved:
        return {"grounding": GroundingConfidence.LOW.value}

    top_similarity = max(float(chunk.get("similarity") or 0.0) for chunk in retrieved)
    total_chars = sum(len(str(chunk.get("text") or "")) for chunk in retrieved)

    sufficient = top_similarity >= float(
        getattr(settings, "GROUNDING_MIN_SIM", 0.30)
    ) and total_chars >= int(getattr(settings, "GROUNDING_MIN_CHARS", 400))

    logger.info(
        "Grounding for %s: top similarity %.4f over %d chars -> %s",
        state["context"]["package_name"],
        top_similarity,
        total_chars,
        "sufficient" if sufficient else "low",
    )
    return {
        "grounding": (
            GroundingConfidence.SUFFICIENT.value
            if sufficient
            else GroundingConfidence.LOW.value
        )
    }


def generate(state: AgentState) -> dict:
    """Exactly one Groq call, temperature 0 (§5.9).

    The low-confidence path still calls the model, and that is deliberate. The
    scan has measured real things about this dependency — advisories, a fixed
    version, a deprecation flag — and a page that refused to say any of them
    because a changelog could not be found would be withholding information it
    has. What changes is what the model is permitted to claim: the ungrounded
    system prompt allows it to restate measurements and forbids it to describe
    anything it has not been shown. §5.9's "state insufficient information
    rather than guess" is an instruction about the *content*, not an
    instruction to skip the call.

    One repair retry, exactly as COMBINED has (§10 Phase 7), and for the same
    reason: a schema violation is usually a formatting slip, and a second
    request is far cheaper than a failed report.
    """
    complete = state.get("complete") or complete_json
    grounded = state["grounding"] == GroundingConfidence.SUFFICIENT.value
    system_prompt = GROUNDED_SYSTEM_PROMPT if grounded else UNGROUNDED_SYSTEM_PROMPT

    retrieved = state.get("retrieved") or []
    # Only what cleared the bar is shown as citable source. On the low path the
    # chunks are still recorded in the trace — the study needs to know what was
    # retrieved and rejected — but they are not put in front of the model,
    # because a prompt that says "you have insufficient information" above five
    # quoted passages is asking to be disbelieved.
    prompt_chunks = retrieved if grounded else []
    chunk_ids = [str(chunk.get("chunk_id")) for chunk in prompt_chunks]

    user_prompt = build_per_dependency_user_prompt(
        target=state["target"],
        chunks=prompt_chunks,
        query=state["query"],
        branch=state["branch"],
    )

    rows = state["context"]["rows"]

    first: LlmCall = complete(system_prompt, user_prompt)
    requests = first.requests
    try:
        payload = validate_grounded(parse_content(first.content), rows, chunk_ids)
        return _generation(state, payload, first, requests)
    except PayloadInvalid as invalid:
        logger.info(
            "Per-dependency report for %s needs a repair: %s",
            state["context"]["package_name"],
            invalid,
        )
        repair_reason = invalid.detail

    second: LlmCall = complete(
        system_prompt,
        f"{user_prompt}\n{repair_reason}\n"
        "Answer again with a corrected JSON object. Same schema, same rules.",
    )
    requests += second.requests

    try:
        payload = drop_unmatched_grounded(parse_content(second.content), rows, chunk_ids)
    except PayloadInvalid as invalid:
        raise AgentFailed(str(invalid)) from invalid

    if not payload["fixes"]:
        # §7.3, one level down: a summary above an empty fixes list, on a
        # dependency the scan flagged, reads as "nothing to do here" about
        # something that has something to do.
        raise AgentFailed(
            "The generated report named no dependency this scan actually found."
        )

    return _generation(state, payload, second, requests)


def persist(state: AgentState) -> dict:
    """The report row and the permanent trace, in that order.

    §5.9's node, and §10 Phase 8's commit: "report + permanent trace
    persistence". The report is what the user reads and dies with its scan; the
    trace is what S3 reads and outlives everything. Writing both here rather
    than back in `services` is what makes "fully traced" true of the honest
    empty-handed path as well as the good one — a report that says it could not
    find anything is exactly as much of an observation as one that could.
    """
    context = state["context"]
    payload = state["generation"]
    retrieved = state.get("retrieved") or []

    report = Report.objects.get(pk=state["report_id"])
    report.status = ReportStatus.COMPLETED.value
    report.summary_text = payload["summary_md"]
    report.fixes_json = payload["fixes"]
    report.citations_json = payload.get("citations") or []
    report.retrieved_chunks_json = retrieved
    report.grounding_confidence = state["grounding"]
    report.model_name = state.get("model_name") or active_model()
    report.error_message = None
    report.generated_at = timezone.now()
    report.save(
        update_fields=[
            "status",
            "summary_text",
            "fixes_json",
            "citations_json",
            "retrieved_chunks_json",
            "grounding_confidence",
            "model_name",
            "error_message",
            "generated_at",
            "updated_at",
        ]
    )

    trace = AgentExecutionTrace.objects.create(
        source_report_id=report.pk,
        source_scan_id=context["scan_id"],
        github_user_id=context["github_user_id"],
        repo_full_name=context["repo_full_name"],
        ecosystem=context["ecosystem"],
        package_name=context["package_name"],
        resolved_version=context["resolved_version"],
        branch_taken=state["branch"],
        retrieval_query=state["query"],
        # Everything retrieved, cited or not (§5.1) — including on the low path,
        # where what was retrieved and rejected is the measurement.
        retrieved_chunks_json=retrieved,
        generation_json={
            "summary_md": payload["summary_md"],
            "fixes": payload["fixes"],
            "citations": payload.get("citations") or [],
            "prompt": {
                "system": "grounded"
                if state["grounding"] == GroundingConfidence.SUFFICIENT.value
                else "ungrounded",
                "query": state["query"],
                "branch": state["branch"],
                "chunks_offered": len(retrieved),
            },
            "corpus": state.get("corpus") or {},
            "llm": {
                "model": state.get("model_name") or active_model(),
                "requests": state.get("requests", 0),
                "temperature": 0,
            },
        },
        grounding_confidence=state["grounding"],
        model_name=state.get("model_name") or active_model(),
    )
    return {"trace_id": trace.pk}


def cleanup(state: AgentState) -> dict:
    """§5.9's last node: delete this dependency's chunks.

    "everything of value now lives in Postgres" — the answer, the citations,
    and the full text of every retrieved chunk, in two tables, one of which is
    never deleted by anything. What goes is an index rebuildable from two files.

    Failure here is logged and swallowed. The report is already committed, and
    turning a successful generation into a failed one because a vector index
    would not drop a row would be the tail wagging the dog; Phase 9's
    `cleanup_chroma` sweeps what this misses.
    """
    context = state["context"]
    try:
        chroma_store.delete_for(
            scan_id=context["scan_id"],
            ecosystem=context["ecosystem"],
            package_name=context["package_name"],
            resolved_version=context["resolved_version"],
        )
    except Exception:
        logger.exception("Could not clean up chunks after persisting a report.")
    return {}


# ── assembly ───────────────────────────────────────────────────────────────


def build_graph():
    """§5.9's sequence, compiled. Built per call — it is microseconds.

    Not cached at module scope on purpose: a compiled graph held in a module
    global is one more thing that survives a code reload in a way the code it
    was compiled from did not, and this one is cheap enough that the cache
    would be the only risk either way.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)
    for name, node in (
        ("load_context", load_context),
        ("ensure_corpus", ensure_corpus),
        ("frame_query", frame_query),
        ("retrieve", retrieve),
        ("assess_grounding", assess_grounding),
        ("generate", generate),
        ("persist", persist),
        ("cleanup", cleanup),
    ):
        graph.add_node(name, node)

    order = [
        "load_context",
        "ensure_corpus",
        "frame_query",
        "retrieve",
        "assess_grounding",
        "generate",
        "persist",
        "cleanup",
    ]
    graph.add_edge(START, order[0])
    for source, destination in pairwise(order):
        graph.add_edge(source, destination)
    graph.add_edge(order[-1], END)
    return graph.compile()


def run(
    report: Report, occurrence: DependencyOccurrence, *, complete=None
) -> AgentResult:
    """One pass of §5.9's graph for one flagged dependency.

    `complete` is injectable for the same reason `combined.generate`'s is, and
    resolved at call time rather than in the signature — a default argument
    binds the function object at import, so patching the module attribute would
    not reach a caller that omitted it, which is every production caller
    (`docs/decisions.md` §7.11).
    """
    final = build_graph().invoke(
        {
            "report_id": report.pk,
            "occurrence": occurrence,
            "complete": complete or complete_json,
        }
    )
    return AgentResult(
        payload=final["generation"],
        grounding=final["grounding"],
        branch=final["branch"],
        retrieved=final.get("retrieved") or [],
        model_name=final.get("model_name") or active_model(),
        requests=final.get("requests", 0),
        trace_id=final.get("trace_id"),
    )


# ── helpers ────────────────────────────────────────────────────────────────


def _generation(state: AgentState, payload: dict, call: LlmCall, requests: int) -> dict:
    return {
        "generation": payload,
        "model_name": call.model,
        "requests": requests,
        # `corpus` is echoed back untouched so the trace's account of what was
        # fetched survives into `persist` whatever path the generation took.
        "corpus": state.get("corpus") or {},
    }


def _first_fixed_version(target: dict) -> str | None:
    """The fixed version of the worst advisory, when OSV named one.

    Worst first is already the order `load_context` built, so this is the
    advisory driving the severity the reader is looking at — which is the one a
    query about "what fixed it" should be about.
    """
    for advisory in target.get("advisories") or []:
        fixed = advisory.get("fixed_version")
        if fixed:
            return str(fixed)
    return None


def _token_for(occurrence: DependencyOccurrence) -> str:
    """The GitHub token retrieval reads with.

    The repository owner's own, exactly as a scan uses (§5.6): the documents
    fetched are public in every realistic case, but an unauthenticated GitHub
    request is rate-limited at 60/hour per IP, which on a shared free-tier
    address is no budget at all. An expired token is not fatal here — the
    fetch fails, the corpus is empty, and the report says so.
    """
    try:
        return occurrence.manifest.scan.triggered_by.get_github_token() or ""
    except Exception:
        logger.info("No usable GitHub token for a retrieval fetch.")
        return ""
