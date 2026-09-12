"""The embedding model: one instance per process, loaded on first use (D7).

D7 picks fastembed over sentence-transformers for one measured reason -- torch
alone is ~700 MB installed against a 512 MB tier -- and §6 pins the model to
`all-MiniLM-L6-v2`. Everything in this module follows from those two facts.

**It is a singleton, and it is lazy.** Loading the ONNX model costs ~180 MB
resident (§1.13 measured 86.3 MB before it and 270.7 MB after) and several
seconds on a cold instance. Loading it once per request would be unaffordable;
loading it at import would make every web worker pay for a feature most
requests never touch. So it loads on the first embedding and stays, and the
process that pays is a background generation thread.

**The load is guarded by a lock.** Two generations starting at the same moment
would otherwise each build their own model and hold two copies -- ~360 MB on a
512 MB instance, which is not a slowdown but an OOM that kills the worker for
every user. The double-check inside the lock is what makes the second thread
wait for the first one's model rather than build its own.

**Its output order is its input order.** `fastembed.embed` is a generator and
the caller zips the vectors back onto the chunks by position, so the list is
materialized here rather than handed out lazily.

**And it is bounded in two ways that the 512 MB tier turned out to require.**
The first per-dependency generation on production killed the worker: Render
reported "Ran out of memory (used over 512MB)". Measuring *peak* RSS rather
than settled RSS found where it went (§8.15):

    configuration                         peak       settled
    ONNX defaults, one batch of 40       403.0 MB    374.6 MB
    arena off + one ORT thread           334.4 MB    247.0 MB
    both, plus batches of 8              266.9 MB    245.9 MB

`enable_cpu_mem_arena=False` is the larger lever and it works on both numbers:
ONNX Runtime's CPU arena reserves a block far bigger than this model needs and
then *keeps* it, which is 127 MB of the resting footprint of a worker that has
generated once. `MAX_EMBED_BATCH` is the second: embedding forty 1,200-character
chunks in one call allocates ~160 MB transiently, and a spike is as fatal as a
resident cost when a cap kills the process. Neither changes a single vector —
the same text produces the same embedding either way, so §10's determinism
acceptance is untouched.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

#: 384 for all-MiniLM-L6-v2. Asserted rather than assumed: a model swap that
#: changed the dimension would otherwise write vectors a stored collection
#: cannot index, and the failure would surface as an unrelated Chroma error.
EXPECTED_DIMENSION = 384

#: Chunks per `model.embed` call. See the module docstring for the measurements.
#: Eight rather than four because the two are within 10 MB of each other and
#: eight is half the ORT invocations; a whole changelog still fits the tier.
MAX_EMBED_BATCH = 8

_model = None
_model_lock = threading.Lock()

#: Serializes embedding across threads. Not for correctness -- ORT sessions are
#: safe to call concurrently -- but for the tier: two generations embedding at
#: once would stack their transient allocations, and the one thing this process
#: must never do is exceed 512 MB. Generation is already a background thread, so
#: the cost is latency on a second concurrent report rather than a blocked
#: request.
_embed_lock = threading.Lock()


class EmbeddingUnavailable(Exception):
    """The embedding model could not be loaded or run.

    Raised rather than returning empty vectors: a generation with no embeddings
    is not a low-confidence generation, it is a broken one, and the difference
    matters because low confidence is a *finding* this product reports.
    """


def model_name() -> str:
    return (
        getattr(settings, "EMBED_MODEL", "") or "sentence-transformers/all-MiniLM-L6-v2"
    )


def load_model():
    """The process-wide `TextEmbedding`, built on first call."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                # Imported here, not at module scope: see the package docstring.
                # `fastembed` pulls `onnxruntime`, and a web worker that never
                # generates a per-dependency report should never hold either.
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - a packaging fault
                raise EmbeddingUnavailable("fastembed is not installed.") from exc
            name = model_name()
            logger.info("Loading embedding model %s.", name)
            try:
                _model = TextEmbedding(
                    model_name=name,
                    # One intra-op thread. This process has one gunicorn worker
                    # and generation already runs off the request path, so
                    # parallelism inside a single embedding buys latency nobody
                    # is waiting on and costs a thread pool's worth of arenas.
                    threads=1,
                    # The lever that matters (§8.15). ORT's CPU arena reserves
                    # far more than this model needs and keeps it for the life
                    # of the process: 127 MB of a 512 MB tier, held by a worker
                    # that has generated once and may never generate again.
                    enable_cpu_mem_arena=False,
                )
            except Exception as exc:
                raise EmbeddingUnavailable(
                    f"The embedding model {name!r} could not be loaded."
                ) from exc
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts in bounded batches, preserving order.

    Raises `EmbeddingUnavailable`.

    **Why batches and not one call.** One call for everything is what this
    function used to do, on the reasoning that fastembed batches internally and
    a loop pays per-call overhead per chunk. That reasoning was right about
    speed and wrong about the constraint that actually binds: embedding forty
    1,200-character chunks in a single call allocated ~160 MB transiently and
    took the production worker over 512 MB (§8.15). Batching caps the spike at
    roughly 20 MB for the same total work.

    Order is preserved across batch boundaries, which is what the caller relies
    on when it zips these back onto the chunks.
    """
    if not texts:
        return []
    model = load_model()

    vectors: list[list[float]] = []
    try:
        with _embed_lock:
            for start in range(0, len(texts), MAX_EMBED_BATCH):
                window = texts[start : start + MAX_EMBED_BATCH]
                vectors.extend(
                    [float(value) for value in vector] for vector in model.embed(window)
                )
    except Exception as exc:
        raise EmbeddingUnavailable("The embedding model failed to run.") from exc

    if len(vectors) != len(texts):  # pragma: no cover - fastembed contract
        raise EmbeddingUnavailable(
            f"Embedded {len(vectors)} vectors for {len(texts)} texts."
        )
    if vectors and len(vectors[0]) != EXPECTED_DIMENSION:
        raise EmbeddingUnavailable(
            f"{model_name()} produced {len(vectors[0])}-dimensional vectors; "
            f"the store is built for {EXPECTED_DIMENSION}."
        )
    return vectors


def reset_for_tests() -> None:
    """Drop the cached model. Only the test suite has any business calling it."""
    global _model
    with _model_lock:
        _model = None
