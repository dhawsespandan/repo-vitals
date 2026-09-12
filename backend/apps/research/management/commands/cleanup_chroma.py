"""`cleanup_chroma` — §10 Phase 9's orphan sweep over the vector store.

File A: "`cleanup_chroma`: drop collections whose scan is gone or whose reports
all persisted."

**Why anything is left behind at all.** §5.9's graph deletes a dependency's
chunks the moment its report persists, so the normal path leaves nothing. What
escapes that are the abnormal ones, and both are ordinary rather than exotic:

* a scan deleted by §5.7's retention takes its reports and occurrences with it
  and cannot take its Chroma collection, because the collection is not in
  Postgres and no cascade reaches it;
* a generation that died between `ensure_corpus` and `persist` — a restarted
  worker, an LLM timeout — embedded a changelog nothing will ever read.

Neither is a correctness problem. Both are disk on a free tier that has 512 MB
of RAM and an ephemeral disk (§8), and both are invisible: nothing in the
product ever lists what the store is holding.

**What the sweep will not touch.** A collection whose scan still exists *and*
has a generation queued or running is in use — that is the whole rule, and it
is stated as "nothing is actively generating" rather than "every report is
completed" on purpose. A scan whose only report failed has nothing reading its
chunks either; keeping the collection for a retry would save one changelog
fetch (`ensure_corpus` is idempotent and re-enterable by construction) at the
price of a rule with two clauses instead of one.

**It is safe to run twice.** Dropping a collection that is already gone is not
an error, and the second run simply finds nothing to do — which is what "idempotent"
has to mean for a command whose failure mode is deleting something in use.

Run on the research machine or in dev; it needs no key and touches no research
table (D10 — it writes nothing to the database at all).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.reports.models import Report, ReportStatus
from apps.scanning.models import ScanRun


class Command(BaseCommand):
    help = "Drop Chroma collections whose scan is gone or whose reports all persisted."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be dropped and drop nothing.",
        )

    def handle(self, *args, **options) -> None:
        # Imported inside the handler, for §8.9's reason: `chromadb` costs
        # ~31 MB resident on import and this module is discovered by every
        # `manage.py` invocation there is, including the one Render runs to
        # migrate. A management command's import must not move the floor of a
        # 512 MB tier.
        from apps.reports.rag import chroma_store

        dry_run: bool = options["dry_run"]

        held = chroma_store.list_scan_ids()
        if not held:
            self.stdout.write("The chunk store holds no scan collections.")
            return

        # One query for every scan in the store rather than one per scan: the
        # sweep runs against a research database that may hold a whole corpus.
        live = {
            str(pk)
            for pk in ScanRun.objects.filter(pk__in=held).values_list("pk", flat=True)
        }
        busy = {
            str(scan_id)
            for scan_id in Report.objects.filter(
                scan_id__in=held, status__in=ReportStatus.active()
            ).values_list("scan_id", flat=True)
        }

        dropped = 0
        kept = 0
        for scan_id in held:
            if scan_id not in live:
                reason = "its scan is gone"
            elif scan_id not in busy:
                reason = "nothing is generating against it"
            else:
                kept += 1
                self.stdout.write(f"  keep  {scan_id} - a generation is in flight")
                continue

            if dry_run:
                self.stdout.write(f"  would drop {scan_id} - {reason}")
            else:
                chroma_store.drop_scan(scan_id)
                self.stdout.write(f"  dropped {scan_id} - {reason}")
            dropped += 1

        verb = "would be dropped" if dry_run else "dropped"
        self.stdout.write(
            self.style.SUCCESS(
                f"{dropped} collection(s) {verb}, {kept} left in place "
                f"(of {len(held)} held)."
            )
        )
