"""Scan serializers. camelCase to match `frontend/src/types/index.ts` (Phase 1).

Two shapes appear repeatedly and mean different things, so they are named
rather than inlined:

* **`ScanStateSerializer`** — a repository's newest scan, whatever its status.
  This is what a status pill and the polling loop read, and it is small on
  purpose because it is fetched every three seconds.
* **`ScanDetailSerializer`** — one scan and its manifests, fetched once when a
  detail page opens.

Neither exposes a database id that is not a UUID primary key, and every
queryset reaching them has already passed through `OwnedQuerySetMixin`.
"""

from __future__ import annotations

from django.db.models import Count, Q
from rest_framework import serializers

from apps.scoring.signals import top_contributors

from .models import DependencyOccurrence, ManifestFile, ScanRun


def annotated_scans():
    """`ScanRun` rows carrying the four counts every scan surface displays.

    Computed rather than stored: §5.1 puts these counts on `scan_history`, not
    on `scan_runs`, because a denormalized count on a live row is a second
    source of truth that can disagree with the rows it counts. `distinct=True`
    throughout — the counts share one join path, so without it each multiplies
    the others.
    """
    return ScanRun.objects.annotate(
        manifest_count=Count("manifests", distinct=True),
        dependency_count=Count("manifests__occurrences", distinct=True),
        unassessable_count=Count(
            "manifests__occurrences",
            filter=Q(manifests__occurrences__is_unassessable=True),
            distinct=True,
        ),
        flagged_count=Count(
            "manifests__occurrences",
            filter=Q(manifests__occurrences__is_flagged=True),
            distinct=True,
        ),
    )


class ScanStateSerializer(serializers.ModelSerializer):
    """One scan, small enough to poll. Counts default to 0 when unannotated."""

    id = serializers.UUIDField(source="scan_id", read_only=True)
    triggerType = serializers.CharField(source="trigger_type", read_only=True)
    startedAt = serializers.DateTimeField(source="started_at", read_only=True)
    completedAt = serializers.DateTimeField(source="completed_at", read_only=True)
    errorMessage = serializers.CharField(source="error_message", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    # Null until the scan completes and is scored. The UI shows no number
    # rather than a placeholder while they are (see `ScoreBadge`'s hollow ring):
    # a running scan has not measured anything yet, and a failed one never will.
    riskScore = serializers.DecimalField(
        source="risk_score", max_digits=5, decimal_places=2, read_only=True
    )
    scoringFormulaVersion = serializers.CharField(
        source="scoring_formula_version", read_only=True
    )

    manifestCount = serializers.IntegerField(source="manifest_count", default=0)
    #: Manifests found and not read. Surfaced because the dependency table
    #: otherwise claims completeness it does not have.
    skippedManifestCount = serializers.IntegerField(
        source="skipped_manifest_count", read_only=True
    )
    dependencyCount = serializers.IntegerField(source="dependency_count", default=0)
    unassessableCount = serializers.IntegerField(source="unassessable_count", default=0)
    flaggedCount = serializers.IntegerField(source="flagged_count", default=0)

    class Meta:
        model = ScanRun
        fields = [
            "id",
            "status",
            "triggerType",
            "classification",
            "riskScore",
            "scoringFormulaVersion",
            "errorMessage",
            "createdAt",
            "startedAt",
            "completedAt",
            "manifestCount",
            "skippedManifestCount",
            "dependencyCount",
            "unassessableCount",
            "flaggedCount",
        ]
        read_only_fields = fields


class ManifestSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="manifest_id", read_only=True)
    manifestPath = serializers.CharField(source="manifest_path", read_only=True)
    lockfilePath = serializers.CharField(source="lockfile_path", read_only=True)
    parserName = serializers.CharField(source="parser_name", read_only=True)
    dependencyCount = serializers.IntegerField(source="dependency_count", default=0)

    class Meta:
        model = ManifestFile
        fields = [
            "id",
            "ecosystem",
            "manifestPath",
            "lockfilePath",
            "parserName",
            "dependencyCount",
        ]
        read_only_fields = fields


#: How many occurrences the detail page names as the reason for the score.
#: §10 Phase 4 says three. It is a strip, not a list — the full accounting is
#: the dependency table directly beneath it, and Phase 5's breakdown after that.
TOP_CONTRIBUTOR_COUNT = 3


class ScanDetailSerializer(ScanStateSerializer):
    manifests = serializers.SerializerMethodField()
    topContributors = serializers.SerializerMethodField()

    class Meta(ScanStateSerializer.Meta):
        fields = [*ScanStateSerializer.Meta.fields, "manifests", "topContributors"]
        read_only_fields = fields

    def get_manifests(self, scan: ScanRun) -> list[dict]:
        manifests = scan.manifests.annotate(
            dependency_count=Count("occurrences")
        ).order_by("manifest_path")
        return ManifestSerializer(manifests, many=True).data

    def get_topContributors(self, scan: ScanRun) -> list[dict]:
        """Which occurrences cost this repository the most, and by how much.

        Computed here rather than in the browser even though the detail page
        already holds every dependency row. The roll-up's rank decay (§5.3) is
        the definition of the score, and a second implementation of it in
        TypeScript would be a second definition — free to drift from the one
        that produced the number on the badge beside it.

        Empty while the scan is unscored, and empty for a repository where
        nothing deducted anything: a strip naming three packages that each cost
        zero points would be an explanation of a score that needs none.
        """
        if scan.risk_score is None:
            return []
        return [
            {
                "dependencyId": contributor.dependency_id,
                "packageName": contributor.package_name,
                "manifestPath": contributor.manifest_path,
                "penalty": str(contributor.penalty),
                "points": str(contributor.points),
            }
            for contributor in top_contributors(scan, limit=TOP_CONTRIBUTOR_COUNT)
        ]


class DependencyOccurrenceSerializer(serializers.ModelSerializer):
    """One row of the dependency table.

    Deliberately without the vulnerability list: §5.5 gives that its own route
    (`GET /api/dependencies/{id}/`, Phase 5), and a table of 300 rows each
    carrying nested advisories is a page-weight problem for information nobody
    has asked to see yet. The count and the worst severity are enough for the
    badge, and both are already stored on the occurrence.
    """

    id = serializers.UUIDField(source="dependency_id", read_only=True)
    packageName = serializers.CharField(source="package.package_name", read_only=True)
    ecosystem = serializers.CharField(source="package.ecosystem", read_only=True)
    registryUrl = serializers.CharField(source="package.registry_url", read_only=True)
    manifestPath = serializers.CharField(source="manifest.manifest_path", read_only=True)
    group = serializers.CharField(source="dependency_group", read_only=True)
    declaredSpecifier = serializers.CharField(source="declared_specifier", read_only=True)
    resolvedVersion = serializers.CharField(source="resolved_version", read_only=True)
    latestVersion = serializers.CharField(source="latest_version", read_only=True)
    latestReleaseAt = serializers.DateTimeField(
        source="latest_release_at", read_only=True
    )
    stalenessDays = serializers.IntegerField(source="staleness_days", read_only=True)
    versionsBehind = serializers.SerializerMethodField()
    isDeprecated = serializers.BooleanField(source="is_deprecated", read_only=True)
    deprecationReason = serializers.CharField(source="deprecation_reason", read_only=True)
    isUnassessable = serializers.BooleanField(source="is_unassessable", read_only=True)
    unassessableReason = serializers.CharField(
        source="unassessable_reason", read_only=True
    )
    vulnerabilityCount = serializers.IntegerField(
        source="vulnerability_count", read_only=True
    )
    highestSeverity = serializers.CharField(source="highest_severity", read_only=True)
    cvssMax = serializers.DecimalField(
        source="cvss_max", max_digits=3, decimal_places=1, read_only=True
    )
    isFlagged = serializers.BooleanField(source="is_flagged", read_only=True)
    riskComponentScore = serializers.DecimalField(
        source="risk_component_score", max_digits=5, decimal_places=2, read_only=True
    )
    #: True when this row's severity term rests on §5.2's 5.0 placeholder
    #: because the advisory carried no CVSS anywhere. Surfaced rather than
    #: absorbed: the score is real, and the fact that part of it was assumed
    #: travels with it.
    cvssReducedConfidence = serializers.BooleanField(
        source="cvss_reduced_confidence", read_only=True
    )

    class Meta:
        model = DependencyOccurrence
        fields = [
            "id",
            "packageName",
            "ecosystem",
            "registryUrl",
            "manifestPath",
            "group",
            "declaredSpecifier",
            "resolvedVersion",
            "resolution",
            "latestVersion",
            "latestReleaseAt",
            "stalenessDays",
            "versionsBehind",
            "isDeprecated",
            "deprecationReason",
            "isUnassessable",
            "unassessableReason",
            "vulnerabilityCount",
            "highestSeverity",
            "cvssMax",
            "isFlagged",
            "riskComponentScore",
            "cvssReducedConfidence",
        ]
        read_only_fields = fields

    def get_versionsBehind(self, occurrence: DependencyOccurrence) -> dict:
        return {
            "major": occurrence.versions_behind_major,
            "minor": occurrence.versions_behind_minor,
            "patch": occurrence.versions_behind_patch,
        }
