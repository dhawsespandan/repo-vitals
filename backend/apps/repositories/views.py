"""Repository endpoints — §5.5.

    POST   /api/repositories/        validate (§5.6) + register, then scan
    GET    /api/repositories/        the user's own registrations
    GET    /api/repositories/{id}/   one registration (Phase 3; see below)
    DELETE /api/repositories/{id}/   remove one

All of them sit behind `OwnedQuerySetMixin`, so a foreign id is invisible
rather than forbidden (§11 BOLA).

**The GET on `{id}/` is a Phase 3 addition to a route §5.5 already lists.**
The repository detail page has to render for someone who typed the URL or
refreshed the tab, and without it the only way to learn a repository's name is
to fetch the whole list and filter client-side. It is a method on an existing
route rather than a new route, and it answers with the same serializer the
list does.

**Registration triggers the initial scan and does not wait for it.** §10 Phase
3's acceptance is "registration returns < 2 s with the scan running behind",
and §8 forces the same conclusion from the other side: Render's ~100 s request
timeout makes an inline scan impossible in the general case. A scan that fails
to *start* is logged and swallowed — the registration itself succeeded, and
answering 500 would leave the user with a repository they can see but were
told they do not have.
"""

from __future__ import annotations

import logging

from rest_framework import generics, status
from rest_framework.response import Response

from apps.common.authz import OwnedQuerySetMixin
from apps.scanning.background import ScanInProgress, start_scan
from apps.scanning.models import TriggerType
from apps.scanning.views import scan_states_for

from .models import Repository
from .serializers import SCAN_STATES, RepositorySerializer
from .validation import DuplicateRegistration, validate_and_describe

logger = logging.getLogger(__name__)


class ScanStateContextMixin:
    """Batch-load the scan state for whatever rows this view is about to send.

    One query for every repository in the response rather than one per row —
    see `repositories/serializers.py`. Views call it explicitly rather than
    inheriting a `get_serializer_context` override, because the create path
    serializes a single fresh row that is not in any queryset yet.
    """

    def scan_context(self, repositories) -> dict:
        return {
            **super().get_serializer_context(),
            SCAN_STATES: scan_states_for([repository.pk for repository in repositories]),
        }


class RepositoryListCreateView(
    ScanStateContextMixin, OwnedQuerySetMixin, generics.ListCreateAPIView
):
    queryset = Repository.objects.all()
    serializer_class = RepositorySerializer

    def list(self, request, *args, **kwargs):
        repositories = list(self.filter_queryset(self.get_queryset()))
        serializer = self.get_serializer_class()(
            repositories, many=True, context=self.scan_context(repositories)
        )
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """Register a repository, or explain precisely why it cannot be.

        The request body carries a raw pasted URL and nothing else. It is not
        run through an input serializer on purpose: §5.6 owns every rejection
        message, and a serializer's own validation error would answer in DRF's
        envelope instead of the `{code, message}` the frontend branches on.
        """
        raw_url = ""
        if isinstance(request.data, dict):
            raw_url = str(request.data.get("url") or "")

        try:
            validated = validate_and_describe(request.user, raw_url)
        except DuplicateRegistration as duplicate:
            # §5.6: a duplicate is a 200, not an error — the user asked for a
            # repository they already have, and the useful answer is where to
            # find it. The frontend redirects to `repository.id`.
            return Response(
                {
                    "code": "already_registered",
                    "message": "You're already monitoring this repository.",
                    "repository": RepositorySerializer(duplicate.repository).data,
                },
                status=status.HTTP_200_OK,
            )

        repository = Repository.objects.create(
            user=request.user,
            github_repo_id=validated.github_repo_id,
            owner=validated.owner,
            name=validated.name,
            full_name=validated.full_name,
            html_url=validated.html_url,
            default_branch=validated.default_branch,
            visibility=validated.visibility,
            access_level=validated.access_level,
        )
        logger.info(
            "Registered %s for user %s (%s, %s).",
            repository.full_name,
            request.user.pk,
            repository.visibility,
            repository.access_level,
        )

        try:
            start_scan(repository, request.user, TriggerType.INITIAL.value)
        except ScanInProgress:
            # Unreachable for a row created a line ago, and harmless if it ever
            # were: the scan the user wanted is already running.
            logger.info("Initial scan for %s was already running.", repository.pk)
        except Exception:
            # The registration stands. The user can press Run scan.
            logger.exception("Could not start the initial scan for %s.", repository.pk)

        return Response(
            RepositorySerializer(
                repository, context=self.scan_context([repository])
            ).data,
            status=status.HTTP_201_CREATED,
        )


class RepositoryDetailView(
    ScanStateContextMixin, OwnedQuerySetMixin, generics.RetrieveDestroyAPIView
):
    """Read or remove one registration.

    The row's operational data (scans, manifests, occurrences, reports from
    Phase 3 onward) cascades with it. The research tables do **not** — D9 is
    explicit that `scan_history`, `dependency_history` and
    `agent_execution_traces` are never cascaded by any trigger, including
    this one. That is by design, not an oversight: those rows are denormalized
    precisely so they can outlive the live row they came from.
    """

    queryset = Repository.objects.all()
    serializer_class = RepositorySerializer
    lookup_field = "repository_id"
    lookup_url_kwarg = "repository_id"

    def retrieve(self, request, *args, **kwargs):
        repository = self.get_object()
        serializer = self.get_serializer_class()(
            repository, context=self.scan_context([repository])
        )
        return Response(serializer.data)
