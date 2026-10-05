"""`manage.py scan_anchors` — the WP-2 anchor set, scanned as it is today.

    python manage.py scan_anchors --anchors wp2_anchor_set.csv

§10 Phase 12: "research-side current-state scan of the WP-2 CSV (fetch
manifests with PAT -> signals -> score; **no product registration**)". Each
repository goes through the corpus pipeline (`validation.anchors`), its
manifests are archived, and every occurrence's signals land in
`anchor_scan.json`, which `validate_formula` scores offline under each weights
version it compares.

**What it prints is what a WP-2 reviewer checks, and no score.** File B's
anchoring rule: bucket judgements are formed before anyone sees the formula's
output. So this command says whether each repository exists, whether each
known anchor's package was read at its version and how (pinned, lockfile, or a
range scored against the latest release, which does not count), whether it is
flagged and why, and how the CSV's lockfile and dependency-count claims compare
with what was read. Scores appear only in the validation report.

Needs `GITHUB_API_PAT` (zero scopes, §6). Writes files only.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.research.github import (
    RateBudgetExhausted,
    ResearchClient,
    ResearchCredentialMissing,
)
from apps.research.guards import no_operational_writes
from apps.research.validation import anchors
from apps.scoring.weights import active_weights

DEFAULT_OUT = "../research_data/validation_report/anchors"


class Command(BaseCommand):
    help = (
        "Scan the WP-2 anchor set through the corpus pipeline (no registration) "
        "and report what a WP-2 reviewer checks. Prints no scores."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--anchors", required=True, metavar="ANCHORS.csv")
        parser.add_argument("--out", default=DEFAULT_OUT, metavar="DIR")
        parser.add_argument("--no-wait", action="store_true")

    def handle(self, *args, **options) -> None:
        source = Path(options["anchors"]).expanduser()
        out = Path(options["out"]).expanduser()
        if not out.is_absolute():
            out = (Path(settings.BASE_DIR) / out).resolve()
        try:
            rows = anchors.read_anchor_set(source)
            client = ResearchClient.from_settings(wait_for_reset=not options["no_wait"])
            with no_operational_writes():
                scan = anchors.scan_anchor_set(
                    rows,
                    client,
                    out,
                    source=source,
                    progress=lambda line: self.stdout.write(f"  {line}"),
                )
        except (
            anchors.AnchorSetError,
            ResearchCredentialMissing,
            RateBudgetExhausted,
        ) as exc:
            raise CommandError(str(exc)) from exc

        # Flags only, under the active rule; the rule is score-independent
        # (§5.2), so printing it reveals nothing about any weight.
        results = anchors.evaluate(rows, scan, active_weights())
        self.stdout.write("")
        for result in results:
            if not result.row.is_known_anchor:
                continue
            target = f"{result.row.anchor_package}@{result.row.anchor_version}"
            if not result.scanned:
                line = f"not scanned ({result.scan.get('status')}: {result.scan.get('error', '')})"
            elif result.anchor_occurrence is None:
                line = (
                    "NOT SEEN at that version among the "
                    f"{result.observed_dependencies} declared dependencies read"
                )
            else:
                occurrence = result.anchor_occurrence
                line = (
                    f"seen in {occurrence['manifest_path']} ({occurrence['resolution']}); "
                    f"flags: {', '.join(result.anchor_flags) or 'NONE'}"
                )
            self.stdout.write(f"{result.row.full_name}: {target}: {line}")

        self.stdout.write("")
        for check in anchors.anchor_set_checks(rows, scan):
            marker = "ok   " if check.ok else "CHECK"
            self.stdout.write(f"[{marker}] {check.check}: {check.value}")
        self.stdout.write(f"\n  wrote {out / anchors.SCAN_FILENAME}")
