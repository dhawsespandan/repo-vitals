"""Projects - §10 Phase 10's grouping, and the rules §5.1 leaves to this layer.

§5.1: "Membership = `repositories.project_id`. The >=2-member rule and
same-owner rule are enforced in the service layer at creation; a non-empty
`project_id` therefore implies same-user siblings exist by construction."

That last clause is what the rest of the phase leans on. The sibling notice
(`apps.reports.project_context`) reads each sibling's latest scan into a
report, and it is safe to do so only because nothing but this module ever sets
`project_id` - so every rule that makes a sibling safe to read is checked here,
once, before the membership exists.

**A foreign repository is refused with the same answer as a missing one.**
§11's BOLA rule applies to ids in a body as much as to ids in a path: telling
a caller "that repository belongs to someone else" confirms it exists. An id
this user does not own and an id that names nothing are therefore one outcome,
`project_repository_unknown`, with one message.

**A repository already in a project is refused rather than moved.** Moving it
would shrink its old project, possibly to a single member, and a project of one
is not a project - the same rule the cascade delete enforces from the other
side. The reader is told which repositories are grouped and what to do instead.
"""

from __future__ import annotations

import logging
import uuid

from django.db import transaction
from rest_framework import status

from .models import Project, Repository

logger = logging.getLogger(__name__)

#: §10 Phase 10: "creation requires >=2 repo ids".
MIN_MEMBERS = 2

#: Long enough for any name a person gives a group of services, short enough
#: that a dashboard section header cannot be made to wrap five times.
MAX_NAME_LENGTH = 80


class ProjectRejected(Exception):
    """A request this layer refuses, carrying the `{code, message}` to answer with.

    The code and status live here rather than in the view because the rule and
    its explanation are one thing: a view that chose its own status for
    `project_too_small` would be a second place the contract could drift.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        extra: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


UNKNOWN_REPOSITORY = ProjectRejected(
    "project_repository_unknown",
    "One or more of those repositories isn't registered to you. "
    "Choose from the repositories you monitor.",
    status.HTTP_422_UNPROCESSABLE_ENTITY,
)


def _requested_ids(raw) -> list[uuid.UUID]:
    """Distinct repository ids in the order given. Raises for a malformed one.

    Duplicates are collapsed before the size rule is applied, so `[a, a]` is a
    project of one and refused as such rather than slipping past a length check.
    Anything that is not a UUID is an id that names nothing, and is answered
    exactly as an id that names someone else's repository.
    """
    if not isinstance(raw, list):
        return []
    ids: list[uuid.UUID] = []
    for value in raw:
        try:
            parsed = uuid.UUID(str(value).strip())
        except (ValueError, TypeError):
            raise UNKNOWN_REPOSITORY from None
        if parsed not in ids:
            ids.append(parsed)
    return ids


def create_project(user, name, repository_ids) -> Project:
    """Group two or more of `user`'s repositories. Raises `ProjectRejected`.

    Checked in an order where every refusal is about the request as sent: the
    name, then the size, then ownership, then existing membership. The size
    rule comes before ownership so that a single foreign id is refused as a
    project of one - which leaks nothing - rather than prompting a lookup.
    """
    cleaned = " ".join(str(name or "").split())
    if not cleaned:
        raise ProjectRejected(
            "project_name_required",
            "Give the project a name.",
            status.HTTP_400_BAD_REQUEST,
        )
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ProjectRejected(
            "project_name_too_long",
            f"Keep the project name to {MAX_NAME_LENGTH} characters or fewer.",
            status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(repository_ids, list) or len(repository_ids) < MIN_MEMBERS:
        raise _too_small()
    ids = _requested_ids(repository_ids)
    if len(ids) < MIN_MEMBERS:
        raise _too_small()

    with transaction.atomic():
        # Locked, so a second request grouping one of these repositories into
        # another project waits for this one rather than both succeeding.
        members = list(
            Repository.objects.select_for_update()
            .filter(user=user, pk__in=ids)
            .order_by("full_name")
        )
        if len(members) != len(ids):
            raise UNKNOWN_REPOSITORY

        grouped = [member for member in members if member.project_id is not None]
        if grouped:
            names = ", ".join(member.full_name for member in grouped)
            raise ProjectRejected(
                "repository_in_project",
                f"{names} {'is' if len(grouped) == 1 else 'are'} already in a "
                "project. A repository belongs to one project at a time - "
                "ungroup that project first.",
                status.HTTP_409_CONFLICT,
                extra={"repositoryIds": [str(member.pk) for member in grouped]},
            )

        project = Project.objects.create(user=user, name=cleaned)
        Repository.objects.filter(pk__in=[member.pk for member in members]).update(
            project=project
        )

    logger.info(
        "Created project %s for user %s with %d repositories.",
        project.pk,
        user.pk,
        len(members),
    )
    return project


def ungroup_project(project: Project) -> int:
    """Delete the project row; its members stay, independent. Returns their count.

    Non-destructive by construction: `repositories.project_id` is ON DELETE SET
    NULL (§5.1), so no scan, report or history row is touched. Reports already
    generated keep the sibling notices they were written with - those are a
    record of what was true at generation time, not a live view.
    """
    with transaction.atomic():
        count = project.repositories.count()
        project.delete()
    logger.info("Ungrouped project %s (%d repositories kept).", project.pk, count)
    return count


def delete_repository(repository: Repository, *, confirm) -> int:
    """Delete one repository - or, for a project member, the whole project.

    §10 Phase 10: "deleting a repo in a multi-repo project -> 409
    `project_cascade_confirm` + counts; confirm deletes **all** member repos
    (normal operational cascades) + the project row (a project cannot shrink to
    one member); history/traces persist." Returns how many repositories went.

    **The confirmation is the project's id, not `true`** (`docs/decisions.md`
    §10.3). A boolean answers "delete?"; the dialog asked "delete these N
    repositories?", and between the dialog and the click another tab can
    ungroup the project and regroup this repository with something else. Under
    a boolean that click would delete a repository the reader never saw named.
    Under an id it is refused, and the refusal names the group that exists now.

    **History and traces persist without doing anything here.** `scan_history`,
    `dependency_history` and `agent_execution_traces` have no foreign key into
    the operational schema (D9), so the cascade below cannot reach them.
    """
    with transaction.atomic():
        # Read and locked inside the transaction: the membership this decides
        # on has to be the membership it deletes.
        current = (
            Repository.objects.select_for_update()
            .select_related("project")
            .filter(pk=repository.pk)
            .first()
        )
        if current is None:
            # A concurrent request deleted it between the lookup and here.
            return 0

        project = current.project
        if project is None:
            current.delete()
            return 1

        members = list(
            Repository.objects.select_for_update().filter(
                project=project, user_id=current.user_id
            )
        )
        if len(members) < MIN_MEMBERS:
            # Unreachable through `create_project`, which is the only writer
            # of `project_id`. A project of one is not a group anyone agreed
            # to, so there is nothing to ask about: it goes with its member.
            current.delete()
            project.delete()
            return 1

        if _project_id(confirm) != project.pk:
            others = len(members) - 1
            raise ProjectRejected(
                "project_cascade_confirm",
                f"{current.full_name} is part of the project {project.name} with "
                f"{others} other {'repository' if others == 1 else 'repositories'}. "
                "A project can't shrink to one repository, so removing it removes "
                f"all {len(members)}, with their scans and reports.",
                status.HTTP_409_CONFLICT,
                # camelCase like every other `extra` on this API (§9.11).
                extra={
                    "projectId": str(project.pk),
                    "projectName": project.name,
                    "memberCount": len(members),
                    "otherCount": others,
                    # Sorted here rather than by the database: Postgres
                    # collation ignores punctuation, so "a-b/x" and "ab/x"
                    # order differently there than in the dialog's own sort.
                    "repositories": sorted(member.full_name for member in members),
                },
            )

        Repository.objects.filter(pk__in=[member.pk for member in members]).delete()
        project.delete()

    logger.info(
        "Deleted project %s and its %d repositories on confirmation.",
        project.pk,
        len(members),
    )
    return len(members)


def _project_id(value) -> uuid.UUID | None:
    """The project a confirmation names, or None when it names none.

    Strict on purpose, for §9.2's reason: `true`, `1` and `yes` are not ids, and
    a destructive confirmation is the one place this API refuses to guess what a
    value was meant to say.
    """
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def _too_small() -> ProjectRejected:
    return ProjectRejected(
        "project_too_small",
        "A project groups at least two of your repositories. Choose another one "
        "to group with it.",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
