"""S3 end to end, through the commands WP-8 and WP-9 type (§10 Phase 13 commit 8).

The pilot (§10 Phase 13's acceptance: "20 items x A/B/C end-to-end with pacing")
is a live run with real keys; this is the same sequence with the network
replaced at its edge — OSV, the registries, GitHub, Groq and Gemini — so every
file contract between the six commands is exercised:

    extract_ground_truth -> run_experiment A, B, C, D -> analyze_experiment
                         -> judge_validation_packet -> judge_validation_kappa

`responses` is active throughout with only the expected hosts registered, so a
call to anything else fails the test, and the whole sequence ends with zero
operational rows.
"""

from __future__ import annotations

import csv
import json
import math
from io import StringIO

import pytest
import responses
from django.core.management import call_command

from apps.common import http
from apps.reports.llm import groq_client
from apps.reports.llm.groq_client import LlmCall
from apps.reports.models import Report
from apps.reports.rag import chroma_store, fetch_docs
from apps.research.corpus import read_jsonl
from apps.research.experiment import driver, judge, judge_validation, runner
from apps.research.models import AgentExecutionTrace
from apps.scanning.models import DependencyOccurrence, ScanRun
from tests.test_agent_graph import CHANGELOG
from tests.test_experiment_groundtruth import build_rows, mock_osv, mock_registries

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"


def fake_generator(system_prompt: str, user_prompt: str) -> LlmCall:
    """Answers from TARGET alone: upgrade to the first fixed version, or name
    nothing — the shape of a real answer, deliberately not always right."""
    target = json.loads(
        user_prompt.split("BEGIN TARGET\n", 1)[1].split("\nEND TARGET", 1)[0]
    )
    fixed = next(
        (a["fixed_version"] for a in target["advisories"] if a.get("fixed_version")), None
    )
    fix = {
        "package": target["package"],
        "manifest_path": target["manifest_path"],
        "ecosystem": target["ecosystem"],
        "fix_type": "upgrade" if fixed else "investigate",
        "target_version": fixed,
        "replacement_package": None,
        "priority": 1,
    }
    content = json.dumps({"summary_md": "Upgrade.", "fixes": [fix], "citations": []})
    return LlmCall(content, "openai/gpt-oss-120b", 1, 1, 1, 1)


def mock_gemini() -> None:
    def answer(request):
        prompt = json.loads(request.body)["contents"][0]["parts"][0]["text"]
        if "QUESTION:" in prompt:
            ids = [
                line[1:-1]
                for line in prompt.splitlines()
                if line.startswith("[") and line.endswith("]")
            ]
            payload = {
                "passages": [{"id": i, "relevant": n == 0} for n, i in enumerate(ids)]
            }
        else:
            payload = {
                "claims": [{"claim": "Upgrade", "core": True, "supported": True}],
                "verdict": "faithful",
            }
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
        return (200, {}, json.dumps(body))

    responses.add_callback(responses.POST, GEMINI, callback=answer)


@pytest.fixture
def stubs(tmp_path, settings, monkeypatch):
    settings.CHROMA_DIR = str(tmp_path / "chroma")
    settings.GITHUB_API_PAT = "ghp_research_token"
    settings.GEMINI_API_KEY = "gemini-test-key"
    settings.JUDGE_MODEL = "gemini-3.5-flash"
    settings.GROQ_MODEL = "openai/gpt-oss-120b"
    chroma_store.reset_for_tests()
    monkeypatch.setattr(http, "_local", type(http._local)())
    monkeypatch.setattr(http, "_sleep", lambda _s: None)
    monkeypatch.setattr(runner, "_sleep", lambda _s: None)
    monkeypatch.setattr(judge, "_sleep", lambda _s: None)
    monkeypatch.setattr(groq_client, "complete_json", fake_generator)
    monkeypatch.setattr(
        driver.fetch_docs,
        "fetch_for",
        lambda **kw: fetch_docs.FetchResult(
            docs=(fetch_docs.SourceDoc("changelog", "CHANGELOG.md", "blob1", CHANGELOG),),
            repo_full_name="lodash/lodash",
        ),
    )
    monkeypatch.setattr(
        driver.embeddings,
        "embed",
        lambda texts: [
            [1.0, 0.0] if len(texts) > 1 else [math.cos(0.2), math.sin(0.2)]
            for _ in texts
        ],
    )
    yield
    chroma_store.reset_for_tests()


@pytest.mark.django_db
@responses.activate
def test_the_whole_s3_sequence(tmp_path, stubs):
    build_rows()
    mock_osv()
    mock_registries()
    mock_gemini()
    responses.add(
        responses.GET,
        "https://api.github.com/search/issues",
        json={
            "items": [
                {
                    "number": 1,
                    "title": "Security fix",
                    "body": "Upgrade to 4.17.21.",
                    "updated_at": "x",
                }
            ]
        },
        headers={"x-ratelimit-remaining": "29", "x-ratelimit-reset": "0"},
    )

    gt_dir = tmp_path / "gt"
    runs_dir = tmp_path / "runs"
    call_command(
        "extract_ground_truth", "--out", str(gt_dir), "--size", "4", stdout=StringIO()
    )
    labelled = gt_dir / "labelled_set.jsonl"
    items = read_jsonl(labelled)
    assert {(i["ecosystem"], i["case_type"]) for i in items} == {
        ("npm", "cve_fix"),
        ("npm", "deprecation_replacement"),
        ("pypi", "cve_fix"),
        ("pypi", "deprecation_replacement"),
    }

    run_ids = []
    for condition in "ABCD":
        out = StringIO()
        call_command(
            "run_experiment", "--condition", condition, "--items", str(labelled),
            "--out", str(runs_dir), "--pace", "0", stdout=out,
        )  # fmt: skip
        assert "4 completed, 0 failed" in out.getvalue(), out.getvalue()
        run_ids.append(
            next(p.name for p in runs_dir.iterdir() if p.name.startswith(f"{condition}_"))
        )

    # A re-run of the same command is a no-op continuation.
    again = StringIO()
    call_command(
        "run_experiment", "--condition", "C", "--items", str(labelled),
        "--out", str(runs_dir), "--resume", "--pace", "0", stdout=again,
    )  # fmt: skip
    assert "0 completed, 0 failed, 4 already done" in again.getvalue()

    # D read the issue as well as the changelog, through the research PAT.
    d_records = read_jsonl(runs_dir / run_ids[3] / runner.ITEMS_FILENAME)
    assert all(r["corpus"]["issues"]["count"] == 1 for r in d_records)

    # Judged as they ran: a second pass is entirely cache.
    judged_calls = sum(
        1 for c in responses.calls if "generativelanguage" in c.request.url
    )
    assert judged_calls > 0
    out = StringIO()
    call_command(
        "analyze_experiment", "--runs", *run_ids, "--runs-dir", str(runs_dir),
        "--items", str(labelled), "--out", str(runs_dir / "analysis"),
        "--judge", "--bootstrap", "20", stdout=out,
    )  # fmt: skip
    assert "judge: 0 call(s)" in out.getvalue()
    tables = (runs_dir / "analysis" / "tables.md").read_text(encoding="utf-8")
    assert "| correctness | A -> B | all |" in tables
    # The fake generator copies TARGET's fixed version, which is right for the
    # cve_fix items and names nothing for the replacements.
    with (runs_dir / "analysis" / "correctness.csv").open(encoding="utf-8") as handle:
        rows = {
            (r["condition"], r["ecosystem"], r["case_type"]): r
            for r in csv.DictReader(handle)
        }
    assert rows[("A", "npm", "cve_fix")]["correct"] == "1"
    assert rows[("A", "npm", "deprecation_replacement")]["correct"] == "0"

    # WP-9: packet out, labels back, kappa.
    call_command(
        "judge_validation_packet", "--items", str(labelled), "--runs", *run_ids,
        "--runs-dir", str(runs_dir), "--size", "8", stdout=StringIO(),
    )  # fmt: skip
    wp9 = runs_dir / "judge_validation"
    key = json.loads((wp9 / judge_validation.KEY_FILENAME).read_text())["items"]
    labels = wp9 / "labels.csv"
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item_id", "label", "note"])
        for number, entry in key.items():
            writer.writerow([number, entry["judge_verdict"], ""])
    out = StringIO()
    call_command(
        "judge_validation_kappa", "--labels", str(labels),
        "--key", str(wp9 / judge_validation.KEY_FILENAME), stdout=out,
    )  # fmt: skip
    assert "over 8 items" in out.getvalue()

    # D10: the whole sequence wrote no operational row.
    assert ScanRun.objects.count() == 0
    assert DependencyOccurrence.objects.count() == 0
    assert Report.objects.count() == 0
    assert AgentExecutionTrace.objects.count() == 0
