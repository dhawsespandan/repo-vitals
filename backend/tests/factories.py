"""factory_boy factories. Grows with the schema each phase."""

from __future__ import annotations

import factory
from django.utils import timezone

from apps.accounts.crypto import encrypt_token
from apps.accounts.models import User
from apps.reports.models import Report, ReportStatus, ReportType
from apps.repositories.models import AccessLevel, Repository, Visibility
from apps.scanning.models import (
    DependencyGroup,
    DependencyOccurrence,
    Ecosystem,
    ManifestFile,
    Package,
    Resolution,
    ScanRun,
    ScanStatus,
    TriggerType,
)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("github_user_id",)

    github_user_id = factory.Sequence(lambda n: 1000 + n)
    github_username = factory.Sequence(lambda n: f"dev-user-{n}")
    display_name = factory.LazyAttribute(
        lambda o: o.github_username.replace("-", " ").title()
    )
    email = factory.LazyAttribute(lambda o: f"{o.github_username}@example.com")
    avatar_url = factory.LazyAttribute(
        lambda o: f"https://avatars.githubusercontent.com/u/{o.github_user_id}"
    )
    encrypted_github_token = factory.LazyFunction(
        lambda: encrypt_token("gho_testtokentesttokentesttoken00000000")
    )
    token_scopes = "repo,read:user,user:email"


class RepositoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Repository

    user = factory.SubFactory(UserFactory)
    github_repo_id = factory.Sequence(lambda n: 500000 + n)
    owner = factory.LazyAttribute(lambda o: o.user.github_username)
    name = factory.Sequence(lambda n: f"service-{n}")
    full_name = factory.LazyAttribute(lambda o: f"{o.owner}/{o.name}")
    html_url = factory.LazyAttribute(lambda o: f"https://github.com/{o.full_name}")
    default_branch = "main"
    visibility = Visibility.PUBLIC
    access_level = AccessLevel.OWNER


class ScanRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScanRun

    repository = factory.SubFactory(RepositoryFactory)
    triggered_by = factory.LazyAttribute(lambda o: o.repository.user)
    trigger_type = TriggerType.MANUAL.value
    status = ScanStatus.COMPLETED.value
    scoring_formula_version = "v1"
    completed_at = factory.LazyFunction(timezone.now)


class ManifestFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ManifestFile

    scan = factory.SubFactory(ScanRunFactory)
    ecosystem = Ecosystem.NPM.value
    manifest_path = "package.json"
    lockfile_path = "package-lock.json"
    parser_name = "npm/package.json@1"


class PackageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Package
        django_get_or_create = ("ecosystem", "package_name")

    ecosystem = Ecosystem.NPM.value
    package_name = factory.Sequence(lambda n: f"package-{n}")


class DependencyOccurrenceFactory(factory.django.DjangoModelFactory):
    """A scanned occurrence with every signal at its benign value.

    Every test that wants a *finding* overrides exactly the signals it is
    testing, so what a case is about is visible in the override list rather
    than buried in a wall of defaults. `staleness_days=0` rather than None on
    purpose: None means "no publish history", which triggers §5.2's weight
    redistribution and would silently change the arithmetic of any test that
    did not mean to ask for it.
    """

    class Meta:
        model = DependencyOccurrence

    manifest = factory.SubFactory(ManifestFileFactory)
    package = factory.SubFactory(PackageFactory)
    dependency_group = DependencyGroup.RUNTIME.value
    declared_specifier = "^1.0.0"
    resolved_version = "1.0.0"
    resolution = Resolution.LOCKFILE.value
    latest_version = "1.0.0"
    staleness_days = 0
    is_deprecated = False
    vulnerability_count = 0
    cvss_max = None


class ReportFactory(factory.django.DjangoModelFactory):
    """A completed combined report. Tests that care about a generation in
    flight override `status` (and clear `generated_at`, which a queued row has
    no business carrying)."""

    class Meta:
        model = Report

    scan = factory.SubFactory(ScanRunFactory)
    dependency = None
    report_type = ReportType.COMBINED.value
    status = ReportStatus.COMPLETED.value
    summary_text = "Two dependencies need attention."
    fixes_json = factory.LazyFunction(list)
    model_name = "openai/gpt-oss-120b"
    generated_at = factory.LazyFunction(timezone.now)
