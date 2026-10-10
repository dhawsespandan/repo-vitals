"""`manage.py analyze_experiment` — S3's tables, from the runs.

    python manage.py analyze_experiment --runs A_1a2b3c4d_model B_1a2b3c4d_model C_1a2b3c4d_model
    python manage.py analyze_experiment --runs ... --judge     # judge what is not judged yet

One run per condition, all over the same frozen labelled set (the runs'
manifests are checked). Writes `tables.md` and one CSV per table into
`--out` (default `research_data/runs/analysis/`). With `--judge`, judges any
successful generation the judge has not scored yet — paced, cached, and
stopping cleanly at the judge's daily limit — before rendering.

The labelled set is found from the runs' own manifests unless `--items` names
it. Writes files only.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.experiment import analysis, judge, runner
from apps.research.management.commands.run_experiment import (
    DEFAULT_OUT,
    resolve_items,
)


class Command(BaseCommand):
    help = "Render S3's condition x ecosystem x case-type tables and paired tests."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--runs", required=True, nargs="+", metavar="RUN_ID")
        parser.add_argument("--runs-dir", default=DEFAULT_OUT, metavar="DIR")
        parser.add_argument("--items", metavar="labelled_set.jsonl")
        parser.add_argument("--out", metavar="DIR", help="(default: <runs-dir>/analysis)")
        parser.add_argument(
            "--judge", action="store_true", help="Judge unjudged generations first."
        )
        parser.add_argument("--bootstrap", type=int, default=2000)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options) -> None:
        runs_dir = Path(options["runs_dir"]).expanduser()
        if not runs_dir.is_absolute():
            runs_dir = (Path(settings.BASE_DIR) / runs_dir).resolve()
        run_dirs = [runs_dir / run_id for run_id in options["runs"]]
        missing = [d.name for d in run_dirs if not (d / runner.RUN_FILENAME).exists()]
        if missing:
            raise CommandError(f"No run manifest for: {', '.join(missing)}.")

        items_name = (
            options["items"]
            or json.loads(
                (run_dirs[0] / runner.RUN_FILENAME).read_text(encoding="utf-8")
            )["items_file"]
        )
        try:
            items, _ = runner.load_items(resolve_items(items_name))
        except runner.RunError as exc:
            raise CommandError(
                f"{exc} Pass --items with the labelled set's path."
            ) from exc

        judge_missing = None
        if options["judge"]:
            if not judge.is_configured():
                raise CommandError("--judge needs GEMINI_API_KEY (§6, Phase 13).")
            judge_missing = judge.Judge(
                cache=judge.JudgeCache(runs_dir / judge.CACHE_FILENAME)
            )

        try:
            dataset = analysis.load(
                run_dirs,
                {item["item_id"]: item for item in items},
                judge.JudgeCache(runs_dir / judge.CACHE_FILENAME),
                judge_missing=judge_missing,
                progress=lambda line: self.stdout.write(self.style.WARNING(f"  {line}")),
            )
        except analysis.AnalysisError as exc:
            raise CommandError(str(exc)) from exc

        out = (
            Path(options["out"]).expanduser() if options["out"] else runs_dir / "analysis"
        )
        written = analysis.write(
            dataset, out, bootstrap=max(0, options["bootstrap"]), seed=options["seed"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Analysed {len(dataset.rows)} item-condition record(s) across "
                f"{len(dataset.runs)} condition(s)."
            )
        )
        if dataset.unjudged:
            self.stdout.write(
                self.style.WARNING(
                    f"  {dataset.unjudged} successful generation(s) unjudged."
                )
            )
        if judge_missing is not None:
            self.stdout.write(
                f"  judge: {judge_missing.calls} call(s), {judge_missing.hits} cache hit(s)"
            )
        for path in written:
            self.stdout.write(f"  wrote {path}")
