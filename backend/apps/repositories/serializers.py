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

from .models import Project, Repository

#: Context key holding `{repository_id: scan_state}` (see `scanning.views`).
SCAN_STATES = "scan_states"


class RepositorySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="repository_id", read_only=True)
    #: Phase 10: `{id, name}` or null. Two fields rather than the project with
    #: its members, because the dashboard groups by it and a list of twelve
    #: repositories should not carry the membership of their projects twelve
    #: times over. Views `select_related("project")`, so this is not a query.
    project = serializers.SerializerMethodField()
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
            "project",
            "latestScan",
            "latestCompletedScanId",
        ]
        read_only_fields = fields

    def _state(self, repository: Repository) -> dict:
        states = self.context.get(SCAN_STATES) or {}
        return states.get(str(repository.repository_id)) or {}

    def get_project(self, repository: Repository) -> dict | None:
        project = repository.project
        if project is None:
            return None
        return {"id": str(project.project_id), "name": project.name}

    def get_latestScan(self, repository: Repository) -> dict | None:
        return self._state(repository).get("scan")

    def get_latestCompletedScanId(self, repository: Repository) -> str | None:
        return self._state(repository).get("latestCompletedScanId")


class ProjectSerializer(serializers.ModelSerializer):
    """One project with its members, each carrying its scan state.

    Members are full repository rows rather than ids because the Projects page
    shows each member's score, and a page that fetched the repository list
    separately to join it in the browser would be two requests reading the same
    rows. The scan state arrives through the same batch-loaded context the
    repository list uses, so a project of five is one scan-state query, not
    five.
    """

    id = serializers.UUIDField(source="project_id", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    repositories = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "name", "createdAt", "repositories"]
        read_only_fields = fields

    def get_repositories(self, project: Project) -> list[dict]:
        members = sorted(project.repositories.all(), key=lambda member: member.full_name)
        return RepositorySerializer(members, many=True, context=self.context).data
