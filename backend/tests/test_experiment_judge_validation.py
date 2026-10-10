"""WP-9's packet and kappa (§10 Phase 13 commit 6).

The packet's job is to be blind, so most of these assert what it must *not*
contain: the judge's verdict or note, the condition, the run, the grounding flag.
"""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.research.corpus import append_jsonl
from apps.research.experiment import judge, judge_validation, runner
from apps.research.validation import stats
from tests.test_experiment_driver import ITEM


def make_item(index: int, ecosystem: str) -> dict:
    item = json.loads(json.dumps(ITEM))
    item["item_id"] = f"S3-{ecosystem}{index:04d}"
    item["ecosystem"] = ecosystem
    return item


def make_record(item: dict, condition: str, status: str = "ok") -> dict:
    return {
        "item_id": item["item_id"],
        "condition": condition,
        "status": status,
        "grounding": "sufficient",
        "generation": {
            "summary_md": f"Upgrade {item['item_id']} to 3.1.2.",
            "fixes": [
                {"package": "express", "fix_type": "upgrade", "target_version": "3.1.2"}
            ],
        },
        "retrieved": [
            {"chunk_id": "c1", "text": "3.1.2 fixes it", "source_path": "CHANGELOG.md"}
        ],
        "shown_chunk_ids": ["c1"] if condition != "A" else [],
    }


@pytest.fixture
def judged_runs(tmp_path, settings):
    """Three conditions x two ecosystems, every success judged, one failure."""
    settings.JUDGE_MODEL = "gemini-2.5-flash"
    runs = tmp_path / "runs"
    cache = judge.JudgeCache(runs / judge.CACHE_FILENAME)
    items = [make_item(i, eco) for eco in ("npm", "pypi") for i in range(12)]
    verdicts = [judge.FAITHFUL, judge.MINOR, judge.MAJOR]
    for condition in "ABC":
        directory = runs / f"{condition}_digest00_model"
        for index, item in enumerate(items):
            status = "failed" if (condition, index) == ("C", 0) else "ok"
            record = make_record(item, condition, status)
            append_jsonl(directory / runner.ITEMS_FILENAME, record)
            if status != "ok":
                continue
            shown = [
                c
                for c in record["retrieved"]
                if c["chunk_id"] in record["shown_chunk_ids"]
            ]
            key = judge.cache_key(
                judge.FAITHFULNESS,
                item["item_id"],
                condition,
                {
                    "target": item["target"],
                    "generation": record["generation"],
                    "shown": shown,
                },
            )
            cache.put(
                key,
                {
                    "task": "faithfulness",
                    "item_id": item["item_id"],
                    "condition": condition,
                    "judge_version": judge.judge_version(),
                    "verdict": verdicts[index % 3],
                    "note": f"judge note {item['item_id']}",
                },
            )
    return {
        "runs": runs,
        "dirs": [runs / f"{c}_digest00_model" for c in "ABC"],
        "items": {item["item_id"]: item for item in items},
        "cache": judge.JudgeCache(runs / judge.CACHE_FILENAME),
    }


class TestThePacket:
    def test_fifty_items_blind_with_a_template_and_a_private_key(
        self, judged_runs, tmp_path
    ):
        out = tmp_path / "wp9"
        judge_validation.build_packet(
            judged_runs["dirs"], judged_runs["items"], judged_runs["cache"], out, size=50
        )
        packet = (out / judge_validation.PACKET_FILENAME).read_text(encoding="utf-8")
        template = list(
            csv.reader((out / judge_validation.TEMPLATE_FILENAME).open(encoding="utf-8"))
        )
        key = json.loads((out / judge_validation.KEY_FILENAME).read_text())["items"]

        assert template[0] == ["item_id", "label", "note"]
        assert [row[0] for row in template[1:]] == [f"ITEM-{n:03d}" for n in range(1, 51)]
        assert all(row[1] == "" for row in template[1:])
        assert len(key) == 50
        # Blind: no verdict note, no run, no condition label, no grounding flag.
        assert "judge note" not in packet
        assert "digest00" not in packet
        assert "Condition" not in packet and "condition C" not in packet
        assert "grounding" not in packet.lower()
        assert {entry["judge_verdict"] for entry in key.values()} <= set(judge.VERDICTS)

    def test_the_labeller_sees_every_field_the_judge_sees(self, judged_runs, tmp_path):
        """The judge is given the whole target record as MEASURED DATA, so the
        packet has to show all of it. The first real packet showed four of the
        fifteen fields every item carries, and its kappa measured the packet rather than the judge
        (decisions §13.16)."""
        target = dict(ITEM["target"], an_unforeseen_field="kept")
        text = "\n".join(judge_validation.measured_lines(target))
        assert "**Dependency:** `express` (npm)" in text
        for key in target:
            if key not in ("advisories", "package", "ecosystem"):
                assert judge_validation.MEASURED_LABELS.get(key, key) in text, key
        assert "- Latest release on the registry: 4.0.0" in text
        assert "- Versions behind the latest release: major 1, minor 0, patch 0" in text
        assert "- an_unforeseen_field: kept" in text
        assert "CVE-2026-0001 / GHSA-1: severity high, CVSS 7.5, fixed in 3.1.2" in text

        out = tmp_path / "wp9"
        judge_validation.build_packet(
            judged_runs["dirs"], judged_runs["items"], judged_runs["cache"], out, size=50
        )
        packet = (out / judge_validation.PACKET_FILENAME).read_text(encoding="utf-8")
        assert "- Latest release on the registry: 4.0.0" in packet
        assert "- Manifest: package.json" in packet

    def test_condition_a_is_shown_with_no_passages(self, judged_runs, tmp_path):
        out = tmp_path / "wp9"
        judge_validation.build_packet(
            judged_runs["dirs"], judged_runs["items"], judged_runs["cache"], out, size=69
        )
        packet = (out / judge_validation.PACKET_FILENAME).read_text(encoding="utf-8")
        assert "The author was shown no passages for this item." in packet
        assert "**Passage `c1`**" in packet

    def test_every_cell_is_represented_and_failures_are_not_sampled(self, judged_runs):
        candidates = judge_validation.judged_candidates(
            judged_runs["dirs"], judged_runs["items"], judged_runs["cache"]
        )
        assert len(candidates) == 3 * 24 - 1
        chosen = judge_validation.stratified(candidates, 50, seed=4)
        assert len(chosen) == 50
        cells = {(c.record["condition"], c.item["ecosystem"]) for c in chosen}
        assert cells == {(c, e) for c in "ABC" for e in ("npm", "pypi")}
        assert judge_validation.stratified(candidates, 50, seed=4) == chosen

    def test_nothing_judged_is_a_refusal(self, tmp_path):
        with pytest.raises(judge_validation.ValidationPacketError, match="No judged"):
            judge_validation.build_packet(
                [], {}, judge.JudgeCache(tmp_path / "c.jsonl"), tmp_path / "out"
            )


def write_labels(path, rows, header=("item_id", "label", "note")) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


KEY = {
    f"ITEM-{n:03d}": {
        "judge_verdict": verdict,
        "judge_note": "",
        "condition": "B",
        "ecosystem": "npm",
    }
    for n, verdict in enumerate(
        [judge.FAITHFUL] * 5 + [judge.MINOR] * 3 + [judge.MAJOR] * 2, start=1
    )
}


class TestTheLabels:
    @pytest.mark.parametrize(
        ("rows", "message"),
        [
            ([("ITEM-999", "faithful", "")], "not a packet item id"),
            ([("ITEM-001", "PENDING", "")], "the labels are"),
            ([("ITEM-001", "faithful", ""), ("ITEM-001", "faithful", "")], "twice"),
            ([("ITEM-001", "faithful", "")], "unlabelled"),
        ],
    )
    def test_file_bs_quality_checks(self, tmp_path, rows, message):
        path = tmp_path / "labels.csv"
        write_labels(path, rows)
        with pytest.raises(judge_validation.ValidationPacketError, match=message):
            judge_validation.read_labels(path, KEY)

    def test_the_header_is_file_bs(self, tmp_path):
        path = tmp_path / "labels.csv"
        write_labels(path, [], header=("id", "label"))
        with pytest.raises(judge_validation.ValidationPacketError, match="header"):
            judge_validation.read_labels(path, KEY)

    def test_perfect_agreement(self, tmp_path):
        labels = {number: (entry["judge_verdict"], "x") for number, entry in KEY.items()}
        result = judge_validation.kappa(labels, KEY)
        assert result.kappa == pytest.approx(1.0)
        assert result.disagreements == []
        assert "used as-is" in result.decision

    def test_disagreements_are_listed_with_both_notes(self):
        labels = {number: (entry["judge_verdict"], "") for number, entry in KEY.items()}
        labels["ITEM-001"] = (judge.MAJOR, "invented version")
        result = judge_validation.kappa(labels, KEY)
        assert [row["id"] for row in result.disagreements] == ["ITEM-001"]
        assert result.disagreements[0]["human_note"] == "invented version"
        assert result.missing_notes == [
            n for n in sorted(KEY) if KEY[n]["judge_verdict"] != judge.FAITHFUL
        ]

    @pytest.mark.parametrize(
        ("value", "phrase"),
        [(0.75, "as-is"), (0.6, "softened"), (0.3, "tighten the rubric")],
    )
    def test_file_cs_decision_rule(self, value, phrase):
        result = judge_validation.KappaResult(10, value, None, 0.5, [], [], [])
        assert phrase in result.decision


def test_weighted_kappa_by_hand():
    """3x3, weights |i-j|/2: observed disagreement 0.1, expected 0.444..."""
    matrix = [[4, 1, 0], [0, 3, 0], [0, 0, 2]]
    total = 10
    rows = [5 / total, 3 / total, 2 / total]
    columns = [4 / total, 4 / total, 2 / total]
    observed = 0.5 * 1 / total
    expected = sum(
        abs(i - j) / 2 * rows[i] * columns[j] for i in range(3) for j in range(3)
    )
    assert stats.weighted_kappa(matrix) == pytest.approx(1 - observed / expected)


class TestTheCommands:
    def test_packet_then_kappa(self, judged_runs, tmp_path, settings):
        items_path = tmp_path / "labelled_set.jsonl"
        for item in judged_runs["items"].values():
            append_jsonl(items_path, item)
        out = tmp_path / "wp9"
        stdout = StringIO()
        call_command(
            "judge_validation_packet",
            "--items", str(items_path),
            "--runs", *[d.name for d in judged_runs["dirs"]],
            "--runs-dir", str(judged_runs["runs"]),
            "--out", str(out),
            stdout=stdout,
        )  # fmt: skip
        assert "holds the judge's verdicts" in stdout.getvalue()

        key = json.loads((out / judge_validation.KEY_FILENAME).read_text())["items"]
        write_labels(
            out / "wp9_judge_labels.csv",
            [(number, entry["judge_verdict"], "note") for number, entry in key.items()],
        )
        stdout = StringIO()
        call_command(
            "judge_validation_kappa",
            "--labels", str(out / "wp9_judge_labels.csv"),
            "--key", str(out / judge_validation.KEY_FILENAME),
            stdout=stdout,
        )  # fmt: skip
        assert "kappa = 1.000 over 50 items" in stdout.getvalue()
        assert (out / "judge_validation_kappa.md").exists()

    def test_kappa_refuses_a_bad_csv(self, tmp_path):
        key = tmp_path / "key.json"
        key.write_text(json.dumps({"items": KEY}))
        labels = tmp_path / "labels.csv"
        write_labels(labels, [("ITEM-001", "PENDING", "")])
        with pytest.raises(CommandError, match="the labels are"):
            call_command(
                "judge_validation_kappa", "--labels", str(labels), "--key", str(key),
                stdout=StringIO(),
            )  # fmt: skip


# ── decisions §15.3-15.4: the key rebuilt, a fresh 50, the human labels ────


def candidates_of(judged_runs) -> list[judge_validation.Candidate]:
    return judge_validation.judged_candidates(
        judged_runs["dirs"], judged_runs["items"], judged_runs["cache"]
    )


class TestTheRebuiltKey:
    def test_the_key_comes_back_from_the_runs_and_the_packet(self, judged_runs, tmp_path):
        out = tmp_path / "wp9"
        judge_validation.build_packet(
            judged_runs["dirs"], judged_runs["items"], judged_runs["cache"], out, size=20
        )
        packet = (out / judge_validation.PACKET_FILENAME).read_text(encoding="utf-8")
        original = json.loads((out / judge_validation.KEY_FILENAME).read_text())["items"]

        rebuilt = judge_validation.reconstruct_key(
            candidates_of(judged_runs), packet, size=20, seed=42
        )

        assert rebuilt == original

    def test_another_seed_is_refused_not_repaired(self, judged_runs, tmp_path):
        out = tmp_path / "wp9"
        judge_validation.build_packet(
            judged_runs["dirs"], judged_runs["items"], judged_runs["cache"], out, size=20
        )
        packet = (out / judge_validation.PACKET_FILENAME).read_text(encoding="utf-8")

        with pytest.raises(judge_validation.ValidationPacketError, match="verbatim"):
            judge_validation.reconstruct_key(
                candidates_of(judged_runs), packet, size=20, seed=7
            )

    def test_an_item_the_rebuild_did_not_produce_is_refused(self, judged_runs, tmp_path):
        out = tmp_path / "wp9"
        judge_validation.build_packet(
            judged_runs["dirs"], judged_runs["items"], judged_runs["cache"], out, size=20
        )
        packet = (out / judge_validation.PACKET_FILENAME).read_text(encoding="utf-8")

        with pytest.raises(judge_validation.ValidationPacketError, match="holds 21"):
            judge_validation.reconstruct_key(
                candidates_of(judged_runs),
                packet + "\n## ITEM-021\n\nsmuggled\n",
                size=20,
                seed=42,
            )


class TestAFreshFifty:
    def test_an_earlier_keys_items_are_left_out(self, judged_runs, tmp_path):
        first = tmp_path / "round1"
        judge_validation.build_packet(
            judged_runs["dirs"],
            judged_runs["items"],
            judged_runs["cache"],
            first,
            size=30,
        )
        used = {
            (entry["item_id"], entry["condition"])
            for entry in json.loads((first / judge_validation.KEY_FILENAME).read_text())[
                "items"
            ].values()
        }

        judge_validation.build_packet(
            judged_runs["dirs"],
            judged_runs["items"],
            judged_runs["cache"],
            tmp_path / "round2",
            size=30,
            exclude=frozenset(used),
        )
        second = json.loads(
            (tmp_path / "round2" / judge_validation.KEY_FILENAME).read_text()
        )["items"]

        assert len(second) == 30
        assert not {(e["item_id"], e["condition"]) for e in second.values()} & used

    def test_the_command_takes_the_earlier_key(self, judged_runs, tmp_path):
        items = tmp_path / "items.jsonl"
        for item in judged_runs["items"].values():
            append_jsonl(items, item)
        first = tmp_path / "round1"
        judge_validation.build_packet(
            judged_runs["dirs"],
            judged_runs["items"],
            judged_runs["cache"],
            first,
            size=30,
        )
        call_command(
            "judge_validation_packet",
            "--items", str(items),
            "--runs", *[d.name for d in judged_runs["dirs"]],
            "--runs-dir", str(judged_runs["runs"]),
            "--out", str(tmp_path / "round2"),
            "--size", "30",
            "--exclude-key", str(first / judge_validation.KEY_FILENAME),
            stdout=StringIO(),
        )  # fmt: skip
        used = {
            (e["item_id"], e["condition"])
            for e in json.loads((first / judge_validation.KEY_FILENAME).read_text())[
                "items"
            ].values()
        }
        second = json.loads(
            (tmp_path / "round2" / judge_validation.KEY_FILENAME).read_text()
        )["items"]
        assert not {(e["item_id"], e["condition"]) for e in second.values()} & used

    def test_a_file_that_is_not_a_key_is_refused(self, judged_runs, tmp_path):
        items = tmp_path / "items.jsonl"
        for item in judged_runs["items"].values():
            append_jsonl(items, item)
        bogus = tmp_path / "bogus.json"
        bogus.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(CommandError, match="not a packet key"):
            call_command(
                "judge_validation_packet",
                "--items", str(items),
                "--runs", *[d.name for d in judged_runs["dirs"]],
                "--runs-dir", str(judged_runs["runs"]),
                "--exclude-key", str(bogus),
                stdout=StringIO(),
            )  # fmt: skip


class TestTheHumanLabels:
    KEY = {
        "ITEM-001": {
            "condition": "A",
            "ecosystem": "npm",
            "judge_verdict": judge.FAITHFUL,
        },
        "ITEM-002": {
            "condition": "A",
            "ecosystem": "pypi",
            "judge_verdict": judge.FAITHFUL,
        },
        "ITEM-003": {"condition": "B", "ecosystem": "npm", "judge_verdict": judge.MINOR},
        "ITEM-004": {
            "condition": "B",
            "ecosystem": "npm",
            "judge_verdict": judge.FAITHFUL,
        },
    }
    LABELS = {
        "ITEM-001": (judge.MAJOR, "invented a version"),
        "ITEM-002": (judge.FAITHFUL, ""),
        "ITEM-003": (judge.MINOR, "peripheral"),
        "ITEM-004": (judge.FAITHFUL, ""),
    }

    def test_counts_per_cell_per_condition_and_overall(self):
        rows = {
            (r.condition, r.ecosystem): r
            for r in judge_validation.human_faithfulness(self.LABELS, self.KEY)
        }

        assert set(rows) == {("A", "npm"), ("A", "pypi"), ("A", "all"), ("B", "npm"), ("B", "all"), ("all", "all")}  # fmt: skip
        assert rows[("A", "all")].human == {
            judge.FAITHFUL: 1,
            judge.MINOR: 0,
            judge.MAJOR: 1,
        }
        assert rows[("A", "all")].judge == {
            judge.FAITHFUL: 2,
            judge.MINOR: 0,
            judge.MAJOR: 0,
        }
        assert rows[("all", "all")].n == 4 and rows[("all", "all")].unsupported == 2
        ordered = judge_validation.human_faithfulness(self.LABELS, self.KEY)
        assert (ordered[-1].condition, ordered[-1].ecosystem) == ("all", "all")

    def test_the_table_carries_wilson_intervals(self):
        table = judge_validation.human_faithfulness_table(
            judge_validation.human_faithfulness(self.LABELS, self.KEY)
        )
        assert (
            "| all | all | 4 | 2 / 1 / 1 | 0.50 [0.15, 0.85] | 0.25 [0.05, 0.70] | 3 / 1 / 0 |"
            in table
        )

    @pytest.mark.parametrize(
        ("k", "n", "low", "high"),
        [(0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (5, 10, 0.2366, 0.7634)],
    )
    def test_wilson_matches_the_textbook(self, k, n, low, high):
        found = judge_validation.wilson_interval(k, n)
        assert found == pytest.approx((low, high), abs=1e-4)


class TestTheRubrics:
    def test_v1_is_the_default_so_the_signed_cache_still_matches(self, settings):
        settings.JUDGE_RUBRIC = ""
        settings.JUDGE_MODEL = "gemini-3.5-flash-lite"
        assert judge.rubric_version() == "rubric-v1"
        assert judge.judge_version() == "gemini-3.5-flash-lite|rubric-v1"
        assert judge.faithfulness_system() == judge.FAITHFULNESS_SYSTEM

    def test_v2_changes_the_prompt_and_every_cache_key(self, settings):
        settings.JUDGE_RUBRIC = ""
        before = judge.cache_key(judge.FAITHFULNESS, "S3-x", "A", {"a": 1})
        settings.JUDGE_RUBRIC = "rubric-v2"
        after = judge.cache_key(judge.FAITHFULNESS, "S3-x", "A", {"a": 1})

        assert before != after
        text = judge.faithfulness_system()
        assert text == judge.FAITHFULNESS_SYSTEM_V2
        # §13.17's four changes, each in the text.
        assert "contradicts is unsupported" in text
        assert "needs \nno code changes" in text or "no code changes" in text
        assert "Read MEASURED DATA's deprecation message" in text
        assert "fixes all known vulnerabilities is supported" in text

    def test_an_unknown_rubric_is_refused(self, settings):
        settings.JUDGE_RUBRIC = "rubric-v9"
        with pytest.raises(judge.JudgeRefused, match="rubric-v1, rubric-v2"):
            judge.judge_version()

    def test_the_judge_asks_with_the_rubric_in_force(self, settings, tmp_path):
        settings.JUDGE_RUBRIC = "rubric-v2"
        asked = []

        def complete(system, user):
            asked.append(system)
            return {"claims": [], "verdict": "faithful", "note": ""}

        worker = judge.Judge(
            judge.JudgeCache(tmp_path / "cache.jsonl"), complete=complete, pace_seconds=0
        )
        item = make_item(1, "npm")
        entry = worker.faithfulness(make_record(item, "B"), item)

        assert asked == [judge.FAITHFULNESS_SYSTEM_V2]
        assert entry["judge_version"].endswith("|rubric-v2")
