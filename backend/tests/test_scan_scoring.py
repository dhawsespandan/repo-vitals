"""The completion pipeline: score, record, retain (§5.2, §5.7, §10 Phase 4).

The engine's arithmetic is proved in `test_scoring_engine.py`. What is at stake
here is everything around it — which rows get written, which get deleted, and
in what order — because the pipeline's failure modes are not wrong numbers but
missing data, and a missing history row is unrecoverable.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.research.history import NotScored, record_scan
from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scanning.background import finalize
from apps.scanning.models import (
    DependencyOccurrence,
    ManifestFile,
    Package,
    ScanRun,
    ScanStatus,
)
from apps.scanning.retention import prune_prior_scans
from apps.scoring.signals import score_scan, top_contributors
from apps.scoring.weights import load_weights
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    RepositoryFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def repository(user):
    return RepositoryFactory(user=user, owner="acme", name="shop", full_name="acme/shop")


@pytest.fixture
def manifest(repository):
    return ManifestFileFactory(scan__repository=repository, scan__status="running")


def occurrence(manifest, name: str, **signals) -> DependencyOccurrence:
    return DependencyOccurrenceFactory(
        manifest=manifest, package__package_name=name, **signals
    )


def mixed_scan(manifest) -> ScanRun:
    """One deprecated-and-stale package, one vulnerable, one clean, one unassessable.

    Penalties under v1/npm, all computed in `test_scoring_engine.py`:
    56.00, 31.55, 0.00, and none at all.
    """
    occurrence(manifest, "request", is_deprecated=True, staleness_days=4000)
    occurrence(
        manifest,
        "lodash",
        vulnerability_count=2,
        cvss_max=Decimal("9.8"),
        staleness_days=100,
    )
    occurrence(manifest, "express", staleness_days=0)
    occurrence(
        manifest,
        "shared-utils",
        is_unassessable=True,
        unassessable_reason="file_specifier",
        declared_specifier="file:../shared",
        resolved_version=None,
        resolution=None,
        staleness_days=None,
    )
    return manifest.scan


class TestScoreScan:
    def test_the_scan_and_every_occurrence_get_their_derived_fields(self, manifest):
        scan = mixed_scan(manifest)
        result = score_scan(scan)

        scan.refresh_from_db()
        # rank 0: 56.00 · rank 1: 31.55*0.5 = 15.78 · rank 2: 0.00
        assert scan.risk_score == Decimal("28.22")
        assert scan.classification == "high_alert"
        assert scan.scoring_formula_version == "v1"
        assert result.assessed_count == 3
        assert result.unassessable_count == 1

        scores = {
            row.package.package_name: row.risk_component_score
            for row in DependencyOccurrence.objects.filter(
                manifest__scan=scan
            ).select_related("package")
        }
        assert scores["request"] == Decimal("44.00")
        assert scores["lodash"] == Decimal("68.45")
        assert scores["express"] == Decimal("100.00")
        # Not scored, not flagged, excluded from the roll-up entirely (§5.2).
        assert scores["shared-utils"] is None

    def test_the_flag_rule_is_applied_per_occurrence(self, manifest):
        scan = mixed_scan(manifest)
        score_scan(scan)
        flagged = set(
            DependencyOccurrence.objects.filter(
                manifest__scan=scan, is_flagged=True
            ).values_list("package__package_name", flat=True)
        )
        assert flagged == {"request", "lodash"}

    def test_an_unassessable_occurrence_is_never_flagged(self, manifest):
        # Even one that would trip the rule on its raw columns: it was not
        # assessed, so there is nothing to have a finding about.
        occurrence(
            manifest,
            "vendored",
            is_unassessable=True,
            unassessable_reason="git_specifier",
            is_deprecated=True,
            staleness_days=4000,
        )
        score_scan(manifest.scan)
        assert not DependencyOccurrence.objects.filter(is_flagged=True).exists()

    def test_the_placeholder_is_recorded_on_the_row_that_used_it(self, manifest):
        occurrence(manifest, "quiet-advisory", vulnerability_count=1, cvss_max=None)
        occurrence(
            manifest, "scored-advisory", vulnerability_count=1, cvss_max=Decimal("7.1")
        )
        score_scan(manifest.scan)
        rows = {
            row.package.package_name: row.cvss_reduced_confidence
            for row in DependencyOccurrence.objects.select_related("package")
        }
        assert rows == {"quiet-advisory": True, "scored-advisory": False}

    def test_scoring_the_same_scan_twice_is_identical(self, manifest):
        """§10 Phase 4: a rescan of an unchanged repository scores the same."""
        scan = mixed_scan(manifest)
        first = score_scan(scan)
        second = score_scan(scan)
        assert first == second

    def test_a_scan_with_no_occurrences_scores_100(self, manifest):
        result = score_scan(manifest.scan)
        assert result.risk_score == Decimal("100.00")
        assert result.classification == "safe"
        assert result.assessed_count == 0

    def test_a_different_weights_version_produces_a_different_number(self, manifest):
        scan = mixed_scan(manifest)
        under_v1 = score_scan(scan).risk_score
        under_v0 = score_scan(scan, load_weights("v0_equal")).risk_score
        assert under_v0 != under_v1
        scan.refresh_from_db()
        # The tag names the file that produced the number now stored (D5).
        assert scan.scoring_formula_version == "v0_equal"

    def test_a_pypi_manifest_is_scored_under_the_pypi_vector(self, repository):
        npm = ManifestFileFactory(
            scan__repository=repository, ecosystem="npm", manifest_path="package.json"
        )
        pypi = ManifestFileFactory(
            scan=npm.scan,
            ecosystem="pypi",
            manifest_path="pyproject.toml",
            lockfile_path=None,
            parser_name="pypi/pyproject.toml@1",
        )
        occurrence(npm, "left-pad", is_deprecated=True, staleness_days=0)
        DependencyOccurrenceFactory(
            manifest=pypi,
            package__package_name="nose",
            package__ecosystem="pypi",
            is_deprecated=True,
            staleness_days=0,
        )
        score_scan(npm.scan)
        scores = {
            row.package.package_name: row.risk_component_score
            for row in DependencyOccurrence.objects.select_related("package")
        }
        assert scores["left-pad"] == Decimal("54.00")  # 100 - 46 (npm)
        assert scores["nose"] == Decimal("68.00")  # 100 - 32 (pypi)


class TestTopContributors:
    def test_the_worst_occurrences_are_named_with_their_decayed_points(self, manifest):
        scan = mixed_scan(manifest)
        score_scan(scan)
        top = top_contributors(scan)
        assert [(c.package_name, c.points) for c in top] == [
            ("request", Decimal("56.00")),
            ("lodash", Decimal("15.78")),
        ]

    def test_a_clean_repository_names_nobody(self, manifest):
        occurrence(manifest, "express", staleness_days=0)
        score_scan(manifest.scan)
        # Every occurrence cost zero points; a strip listing them would be an
        # explanation of a score that needs none.
        assert top_contributors(manifest.scan) == []

    def test_the_strip_is_capped_at_three(self, manifest):
        for index in range(6):
            occurrence(manifest, f"bad-{index}", is_deprecated=True, staleness_days=0)
        score_scan(manifest.scan)
        assert len(top_contributors(manifest.scan)) == 3

    def test_ties_are_broken_deterministically(self, manifest):
        for name in ("zeta", "alpha", "middle"):
            occurrence(manifest, name, is_deprecated=True, staleness_days=0)
        score_scan(manifest.scan)
        names = [c.package_name for c in top_contributors(manifest.scan)]
        assert names == sorted(names)
        assert names == [c.package_name for c in top_contributors(manifest.scan)]


class TestHistory:
    def test_one_scan_history_row_and_one_row_per_occurrence(self, manifest):
        scan = mixed_scan(manifest)
        score_scan(scan)
        entry = record_scan(scan)

        assert ScanHistory.objects.count() == 1
        assert entry.source_scan_id == scan.pk
        assert entry.repo_full_name == "acme/shop"
        assert entry.github_user_id == scan.repository.user.github_user_id
        assert entry.risk_score == Decimal("28.22")
        assert entry.classification == "high_alert"
        assert entry.scoring_formula_version == "v1"
        assert entry.data_source == DataSource.LIVE_SCAN.value
        assert entry.ecosystems == "npm"
        assert entry.snapshot_date is None

        # Every occurrence, including the clean one and the unassessable one:
        # a hazard model needs the at-risk denominator, not only the events.
        assert entry.dependency_count == 4
        assert entry.flagged_dependency_count == 2
        assert DependencyHistory.objects.filter(scan_history=entry).count() == 4
        assert DependencyHistory.objects.filter(is_unassessable=True).count() == 1

    def test_the_raw_signals_are_copied_verbatim(self, manifest):
        occurrence(
            manifest,
            "request",
            is_deprecated=True,
            deprecation_reason="request has been deprecated, see #3142",
            staleness_days=2100,
            vulnerability_count=1,
            cvss_max=Decimal("6.1"),
            highest_severity="medium",
            versions_behind_major=3,
        )
        score_scan(manifest.scan)
        record_scan(manifest.scan)

        row = DependencyHistory.objects.get(package_name="request")
        assert row.deprecation_reason == "request has been deprecated, see #3142"
        assert row.staleness_days == 2100
        assert row.cvss_max == Decimal("6.1")
        assert row.highest_severity == "medium"
        assert row.versions_behind_major == 3
        assert row.manifest_path == "package.json"
        assert row.ecosystem == "npm"

    def test_an_unscored_scan_is_refused(self, manifest):
        # `scan_history.risk_score` is NOT NULL (§5.1); recording an unscored
        # scan would fail at the database with an error nobody could act on.
        with pytest.raises(NotScored):
            record_scan(mixed_scan(manifest))

    def test_a_polyglot_repository_records_both_ecosystems(self, repository):
        npm = ManifestFileFactory(scan__repository=repository)
        ManifestFileFactory(
            scan=npm.scan,
            ecosystem="pypi",
            manifest_path="requirements.txt",
            lockfile_path=None,
            parser_name="pypi/requirements.txt@1",
        )
        occurrence(npm, "express", staleness_days=0)
        DependencyOccurrenceFactory(
            manifest=npm.scan.manifests.get(ecosystem="pypi"),
            package__package_name="flask",
            package__ecosystem="pypi",
            staleness_days=0,
        )
        score_scan(npm.scan)
        assert record_scan(npm.scan).ecosystems == "npm,pypi"


class TestRetention:
    def test_a_new_scan_removes_the_previous_one_and_its_rows(self, repository):
        old = ManifestFileFactory(scan__repository=repository)
        occurrence(old, "express", staleness_days=0)
        old_scan = old.scan

        new = ManifestFileFactory(scan__repository=repository, scan__status="running")
        occurrence(new, "express", staleness_days=0)

        prune_prior_scans(new.scan)

        assert not ScanRun.objects.filter(pk=old_scan.pk).exists()
        assert ScanRun.objects.filter(pk=new.scan.pk).exists()
        assert ManifestFile.objects.count() == 1
        assert DependencyOccurrence.objects.count() == 1
        # Shared identity, never cascaded (§5.1's RESTRICT).
        assert Package.objects.filter(package_name="express").exists()

    def test_history_survives_retention(self, repository):
        old = ManifestFileFactory(scan__repository=repository, scan__status="running")
        occurrence(old, "request", is_deprecated=True, staleness_days=4000)
        score_scan(old.scan)
        record_scan(old.scan)

        new = ManifestFileFactory(scan__repository=repository, scan__status="running")
        occurrence(new, "request", is_deprecated=True, staleness_days=4000)
        prune_prior_scans(new.scan)

        assert not ScanRun.objects.filter(pk=old.scan.pk).exists()
        # D9: no foreign key reaches these rows, so no cascade can.
        assert ScanHistory.objects.count() == 1
        assert DependencyHistory.objects.count() == 1

    def test_another_repository_is_untouched(self, repository, user):
        other = RepositoryFactory(user=user, name="other", full_name="acme/other")
        other_scan = ScanRunFactory(repository=other)

        new = ManifestFileFactory(scan__repository=repository, scan__status="running")
        prune_prior_scans(new.scan)

        assert ScanRun.objects.filter(pk=other_scan.pk).exists()

    def test_a_superseded_failure_is_removed_too(self, repository):
        failed = ScanRunFactory(
            repository=repository,
            status=ScanStatus.FAILED.value,
            error_message="GitHub rate-limited this scan.",
        )
        new = ManifestFileFactory(scan__repository=repository, scan__status="running")
        prune_prior_scans(new.scan)
        assert not ScanRun.objects.filter(pk=failed.pk).exists()


class TestFinalize:
    """The three steps in the order §5.7 fixes: score, record, then delete."""

    def test_a_completed_scan_leaves_exactly_one_of_each(self, repository):
        previous = ManifestFileFactory(
            scan__repository=repository, scan__status="running"
        )
        occurrence(previous, "express", staleness_days=0)
        finalize(previous.scan)

        current = ManifestFileFactory(scan__repository=repository, scan__status="running")
        occurrence(current, "request", is_deprecated=True, staleness_days=4000)
        finalize(current.scan)

        assert ScanRun.objects.count() == 1
        assert ScanRun.objects.get().pk == current.scan.pk
        # Two scans happened, so two permanent records exist.
        assert ScanHistory.objects.count() == 2
        assert DependencyHistory.objects.count() == 2

        current.scan.refresh_from_db()
        assert current.scan.risk_score == Decimal("44.00")
        assert current.scan.classification == "high_alert"

    def test_history_is_written_before_the_previous_scan_is_deleted(
        self, repository, monkeypatch
    ):
        """The ordering is the safety argument, so it is asserted directly.

        Reversed, a failure between the two steps destroys the only copy of a
        repository's state. Both run in one transaction, and this proves the
        permanent row exists by the time the delete is reached.
        """
        previous = ManifestFileFactory(
            scan__repository=repository, scan__status="running"
        )
        occurrence(previous, "express", staleness_days=0)
        finalize(previous.scan)

        seen: list[int] = []
        from apps.scanning import background

        original = background.prune_prior_scans

        def spy(scan):
            seen.append(ScanHistory.objects.count())
            return original(scan)

        monkeypatch.setattr(background, "prune_prior_scans", spy)

        current = ManifestFileFactory(scan__repository=repository, scan__status="running")
        occurrence(current, "request", is_deprecated=True, staleness_days=4000)
        finalize(current.scan)

        assert seen == [2]

    def test_a_failure_in_history_leaves_the_previous_scan_intact(
        self, repository, monkeypatch
    ):
        previous = ManifestFileFactory(
            scan__repository=repository, scan__status="running"
        )
        finalize(previous.scan)

        from apps.scanning import background

        monkeypatch.setattr(
            background,
            "record_scan",
            lambda scan: (_ for _ in ()).throw(RuntimeError("supabase said no")),
        )

        current = ManifestFileFactory(scan__repository=repository, scan__status="running")
        with pytest.raises(RuntimeError):
            finalize(current.scan)

        assert ScanRun.objects.filter(pk=previous.scan.pk).exists()
        assert ScanHistory.objects.count() == 1
