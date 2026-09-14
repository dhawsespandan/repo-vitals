"""`repositories` — §5.1.

A registration is a *per-user* claim on a GitHub repository, not a global
record of it: two users may each track the same repo, and each gets their own
row, their own scans and their own history. Both uniqueness constraints are
therefore scoped by `user_id` (§5.1), and every queryset that reaches a
request is filtered by owner through `common.authz.OwnedQuerySetMixin`.

Columns here are written from the pre-scan validation responses (§5.6) and
never from user input: the pasted URL is parsed to `owner/repo`, discarded,
and everything stored is what GitHub itself returned for that pair.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class AccessLevel(models.TextChoices):
    """How the registering user reaches the repository.

    `owner` means the account itself owns it. `collaborator` is admin rights
    on someone else's repo; `write` is push without admin. The distinction is
    recorded because §1.12 restricts *private* repositories to the user's own
    namespace — the stored level is what makes that decision auditable after
    the fact.
    """

    OWNER = "owner", "Owner"
    WRITE = "write", "Write"
    COLLABORATOR = "collaborator", "Collaborator"


class Project(models.Model):
    """§5.1's `projects` - a user's name for repositories that ship together.

    Membership is not a table of its own: it is `repositories.project_id`
    (§5.1), so a repository belongs to at most one project by construction and
    there is no join row to outlive either side.

    **Two rules the schema cannot state, enforced where membership is written**
    (`projects.create_project`, the only code that sets `project_id`). A project
    has at least two members, and every member belongs to the user who owns the
    project. The second is the one with teeth: Phase 10's sibling notice reads a
    sibling's latest scan into a report, and a sibling registered by another
    user would put *their* private dependency list into *this* user's report.
    """

    project_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects"
        ordering = ["name", "created_at"]

    def __str__(self) -> str:
        return self.name


class Repository(models.Model):
    repository_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="repositories",
    )

    # GitHub's own id: durable across renames and transfers, which is why the
    # primary duplicate check uses it rather than the owner/name pair.
    github_repo_id = models.BigIntegerField()

    owner = models.TextField()
    name = models.TextField()
    full_name = models.TextField()
    html_url = models.TextField()

    # §5.1 specifies this column as nullable, and the distinction is real:
    # NULL means "GitHub reported no default branch" (a repository with no
    # commits), which is not the same fact as an empty string. Pre-scan
    # validation rejects that case as `repo_empty` before a row is ever
    # written (§5.6), so in practice the column is always populated — but the
    # schema keeps the two states distinguishable rather than collapsing them.
    # DJ001 is the general "prefer '' over NULL for text" convention; here the
    # spec and the semantics both say otherwise.
    default_branch = models.TextField(null=True, blank=True)  # noqa: DJ001

    visibility = models.TextField(choices=Visibility.choices)
    access_level = models.TextField(choices=AccessLevel.choices)

    #: §5.1, Phase 10. SET_NULL rather than CASCADE, because deleting a
    #: *project* means ungrouping, and ungrouping must never delete a
    #: repository. The other direction - deleting a repository that is in a
    #: project removes every member - is a service-layer rule with a
    #: confirmation in front of it (`projects.delete_repository`), not a
    #: database cascade anyone could trigger by accident.
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="repositories",
    )

    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "repositories"
        verbose_name_plural = "repositories"
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "github_repo_id"],
                name="repositories_unique_user_github_repo_id",
            ),
            models.UniqueConstraint(
                fields=["user", "owner", "name"],
                name="repositories_unique_user_owner_name",
            ),
            models.CheckConstraint(
                condition=models.Q(visibility__in=Visibility.values),
                name="repositories_visibility_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(access_level__in=AccessLevel.values),
                name="repositories_access_level_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name
