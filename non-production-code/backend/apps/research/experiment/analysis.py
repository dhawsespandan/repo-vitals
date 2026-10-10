"""`analyze_experiment`: S3's tables, from the runs alone.

§10 Phase 13: "tables (correctness / faithfulness / precision@k) x condition x
ecosystem x case-type; paired tests (McNemar for binary correctness, Wilcoxon
signed-rank for ordinal faithfulness) -> md/csv. Null results render as
first-class outputs — the harness has no thumb on the scale."

**Only File C's prespecified analyses** (§3.4), in its order: completion, then
correctness, faithfulness with its own `major_unsupported` table, precision@k,
the paired tests with Holm's correction within each metric's family, the
ecosystem contrast inside the `cve_fix` stratum (the controlled head-to-head)
before the full-set one, and the insufficient-information calibration.
Anything else is exploratory and does not belong in this file.

**Pairs are items both conditions answered.** A generation that failed has no
correctness; it is excluded from that pair's test and counted beside it, so a
condition that fails often cannot look better by failing on its hard items.

**Every interval resamples items** (File C §3.4.2 and §3.4.4: cluster = item),
seeded and printed. Every p-value is reported whatever it is, and each test's
sentence reads the same whichever way the result falls.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from apps.research.validation import stats

from . import judge, metrics, runner

#: The condition pairs File C asks about: RQ1 (A-B), RQ2 (B-C), A-C beside
#: them, RQ4 (C-D) when D was run.
PAIRS: tuple[tuple[str, str], ...] = (("A", "B"), ("B", "C"), ("A", "C"), ("C", "D"))
#: Ordinal faithfulness, higher is better: a positive paired difference means
#: the second condition was more faithful.
FAITHFULNESS_SCORE = {judge.FAITHFUL: 2, judge.MINOR: 1, judge.MAJOR: 0}
GROUPS = ("all", "npm", "pypi")


class AnalysisError(Exception):
    pass


@dataclass
class Dataset:
    runs: dict[str, dict]  # condition -> run manifest
    rows: list[metrics.ItemMetrics] = field(default_factory=list)
    unjudged: int = 0

    def by_condition(self) -> dict[str, dict[str, metrics.ItemMetrics]]:
        found: dict[str, dict[str, metrics.ItemMetrics]] = defaultdict(dict)
        for row in self.rows:
            found[row.condition][row.item_id] = row
        return found


def _judgments(cache: judge.JudgeCache, record: dict, item: dict) -> dict:
    shown_ids = set(record.get("shown_chunk_ids") or [])
    shown = [
        c for c in record.get("retrieved") or [] if str(c.get("chunk_id")) in shown_ids
    ]
    faith = cache.get(
        judge.cache_key(
            judge.FAITHFULNESS,
            record["item_id"],
            record["condition"],
            {
                "target": item["target"],
                "generation": record.get("generation") or {},
                "shown": shown,
            },
        )
    )
    relevance = None
    if record.get("retrieved"):
        relevance = cache.get(
            judge.cache_key(
                judge.RELEVANCE,
                record["item_id"],
                record["condition"],
                {
                    "question": judge.relevance_question(item),
                    "chunks": record["retrieved"],
                },
            )
        )
    return {judge.FAITHFULNESS: faith, judge.RELEVANCE: relevance}


def load(
    run_dirs: list[Path],
    items: dict[str, dict],
    cache: judge.JudgeCache,
    *,
    judge_missing: judge.Judge | None = None,
    progress=None,
) -> Dataset:
    """Every run's latest records, measured; optionally judging what is not yet judged."""
    manifests = {}
    digests = set()
    for directory in run_dirs:
        manifest = json.loads(
            (directory / runner.RUN_FILENAME).read_text(encoding="utf-8")
        )
        if manifest["condition"] in manifests:
            raise AnalysisError(
                f"Two runs of condition {manifest['condition']}: "
                f"{manifests[manifest['condition']]['run_id']} and {manifest['run_id']}. "
                f"A paired analysis takes one run per condition."
            )
        manifests[manifest["condition"]] = manifest
        digests.add(manifest["items_sha256"])
    if len(digests) > 1:
        raise AnalysisError(
            "The runs are over different labelled sets, so their items are not "
            "paired. Analyse runs over one frozen labelled set (File B WP-8 step 1)."
        )

    dataset = Dataset(runs=manifests)
    judging = judge_missing is not None
    for directory in run_dirs:
        for record in runner.latest_records(directory / runner.ITEMS_FILENAME).values():
            item = items.get(record["item_id"])
            if item is None:
                raise AnalysisError(
                    f"{record['item_id']} is in {directory.name} but not in the labelled set given."
                )
            judgments = _judgments(cache, record, item)
            if (
                judging
                and record.get("status") == "ok"
                and judgments[judge.FAITHFULNESS] is None
            ):
                try:
                    judgments = judge_missing.judge(record, item)
                except (judge.JudgeUnavailable, judge.JudgeRefused) as exc:
                    judging = False
                    if progress is not None:
                        progress(
                            f"Judging stopped ({exc}); the rest stay unjudged for now."
                        )
                except judge.JudgeUnusable:
                    pass
            row = metrics.measure(record, item, judgments)
            if row.status == "ok" and row.faithfulness is None:
                dataset.unjudged += 1
            dataset.rows.append(row)
    return dataset


# ── tables ─────────────────────────────────────────────────────────────────


def _in_group(row: metrics.ItemMetrics, group: str) -> bool:
    return group == "all" or row.ecosystem == group


def _rate_interval(values: list[bool], bootstrap: int, seed: int):
    if len(values) < 2:
        return None
    return stats.bootstrap_interval(
        len(values),
        lambda idx: sum(values[i] for i in idx) / len(idx),
        iterations=bootstrap,
        seed=seed,
    )


def _f(value, places: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{places}f}"


def _ci(interval) -> str:
    return "" if interval is None else f"[{interval[0]:.3f}, {interval[1]:.3f}]"


@dataclass
class PairedTest:
    metric: str
    first: str
    second: str
    group: str
    n: int
    excluded: int
    statistic: dict
    p: float
    p_holm: float = 1.0


#: The metric label of the restricted family (decisions §13.13).
NOT_GIVEN = "correctness, answer not given"


def correctness_tests(
    dataset: Dataset, bootstrap: int, seed: int, *, answer_not_given: bool = False
) -> list[PairedTest]:
    """McNemar per pair and group; with `answer_not_given`, only the items whose
    answer TARGET does not already show, as a family of its own."""
    conditions = dataset.by_condition()
    tests: list[PairedTest] = []
    for first, second in PAIRS:
        if first not in conditions or second not in conditions:
            continue
        for group in GROUPS:
            shared = [
                item_id
                for item_id, row in conditions[first].items()
                if item_id in conditions[second]
                and _in_group(row, group)
                and not (answer_not_given and row.answer_given)
            ]
            pairs = [
                (conditions[first][i].correct, conditions[second][i].correct)
                for i in shared
                if conditions[first][i].correct is not None
                and conditions[second][i].correct is not None
            ]
            if not pairs:
                continue
            b = sum(1 for x, y in pairs if x and not y)
            c = sum(1 for x, y in pairs if y and not x)
            difference = sum(y for _, y in pairs) / len(pairs) - sum(
                x for x, _ in pairs
            ) / len(pairs)
            interval = stats.bootstrap_interval(
                len(pairs),
                lambda idx, pairs=pairs: (
                    sum(pairs[i][1] - pairs[i][0] for i in idx) / len(idx)
                ),
                iterations=bootstrap,
                seed=seed,
            )
            tests.append(
                PairedTest(
                    metric=NOT_GIVEN if answer_not_given else "correctness",
                    first=first,
                    second=second,
                    group=group,
                    n=len(pairs),
                    excluded=len(shared) - len(pairs),
                    statistic={
                        "first_only_correct": b,
                        "second_only_correct": c,
                        "odds_ratio": (c / b) if b else None,
                        "rate_difference": difference,
                        "interval": interval,
                    },
                    p=stats.mcnemar_exact(b, c),
                )
            )
    _holm(tests)
    return tests


def faithfulness_tests(dataset: Dataset) -> list[PairedTest]:
    conditions = dataset.by_condition()
    tests: list[PairedTest] = []
    for first, second in PAIRS:
        if first not in conditions or second not in conditions:
            continue
        for group in GROUPS:
            shared = [
                item_id
                for item_id, row in conditions[first].items()
                if item_id in conditions[second] and _in_group(row, group)
            ]
            differences = [
                FAITHFULNESS_SCORE[conditions[second][i].faithfulness]
                - FAITHFULNESS_SCORE[conditions[first][i].faithfulness]
                for i in shared
                if conditions[first][i].faithfulness in FAITHFULNESS_SCORE
                and conditions[second][i].faithfulness in FAITHFULNESS_SCORE
            ]
            if not differences:
                continue
            result = stats.wilcoxon_signed_rank(differences)
            tests.append(
                PairedTest(
                    metric="faithfulness",
                    first=first,
                    second=second,
                    group=group,
                    n=len(differences),
                    excluded=len(shared) - len(differences),
                    statistic=result,
                    p=result["p"],
                )
            )
    _holm(tests)
    return tests


def _holm(tests: list[PairedTest]) -> None:
    """Within one metric's family, over every pair and group in it (File C §3.4.5)."""
    adjusted = stats.holm([test.p for test in tests])
    for test, value in zip(tests, adjusted, strict=True):
        test.p_holm = value


def ecosystem_contrast(
    dataset: Dataset, bootstrap: int, seed: int, case_type: str | None
):
    """npm minus PyPI correctness per condition; unpaired, items resampled per ecosystem."""
    rows = []
    for condition, by_item in sorted(dataset.by_condition().items()):
        values = {
            ecosystem: [
                row.correct
                for row in by_item.values()
                if row.ecosystem == ecosystem
                and row.correct is not None
                and (case_type is None or row.case_type == case_type)
            ]
            for ecosystem in ("npm", "pypi")
        }
        if not values["npm"] or not values["pypi"]:
            continue
        npm, pypi = values["npm"], values["pypi"]
        difference = sum(npm) / len(npm) - sum(pypi) / len(pypi)
        both = [(0, v) for v in npm] + [(1, v) for v in pypi]

        def statistic(indices, both=both):
            a = [both[i][1] for i in indices if both[i][0] == 0]
            b = [both[i][1] for i in indices if both[i][0] == 1]
            if not a or not b:
                return None
            return sum(a) / len(a) - sum(b) / len(b)

        rows.append(
            {
                "condition": condition,
                "npm_n": len(npm),
                "npm_rate": sum(npm) / len(npm),
                "pypi_n": len(pypi),
                "pypi_rate": sum(pypi) / len(pypi),
                "difference": difference,
                "interval": stats.bootstrap_interval(
                    len(both), statistic, iterations=bootstrap, seed=seed
                ),
            }
        )
    return rows


def render(
    dataset: Dataset, *, bootstrap: int, seed: int
) -> tuple[str, dict[str, list[list]]]:
    """The markdown, and every table as CSV rows keyed by file name."""
    csvs: dict[str, list[list]] = {}
    conditions = dataset.by_condition()
    lines = [
        "# S3 experiment analysis",
        "",
        "Generated by `manage.py analyze_experiment` (§10 Phase 13). File C §3.4's "
        "prespecified analyses only; anything else is exploratory. Intervals: 95% "
        f"bootstrap over items, {bootstrap} resamples, seed {seed}.",
        "",
        "## Runs",
        "",
        "| Condition | Run | Generator | Items | Completed | Failed | Judged |",
        "|---|---|---|---|---|---|---|",
    ]
    for condition, manifest in sorted(dataset.runs.items()):
        rows = list(conditions.get(condition, {}).values())
        judged = sum(1 for row in rows if row.faithfulness is not None)
        lines.append(
            f"| {condition} | `{manifest['run_id']}` | {manifest['generator_model']} | "
            f"{manifest['items']} | {sum(r.status == 'ok' for r in rows)} | "
            f"{sum(r.status == 'failed' for r in rows)} | {judged} |"
        )
    if dataset.unjudged:
        lines += [
            "",
            f"**{dataset.unjudged} successful generation(s) are not judged yet**; the "
            "faithfulness and precision tables cover only judged ones. Run with "
            "`--judge` to fill them.",
        ]

    # ── correctness ──
    lines += [
        "",
        "## Correctness (deterministic)",
        "",
        "| Condition | Ecosystem | Case type | n | Correct | Rate | 95% interval |",
        "|---|---|---|---|---|---|---|",
    ]
    csvs["correctness.csv"] = [
        [
            "condition",
            "ecosystem",
            "case_type",
            "n",
            "correct",
            "rate",
            "ci_low",
            "ci_high",
        ]
    ]
    for condition in sorted(conditions):
        for ecosystem in ("npm", "pypi"):
            for case_type in ("cve_fix", "deprecation_replacement", "all"):
                values = [
                    row.correct
                    for row in conditions[condition].values()
                    if row.ecosystem == ecosystem
                    and row.correct is not None
                    and (case_type == "all" or row.case_type == case_type)
                ]
                if not values:
                    continue
                interval = _rate_interval(values, bootstrap, seed)
                rate = sum(values) / len(values)
                lines.append(
                    f"| {condition} | {ecosystem} | {case_type} | {len(values)} | "
                    f"{sum(values)} | {rate:.3f} | {_ci(interval)} |"
                )
                csvs["correctness.csv"].append(
                    [condition, ecosystem, case_type, len(values), sum(values), f"{rate:.6f}",
                     *(interval or ("", ""))]
                )  # fmt: skip

    # ── correctness where the answer is not given ──
    lines += [
        "",
        "## Correctness where TARGET does not already show the answer",
        "",
        "Every condition is shown each advisory's fixed version and the deprecation "
        "sentence (decisions §13.2). This table keeps only the items where no value "
        "shown would be correct if copied — a `cve_fix` item whose shown fixes are "
        "each still affected by another advisory. It is the comparison where "
        "retrieval has something to add (decisions §13.13); its paired tests are a "
        "Holm family of their own below.",
        "",
    ]
    items_seen: dict[str, metrics.ItemMetrics] = {}
    for by_item in conditions.values():
        items_seen.update(by_item)
    given = sum(row.answer_given for row in items_seen.values())
    lines.append(
        f"Items: {len(items_seen)}; answer given {given}, not given "
        f"{len(items_seen) - given}."
    )
    csvs["correctness_not_given.csv"] = [
        ["condition", "ecosystem", "n", "correct", "rate", "ci_low", "ci_high"]
    ]
    restricted = [
        (condition, ecosystem, values)
        for condition in sorted(conditions)
        for ecosystem in ("npm", "pypi", "all")
        if (
            values := [
                row.correct
                for row in conditions[condition].values()
                if not row.answer_given
                and row.correct is not None
                and (ecosystem == "all" or row.ecosystem == ecosystem)
            ]
        )
    ]
    if not restricted:
        lines += [
            "",
            "No answered item falls outside TARGET's answer, so this comparison is "
            "empty for this set.",
        ]
    else:
        lines += [
            "",
            "| Condition | Ecosystem | n | Correct | Rate | 95% interval |",
            "|---|---|---|---|---|---|",
        ]
        for condition, ecosystem, values in restricted:
            interval = _rate_interval(values, bootstrap, seed)
            rate = sum(values) / len(values)
            lines.append(
                f"| {condition} | {ecosystem} | {len(values)} | {sum(values)} | "
                f"{rate:.3f} | {_ci(interval)} |"
            )
            csvs["correctness_not_given.csv"].append(
                [condition, ecosystem, len(values), sum(values), f"{rate:.6f}",
                 *(interval or ("", ""))]
            )  # fmt: skip

    # ── faithfulness ──
    lines += [
        "",
        "## Faithfulness (judged)",
        "",
        "| Condition | Ecosystem | n | faithful | minor | major | major rate |",
        "|---|---|---|---|---|---|---|",
    ]
    csvs["faithfulness.csv"] = [
        ["condition", "ecosystem", "n", "faithful", "minor", "major", "major_rate"]
    ]
    for condition in sorted(conditions):
        for ecosystem in ("npm", "pypi"):
            verdicts = [
                row.faithfulness
                for row in conditions[condition].values()
                if row.ecosystem == ecosystem and row.faithfulness is not None
            ]
            if not verdicts:
                continue
            counts = [verdicts.count(v) for v in judge.VERDICTS]
            lines.append(
                f"| {condition} | {ecosystem} | {len(verdicts)} | {counts[0]} | {counts[1]} | "
                f"{counts[2]} | {counts[2] / len(verdicts):.3f} |"
            )
            csvs["faithfulness.csv"].append(
                [
                    condition,
                    ecosystem,
                    len(verdicts),
                    *counts,
                    f"{counts[2] / len(verdicts):.6f}",
                ]
            )
    lines += [
        "",
        "`major_unsupported` — a hallucinated core claim — is the practically fatal "
        "category and has its own column (File C §3.4.3).",
    ]

    # ── precision@k ──
    lines += [
        "",
        "## Retrieval precision@k (judged; B, C, D)",
        "",
        "| Condition | Ecosystem | n | Mean precision@k | 95% interval |",
        "|---|---|---|---|---|",
    ]
    csvs["precision.csv"] = [["condition", "ecosystem", "n", "mean", "ci_low", "ci_high"]]
    for condition in sorted(conditions):
        for ecosystem in ("npm", "pypi"):
            values = [
                row.precision_at_k
                for row in conditions[condition].values()
                if row.ecosystem == ecosystem and row.precision_at_k is not None
            ]
            if not values:
                continue
            interval = (
                stats.bootstrap_interval(
                    len(values),
                    lambda idx, values=values: sum(values[i] for i in idx) / len(idx),
                    iterations=bootstrap,
                    seed=seed,
                )
                if len(values) > 1
                else None
            )
            mean = sum(values) / len(values)
            lines.append(
                f"| {condition} | {ecosystem} | {len(values)} | {mean:.3f} | {_ci(interval)} |"
            )
            csvs["precision.csv"].append(
                [
                    condition,
                    ecosystem,
                    len(values),
                    f"{mean:.6f}",
                    *(interval or ("", "")),
                ]
            )

    # ── paired tests ──
    lines += [
        "",
        "## Paired tests",
        "",
        "Correctness: exact McNemar on discordant pairs; the odds ratio is "
        "(second only correct) / (first only correct). Faithfulness: Wilcoxon "
        "signed-rank on faithful=2 / minor=1 / major=0, effect = matched rank-biserial "
        "r, positive when the second condition is more faithful. Holm's correction runs "
        "within each metric's family (File C §3.4.5).",
        "",
        "| Metric | Pair | Group | n (excluded) | Effect | p | p (Holm) |",
        "|---|---|---|---|---|---|---|",
    ]
    csvs["paired_tests.csv"] = [
        ["metric", "first", "second", "group", "n", "excluded", "effect", "p", "p_holm"]
    ]
    correctness_family = correctness_tests(dataset, bootstrap, seed)
    not_given_family = correctness_tests(dataset, bootstrap, seed, answer_not_given=True)
    faithfulness_family = faithfulness_tests(dataset)
    for test in [*correctness_family, *not_given_family, *faithfulness_family]:
        if test.metric in ("correctness", NOT_GIVEN):
            s = test.statistic
            effect = (
                f"{s['second_only_correct']} vs {s['first_only_correct']} discordant; "
                f"OR {_f(s['odds_ratio'], 2)}; rate diff {s['rate_difference']:+.3f} "
                f"{_ci(s['interval'])}"
            )
        else:
            s = test.statistic
            effect = f"r = {_f(s['r'], 3)} ({s['method']}, {s['n']} nonzero)"
        lines.append(
            f"| {test.metric} | {test.first} -> {test.second} | {test.group} | "
            f"{test.n} ({test.excluded}) | {effect} | {test.p:.4f} | {test.p_holm:.4f} |"
        )
        csvs["paired_tests.csv"].append(
            [test.metric, test.first, test.second, test.group, test.n, test.excluded, effect,
             f"{test.p:.6f}", f"{test.p_holm:.6f}"]
        )  # fmt: skip

    # ── RQ3 ──
    lines += [
        "",
        "## RQ3: npm vs PyPI",
        "",
        "Within the `cve_fix` stratum first — the controlled ecosystem head-to-head "
        "(File C §3.4.6, L7) — then over the full set, where the two ecosystems "
        "contribute different case mixes and the comparison carries that confound.",
        "",
        "| Stratum | Condition | npm n | npm rate | PyPI n | PyPI rate | npm - PyPI | 95% interval |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, case_type in (
        ("cve_fix", "cve_fix"),
        ("full set (case-mix confounded)", None),
    ):
        for row in ecosystem_contrast(dataset, bootstrap, seed, case_type):
            lines.append(
                f"| {label} | {row['condition']} | {row['npm_n']} | {row['npm_rate']:.3f} | "
                f"{row['pypi_n']} | {row['pypi_rate']:.3f} | {row['difference']:+.3f} | "
                f"{_ci(row['interval'])} |"
            )

    # ── calibration ──
    lines += [
        "",
        "## Insufficient-information calibration (File C §3.4.7)",
        "",
        "How often each gated condition said it could not recommend, against its own "
        "grounding flag.",
        "",
        "| Condition | Ecosystem | Grounding | n | Declared insufficient | Rate |",
        "|---|---|---|---|---|---|",
    ]
    csvs["calibration.csv"] = [
        ["condition", "ecosystem", "grounding", "n", "declared", "rate"]
    ]
    for condition in sorted(conditions):
        for ecosystem in ("npm", "pypi"):
            for grounding in ("sufficient", "low"):
                rows = [
                    row
                    for row in conditions[condition].values()
                    if row.ecosystem == ecosystem
                    and row.grounding == grounding
                    and row.declared_insufficient is not None
                ]
                if not rows:
                    continue
                declared = sum(row.declared_insufficient for row in rows)
                lines.append(
                    f"| {condition} | {ecosystem} | {grounding} | {len(rows)} | {declared} | "
                    f"{declared / len(rows):.3f} |"
                )
                csvs["calibration.csv"].append(
                    [
                        condition,
                        ecosystem,
                        grounding,
                        len(rows),
                        declared,
                        f"{declared / len(rows):.6f}",
                    ]
                )

    lines += [
        "",
        "## Reading these tables",
        "",
        "- Every result is reported at face value with its interval; a null is a "
        "finding (File C §3.4.8).",
        "- Correctness counts the structured fix only, and only against the advisories "
        "on the resolved version (decisions §13).",
        "- TARGET shows every condition the fixed version and the deprecation sentence "
        "the answers were extracted from, so correctness partly measures use of given "
        "facts (decisions §13.2); the answer-not-given table is the comparison that "
        "does not (§13.13).",
        "- Faithfulness is an LLM's verdict; read it with WP-9's kappa (File C L5).",
        "",
    ]

    csvs["metrics.csv"] = [list(metrics.ItemMetrics.__dataclass_fields__)] + [
        list(row.as_json().values()) for row in dataset.rows
    ]
    return "\n".join(lines), csvs


def write(dataset: Dataset, out: Path, *, bootstrap: int, seed: int) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    text, tables = render(dataset, bootstrap=bootstrap, seed=seed)
    written = [out / "tables.md"]
    written[0].write_text(text, encoding="utf-8")
    for name, rows in tables.items():
        path = out / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(rows)
        written.append(path)
    return written
