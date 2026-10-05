"""The checkpointed, paced runner (§10 Phase 13 commit 4).

§10 Phase 13's acceptance: "resumable after a mid-run kill". Damaged the way
the crash would damage it (§11.7's lesson): a run stopped part-way, and a
results file whose last line a kill tore in half.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.reports.llm.groq_client import (
    LlmCall,
    LlmModelUnavailable,
    LlmTruncated,
    LlmUnavailable,
)
from apps.research.corpus import read_jsonl
from apps.research.experiment import runner
from tests.test_experiment_driver import ANSWER, ITEM


def items(count: int) -> list[dict]:
    built = []
    for index in range(count):
        item = json.loads(json.dumps(ITEM))
        item["item_id"] = f"S3-item{index:05d}"
        built.append(item)
    return built


def write_items(tmp_path, count: int = 4):
    path = tmp_path / "labelled_set.jsonl"
    path.write_text(
        "".join(json.dumps(item) + "\n" for item in items(count)), encoding="utf-8"
    )
    return path


class Scripted:
    """A generator whose answer for the n-th call is scripted; default ANSWER."""

    def __init__(self, script: dict | None = None) -> None:
        self.script = script or {}
        self.calls = 0

    def __call__(self, system_prompt: str, user_prompt: str) -> LlmCall:
        self.calls += 1
        step = self.script.get(self.calls, ANSWER)
        if isinstance(step, Exception):
            raise step
        return LlmCall(step, "test-model", 1, 1, 1, 1)


@pytest.fixture(autouse=True)
def setup(monkeypatch, settings):
    monkeypatch.setattr(runner, "_sleep", lambda _seconds: None)
    settings.GROQ_MODEL = "openai/gpt-oss-120b"


def run(tmp_path, items_path, model=None, **kwargs) -> runner.RunOutcome:
    return runner.run_experiment(
        items_path=items_path,
        condition_name=kwargs.pop("condition", "A"),
        out_dir=tmp_path / "runs",
        complete=model or Scripted(),
        **kwargs,
    )


def lines(outcome: runner.RunOutcome) -> list[dict]:
    """Every intact record, read the way a resume reads them (§11.7)."""
    return read_jsonl(outcome.directory / runner.ITEMS_FILENAME)


@pytest.mark.django_db
class TestResuming:
    def test_a_run_writes_one_line_per_item_and_a_manifest(self, tmp_path):
        outcome = run(tmp_path, write_items(tmp_path))
        assert outcome.completed == 4
        assert outcome.run_id.startswith("A_") and outcome.run_id.endswith(
            "_openai-gpt-oss-120b"
        )
        manifest = json.loads((outcome.directory / runner.RUN_FILENAME).read_text())
        assert manifest["generator_model"] == "openai/gpt-oss-120b"
        assert manifest["items"] == 4
        assert manifest["completed"] == 4
        assert [record["status"] for record in lines(outcome)] == ["ok"] * 4

    def test_stopped_part_way_then_resumed_completes_without_duplicates(self, tmp_path):
        path = write_items(tmp_path)
        first = run(tmp_path, path, limit=2)
        second = run(tmp_path, path, resume=True)
        assert (first.completed, second.completed, second.skipped) == (2, 2, 2)
        assert len({record["item_id"] for record in lines(second)}) == 4
        assert len(lines(second)) == 4

    def test_a_line_torn_by_a_kill_is_redone_and_costs_nothing_else(self, tmp_path):
        path = write_items(tmp_path)
        first = run(tmp_path, path, limit=3)
        results = first.directory / runner.ITEMS_FILENAME
        text = results.read_text()
        results.write_text(text[: len(text) - 40])  # the third line, torn

        second = run(tmp_path, path, resume=True)

        assert second.skipped == 2
        assert second.completed == 2
        assert {record["item_id"] for record in lines(second)} == {
            f"S3-item{i:05d}" for i in range(4)
        }

    def test_results_are_never_overwritten_without_resume(self, tmp_path):
        path = write_items(tmp_path)
        run(tmp_path, path)
        with pytest.raises(runner.RunError, match="--resume"):
            run(tmp_path, path)


@pytest.mark.django_db
class TestStopping:
    def test_a_provider_that_stops_answering_ends_the_session_cleanly(self, tmp_path):
        path = write_items(tmp_path)
        model = Scripted({2: LlmUnavailable("x"), 3: LlmUnavailable("x")})
        outcome = run(tmp_path, path, model)
        assert outcome.completed == 1
        assert "daily limit" in outcome.stopped
        # The unanswered items are not in the data: the cap is not a result.
        assert [record["item_id"] for record in lines(outcome)] == ["S3-item00000"]

        resumed = run(tmp_path, path, resume=True)
        assert resumed.completed == 3
        assert resumed.stopped is None

    def test_one_non_answer_is_not_a_stop(self, tmp_path):
        outcome = run(tmp_path, write_items(tmp_path), Scripted({2: LlmUnavailable("x")}))
        assert outcome.stopped is None
        assert outcome.completed == 3  # the unanswered one waits for the resume

    def test_a_configuration_fault_stops_at_once(self, tmp_path):
        outcome = run(
            tmp_path, write_items(tmp_path), Scripted({1: LlmModelUnavailable("gone")})
        )
        assert "GROQ_MODEL" in outcome.stopped
        assert outcome.completed == 0

    def test_an_answer_that_is_not_json_is_a_failed_item_not_a_stop(self, tmp_path):
        """The client reports both as LlmUnavailable; only a non-answer stops."""
        model = Scripted({1: "not json", 2: "still not json"})
        outcome = run(tmp_path, write_items(tmp_path), model)
        assert outcome.stopped is None
        assert lines(outcome)[0]["status"] == "failed"

    def test_a_truncated_answer_is_a_failed_item(self, tmp_path):
        outcome = run(tmp_path, write_items(tmp_path), Scripted({1: LlmTruncated("cap")}))
        assert outcome.failed == 1
        assert outcome.completed == 3


@pytest.mark.django_db
class TestFailuresAndModels:
    def test_retry_failed_reruns_only_the_failures_and_the_new_result_wins(
        self, tmp_path
    ):
        path = write_items(tmp_path)
        run(tmp_path, path, Scripted({1: '{"bad": 1}', 2: '{"bad": 1}'}))
        retried = run(tmp_path, path, resume=True, retry_failed=True)
        assert retried.completed == 1
        assert retried.skipped == 3
        latest = runner.latest_records(retried.directory / runner.ITEMS_FILENAME)
        assert latest["S3-item00000"]["status"] == "ok"

    def test_a_new_model_is_a_new_run_and_the_old_one_is_named(self, tmp_path, settings):
        path = write_items(tmp_path)
        old = run(tmp_path, path, limit=1)
        settings.GROQ_MODEL = "openai/gpt-oss-20b"
        new = run(tmp_path, path, resume=True)
        assert new.run_id != old.run_id
        assert new.other_runs == [old.run_id]
        assert new.completed == 4

    def test_a_labelled_set_with_a_duplicate_is_refused(self, tmp_path):
        path = tmp_path / "set.jsonl"
        line = json.dumps(items(1)[0]) + "\n"
        path.write_text(line + line, encoding="utf-8")
        with pytest.raises(runner.RunError, match="twice"):
            run(tmp_path, path)


@pytest.mark.django_db
def test_the_command_reports_a_clean_stop(tmp_path, monkeypatch, settings):
    settings.GROQ_API_KEY = ""
    path = write_items(tmp_path)
    out = StringIO()
    call_command(
        "run_experiment", "--condition", "A", "--items", str(path),
        "--out", str(tmp_path / "runs"), stdout=out,
    )  # fmt: skip
    assert "Stopped:" in out.getvalue()
    assert "GROQ_API_KEY" in out.getvalue()


@pytest.mark.django_db
def test_the_command_refuses_to_overwrite(tmp_path):
    path = write_items(tmp_path)
    runner.run_experiment(
        items_path=path,
        condition_name="A",
        out_dir=tmp_path / "runs",
        complete=Scripted(),
    )
    with pytest.raises(CommandError, match="--resume"):
        call_command(
            "run_experiment", "--condition", "A", "--items", str(path),
            "--out", str(tmp_path / "runs"), stdout=StringIO(),
        )  # fmt: skip
