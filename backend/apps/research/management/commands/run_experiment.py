"""`manage.py run_experiment` — WP-8's command, one condition at a time.

    python manage.py run_experiment --condition A --items labelled_set.jsonl --resume

Runs one S3 condition over the labelled set (§10 Phase 13) and writes
`research_data/runs/{run_id}/items.jsonl` plus `run.json`. Re-typing the same
command continues the same run; it stops cleanly at the generator's daily cap
and says so. **Never run two conditions at once** (File B WP-8 step 2): they
would share one free-tier budget.

Needs `GROQ_API_KEY`; conditions B-D also read documents with
`GITHUB_API_PAT`, and D searches issues with it (D13: this command is the only
way D can run). Writes files only.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.experiment import conditions, runner
from apps.research.github import RateBudgetExhausted, ResearchCredentialMissing
from apps.research.guards import no_operational_writes

DEFAULT_OUT = "../research_data/runs"
DEFAULT_ITEMS_DIR = "../research_data/runs/ground_truth"


def resolve_items(value: str) -> Path:
    """As typed, else relative to `backend/`, else in the ground-truth folder."""
    for candidate in (
        Path(value).expanduser(),
        Path(settings.BASE_DIR) / value,
        Path(settings.BASE_DIR) / DEFAULT_ITEMS_DIR / value,
    ):
        if candidate.exists():
            return candidate.resolve()
    return Path(value)


class Command(BaseCommand):
    help = "Run one S3 condition over the labelled set; resumable, paced, checkpointed."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--condition", required=True, choices=list("ABCDabcd"))
        parser.add_argument("--items", required=True, metavar="labelled_set.jsonl")
        parser.add_argument("--out", default=DEFAULT_OUT, metavar="DIR")
        parser.add_argument("--resume", action="store_true")
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Run again the items recorded as failed (their new result is appended).",
        )
        parser.add_argument("--limit", type=int, metavar="N", help="Stop after N items.")
        parser.add_argument(
            "--pace",
            type=float,
            default=runner.DEFAULT_PACE_SECONDS,
            metavar="SECONDS",
            help="Minimum seconds between generations.",
        )

    def handle(self, *args, **options) -> None:
        out = Path(options["out"]).expanduser()
        if not out.is_absolute():
            out = (Path(settings.BASE_DIR) / out).resolve()
        condition = conditions.get(options["condition"])
        if condition.internal:
            self.stdout.write(
                self.style.WARNING(
                    f"Condition {condition.name} is internal (D13): it reads public "
                    f"issue text and exists only as this command."
                )
            )
        try:
            with no_operational_writes():
                outcome = runner.run_experiment(
                    items_path=resolve_items(options["items"]),
                    condition_name=condition.name,
                    out_dir=out,
                    resume=options["resume"],
                    retry_failed=options["retry_failed"],
                    limit=options["limit"],
                    pace_seconds=max(0.0, options["pace"]),
                    progress=lambda line: self.stdout.write(f"  {line}"),
                )
        except (runner.RunError, ResearchCredentialMissing, RateBudgetExhausted) as exc:
            raise CommandError(str(exc)) from exc

        for other in outcome.other_runs:
            self.stdout.write(
                self.style.WARNING(
                    f"  Another run of condition {condition.name} over this labelled "
                    f"set exists: {other} (a different generator model)."
                )
            )
        summary = (
            f"Run {outcome.run_id}: {outcome.completed} completed, {outcome.failed} "
            f"failed, {outcome.skipped} already done, {outcome.remaining} remaining."
        )
        if outcome.stopped:
            self.stdout.write(
                self.style.WARNING(f"{summary}\n  Stopped: {outcome.stopped}")
            )
        else:
            self.stdout.write(self.style.SUCCESS(summary))
        self.stdout.write(f"  {outcome.directory / runner.ITEMS_FILENAME}")
