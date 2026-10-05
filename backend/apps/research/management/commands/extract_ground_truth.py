"""`manage.py extract_ground_truth` — S3's labelled set (D15).

    python manage.py extract_ground_truth
    python manage.py extract_ground_truth --sample 300      # a coverage estimate only

Reads the corpus snapshot's flagged dependencies from the research database
(D8), extracts a checkable answer for each it can — the minimum fixing version
from OSV's ranges, or a registry-verified successor from the deprecation text —
and draws the stratified 150 (75 npm / 75 PyPI, case-type quotas recorded).

Writes, under `--out`:

    ground_truth_candidates.jsonl   every item extracted
    labelled_set.jsonl              the stratified sample WP-8 runs
    labelled_set_meta.json          seed, snapshot, quotas, coverage
    extraction_report.md            coverage per stratum, drops by reason

**The labelled set is frozen once WP-8 starts** (File B WP-8 step 1), so an
existing `labelled_set.jsonl` is never overwritten unless `--overwrite` says to.
Asks OSV and the registries — no credential needed — and writes no row.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.corpus import append_jsonl
from apps.research.experiment import groundtruth
from apps.research.guards import no_operational_writes
from apps.research.validation.panel import PanelError, resolve_snapshot

DEFAULT_OUT = "../research_data/runs/ground_truth"
LABELLED_SET = "labelled_set.jsonl"
CANDIDATES = "ground_truth_candidates.jsonl"
META = "labelled_set_meta.json"
REPORT = "extraction_report.md"


class Command(BaseCommand):
    help = "Extract S3's auto-labelled items from the corpus and draw the stratified set."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--snapshot-date", metavar="YYYY-MM-DD")
        parser.add_argument("--out", default=DEFAULT_OUT, metavar="DIR")
        parser.add_argument("--size", type=int, default=groundtruth.DEFAULT_SIZE)
        parser.add_argument(
            "--replacement-share",
            type=float,
            default=0.5,
            help="Share of each ecosystem's half given to deprecation_replacement.",
        )
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument(
            "--sample",
            type=int,
            metavar="N",
            help="Extract from a seeded sample of N candidates: a coverage "
            "estimate, written as a report only, never as a labelled set.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace an existing labelled_set.jsonl. Never after WP-8 has started.",
        )

    def handle(self, *args, **options) -> None:
        out = Path(options["out"]).expanduser()
        if not out.is_absolute():
            out = (Path(settings.BASE_DIR) / out).resolve()
        labelled = out / LABELLED_SET
        writing_set = options["sample"] is None
        if writing_set and labelled.exists() and not options["overwrite"]:
            raise CommandError(
                f"{labelled} already exists, and a labelled set is frozen once WP-8 "
                f"starts (File B WP-8 step 1). Pass --overwrite only if no run has "
                f"used it, or --out somewhere else."
            )
        if not 0 <= options["replacement_share"] <= 1:
            raise CommandError("--replacement-share must be between 0 and 1.")

        requested = None
        if options["snapshot_date"]:
            try:
                requested = date.fromisoformat(options["snapshot_date"])
            except ValueError as exc:
                raise CommandError("--snapshot-date must be YYYY-MM-DD.") from exc

        try:
            with no_operational_writes():
                snapshot = resolve_snapshot(requested)
                candidates = groundtruth.corpus_candidates(snapshot)
                sampled_from = None
                if options["sample"] is not None:
                    ordered = sorted(candidates, key=lambda c: c.key)
                    random.Random(options["seed"]).shuffle(ordered)  # noqa: S311
                    candidates = ordered[: options["sample"]]
                    sampled_from = options["sample"]
                self.stdout.write(
                    f"Snapshot {snapshot}: {len(candidates)} flagged (package, version) "
                    f"candidate(s)"
                )
                extraction = groundtruth.extract(
                    candidates,
                    snapshot_date=snapshot,
                    progress=lambda line: self.stdout.write(f"  {line}"),
                )
        except PanelError as exc:
            raise CommandError(str(exc)) from exc

        out.mkdir(parents=True, exist_ok=True)
        candidates_path = out / CANDIDATES
        candidates_path.unlink(missing_ok=True)
        for item in extraction.items:
            append_jsonl(candidates_path, item)

        quotas = None
        if writing_set:
            selected, quotas = groundtruth.stratified_sample(
                extraction.items,
                size=options["size"],
                replacement_share=options["replacement_share"],
                seed=options["seed"],
            )
            labelled.unlink(missing_ok=True)
            for item in selected:
                append_jsonl(labelled, item)
            (out / META).write_text(
                json.dumps(
                    {
                        "generated_at": datetime.now(UTC).isoformat(),
                        "snapshot_date": snapshot.isoformat(),
                        "seed": options["seed"],
                        "size": options["size"],
                        "replacement_share": options["replacement_share"],
                        "items": len(selected),
                        "quotas": [quota.__dict__ for quota in quotas],
                        "coverage": {
                            f"{ecosystem}|{case}": cell
                            for (ecosystem, case), cell in extraction.coverage.items()
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        (out / REPORT).write_text(
            groundtruth.extraction_report(
                extraction,
                quotas,
                snapshot_date=snapshot,
                size=options["size"],
                sampled_from=sampled_from,
            ),
            encoding="utf-8",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(extraction.items)} item(s) extracted"
                + (
                    f"; labelled set of {sum(q.taken for q in quotas)} written"
                    if quotas is not None
                    else "; coverage estimate only"
                )
            )
        )
        if len(extraction.items) < options["size"]:
            self.stdout.write(
                self.style.WARNING(
                    f"  SHORTFALL: fewer than {options['size']} items. See {REPORT}."
                )
            )
        for name in (CANDIDATES, LABELLED_SET, META, REPORT):
            if (out / name).exists():
                self.stdout.write(f"  wrote {out / name}")
