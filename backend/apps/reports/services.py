"""Cache-or-generate: the rule that a scan is billed for at most one report.

§10 Phase 7 in one line: "cache-or-generate on `(scan, 'combined')` — hit
serves stored row; miss → per-key in-process generation lock → background
thread → polling. UI always reads stored rows."

The three layers behind "a double-click bills one generation" are the same
three `apps.scanning.background` uses for scans, and the reasoning transfers
without change:

* the **in-process lock** closes the millisecond race between two requests, which
  a status check alone cannot — there is a window between the read and the
  insert that a double-click fits through comfortably;
* the **row's own status** is what makes the answer correct across processes,
  because a lock is per process and one worker is a deployment fact rather than
  a guarantee;
* the **partial unique** in §5.1 refuses whatever got past both.

Two things differ from a scan, and both come from what is being protected.

**A failed report may be retried without a rescan.** A failed *scan* leaves
nothing to keep and a rescan is cheap; a failed report is one unlucky HTTP call
away from a rescan that would destroy the scan's results under §5.7. Forcing a
full rescan to retry a transient 503 would be absurd. So a `failed` row is
reset and regenerated in place. A `completed` one never is — that is the cache,
and §10 Phase 9's rescan confirmation exists precisely because clearing it is
destructive.

**Generation is bounded by the LLM's own timeouts**, so a row presumed dead is
presumed dead sooner than a scan is: `STALE_GENERATION_AFTER` is minutes, not
the scanner's fifteen. A worker restarted mid-generation must not leave a
report spinning forever behind its own 409.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone

# Imported as a module, not as a name. `from ... import spawn` would bind the
# function at import time, and the test suite's `no_background_threads` fixture
# — which patches `background.spawn` so a test never races a real thread —
# would silently stop applying here. It did, and the first run of the
# double-click test spawned a real thread that deadlocked SQLite.
from apps.scanning import background
from apps.scanning.models import ScanRun, ScanStatus

from .combined import GenerationFailed, generate
from .llm.groq_client import (
    LlmModelUnavailable,
    LlmNotConfigured,
    LlmRefused,
    LlmTruncated,
    LlmUnavailable,
    is_configured,
)
from .models import Report, ReportStatus, ReportType

logger = logging.getLogger(__name__)

#: How long a `queued`/`running` report may sit before it is presumed dead.
#: A generation is at most four HTTP requests at a 60 s read timeout, so five
#: minutes is past any honest slow path and short enough that a killed worker
#: does not strand the button for a quarter of an hour.
STALE_GENERATION_AFTER = timedelta(minutes=5)

#: What a generation that never reported back says for itself.
STALLED_MESSAGE = "This report stopped before it finished. Please generate it again."

#: Failure text is written for the person looking at the panel, so each one
#: names what to do next. The internal detail stays in the logs: an exception
#: message can carry upstream text, ids, or the shape of a key.
#:
#: A list of pairs rather than a dict keyed on the exact class, so a subclass
#: added later inherits its parent's message instead of silently falling
#: through to the generic one. `LlmNotConfigured` and `LlmRefused` deliberately
#: share text: both are deployment faults, and neither is something to explain
#: to the person who pressed the button.
FAILURE_MESSAGES: tuple[tuple[type[Exception], str], ...] = (
    (
        LlmUnavailable,
        "We couldn't reach the report service. Please try again in a few minutes.",
    ),
    (
        LlmTruncated,
        "The report came back incomplete. Please try again.",
    ),
    (
        # All three are deployment faults - a bad key, no key, or a model that
        # no longer exists - and none of them is something to explain to the
        # person who pressed the button. The log line carries the detail.
        (LlmRefused, LlmNotConfigured, LlmModelUnavailable),  # type: ignore[arg-type]
        "Report generation isn't available right now. Please try again later.",
    ),
    (
        GenerationFailed,
        "We couldn't produce a reliable report for this scan. Please try again.",
    ),
)
GENERIC_FAILURE = "Something went wrong while writing this report. Please try again."


class GenerationInProgress(Exception):
    """A generation for this key is already queued or running."""

    def __init__(self, report: Report) -> None:
        super().__init__(f"A report is already being generated for {report.scan_id}.")
        self.report = report


class ScanNotReportable(Exception):
    """The scan has no results to report on — it never completed, or it failed."""


class ReportsUnavailable(Exception):
    """The deployment has no generator configured. Not the user's problem."""


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    """One lock per cache key, created on first use.

    The dict needs its own lock for the same reason `background._lock_for`'s
    does: two threads racing to create the *same* key's lock would each get
    their own, which is no lock at all. Entries are never removed — a
    `threading.Lock` per scan a process has generated for is a few dozen bytes,
    and a removal path would reintroduce the race this guard closes.
    """
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def combined_key(scan_id) -> str:
    return f"combined:{scan_id}"


def expire_stale(scan: ScanRun) -> int:
    """Fail every generation for this scan old enough to be presumed dead.

    Called from the read path as well as the request path, deliberately: a
    report whose worker was restarted mid-call would otherwise sit on a spinner
    until someone thought to reload. One UPDATE that normally matches nothing
    is a cheap price for a panel that repairs itself.
    """
    now = timezone.now()
    stalled = Report.objects.filter(
        scan=scan,
        status__in=ReportStatus.active(),
        created_at__lt=now - STALE_GENERATION_AFTER,
    ).update(status=ReportStatus.FAILED.value, error_message=STALLED_MESSAGE)
    if stalled:
        logger.warning("Marked %d stalled report generation(s) failed.", stalled)
    return stalled


def combined_for(scan: ScanRun) -> Report | None:
    """The stored combined report for a scan, if there is one.

    The read path. Every surface that displays a report goes through here or
    through the report's own detail route — never through a generation's return
    value — which is what "the UI always reads stored rows" means in practice.
    """
    expire_stale(scan)
    return Report.objects.filter(scan=scan, report_type=ReportType.COMBINED.value).first()


def request_combined(scan: ScanRun) -> tuple[Report, bool]:
    """Serve the cached report, or start one. Returns `(report, was_cached)`.

    Raises `GenerationInProgress` for the 409, `ScanNotReportable` when there
    are no results to describe, and `ReportsUnavailable` when the deployment
    has no key.
    """
    if scan.status != ScanStatus.COMPLETED.value:
        raise ScanNotReportable(
            "A report can only be generated from a scan that finished."
        )

    key = combined_key(scan.pk)
    with _lock_for(key):
        expire_stale(scan)
        existing = Report.objects.filter(
            scan=scan, report_type=ReportType.COMBINED.value
        ).first()

        if existing is not None:
            if existing.status == ReportStatus.COMPLETED.value:
                # The whole point of the phase: a second click costs nothing.
                return existing, True
            if existing.is_active:
                raise GenerationInProgress(existing)
            # Failed. Retried in place — see the module docstring.
            if not is_configured():
                raise ReportsUnavailable("GROQ_API_KEY is not set.")
            existing.status = ReportStatus.QUEUED.value
            existing.error_message = None
            existing.save(update_fields=["status", "error_message", "updated_at"])
            report = existing
        else:
            if not is_configured():
                raise ReportsUnavailable("GROQ_API_KEY is not set.")
            try:
                report = Report.objects.create(
                    scan=scan,
                    report_type=ReportType.COMBINED.value,
                    status=ReportStatus.QUEUED.value,
                )
            except IntegrityError as clash:
                # §5.1's partial unique, doing the job the lock cannot: another
                # process created the row between our read and our insert. The
                # row that won is the answer.
                logger.info("A concurrent process created this scan's report first.")
                winner = Report.objects.filter(
                    scan=scan, report_type=ReportType.COMBINED.value
                ).first()
                if winner is None:  # pragma: no cover — the row must exist
                    raise
                if winner.status == ReportStatus.COMPLETED.value:
                    return winner, True
                raise GenerationInProgress(winner) from clash

    background.spawn(run_combined, report.pk)
    return report, False


def run_combined(report_id) -> None:
    """The thread body: generate, then write the row. Never raises.

    Mirrors `background.execute` — the generation does the work, this owns the
    lifecycle — so a failure at any point leaves a row that says what happened
    rather than a row stuck on `running` forever.
    """
    try:
        report = Report.objects.select_related("scan", "scan__repository").get(
            pk=report_id
        )
    except Report.DoesNotExist:
        # The scan was replaced by retention (§5.7) between the request and the
        # thread starting, and the report cascaded with it. Nothing to do.
        return

    report.status = ReportStatus.RUNNING.value
    report.save(update_fields=["status", "updated_at"])

    try:
        result = generate(report.scan)
    # Broad on purpose: this is the top of a background thread, so an
    # exception that escapes here is lost and the row stays `running`
    # until `expire_stale` reaps it. `_fail` decides what the reader sees.
    except Exception as failure:
        _fail(report, failure)
        return

    report.status = ReportStatus.COMPLETED.value
    report.summary_text = result.payload["summary_md"]
    report.fixes_json = result.payload["fixes"]
    report.model_name = result.model_name
    report.error_message = None
    report.generated_at = timezone.now()
    report.save(
        update_fields=[
            "status",
            "summary_text",
            "fixes_json",
            "model_name",
            "error_message",
            "generated_at",
            "updated_at",
        ]
    )
    logger.info(
        "Generated combined report %s for scan %s in %d request(s).",
        report.pk,
        report.scan_id,
        result.requests,
    )


def _fail(report: Report, failure: Exception) -> None:
    message = GENERIC_FAILURE
    for kinds, text in FAILURE_MESSAGES:
        if isinstance(failure, kinds):
            message = text
            break

    if message is GENERIC_FAILURE:
        # An unrecognised exception is a bug, not a known upstream condition,
        # so the traceback is kept where a developer will find it.
        logger.exception("Report %s raised an unexpected error.", report.pk)
    else:
        logger.info("Report %s failed: %s", report.pk, failure)

    report.status = ReportStatus.FAILED.value
    report.error_message = message
    report.save(update_fields=["status", "error_message", "updated_at"])
