"""The permanent tables — §5.1's `scan_history`, `dependency_history`, and
(from Phase 8) `agent_execution_traces`.

They live in their own app, and the app boundary is the point. D9 says these
rows never cascade on any trigger: not a rescan, not deleting a repository, not
deleting a user. Every other table in this project is operational and disposable
— §5.7 deletes a repository's previous scan the moment a newer one finishes.
These are the opposite: they are the study's raw data, and the whole reason it
is safe to throw the operational rows away.

Three properties follow from that and are enforced structurally rather than by
convention:

**No foreign keys out of this app.** `scan_history` has none at all,
`agent_execution_traces` has none at all, and `dependency_history`'s only FK
points at `scan_history` with `ON DELETE RESTRICT`. A cascade that reached
these tables would silently delete the evidence, and a cascade is easy to add
by accident — an FK to `repositories` would do it. There is no FK to add it to.
The trace table is the sharpest case: the `reports` row it records *does*
cascade with its scan (§5.7), so a foreign key there would delete the agent's
raw data every time a user pressed Rescan.

**Identifying fields are denormalized snapshots.** `github_username`,
`repo_full_name`, `package_name` and `manifest_path` are copied in as text at
write time. A repository renamed or deleted a year later does not rewrite
history, and a research query never has to join back to a live row that may no
longer exist.

**Every occurrence is recorded, including the clean and the unassessable
ones.** §5.1 is explicit and the reason is statistical: hazard models need the
at-risk denominator, not just the events. A history containing only bad rows
can tell you how many packages went bad and never what fraction that was.

`data_source` separates live product scans from Phase 11's reconstructed
monthly snapshots, which land in a different database entirely (D8) using these
same models — one schema, three contexts, selected by `DATABASE_URL`.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.scanning.models import (
    Classification,
    DependencyGroup,
    Ecosystem,
    Resolution,
    Severity,
)


class DataSource(models.TextChoices):
    """Where a history row came from (D14, D17).

    `backfill` rows are reconstructed as-of a month-end grid from the registry
    and OSV publication dates; `live_scan` rows are what a user's scan actually
    observed on the day. WP-10's agreement report exists precisely because the
    two are not interchangeable, so the column that tells them apart is not
    optional.
    """

    LIVE_SCAN = "live_scan", "Live scan"
    BACKFILL = "backfill", "Backfill"


class ScanHistory(models.Model):
    scan_history_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    #: Traceability only, deliberately not a ForeignKey (§5.1). The scan it
    #: names is normally already deleted by §5.7's retention by the time anyone
    #: reads this row; the id is kept because it is free and occasionally
    #: settles "did these two records come from the same run".
    source_scan_id = models.UUIDField(null=True, blank=True)

    github_user_id = models.BigIntegerField()
    github_username = models.TextField()
    github_repo_id = models.BigIntegerField()
    repo_full_name = models.TextField()

    #: Comma-joined and sorted, e.g. `npm` or `npm,pypi` — S3 groups by
    #: ecosystem, and a polyglot repository has to be identifiable as one.
    ecosystems = models.TextField()

    risk_score = models.DecimalField(max_digits=5, decimal_places=2)
    classification = models.TextField(choices=Classification.choices)

    dependency_count = models.IntegerField(default=0)
    flagged_dependency_count = models.IntegerField(default=0)

    scoring_formula_version = models.TextField()

    data_source = models.TextField(
        choices=DataSource.choices, default=DataSource.LIVE_SCAN
    )
    #: The month-end a backfill row reconstructs. NULL for a live scan, whose
    #: date is simply `scanned_at` — there is no grid to snap to.
    snapshot_date = models.DateField(null=True, blank=True)
    #: Corpus stratification weight (D14). NULL outside the backfill corpus.
    sampling_weight = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )

    scanned_at = models.DateTimeField()

    class Meta:
        db_table = "scan_history"
        ordering = ["-scanned_at"]
        indexes = [
            models.Index(
                fields=["github_repo_id", "snapshot_date"],
                name="scan_history_repo_date_idx",
            ),
            models.Index(fields=["data_source"], name="scan_history_source_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(risk_score__gte=0, risk_score__lte=100),
                name="scan_history_risk_score_range",
            ),
            models.CheckConstraint(
                condition=models.Q(classification__in=Classification.values),
                name="scan_history_classification_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(data_source__in=DataSource.values),
                name="scan_history_data_source_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(dependency_count__gte=0)
                & models.Q(flagged_dependency_count__gte=0),
                name="scan_history_counts_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.repo_full_name} {self.risk_score} @ {self.scanned_at:%Y-%m-%d}"


class DependencyHistory(models.Model):
    dependency_history_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    #: RESTRICT, not CASCADE (§5.1): deleting a scan_history row that still has
    #: dependency rows under it must be refused rather than quietly take them
    #: with it. There is no code path that deletes either — this is the guard
    #: against a future one written without reading D9.
    scan_history = models.ForeignKey(
        ScanHistory, on_delete=models.RESTRICT, related_name="dependencies"
    )

    ecosystem = models.TextField(choices=Ecosystem.choices)
    package_name = models.TextField()
    manifest_path = models.TextField()
    dependency_group = models.TextField(choices=DependencyGroup.choices)

    declared_specifier = models.TextField(null=True, blank=True)  # noqa: DJ001
    resolved_version = models.TextField(null=True, blank=True)  # noqa: DJ001
    resolution = models.TextField(  # noqa: DJ001
        choices=Resolution.choices, null=True, blank=True
    )
    latest_version = models.TextField(null=True, blank=True)  # noqa: DJ001

    staleness_days = models.IntegerField(null=True, blank=True)
    versions_behind_major = models.IntegerField(default=0)
    versions_behind_minor = models.IntegerField(default=0)
    versions_behind_patch = models.IntegerField(default=0)

    is_deprecated = models.BooleanField(default=False)
    #: Verbatim, never normalized — S3's independent variable is the
    #: information content of this exact text (D2).
    deprecation_reason = models.TextField(null=True, blank=True)  # noqa: DJ001

    vulnerability_count = models.IntegerField(default=0)
    highest_severity = models.TextField(  # noqa: DJ001
        choices=Severity.choices, null=True, blank=True
    )
    cvss_max = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)

    is_unassessable = models.BooleanField(default=False)

    #: The score as computed on the day, under the version named on the parent
    #: row. Kept for product display and for auditing what was shown; research
    #: recomputes from the raw signals beside it rather than trusting this
    #: (D6), which is why re-scoring never needs to write here.
    risk_component_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dependency_history"
        ordering = ["manifest_path", "package_name"]
        indexes = [
            models.Index(fields=["scan_history"], name="dep_history_scan_idx"),
            models.Index(
                fields=["package_name", "ecosystem"], name="dep_history_package_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ecosystem__in=Ecosystem.values),
                name="dep_history_ecosystem_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(vulnerability_count__gte=0),
                name="dep_history_vuln_count_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(risk_component_score__isnull=True)
                | models.Q(risk_component_score__gte=0, risk_component_score__lte=100),
                name="dep_history_component_score_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.package_name}@{self.resolved_version or self.declared_specifier}"


class AgentBranch(models.TextChoices):
    """§5.1's `branch_taken`, and the only two values §5.9's graph can produce.

    The branch is decided in `frame_query` on one fact: whether the registry
    gave a reason for deprecating this package. That fact is S3's independent
    variable — the study is about whether retrieved documentation improves a
    remediation plan, and a package that came with its own explanation is a
    materially different starting point from one that did not — so the branch
    is stored as a column rather than reconstructed later from the query text.
    """

    REASON_AVAILABLE = "reason_available", "Reason available"
    NO_REASON = "no_reason", "No reason"


class GroundingConfidence(models.TextChoices):
    """§5.9's deterministic verdict, duplicated here on purpose.

    `apps.reports.models` has the same two values, and the duplication is the
    point: this app has no foreign key into the operational schema and must not
    grow one (D9). A trace is readable with `apps.reports` deleted from the
    project, which is the state Phase 11's research database is actually in.
    """

    SUFFICIENT = "sufficient", "Sufficient"
    LOW = "low", "Low"


class AgentExecutionTrace(models.Model):
    """§5.1's `agent_execution_traces` — S3's raw data, kept forever.

    The table the study is actually about. Every other permanent row in this
    app records a *measurement*; this records a *run of the agent*: which
    branch it took, what it asked, everything it got back with the score
    attached, and what it produced.

    **Decoupled from the reports cascade, deliberately.** §10 Phase 8: "trace
    decoupled from the reports cascade so it survives rescans". A `reports` row
    dies with its scan under §5.7 because it is an interpretation of one
    measurement; a trace is an observation of the agent, and the agent's
    behaviour is not invalidated by the user rescanning their repository
    afterwards. `source_report_id` and `source_scan_id` are plain UUID columns
    for exactly that reason — by the time most of these are read, both rows
    they name are gone.

    **Every retrieved chunk, not only the cited ones.** §5.1 says so in as many
    words, and it is the difference between a dataset that can measure
    retrieval quality and one that can only measure the model's citation
    manners. A chunk that scored 0.31 and was ignored is evidence; a chunk that
    was never written down is not.
    """

    trace_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: Snapshots, deliberately not ForeignKeys (§5.1). Both rows they name are
    #: normally already gone: the report cascades with its scan, and the scan
    #: is deleted by the next one under §5.7.
    source_report_id = models.UUIDField(null=True, blank=True)
    source_scan_id = models.UUIDField(null=True, blank=True)

    github_user_id = models.BigIntegerField()
    repo_full_name = models.TextField()

    #: Denormalized so S3 groups from this table alone — §5.1 says exactly that
    #: about `ecosystem`, and the same argument carries the other two: the
    #: `packages` row may be deleted and the occurrence certainly will be.
    ecosystem = models.TextField(choices=Ecosystem.choices)
    package_name = models.TextField()
    resolved_version = models.TextField(null=True, blank=True)  # noqa: DJ001

    branch_taken = models.TextField(choices=AgentBranch.choices)

    #: The text `retrieve` embedded. Null only if the graph failed before
    #: framing, which `persist` cannot be reached from.
    retrieval_query = models.TextField(null=True, blank=True)  # noqa: DJ001

    #: ALL retrieved chunks with their similarity scores, not only the cited
    #: ones (§5.1). NOT NULL: an empty list is a finding — retrieval ran and
    #: found nothing — and null would make it indistinguishable from a trace
    #: written by code that forgot to record them.
    retrieved_chunks_json = models.JSONField(default=list)

    #: The final payload plus prompt and model metadata (§5.1).
    generation_json = models.JSONField(default=dict)

    grounding_confidence = models.TextField(choices=GroundingConfidence.choices)

    model_name = models.TextField(null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_execution_traces"
        ordering = ["-created_at"]
        indexes = [
            # S3's two grouping keys: by package across users, and by run date.
            models.Index(
                fields=["package_name", "ecosystem"], name="agent_trace_package_idx"
            ),
            models.Index(fields=["branch_taken"], name="agent_trace_branch_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ecosystem__in=Ecosystem.values),
                name="agent_trace_ecosystem_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(branch_taken__in=AgentBranch.values),
                name="agent_trace_branch_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(grounding_confidence__in=GroundingConfidence.values),
                name="agent_trace_grounding_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.package_name} [{self.branch_taken}/{self.grounding_confidence}]"
