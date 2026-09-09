"""Report endpoints — §5.5.

    POST /api/scans/{id}/reports/combined/   200 cached | 202 started | 409 busy
    GET  /api/reports/{id}/                  the stored row, polled

Both sit behind `OwnedQuerySetMixin`, each declaring the path back to its owner
— `repository__user` for a scan, `scan__repository__user` for a report. A
foreign id is not in the queryset at all and 404s on its own (§11 BOLA).

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
from apps.scanning.models import ScanRun

from .models import Report
from .serializers import ReportSerializer
from .services import (
    GenerationInProgress,
    ReportsUnavailable,
    ScanNotReportable,
    request_combined,
)

logger = logging.getLogger(__name__)


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
        scan = self.get_object()
        try:
            report, cached = request_combined(scan)
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


class ReportDetailView(OwnedQuerySetMixin, generics.RetrieveAPIView):
    """`GET /api/reports/{id}/` — the stored row, whatever state it is in."""

    owner_field = "scan__repository__user"
    serializer_class = ReportSerializer
    lookup_field = "report_id"
    lookup_url_kwarg = "report_id"
    queryset = Report.objects.select_related("scan", "scan__repository")
