"""Phase 14's audit of the frozen set: the advisories kept, and why they cannot fire.

`pip-audit -r requirements.txt` over the lock, run 2026-10-10 (decisions §14),
reports advisories against four runtime packages. None has a fix inside the
declared ranges (chromadb's have no fix at all; LangGraph's are fixed only in
later majors), and none is reachable from this code — but each "not
reachable" is a property of the code that a later change could quietly
remove, so each one is pinned here rather than asserted in prose:

* **chromadb 1.5.9** — CVE-2026-45829, -45830, -45831, -45833: the Chroma
  *server's* HTTP API (`/api/v2/...`) and its RBAC provider. RepoVitals embeds
  Chroma in-process through `PersistentClient` and never starts, exposes or
  calls a server.
* **langgraph 0.6.11, langgraph-checkpoint 3.0.1** — CVE-2026-28277, -27794,
  -48775: deserialization from a checkpointer's store or a node cache. The
  agent graph is compiled with neither (§5.9: single pass, no state kept).
* **langgraph-sdk 0.2.15** — CVE-2026-48776, GHSA-fvww-7h3r-vfhp: the LangGraph
  Platform *client*. It is installed as a dependency of langgraph and imported
  by nothing here.

A failure in this file means one of them just became reachable: upgrade
(langgraph >= 1.0.10, langgraph-checkpoint >= 4.1.1, langgraph-sdk >= 0.4.4)
in the same change, or don't make it.
"""

from __future__ import annotations

import re
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent / "apps"


def _sources() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in APPS.rglob("*.py")}


def test_the_agent_graph_keeps_no_checkpoint_cache_or_store():
    from apps.reports.agent.graph import build_graph

    compiled = build_graph()
    assert compiled.checkpointer is None
    assert compiled.cache is None
    assert compiled.store is None


def test_chroma_is_only_ever_embedded():
    server = re.compile(
        r"chromadb\.(?:HttpClient|AsyncHttpClient|CloudClient|Client)\s*\(|chromadb\.server|chromadb\.app"
    )
    found = [str(path) for path, text in _sources().items() if server.search(text)]
    assert found == []
    store = (APPS / "reports" / "rag" / "chroma_store.py").read_text(encoding="utf-8")
    assert "chromadb.PersistentClient(" in store


def test_nothing_imports_the_langgraph_platform_client():
    found = [
        str(path)
        for path, text in _sources().items()
        if re.search(r"^\s*(?:from|import)\s+langgraph_sdk\b", text, re.MULTILINE)
    ]
    assert found == []
