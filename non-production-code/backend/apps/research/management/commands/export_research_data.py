"""`manage.py export_research_data` — the replication package's data, in one folder.

    python manage.py export_research_data
    python manage.py export_research_data --out ../research_data/exports --overwrite

Writes `research_data/exports/` (§10 Phase 14): `scan_history`,
`dependency_history` and `agent_traces` as Parquet and CSV from the database
`DATABASE_URL` points at, the signed deliverables File C reads (corpus
manifest, validation report, the WP-8 runs and labelled set, the WP-9 labels,
the AHP matrix and anchor set) and the weights files, plus `MANIFEST.json`
with every file's sha256. File B's deliverables are archived as received
under `research_data/deliverables/`.

**Point `DATABASE_URL` at the research database** (D8) with WP-5's dump
restored: `pg_restore --no-owner -d <research db> wp/wp-5/wp5_research_db.dump`.
Nothing is written to it; the whole export runs inside a guard that refuses
every write.

Only `corpus_scan` rows are exported unless `--source` says otherwise (File C
§1.2); `--source all` adds `live_scan` rows and the live agent traces, which
name RepoVitals users and their repositories.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research import export
from apps.research.guards import no_writes
from apps.research.models import DataSource

DEFAULT_OUT = "../research_data/exports"
DEFAULT_DELIVERABLES = "../wp"
DEFAULT_ARCHIVE = "../research_data/deliverables"


def _path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path(settings.BASE_DIR) / path).resolve()
    return path


class Command(BaseCommand):
    help = (
        "Export the permanent tables (Parquet + CSV), the signed deliverables File C "
        "reads, and the weights files, with a sha256 manifest. Reads only."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--out", default=DEFAULT_OUT, metavar="DIR", help=f"(default: {DEFAULT_OUT})"
        )
        parser.add_argument(
            "--deliverables",
            default=DEFAULT_DELIVERABLES,
            metavar="DIR",
            help=f"The signed File B deliverables (default: {DEFAULT_DELIVERABLES}).",
        )
        parser.add_argument(
            "--archive",
            default=DEFAULT_ARCHIVE,
            metavar="DIR",
            help=f"Where the deliverables are archived as received (default: "
            f"{DEFAULT_ARCHIVE}).",
        )
        parser.add_argument(
            "--no-archive",
            action="store_true",
            help="Export only; do not archive the deliverables.",
        )
        parser.add_argument(
            "--source",
            choices=[*DataSource.values, "all"],
            default=DataSource.CORPUS_SCAN.value,
            help="Which history rows to export (default: corpus_scan). `live_scan` "
            "and `all` include the live agent traces.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace a previous export in --out, removing only the files its "
            "MANIFEST.json lists, and copy over an existing archive. Nothing else "
            "in either folder is touched.",
        )

    def handle(self, *args, **options) -> None:
        sources = (
            tuple(DataSource.values)
            if options["source"] == "all"
            else (options["source"],)
        )
        archive = None if options["no_archive"] else _path(options["archive"])

        self.stdout.write(f"Database: {settings.DATABASES['default'].get('NAME')}")
        try:
            with no_writes():
                result = export.export_research_data(
                    _path(options["out"]),
                    _path(options["deliverables"]),
                    archive=archive,
                    sources=sources,
                    overwrite=options["overwrite"],
                    progress=lambda line: self.stdout.write(f"  {line}"),
                )
        except export.ExportError as exc:
            raise CommandError(str(exc)) from exc

        rows = ", ".join(f"{table.name} {table.rows}" for table in result.tables)
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(result.files)} file(s) to {result.out} ({rows})."
            )
        )
        self.stdout.write(f"  wrote {result.manifest}")
