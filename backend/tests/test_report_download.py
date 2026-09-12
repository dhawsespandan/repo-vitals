"""`GET /api/reports/{id}/download/?fmt=md|json` — §10 Phase 9's downloads.

Acceptance: "JSON validates against §5.8" and "download auth". The first is a
schema assertion; the second is the BOLA suite's (`test_bola_suite.py` covers
this route with every other), so what is left here is what the two files say
and what they refuse to say.

**The confidence note gets a case each.** Four branches over two stored facts,
and they are four different findings about the same report — the one §8.14
found on a live run (thresholds cleared, nothing cited) is the one a reader
cannot detect for themselves, and the one most likely to be dropped by someone
simplifying this later.
"""

from __future__ import annotations

import json

import pytest

from apps.reports.download import render_json, render_markdown
from apps.reports.models import GroundingConfidence, ReportStatus, ReportType
from apps.scanning.models import ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    PackageFactory,
    ReportFactory,
    RepositoryFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db

FIX = {
    "package": "lodash",
    "manifest_path": "package.json",
    "ecosystem": "npm",
    "current_version": "4.17.19",
    "fix_type": "upgrade",
    "target_version": "4.17.21",
    "replacement_package": None,
    "cves": ["CVE-2021-23337"],
    "severity": "high",
    "priority": 1,
}

CHUNK = {
    "chunk_id": "c1",
    "text": "### 4.17.21\n\n- fix prototype pollution in zipObjectDeep",
    "similarity": 0.71,
    "source_path": "CHANGELOG.md",
    "source_sha": "abc123",
    "source_kind": "changelog",
    "heading": "4.17.21",
    "index": 0,
}


@pytest.fixture
def scan(user):
    return ScanRunFactory(
        repository=RepositoryFactory(user=user, name="rv-accept-basic"),
        triggered_by=user,
        status=ScanStatus.COMPLETED.value,
    )


@pytest.fixture
def combined(scan):
    return ReportFactory(
        scan=scan, summary_text="Upgrade lodash first.", fixes_json=[FIX]
    )


def occurrence_for(scan, **overrides):
    return DependencyOccurrenceFactory(
        manifest=ManifestFileFactory(scan=scan),
        package=PackageFactory(package_name="lodash"),
        resolved_version="4.17.19",
        is_flagged=True,
        **overrides,
    )


def per_dependency(scan, **overrides):
    fields = {
        "summary_text": "Upgrade to 4.17.21 [c1].",
        "fixes_json": [FIX],
        "citations_json": ["c1"],
        "retrieved_chunks_json": [CHUNK],
        "grounding_confidence": GroundingConfidence.SUFFICIENT.value,
    }
    fields.update(overrides)
    return ReportFactory(
        scan=scan,
        dependency=occurrence_for(scan),
        report_type=ReportType.PER_DEPENDENCY.value,
        **fields,
    )


def url(report, fmt: str) -> str:
    return f"/api/reports/{report.pk}/download/?fmt={fmt}"


# ── The two files ───────────────────────────────────────────────────────────


def test_markdown_arrives_as_a_file_with_the_name_phase_9_specifies(
    auth_client, combined
):
    response = auth_client.get(url(combined, "md"))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/markdown; charset=utf-8"
    assert response["Content-Disposition"] == (
        'attachment; filename="repovitals_rv-accept-basic_combined_'
        f'{combined.scan_id.hex}.md"'
    )


def test_json_arrives_as_a_file_too(auth_client, combined):
    response = auth_client.get(url(combined, "json"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Content-Disposition"].endswith(f'{combined.scan_id.hex}.json"')


def test_a_private_dependency_inventory_is_not_cached_by_anything_between(
    auth_client, combined
):
    assert auth_client.get(url(combined, "md"))["Cache-Control"] == "private, no-store"


def test_the_json_is_section_5_8s_payload(auth_client, combined):
    """§5.8 is binding and is what an external agent parses."""
    payload = json.loads(auth_client.get(url(combined, "json")).content)

    assert payload["summary_md"] == "Upgrade lodash first."
    assert payload["fixes"] == [FIX]
    # Every §5.8 key, in §5.8's snake_case, unrewritten.
    assert set(payload["fixes"][0]) == {
        "package",
        "manifest_path",
        "ecosystem",
        "current_version",
        "fix_type",
        "target_version",
        "replacement_package",
        "cves",
        "severity",
        "priority",
    }


def test_the_json_says_what_it_is_a_payload_about(auth_client, combined):
    """A bare fixes array tells an agent what to do and not *to what*."""
    payload = json.loads(auth_client.get(url(combined, "json")).content)

    assert payload["repository"] == combined.scan.repository.full_name
    assert payload["scan_id"] == str(combined.scan_id)
    assert payload["scoring_formula_version"] == combined.scan.scoring_formula_version
    assert payload["report_type"] == ReportType.COMBINED.value
    assert "never applies them" in payload["note"]


def test_the_markdown_carries_the_scan_the_fixes_and_the_closing_note(combined):
    text = render_markdown(combined)

    assert text.startswith("# Dependency triage - ")
    assert "## Recommended fixes" in text
    assert "| 1 | `lodash` | package.json | 4.17.19 | Upgrade to 4.17.21 |" in text
    assert "CVE-2021-23337" in text
    assert text.rstrip().endswith(
        "reading this file is the only thing that has happened."
    )


def test_a_pipe_in_a_manifest_path_cannot_break_the_table(scan):
    """It would shift every column after it — the table still renders, wrong."""
    report = ReportFactory(
        scan=scan, fixes_json=[{**FIX, "manifest_path": "weird|name/package.json"}]
    )

    row = next(
        line for line in render_markdown(report).splitlines() if line.startswith("| 1 ")
    )

    assert r"weird\|name/package.json" in row
    # Six columns, still: the escape is what keeps the count right.
    assert row.count("|") - row.count(r"\|") == 7


def test_a_report_generated_twice_downloads_identically(auth_client, combined):
    """Determinism (§11): the download is a pure function of the stored row."""
    first = auth_client.get(url(combined, "md")).content
    second = auth_client.get(url(combined, "md")).content

    assert first == second


# ── Per-dependency: the citations and the confidence note ───────────────────


def test_the_cited_passage_travels_inside_the_markdown(auth_client, scan):
    """A file read away from the product has no citation pane beside it."""
    report = per_dependency(scan)

    text = render_markdown(report)

    assert "## Sources cited" in text
    assert "### 1. `CHANGELOG.md` - 4.17.21 (similarity 0.71)" in text
    assert "> - fix prototype pollution in zipObjectDeep" in text


def test_the_json_citation_carries_its_source_not_just_an_id(auth_client, scan):
    """A chunk id is a content digest and means nothing outside this product."""
    report = per_dependency(scan)

    citations = render_json(report)["citations"]

    assert citations == [
        {
            "chunk_id": "c1",
            "source_path": "CHANGELOG.md",
            "source_sha": "abc123",
            "heading": "4.17.21",
            "similarity": 0.71,
            "text": CHUNK["text"],
        }
    ]


def test_a_citation_naming_no_retrieved_chunk_is_dropped(scan):
    """Rather than rendered as an empty quotation under a numbered heading."""
    report = per_dependency(scan, citations_json=["c1", "ghost"])

    text = render_markdown(report)

    assert text.count("### 1.") == 1
    assert "### 2." not in text
    assert "ghost" not in text


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {},
            "Grounded in 1 retrieved passage",
        ),
        (
            {
                "grounding_confidence": GroundingConfidence.LOW.value,
                "retrieved_chunks_json": [],
                "citations_json": [],
            },
            "No source material.",
        ),
        (
            {"grounding_confidence": GroundingConfidence.LOW.value, "citations_json": []},
            "Not enough source material.",
        ),
        (
            {"citations_json": []},
            "Nothing cited.",
        ),
    ],
    ids=["grounded", "nothing-retrieved", "weak-match", "cleared-the-gate-cited-nothing"],
)
def test_the_confidence_note_says_which_of_four_findings_this_is(
    scan, overrides, expected
):
    """§8.14's lesson, carried into the file.

    "We retrieved something relevant" and "the answer is grounded in it" are
    two different claims, and the page learned that the hard way against a real
    `django` row. A downloaded plan with no caveat on it is the same defect
    with the banner removed.
    """
    report = per_dependency(scan, **overrides)

    assert expected in render_markdown(report)


def test_the_passages_are_printed_even_when_the_plan_cited_none_of_them(scan):
    """A caveat the reader cannot check is not much of a caveat.

    The note says retrieval found passages and the plan rests on none of them.
    Withholding those passages would leave that unfalsifiable.
    """
    report = per_dependency(scan, citations_json=[])

    text = render_markdown(report)

    assert "## Sources retrieved (none cited)" in text
    assert "fix prototype pollution" in text


def test_a_combined_report_says_it_was_never_grounded(combined):
    """§5.9 keeps COMBINED out of the retrieval graph — a property, not a failure."""
    text = render_markdown(combined)

    assert "Not grounded, by design." in text
    assert "## Sources" not in text


# ── What it refuses ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("query", ["", "?fmt=", "?fmt=pdf", "?fmt=markdown"])
def test_a_format_it_does_not_know_is_refused_rather_than_guessed(
    auth_client, combined, query
):
    """Two genuinely different artifacts; choosing for the caller is a guess.

    No default, including for a missing `fmt`. §10 names both formats and no
    default, and picking one for a caller who did not say is the same kind of
    invention `_boolean_param` refuses when asked what `?flagged=maybe` means.
    """
    response = auth_client.get(f"/api/reports/{combined.pk}/download/{query}")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_format"


@pytest.mark.parametrize("query", ["?fmt=MD", "?fmt=%20json%20", "?fmt=Json"])
def test_the_format_name_itself_is_read_leniently(auth_client, combined, query):
    """Case and surrounding space, unlike the rescan confirmation.

    The two are deliberately different. `fmt` chooses between two renderings of
    a row that is already on disk and nothing is destroyed by reading it the
    obvious way; `confirm` destroys generated work, so it takes one spelling
    and no guesses (`apps/scanning/views.py::_confirmed`).
    """
    assert (
        auth_client.get(f"/api/reports/{combined.pk}/download/{query}").status_code == 200
    )


@pytest.mark.parametrize(
    "status",
    [ReportStatus.QUEUED.value, ReportStatus.RUNNING.value, ReportStatus.FAILED.value],
)
def test_an_unfinished_report_has_nothing_to_download(auth_client, scan, status):
    """An empty document that looks like an answer is worse than a refusal."""
    report = ReportFactory(scan=scan, status=status, summary_text=None, generated_at=None)

    response = auth_client.get(url(report, "md"))

    assert response.status_code == 409
    assert response.json()["code"] == "report_not_downloadable"


def test_signing_out_is_enough_to_lose_the_file(api_client, combined):
    """No session, no download — it is a resource route like any other.

    403 rather than 401 because the API authenticates by session cookie and
    offers no challenge to repeat: DRF answers 401 only when an authentication
    class advertises a `WWW-Authenticate` scheme, which a cookie does not.
    """
    response = api_client.get(url(combined, "md"))

    assert response.status_code == 403
    assert response.json()["code"] == "not_authenticated"


def test_a_browser_navigating_to_the_link_is_not_told_406(auth_client, combined):
    """The link is followed by a browser, whose Accept header is not JSON.

    Without a renderer that matches anything, DRF negotiates against
    `DEFAULT_RENDERER_CLASSES` — JSON alone — and a client that does not send
    `*/*` gets a 406 instead of a file.
    """
    response = auth_client.get(
        url(combined, "md"), HTTP_ACCEPT="text/html,application/xhtml+xml;q=0.9"
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/markdown; charset=utf-8"


def test_the_filename_survives_a_repository_name_that_is_not_filename_safe(scan):
    """GitHub's own names are already safe; a filename is interpreted elsewhere."""
    from apps.reports.download import filename

    scan.repository.name = "../../etc/passwd"
    report = ReportFactory(scan=scan)

    name = filename(report, "md")

    assert "/" not in name
    assert ".." not in name
    assert name.startswith("repovitals_etc-passwd_combined_")
