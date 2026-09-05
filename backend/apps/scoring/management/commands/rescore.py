"""`manage.py rescore` — D6's escape hatch, made concrete.

D6 states the property this command exists to preserve: *signals are persisted
raw, scoring is a pure function over stored signals*. That is what makes a
weight revision free and retroactive — every score the product ever showed can
be recomputed under any later weights version without rescanning a single
repository, because the inputs were never thrown away.

It also states the constraint: **history rows are never mutated by re-scoring.**
`dependency_history` is the evidence. A command that rewrote
`risk_component_score` in place under `v2` would destroy the ability to say
what the product actually reported to a user in March, and would make two
research runs under different versions overwrite each other. So this command
opens no write transaction at all. Its output is a materialized panel of files,
named for the version that produced it, which WP-6's sensitivity analysis and
the S1 validation harness read as ordinary data.

Nothing here is user-facing: no route, no serializer, no import from
request-handling code (§3, and the same discipline D13 puts around issue
search). It reads the permanent tables in whichever database `DATABASE_URL`
points at — prod's Supabase for live-scan rows, the teammate's research
Postgres for backfill (D8).

    python manage.py rescore --weights v1 --out ../research_data/exports/v1
    python manage.py rescore --weights v0_equal --out /tmp/naive --source live_scan

Two files land per run, plus a manifest recording exactly what was computed:

    <out>_occurrences.csv    one row per dependency_history row, recomputed
    <out>_repositories.csv   one row per scan_history row, rolled up
    <out>_manifest.json      weights, filters, counts, and when it ran
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scoring.engine import classify, is_flagged, roll_up, score_occurrence
from apps.scoring.signals import signals_for
from apps.scoring.weights import WeightsError, available_versions, load_weights

OCCURRENCE_COLUMNS = [
    "scan_history_id",
    "repo_full_name",
    "github_repo_id",
    "data_source",
    "snapshot_date",
    "scanned_at",
    "ecosystem",
    "package_name",
    "manifest_path",
    "dependency_group",
    "resolved_version",
    "is_unassessable",
    "is_deprecated",
    "vulnerability_count",
    "cvss_max",
    "staleness_days",
    # What this run computed, beside what was stored on the day. Both are
    # present so a reader can see the revision's effect without a join.
    "recomputed_score",
    "recomputed_penalty",
    "recomputed_flagged",
    "cvss_reduced_confidence",
    "stored_score",
    "stored_formula_version",
]

REPOSITORY_COLUMNS = [
    "scan_history_id",
    "repo_full_name",
    "github_repo_id",
    "github_username",
    "ecosystems",
    "data_source",
    "snapshot_date",
    "scanned_at",
    "dependency_count",
    "assessed_count",
    "recomputed_flagged_count",
    "recomputed_score",
    "recomputed_classification",
    "stored_score",
    "stored_classification",
    "stored_formula_version",
]

#: Snapshots are streamed a chunk at a time. The research database holds a few
#: million `dependency_history` rows after Phase 11's backfill (D8), and this
#: command has to run on the teammate's laptop.
CHUNK = 500


class Command(BaseCommand):
    help = (
        "Recompute scores from stored history signals under a named weights "
        "version, writing a materialized panel. Never writes to the database."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--weights",
            required=True,
            metavar="VERSION",
            help="Weights version to score under, e.g. v1 or v0_equal.",
        )
        parser.add_argument(
            "--out",
            required=True,
            metavar="PREFIX",
            help="Output path prefix; _occurrences.csv, _repositories.csv and "
            "_manifest.json are appended.",
        )
        parser.add_argument(
            "--source",
            choices=[*DataSource.values, "all"],
            default="all",
            help="Restrict to one data_source (default: all).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            metavar="N",
            help="Score at most N scan_history rows — useful for a smoke run.",
        )

    def handle(self, *args, **options) -> None:
        version = options["weights"]
        try:
            weights = load_weights(version)
        except WeightsError as exc:
            raise CommandError(
                f"{exc}\nAvailable versions: {', '.join(available_versions()) or 'none'}"
            ) from exc

        prefix = Path(options["out"]).expanduser()
        if prefix.parent and not prefix.parent.exists():
            prefix.parent.mkdir(parents=True, exist_ok=True)

        scans = ScanHistory.objects.all().order_by("scanned_at", "scan_history_id")
        if options["source"] != "all":
            scans = scans.filter(data_source=options["source"])
        if options["limit"]:
            scans = scans[: options["limit"]]

        occurrence_path = prefix.with_name(f"{prefix.name}_occurrences.csv")
        repository_path = prefix.with_name(f"{prefix.name}_repositories.csv")
        manifest_path = prefix.with_name(f"{prefix.name}_manifest.json")

        scan_count = 0
        occurrence_count = 0
        changed = 0

        with (
            occurrence_path.open("w", encoding="utf-8", newline="") as occurrence_file,
            repository_path.open("w", encoding="utf-8", newline="") as repository_file,
        ):
            occurrence_writer = csv.DictWriter(
                occurrence_file, fieldnames=OCCURRENCE_COLUMNS
            )
            occurrence_writer.writeheader()
            repository_writer = csv.DictWriter(
                repository_file, fieldnames=REPOSITORY_COLUMNS
            )
            repository_writer.writeheader()

            for scan in scans.iterator(chunk_size=CHUNK):
                rows = list(
                    DependencyHistory.objects.filter(scan_history=scan).order_by(
                        "manifest_path", "package_name"
                    )
                )
                penalties: list[Decimal] = []
                flagged = 0

                for row in rows:
                    occurrence_count += 1
                    if row.is_unassessable:
                        # §5.2: never scored, never flagged, excluded from every
                        # denominator. Still emitted, because the panel's whole
                        # value is that it accounts for every occurrence.
                        occurrence_writer.writerow(
                            self._occurrence_row(scan, row, None, False, False)
                        )
                        continue

                    signals = signals_for(row)
                    result = score_occurrence(signals, weights, row.ecosystem)
                    flag = is_flagged(signals, weights)
                    penalties.append(result.penalty)
                    flagged += int(flag)
                    occurrence_writer.writerow(
                        self._occurrence_row(
                            scan, row, result, flag, result.cvss_reduced_confidence
                        )
                    )

                repository = roll_up(penalties, weights)
                classification = classify(repository.score, weights)
                if repository.score != scan.risk_score:
                    changed += 1

                repository_writer.writerow(
                    {
                        "scan_history_id": str(scan.pk),
                        "repo_full_name": scan.repo_full_name,
                        "github_repo_id": scan.github_repo_id,
                        "github_username": scan.github_username,
                        "ecosystems": scan.ecosystems,
                        "data_source": scan.data_source,
                        "snapshot_date": scan.snapshot_date or "",
                        "scanned_at": scan.scanned_at.isoformat(),
                        "dependency_count": len(rows),
                        "assessed_count": repository.assessed_count,
                        "recomputed_flagged_count": flagged,
                        "recomputed_score": repository.score,
                        "recomputed_classification": classification,
                        "stored_score": scan.risk_score,
                        "stored_classification": scan.classification,
                        "stored_formula_version": scan.scoring_formula_version,
                    }
                )
                scan_count += 1

        manifest = {
            "generated_at": timezone.now().isoformat(),
            "weights_version": weights.version,
            "weights_derivation": weights.derivation,
            "weights_file": weights.path.name,
            "weights": {
                ecosystem: {name: str(weight) for name, weight in vector.items()}
                for ecosystem, vector in weights.weights.items()
            },
            "rollup": {
                "decay": str(weights.rollup.decay),
                "max_terms": weights.rollup.max_terms,
            },
            "thresholds": {
                "safe_min": str(weights.thresholds.safe_min),
                "medium_min": str(weights.thresholds.medium_min),
            },
            "filters": {"source": options["source"], "limit": options["limit"]},
            "scan_history_rows": scan_count,
            "dependency_history_rows": occurrence_count,
            "repository_scores_differing_from_stored": changed,
            # Stated in the artifact itself so a panel found on disk a year
            # from now cannot be mistaken for something the product served.
            "note": (
                "Recomputed from stored signals under the named weights version "
                "(D6). No database row was written or modified by this run; the "
                "stored_* columns are what the product reported at scan time."
            ),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Rescored {scan_count} scan(s) / {occurrence_count} occurrence(s) "
                f"under {weights.version}. {changed} repository score(s) differ "
                f"from what was stored."
            )
        )
        for path in (occurrence_path, repository_path, manifest_path):
            self.stdout.write(f"  wrote {path}")

    @staticmethod
    def _occurrence_row(
        scan: ScanHistory,
        row: DependencyHistory,
        result,
        flagged: bool,
        reduced_confidence: bool,
    ) -> dict:
        return {
            "scan_history_id": str(scan.pk),
            "repo_full_name": scan.repo_full_name,
            "github_repo_id": scan.github_repo_id,
            "data_source": scan.data_source,
            "snapshot_date": scan.snapshot_date or "",
            "scanned_at": scan.scanned_at.isoformat(),
            "ecosystem": row.ecosystem,
            "package_name": row.package_name,
            "manifest_path": row.manifest_path,
            "dependency_group": row.dependency_group,
            "resolved_version": row.resolved_version or "",
            "is_unassessable": row.is_unassessable,
            "is_deprecated": row.is_deprecated,
            "vulnerability_count": row.vulnerability_count,
            "cvss_max": "" if row.cvss_max is None else row.cvss_max,
            "staleness_days": "" if row.staleness_days is None else row.staleness_days,
            "recomputed_score": "" if result is None else result.score,
            "recomputed_penalty": "" if result is None else result.penalty,
            "recomputed_flagged": flagged,
            "cvss_reduced_confidence": reduced_confidence,
            "stored_score": ""
            if row.risk_component_score is None
            else row.risk_component_score,
            "stored_formula_version": scan.scoring_formula_version,
        }
