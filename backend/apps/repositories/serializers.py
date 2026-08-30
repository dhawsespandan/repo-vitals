"""Repository serializers.

Field names are camelCase to match `frontend/src/types/index.ts`, following
the convention `UserSerializer` set in Phase 1. `user` is absent from `fields`
by construction — the browser only ever sees its own rows, so the column would
be noise, and an explicit allowlist cannot leak a column added later.

From Phase 3 a repository carries its scan state, because every surface that
lists repositories also shows whether they are scanning. The state is supplied
through the serializer *context*, batch-loaded by the view in one query: a
`SerializerMethodField` that queried per row would turn a dashboard of twelve
repositories into twelve extra round trips to Supabase.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import Repository

#: Context key holding `{repository_id: scan_state}` (see `scanning.views`).
SCAN_STATES = "scan_states"


class RepositorySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="repository_id", read_only=True)
    latestScan = serializers.SerializerMethodField()
    latestCompletedScanId = serializers.SerializerMethodField()
    fullName = serializers.CharField(source="full_name", read_only=True)
    htmlUrl = serializers.CharField(source="html_url", read_only=True)
    defaultBranch = serializers.CharField(source="default_branch", read_only=True)
    accessLevel = serializers.CharField(source="access_level", read_only=True)
    registeredAt = serializers.DateTimeField(source="registered_at", read_only=True)

    class Meta:
        model = Repository
        fields = [
            "id",
            "owner",
            "name",
            "fullName",
            "htmlUrl",
            "defaultBranch",
            "visibility",
            "accessLevel",
            "registeredAt",
            "latestScan",
            "latestCompletedScanId",
        ]
        read_only_fields = fields

    def _state(self, repository: Repository) -> dict:
        states = self.context.get(SCAN_STATES) or {}
        return states.get(str(repository.repository_id)) or {}

    def get_latestScan(self, repository: Repository) -> dict | None:
        return self._state(repository).get("scan")

    def get_latestCompletedScanId(self, repository: Repository) -> str | None:
        return self._state(repository).get("latestCompletedScanId")
