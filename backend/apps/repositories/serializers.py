"""Repository serializers.

Field names are camelCase to match `frontend/src/types/index.ts`, following
the convention `UserSerializer` set in Phase 1. `user` is absent from `fields`
by construction — the browser only ever sees its own rows, so the column would
be noise, and an explicit allowlist cannot leak a column added later.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import Repository


class RepositorySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="repository_id", read_only=True)
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
        ]
        read_only_fields = fields
