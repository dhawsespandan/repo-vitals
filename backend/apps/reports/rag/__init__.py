"""Retrieval for the PER_DEPENDENCY agent (§5.9).

Four modules, in the order the graph uses them:

* `fetch_docs` — package name to changelog or README text, with the source
  reference (path + blob sha) recorded for every document.
* `chunker` — heading-aware windows with stable ids.
* `embeddings` — the fastembed singleton (D7).
* `chroma_store` — the per-scan collection, its write lock, and the cleanup
  that empties it again.

**Everything here imports its heavy dependency lazily.** `fastembed`,
`onnxruntime` and `chromadb` together cost roughly 230 MB resident once loaded
(§8.9), against a 512 MB tier that also has to hold Django, a connection pool
and the scan threads. A web worker that has never generated a per-dependency
report must not be paying for them, and the request path that does pay is a
background thread. So the imports sit inside the functions that need them, and
the module-level import graph stays cheap.
"""
