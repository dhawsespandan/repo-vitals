"""Root URLconf.

Every route lives under `/api/` because the browser only ever reaches this
service through the Vercel rewrite `/api/* -> Render` (§2). The API surface is
specified in full in §5.5 and is built up phase by phase; this file carries
Phase 1's slice.
"""

from django.urls import path

from apps.common.views import HealthView

urlpatterns = [
    path("api/health/", HealthView.as_view(), name="health"),
]
