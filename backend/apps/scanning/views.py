"""Scan endpoints — §5.5.

    POST /api/repositories/{id}/scan/          202 | 409 in-progress
                                               | 409 confirm-required (Phase 9)
    GET  /api/repositories/{id}/scan-status/   the small, pollable state
    GET  /api/scans/{id}/                      one scan and its manifests
    GET  /api/scans/{id}/dependencies/         paginated occurrences

Every one sits behind `OwnedQuerySetMixin`, which is why each declares an
`owner_field` naming its path back to the user — `repository__user` for a
scan, `manifest__scan__repository__user` for an occurrence. A foreign id is
therefore not in the queryset at all, and 404s on its own (§11 BOLA).

`scan-status` is a route of its own rather than part of the scan detail
because it is polled every three seconds while a scan runs. It answers with
the newest scan whatever its status, plus the id of the last scan that
*completed* — which is what the detail page is actually displaying while a
rescan runs behind it.
"""

from __future__ import annotations

import logging

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.common.authz import OwnedQuerySetMixin
from apps.common.errors import ApiError
from apps.reports.models import Report, ReportType
from apps.repositories.models import Repository

from .background import ScanInProgress, expire_stale, start_scan
from .models import DependencyOccurrence, ScanRun, ScanStatus, TriggerType
from .retention import reports_at_risk
from .serializers import (
    DependencyBreakdownSerializer,
    DependencyOccurrenceSerializer,
    ScanDetailSerializer,
    ScanStateSerializer,
    annotated_scans,
)

logger = logging.getLogger(__name__)


EMPTY_STATE: dict = {"scan": None, "latestCompletedScanId": None}


def _per_dependency_reports() -> Prefetch:
    """Each occurrence's remediation report, in one query for the whole page.

    Filtered to `per_dependency` on the prefetch rather than in the serializer:
    the related name covers both report types, and a combined report has a null
    `dependency_id` so it cannot appear here anyway — but stating the filter
    where the query is built is what keeps that true if §5.1 ever grows a third
    type.

    `only()` because three fields are all `ReportStateSerializer` renders, and
    a per-dependency report carries every retrieved chunk in full: fetching
    those to display a status pill would pull the whole corpus of every report
    on the page across the wire.
    """
    return Prefetch(
        "reports",
        queryset=Report.objects.filter(report_type=ReportType.PER_DEPENDENCY.value).only(
            "report_id", "status", "generated_at", "dependency_id"
        ),
        to_attr="per_dependency_reports",
    )


def scan_states_for(repository_ids) -> dict[str, dict]:
    """The scan state of many repositories, in one query rather than N.

    Two fields, because they are two different questions. `scan` is the newest
    scan whatever its status — what a status pill reads. `latestCompletedScanId`
    is the last scan that produced results — what a detail page is actually
    displaying. While a rescan runs they differ, and conflating them is how a
    UI ends up showing a finished dependency table under a spinner.

    Stale scans are expired first, so a worker restarted mid-scan does not
    leave a repository spinning until someone thinks to press Run scan.

    The newest row is authoritative for `scan` without a separate "is one
    active?" check: a scan cannot start while another is active, and one that
    is merely *stuck* has just been failed by `expire_stale`. Phase 4's
    retention (§5.7) bounds the row count per repository; until then it grows
    only with how often someone pressed Run scan.
    """
    ids = list(repository_ids)
    if not ids:
        return {}

    expire_stale(ids)

    states: dict[str, dict] = {str(pk): dict(EMPTY_STATE) for pk in ids}
    rows = annotated_scans().filter(repository_id__in=ids).order_by("-created_at")

    for scan in rows:
        state = states[str(scan.repository_id)]
        if state["scan"] is None:
            state["scan"] = ScanStateSerializer(scan).data
        if (
            state["latestCompletedScanId"] is None
            and scan.status == ScanStatus.COMPLETED.value
        ):
            state["latestCompletedScanId"] = str(scan.pk)

    return states


def scan_state(repository_id) -> dict:
    """`scan_states_for` for exactly one repository."""
    return scan_states_for([repository_id]).get(str(repository_id), dict(EMPTY_STATE))


def _boolean_param(raw: str | None) -> bool | None:
    """Read a query-string boolean, or None when it says nothing.

    The three states matter and only two were handled before: a truthy value
    filtered, and *everything else* — including an explicit `false` — fell
    through to no filter at all. `?flagged=false` therefore returned every row
    rather than the clean ones, which is the opposite of what it asks for and
    silent about it. Phase 5's Flagged / All / Unassessable tabs are the caller
    that would have found out the hard way.

    An unrecognised value is None (no filter) rather than False: guessing that
    `?flagged=maybe` means "show me the unflagged ones" would be inventing an
    answer to a question nobody asked.
    """
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return None


def _confirmed(data) -> bool:
    """Did the caller explicitly confirm a destructive rescan?

    A destructive confirmation is the one place in this API where guessing is
    unacceptable. `_boolean_param` above deliberately treats an unrecognised
    value as "said nothing" for query strings, and the same generosity here
    would mean a stale client sending `confirm: 1` — meaning something else
    entirely — destroying a report on the strength of a value nobody defined.

    Accepted: the JSON boolean the frontend sends, and the string `"true"` in
    any case, because a form-encoded client cannot express a JSON boolean.
    Nothing else, and the first version of this got it wrong in a way worth
    keeping a note about: it compared with `value in (True, "true", "True")`,
    and `1 == True` in Python, so `confirm: 1` — a value nobody had agreed
    meant yes — sailed through. The test for it is what found it.
    """
    try:
        value = data.get("confirm")
    except AttributeError:  # pragma: no cover - a non-mapping body
        return False
    # `is True` rather than `== True`: identity excludes 1, 1.0 and Decimal(1).
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() == "true"


def guard_destructive_rescan(repository: Repository, *, confirmed: bool) -> None:
    """Refuse a rescan that would silently destroy generated reports.

    §10 Phase 9: "`POST /scan/` when the latest scan has >=1 report → 409
    `confirm_required` + `{reports_count}`; proceeds with `{confirm:true}`
    (value-based guard — no cooldown timers)."

    The guard is on the *value at stake*, not on elapsed time, and that is the
    whole design. A cooldown would refuse a cheap rescan of a repository with
    nothing generated and permit an expensive one a minute later; this refuses
    exactly the rescans that throw work away, and refuses them only once.

    **It runs unconditionally, before `start_scan`'s in-progress check.** The
    tidier-looking arrangement — skip the confirmation when a scan is already
    running, since a refused request destroys nothing — has a hole in it. "Is a
    scan running?" is only answerable after `expire_stale` has reaped the ones
    presumed dead, and a stalled `running` row that had not been reaped yet
    would read as active, skip this guard, and then be expired by `start_scan`
    a moment later — starting the rescan, and destroying the reports, with no
    confirmation asked. Putting the guard first means there is no state in
    which a scan starts without passing it.

    What that costs is a stale tab clicking Run scan mid-scan: it is asked to
    confirm, and then told a scan is already running. Both sentences are true
    — the running scan will clear those reports when it completes — and the
    order is the order they became true.
    """
    if confirmed:
        return
    count = reports_at_risk(repository.pk)
    if count == 0:
        return
    raise ApiError(
        "confirm_required",
        f"This repository has {count} generated "
        f"{'report' if count == 1 else 'reports'}. A new scan replaces these "
        "results and clears them - regenerating costs a fresh model call.",
        status_code=status.HTTP_409_CONFLICT,
        # camelCase like every other `extra` on this API (§7.7, §8.13). §10
        # writes it `reports_count`; that is the plan naming a quantity, not
        # the wire format, and one spelling across the surface is what keeps
        # the client from having two conventions to remember.
        extra={"reportsCount": count},
    )


def trigger_scan(repository: Repository, user, trigger_type: str):
    """Start a scan, or raise the §5.5 409. Shared by registration and the route."""
    try:
        return start_scan(repository, user, trigger_type)
    except ScanInProgress as busy:
        raise ApiError(
            "scan_in_progress",
            "A scan is already running for this repository. "
            "It'll finish on its own — no need to start another.",
            status_code=status.HTTP_409_CONFLICT,
            extra={"scanId": str(busy.scan.pk)},
        ) from busy


class RepositoryScanView(OwnedQuerySetMixin, generics.GenericAPIView):
    """`POST /api/repositories/{id}/scan/` — 202, or 409 if one is running.

    202 rather than 201: the response describes work accepted, not a resource
    finished. §8 makes this mandatory rather than stylistic — Render's request
    timeout is about 100 s and a scan can legitimately take longer, so a scan
    has to be a background thread plus polling and can never be inline.

    From Phase 9 it can also answer 409 `confirm_required`, which is not a
    failure but a question: this scan's generated reports die with it (§5.7),
    and the caller is asked to say so out loud before they do.
    """

    queryset = Repository.objects.all()
    lookup_field = "repository_id"
    lookup_url_kwarg = "repository_id"

    def post(self, request, *args, **kwargs):
        repository = self.get_object()
        guard_destructive_rescan(repository, confirmed=_confirmed(request.data))
        trigger_scan(repository, request.user, TriggerType.MANUAL.value)
        return Response(scan_state(repository.pk), status=status.HTTP_202_ACCEPTED)


class RepositoryScanStatusView(OwnedQuerySetMixin, generics.GenericAPIView):
    """`GET /api/repositories/{id}/scan-status/` — the polling endpoint."""

    queryset = Repository.objects.all()
    lookup_field = "repository_id"
    lookup_url_kwarg = "repository_id"

    def get(self, request, *args, **kwargs):
        repository = self.get_object()
        return Response(scan_state(repository.pk))


class ScanDetailView(OwnedQuerySetMixin, generics.RetrieveAPIView):
    """`GET /api/scans/{id}/` — one scan, its counts, and its manifests."""

    owner_field = "repository__user"
    serializer_class = ScanDetailSerializer
    lookup_field = "scan_id"
    lookup_url_kwarg = "scan_id"
    queryset = annotated_scans()


class DependencyPagination(PageNumberPagination):
    """`?page=` per §5.5.

    50 rows is roughly a screenful of table plus scroll, and it keeps the
    response small enough that a repository with 800 occurrences does not
    serialize all of them into a free tier's memory at once (§8). `page_size`
    is deliberately not client-settable: an unbounded page is the same problem
    wearing a query parameter.
    """

    page_size = 50
    max_page_size = 50


class ScanDependenciesView(OwnedQuerySetMixin, generics.ListAPIView):
    """`GET /api/scans/{id}/dependencies/?flagged=&page=`.

    `flagged=true` filters to `is_flagged`, which the Phase 4 engine sets — in
    Phase 3 the column is uniformly false, so the filter is honest and returns
    nothing rather than pretending to know which rows matter.

    A foreign or unknown `scan_id` is a 404, not an empty page. Scoping the
    occurrence queryset alone would already leak nothing — a foreign scan's
    rows are simply absent — but it would answer a foreign id exactly as it
    answers an empty scan, which is a different statement, and every other
    route on this surface says 404. Consistency here is what keeps the BOLA
    suite (§11) able to assert one rule instead of a table of exceptions.
    """

    owner_field = "manifest__scan__repository__user"
    serializer_class = DependencyOccurrenceSerializer
    pagination_class = DependencyPagination
    queryset = DependencyOccurrence.objects.all()

    def get_queryset(self):
        scan = get_object_or_404(
            ScanRun.objects.filter(repository__user=self.request.user),
            pk=self.kwargs["scan_id"],
        )
        queryset = (
            super()
            .get_queryset()
            .filter(manifest__scan=scan)
            .select_related("manifest", "package")
            # Phase 8: one query for every row's remediation-report state
            # instead of one per row. `to_attr` rather than a plain prefetch so
            # the serializer can tell "prefetched and empty" from "not
            # prefetched" — the difference between reading a list and issuing a
            # query, on a route that renders up to 300 of them.
            .prefetch_related(_per_dependency_reports())
        )

        flagged = _boolean_param(self.request.query_params.get("flagged"))
        if flagged is not None:
            queryset = queryset.filter(is_flagged=flagged)

        unassessable = _boolean_param(self.request.query_params.get("unassessable"))
        if unassessable is not None:
            queryset = queryset.filter(is_unassessable=unassessable)

        # Unassessable rows sort last: they are not findings, and a table that
        # opens on six "can't assess" rows buries the ones that matter.
        return queryset.order_by(
            "is_unassessable", "manifest__manifest_path", "package__package_name"
        )


class DependencyDetailView(OwnedQuerySetMixin, generics.RetrieveAPIView):
    """`GET /api/dependencies/{id}/` — one occurrence and why it scored that.

    The route §5.5 reserves for Phase 5. It takes the occurrence id directly
    rather than hanging off the scan, because that is what the UI has: a table
    row knows its own id and nothing about the route that fetched it.

    Reaching the user takes four joins (`manifest__scan__repository__user`),
    which is exactly why the mixin owns the rule instead of each view. A
    foreign occurrence is not in the queryset at all, so it 404s without a
    permission check anyone could forget to write (§11 BOLA).

    `prefetch_related` on the advisories rather than a second query per row:
    a package with a dozen CVEs is common, and the panel shows all of them.
    """

    owner_field = "manifest__scan__repository__user"
    serializer_class = DependencyBreakdownSerializer
    lookup_field = "dependency_id"
    lookup_url_kwarg = "dependency_id"
    queryset = (
        DependencyOccurrence.objects.select_related(
            "manifest", "manifest__scan", "package"
        )
        .prefetch_related("vulnerabilities")
        .prefetch_related(_per_dependency_reports())
    )
