"""The production graph's components, driven for one experiment item.

§10 Phase 13: "The runner drives the same graph components against experiment
items without any operational scan — Chroma collection keyed by run id, context
built from `labelled_set` signals, so corpus items don't need product
registrations."

`graph.run` needs a `Report` row and a `DependencyOccurrence` with a scan, a
repository and a user behind it, and it writes a report and a trace. None of
that exists for a corpus item, and creating it would be writing operational
rows from a research command — exactly what D10 forbids. So this module calls
the graph's *components* in the graph's order with a state built from the
item, and stops before `persist`:

    framing   conditions.frame       -> graph.frame_query for C and D
    corpus    fetch_docs.fetch_for   -> chunker.chunk_document -> embeddings.embed
              -> chroma_store.add_chunks          (the item's documents, once)
    retrieve  embeddings.embed(query) -> chroma_store.query(k=5)
    gate      conditions.grounding_for -> graph.assess_grounding for C and D
    generate  graph.generate          (one call, temp 0, one repair retry)
    cleanup   chroma_store.delete_for

`ensure_corpus` and `retrieve` are not called directly because both read the
occurrence's scan and token; their bodies are re-sequenced here with the same
module functions, through the module attributes so the tests' stubs reach them
(§7.11). Chunks are written to a collection named for the *run*, tagged with
the item's resolved version exactly as §5.9 requires, and deleted after the
item, so the store holds one item's chunks at a time.

**Documents are cached across conditions.** WP-8 runs one condition at a time,
days apart (File B), and a changelog can change in between. A paired design
needs B, C and D to retrieve over the *same* text, so the first fetch of a
package's documents is written to `runs/_docs/` and every later condition reads
that copy. The cache file is the record of exactly what each condition saw.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from apps.reports.agent import graph
from apps.reports.rag import chroma_store, chunker, embeddings, fetch_docs
from apps.research import issue_search

from . import conditions as conditions_module
from .conditions import Condition

logger = logging.getLogger(__name__)

DOCS_DIRNAME = "_docs"

STATUS_OK = "ok"
STATUS_FAILED = "failed"


def run_uuid(run_id: str) -> uuid.UUID:
    """The Chroma collection key for a run: stable, so a resume reuses it."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"repovitals:s3-run:{run_id}")


# ── the shared document cache ──────────────────────────────────────────────


@dataclass
class DocsCache:
    """One JSON file per (ecosystem, package) — and per repository for issues."""

    directory: Path

    def _path(self, kind: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return self.directory / DOCS_DIRNAME / kind / f"{digest}.json"

    def get(self, kind: str, key: str) -> dict | None:
        path = self._path(kind, key)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def put(self, kind: str, key: str, payload: dict) -> None:
        path = self._path(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"key": key, **payload}), encoding="utf-8")
        temporary.replace(path)  # never a half-written cache file


def _doc_json(doc: fetch_docs.SourceDoc) -> dict:
    return {"kind": doc.kind, "path": doc.path, "sha": doc.sha, "text": doc.text}


def _doc_from(data: dict) -> fetch_docs.SourceDoc:
    return fetch_docs.SourceDoc(
        kind=str(data["kind"]),
        path=str(data["path"]),
        sha=str(data["sha"]),
        text=str(data["text"]),
    )


def changelog_documents(
    item: dict, *, token: str, cache: DocsCache
) -> tuple[list[fetch_docs.SourceDoc], dict]:
    """The package's changelog or README, from the cache or through `fetch_docs`."""
    key = f"{item['ecosystem']}:{item['package']}"
    cached = cache.get("changelog", key)
    if cached is None:
        found = fetch_docs.fetch_for(
            ecosystem=item["ecosystem"], package_name=item["package"], token=token
        )
        cached = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "reason": found.reason,
            "repo_full_name": found.repo_full_name,
            "source_url": found.source_url,
            "docs": [_doc_json(doc) for doc in found.docs],
        }
        cache.put("changelog", key, cached)
    return [_doc_from(entry) for entry in cached["docs"]], cached


def issue_documents(
    repo_full_name: str | None, *, client, cache: DocsCache
) -> tuple[list[fetch_docs.SourceDoc], dict]:
    """Condition D's issues for the package's repository, cached the same way."""
    if not repo_full_name:
        return [], {"reason": "no_repository", "docs": []}
    cached = cache.get("issues", repo_full_name)
    if cached is None:
        docs = (
            issue_search.fetch_issues(client, repo_full_name)
            if client is not None
            else []
        )
        cached = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "reason": None if docs else "no_issues",
            "docs": [_doc_json(doc) for doc in docs],
        }
        cache.put("issues", repo_full_name, cached)
    return [_doc_from(entry) for entry in cached["docs"]], cached


# ── one item ───────────────────────────────────────────────────────────────


@dataclass
class ItemResult:
    item_id: str
    condition: str
    ecosystem: str
    case_type: str
    status: str
    branch: str = ""
    query: str = ""
    grounding: str = ""
    retrieved: list = field(default_factory=list)
    #: The chunk ids the generation was shown (empty on the low path and for A).
    shown_chunk_ids: list = field(default_factory=list)
    generation: dict = field(default_factory=dict)
    model: str = ""
    requests: int = 0
    corpus: dict = field(default_factory=dict)
    timings_ms: dict = field(default_factory=dict)
    error: str | None = None
    finished_at: str = ""

    def as_json(self) -> dict:
        return asdict(self)


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def run_item(
    item: dict,
    condition: Condition,
    *,
    run_id: str,
    complete,
    cache: DocsCache,
    token: str = "",
    issue_client=None,
) -> ItemResult:
    """One condition over one item. Raises `LlmError` for the runner to judge.

    A payload the model cannot be made to produce validly (`AgentFailed`, after
    the one repair retry) is a result — this pipeline failed on this item —
    and is returned as `failed`. A provider that does not answer is not a fact
    about the item, so it propagates and the runner decides whether to stop.
    """
    target = item["target"]
    collection = run_uuid(run_id)
    context = {
        "scan_id": collection,
        "ecosystem": item["ecosystem"],
        "package_name": item["package"],
        "resolved_version": target.get("current_version"),
        "rows": item["context_rows"],
    }
    result = ItemResult(
        item_id=item["item_id"],
        condition=condition.name,
        ecosystem=item["ecosystem"],
        case_type=item["case_type"],
        status=STATUS_FAILED,
    )
    branch, query = conditions_module.frame(condition, target)
    result.branch, result.query = branch, query

    retrieved: list[dict] = []
    corpus: dict = {"chunks": 0, "sources": [], "reason": "no_retrieval"}
    if condition.retrieval:
        started = time.monotonic()
        docs, changelog = changelog_documents(item, token=token, cache=cache)
        corpus = {
            "reason": changelog["reason"],
            "repo_full_name": changelog["repo_full_name"],
            "fetched_at": changelog["fetched_at"],
            "sources": [{"kind": d.kind, "path": d.path, "sha": d.sha} for d in docs],
        }
        if conditions_module.ISSUES in condition.sources:
            issues, found = issue_documents(
                changelog["repo_full_name"], client=issue_client, cache=cache
            )
            docs = [*docs, *issues]
            corpus["issues"] = {"count": len(issues), "reason": found["reason"]}
            corpus["sources"] += [
                {"kind": d.kind, "path": d.path, "sha": d.sha} for d in issues
            ]
        result.timings_ms["fetch"] = _elapsed(started)

        chunks = []
        for doc in docs:
            chunks.extend(
                chunker.chunk_document(
                    doc.text,
                    source_path=doc.path,
                    source_sha=doc.sha,
                    source_kind=doc.kind,
                )
            )
        corpus["chunks"] = len(chunks)
        started = time.monotonic()
        try:
            if chunks:
                chroma_store.add_chunks(
                    scan_id=collection,
                    ecosystem=item["ecosystem"],
                    package_name=item["package"],
                    resolved_version=context["resolved_version"],
                    chunks=chunks,
                    vectors=embeddings.embed([chunk.text for chunk in chunks]),
                )
                found_chunks = chroma_store.query(
                    scan_id=collection,
                    ecosystem=item["ecosystem"],
                    package_name=item["package"],
                    resolved_version=context["resolved_version"],
                    vector=embeddings.embed([query])[0],
                    k=chroma_store.DEFAULT_K,
                )
                retrieved = [chunk.as_json() for chunk in found_chunks]
        except embeddings.EmbeddingUnavailable:
            logger.exception(
                "Embedding failed for one item; it is answered without passages."
            )
            corpus["reason"] = "embedding_unavailable"
        finally:
            if chunks:
                try:
                    chroma_store.delete_for(
                        scan_id=collection,
                        ecosystem=item["ecosystem"],
                        package_name=item["package"],
                        resolved_version=context["resolved_version"],
                    )
                except Exception:
                    logger.exception(
                        "Could not clear one item's chunks; the next resume will."
                    )
        result.timings_ms["retrieve"] = _elapsed(started)

    state = {
        "target": target,
        "context": context,
        "retrieved": retrieved,
        "query": query,
        "branch": branch,
        "complete": complete,
        "corpus": corpus,
    }
    state["grounding"] = conditions_module.grounding_for(condition, state)
    result.grounding = state["grounding"]
    result.retrieved = retrieved
    result.corpus = corpus
    # `graph.generate` shows the passages only on the grounded path; record
    # exactly which ones the model saw, because faithfulness is judged
    # against those and nothing else.
    shown = retrieved if state["grounding"] == "sufficient" else []
    result.shown_chunk_ids = [str(chunk.get("chunk_id")) for chunk in shown]

    started = time.monotonic()
    try:
        generated = graph.generate(state)
    except graph.AgentFailed as exc:
        result.error = str(exc)
        result.timings_ms["generate"] = _elapsed(started)
        result.finished_at = datetime.now(UTC).isoformat()
        return result
    result.timings_ms["generate"] = _elapsed(started)
    result.generation = generated["generation"]
    result.model = generated.get("model_name") or ""
    result.requests = generated.get("requests", 0)
    result.status = STATUS_OK
    result.finished_at = datetime.now(UTC).isoformat()
    return result
