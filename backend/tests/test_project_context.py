"""The sibling notice and scope disclaimer — §10 Phase 10.

§10's acceptance: "sibling notice appears exactly when warranted". Both halves
of "exactly" are cases here - a line for every package a sibling's latest scan
really shares, and no line for anything else - and the second half has more
ways to go wrong than the first: a clean or unassessable package of *this*
repository, a package only a sibling's older or unfinished scan contained, a
package in a repository that is not a sibling at all.

Every sentence is asserted whole (§6.7). The notice is built from a package
name, a sibling, a manifest path, a version and a verdict, which is five joins,
and substring assertions cannot see a join.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.reports import project_context, services
from apps.reports.agent import graph as agent_graph
from apps.reports.llm.groq_client import LlmCall
from apps.reports.models import Report, ReportStatus, ReportType
from apps.reports.project_context import SCOPE_DISCLAIMER, for_occurrence, for_scan
from apps.reports.rag import chroma_store, fetch_docs
from apps.repositories.models import Repository
from apps.scanning.models import ManifestFile, ScanRun, ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    PackageFactory,
    ProjectFactory,
    ReportFactory,
    RepositoryFactory,
    ScanRunFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

WITH_KEY = override_settings(GROQ_API_KEY="gsk_test", GROQ_MODEL="test-model")


# ── builders ───────────────────────────────────────────────────────────────


def completed_scan(repository, *, completed_at=None) -> ScanRun:
    return ScanRunFactory(
        repository=repository,
        status=ScanStatus.COMPLETED.value,
        completed_at=completed_at or timezone.now(),
        risk_score=Decimal("60.00"),
        classification="medium",
    )


def uses(
    scan,
    name,
    *,
    path="package.json",
    version="1.0.0",
    flagged=False,
    unassessable=False,
):
    """One occurrence of `name` in `path` of `scan`."""
    manifest = ManifestFile.objects.filter(scan=scan, manifest_path=path).first()
    if manifest is None:
        manifest = ManifestFileFactory(scan=scan, manifest_path=path)
    return DependencyOccurrenceFactory(
        manifest=manifest,
        package=PackageFactory(ecosystem="npm", package_name=name),
        resolved_version=None if unassessable else version,
        declared_specifier="workspace:*" if unassessable else f"^{version}",
        is_flagged=flagged,
        is_unassessable=unassessable,
        risk_component_score=Decimal("40.00") if flagged else Decimal("100.00"),
    )


@pytest.fixture
def checkout(user):
    """A project of three: `api`, `web`, `worker`, all the test user's."""
    project = ProjectFactory(user=user, name="Checkout")
    return {
        name: RepositoryFactory(user=user, project=project, name=name)
        for name in ("api", "web", "worker")
    }


def texts(context) -> list[str]:
    return [line["text"] for line in context["lines"]]


# ── when a notice is warranted ─────────────────────────────────────────────


def test_an_independent_repository_gets_neither_notice_nor_disclaimer(user):
    scan = completed_scan(RepositoryFactory(user=user))
    occurrence = uses(scan, "lodash", flagged=True)

    assert for_scan(scan) is None
    assert for_occurrence(occurrence) is None
    assert project_context.payload(None) is None


def test_a_shared_package_is_named_with_what_each_siblings_own_scan_found(checkout):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", version="4.17.19", flagged=True)
    web = completed_scan(checkout["web"])
    uses(web, "lodash", version="4.17.15", flagged=True)
    worker = completed_scan(checkout["worker"])
    uses(worker, "lodash", path="services/queue/package.json", version="4.17.21")

    context = for_scan(api)

    web_name, worker_name = checkout["web"].full_name, checkout["worker"].full_name
    assert texts(context) == [
        f"lodash is also a dependency of {web_name} (package.json, 4.17.15), "
        "where it is flagged too.",
        f"lodash is also a dependency of {worker_name} "
        "(services/queue/package.json, 4.17.21), where it is not flagged.",
    ]
    assert [line["status"] for line in context["lines"]] == ["flagged", "clean"]
    assert context["lines"][0]["sibling_repository_id"] == str(checkout["web"].pk)
    assert context["project"] == {
        "id": str(checkout["api"].project_id),
        "name": "Checkout",
    }
    assert context["disclaimer"] is True
    assert context["lines_omitted"] == 0


def test_an_unassessable_sibling_occurrence_says_it_could_not_be_assessed(checkout):
    api = completed_scan(checkout["api"])
    uses(api, "shared-ui", flagged=True)
    uses(completed_scan(checkout["web"]), "shared-ui", unassessable=True)

    assert texts(for_scan(api)) == [
        f"shared-ui is also a dependency of {checkout['web'].full_name} "
        "(package.json, workspace:*), where it could not be assessed."
    ]


def test_one_package_in_two_sibling_manifests_is_two_lines(checkout):
    api = completed_scan(checkout["api"])
    uses(api, "axios", flagged=True)
    web = completed_scan(checkout["web"])
    uses(web, "axios", path="package.json", version="0.21.1", flagged=True)
    uses(web, "axios", path="client/package.json", version="1.7.0")

    assert [line["manifest_path"] for line in for_scan(api)["lines"]] == [
        "client/package.json",
        "package.json",
    ]


def test_a_package_no_sibling_shares_gets_no_line_and_the_scope_says_so(user):
    project = ProjectFactory(user=user, name="Checkout")
    api = RepositoryFactory(user=user, project=project, name="api")
    web = RepositoryFactory(user=user, project=project, name="web")
    scan = completed_scan(api)
    uses(scan, "lodash", flagged=True)
    uses(completed_scan(web), "express", flagged=True)

    payload = project_context.payload(for_scan(scan))

    assert payload["lines"] == []
    assert payload["comparison_text"] == (
        "Part of the project Checkout. None of the dependencies this report covers "
        f"appear in the latest scan of {web.full_name}, as it stood when this "
        "report was generated."
    )
    # The disclaimer is not conditional on finding something: what the product
    # cannot see between two repositories is the same whether they share a
    # package or not.
    assert payload["disclaimer_text"] == SCOPE_DISCLAIMER


def test_the_scope_sentence_names_what_was_compared_and_what_was_not(checkout):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    uses(completed_scan(checkout["web"]), "lodash", flagged=True)
    # `worker` is mid-scan. Its occurrence is not a measurement anyone finished.
    running = ScanRunFactory(
        repository=checkout["worker"], status=ScanStatus.RUNNING.value, completed_at=None
    )
    uses(running, "lodash", flagged=True)

    payload = project_context.payload(for_scan(api))

    assert len(payload["lines"]) == 1
    assert payload["siblings_compared"] == [checkout["web"].full_name]
    assert payload["siblings_not_scanned"] == [checkout["worker"].full_name]
    assert payload["comparison_text"] == (
        f"Part of the project Checkout. Compared against the latest scan of "
        f"{checkout['web'].full_name}, as it stood when this report was generated. "
        f"{checkout['worker'].full_name} had no completed scan and was not compared."
    )


def test_a_project_where_no_sibling_has_finished_a_scan_says_nothing_was_compared(
    checkout,
):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)

    payload = project_context.payload(for_scan(api))

    assert payload["lines"] == []
    assert payload["comparison_text"] == (
        "Part of the project Checkout. None of its other repositories had a "
        "completed scan when this report was generated, so nothing was compared."
    )


def test_the_siblings_latest_completed_scan_is_the_one_compared(checkout):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    older = completed_scan(
        checkout["web"], completed_at=timezone.now() - timedelta(days=3)
    )
    uses(older, "lodash", version="4.17.15", flagged=True)
    newer = completed_scan(checkout["web"])
    uses(newer, "lodash", version="4.17.21")
    failed_since = ScanRunFactory(
        repository=checkout["web"], status=ScanStatus.FAILED.value
    )
    uses(failed_since, "lodash", version="4.17.10", flagged=True)

    assert texts(for_scan(api)) == [
        f"lodash is also a dependency of {checkout['web'].full_name} "
        "(package.json, 4.17.21), where it is not flagged."
    ]


# ── what a notice is about ─────────────────────────────────────────────────


def test_a_combined_notice_covers_only_the_packages_this_scan_flagged(checkout):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    uses(api, "express")  # clean here
    uses(api, "shared-ui", unassessable=True)  # never measured here
    web = completed_scan(checkout["web"])
    for name in ("lodash", "express", "shared-ui"):
        uses(web, name, flagged=True)

    assert [line["package"] for line in for_scan(api)["lines"]] == ["lodash"]


def test_a_remediation_notice_covers_only_its_own_package(checkout):
    api = completed_scan(checkout["api"])
    lodash = uses(api, "lodash", flagged=True)
    uses(api, "moment", flagged=True)
    web = completed_scan(checkout["web"])
    uses(web, "lodash", flagged=True)
    uses(web, "moment", flagged=True)

    assert [line["package"] for line in for_occurrence(lodash)["lines"]] == ["lodash"]


def test_another_users_repository_never_appears_even_in_a_corrupted_project(
    checkout,
):
    """Same-owner data only, checked where the data is read.

    `create_project` cannot produce this row. It is built by hand to prove the
    notice does not depend on that: a stranger's private dependency list must
    not reach this report because of one bad UPDATE.
    """
    stranger = RepositoryFactory(user=UserFactory(), name="stolen")
    Repository.objects.filter(pk=stranger.pk).update(project=checkout["api"].project)
    uses(completed_scan(stranger), "lodash", flagged=True)
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)

    context = for_scan(api)

    assert context["lines"] == []
    assert stranger.full_name not in (
        context["siblings_compared"] + context["siblings_not_scanned"]
    )


def test_the_lines_are_capped_and_what_was_left_out_is_counted(monkeypatch, checkout):
    monkeypatch.setattr(project_context, "MAX_LINES", 2)
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    web = completed_scan(checkout["web"])
    uses(web, "lodash", path="a/package.json", flagged=True)
    uses(web, "lodash", path="b/package.json", flagged=True)
    uses(completed_scan(checkout["worker"]), "lodash", flagged=True)

    context = for_scan(api)

    assert len(context["lines"]) == 2
    assert context["lines_omitted"] == 1


# ── stored at generation time ──────────────────────────────────────────────


def fixes_for(package: str) -> str:
    return json.dumps(
        {
            "summary_md": f"{package} needs attention.",
            "fixes": [
                {
                    "package": package,
                    "manifest_path": "package.json",
                    "ecosystem": "npm",
                    "fix_type": "upgrade",
                    "target_version": "9.9.9",
                    "replacement_package": None,
                    "priority": 1,
                }
            ],
            "citations": [],
        }
    )


class Model:
    """Counts calls, and answers with a fix for `package`."""

    def __init__(self, package: str) -> None:
        self.package = package
        self.calls = 0

    def __call__(self, system_prompt: str, user_prompt: str) -> LlmCall:
        self.calls += 1
        return LlmCall(
            content=fixes_for(self.package),
            model="test-model",
            prompt_tokens=10,
            completion_tokens=10,
            latency_ms=5,
            requests=1,
        )


@pytest.fixture
def combined_model(monkeypatch):
    model = Model("lodash")
    monkeypatch.setattr("apps.reports.combined.complete_json", model)
    return model


@WITH_KEY
def test_a_combined_report_is_stored_with_its_project_context(
    combined_model, checkout, no_background_threads
):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    uses(completed_scan(checkout["web"]), "lodash", flagged=True)

    report, _ = services.request_combined(api)
    services.run_combined(report.pk)

    report.refresh_from_db()
    assert report.status == ReportStatus.COMPLETED.value
    assert texts(report.project_context_json) == [
        f"lodash is also a dependency of {checkout['web'].full_name} "
        "(package.json, 1.0.0), where it is flagged too."
    ]


@WITH_KEY
def test_an_independent_repositorys_report_stores_no_context(
    combined_model, user, no_background_threads
):
    scan = completed_scan(RepositoryFactory(user=user))
    uses(scan, "lodash", flagged=True)

    report, _ = services.request_combined(scan)
    services.run_combined(report.pk)

    report.refresh_from_db()
    assert report.status == ReportStatus.COMPLETED.value
    assert report.project_context_json is None


@WITH_KEY
def test_the_context_is_built_before_the_model_is_called(
    monkeypatch, combined_model, checkout, no_background_threads
):
    """A fault building the notice must not cost a generation.

    Verified against the other order: with the context built after `generate`,
    this test fails on `calls == 0`.
    """

    def broken(scan):
        raise RuntimeError("sibling query failed")

    monkeypatch.setattr(project_context, "for_scan", broken)
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)

    report, _ = services.request_combined(api)
    services.run_combined(report.pk)

    report.refresh_from_db()
    assert report.status == ReportStatus.FAILED.value
    assert combined_model.calls == 0


@pytest.fixture
def no_documents(monkeypatch, tmp_path, settings):
    """Retrieval finds nothing, so the graph runs end to end with no network."""
    settings.CHROMA_DIR = str(tmp_path / "chroma")
    chroma_store.reset_for_tests()
    monkeypatch.setattr(
        agent_graph.fetch_docs,
        "fetch_for",
        lambda **kwargs: fetch_docs.FetchResult(
            docs=(), repo_full_name=None, reason="no_repository"
        ),
    )
    yield
    chroma_store.reset_for_tests()


def test_a_remediation_report_is_stored_with_its_project_context(no_documents, checkout):
    api = completed_scan(checkout["api"])
    lodash = uses(api, "lodash", flagged=True)
    uses(api, "moment", flagged=True)
    web = completed_scan(checkout["web"])
    uses(web, "lodash", version="4.17.15", flagged=True)
    uses(web, "moment", flagged=True)
    report = Report.objects.create(
        scan=api,
        dependency=lodash,
        report_type=ReportType.PER_DEPENDENCY.value,
        status=ReportStatus.RUNNING.value,
    )

    agent_graph.run(report, lodash, complete=Model("lodash"))

    report.refresh_from_db()
    assert report.status == ReportStatus.COMPLETED.value
    assert texts(report.project_context_json) == [
        f"lodash is also a dependency of {checkout['web'].full_name} "
        "(package.json, 4.17.15), where it is flagged too."
    ]


def test_the_notice_never_reaches_the_prompt(no_documents, checkout):
    """Computed, never generated - and never shown to the model to restate."""
    api = completed_scan(checkout["api"])
    lodash = uses(api, "lodash", flagged=True)
    uses(completed_scan(checkout["web"]), "lodash", flagged=True)
    report = Report.objects.create(
        scan=api,
        dependency=lodash,
        report_type=ReportType.PER_DEPENDENCY.value,
        status=ReportStatus.RUNNING.value,
    )
    prompts: list[str] = []

    def model(system_prompt: str, user_prompt: str) -> LlmCall:
        prompts.append(system_prompt + user_prompt)
        return Model("lodash")(system_prompt, user_prompt)

    agent_graph.run(report, lodash, complete=model)

    assert prompts
    assert not any(checkout["web"].full_name in prompt for prompt in prompts)
    assert not any("Checkout" in prompt for prompt in prompts)


def test_a_stored_notice_is_a_snapshot_not_a_live_view(auth_client, checkout):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    web = completed_scan(checkout["web"])
    shared = uses(web, "lodash", flagged=True)
    report = ReportFactory(scan=api, project_context_json=for_scan(api))

    # The sibling upgrades and rescans. The report said what was true then.
    shared.is_flagged = False
    shared.save(update_fields=["is_flagged"])
    body = auth_client.get(f"/api/reports/{report.pk}/").json()

    assert body["projectContext"]["lines"][0]["status"] == "flagged"


# ── what a reader receives ─────────────────────────────────────────────────


def test_the_api_resolves_both_sentences(auth_client, checkout):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    uses(completed_scan(checkout["web"]), "lodash", flagged=True)
    report = ReportFactory(scan=api, project_context_json=for_scan(api))

    context = auth_client.get(f"/api/reports/{report.pk}/").json()["projectContext"]

    assert context["disclaimer_text"] == SCOPE_DISCLAIMER
    assert context["comparison_text"].startswith("Part of the project Checkout.")
    assert len(context["lines"]) == 1


def test_a_report_with_no_context_says_null_rather_than_empty(auth_client, user):
    report = ReportFactory(scan=completed_scan(RepositoryFactory(user=user)))

    body = auth_client.get(f"/api/reports/{report.pk}/").json()

    assert body["projectContext"] is None


def test_the_markdown_download_carries_the_notice_and_the_disclaimer(
    auth_client, checkout
):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    uses(completed_scan(checkout["web"]), "lodash", flagged=True)
    context = for_scan(api)
    report = ReportFactory(scan=api, project_context_json=context)

    body = auth_client.get(f"/api/reports/{report.pk}/download/?fmt=md").content.decode()

    web = checkout["web"].full_name
    assert (
        "## Project context\n\n"
        f"Part of the project Checkout. Compared against the latest scan of {web}, "
        "as it stood when this report was generated. "
        f"{checkout['worker'].full_name} had no completed scan and was not compared."
        "\n\n"
        f"- lodash is also a dependency of {web} (package.json, 1.0.0), where it "
        "is flagged too.\n\n"
        f"_{SCOPE_DISCLAIMER}_\n"
    ) in body


def test_the_markdown_download_of_an_independent_repository_has_no_section(
    auth_client, user
):
    report = ReportFactory(scan=completed_scan(RepositoryFactory(user=user)))

    body = auth_client.get(f"/api/reports/{report.pk}/download/?fmt=md").content.decode()

    assert "Project context" not in body
    assert SCOPE_DISCLAIMER not in body


def test_the_json_download_carries_the_context_as_provenance(auth_client, checkout):
    api = completed_scan(checkout["api"])
    uses(api, "lodash", flagged=True)
    uses(completed_scan(checkout["web"]), "lodash", flagged=True)
    report = ReportFactory(scan=api, project_context_json=for_scan(api))

    body = auth_client.get(f"/api/reports/{report.pk}/download/?fmt=json").json()

    assert body["project_context"]["disclaimer_text"] == SCOPE_DISCLAIMER
    assert body["project_context"]["lines"][0]["package"] == "lodash"
