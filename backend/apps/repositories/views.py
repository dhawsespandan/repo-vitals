"""Repository endpoints — §5.5.

    POST   /api/repositories/        validate (§5.6) + register
    GET    /api/repositories/        the user's own registrations
    DELETE /api/repositories/{id}/   remove one

All three sit behind `OwnedQuerySetMixin`, so a foreign id is invisible rather
than forbidden (§11 BOLA).
"""

from __future__ import annotations

import logging

from rest_framework import generics, status
from rest_framework.response import Response

from apps.common.authz import OwnedQuerySetMixin

from .models import Repository
from .serializers import RepositorySerializer
from .validation import DuplicateRegistration, validate_and_describe

logger = logging.getLogger(__name__)


class RepositoryListCreateView(OwnedQuerySetMixin, generics.ListCreateAPIView):
    queryset = Repository.objects.all()
    serializer_class = RepositorySerializer

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
        return Response(
            RepositorySerializer(repository).data,
            status=status.HTTP_201_CREATED,
        )


class RepositoryDestroyView(OwnedQuerySetMixin, generics.DestroyAPIView):
    """Remove a registration.

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
