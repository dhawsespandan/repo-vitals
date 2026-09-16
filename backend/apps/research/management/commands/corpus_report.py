"""`manage.py corpus_report` — the corpus's descriptive figures.

    python manage.py corpus_report --corpus research_data/corpus/corpus_manifest.json

Two PNGs and a short markdown summary: the score histogram per ecosystem and
the flagged rate by stratum (§10 Phase 11). They are S1's descriptive figures
and they are also the phase's mentor demo — "a thousand repositories sampled
on a documented frame and scored by the exact code the product runs".

They are also the artefact WP-5's hardest review question needs. File B asks
the teammate to confirm that the score distribution *spreads* rather than
piling into one class, which is a judgement no single number supports.

Reads only. It writes files and not one database row, so it is safe to run
against any database that holds corpus rows — but point `DATABASE_URL` at the
research one (D8), because that is the only place they are.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.charts import (
    SUMMARY_FILENAME,
    ChartsUnavailable,
    collect,
    render_figures,
    summary,
)
from apps.research.corpus import MANIFEST_FILENAME
from apps.research.guards import no_operational_writes

DEFAULT_CORPUS = f"../research_data/corpus/{MANIFEST_FILENAME}"


class Command(BaseCommand):
    help = (
        "Render the corpus score histogram and flagged-rate-by-stratum charts "
        "from corpus_scan rows. Writes files only."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--corpus",
            default=DEFAULT_CORPUS,
            metavar="PATH",
            help=f"corpus_manifest.json, for the strata (default: {DEFAULT_CORPUS}).",
        )
        parser.add_argument(
            "--out",
            metavar="DIR",
            help="Where the figures are written (default: beside the manifest).",
        )
        parser.add_argument(
            "--snapshot-date",
            metavar="YYYY-MM-DD",
            help="Chart one run (default: the most recent snapshot date present). "
            "A research database holding two runs must chart one of them, not "
            "both superimposed.",
        )

    def handle(self, *args, **options) -> None:
        corpus_path = Path(options["corpus"]).expanduser()
        if not corpus_path.is_absolute():
            corpus_path = (Path(settings.BASE_DIR) / corpus_path).resolve()
        if not corpus_path.exists():
            raise CommandError(
                f"No corpus manifest at {corpus_path}. The strata come from it, "
                f"so the flagged-rate chart cannot be drawn without it."
            )

        out_dir = (
            Path(options["out"]).expanduser() if options["out"] else corpus_path.parent
        )

        snapshot_date = None
        if options["snapshot_date"]:
            try:
                snapshot_date = date.fromisoformat(options["snapshot_date"])
            except ValueError as exc:
                raise CommandError(
                    f"--snapshot-date must be YYYY-MM-DD, not "
                    f"{options['snapshot_date']!r}."
                ) from exc

        with no_operational_writes():
            stats = collect(corpus_path, snapshot_date)

        if not stats.repositories:
            raise CommandError(
                "No `corpus_scan` rows found"
                + (f" for {snapshot_date}." if snapshot_date else ".")
                + " Run `manage.py scan_corpus` first, and check DATABASE_URL "
                "points at the research database (D8)."
            )

        try:
            figures = render_figures(stats, out_dir)
        except ChartsUnavailable as exc:
            raise CommandError(str(exc)) from exc

        summary_path = out_dir / SUMMARY_FILENAME
        summary_path.write_text(summary(stats, figures), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Charted {stats.repositories} corpus repositor(ies) / "
                f"{stats.occurrences} occurrence(s) as of {stats.snapshot_date}."
            )
        )
        if stats.unmatched:
            self.stdout.write(
                self.style.WARNING(
                    f"  {stats.unmatched} corpus row(s) are not in this manifest — "
                    f"the database and the manifest may describe different runs."
                )
            )
        for path in [*figures, summary_path]:
            self.stdout.write(f"  wrote {path}")
