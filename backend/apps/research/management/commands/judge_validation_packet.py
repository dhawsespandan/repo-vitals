"""`manage.py judge_validation_packet` — WP-9's blind labelling packet.

    python manage.py judge_validation_packet --items labelled_set.jsonl --runs A_1a2b3c4d_model C_1a2b3c4d_model

Samples 50 judged generations across the given runs, stratified by condition
and ecosystem, and writes three files into `--out`:

    judge_validation_packet.md     send to the labeller
    wp9_judge_labels_template.csv  send to the labeller
    judge_validation_key.json      KEEP: the judge's verdicts and where each item came from

Reads files only.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.experiment import judge, judge_validation, runner
from apps.research.management.commands.run_experiment import DEFAULT_OUT, resolve_items


class Command(BaseCommand):
    help = "Build WP-9's blind judge-validation packet from judged runs."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--items", required=True, metavar="labelled_set.jsonl")
        parser.add_argument("--runs", required=True, nargs="+", metavar="RUN_ID")
        parser.add_argument("--runs-dir", default=DEFAULT_OUT, metavar="DIR")
        parser.add_argument(
            "--out", metavar="DIR", help="(default: <runs-dir>/judge_validation)"
        )
        parser.add_argument("--size", type=int, default=judge_validation.DEFAULT_SIZE)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options) -> None:
        runs_dir = Path(options["runs_dir"]).expanduser()
        if not runs_dir.is_absolute():
            runs_dir = (Path(settings.BASE_DIR) / runs_dir).resolve()
        out = (
            Path(options["out"]).expanduser()
            if options["out"]
            else runs_dir / "judge_validation"
        )
        try:
            items, _ = runner.load_items(resolve_items(options["items"]))
            run_dirs = [runs_dir / run_id for run_id in options["runs"]]
            missing = [
                d.name for d in run_dirs if not (d / runner.ITEMS_FILENAME).exists()
            ]
            if missing:
                raise CommandError(f"No results for run(s): {', '.join(missing)}.")
            written = judge_validation.build_packet(
                run_dirs,
                {item["item_id"]: item for item in items},
                judge.JudgeCache(runs_dir / judge.CACHE_FILENAME),
                out,
                size=options["size"],
                seed=options["seed"],
            )
        except (runner.RunError, judge_validation.ValidationPacketError) as exc:
            raise CommandError(str(exc)) from exc
        for path in written:
            self.stdout.write(f"  wrote {path}")
        self.stdout.write(
            self.style.WARNING(
                f"  Send {judge_validation.PACKET_FILENAME} and "
                f"{judge_validation.TEMPLATE_FILENAME} only. "
                f"{judge_validation.KEY_FILENAME} holds the judge's verdicts."
            )
        )
