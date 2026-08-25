"""Endpoints that belong to no particular resource."""

from __future__ import annotations

import logging

from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """`GET /api/health/` — liveness plus a real database round-trip.

    The keepalive cron hits this every 10 minutes, which both keeps the Render
    free instance from sleeping (≈50 s cold start otherwise) and counts as
    Supabase activity so the free project is not paused after ~7 idle days
    (§4.2). Because it is what keeps the database awake, it has to *touch* the
    database — a bare 200 would let the project pause anyway.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            logger.exception("Health check failed: database unreachable.")
            return Response(
                {"status": "error", "database": "unreachable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok"})
