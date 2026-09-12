"""The per-scan vector collection, and the three disciplines §5.9 puts on it.

§5.9, verbatim: "Chroma discipline: `get_or_create_collection` (creation-race
safe); per-scan `threading.Lock` serializes chunk writes (embedded Chroma is
SQLite-backed -- limited concurrent-write support); the **resolved** version
string is used both at write-tag time and read-filter time (a manifest-range
string on one side causes silent empty retrieval -> false low-confidence)."

Each of those is a defect that has a specific shape, and all three are silent:

**The creation race.** Two dependencies of one scan, generated at the same
moment, both find no collection and both create it. `get_or_create_collection`
is the single call that cannot lose that race, which is why it is the only way
a collection is obtained here -- there is no `create_collection` in this file.

**The write lock.** Chroma's embedded persistence is SQLite, and SQLite's
concurrent-write story is a database-level lock and a busy timeout. Two threads
adding chunks to one collection is not a corruption risk so much as a
`database is locked` error surfacing as a failed report. One lock per scan
serializes the writers without serializing the readers, which is the shape the
underlying store actually wants.

**The version tag.** A row whose `resolution` is `range_latest_approx` has a
`declared_specifier` of `^4.17.0` and a `resolved_version` of `4.17.21`. Tag
the chunks with one and filter with the other and the query matches nothing --
no error, no warning, an empty result that the grounding check then reports as
low confidence. The product would say "there is not enough source material to
answer this" about a package whose changelog it had just downloaded and
embedded. `version_tag` is the single function both sides call, so the two
cannot disagree.

**And one thing §5.9 does not say, which the store has to decide: distance or
similarity?** The collection is created with `hnsw:space = cosine`, so Chroma
returns cosine *distance* and this module converts it to a similarity as
`1 - distance` before anything else sees it. `GROUNDING_MIN_SIM` is a
similarity threshold (§6: 0.30), and a comparison that accidentally read a
distance would invert it -- passing exactly the retrievals it should refuse.
The conversion happens once, here, at the boundary.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

#: Chroma requires 3-512 characters of `[a-zA-Z0-9._-]`, starting and ending
#: alphanumeric. A bare UUID hex satisfies that; the prefix makes a stray
#: directory on disk self-describing.
COLLECTION_PREFIX = "scan-"

#: §5.9's retrieval width.
DEFAULT_K = 5

_client = None
_client_lock = threading.Lock()

#: One lock per scan. Never removed, for the same reason `background._locks`
#: never removes one: an entry is a few dozen bytes, and a removal path
#: reintroduces the creation race the guard exists to close.
_write_locks: dict[str, threading.Lock] = {}
_write_locks_guard = threading.Lock()


@dataclass(frozen=True)
class Retrieved:
    """One chunk that came back from a query, with its similarity.

    `similarity` is cosine similarity in [0, 1] after the conversion described
    in the module docstring — never a distance.
    """

    chunk_id: str
    text: str
    similarity: float
    source_path: str
    source_sha: str
    source_kind: str
    heading: str
    index: int

    def as_json(self) -> dict:
        """The shape stored in `reports.retrieved_chunks_json` and the trace.

        Rounded to four decimals on the way out. The number is displayed beside
        each chunk in the citation pane and compared against a threshold with
        two decimals; carrying seventeen significant figures into permanent
        research data records the float's representation error as though it
        were a measurement.
        """
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "similarity": round(self.similarity, 4),
            "source_path": self.source_path,
            "source_sha": self.source_sha,
            "source_kind": self.source_kind,
            "heading": self.heading,
            "index": self.index,
        }


def version_tag(resolved_version: str | None) -> str:
    """The one spelling of a version this module writes and reads.

    Called by the writer and by the reader, so the two cannot drift — which is
    the entire point of §5.9's sentence about it. `None` becomes the empty
    string rather than being omitted: a metadata key that is absent on write
    and filtered on read is the same silent miss by another route, and Chroma's
    `where` cannot express "missing".
    """
    return (resolved_version or "").strip()


def collection_name(scan_id) -> str:
    return f"{COLLECTION_PREFIX}{str(scan_id).replace('-', '')}"


def _get_client():
    """The embedded persistent client, built once per process.

    Telemetry is off. Chroma's default is to post anonymous usage events to a
    third party, which would be a second outbound HTTP path with its own rules
    — exactly what `common/http.py` exists to prevent (§5.6) — and this
    project's whole posture is that nothing leaves the box except the calls
    listed in the allowlist.
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            # Imported here rather than at module scope: chromadb costs ~50 MB
            # resident on import, and a worker that never generates a
            # per-dependency report should not hold it (see the package
            # docstring).
            import chromadb
            from chromadb.config import Settings

            directory = str(getattr(settings, "CHROMA_DIR", "") or "")
            logger.info("Opening the chunk store at %s.", directory)
            _client = chromadb.PersistentClient(
                path=directory,
                settings=Settings(anonymized_telemetry=False, allow_reset=False),
            )
    return _client


def _write_lock(scan_id) -> threading.Lock:
    key = str(scan_id)
    with _write_locks_guard:
        if key not in _write_locks:
            _write_locks[key] = threading.Lock()
        return _write_locks[key]


def _collection(scan_id):
    """This scan's collection, created if it is not there yet.

    `embedding_function=None` because every vector is supplied by the caller.
    Left at its default, Chroma would instantiate its own ONNX MiniLM — a
    second embedding model in a process that already holds fastembed's, on a
    512 MB tier, silently, to embed nothing.
    """
    return _get_client().get_or_create_collection(
        name=collection_name(scan_id),
        # Cosine, so `1 - distance` is a similarity in [0, 1]. The default is
        # squared L2, which is unbounded above and would make §6's 0.30
        # threshold meaningless.
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )


def add_chunks(
    *,
    scan_id,
    ecosystem: str,
    package_name: str,
    resolved_version: str | None,
    chunks,
    vectors: list[list[float]],
) -> int:
    """Write one dependency's chunks. Returns how many were written.

    Idempotent by construction: ids are content digests (`chunker._chunk_id`),
    so re-adding a chunk that is already there is an upsert of identical data
    rather than a duplicate. That is what makes `ensure_corpus` safe to re-enter
    after a generation failed halfway.
    """
    if not chunks:
        return 0
    if len(chunks) != len(vectors):  # pragma: no cover - caller contract
        raise ValueError("Each chunk needs exactly one vector.")

    tag = version_tag(resolved_version)
    metadatas = [
        {
            "package": package_name,
            "ecosystem": ecosystem,
            "version": tag,
            "source_path": chunk.source_path,
            "source_sha": chunk.source_sha,
            "source_kind": chunk.source_kind,
            "heading": chunk.heading,
            "index": chunk.index,
        }
        for chunk in chunks
    ]

    with _write_lock(scan_id):
        _collection(scan_id).upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=metadatas,
        )
    return len(chunks)


def query(
    *,
    scan_id,
    ecosystem: str,
    package_name: str,
    resolved_version: str | None,
    vector: list[float],
    k: int = DEFAULT_K,
) -> list[Retrieved]:
    """The k nearest chunks *of this dependency*, best first.

    The filter is the whole reason a per-scan collection is workable: one
    collection holds every dependency the user generated a report for, and the
    `where` clause is what keeps `lodash`'s changelog out of an answer about
    `request`.
    """
    collection = _collection(scan_id)
    result = collection.query(
        query_embeddings=[vector],
        n_results=k,
        where=_where(ecosystem, package_name, resolved_version),
        include=["documents", "metadatas", "distances"],
    )

    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    retrieved: list[Retrieved] = []
    for position, chunk_id in enumerate(ids):
        metadata = metadatas[position] if position < len(metadatas) else {}
        metadata = metadata or {}
        distance = distances[position] if position < len(distances) else 1.0
        retrieved.append(
            Retrieved(
                chunk_id=str(chunk_id),
                text=str(documents[position] if position < len(documents) else ""),
                # Clamped: floating-point arithmetic in the index can return a
                # cosine distance a hair outside [0, 2], and a similarity of
                # 1.0000000002 printed beside a chunk reads as a bug.
                similarity=max(0.0, min(1.0, 1.0 - float(distance))),
                source_path=str(metadata.get("source_path") or ""),
                source_sha=str(metadata.get("source_sha") or ""),
                source_kind=str(metadata.get("source_kind") or ""),
                heading=str(metadata.get("heading") or ""),
                index=int(metadata.get("index") or 0),
            )
        )
    return retrieved


def count_for(
    *, scan_id, ecosystem: str, package_name: str, resolved_version: str | None
) -> int:
    """How many chunks this dependency has in the store.

    §10 Phase 8's acceptance asserts this is 0 after a report persists, so it
    is a first-class query rather than something a test reaches into Chroma to
    work out for itself.
    """
    result = _collection(scan_id).get(
        where=_where(ecosystem, package_name, resolved_version), include=[]
    )
    return len(result.get("ids") or [])


def delete_for(
    *, scan_id, ecosystem: str, package_name: str, resolved_version: str | None
) -> None:
    """§5.9's cleanup: drop this dependency's chunks once the report is stored.

    Everything of value is in Postgres by the time this runs — the answer, the
    citations, and every retrieved chunk's full text in both the report row and
    the permanent trace. What is deleted is an index that can be rebuilt from
    the same two files, and keeping it would mean a free-tier disk holding a
    vector copy of every changelog any user ever asked about.
    """
    with _write_lock(scan_id):
        _collection(scan_id).delete(
            where=_where(ecosystem, package_name, resolved_version)
        )


def drop_scan(scan_id) -> None:
    """Delete a whole scan's collection. Tolerant of it not being there.

    Phase 9's `cleanup_chroma` sweeps orphans with this; Phase 8 uses it only
    to keep the test suite from leaving collections behind.
    """
    try:
        _get_client().delete_collection(collection_name(scan_id))
    except Exception:
        logger.debug("No collection to drop for scan %s.", scan_id)


def _where(ecosystem: str, package_name: str, resolved_version: str | None) -> dict:
    """Chroma's filter for exactly one dependency at exactly one version.

    Three clauses under `$and` rather than a flat dict: Chroma reads a
    multi-key `where` as needing an explicit operator, and the explicit form is
    also the one that says out loud that all three must hold.
    """
    return {
        "$and": [
            {"package": package_name},
            {"ecosystem": ecosystem},
            {"version": version_tag(resolved_version)},
        ]
    }


def reset_for_tests() -> None:
    """Drop the cached client so a test can point `CHROMA_DIR` somewhere else."""
    global _client
    with _client_lock:
        _client = None
