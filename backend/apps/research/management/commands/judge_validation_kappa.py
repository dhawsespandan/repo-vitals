"""`manage.py judge_validation_kappa` — WP-9's labels in, the judge's credibility out.

    python manage.py judge_validation_kappa --labels wp9_judge_labels.csv --key judge_validation_key.json

Checks the CSV the way File B's quality checks do (50/50 labelled, only the
three labels, every id from the packet), then reports Cohen's kappa between
the human and the judge, the linearly weighted kappa, the confusion matrix,
every disagreement with both notes, and File C §3.4.1's decision for the
number. Writes `judge_validation_kappa.md` beside the key. Reads files only.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.research.experiment import judge_validation


class Command(BaseCommand):
    help = "Cohen's kappa between WP-9's human labels and the judge."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--labels", required=True, metavar="wp9_judge_labels.csv")
        parser.add_argument("--key", required=True, metavar="judge_validation_key.json")

    def handle(self, *args, **options) -> None:
        key_path = Path(options["key"]).expanduser()
        try:
            key = json.loads(key_path.read_text(encoding="utf-8"))["items"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
            raise CommandError(
                f"{key_path} is not a judge-validation key: {exc}"
            ) from exc
        try:
            labels = judge_validation.read_labels(
                Path(options["labels"]).expanduser(), key
            )
        except judge_validation.ValidationPacketError as exc:
            raise CommandError(str(exc)) from exc

        result = judge_validation.kappa(labels, key)
        report = key_path.with_name("judge_validation_kappa.md")
        report.write_text(judge_validation.kappa_report(result), encoding="utf-8")
        value = "n/a" if result.kappa is None else f"{result.kappa:.3f}"
        self.stdout.write(self.style.SUCCESS(f"kappa = {value} over {result.n} items"))
        self.stdout.write(f"  {result.decision}")
        if result.missing_notes:
            self.stdout.write(
                self.style.WARNING(
                    f"  {len(result.missing_notes)} non-faithful label(s) without the "
                    f"required note: {', '.join(result.missing_notes)}"
                )
            )
        self.stdout.write(f"  wrote {report}")
