"""Root URLconf.

Every route lives under `/api/` because the browser only ever reaches this
service through the Vercel rewrite `/api/* -> Render` (§2). The API surface is
specified in full in §5.5 and is built up phase by phase; this file carries
Phase 1's slice.

The two GitHub OAuth views are wired explicitly rather than by including
`allauth.urls`, for two reasons: it pins the callback path to the §5.5 spelling
(`/api/auth/github/callback/`, not allauth's default `.../login/callback/`),
and it keeps allauth's password/signup/email routes — none of which exist in
this product — off the URLconf entirely.
"""

from allauth.socialaccount.providers.oauth2.views import (
    OAuth2CallbackView,
    OAuth2LoginView,
)
from django.urls import path

from apps.accounts.oauth import RepoVitalsGitHubOAuth2Adapter
from apps.accounts.views import LogoutView, SessionView
from apps.common.views import HealthView
from apps.reports.views import ReportDetailView, ScanCombinedReportView
from apps.repositories.views import RepositoryDetailView, RepositoryListCreateView
from apps.scanning.views import (
    DependencyDetailView,
    RepositoryScanStatusView,
    RepositoryScanView,
    ScanDependenciesView,
    ScanDetailView,
)

github_login = OAuth2LoginView.adapter_view(RepoVitalsGitHubOAuth2Adapter)
github_callback = OAuth2CallbackView.adapter_view(RepoVitalsGitHubOAuth2Adapter)

urlpatterns = [
    path("api/health/", HealthView.as_view(), name="health"),
    # URL names are allauth's convention (`<provider_id>_login` /
    # `<provider_id>_callback`); the adapter reverses `github_callback` to
    # build redirect_uri, so the name must not change.
    path("api/auth/github/login/", github_login, name="github_login"),
    path("api/auth/github/callback/", github_callback, name="github_callback"),
    path("api/auth/session/", SessionView.as_view(), name="auth-session"),
    path("api/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path(
        "api/repositories/",
        RepositoryListCreateView.as_view(),
        name="repository-list",
    ),
    path(
        "api/repositories/<uuid:repository_id>/",
        RepositoryDetailView.as_view(),
        name="repository-detail",
    ),
    path(
        "api/repositories/<uuid:repository_id>/scan/",
        RepositoryScanView.as_view(),
        name="repository-scan",
    ),
    path(
        "api/repositories/<uuid:repository_id>/scan-status/",
        RepositoryScanStatusView.as_view(),
        name="repository-scan-status",
    ),
    path("api/scans/<uuid:scan_id>/", ScanDetailView.as_view(), name="scan-detail"),
    path(
        "api/scans/<uuid:scan_id>/dependencies/",
        ScanDependenciesView.as_view(),
        name="scan-dependencies",
    ),
    path(
        "api/dependencies/<uuid:dependency_id>/",
        DependencyDetailView.as_view(),
        name="dependency-detail",
    ),
    path(
        "api/scans/<uuid:scan_id>/reports/combined/",
        ScanCombinedReportView.as_view(),
        name="scan-combined-report",
    ),
    path(
        "api/reports/<uuid:report_id>/",
        ReportDetailView.as_view(),
        name="report-detail",
    ),
]
