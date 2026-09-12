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

_model = None
_model_lock = threading.Lock()


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
                _model = TextEmbedding(model_name=name)
            except Exception as exc:
                raise EmbeddingUnavailable(
                    f"The embedding model {name!r} could not be loaded."
                ) from exc
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch, preserving order. Raises `EmbeddingUnavailable`.

    One call for the whole batch: fastembed batches internally, and a loop of
    single embeddings pays the per-call overhead once per chunk for no benefit.
    """
    if not texts:
        return []
    model = load_model()
    try:
        vectors = [[float(value) for value in vector] for vector in model.embed(texts)]
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
