"""Report endpoints — §5.5.

    POST /api/scans/{id}/reports/combined/   200 cached | 202 started | 409 busy
    POST /api/dependencies/{id}/report/      200 cached | 202 started | 409 busy
    GET  /api/reports/{id}/                  the stored row, polled

All three sit behind `OwnedQuerySetMixin`, each declaring the path back to its
owner — `repository__user` for a scan, `manifest__scan__repository__user` for
an occurrence, `scan__repository__user` for a report. A foreign id is not in
the queryset at all and 404s on its own (§11 BOLA).

**The two POSTs are the same shape and deliberately so.** §10 Phase 8 asks for
the per-dependency endpoint to sit "on the shared cache/lock/polling pattern",
so the status codes, the 409 body and the polling route are identical and the
frontend has one flow to implement rather than two. What differs is the key —
`(scan, 'per_dependency', dependency)` rather than `(scan, 'combined')` — and
one extra refusal: there is nothing to remediate about a dependency the scan
did not flag.

**The POST is the only route that can spend money, and it never spends it
twice.** 200 means the answer was already on disk; 202 means a thread has been
handed the work; 409 means someone else's request is already doing it. Only the
202 path can reach the model, and `services.request_combined` is what decides
— the view's job is to turn three outcomes into three status codes.

**The GET is what the UI actually reads.** A generation's result never travels
back through the request that started it; the panel polls this route until the
status is terminal. That is what "the UI always reads stored rows" (§5.1) means
operationally, and it is also why a browser refresh mid-generation loses
nothing.
"""

from __future__ import annotations

import logging

from rest_framework import generics, status
from rest_framework.response import Response

from apps.common.authz import OwnedQuerySetMixin
from apps.common.errors import ApiError
from apps.scanning.models import DependencyOccurrence, ScanRun

from .models import Report
from .serializers import ReportSerializer
from .services import (
    DependencyNotReportable,
    GenerationInProgress,
    ReportsUnavailable,
    ScanNotReportable,
    request_combined,
    request_per_dependency,
)

logger = logging.getLogger(__name__)


def _report_response(request_fn, target):
    """Turn one `request_*` call into §5.5's three status codes.

    Shared by both POSTs because the mapping is the contract, not an
    implementation detail: 200 means the answer was already on disk and no
    model ran, 202 means a thread has the work, 409 means someone else's
    request already does. Two copies of this would be two places for a status
    code to drift from the one the client branches on.
    """
    try:
        report, cached = request_fn(target)
    except GenerationInProgress as busy:
        raise ApiError(
            "report_generating",
            "This report is already being written. It'll be ready in a "
            "moment - no need to ask again.",
            status_code=status.HTTP_409_CONFLICT,
            extra={"reportId": str(busy.report.pk)},
        ) from busy
    except ScanNotReportable as unfinished:
        raise ApiError(
            "scan_not_reportable",
            "There's nothing to report on yet - this scan hasn't finished.",
            status_code=status.HTTP_409_CONFLICT,
        ) from unfinished
    except DependencyNotReportable as nothing_to_fix:
        raise ApiError(
            "dependency_not_reportable",
            str(nothing_to_fix),
            status_code=status.HTTP_409_CONFLICT,
        ) from nothing_to_fix
    except ReportsUnavailable as unavailable:
        # A deployment fault, answered as one. The reader is not told which
        # setting is missing; the log line is where that belongs.
        logger.error("A report was requested but no generator is configured.")
        raise ApiError(
            "reports_unavailable",
            "Report generation isn't available on this deployment.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from unavailable

    return Response(
        ReportSerializer(report).data,
        status=status.HTTP_200_OK if cached else status.HTTP_202_ACCEPTED,
    )


class ScanCombinedReportView(OwnedQuerySetMixin, generics.GenericAPIView):
    """`POST /api/scans/{id}/reports/combined/`.

    202 rather than 201 for the same reason a scan answers 202 (§10 Phase 3):
    the response describes work accepted, not a resource finished. A generation
    is tens of seconds against Render's ~100 s request ceiling (§8), so it can
    never be inline.
    """

    owner_field = "repository__user"
    queryset = ScanRun.objects.select_related("repository").all()
    lookup_field = "scan_id"
    lookup_url_kwarg = "scan_id"
    serializer_class = ReportSerializer

    def post(self, request, *args, **kwargs):
        return _report_response(request_combined, self.get_object())


class DependencyReportView(OwnedQuerySetMixin, generics.GenericAPIView):
    """`POST /api/dependencies/{id}/report/` — §5.5's Phase 8 route.

    Keyed on the occurrence rather than on `(scan, package)`, because §5.1 is
    explicit that duplicates across manifests are independent rows: the same
    package in `package.json` and in `api/package.json` are two installations
    needing two remediations, and they can be at different versions. The route
    takes the id the table row already has, exactly as Phase 5's breakdown
    route does.

    `prefetch_related` on the advisories because the graph's `load_context`
    reads all of them, and `select_related` down to the user because
    retrieval needs that user's GitHub token.
    """

    owner_field = "manifest__scan__repository__user"
    queryset = DependencyOccurrence.objects.select_related(
        "manifest",
        "manifest__scan",
        "manifest__scan__repository",
        "manifest__scan__repository__user",
        "package",
    ).prefetch_related("vulnerabilities")
    lookup_field = "dependency_id"
    lookup_url_kwarg = "dependency_id"
    serializer_class = ReportSerializer

    def post(self, request, *args, **kwargs):
        return _report_response(request_per_dependency, self.get_object())


class ReportDetailView(OwnedQuerySetMixin, generics.RetrieveAPIView):
    """`GET /api/reports/{id}/` — the stored row, whatever state it is in."""

    owner_field = "scan__repository__user"
    serializer_class = ReportSerializer
    lookup_field = "report_id"
    lookup_url_kwarg = "report_id"
    queryset = Report.objects.select_related("scan", "scan__repository")
