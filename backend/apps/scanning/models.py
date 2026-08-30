"""The five operational scan tables — §5.1.

These are the *operational* half of the schema: they hold the current picture
of one repository and nothing older. §5.7's retention rule deletes a repo's
prior completed scan (and everything cascading from it) as soon as a newer one
finishes, because the permanent record lives in the research tables
(`scan_history`, `dependency_history`) which carry no foreign keys at all and
are never cascaded by any trigger (D9). Retention itself arrives in Phase 4
alongside the history writes it depends on — deleting the old scan before
there is anywhere permanent to put it would lose the data outright.

The columns divide cleanly in two, and the division is the whole point of D6:

* **Raw signals** — resolved version, latest version, release timestamps,
  staleness, deprecation text verbatim, CVE ids, CVSS scores, disclosure
  dates. Written by the scanner (Phase 3), never derived from one another.
* **Derived values** — `risk_component_score`, `is_flagged`, `risk_score`,
  `classification`. Pure functions of the raw signals under a named weights
  version, written by the scoring engine (Phase 4) and recomputable at any
  time from what is stored.

Phase 3 fills the first group and leaves the second null. That is not an
unfinished state: D6 says scoring is a pure function over stored signals, so a
scan that has recorded every signal is complete as a *measurement* whether or
not a formula has been applied to it yet.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Ecosystem(models.TextChoices):
    """§5.1's CHECK. PyPI is listed from the start (D1) though its adapter
    lands in Phase 6 — the constraint is part of the schema, not the adapter."""

    NPM = "npm", "npm"
    PYPI = "pypi", "PyPI"


class ScanStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"

    @classmethod
    def active(cls) -> tuple[str, str]:
        """The two states that mean "a scan is already happening here"."""
        return (cls.QUEUED.value, cls.RUNNING.value)

    @classmethod
    def terminal(cls) -> tuple[str, str]:
        return (cls.COMPLETED.value, cls.FAILED.value)


class TriggerType(models.TextChoices):
    INITIAL = "initial", "Initial"
    MANUAL = "manual", "Manual"


class Classification(models.TextChoices):
    SAFE = "safe", "Safe"
    MEDIUM = "medium", "Medium"
    HIGH_ALERT = "high_alert", "High alert"


class DependencyGroup(models.TextChoices):
    RUNTIME = "runtime", "Runtime"
    DEVELOPMENT = "development", "Development"
    OPTIONAL = "optional", "Optional"
    PEER = "peer", "Peer"
    BUILD = "build", "Build"
    UNKNOWN = "unknown", "Unknown"


class Resolution(models.TextChoices):
    """Where the version the signals were computed against came from.

    This is provenance, not quality — but the UI shows it, because the two are
    not the same claim. `lockfile` and `pinned` describe what is actually
    installed; `range_latest_approx` describes what the registry's newest
    release looks like, which is the closest honest answer available when a
    project declares a range and checks in no lockfile.
    """

    LOCKFILE = "lockfile", "From lockfile"
    PINNED = "pinned", "Pinned in manifest"
    RANGE_LATEST_APPROX = "range_latest_approx", "Approximated against latest"


class Severity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"
    UNKNOWN = "unknown", "Unknown"


#: Worst-first ordering, used to roll several vulnerabilities up into one
#: `highest_severity`. `unknown` sorts last: it is an absence of information,
#: not a claim that the vulnerability is mild.
SEVERITY_RANK: dict[str, int] = {
    Severity.CRITICAL.value: 4,
    Severity.HIGH.value: 3,
    Severity.MEDIUM.value: 2,
    Severity.LOW.value: 1,
    Severity.UNKNOWN.value: 0,
}


class ScanRunQuerySet(models.QuerySet):
    def with_counts(self):
        """Annotate manifest and dependency counts in one query.

        `distinct=True` on both because they share a join path: without it the
        manifest count is multiplied by the number of occurrences beneath it.
        """
        return self.annotate(
            manifest_count=models.Count("manifests", distinct=True),
            dependency_count=models.Count("manifests__occurrences", distinct=True),
        )


class ScanRun(models.Model):
    scan_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    repository = models.ForeignKey(
        "repositories.Repository",
        on_delete=models.CASCADE,
        related_name="scans",
    )
    # Scans run on the triggering user's own GitHub token (§8), so this column
    # records whose quota paid for the run, not merely who asked for it.
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="triggered_scans",
        db_column="triggered_by_user_id",
    )

    trigger_type = models.TextField(choices=TriggerType.choices)
    status = models.TextField(choices=ScanStatus.choices, default=ScanStatus.QUEUED)

    risk_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    classification = models.TextField(  # noqa: DJ001 — NULL means "not scored"
        choices=Classification.choices, null=True, blank=True
    )

    # §5.1 makes this NOT NULL: every scan states which formula applies to it.
    # Phase 3 writes `settings.WEIGHTS_VERSION`, whose default is the literal
    # string "unscored" until Phase 4 ships `weights_v0_equal.yaml` — a scan no
    # formula has touched should say so rather than borrow a version tag it
    # never ran under.
    scoring_formula_version = models.TextField()

    error_message = models.TextField(null=True, blank=True)  # noqa: DJ001

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScanRunQuerySet.as_manager()

    class Meta:
        db_table = "scan_runs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["repository", "-created_at"], name="scan_runs_repo_recent_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(trigger_type__in=TriggerType.values),
                name="scan_runs_trigger_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ScanStatus.values),
                name="scan_runs_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(risk_score__isnull=True)
                | models.Q(risk_score__gte=0, risk_score__lte=100),
                name="scan_runs_risk_score_range",
            ),
            models.CheckConstraint(
                condition=models.Q(classification__isnull=True)
                | models.Q(classification__in=Classification.values),
                name="scan_runs_classification_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repository_id} {self.status}"

    @property
    def is_active(self) -> bool:
        return self.status in ScanStatus.active()


class ManifestFile(models.Model):
    manifest_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(
        ScanRun, on_delete=models.CASCADE, related_name="manifests"
    )

    ecosystem = models.TextField(choices=Ecosystem.choices)
    # Repository-relative, e.g. `services/api/package.json`. Root manifests
    # carry no leading slash.
    manifest_path = models.TextField()
    # NULL when the manifest had no sibling lockfile, or it could not be read —
    # which is also what tells the UI why its rows say `range_latest_approx`.
    lockfile_path = models.TextField(null=True, blank=True)  # noqa: DJ001
    parser_name = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "manifest_files"
        ordering = ["manifest_path"]
        constraints = [
            models.UniqueConstraint(
                fields=["scan", "manifest_path"],
                name="manifest_files_unique_scan_path",
            ),
            models.CheckConstraint(
                condition=models.Q(ecosystem__in=Ecosystem.values),
                name="manifest_files_ecosystem_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.manifest_path


class Package(models.Model):
    """Identity only — deliberately no cached metadata (§5.1).

    Everything volatile (latest version, deprecation, release dates) lives on
    the occurrence, stamped with the scan that observed it. A `latest_version`
    column here would be a cache with no invalidation story, and it would make
    two scans a week apart indistinguishable in the history — which is exactly
    the signal the research needs (D17).
    """

    package_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ecosystem = models.TextField(choices=Ecosystem.choices)
    package_name = models.TextField()
    registry_url = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "packages"
        ordering = ["ecosystem", "package_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["ecosystem", "package_name"],
                name="packages_unique_ecosystem_name",
            ),
            models.CheckConstraint(
                condition=models.Q(ecosystem__in=Ecosystem.values),
                name="packages_ecosystem_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ecosystem}:{self.package_name}"


class DependencyOccurrence(models.Model):
    """One package, in one manifest, in one scan (§5.1).

    The same package declared by three manifests in a monorepo is three rows,
    not one row with a count. Each is an independent installation that has to
    be remediated separately — and §5.3's roll-up counts them independently by
    construction, which only works if they exist independently here.
    """

    dependency_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    manifest = models.ForeignKey(
        ManifestFile, on_delete=models.CASCADE, related_name="occurrences"
    )
    # RESTRICT per §5.1: `packages` is shared identity, so deleting one out
    # from under a live occurrence must be refused rather than cascade.
    package = models.ForeignKey(
        Package, on_delete=models.RESTRICT, related_name="occurrences"
    )

    dependency_group = models.TextField(
        choices=DependencyGroup.choices, default=DependencyGroup.RUNTIME
    )

    # ── what the project asked for, and what it actually gets ──────────────
    declared_specifier = models.TextField()
    resolved_version = models.TextField(null=True, blank=True)  # noqa: DJ001
    resolution = models.TextField(  # noqa: DJ001
        choices=Resolution.choices, null=True, blank=True
    )

    # ── registry state at scan time ────────────────────────────────────────
    latest_version = models.TextField(null=True, blank=True)  # noqa: DJ001
    latest_release_at = models.DateTimeField(null=True, blank=True)
    # NULL is "unknown", which §5.2 treats differently from zero: an unknown
    # staleness drops the term and redistributes its weight, where zero is an
    # informative "released today".
    staleness_days = models.IntegerField(null=True, blank=True)

    versions_behind_major = models.IntegerField(default=0)
    versions_behind_minor = models.IntegerField(default=0)
    versions_behind_patch = models.IntegerField(default=0)

    is_deprecated = models.BooleanField(default=False)
    # Stored exactly as the registry wrote it, however terse or empty. S3's
    # independent variable is the *information content* of this text (D2), so
    # normalizing it would destroy the measurement.
    deprecation_reason = models.TextField(null=True, blank=True)  # noqa: DJ001

    is_unassessable = models.BooleanField(default=False)
    unassessable_reason = models.TextField(null=True, blank=True)  # noqa: DJ001

    # ── vulnerability roll-up over `dependency_vulnerabilities` ────────────
    vulnerability_count = models.IntegerField(default=0)
    highest_severity = models.TextField(  # noqa: DJ001
        choices=Severity.choices, null=True, blank=True
    )
    cvss_max = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    cvss_reduced_confidence = models.BooleanField(default=False)

    # ── derived by the scoring engine (Phase 4); NULL until then ───────────
    risk_component_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    is_flagged = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dependency_occurrences"
        ordering = ["manifest__manifest_path", "package__package_name"]
        indexes = [
            models.Index(fields=["manifest"], name="dep_occ_manifest_idx"),
            models.Index(fields=["is_flagged"], name="dep_occ_flagged_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(dependency_group__in=DependencyGroup.values),
                name="dep_occ_group_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(resolution__isnull=True)
                | models.Q(resolution__in=Resolution.values),
                name="dep_occ_resolution_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(highest_severity__isnull=True)
                | models.Q(highest_severity__in=Severity.values),
                name="dep_occ_severity_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(vulnerability_count__gte=0),
                name="dep_occ_vuln_count_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(versions_behind_major__gte=0)
                & models.Q(versions_behind_minor__gte=0)
                & models.Q(versions_behind_patch__gte=0),
                name="dep_occ_versions_behind_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(risk_component_score__isnull=True)
                | models.Q(risk_component_score__gte=0, risk_component_score__lte=100),
                name="dep_occ_component_score_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.package_id}@{self.resolved_version or self.declared_specifier}"


class DependencyVulnerability(models.Model):
    vulnerability_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    dependency = models.ForeignKey(
        DependencyOccurrence, on_delete=models.CASCADE, related_name="vulnerabilities"
    )

    osv_id = models.TextField()
    cve_id = models.TextField(null=True, blank=True)  # noqa: DJ001
    severity = models.TextField(  # noqa: DJ001
        choices=Severity.choices, null=True, blank=True
    )
    cvss_score = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    # D17: the backfill engine's as-of filter needs the disclosure date, and it
    # cannot be recovered later for an advisory that has since been edited.
    published_at = models.DateTimeField(null=True, blank=True)

    summary = models.TextField(null=True, blank=True)  # noqa: DJ001
    affected_range = models.TextField(null=True, blank=True)  # noqa: DJ001
    # S3's ground truth: "the fix was to upgrade to X" is only checkable if X
    # was recorded at scan time.
    fixed_version = models.TextField(null=True, blank=True)  # noqa: DJ001
    source_url = models.TextField(null=True, blank=True)  # noqa: DJ001

    # §5.1 reserves this for Phase 12's flag-gated EPSS enrichment. The column
    # exists now because the table is created now, and an additive migration
    # later would buy nothing.
    epss_score = models.DecimalField(
        max_digits=6, decimal_places=5, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dependency_vulnerabilities"
        ordering = ["osv_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dependency", "osv_id"],
                name="dep_vuln_unique_dependency_osv_id",
            ),
            models.CheckConstraint(
                condition=models.Q(severity__isnull=True)
                | models.Q(severity__in=Severity.values),
                name="dep_vuln_severity_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.osv_id
