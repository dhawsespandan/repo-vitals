"""`manage.py scan_corpus` — WP-5's run, and S1's dataset.

    python manage.py scan_corpus --corpus research_data/corpus/corpus_manifest.json --resume

Scans every repository `build_corpus` admitted, once, through the adapters and
the formula the product ships, and writes `scan_history` + `dependency_history`
rows tagged `corpus_scan` (D10/D14). Two to three hours for a thousand
repositories, checkpointed continuously; a crash, a closed laptop or a
rate-limit pause costs nothing but the repository in flight.

**Point `DATABASE_URL` at the research database before running this** (D8). A
thousand-repository scan is roughly forty thousand `dependency_history` rows,
which is not product data, must never be reachable from a product query, and
would spend Supabase's free tier on a single run. `docker compose --profile
research up -d` brings that database up; the guard in this command refuses
operational writes but cannot tell which *database* it is connected to, so
this one is on the operator.

Nothing here is user-facing: no route, no serializer, never imported by
request-handling code (§3).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.corpus import MANIFEST_FILENAME
from apps.research.corpus_scan import CorpusManifestError, load_corpus, run_guarded
from apps.research.github import (
    RateBudgetExhausted,
    ResearchClient,
    ResearchCredentialMissing,
)
from apps.scoring.weights import WeightsError, available_versions, load_weights

DEFAULT_CORPUS = f"../research_data/corpus/{MANIFEST_FILENAME}"


class Command(BaseCommand):
    help = (
        "Scan every admitted corpus repository once through the product's own "
        "adapters and formula, writing research history rows only (D10)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--corpus",
            default=DEFAULT_CORPUS,
            metavar="PATH",
            help=f"corpus_manifest.json from build_corpus (default: {DEFAULT_CORPUS}).",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip repositories already scanned for this snapshot date. "
            "Checked against the database as well as the checkpoint, so a "
            "kill -9 between the two cannot duplicate rows.",
        )
        parser.add_argument(
            "--repo",
            metavar="OWNER/NAME",
            help="Scan one admitted repository and stop. Writes the same rows.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            metavar="N",
            help="Stop after N repositories — a pilot run over a large corpus.",
        )
        parser.add_argument(
            "--weights",
            metavar="VERSION",
            help="Weights version to score under (default: the active one).",
        )
        parser.add_argument(
            "--snapshot-date",
            metavar="YYYY-MM-DD",
            help="The as-of date recorded on every row (default: today). "
            "Also the key --resume matches on, so a multi-day run must pass "
            "the same value it started with.",
        )
        parser.add_argument(
            "--no-wait",
            action="store_true",
            help="Stop rather than sleep when GitHub's hourly budget runs low.",
        )

    def handle(self, *args, **options) -> None:
        corpus_path = Path(options["corpus"]).expanduser()
        if not corpus_path.is_absolute():
            corpus_path = (Path(settings.BASE_DIR) / corpus_path).resolve()

        try:
            corpus = load_corpus(corpus_path)
        except CorpusManifestError as exc:
            raise CommandError(str(exc)) from exc

        weights = None
        if options["weights"]:
            try:
                weights = load_weights(options["weights"])
            except WeightsError as exc:
                raise CommandError(
                    f"{exc}\nAvailable versions: "
                    f"{', '.join(available_versions()) or 'none'}"
                ) from exc

        snapshot_date = None
        if options["snapshot_date"]:
            try:
                snapshot_date = date.fromisoformat(options["snapshot_date"])
            except ValueError as exc:
                raise CommandError(
                    f"--snapshot-date must be YYYY-MM-DD, not "
                    f"{options['snapshot_date']!r}."
                ) from exc

        try:
            client = ResearchClient.from_settings(wait_for_reset=not options["no_wait"])
        except ResearchCredentialMissing as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Corpus: {corpus_path} ({len(corpus.repositories)} repos)")
        self.stdout.write(f"Database: {settings.DATABASES['default'].get('NAME')}")

        try:
            outcome = run_guarded(
                corpus=corpus,
                client=client,
                weights=weights,
                snapshot_date=snapshot_date,
                resume=options["resume"],
                only=options["repo"],
                limit=options["limit"],
                progress=lambda line: self.stdout.write(f"  {line}"),
            )
        except RateBudgetExhausted as exc:
            raise CommandError(str(exc)) from exc
        except CorpusManifestError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {outcome.scanned} repositor(ies) under "
                f"{outcome.weights_version} as of {outcome.snapshot_date}: "
                f"{outcome.occurrences} occurrence(s), {outcome.flagged} flagged, "
                f"{outcome.unassessable} unassessable."
            )
        )
        if outcome.skipped:
            self.stdout.write(f"  skipped {outcome.skipped} already-scanned repo(s)")
        if outcome.failed:
            self.stdout.write(
                self.style.WARNING(
                    f"  {outcome.failed} repositor(ies) failed; they are listed in "
                    f"the completion report and --resume will retry them."
                )
            )
        self.stdout.write(f"  wrote {outcome.report_path}")
