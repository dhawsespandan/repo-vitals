"""Fire-and-forget scan threads, and the lock that keeps them from colliding.

§2 rules out Celery and Redis, and §8 rules out a second Render service, so
background work is threads inside the one gunicorn worker. That is a perfectly
sound arrangement at this scale — `gthread` with 8 threads is chosen in §3
precisely for the mixed request-plus-background pattern — but it has two sharp
edges that are cheap to handle here and expensive to debug later.

**Database connections are not thread-safe to share.** Django keeps one
connection per thread in a thread-local, so a new thread opens its own. What it
does *not* do is close it: a thread that exits leaves its connection behind,
and with `CONN_MAX_AGE = 60` those accumulate against Supabase's free-tier
connection limit until new work cannot connect at all. `close_old_connections()`
at both ends is the documented remedy — at the start because the thread may
inherit a connection closed by the server while it was idle, and at the end
because nothing else will ever tidy up after it.

**Two scans of one repository must not run at once.** The check is in two
layers, and both are needed. The in-process `threading.Lock` closes the race
between two requests arriving in the same millisecond — a database status check
alone has a window between the read and the insert that a double-click fits
through comfortably. The database status check is what makes the answer
*correct*: the lock is per process, and while one worker is the deployed
topology (§8: exactly one always-on service), a rule enforced only by a
process-local lock would quietly stop being enforced the day that changes.

**A scan can die without finishing.** Render restarts free instances at will,
and a killed process leaves a row saying `running` with nobody running it —
which would otherwise wedge that repository forever behind a 409. Any active
scan older than `STALE_SCAN_AFTER` is treated as dead: it stops blocking new
work, and the new scan marks it failed on the way past.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import timedelta

from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.research.history import record_scan
from apps.scoring.signals import score_scan
from apps.scoring.weights import active_weights

from .models import ScanRun, ScanStatus, TriggerType
from .retention import prune_prior_scans
from .scanner import ScanFailed, run_scan

logger = logging.getLogger(__name__)

#: How long a `queued`/`running` scan may sit before it is presumed dead. A
#: real scan of a repository at this product's scale finishes in under two
#: minutes (§10 Phase 3 acceptance); fifteen is generous enough that a slow
#: upstream is never mistaken for a crash.
STALE_SCAN_AFTER = timedelta(minutes=15)

#: Shown when a scan failed for a reason with no user-facing remedy. Internal
#: detail stays in the logs: an exception message is written for developers and
#: can carry paths, ids or upstream text that has no business in a browser.
GENERIC_FAILURE = "Something went wrong while scanning this repository. Please try again."


class ScanInProgress(Exception):
    """A scan is already queued or running for this repository."""

    def __init__(self, scan: ScanRun) -> None:
        super().__init__(f"A scan is already in progress for {scan.repository_id}.")
        self.scan = scan


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(repository_id) -> threading.Lock:
    """One lock per repository, created on first use.

    The dict itself needs a lock: two threads racing to create the *same*
    repository's lock would otherwise each get their own, which is no lock at
    all. Entries are never removed — one `threading.Lock` per repository a
    process has ever scanned is a few dozen bytes, and a removal path would
    reintroduce exactly the race this guard closes.
    """
    key = str(repository_id)
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


#: What a scan that never reported back says for itself.
STALLED_MESSAGE = "This scan stopped before it finished. Please run it again."


def expire_stale(repository_ids) -> int:
    """Fail every active scan old enough to be presumed dead. Returns the count.

    Called from the read path as well as the trigger path, and deliberately so:
    a repository whose worker was restarted mid-scan would otherwise sit on a
    spinner until someone thought to press Run scan again. One `UPDATE` that
    normally matches nothing is a cheap price for a UI that repairs itself.
    """
    ids = list(repository_ids)
    if not ids:
        return 0
    now = timezone.now()
    stalled = ScanRun.objects.filter(
        repository_id__in=ids,
        status__in=ScanStatus.active(),
        created_at__lt=now - STALE_SCAN_AFTER,
    ).update(
        status=ScanStatus.FAILED.value,
        error_message=STALLED_MESSAGE,
        completed_at=now,
    )
    if stalled:
        logger.warning("Marked %d stalled scan(s) failed.", stalled)
    return stalled


def active_scan(repository_id) -> ScanRun | None:
    """The live scan for a repository, ignoring ones presumed dead."""
    cutoff = timezone.now() - STALE_SCAN_AFTER
    return (
        ScanRun.objects.filter(
            repository_id=repository_id,
            status__in=ScanStatus.active(),
            created_at__gte=cutoff,
        )
        .order_by("-created_at")
        .first()
    )


def start_scan(repository, user, trigger_type: str = TriggerType.MANUAL.value) -> ScanRun:
    """Create a queued scan and hand it to a thread. Raises `ScanInProgress`.

    The lock is held across the check *and* the insert, and released as soon as
    the row exists — from then on the row's own status is what refuses a second
    trigger. Holding it for the whole scan would serialize every repository
    behind whichever one is slowest to answer, since the lock is per repository
    but the thread pool is not.
    """
    lock = _lock_for(repository.pk)
    with lock:
        expire_stale([repository.pk])
        existing = active_scan(repository.pk)
        if existing is not None:
            raise ScanInProgress(existing)

        scan = ScanRun.objects.create(
            repository=repository,
            triggered_by=user,
            trigger_type=trigger_type,
            status=ScanStatus.QUEUED.value,
            # The version active when the row was created. `score_scan`
            # re-stamps it with the file that actually produced the number, so
            # a queued or failed scan still names a real formula and a
            # completed one names the formula it was scored under.
            scoring_formula_version=active_weights().version,
        )

    spawn(execute, scan.pk)
    return scan


def spawn(target: Callable, *args) -> threading.Thread:
    """Run `target` on a daemon thread with connection hygiene at both ends.

    Daemon so a deploy or a restart is never held open by a scan in flight: the
    row is left `running`, and `expire_stale` releases it on the next read or trigger.
    Losing a scan to a restart is recoverable; refusing to shut down is not.
    """

    def wrapper() -> None:
        close_old_connections()
        try:
            target(*args)
        except Exception:
            # Nothing above this frame will ever see the exception, so it is
            # logged here or it is lost entirely.
            logger.exception("Background task failed.")
        finally:
            close_old_connections()

    thread = threading.Thread(target=wrapper, daemon=True, name="repovitals-scan")
    thread.start()
    return thread


def execute(scan_id) -> None:
    """Run one scan, recording every status transition it passes through.

    The scanner does the measurement; this owns the lifecycle. Keeping them
    apart means the scanner can be called directly in a test without a thread,
    a status machine, or an exception-handling policy in the way.
    """
    try:
        scan = ScanRun.objects.select_related("repository", "triggered_by").get(
            pk=scan_id
        )
    except ScanRun.DoesNotExist:
        # The repository was deleted between the trigger and the thread
        # starting; the scan cascaded with it. Nothing to do and nothing wrong.
        return

    scan.status = ScanStatus.RUNNING.value
    scan.started_at = timezone.now()
    scan.save(update_fields=["status", "started_at"])

    try:
        run_scan(scan)
    except ScanFailed as failure:
        _finish(scan, ScanStatus.FAILED.value, str(failure))
        logger.info("Scan %s failed: %s", scan.pk, failure)
        return
    except Exception:
        logger.exception("Scan %s raised an unexpected error.", scan.pk)
        _finish(scan, ScanStatus.FAILED.value, GENERIC_FAILURE)
        return

    # The measurement succeeded. Stamped now so `scan_history.scanned_at` and
    # `scan_runs.completed_at` name the same instant rather than two instants a
    # few hundred milliseconds apart.
    scan.completed_at = timezone.now()
    try:
        finalize(scan)
    except Exception:
        logger.exception("Scan %s could not be finalized.", scan.pk)
        _finish(scan, ScanStatus.FAILED.value, GENERIC_FAILURE)
        return

    _finish(scan, ScanStatus.COMPLETED.value, None)


def finalize(scan: ScanRun) -> None:
    """Score the scan, record it permanently, then retire the one it replaces.

    §10 Phase 4's completion pipeline, and the order is §5.7's: history rows
    are written *before* the previous scan is deleted, so the permanent copy
    exists before the disposable one is destroyed.

    History and retention share one transaction; scoring gets its own. That
    split is deliberate. Scoring only rewrites derived columns on rows that
    already exist, so it is safe to have committed on its own — and if the
    write-then-delete pair fails, the scan is marked failed with its signals
    scored and its previous scan intact, which is a recoverable state. Rolling
    the score back too would buy nothing and lose the diagnosis.

    A failure anywhere here fails the scan. A scan that measured a repository
    but could not score it has no number to show, and a completed row with a
    null `risk_score` would render as a blank badge with no explanation — the
    silent-miscount shape this product exists to avoid. Better a visible
    failure with a Try again beside it.
    """
    score_scan(scan)
    with transaction.atomic():
        record_scan(scan)
        prune_prior_scans(scan)


def _finish(scan: ScanRun, status: str, error_message: str | None) -> None:
    scan.status = status
    scan.error_message = error_message
    # Preserved when the completion path already stamped it, so the timestamp
    # in `scan_history` and the one on the scan row agree exactly.
    scan.completed_at = scan.completed_at or timezone.now()
    scan.save(update_fields=["status", "error_message", "completed_at"])
