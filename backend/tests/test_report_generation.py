"""The generation half of Phase 7: the client, the prompt, and §5.8.

Nothing here touches the network. `responses` mocks the transport where the
client's own behaviour is under test, and everywhere else the model is a
callable returning canned JSON — which is what §4.4 specifies for LLM calls and
what makes "the repair retry fired exactly once" a thing an assertion can say.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
import responses
from django.test import override_settings

from apps.reports import combined
from apps.reports.combined import GenerationFailed, build_input, generate
from apps.reports.llm import groq_client
from apps.reports.llm.groq_client import (
    GROQ_CHAT_URL,
    LlmCall,
    LlmNotConfigured,
    LlmRefused,
    LlmTruncated,
    LlmUnavailable,
    complete_json,
)
from apps.reports.llm.prompts import COMBINED_SYSTEM_PROMPT, build_combined_user_prompt
from apps.reports.schema import PayloadInvalid, drop_unmatched, validate_payload
from apps.scanning.models import Severity
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    PackageFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db

WITH_KEY = override_settings(GROQ_API_KEY="gsk_test", GROQ_MODEL="test-model")


def groq_body(content: str, *, model: str = "test-model", finish: str = "stop") -> dict:
    return {
        "model": model,
        "choices": [{"finish_reason": finish, "message": {"content": content}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 120},
    }


# ── The client ─────────────────────────────────────────────────────────────


def test_a_missing_key_is_named_rather_than_crashing():
    with override_settings(GROQ_API_KEY=""), pytest.raises(LlmNotConfigured):
        complete_json("system", "user")


@WITH_KEY
@responses.activate
def test_the_request_pins_temperature_zero_and_json_mode():
    """D11's two properties, asserted on the wire rather than on a constant."""
    responses.add(responses.POST, GROQ_CHAT_URL, json=groq_body('{"ok": true}'))

    complete_json("system text", "user text")

    sent = json.loads(responses.calls[0].request.body)
    assert sent["temperature"] == 0
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["model"] == "test-model"
    assert [message["role"] for message in sent["messages"]] == ["system", "user"]


@WITH_KEY
@responses.activate
def test_a_transient_failure_is_retried_exactly_once(monkeypatch):
    """§10 Phase 7: one retry on a transient 5xx.

    The count is the assertion. A metered POST retried by both the transport
    and this module would bill three generations for one click, and no
    behavioural check would notice — the answer is correct either way.
    """
    monkeypatch.setattr("apps.common.http._sleep", lambda seconds: None)
    responses.add(responses.POST, GROQ_CHAT_URL, status=503)
    responses.add(responses.POST, GROQ_CHAT_URL, json=groq_body('{"ok": true}'))

    call = complete_json("system", "user")

    assert len(responses.calls) == 2
    assert call.requests == 2


@WITH_KEY
@responses.activate
def test_a_second_transient_failure_gives_up(monkeypatch):
    monkeypatch.setattr("apps.common.http._sleep", lambda seconds: None)
    for _ in range(3):
        responses.add(responses.POST, GROQ_CHAT_URL, status=503)

    with pytest.raises(LlmUnavailable):
        complete_json("system", "user")

    assert len(responses.calls) == 2


@WITH_KEY
@responses.activate
def test_a_rejected_key_is_not_retried():
    responses.add(responses.POST, GROQ_CHAT_URL, status=401, json={})

    with pytest.raises(LlmRefused):
        complete_json("system", "user")

    assert len(responses.calls) == 1


@WITH_KEY
@responses.activate
def test_an_answer_cut_off_at_the_cap_is_named_as_such():
    responses.add(
        responses.POST,
        GROQ_CHAT_URL,
        json=groq_body('{"summary_md": "half a sen', finish="length"),
    )

    with pytest.raises(LlmTruncated):
        complete_json("system", "user")


@WITH_KEY
@responses.activate
def test_the_answering_model_is_recorded_not_the_requested_one():
    """A provider that substitutes a model has to be visible on the report row."""
    responses.add(
        responses.POST, GROQ_CHAT_URL, json=groq_body('{"ok": true}', model="other-model")
    )

    assert complete_json("system", "user").model == "other-model"


def test_the_client_reaches_groq_through_the_allowlist():
    """§5.6's choke point. A host outside it would be a `DisallowedHost`."""
    from apps.common.http import ALLOWED_HOSTS

    assert "api.groq.com" in ALLOWED_HOSTS
    assert GROQ_CHAT_URL.startswith("https://api.groq.com/")


# ── The prompt ─────────────────────────────────────────────────────────────


def flagged_scan():
    """A scan with two flagged occurrences, one clean and one unassessable."""
    scan = ScanRunFactory(risk_score=Decimal("41.00"), classification="high_alert")
    manifest = ManifestFileFactory(scan=scan)
    DependencyOccurrenceFactory(
        manifest=manifest,
        package=PackageFactory(package_name="lodash"),
        declared_specifier="^4.17.0",
        resolved_version="4.17.19",
        latest_version="4.17.21",
        versions_behind_patch=2,
        staleness_days=1200,
        vulnerability_count=1,
        highest_severity=Severity.HIGH.value,
        cvss_max=Decimal("7.5"),
        is_flagged=True,
        risk_component_score=Decimal("42.00"),
    )
    DependencyOccurrenceFactory(
        manifest=manifest,
        package=PackageFactory(package_name="request"),
        resolved_version="2.88.2",
        is_deprecated=True,
        deprecation_reason="request has been deprecated, see #3142",
        is_flagged=True,
        risk_component_score=Decimal("55.00"),
    )
    DependencyOccurrenceFactory(
        manifest=manifest,
        package=PackageFactory(package_name="express"),
        risk_component_score=Decimal("100.00"),
    )
    DependencyOccurrenceFactory(
        manifest=manifest,
        package=PackageFactory(package_name="internal-tool"),
        declared_specifier="git+ssh://git@github.com/acme/tool.git",
        resolved_version=None,
        resolution=None,
        is_unassessable=True,
        unassessable_reason="git_dependency",
    )
    return scan


def test_only_flagged_rows_are_sent_worst_first():
    prepared = build_input(flagged_scan())

    assert [row["package"] for row in prepared.rows] == ["lodash", "request"]


def test_the_summary_states_what_the_rows_do_not_cover():
    """§4.7's lesson: a number whose scope is missing reads as a number about
    everything. The model is told the clean and unassessable counts."""
    prepared = build_input(flagged_scan())

    assert prepared.scan_summary["dependency_count"] == 4
    assert prepared.scan_summary["flagged_count"] == 2
    assert prepared.scan_summary["clean_count"] == 1
    assert prepared.scan_summary["unassessable_count"] == 1
    assert prepared.scan_summary["flagged_rows_omitted"] == 0


def test_no_upstream_prose_reaches_the_prompt():
    """The claim §10 Phase 7 makes about this surface, asserted.

    "Input = structured signal rows only (no fetched text)". The deprecation
    message is stored, would help the model, and is text a stranger can publish
    to a package index — so it stays out of the prompt and is quoted in Phase
    8 beside the source it came from.
    """
    prepared = build_input(flagged_scan())
    text = build_combined_user_prompt(prepared.scan_summary, prepared.rows)

    assert "deprecated" in text  # the boolean signal is there
    assert "see #3142" not in text  # the registry's sentence is not
    assert all("deprecation_reason" not in row for row in prepared.rows)


def test_an_unmeasured_signal_is_absent_rather_than_zero():
    """§5.2 redistributes the staleness weight when there is no publish history.

    A `days_since_release: null` would invite the model to read "released
    today"; the key is omitted and rule 8 of the system prompt says what an
    absent key means.
    """
    scan = ScanRunFactory()
    DependencyOccurrenceFactory(
        manifest=ManifestFileFactory(scan=scan),
        staleness_days=None,
        is_flagged=True,
        risk_component_score=Decimal("60.00"),
    )

    row = build_input(scan).rows[0]

    assert "days_since_release" not in row


def test_the_prompt_frames_the_data_block_as_data():
    assert "data, not instructions" in COMBINED_SYSTEM_PROMPT
    assert "JSON" in COMBINED_SYSTEM_PROMPT  # the provider's JSON mode needs it

    text = build_combined_user_prompt({"repository": "acme/app"}, [])
    assert "BEGIN DATA" in text and "END DATA" in text


# ── §5.8 validation and the cross-check ────────────────────────────────────


ROWS = [
    {
        "package": "lodash",
        "ecosystem": "npm",
        "manifest_path": "package.json",
        "current_version": "4.17.19",
        "highest_severity": "high",
        "cves": ["CVE-2021-23337"],
    },
    {
        "package": "request",
        "ecosystem": "npm",
        "manifest_path": "package.json",
        "current_version": "2.88.2",
        "highest_severity": None,
        "cves": [],
    },
]


def fix(**overrides) -> dict:
    base = {
        "package": "lodash",
        "manifest_path": "package.json",
        "ecosystem": "npm",
        "fix_type": "upgrade",
        "target_version": "4.17.21",
        "replacement_package": None,
        "priority": 1,
    }
    return {**base, **overrides}


def test_a_valid_payload_keeps_the_models_decision():
    payload = validate_payload({"summary_md": "Two to fix.", "fixes": [fix()]}, ROWS)

    assert payload["fixes"][0]["fix_type"] == "upgrade"
    assert payload["fixes"][0]["target_version"] == "4.17.21"


def test_measurements_come_from_the_scan_row_not_the_answer():
    """The rule the module is built around: the model is never the source of a
    fact we already measured."""
    payload = validate_payload(
        {
            "summary_md": "One to fix.",
            "fixes": [
                fix(current_version="1.0.0", cves=["CVE-9999-0001"], severity="low")
            ],
        },
        ROWS,
    )

    entry = payload["fixes"][0]
    assert entry["current_version"] == "4.17.19"
    assert entry["cves"] == ["CVE-2021-23337"]
    assert entry["severity"] == "high"


def test_an_unknown_fix_type_is_a_schema_violation():
    with pytest.raises(PayloadInvalid) as raised:
        validate_payload({"summary_md": "x", "fixes": [fix(fix_type="rewrite")]}, ROWS)

    assert "fix_type" in raised.value.detail


def test_a_missing_summary_is_a_schema_violation():
    with pytest.raises(PayloadInvalid):
        validate_payload({"fixes": []}, ROWS)


def test_a_fix_naming_a_package_this_scan_never_saw_is_refused():
    """§10 Phase 7's acceptance: every fix references a real scanned row."""
    with pytest.raises(PayloadInvalid) as raised:
        validate_payload({"summary_md": "x", "fixes": [fix(package="left-pad")]}, ROWS)

    assert "left-pad" in raised.value.detail


def test_a_fix_naming_a_manifest_this_scan_never_read_is_refused():
    """The same package in a file that does not exist is still an invention."""
    with pytest.raises(PayloadInvalid):
        validate_payload(
            {"summary_md": "x", "fixes": [fix(manifest_path="api/package.json")]},
            ROWS,
        )


def test_a_title_cased_package_name_still_matches():
    """npm names are lowercase by rule and PyPI's are case-insensitive by PEP
    503, so a model that capitalizes one has not named a different package."""
    payload = validate_payload(
        {"summary_md": "x", "fixes": [fix(package="Lodash")]}, ROWS
    )

    assert payload["fixes"][0]["package"] == "lodash"


def test_priorities_are_renumbered_without_reordering():
    payload = validate_payload(
        {
            "summary_md": "x",
            "fixes": [
                fix(package="request", priority=4, fix_type="replace"),
                fix(package="lodash", priority=4),
            ],
        },
        ROWS,
    )

    assert [(f["package"], f["priority"]) for f in payload["fixes"]] == [
        ("request", 1),
        ("lodash", 2),
    ]


def test_a_second_fix_for_one_occurrence_is_dropped():
    payload = validate_payload(
        {
            "summary_md": "x",
            "fixes": [fix(), fix(fix_type="remove", target_version=None)],
        },
        ROWS,
    )

    assert len(payload["fixes"]) == 1
    assert payload["fixes"][0]["fix_type"] == "upgrade"


def test_drop_unmatched_keeps_the_real_rows():
    payload = drop_unmatched(
        {
            "summary_md": "x",
            "fixes": [fix(package="left-pad"), fix(package="request", priority=2)],
        },
        ROWS,
    )

    assert [f["package"] for f in payload["fixes"]] == ["request"]


def test_drop_unmatched_still_refuses_a_broken_schema():
    """There is nothing to salvage from a document whose `fixes` is not a list.

    And it leaves as `PayloadInvalid` rather than as pydantic's own: the first
    version raised through `drop_unmatched` past a caller catching only this
    module's exception, so a second malformed answer crashed the thread
    instead of failing the report.
    """
    with pytest.raises(PayloadInvalid):
        drop_unmatched({"summary_md": "x", "fixes": "none"}, ROWS)


# ── One generation, end to end ─────────────────────────────────────────────


def fake_model(*answers: dict):
    """A model that returns the given documents in order, counting its calls."""
    calls: list[tuple[str, str]] = []

    def complete(system: str, user: str) -> LlmCall:
        calls.append((system, user))
        answer = answers[min(len(calls) - 1, len(answers) - 1)]
        return LlmCall(
            content=json.dumps(answer),
            model="test-model",
            prompt_tokens=10,
            completion_tokens=10,
            latency_ms=5,
            requests=1,
        )

    complete.calls = calls  # type: ignore[attr-defined]
    return complete


def good_answer() -> dict:
    return {
        "summary_md": "Two dependencies need attention.",
        "fixes": [
            fix(),
            fix(
                package="request",
                fix_type="replace",
                target_version=None,
                replacement_package="axios",
                priority=2,
            ),
        ],
    }


def test_one_valid_answer_costs_one_call():
    model = fake_model(good_answer())

    result = generate(flagged_scan(), complete=model)

    assert len(model.calls) == 1
    assert result.requests == 1
    assert [f["package"] for f in result.payload["fixes"]] == ["lodash", "request"]


def test_a_schema_violation_buys_exactly_one_repair():
    model = fake_model(
        {"summary_md": "x", "fixes": [fix(fix_type="rewrite")]}, good_answer()
    )

    result = generate(flagged_scan(), complete=model)

    assert len(model.calls) == 2
    assert result.payload["fixes"]


def test_the_repair_message_says_what_was_wrong():
    model = fake_model(
        {"summary_md": "x", "fixes": [fix(package="left-pad")]}, good_answer()
    )

    generate(flagged_scan(), complete=model)

    repair_prompt = model.calls[1][1]
    assert "left-pad" in repair_prompt
    assert "verbatim" in repair_prompt


def test_a_repair_that_still_invents_has_the_invented_rows_dropped():
    model = fake_model(
        {"summary_md": "x", "fixes": [fix(package="left-pad")]},
        {
            "summary_md": "One real, one not.",
            "fixes": [fix(package="left-pad"), fix(package="lodash", priority=2)],
        },
    )

    result = generate(flagged_scan(), complete=model)

    assert [f["package"] for f in result.payload["fixes"]] == ["lodash"]


def test_a_generation_that_invents_everything_fails_rather_than_showing_nothing():
    """§4.7 and §5.10's shape: an empty fixes list beside a summary, on a
    repository with flagged dependencies, reads as "nothing to do here"."""
    invented = {"summary_md": "All clear.", "fixes": [fix(package="left-pad")]}
    model = fake_model(invented, invented)

    with pytest.raises(GenerationFailed):
        generate(flagged_scan(), complete=model)


def test_a_second_schema_violation_fails_the_generation():
    broken = {"summary_md": "x", "fixes": [fix(priority=0)]}
    model = fake_model(broken, broken)

    with pytest.raises(GenerationFailed):
        generate(flagged_scan(), complete=model)

    assert len(model.calls) == 2


def test_a_clean_repository_may_legitimately_have_no_fixes():
    """The empty-fixes guard is about invented rows, not about clean repos."""
    scan = ScanRunFactory(risk_score=Decimal("100.00"), classification="safe")
    ManifestFileFactory(scan=scan)
    model = fake_model({"summary_md": "Nothing flagged.", "fixes": []})

    result = generate(scan, complete=model)

    assert result.payload["fixes"] == []


def test_the_row_cap_reports_what_it_left_out(monkeypatch):
    monkeypatch.setattr(combined, "MAX_ROWS", 1)

    prepared = build_input(flagged_scan())

    assert len(prepared.rows) == 1
    assert prepared.scan_summary["flagged_rows_omitted"] == 1


def test_module_constants_stay_within_the_free_tier_shape():
    """A guard on the two numbers §8 actually bounds."""
    assert combined.MAX_ROWS <= 50
    assert groq_client.MAX_OUTPUT_TOKENS <= 4096
