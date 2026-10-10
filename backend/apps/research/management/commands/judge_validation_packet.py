"""`manage.py judge_validation_packet` — WP-9's blind labelling packet.

    python manage.py judge_validation_packet --items labelled_set.jsonl --runs A_1a2b3c4d_model C_1a2b3c4d_model

Samples 50 judged generations across the given runs, stratified by condition
and ecosystem, and writes three files into `--out`:

    judge_validation_packet.md     send to the labeller
    wp9_judge_labels_template.csv  send to the labeller
    judge_validation_key.json      KEEP: the judge's verdicts and where each item came from

Reads files only.

A re-validation (decisions §13.17, §15.4) labels a fresh 50: pass the first
round's key with `--exclude-key`, and its items are left out of the sample.
`wp/wp-9/judge_validation_key.json` is that key for the 2026-10-10 round.
"""

from __future__ import annotations

import json
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
        parser.add_argument(
            "--exclude-key",
            action="append",
            default=[],
            metavar="KEY.json",
            help="leave out every item an earlier packet's key names (repeatable)",
        )

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
            exclude = frozenset(
                (entry["item_id"], entry["condition"])
                for path in options["exclude_key"]
                for entry in _key_items(Path(path).expanduser())
            )
            written = judge_validation.build_packet(
                run_dirs,
                {item["item_id"]: item for item in items},
                judge.JudgeCache(runs_dir / judge.CACHE_FILENAME),
                out,
                size=options["size"],
                seed=options["seed"],
                exclude=exclude,
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


def _key_items(path: Path) -> list[dict]:
    try:
        return list(json.loads(path.read_text(encoding="utf-8"))["items"].values())
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as exc:
        raise CommandError(f"{path} is not a packet key: {exc}") from exc
