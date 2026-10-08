"""Correctness, the judge, and its cache (§10 Phase 13 commit 5).

§10 Phase 13's acceptance names two of these: "judge cache hits on re-run" and
"correctness fixture matrix passes". The matrix is below, case by case; the
cache test counts HTTP requests rather than trusting a hit counter.
"""

from __future__ import annotations

import json

import pytest
import responses

from apps.common import http
from apps.research.experiment import groundtruth as gt
from apps.research.experiment import judge, metrics, runner

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

CVE_ITEM = {
    "item_id": "S3-cve",
    "case_type": gt.CVE_FIX,
    "ecosystem": "npm",
    "package": "lodash",
    "resolved_version": "4.17.19",
    "target": {"package": "lodash", "current_version": "4.17.19"},
    "ground_truth": {
        "target_version": "4.17.21",
        "advisories": [
            {"osv_id": "A", "intervals": [{"introduced": "0", "fixed": "4.17.21"}], "versions": []},
            {"osv_id": "B", "intervals": [{"introduced": "0", "fixed": "4.17.20"},
                                          {"introduced": "4.17.22", "fixed": "4.17.23"}],
             "versions": []},
        ],
    },
}  # fmt: skip

REPLACEMENT_ITEM = {
    "item_id": "S3-rep",
    "case_type": gt.DEPRECATION_REPLACEMENT,
    "ecosystem": "pypi",
    "package": "oldpkg",
    "resolved_version": "1.0",
    "target": {"package": "oldpkg", "current_version": "1.0"},
    "ground_truth": {"successor": "New_Pkg", "successor_normalized": "new-pkg"},
}


def generation(**fix) -> dict:
    base = {"package": "lodash", "fix_type": "upgrade", "priority": 1}
    return {"summary_md": "Upgrade.", "fixes": [{**base, **fix}]}


# ── correctness ────────────────────────────────────────────────────────────


class TestCorrectnessMatrix:
    @pytest.mark.parametrize(
        ("target_version", "correct", "reason"),
        [
            ("4.17.21", True, "escapes_every_advisory"),
            ("^4.17.21", True, "escapes_every_advisory"),
            (">=4.17.21", True, "escapes_every_advisory"),
            ("v4.17.21", True, "escapes_every_advisory"),
            ("4.17.24", True, "escapes_every_advisory"),  # later and still safe
            ("4.17.22", False, "still_affected_or_not_an_upgrade"),  # B reopens here
            ("4.17.20", False, "still_affected_or_not_an_upgrade"),  # escapes B, not A
            ("4.17.18", False, "still_affected_or_not_an_upgrade"),  # a downgrade
            ("latest", False, "unreadable_version"),
            ("4.x", False, "unreadable_version"),
            (None, False, "no_version"),
        ],
    )
    def test_cve_fix(self, target_version, correct, reason):
        found = metrics.correctness(CVE_ITEM, generation(target_version=target_version))
        assert (found.correct, found.reason) == (correct, reason)

    def test_replacing_where_an_upgrade_exists_is_not_a_fix(self):
        found = metrics.correctness(
            CVE_ITEM, generation(fix_type="replace", replacement_package="lodash-es")
        )
        assert (found.correct, found.reason) == (False, "not_an_upgrade")

    def test_a_fix_for_another_package_is_not_a_recommendation(self):
        found = metrics.correctness(
            CVE_ITEM, generation(package="underscore", target_version="1.13.0")
        )
        assert (found.correct, found.reason) == (False, "no_fix_for_this_package")

    def test_the_highest_priority_fix_is_the_recommendation(self):
        found = metrics.correctness(
            CVE_ITEM,
            {
                "fixes": [
                    {
                        "package": "lodash",
                        "fix_type": "upgrade",
                        "target_version": "4.17.20",
                        "priority": 2,
                    },
                    {
                        "package": "lodash",
                        "fix_type": "upgrade",
                        "target_version": "4.17.21",
                        "priority": 1,
                    },
                ]
            },
        )
        assert found.correct

    @pytest.mark.parametrize(
        ("replacement", "correct", "reason"),
        [
            ("new-pkg", True, "successor_named"),
            ("New_Pkg", True, "successor_named"),
            ("new.pkg", True, "successor_named"),
            ("other-pkg", False, "different_replacement"),
            (None, False, "no_replacement"),
        ],
    )
    def test_deprecation_replacement(self, replacement, correct, reason):
        found = metrics.correctness(
            REPLACEMENT_ITEM,
            {
                "fixes": [
                    {
                        "package": "oldpkg",
                        "fix_type": "replace",
                        "replacement_package": replacement,
                    }
                ]
            },
        )
        assert (found.correct, found.reason) == (correct, reason)

    @pytest.mark.parametrize(
        ("summary", "declared"),
        [
            (
                "RepoVitals could not retrieve enough of this package's documentation.",
                True,
            ),
            ("The sources provide insufficient information to name a successor.", True),
            ("Upgrade to 4.17.21, which fixes it.", False),
        ],
    )
    def test_declared_insufficiency(self, summary, declared):
        assert metrics.declared_insufficient({"summary_md": summary}) is declared

    def test_a_failed_generation_has_no_correctness(self):
        found = metrics.measure(
            {"item_id": "S3-cve", "condition": "A", "status": "failed"}, CVE_ITEM
        )
        assert found.correct is None
        assert found.correctness_reason == "generation_failed"


# ── the rubric ─────────────────────────────────────────────────────────────


class TestAnswerGiven:
    """decisions §13.13: does TARGET already show a value that is correct if copied?"""

    @staticmethod
    def shown(*fixed: str) -> dict:
        built = json.loads(json.dumps(CVE_ITEM))
        built["target"]["advisories"] = [
            {"osv_id": f"X{index}", "fixed_version": version}
            for index, version in enumerate(fixed)
        ]
        return built

    def test_a_shown_fix_that_escapes_every_advisory_is_the_answer(self):
        assert gt.answer_given(self.shown("4.17.20", "4.17.21"))

    def test_shown_fixes_each_still_affected_leave_it_to_be_worked_out(self):
        """4.17.20 is still under A; 4.17.22 re-enters B."""
        assert not gt.answer_given(self.shown("4.17.20", "4.17.22"))

    def test_no_fixed_version_shown_is_not_given(self):
        assert not gt.answer_given(self.shown())
        assert not gt.answer_given(CVE_ITEM)

    def test_a_deprecation_sentence_naming_the_successor_gives_it(self):
        item = json.loads(json.dumps(REPLACEMENT_ITEM))
        item["target"]["deprecation_reason"] = "Deprecated. Use new_pkg instead."
        assert gt.answer_given(item)
        item["target"]["deprecation_reason"] = "Deprecated. Use other-pkg instead."
        assert not gt.answer_given(item)

    def test_every_measured_row_carries_it(self):
        record = {
            "item_id": "S3-cve",
            "condition": "A",
            "status": "ok",
            "generation": generation(target_version="4.17.21"),
        }
        assert metrics.measure(record, self.shown("4.17.21")).answer_given is True
        assert metrics.measure(record, CVE_ITEM).answer_given is False


class TestTheVerdictRule:
    @pytest.mark.parametrize(
        ("claims", "verdict"),
        [
            ([{"core": True, "supported": True}], judge.FAITHFUL),
            ([], judge.FAITHFUL),
            (
                [{"core": True, "supported": True}, {"core": False, "supported": False}],
                judge.MINOR,
            ),
            (
                [
                    {"core": False, "supported": False},
                    {"core": False, "supported": False},
                ],
                judge.MAJOR,
            ),
            ([{"core": True, "supported": False}], judge.MAJOR),
        ],
    )
    def test_file_bs_rule(self, claims, verdict):
        assert judge.verdict_from_claims(claims) == verdict

    def test_the_relevance_question_never_contains_the_answer(self):
        question = judge.relevance_question(CVE_ITEM)
        assert "4.17.21" not in question
        assert "new-pkg" not in judge.relevance_question(REPLACEMENT_ITEM).lower()


# ── the Gemini client ──────────────────────────────────────────────────────


def gemini_answer(payload: dict, model: str = "gemini-2.5-flash") -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": json.dumps(payload)}]},
                "finishReason": "STOP",
            }
        ],
        "modelVersion": model,
    }


@pytest.fixture(autouse=True)
def quiet(monkeypatch, settings):
    monkeypatch.setattr(http, "_local", type(http._local)())
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(judge, "_sleep", lambda _seconds: None)
    settings.GEMINI_API_KEY = "gemini-test-key"
    settings.JUDGE_MODEL = "gemini-2.5-flash"


class TestTheClient:
    @responses.activate
    def test_the_key_is_a_header_and_never_in_the_url(self):
        responses.add(responses.POST, GEMINI, json=gemini_answer({"ok": True}))
        assert judge.complete_judge("system", "user") == {"ok": True}
        request = responses.calls[0].request
        assert request.headers["x-goog-api-key"] == "gemini-test-key"
        assert "gemini-test-key" not in request.url
        body = json.loads(request.body)
        assert body["generationConfig"] == {
            "temperature": 0,
            "responseMimeType": "application/json",
        }
        assert body["systemInstruction"]["parts"][0]["text"] == "system"

    @pytest.mark.parametrize(
        ("status", "error"),
        [(404, judge.JudgeRefused), (403, judge.JudgeRefused), (400, judge.JudgeRefused),
         (429, judge.JudgeUnavailable), (503, judge.JudgeUnavailable)],
    )  # fmt: skip
    @responses.activate
    def test_errors_say_whether_waiting_helps(self, status, error):
        responses.add(responses.POST, GEMINI, status=status, json={})
        with pytest.raises(error):
            judge.complete_judge("s", "u")

    def test_no_key_is_a_configuration_not_a_crash(self, settings):
        settings.GEMINI_API_KEY = ""
        assert not judge.is_configured()
        with pytest.raises(judge.JudgeNotConfigured):
            judge.complete_judge("s", "u")

    def test_gemini_is_on_the_allowlist(self):
        assert "generativelanguage.googleapis.com" in http.ALLOWED_HOSTS


# ── the cache, and judging a record ────────────────────────────────────────

RECORD = {
    "item_id": "S3-cve",
    "condition": "C",
    "status": "ok",
    "generation": generation(target_version="4.17.21"),
    "retrieved": [
        {
            "chunk_id": "c1",
            "text": "4.17.21 fixes prototype pollution",
            "source_path": "CHANGELOG.md",
        },
        {"chunk_id": "c2", "text": "docs only", "source_path": "CHANGELOG.md"},
    ],
    "shown_chunk_ids": ["c1", "c2"],
}


def mock_judge() -> None:
    def answer(request):
        prompt = json.loads(request.body)["contents"][0]["parts"][0]["text"]
        if "QUESTION:" in prompt:
            payload = {
                "passages": [
                    {"id": "c1", "relevant": True},
                    {"id": "c2", "relevant": False},
                ]
            }
        else:
            payload = {
                "claims": [
                    {
                        "claim": "Upgrade to 4.17.21",
                        "core": True,
                        "supported": True,
                        "evidence": "c1",
                    },
                    {
                        "claim": "It is faster",
                        "core": False,
                        "supported": False,
                        "evidence": None,
                    },
                ],
                "verdict": "faithful",  # disagrees with its own claims
                "note": "speed claim",
            }
        return (200, {}, json.dumps(gemini_answer(payload)))

    responses.add_callback(responses.POST, GEMINI, callback=answer)


class TestJudging:
    @responses.activate
    def test_a_record_is_judged_and_the_verdict_comes_from_the_claims(self, tmp_path):
        mock_judge()
        found = judge.Judge(cache=judge.JudgeCache(tmp_path / "cache.jsonl")).judge(
            RECORD, CVE_ITEM
        )
        assert found["faithfulness"]["verdict"] == judge.MINOR
        assert found["faithfulness"]["stated_verdict"] == judge.FAITHFUL
        assert found["relevance"]["precision_at_k"] == 0.5
        assert found["relevance"]["k"] == 2

    @responses.activate
    def test_a_rerun_is_served_from_the_cache(self, tmp_path):
        """§10 Phase 13's acceptance: judge cache hits on re-run."""
        mock_judge()
        path = tmp_path / "cache.jsonl"
        judge.Judge(cache=judge.JudgeCache(path)).judge(RECORD, CVE_ITEM)
        asked = len(responses.calls)

        again = judge.Judge(cache=judge.JudgeCache(path))
        again.judge(RECORD, CVE_ITEM)

        assert asked == 2
        assert len(responses.calls) == 2
        assert again.hits == 2

    @responses.activate
    def test_a_changed_answer_is_judged_again(self, tmp_path):
        mock_judge()
        path = tmp_path / "cache.jsonl"
        judge.Judge(cache=judge.JudgeCache(path)).judge(RECORD, CVE_ITEM)
        changed = {**RECORD, "generation": generation(target_version="4.17.24")}
        judge.Judge(cache=judge.JudgeCache(path)).judge(changed, CVE_ITEM)
        assert len(responses.calls) == 3  # faithfulness again; relevance unchanged

    @responses.activate
    def test_only_the_passages_the_model_was_shown_are_evidence(self, tmp_path):
        mock_judge()
        withheld = {**RECORD, "shown_chunk_ids": []}
        judge.Judge(cache=judge.JudgeCache(tmp_path / "c.jsonl")).faithfulness(
            withheld, CVE_ITEM
        )
        prompt = json.loads(responses.calls[0].request.body)["contents"][0]["parts"][0][
            "text"
        ]
        assert "(empty: the author was shown no passages)" in prompt
        assert "4.17.21 fixes prototype pollution" not in prompt

    def test_a_failed_generation_is_not_judged(self, tmp_path):
        assert (
            judge.Judge(cache=judge.JudgeCache(tmp_path / "c.jsonl")).judge(
                {**RECORD, "status": "failed"}, CVE_ITEM
            )
            == {}
        )

    def test_condition_a_has_no_precision(self, tmp_path):
        assert (
            judge.Judge(cache=judge.JudgeCache(tmp_path / "c.jsonl")).relevance(
                {**RECORD, "retrieved": []}, CVE_ITEM
            )
            is None
        )


class TestRetries:
    @responses.activate
    def test_an_overloaded_model_is_retried_not_given_up_on(self, tmp_path):
        """Gemini's first live answer to this module was a 503, then a result."""
        responses.add(responses.POST, GEMINI, status=503, json={})
        mock_judge()  # registered second: answers from the second call on
        found = judge.Judge(cache=judge.JudgeCache(tmp_path / "c.jsonl")).faithfulness(
            RECORD, CVE_ITEM
        )
        assert found["verdict"] == judge.MINOR
        assert len(responses.calls) == 2

    @responses.activate
    def test_three_non_answers_are_unavailable(self, tmp_path):
        responses.add(responses.POST, GEMINI, status=503, json={})
        with pytest.raises(judge.JudgeUnavailable):
            judge.Judge(cache=judge.JudgeCache(tmp_path / "c.jsonl")).faithfulness(
                RECORD, CVE_ITEM
            )
        assert len(responses.calls) == 3

    def test_the_default_is_the_model_checked_by_a_real_call(self, settings):
        settings.JUDGE_MODEL = ""
        assert judge.judge_model() == "gemini-3.5-flash"


class TestTheRunnerHook:
    @responses.activate
    def test_a_judge_at_its_limit_stops_judging_and_not_generating(self, tmp_path):
        responses.add(responses.POST, GEMINI, status=429, json={})
        hook = runner.JudgeHook(judge.Judge(cache=judge.JudgeCache(tmp_path / "c.jsonl")))
        hook(RECORD, CVE_ITEM)
        assert not hook.enabled
        assert "analyze_experiment --judge" in hook.stopped
        asked = len(responses.calls)  # the first call and its two retries
        hook(RECORD, CVE_ITEM)  # disabled: asks nothing more
        assert asked == 3
        assert len(responses.calls) == asked
