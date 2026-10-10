"""`manage.py validate_formula` — WP-6's run, and study S1's results.

    python manage.py validate_formula --ahp wp3_matrix_reconciled.csv --anchors wp2_anchor_set.csv

Gates the reconciled AHP matrix (refusing at CR >= 0.10, with the triads to
revisit), loads one corpus snapshot from the research database and checks its
stored scores reproduce, derives entropy weights, scores the corpus under the
active file, the AHP candidate and the entropy vector, compares them with
deps.dev's Scorecard and an OSV roll-up, sweeps both vectors' sensitivity,
scans and checks the anchors, and writes `research_data/validation_report/`.

**Point `DATABASE_URL` at the research database** (D8), where the WP-5 dump
was restored. Nothing is written to it — the run is inside D10's guard and its
only outputs are files — but the corpus rows are only there.

The anchor scan needs `GITHUB_API_PAT` (zero scopes, §6) and is saved beside
the report, so a second run reuses it unless the anchor CSV changed or
`--rescan-anchors` is given. deps.dev answers are cached the same way.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.github import RateBudgetExhausted, ResearchCredentialMissing
from apps.research.guards import no_operational_writes
from apps.research.validation import ahp, anchors, candidates, harness, panel, report
from apps.scoring.weights import WeightsError

DEFAULT_OUT = "../research_data/validation_report"


def _path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path(settings.BASE_DIR) / path).resolve()
    return path


class Command(BaseCommand):
    help = (
        "S1's validation harness (WP-6): AHP gate, entropy weights, Scorecard and "
        "OSV agreement, dual-vector sensitivity, anchors, and the report folder."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--ahp",
            required=True,
            metavar="MATRIX.csv",
            help="The reconciled WP-3 matrix.",
        )
        parser.add_argument(
            "--anchors", metavar="ANCHORS.csv", help="wp2_anchor_set.csv (RQ4)."
        )
        parser.add_argument(
            "--snapshot-date",
            metavar="YYYY-MM-DD",
            help="The corpus snapshot to validate on. Required only when the "
            "research database holds more than one.",
        )
        parser.add_argument(
            "--baseline",
            metavar="VERSION",
            help="The weights file the candidate is compared with and inherits "
            "caps, roll-up and thresholds from (default: the active one).",
        )
        parser.add_argument(
            "--pypi-shift",
            metavar="SIGNAL=DELTA,...",
            help="The PyPI rule from the WP-3 notes, as a zero-sum shift applied "
            "to the AHP vector, e.g. deprecation=-0.14,severity=+0.07,staleness=+0.07.",
        )
        parser.add_argument(
            "--out", default=DEFAULT_OUT, metavar="DIR", help=f"(default: {DEFAULT_OUT})"
        )
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument(
            "--bootstrap",
            type=int,
            default=2000,
            metavar="N",
            help="Bootstrap resamples for every interval (File C: at least 2,000).",
        )
        parser.add_argument(
            "--skip-reference",
            action="store_true",
            help="Do not ask deps.dev (RQ2 then reports the OSV roll-up only).",
        )
        parser.add_argument(
            "--rescan-anchors",
            action="store_true",
            help="Scan the anchors again even if a scan of this CSV is saved.",
        )
        parser.add_argument(
            "--no-wait",
            action="store_true",
            help="Stop rather than sleep if GitHub's hourly budget runs low.",
        )

    def handle(self, *args, **options) -> None:
        snapshot = None
        if options["snapshot_date"]:
            try:
                snapshot = date.fromisoformat(options["snapshot_date"])
            except ValueError as exc:
                raise CommandError(
                    f"--snapshot-date must be YYYY-MM-DD, not {options['snapshot_date']!r}."
                ) from exc

        inputs = harness.ValidationInputs(
            ahp_path=_path(options["ahp"]),
            out_dir=_path(options["out"]),
            anchors_path=_path(options["anchors"]) if options["anchors"] else None,
            snapshot_date=snapshot,
            baseline_version=options["baseline"],
            pypi_shift=options["pypi_shift"],
            seed=options["seed"],
            bootstrap=max(0, options["bootstrap"]),
            skip_reference=options["skip_reference"],
            rescan_anchors=options["rescan_anchors"],
            wait_for_reset=not options["no_wait"],
        )

        self.stdout.write(f"Database: {settings.DATABASES['default'].get('NAME')}")
        try:
            with no_operational_writes():
                run = harness.run_validation(
                    inputs, progress=lambda line: self.stdout.write(f"  {line}")
                )
                written = report.write_report(run)
        except ahp.InconsistentMatrix as exc:
            raise CommandError(str(exc)) from exc
        except (
            ahp.MatrixError,
            anchors.AnchorSetError,
            candidates.CandidateError,
            harness.ValidationError,
            panel.PanelError,
            WeightsError,
            ResearchCredentialMissing,
            RateBudgetExhausted,
        ) as exc:
            raise CommandError(str(exc)) from exc

        statuses = report.checklist(run)
        self.stdout.write(
            self.style.SUCCESS(
                f"Validated {len(run.panel.repositories)} repositories as of "
                f"{run.panel.snapshot_date}. WP-6 checklist: "
                + ", ".join(f"{check.number} {check.status}" for check in statuses)
                + "."
            )
        )
        for path in written:
            self.stdout.write(f"  wrote {path}")
