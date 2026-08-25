"""`manage.py smoke_memory` — the Phase 1 feasibility answer.

RepoVitals must fit a 512 MB Render instance while holding, in one process:
Django + DRF, a Postgres connection pool, background scan threads, and — from
Phase 8 — a fastembed ONNX embedding model. That last item is the genuine
risk (D7: torch alone would be ~700 MB installed), and it is far cheaper to
find out in week one than in week twenty. So this command runs *now*, before
any of the machinery that depends on the answer exists.

It reproduces the shape of the production worker rather than a synthetic
benchmark:

  1. baseline RSS after Django is fully loaded,
  2. an authenticated request cycle against the session endpoint,
  3. a background thread doing an outbound registry fetch with its own
     database connection, closed on the way out — the exact hygiene every
     Phase 3+ scan thread will need,
  4. one fastembed embedding, which is where the memory actually goes.

Record the peak into `docs/decisions.md` (Phase 1 acceptance). On Render, read
the same number from the service's logs after triggering this via a shell.
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
        from django.test import Client

        client = Client()
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
