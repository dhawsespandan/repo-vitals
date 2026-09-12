"""`manage.py smoke_memory` — the Phase 1 feasibility answer.

RepoVitals must fit a 512 MB Render instance while holding, in one process:
Django + DRF, a Postgres connection pool, background scan threads, and — from
Phase 8 — a fastembed ONNX embedding model, an embedded Chroma store and the
LangGraph runtime. The embedding model was the genuine risk (D7: torch alone
would be ~700 MB installed), and it was far cheaper to find out in week one
than in week twenty. So this command ran in Phase 1, before any of the
machinery that depends on the answer existed.

§10 Phase 8's last commit re-runs it "with chroma + fastembed loaded", which is
why steps 5 and 6 exist: the Phase 1 number was a floor, not a forecast, and
the two libraries Phase 8 adds are not free.

It reproduces the shape of the production worker rather than a synthetic
benchmark:

  1. baseline RSS after Django is fully loaded,
  2. an authenticated request cycle against the session endpoint,
  3. a background thread doing an outbound registry fetch with its own
     database connection, closed on the way out — the exact hygiene every
     Phase 3+ scan thread will need,
  4. one fastembed embedding, which is where the memory actually goes,
  5. the LangGraph runtime, imported and a graph compiled,
  6. an embedded Chroma collection written to and queried.

The last three are what a *generation thread* holds. A web worker that has
never produced a per-dependency report holds none of them — every one of those
imports is inside the function that needs it (§8.9) — so the peak here is the
worst case rather than the resting state.

Record the peak into `docs/decisions.md` (Phase 1 acceptance, re-recorded in
Phase 8). On Render, read the same number from the service's logs after
triggering this via a shell.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request

from django.core.management.base import BaseCommand
from django.db import connection


def _rss_mb() -> float:
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a hard requirement
        return -1.0
    return psutil.Process().memory_info().rss / (1024 * 1024)


class _SmokeChunk:
    """The three attributes `chroma_store.add_chunks` reads off a chunk.

    A local stand-in rather than `rag.chunker.Chunk`, so this command measures
    the store without pulling the chunker's module graph into the process — the
    point of the measurement is the two heavy libraries, and anything else
    imported here inflates the number with something production would not hold.
    """

    def __init__(self, chunk_id: str, text: str, index: int) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.index = index
        self.heading = "## 1.0.0"
        self.source_path = "CHANGELOG.md"
        self.source_sha = "smoke"
        self.source_kind = "changelog"


class Command(BaseCommand):
    help = (
        "Measure worker RSS through a representative request + background-thread cycle."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--skip-embedding",
            action="store_true",
            help="Skip the fastembed step (useful offline; the number is then not comparable).",
        )
        parser.add_argument(
            "--embed-model",
            default="sentence-transformers/all-MiniLM-L6-v2",
            help="fastembed model id (D7 pins all-MiniLM-L6-v2).",
        )
        parser.add_argument(
            "--skip-agent",
            action="store_true",
            help="Skip the Phase 8 langgraph + chroma steps.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the measurements as JSON for pasting into docs/decisions.md.",
        )

    def handle(self, *args, **options) -> None:
        marks: dict[str, float] = {}

        def mark(label: str) -> None:
            marks[label] = round(_rss_mb(), 1)
            self.stdout.write(f"  {label:<28} {marks[label]:>8.1f} MB")

        self.stdout.write(self.style.MIGRATE_HEADING("RepoVitals memory smoke test"))
        mark("baseline (django loaded)")

        # ── 1. Database round-trip on the main thread ──────────────────────
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        mark("after db round-trip")

        # ── 2. A request cycle through the real stack ──────────────────────
        from django.conf import settings
        from django.test import Client

        # Django's test client defaults to Host: testserver, which prod's
        # strict ALLOWED_HOSTS correctly rejects with a 400 before the view
        # ever runs — that would silently turn this into a no-op on a real
        # deploy. Use whatever host prod actually accepts instead.
        host = next((h for h in settings.ALLOWED_HOSTS if h and h != "*"), "testserver")
        server_name = host.lstrip(".") or "testserver"

        client = Client(SERVER_NAME=server_name)
        response = client.get("/api/auth/session/")
        self.stdout.write(f"  session endpoint -> HTTP {response.status_code}")
        mark("after request cycle")

        # ── 3. A background thread shaped like a Phase 3 scan worker ───────
        errors: list[str] = []

        def worker() -> None:
            try:
                request = urllib.request.Request(
                    "https://registry.npmjs.org/left-pad",
                    headers={"User-Agent": "repovitals-smoke-test"},
                )
                # Hard-coded https URL, no user input: the schemes this rule
                # guards against cannot reach it.
                with urllib.request.urlopen(request, timeout=20) as fh:  # noqa: S310
                    payload = json.loads(fh.read().decode("utf-8"))
                self.stdout.write(
                    f"  registry fetch -> left-pad@{payload.get('dist-tags', {}).get('latest')}"
                )
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                # Every background thread owns its connection and must return
                # it; leaking one per scan would exhaust Supabase's pooler.
                connection.close()

        thread = threading.Thread(target=worker, name="smoke-scan", daemon=True)
        thread.start()
        thread.join(timeout=60)
        for error in errors:
            self.stdout.write(self.style.WARNING(f"  thread error: {error}"))
        mark("after background thread")

        # ── 4. The expensive part: one embedding (D7) ──────────────────────
        if options["skip_embedding"]:
            self.stdout.write(self.style.WARNING("  embedding step skipped"))
        else:
            try:
                from fastembed import TextEmbedding

                started = time.monotonic()
                # D7 pins the model; keep the smoke test on the same one so
                # the number measured here is the number Phase 8 inherits.
                model = TextEmbedding(model_name=options["embed_model"])
                mark("after model load")
                vectors = list(
                    model.embed(["RepoVitals memory smoke test: one short chunk."])
                )
                elapsed = time.monotonic() - started
                self.stdout.write(
                    f"  embedded 1 chunk -> dim {len(vectors[0])} in {elapsed:.1f}s"
                )
                mark("after one embedding")
            except ImportError:
                self.stdout.write(
                    self.style.WARNING(
                        "  fastembed not installed; run with --skip-embedding "
                        "or `pip install -r requirements.txt`"
                    )
                )
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  embedding failed: {exc}"))

        # ── 5. The agent runtime (Phase 8) ────────────────────────────────
        if options["skip_agent"]:
            self.stdout.write(self.style.WARNING("  agent runtime step skipped"))
        else:
            try:
                from apps.reports.agent.graph import build_graph

                build_graph()
                mark("after langgraph compile")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  langgraph failed: {exc}"))

            try:
                from apps.reports.rag import chroma_store

                # A throwaway collection under a name no scan can produce, so a
                # smoke run on prod cannot collide with a real one.
                scan_id = "00000000-0000-4000-8000-0000smoketest"
                chroma_store.add_chunks(
                    scan_id=scan_id,
                    ecosystem="npm",
                    package_name="repovitals-smoke-test",
                    resolved_version="0.0.0",
                    chunks=[
                        _SmokeChunk(
                            f"chunk{index}",
                            "RepoVitals memory smoke test: one short chunk of "
                            "changelog-shaped text to embed and store.",
                            index,
                        )
                        for index in range(8)
                    ],
                    vectors=[[0.01 * (index + 1)] * 384 for index in range(8)],
                )
                found = chroma_store.query(
                    scan_id=scan_id,
                    ecosystem="npm",
                    package_name="repovitals-smoke-test",
                    resolved_version="0.0.0",
                    vector=[0.01] * 384,
                )
                self.stdout.write(f"  chroma round-trip -> {len(found)} chunk(s)")
                mark("after chroma round-trip")
                chroma_store.drop_scan(scan_id)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  chroma failed: {exc}"))

        peak = max(marks.values()) if marks else -1.0
        budget = 512.0
        self.stdout.write("")
        self.stdout.write(f"  peak RSS: {peak:.1f} MB of {budget:.0f} MB budget")
        if peak > budget * 0.8:
            self.stdout.write(
                self.style.ERROR("  OVER 80% OF BUDGET — investigate before Phase 8.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("  within budget"))

        if options["json"]:
            self.stdout.write(json.dumps({"marks_mb": marks, "peak_mb": peak}, indent=2))
