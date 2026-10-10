"""S3's supplementary analyses (decisions §15.3-15.5).

The interaction and the example rules are tested on rows built by hand, where
the right answer can be worked out on paper; the whole run is tested on an
export-shaped folder by `test_replication`'s notebook test.
"""

from __future__ import annotations

import json

import pytest

from apps.research.experiment import judge, supplement
from apps.research.experiment.metrics import ItemMetrics


def row(item, condition, ecosystem, correct, **overrides) -> ItemMetrics:
    values = {
        "item_id": item,
        "condition": condition,
        "ecosystem": ecosystem,
        "case_type": "cve_fix",
        "answer_given": True,
        "status": "ok",
        "grounding": "sufficient",
        "branch": "fixed",
        "correct": correct,
        "correctness_reason": "escapes_every_advisory" if correct else "still_affected",
        "declared_insufficient": False,
        "faithfulness": judge.FAITHFUL,
        "stated_verdict": judge.FAITHFUL,
        "precision_at_k": 0.2,
        "k": 5,
    }
    values.update(overrides)
    return ItemMetrics(**values)


# ── the interaction ───────────────────────────────────────────────────────


def test_the_interaction_is_the_difference_of_paired_effects():
    """npm: B fixes one of two items (+0.5); PyPI: B breaks one of two (-0.5).
    The difference is exactly +1.0, and its interval contains it."""
    rows = [
        row("n1", "A", "npm", False),
        row("n1", "B", "npm", True),
        row("n2", "A", "npm", True),
        row("n2", "B", "npm", True),
        row("p1", "A", "pypi", True),
        row("p1", "B", "pypi", False),
        row("p2", "A", "pypi", True),
        row("p2", "B", "pypi", True),
    ]

    (found,) = [
        i
        for i in supplement.interactions(rows, iterations=200, seed=42)
        if (i.stratum, i.first, i.second) == ("cve_fix", "A", "B")
    ]

    assert (found.npm_effect, found.pypi_effect, found.difference) == (0.5, -0.5, 1.0)
    assert found.npm_n == found.pypi_n == 2
    assert found.low <= 1.0 <= found.high


def test_an_item_missing_a_condition_or_unscored_is_not_paired():
    rows = [
        row("n1", "A", "npm", True),
        row("n1", "B", "npm", None),
        row("n2", "A", "npm", True),
        row("n2", "B", "npm", False),
        row("n3", "A", "npm", True),
        row("p1", "A", "pypi", True),
        row("p1", "B", "pypi", True),
    ]

    (found,) = [
        i
        for i in supplement.interactions(rows, iterations=50, seed=1)
        if (i.stratum, i.first, i.second) == ("all", "A", "B")
    ]

    assert found.npm_n == 1 and found.npm_effect == -1.0


def test_the_cve_fix_stratum_leaves_replacements_out():
    rows = [
        row("n1", "A", "npm", False, case_type="deprecation_replacement"),
        row("n1", "B", "npm", True, case_type="deprecation_replacement"),
        row("n2", "A", "npm", True),
        row("n2", "B", "npm", True),
        row("p1", "A", "pypi", True),
        row("p1", "B", "pypi", True),
    ]
    found = {
        (i.stratum, i.first, i.second): i
        for i in supplement.interactions(rows, iterations=50, seed=1)
    }

    assert found[("cve_fix", "A", "B")].npm_effect == 0.0
    assert found[("all", "A", "B")].npm_effect == 0.5


# ── the qualitative slice ─────────────────────────────────────────────────


def record(item, condition, *, citations=(), shown=(), kinds=None, summary="Plan."):
    retrieved = [
        {
            "chunk_id": chunk,
            "text": "t",
            "source_path": "README.md",
            "source_kind": (kinds or {}).get(chunk, "readme"),
            "similarity": 0.4,
        }
        for chunk in shown
    ]
    return {
        "item_id": item,
        "condition": condition,
        "status": "ok",
        "retrieved": retrieved,
        "shown_chunk_ids": list(shown),
        "generation": {
            "summary_md": summary,
            "citations": list(citations),
            "fixes": [{"fix_type": "upgrade", "target_version": "2.0.0"}],
        },
    }


ITEMS = {
    name: {
        "item_id": name,
        "target": {
            "package": f"pkg-{name}",
            "current_version": "1.0.0",
            "latest_version": "2.0.0",
            "deprecated": False,
            "advisories": [
                {"cve_id": "CVE-1", "osv_id": "GHSA-1", "fixed_version": "2.0.0"},
                {"cve_id": "CVE-1", "osv_id": "PYSEC-1", "fixed_version": "2.0.0"},
            ],
        },
        "ground_truth": {"target_version": "2.0.0"},
    }
    for name in ("i1", "i2", "i3", "i4")
}


def test_each_kind_takes_the_first_item_that_meets_its_rule():
    rows = [
        row("i1", "B", "npm", True),
        row("i2", "B", "npm", True),
        row("i3", "C", "npm", False, answer_given=False),
        row("i3", "A", "npm", True, answer_given=False),
        row("i4", "C", "npm", True, grounding="low", declared_insufficient=True),
    ]
    records = {
        ("i1", "B"): record("i1", "B", citations=["c1"], shown=["c1"]),
        ("i2", "B"): record("i2", "B", citations=["c1"], shown=["c1"]),
        ("i3", "C"): record("i3", "C", shown=["c1"]),
        ("i3", "A"): record("i3", "A"),
        ("i4", "C"): record("i4", "C"),
    }
    key = {
        "ITEM-001": {"item_id": "i2", "condition": "B"},
        "ITEM-002": {"item_id": "i1", "condition": "B"},
    }
    labels = {
        "ITEM-001": (judge.FAITHFUL, ""),
        "ITEM-002": (
            judge.MAJOR,
            "'fixes all known vulnerabilities' is contradicted by the measured data",
        ),
    }

    found = {
        e.kind.name: e for e in supplement.examples(rows, records, ITEMS, labels, key)
    }

    # i1 is cited and correct, but its human label is major: not "grounded and correct".
    assert found["grounded and correct"].row.item_id == "i2"
    assert found["unsupported core claim"].row.item_id == "i1"
    assert found["overclaim on coverage"].packet_id == "ITEM-002"
    assert found["retrieval made it worse"].row.item_id == "i3"
    assert found["honest abstention"].row.item_id == "i4"
    assert "grounded but wrong" not in found  # nothing meets it here


def test_the_examples_render_each_advisory_once_and_say_a_retrieves_nothing():
    rows = [row("i3", "A", "npm", True, answer_given=False)]
    example = supplement.Example(
        supplement.KINDS[0], rows[0], record("i3", "A"), ITEMS["i3"], None, None
    )

    text = supplement.render_examples([example])

    assert "CVE-1 (2.0.0)" in text and text.count("CVE-1 (") == 1
    assert "grounding n/a (condition A retrieves nothing)" in text
    assert "upgrade to 2.0.0 or later" in text


def test_a_replacement_truth_is_named():
    assert (
        supplement._truth({"ground_truth": {"successor": "@clerk/react"}})
        == "replace with `@clerk/react`"
    )


# ── inputs ────────────────────────────────────────────────────────────────


def test_the_digests_name_every_run_and_refuse_a_gap(tmp_path):
    files = [
        {"path": name, "sha256": "a" * 64}
        for name in (
            *supplement.INPUT_FILES_FIXED,
            "runs/A_x/items.jsonl",
            "runs/B_x/items.jsonl",
        )
    ]
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"files": files}), encoding="utf-8"
    )

    digests = supplement.input_digests(tmp_path)

    assert "runs/B_x/items.jsonl" in digests and len(digests) == 6
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"files": files[1:]}), encoding="utf-8"
    )
    with pytest.raises(supplement.SupplementError, match="judge_validation_packet"):
        supplement.input_digests(tmp_path)
