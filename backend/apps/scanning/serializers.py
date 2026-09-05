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

from decimal import Decimal

from django.db.models import Count, Q
from rest_framework import serializers

from apps.scoring.signals import OccurrenceBreakdown, breakdown_for, top_contributors

from .models import (
    DependencyOccurrence,
    DependencyVulnerability,
    ManifestFile,
    ScanRun,
)


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


class DependencyVulnerabilitySerializer(serializers.ModelSerializer):
    """One advisory, as OSV reported it (§5.1).

    Nothing here is derived or reworded. `summary` is the advisory's own text,
    `affectedRange` and `fixedVersion` are its own strings, and `sourceUrl` is
    where a reader goes to check us. The panel's claim is that it is showing
    what a public database says, so paraphrasing any of it would quietly turn
    a citation into an assertion of our own.
    """

    id = serializers.UUIDField(source="vulnerability_id", read_only=True)
    osvId = serializers.CharField(source="osv_id", read_only=True)
    cveId = serializers.CharField(source="cve_id", read_only=True)
    cvssScore = serializers.DecimalField(
        source="cvss_score", max_digits=3, decimal_places=1, read_only=True
    )
    publishedAt = serializers.DateTimeField(source="published_at", read_only=True)
    affectedRange = serializers.CharField(source="affected_range", read_only=True)
    fixedVersion = serializers.CharField(source="fixed_version", read_only=True)
    sourceUrl = serializers.CharField(source="source_url", read_only=True)

    class Meta:
        model = DependencyVulnerability
        fields = [
            "id",
            "osvId",
            "cveId",
            "severity",
            "cvssScore",
            "publishedAt",
            "summary",
            "affectedRange",
            "fixedVersion",
            "sourceUrl",
        ]
        read_only_fields = fields


#: How many decimals a normalized term and an effective weight are reported to.
#:
#: Four, and the choice is load-bearing. Only one of the four terms is ever
#: inexact -- `min(days, 1095)/1095`; the other three are exact tenths -- and an
#: effective weight is inexact only when §5.2's redistribution has divided one.
#: At four decimals a reader multiplying the two columns and the factor of 100
#: reproduces the `points` beside them, which is the whole claim this panel
#: makes. Fewer would not; more would print noise as if it were measurement.
#:
#: The identity the page actually rests on is exact and independent of this:
#: §4.1 quantizes every term to two decimals *before* summing, so the points
#: column adds up to `deduction` to the hundredth, and `100 - deduction` is the
#: score, with no tolerance needed anywhere.
TERM_PLACES = Decimal("0.0001")


def _term_decimal(value: Decimal) -> str:
    return str(value.quantize(TERM_PLACES))


class DependencyBreakdownSerializer(DependencyOccurrenceSerializer):
    """`GET /api/dependencies/{id}/` — one occurrence, and why it scored that.

    The table row plus three things it deliberately leaves out: the per-signal
    arithmetic, the advisories behind the CVE count, and the manifest that
    declared the dependency. All three are here rather than on the list route
    because a table of 300 rows carrying nested advisories is a page-weight
    problem for information nobody has asked to see yet.

    **The arithmetic is recomputed, not read back.** §10 Phase 5 says so, and
    the reason is D6: the score is a pure function of stored signals under a
    named weights version, so the panel evaluates that function rather than
    reading four numbers somebody stored earlier. There is no per-term column
    in the schema to drift out of date, and a research rescore three years from
    now runs the same code path over the same signals.
    """

    scanId = serializers.UUIDField(source="manifest.scan_id", read_only=True)
    manifest = serializers.SerializerMethodField()
    scoring = serializers.SerializerMethodField()
    flagReasons = serializers.SerializerMethodField()
    vulnerabilities = serializers.SerializerMethodField()

    class Meta(DependencyOccurrenceSerializer.Meta):
        fields = [
            *DependencyOccurrenceSerializer.Meta.fields,
            "scanId",
            "manifest",
            "scoring",
            "flagReasons",
            "vulnerabilities",
        ]
        read_only_fields = fields

    def _breakdown(self, occurrence: DependencyOccurrence) -> OccurrenceBreakdown | None:
        """Evaluated once per occurrence, not once per field that wants it.

        Keyed by primary key rather than cached on the serializer: three fields
        ask for it, and a single-slot cache would hand every row of a `many=True`
        render the first row's arithmetic — correct today, because this
        serializer only ever serves one object, and wrong the first time it
        does not.
        """
        cache = getattr(self, "_breakdown_cache", None)
        if cache is None:
            cache = self._breakdown_cache = {}
        if occurrence.pk not in cache:
            cache[occurrence.pk] = breakdown_for(occurrence)
        return cache[occurrence.pk]

    def get_manifest(self, occurrence: DependencyOccurrence) -> dict:
        """Where the dependency was declared, and whether a lockfile was read.

        `lockfilePath` is the evidence behind the row's resolution tag. "From
        lockfile" and "approximated against latest" are materially different
        claims, and the second is only honest if a reader can see that there
        was no lockfile to read.
        """
        manifest = occurrence.manifest
        return {
            "id": str(manifest.manifest_id),
            "path": manifest.manifest_path,
            "ecosystem": manifest.ecosystem,
            "lockfilePath": manifest.lockfile_path,
            "parserName": manifest.parser_name,
        }

    def get_flagReasons(self, occurrence: DependencyOccurrence) -> list[str]:
        """Which clauses of §5.2's flag rule fired, as codes the UI phrases."""
        breakdown = self._breakdown(occurrence)
        return list(breakdown.flag_reasons) if breakdown else []

    def get_vulnerabilities(self, occurrence: DependencyOccurrence) -> list[dict]:
        """Worst first, so the advisory driving `cvssMax` is the one on top.

        Ordered by CVSS descending with nulls last, then by OSV id -- fully
        specified, because two advisories can share a score and an unstable
        order would reshuffle the chips on every page load.
        """
        rows = sorted(
            occurrence.vulnerabilities.all(),
            key=lambda row: (
                row.cvss_score is None,
                -(row.cvss_score or Decimal(0)),
                row.osv_id,
            ),
        )
        return DependencyVulnerabilitySerializer(rows, many=True).data

    def get_scoring(self, occurrence: DependencyOccurrence) -> dict | None:
        """§5.2 opened up: raw, normalized, weight, points, per signal.

        Null for an unassessable occurrence. That is the honest answer -- it
        was excluded from the score and from every denominator, so there is no
        arithmetic to show -- and `isUnassessable` with its reason is what the
        panel renders instead.
        """
        breakdown = self._breakdown(occurrence)
        if breakdown is None:
            return None

        return {
            "weightsVersion": breakdown.version,
            "ecosystem": breakdown.ecosystem,
            "score": str(breakdown.score),
            "deduction": str(breakdown.deduction),
            #: False only when the weights file behind this scan's version has
            #: changed since it ran. The panel says so rather than quietly
            #: showing arithmetic that contradicts the badge above it.
            "matchesStoredScore": breakdown.matches_stored,
            "cvssReducedConfidence": breakdown.cvss_reduced_confidence,
            # The caps travel with the numbers so the panel can say "3 of 10
            # CVEs" without hard-coding a bound the weights file owns (§5.4).
            "caps": {
                "cveCount": breakdown.cve_count_cap,
                "stalenessDays": breakdown.staleness_cap_days,
                "staleFlagDays": breakdown.stale_flag_days,
            },
            "terms": [
                {
                    "signal": term.signal,
                    "raw": _raw(term.raw),
                    "normalized": _term_decimal(term.normalized),
                    "weight": _term_decimal(term.weight),
                    "points": str(term.points),
                }
                for term in breakdown.terms
            ],
            "omitted": [
                {
                    "signal": omitted.signal,
                    "declaredWeight": _term_decimal(omitted.declared_weight),
                    "reason": omitted.reason,
                }
                for omitted in breakdown.omitted
            ],
        }


def _raw(value) -> bool | int | str | None:
    """A stored signal, in the JSON type it actually is.

    Decimals go out as strings like every other `NUMERIC` on this API; a CVSS
    of 9.8 through a float would arrive as 9.800000000000001 in some browser
    eventually, and this panel's entire argument is that its numbers are exact.
    """
    return str(value) if isinstance(value, Decimal) else value
