"""Scan endpoints — §5.5.

    POST /api/repositories/{id}/scan/          202, or 409 `scan_in_progress`
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

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.common.authz import OwnedQuerySetMixin
from apps.common.errors import ApiError
from apps.repositories.models import Repository

from .background import ScanInProgress, expire_stale, start_scan
from .models import DependencyOccurrence, ScanRun, ScanStatus, TriggerType
from .serializers import (
    DependencyOccurrenceSerializer,
    ScanDetailSerializer,
    ScanStateSerializer,
    annotated_scans,
)

logger = logging.getLogger(__name__)


EMPTY_STATE: dict = {"scan": None, "latestCompletedScanId": None}


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
    """

    queryset = Repository.objects.all()
    lookup_field = "repository_id"
    lookup_url_kwarg = "repository_id"

    def post(self, request, *args, **kwargs):
        repository = self.get_object()
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
