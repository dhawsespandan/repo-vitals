"""§5.1's `reports` table — cached LLM outputs.

One sentence governs everything here: **the UI always reads stored rows, never
live responses.** A generation is a background thread that writes a row; every
surface that displays a report reads that row back. Nothing renders a value
that came straight out of an HTTP response, which is what makes "second click
serves instantly with zero LLM calls" (§10 Phase 7) a property of the design
rather than a promise about caching behaviour.

Three structural rules, all enforced by constraints rather than by convention:

**A report belongs to a scan, and dies with it.** `ON DELETE CASCADE` to
`scan_runs`, so §5.7's retention destroys a scan's reports along with the
occurrences they describe. That is the intended behaviour and the reason
Phase 9 puts a confirmation in front of a rescan: a report is an *interpretation
of one measurement*, and keeping it beside a newer measurement would be a
statement about dependencies that may no longer be there. The permanent
research record is `agent_execution_traces` (Phase 8), which has no FK into
this table for exactly that reason.

**The type decides whether there is a dependency.** §5.1: `CHECK (combined <=>
dependency_id IS NULL)`. A combined report is repo-wide and cannot name one
occurrence; a per-dependency report is meaningless without one. Both halves of
the biconditional are checked, so neither a combined row carrying a dependency
nor a per-dependency row missing one can exist.

**One report per key.** Two partial uniques: one `combined` per scan, one
`per_dependency` per (scan, dependency). This is the cache key expressed as a
database constraint, and it is the last of the three layers that stop a
double-click billing two generations — the in-process lock closes the
millisecond race, the row's own status refuses the second request, and this
refuses anything that got past both.

Phase 7 writes only `combined` rows and fills `summary_text`, `fixes_json`,
`model_name` and `generated_at`. The retrieval columns (`citations_json`,
`retrieved_chunks_json`, `grounding_confidence`) and `project_context_json` are
declared now and left null: they are §5.1's schema, and a table that grows a
column per phase makes every earlier row's meaning depend on when it was
written.
"""

from __future__ import annotations

import uuid

from django.db import models


class ReportType(models.TextChoices):
    COMBINED = "combined", "Combined"
    PER_DEPENDENCY = "per_dependency", "Per dependency"


class ReportStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"

    @classmethod
    def active(cls) -> tuple[str, ...]:
        """The two that mean "come back in a moment"."""
        return (cls.QUEUED.value, cls.RUNNING.value)


class GroundingConfidence(models.TextChoices):
    """§5.9's deterministic verdict. Phase 8 fills it; a combined report has
    no retrieval to be confident about and leaves it null."""

    SUFFICIENT = "sufficient", "Sufficient"
    LOW = "low", "Low"


class Report(models.Model):
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    scan = models.ForeignKey(
        "scanning.ScanRun",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    #: Null for a combined report, and the constraint below makes that exact.
    dependency = models.ForeignKey(
        "scanning.DependencyOccurrence",
        on_delete=models.CASCADE,
        related_name="reports",
        null=True,
        blank=True,
    )

    report_type = models.TextField(choices=ReportType.choices)
    status = models.TextField(choices=ReportStatus.choices, default=ReportStatus.QUEUED)

    summary_text = models.TextField(null=True, blank=True)  # noqa: DJ001
    #: §5.8's `fixes` array, stored as the validated payload wrote it.
    fixes_json = models.JSONField(null=True, blank=True)
    #: Phase 8: which chunk ids the generation cited.
    citations_json = models.JSONField(null=True, blank=True)
    #: Phase 8: every chunk retrieved, cited or not — the pane beside the answer.
    retrieved_chunks_json = models.JSONField(null=True, blank=True)

    grounding_confidence = models.TextField(  # noqa: DJ001
        choices=GroundingConfidence.choices, null=True, blank=True
    )
    #: Phase 10: sibling shared-dependency lines plus the scope disclaimer.
    project_context_json = models.JSONField(null=True, blank=True)

    #: The model that actually answered, recorded per row rather than read from
    #: settings at display time. `GROQ_MODEL` can change between a generation
    #: and the page that renders it, and a report is evidence about one model.
    model_name = models.TextField(null=True, blank=True)  # noqa: DJ001
    error_message = models.TextField(null=True, blank=True)  # noqa: DJ001
    #: When the generation finished. Null until it does — the "cached" banner
    #: reads this, so a queued row has nothing to claim.
    generated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["scan", "report_type"], name="reports_scan_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(report_type__in=ReportType.values),
                name="reports_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ReportStatus.values),
                name="reports_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(grounding_confidence__isnull=True)
                | models.Q(grounding_confidence__in=GroundingConfidence.values),
                name="reports_grounding_confidence_valid",
            ),
            # §5.1's biconditional, written as the two implications it is made
            # of. Stating only "combined => dependency is null" would still
            # admit a per-dependency row with no dependency, which is the half
            # that actually breaks the drill-down.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        report_type=ReportType.COMBINED.value, dependency__isnull=True
                    )
                    | models.Q(
                        report_type=ReportType.PER_DEPENDENCY.value,
                        dependency__isnull=False,
                    )
                ),
                name="reports_dependency_matches_type",
            ),
            models.UniqueConstraint(
                fields=["scan"],
                condition=models.Q(report_type=ReportType.COMBINED.value),
                name="reports_one_combined_per_scan",
            ),
            models.UniqueConstraint(
                fields=["scan", "dependency"],
                condition=models.Q(report_type=ReportType.PER_DEPENDENCY.value),
                name="reports_one_per_dependency_per_scan",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report_type} {self.status} ({self.scan_id})"

    @property
    def is_active(self) -> bool:
        return self.status in ReportStatus.active()
