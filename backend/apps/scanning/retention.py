"""§5.7 — only the latest scan's operational detail exists at any time.

The rule, in full: on scan completion, write `scan_history` +
`dependency_history` rows, *then* delete the repository's prior scans and
everything cascading from them (manifests, occurrences, vulnerabilities,
reports). This module is the second half; `apps.research.history` is the first,
and the ordering between them is the whole safety argument — the permanent copy
exists before the disposable one is destroyed. They run inside one transaction
at the call site so a failure between the two steps cannot leave a repository
with neither.

**Why delete at all.** Supabase's free tier is 500 MB (§8) and a scan of a
mid-sized monorepo is several hundred occurrence rows plus their advisories.
Keeping every scan of every repository forever would exhaust it, and would do
so with data that is already preserved — in denormalized, research-shaped form
— in the history tables. What is thrown away is a redundant copy, not a record.

**What is never touched.** `scan_history`, `dependency_history` and (from Phase
8) `agent_execution_traces` are not deleted by this or by any other trigger
(D9). They have no foreign key to anything here, so no cascade can reach them
even by accident.

**And what the cascade costs, which is Phase 9's business.** A report is an
interpretation of one measurement, so §5.7 destroys it along with the
measurement — correctly, and expensively, because regenerating one is a model
call. `reports_at_risk` below is the same question asked *before* the fact, so
a rescan that would throw away generated work can say so first. It belongs
here because it is the price of this module's rule, not a separate feature.

**One deliberate widening of the letter of §5.7.** The spec says "delete the
repo's prior *completed* scan_runs". This deletes prior scans whatever their
status, because a superseded failure is operational detail too: its
`error_message` describes a run that a later scan has since answered, nothing
in the UI reads it once a newer scan exists, and leaving failed rows behind
would let them accumulate without bound on a repository someone retried a
dozen times. The rule §5.7 states — only the latest scan's operational detail
survives — is served better by the wider deletion than by the narrower one.
Written up in `docs/decisions.md` §4.5.
"""

from __future__ import annotations

import logging

from .models import ScanRun

logger = logging.getLogger(__name__)


def prune_prior_scans(scan: ScanRun) -> int:
    """Delete every other scan of this scan's repository. Returns the count.

    Safe against deleting the scan that is being kept: it is excluded by
    primary key rather than by status, so a caller that has not yet marked the
    scan `completed` — which is exactly how the completion pipeline calls it —
    cannot lose the run it just finished.
    """
    doomed = ScanRun.objects.filter(repository_id=scan.repository_id).exclude(pk=scan.pk)
    deleted, _ = doomed.delete()
    if deleted:
        logger.info(
            "Retention removed prior scan rows for repository %s (%d row(s) "
            "including cascades).",
            scan.repository_id,
            deleted,
        )
    return deleted


def reports_at_risk(repository_id) -> int:
    """How many completed reports a rescan of this repository would destroy.

    §10 Phase 9's rescan confirmation is a *value-based* guard — it asks how
    much would be lost, not how recently the last scan ran — and this is the
    value. A repository with nothing generated rescans without a dialog,
    because there is nothing to warn about.

    Two decisions are in the query, and both are deliberate.

    **Every scan of the repository, not just the latest.** §5.7's cascade runs
    on *completion* and takes every prior scan with it, so the reports at risk
    are every report this repository holds. Normally that is the same set —
    retention leaves one scan standing — but not always: a scan that *fails*
    prunes nothing, so a repository can sit on a completed scan with reports
    plus a failed newer one. Counting only "the latest scan" there would answer
    zero about a rescan that is about to destroy two reports.

    **Completed reports only.** A queued, running or failed row has nothing in
    it for the reader to lose, and "this scan has 1 generated report" is a
    false sentence about a generation that failed. The count is the number of
    answers that exist, which is what the dialog claims it is.
    """
    # Imported here rather than at module scope: `apps.reports` imports the
    # scanning models, and this module is imported by `apps.scanning.background`
    # on the way in. A module-level import would close that loop.
    from apps.reports.models import Report, ReportStatus

    return Report.objects.filter(
        scan__repository_id=repository_id,
        status=ReportStatus.COMPLETED.value,
    ).count()
