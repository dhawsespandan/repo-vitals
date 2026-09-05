"""`manage.py rescore` — D6's "recompute, never mutate", proved (§10 Phase 4).

The command's arithmetic is the engine's, tested exhaustively elsewhere. What
matters here is the discipline around it: that a revision under a different
weights version produces different numbers, that the artifact says which
version produced it, and above all that every stored row is left exactly as it
was found. A rescore that quietly rewrote history would destroy the record of
what the product actually reported on the day, and make two research runs
under different versions overwrite each other.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.research.history import record_scan
from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scoring.signals import score_scan
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    RepositoryFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def recorded(user):
    """One scan of the mixed fixture, scored under v1 and written to history.

    Penalties, all hand-computed in `test_scoring_engine.py`: 56.00, 31.55,
    0.00, and none at all for the unassessable row. Repository score 28.22.
    """
    repository = RepositoryFactory(
        user=user, owner="acme", name="shop", full_name="acme/shop"
    )
    manifest = ManifestFileFactory(scan__repository=repository, scan__status="running")

    def occurrence(name, **signals):
        return DependencyOccurrenceFactory(
            manifest=manifest, package__package_name=name, **signals
        )

    occurrence("request", is_deprecated=True, staleness_days=4000)
    occurrence(
        "lodash", vulnerability_count=2, cvss_max=Decimal("9.8"), staleness_days=100
    )
    occurrence("express", staleness_days=0)
    occurrence(
        "shared-utils",
        is_unassessable=True,
        unassessable_reason="file_specifier",
        declared_specifier="file:../shared",
        resolved_version=None,
        resolution=None,
        staleness_days=None,
    )
    score_scan(manifest.scan)
    return record_scan(manifest.scan)


def run(tmp_path, version="v1", **options):
    call_command("rescore", weights=version, out=str(tmp_path / "panel"), **options)


def rows_of(path):
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class TestRescore:
    def test_it_reproduces_the_stored_scores_under_the_same_version(
        self, recorded, tmp_path
    ):
        run(tmp_path)

        repositories = rows_of(tmp_path / "panel_repositories.csv")
        assert len(repositories) == 1
        assert (
            repositories[0]["recomputed_score"]
            == repositories[0]["stored_score"]
            == "28.22"
        )
        assert repositories[0]["recomputed_classification"] == "high_alert"
        assert repositories[0]["assessed_count"] == "3"

        occurrences = {
            row["package_name"]: row
            for row in rows_of(tmp_path / "panel_occurrences.csv")
        }
        assert len(occurrences) == 4
        assert occurrences["request"]["recomputed_score"] == "44.00"
        assert occurrences["lodash"]["recomputed_penalty"] == "31.55"
        # Unassessable rows are emitted with no score, never omitted: the
        # panel's value is that it accounts for every occurrence.
        assert occurrences["shared-utils"]["recomputed_score"] == ""
        assert occurrences["shared-utils"]["is_unassessable"] == "True"

    def test_a_different_version_produces_different_numbers_and_says_so(
        self, recorded, tmp_path
    ):
        run(tmp_path, version="v0_equal")

        row = rows_of(tmp_path / "panel_repositories.csv")[0]
        assert row["recomputed_score"] != row["stored_score"]
        assert row["stored_formula_version"] == "v1"

        manifest = json.loads(
            (tmp_path / "panel_manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["weights_version"] == "v0_equal"
        assert manifest["weights_derivation"] == "bootstrap-equal"
        assert manifest["repository_scores_differing_from_stored"] == 1
        assert manifest["dependency_history_rows"] == 4
        # Stated in the artifact itself, so a panel found on disk a year from
        # now cannot be mistaken for something the product served.
        assert "No database row was written" in manifest["note"]

    def test_it_never_writes_to_the_database(self, recorded, tmp_path):
        before = {
            row.pk: (row.risk_component_score, row.recorded_at)
            for row in DependencyHistory.objects.all()
        }
        stored_score = recorded.risk_score

        run(tmp_path, version="v0_equal")

        recorded.refresh_from_db()
        assert recorded.risk_score == stored_score
        assert recorded.scoring_formula_version == "v1"
        after = {
            row.pk: (row.risk_component_score, row.recorded_at)
            for row in DependencyHistory.objects.all()
        }
        assert after == before

    def test_every_score_in_the_panel_carries_two_decimals(self, recorded, tmp_path):
        """A repository that deducted nothing must not read `100` beside `99.45`.

        `NUMERIC(5,2)` normalizes it in the database, so the inconsistency is
        invisible everywhere except an artifact written straight from the
        engine — which is what this file is.
        """
        run(tmp_path)

        for row in rows_of(tmp_path / "panel_repositories.csv"):
            assert row["recomputed_score"].split(".")[1] == "22"
        for row in rows_of(tmp_path / "panel_occurrences.csv"):
            if row["recomputed_score"]:
                assert len(row["recomputed_score"].split(".")[1]) == 2

    def test_an_unknown_version_fails_loudly(self, recorded, tmp_path):
        with pytest.raises(CommandError, match="Available: "):
            run(tmp_path, version="v99")

    def test_the_source_filter_selects_one_data_source(self, recorded, tmp_path):
        ScanHistory.objects.create(
            source_scan_id=None,
            github_user_id=1,
            github_username="corpus",
            github_repo_id=2,
            repo_full_name="corpus/repo",
            ecosystems="npm",
            risk_score=Decimal("70.00"),
            classification="medium",
            dependency_count=0,
            flagged_dependency_count=0,
            scoring_formula_version="v1",
            data_source=DataSource.BACKFILL.value,
            snapshot_date=timezone.now().date(),
            scanned_at=timezone.now(),
        )

        run(tmp_path, source="backfill")

        assert [
            row["repo_full_name"] for row in rows_of(tmp_path / "panel_repositories.csv")
        ] == ["corpus/repo"]
