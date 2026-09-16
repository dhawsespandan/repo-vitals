"""`manage.py build_corpus` — D14's sampling frame, executed.

WP-4 is the run:

    python manage.py build_corpus --seed 42 --target 1000 --config corpus_frame.yaml

It writes `corpus_manifest.json` and `strata_report.md` into
`research_data/corpus/`, archives the manifest blobs it read beside them, and
paces itself under §8's 30 search requests a minute. It takes about an hour
and is resumable: interrupted, rerun the same command with `--resume`.

**It writes no database row at all** — not an operational one and not a
research one. The corpus does not exist in Postgres until `scan_corpus` scores
it; this command's whole output is files. The guard is on anyway (D10), so
that the day someone adds a "just record which repositories we picked" table
the refusal arrives immediately rather than on the teammate's machine.

Nothing here is user-facing: no route, no serializer, never imported by
request-handling code (§3).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.corpus import (
    CorpusConfigError,
    build_corpus,
    load_grid,
)
from apps.research.github import ResearchClient, ResearchCredentialMissing
from apps.research.guards import no_operational_writes

DEFAULT_OUT = "../research_data/corpus"
DEFAULT_CONFIG = "corpus_frame.yaml"


class Command(BaseCommand):
    help = (
        "Build the research corpus sampling frame: enumerate the grid, sample "
        "seeded candidates per cell, verify them, and write corpus_manifest.json "
        "and strata_report.md. Writes no database row."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--config",
            default=DEFAULT_CONFIG,
            metavar="PATH",
            help=f"Sampling-frame YAML (default: {DEFAULT_CONFIG}).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            required=True,
            help="Sampling seed. Recorded in both outputs; the same seed over "
            "an unchanged frame draws the same result positions.",
        )
        parser.add_argument(
            "--target",
            type=int,
            default=1000,
            help="Admissions to aim for across the whole frame (default: 1000).",
        )
        parser.add_argument(
            "--out",
            default=DEFAULT_OUT,
            metavar="DIR",
            help=f"Where the corpus is written (default: {DEFAULT_OUT}).",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Replay the checkpoint instead of starting over.",
        )
        parser.add_argument(
            "--no-wait",
            action="store_true",
            help="Stop rather than sleep when GitHub's hourly budget runs low.",
        )

    def handle(self, *args, **options) -> None:
        config_path = Path(options["config"]).expanduser()
        if not config_path.is_absolute():
            config_path = Path(settings.BASE_DIR) / config_path

        try:
            grid = load_grid(config_path)
        except CorpusConfigError as exc:
            raise CommandError(str(exc)) from exc

        out_dir = Path(options["out"]).expanduser()
        if not out_dir.is_absolute():
            out_dir = (Path(settings.BASE_DIR) / out_dir).resolve()

        try:
            client = ResearchClient.from_settings(wait_for_reset=not options["no_wait"])
        except ResearchCredentialMissing as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Frame: {config_path}")
        self.stdout.write(f"Output: {out_dir}")

        with no_operational_writes():
            result = build_corpus(
                out_dir=out_dir,
                grid=grid,
                seed=options["seed"],
                target=options["target"],
                client=client,
                resume=options["resume"],
                progress=lambda line: self.stdout.write(f"  {line}"),
            )

        rate = result.admitted / result.candidates if result.candidates else 0.0
        self.stdout.write(
            self.style.SUCCESS(
                f"Admitted {result.admitted} of {result.candidates} candidate(s) "
                f"({rate:.0%}) across {len(result.cells)} cell(s) in "
                f"{client.search_calls} search call(s)."
            )
        )
        for reason, count in sorted(result.rejected.items()):
            self.stdout.write(f"  rejected {reason}: {count}")
        self.stdout.write(f"  wrote {result.manifest_path}")
        self.stdout.write(f"  wrote {result.report_path}")
        self.stdout.write(
            "Read the strata report before handing this on — WP-4's checklist "
            "is already computed at the top of it."
        )
