"""The project context a report is generated with — §10 Phase 10.

§10: "Report context at generation time for project members: computed sibling
shared-dependency lines (same package in a sibling's latest scan, same-owner
data only) + a static one-sentence disclaimer that integration-level risks (API
contracts, shared data formats, auth/session behavior, timing) exist and are
not assessed — stored into `project_context_json`; independent repos get
neither."

Four decisions, each small and each load-bearing.

**Computed, never generated.** Every line is assembled here from stored
occurrence rows, and none of it reaches the prompt. A sibling's scan is a
measurement of a *different* repository; asking the model to restate it would
invite restating it wrong (§7.1: the model is never the source of a fact we
already measured), and it would carry a second repository's dependency list
into a request that is about the first.

**A snapshot, taken before the model runs.** The context is built at the start
of the generation and stored with the report, so a sibling rescanned next week
does not rewrite what this report said - a report is an interpretation of one
moment, which is also why it dies with its scan (§5.7). Building it *before*
the model call rather than after means a fault here fails the report before any
money is spent on it.

**Same-owner data only, checked twice.** `projects.create_project` already
guarantees every member belongs to the project's owner. The sibling query
filters on the owner again anyway: the notice is the one place in the product
where one repository's scan is read into another repository's report, and a
project row edited by hand must not be enough to leak a stranger's private
dependency list into it.

**A sibling that was not compared says so.** A member with no completed scan
has nothing to compare against, and silently leaving it out would make the
absence of a line read as "not shared" - the missing-scope defect this project
keeps finding (§4.7). It is named in `siblings_not_scanned` instead.
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.repositories.models import Repository
from apps.scanning.models import DependencyOccurrence, ScanRun, ScanStatus

#: Written into the stored JSON so a reader of an old row knows which shape
#: it is holding. Stored JSON outlives the code that wrote it.
CONTEXT_VERSION = 1

#: Lines stored per report. A combined report over thirty flagged packages in a
#: project of five could otherwise carry hundreds, and a notice nobody reads to
#: the end is not a notice. The count of what was left out is stored beside it.
MAX_LINES = 40

#: §10's "static one-sentence disclaimer", defined once. The stored row carries
#: only the flag (§5.1: "sibling-notice lines + disclaimer flag"); every surface
#: that renders the sentence reads it from here, so the web page and the
#: downloaded file cannot drift into two wordings of what the product cannot see.
SCOPE_DISCLAIMER = (
    "Integration-level risks between the repositories in a project - API "
    "contracts, shared data formats, auth and session behavior, timing - exist "
    "and are not assessed here."
)


def for_scan(scan: ScanRun) -> dict | None:
    """The context for a COMBINED report: every package the scan flagged.

    Flagged and assessable, which is the set the combined prompt is built from
    (`combined.build_input`) - so the notice is about the same dependencies the
    report is about.
    """
    subjects = DependencyOccurrence.objects.filter(
        manifest__scan=scan, is_flagged=True, is_unassessable=False
    ).select_related("package")
    return _build(scan.repository_id, subjects)


def for_occurrence(occurrence: DependencyOccurrence) -> dict | None:
    """The context for a PER_DEPENDENCY report: this one package."""
    return _build(occurrence.manifest.scan.repository_id, [occurrence])


def payload(context: dict | None) -> dict | None:
    """The stored context as a reader receives it, with its sentences resolved.

    Shared by the API serializer and both downloads, so all three say the same
    thing about the same row.
    """
    if not context:
        return None
    return {
        **context,
        "comparison_text": comparison_text(context),
        "disclaimer_text": SCOPE_DISCLAIMER if context.get("disclaimer") else None,
    }


def comparison_text(context: dict) -> str:
    """What was compared, stated even when the comparison found nothing.

    §10's notice "appears exactly when warranted" - a line exists only for a
    package a sibling really shares. But the *absence* of a line is ambiguous
    on its own: it reads identically whether the siblings were compared and
    share nothing, or were never compared at all. §4.7 is the same defect on
    the score badge. So the scope is one quiet sentence that is always there,
    and the notice lines are the loud part that is not.
    """
    name = (context.get("project") or {}).get("name") or "this project"
    compared = list(context.get("siblings_compared") or [])
    missing = list(context.get("siblings_not_scanned") or [])
    opening = f"Part of the project {name}."

    if not compared:
        if not missing:
            return opening
        return (
            f"{opening} None of its other repositories had a completed scan when "
            "this report was generated, so nothing was compared."
        )

    one = len(compared) == 1
    scans = (
        f"the latest {'scan' if one else 'scans'} of {_join(compared)}, as "
        f"{'it' if one else 'they'} stood when this report was generated"
    )
    if context.get("lines"):
        sentence = f"{opening} Compared against {scans}."
    else:
        sentence = (
            f"{opening} None of the dependencies this report covers appear in {scans}."
        )

    if missing:
        sentence += (
            f" {_join(missing)} had no completed scan and "
            f"{'was' if len(missing) == 1 else 'were'} not compared."
        )
    return sentence


def _join(names: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _build(repository_id, subjects: Iterable[DependencyOccurrence]) -> dict | None:
    # Re-read rather than trusting a repository object the caller loaded: the
    # scan's cached repository may predate the project being created, and
    # "independent repos get neither" has to be decided on current membership.
    repository = (
        Repository.objects.select_related("project").filter(pk=repository_id).first()
    )
    if repository is None or repository.project is None:
        return None
    project = repository.project

    # Sorted in Python rather than by the database: Postgres collation ignores
    # punctuation, so an `order_by` would name siblings in one order in CI and
    # another on SQLite - and these names are printed in a sentence.
    siblings = sorted(
        Repository.objects.filter(project=project, user_id=repository.user_id).exclude(
            pk=repository.pk
        ),
        key=lambda sibling: sibling.full_name,
    )
    by_id = {sibling.pk: sibling for sibling in siblings}

    # §10's "a sibling's latest scan": the newest one that *completed*. A
    # running or failed scan has no occurrences to compare against, and
    # retention (§5.7) means the completed one is normally the only one left.
    latest: dict = {}
    for scan in ScanRun.objects.filter(
        repository__in=siblings, status=ScanStatus.COMPLETED.value
    ).order_by("-completed_at", "-created_at"):
        latest.setdefault(scan.repository_id, scan)

    packages = {subject.package_id for subject in subjects}

    lines: list[dict] = []
    if packages and latest:
        shared = DependencyOccurrence.objects.filter(
            manifest__scan__in=list(latest.values()),
            package_id__in=packages,
        ).select_related("manifest", "manifest__scan", "package")
        ordered = sorted(
            shared,
            key=lambda occurrence: (
                occurrence.package.package_name,
                by_id[occurrence.manifest.scan.repository_id].full_name,
                occurrence.manifest.manifest_path,
            ),
        )
        lines = [
            _line(occurrence, by_id[occurrence.manifest.scan.repository_id])
            for occurrence in ordered
        ]

    return {
        "version": CONTEXT_VERSION,
        "project": {"id": str(project.pk), "name": project.name},
        "siblings_compared": [s.full_name for s in siblings if s.pk in latest],
        "siblings_not_scanned": [s.full_name for s in siblings if s.pk not in latest],
        "lines": lines[:MAX_LINES],
        "lines_omitted": max(0, len(lines) - MAX_LINES),
        "disclaimer": True,
    }


def _line(occurrence: DependencyOccurrence, sibling: Repository) -> dict:
    """One shared dependency in one sibling manifest, as data and as a sentence.

    The sentence is built here rather than by each surface for §6.7's reason: a
    sentence assembled from parts in two places is two places for the join to
    break, and a test can assert this one whole.

    It says what the sibling's own scan found, not what to do about it. The
    wireframe's version read "A fix here should be applied there too", which is
    a claim the data does not support when the sibling has already upgraded -
    the status is what the scan can vouch for, so the status is what it says.
    """
    if occurrence.is_unassessable:
        status, verdict = "unassessable", "where it could not be assessed."
    elif occurrence.is_flagged:
        status, verdict = "flagged", "where it is flagged too."
    else:
        status, verdict = "clean", "where it is not flagged."

    version = occurrence.resolved_version or occurrence.declared_specifier or None
    where = occurrence.manifest.manifest_path + (f", {version}" if version else "")

    return {
        "package": occurrence.package.package_name,
        "ecosystem": occurrence.package.ecosystem,
        "sibling_repository_id": str(sibling.pk),
        "sibling_repository": sibling.full_name,
        "manifest_path": occurrence.manifest.manifest_path,
        "version": version,
        "status": status,
        "text": (
            f"{occurrence.package.package_name} is also a dependency of "
            f"{sibling.full_name} ({where}), {verdict}"
        ),
    }
