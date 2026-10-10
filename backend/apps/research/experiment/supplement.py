"""S3's analyses beyond WP-8's signed tables (File C §3.4, decisions §15.3-15.5).

`analyze_experiment` produced File C §3.4's prespecified tables and WP-8 signed
them. Three things S3 still needs, all computed from the export alone:

1. **Faithfulness from the human labels.** WP-9's kappa is 0.134, so File C
   §3.4.1 bars the judge's faithfulness verdicts from S3's claims. Decisions
   §15.3 takes §13.17's second option: faithfulness is reported from the 50
   human labels, by condition and ecosystem, beside what the judge said on the
   same items. The answer key is rebuilt from the runs and the packet
   (`replication.wp9_key`), which also recomputes the kappa.
2. **The condition x ecosystem interaction** (§3.4.6: "does grounding help PyPI
   *more* ... or *less*?"). WP-8's tables give the ecosystem contrast per
   condition; the interaction is the difference of the two ecosystems' paired
   condition effects, with a bootstrap interval that resamples items within
   each ecosystem. Within `cve_fix` first, the controlled stratum (L7).
3. **The qualitative slice** (§3.4.9): one trace-backed example per kind of
   outcome, each chosen by a fixed rule — the first item, by id, that meets the
   kind's definition — so the selection is not the author's taste.
"""

from __future__ import annotations

import csv
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from apps.research.validation import stats

from . import judge, judge_validation, runner
from .metrics import ItemMetrics

PAIRS: tuple[tuple[str, str], ...] = (("A", "B"), ("B", "C"), ("A", "C"))
STRATA: tuple[str, ...] = ("cve_fix", "all")


class SupplementError(Exception):
    pass


# ── 2. The interaction ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Interaction:
    stratum: str
    first: str
    second: str
    npm_n: int
    pypi_n: int
    npm_effect: float
    pypi_effect: float
    difference: float
    low: float | None
    high: float | None


def _paired_effects(
    rows: Sequence[ItemMetrics], first: str, second: str, ecosystem: str, stratum: str
) -> list[float]:
    """Per item, `correct(second) - correct(first)`, over items both scored."""
    by_item: dict[str, dict[str, bool]] = {}
    for row in rows:
        if row.ecosystem != ecosystem or row.correct is None:
            continue
        if stratum != "all" and row.case_type != stratum:
            continue
        by_item.setdefault(row.item_id, {})[row.condition] = row.correct
    return [
        float(conditions[second]) - float(conditions[first])
        for _, conditions in sorted(by_item.items())
        if first in conditions and second in conditions
    ]


def interactions(
    rows: Sequence[ItemMetrics], *, iterations: int, seed: int
) -> list[Interaction]:
    out: list[Interaction] = []
    for stratum in STRATA:
        for first, second in PAIRS:
            npm = _paired_effects(rows, first, second, "npm", stratum)
            pypi = _paired_effects(rows, first, second, "pypi", stratum)
            if not npm or not pypi:
                continue
            npm_mean, pypi_mean = sum(npm) / len(npm), sum(pypi) / len(pypi)
            rng = random.Random(seed)  # noqa: S311 - resampling, not crypto
            draws = []
            for _ in range(iterations):
                a = [npm[rng.randrange(len(npm))] for _ in npm]
                b = [pypi[rng.randrange(len(pypi))] for _ in pypi]
                draws.append(sum(a) / len(a) - sum(b) / len(b))
            draws.sort()
            out.append(
                Interaction(
                    stratum=stratum,
                    first=first,
                    second=second,
                    npm_n=len(npm),
                    pypi_n=len(pypi),
                    npm_effect=npm_mean,
                    pypi_effect=pypi_mean,
                    difference=npm_mean - pypi_mean,
                    low=stats.percentile(draws, 0.025) if draws else None,
                    high=stats.percentile(draws, 0.975) if draws else None,
                )
            )
    return out


# ── 3. The qualitative slice ──────────────────────────────────────────────


@dataclass(frozen=True)
class Kind:
    name: str
    definition: str


KINDS: tuple[Kind, ...] = (
    Kind(
        "grounded and correct",
        "B or C, grounding sufficient, at least one passage cited, correct, and "
        "labelled faithful by the human",
    ),
    Kind(
        "grounded but wrong",
        "B or C, grounding sufficient, at least one passage shown, not correct, "
        "and TARGET did show a correct answer",
    ),
    Kind(
        "honest abstention",
        "C, grounding low, and the plan declares insufficient information",
    ),
    Kind(
        "unsupported core claim",
        "labelled major_unsupported by the human",
    ),
    Kind(
        "overclaim on coverage",
        "labelled unsupported by the human with a note that the plan claims to "
        "fix all known vulnerabilities",
    ),
    Kind(
        "missed successor",
        "labelled unsupported by the human with a note that the plan says no "
        "successor or replacement is known",
    ),
    Kind(
        "retrieval made it worse",
        "TARGET did not show a correct answer; A was correct and C was not",
    ),
    Kind(
        "README-only retrieval",
        "B on PyPI, every passage shown is from a README, and precision@k is 0",
    ),
)


@dataclass(frozen=True)
class Example:
    kind: Kind
    row: ItemMetrics
    record: dict
    item: dict
    label: tuple[str, str] | None
    packet_id: str | None


def _cited(record: dict) -> list[str]:
    return [str(c) for c in (record.get("generation") or {}).get("citations") or []]


def _shown(record: dict) -> list[dict]:
    ids = set(record.get("shown_chunk_ids") or [])
    return [c for c in record.get("retrieved") or [] if str(c.get("chunk_id")) in ids]


def examples(
    rows: Sequence[ItemMetrics],
    records: dict[tuple[str, str], dict],
    items: dict[str, dict],
    labels: dict[str, tuple[str, str]],
    key: dict[str, dict],
) -> list[Example]:
    """One example per kind in `KINDS`, the first by `(item_id, condition)`."""
    labelled = {
        (entry["item_id"], entry["condition"]): number for number, entry in key.items()
    }
    by_pair = {(row.item_id, row.condition): row for row in rows}

    def label_of(row: ItemMetrics) -> tuple[str, str] | None:
        number = labelled.get((row.item_id, row.condition))
        return labels.get(number) if number else None

    def matches(kind: Kind, row: ItemMetrics) -> bool:
        record = records.get((row.item_id, row.condition)) or {}
        label = label_of(row)
        note = (label[1] if label else "").lower()
        if row.status != "ok":
            return False
        if kind.name == "grounded and correct":
            return (
                row.condition in ("B", "C")
                and row.grounding == "sufficient"
                and bool(_cited(record))
                and row.correct is True
                and label is not None
                and label[0] == judge.FAITHFUL
            )
        if kind.name == "grounded but wrong":
            return (
                row.condition in ("B", "C")
                and row.grounding == "sufficient"
                and bool(_shown(record))
                and row.correct is False
                and row.answer_given
            )
        if kind.name == "honest abstention":
            return (
                row.condition == "C"
                and row.grounding == "low"
                and row.declared_insufficient is True
            )
        if kind.name == "unsupported core claim":
            return label is not None and label[0] == judge.MAJOR
        if kind.name == "overclaim on coverage":
            return (
                label is not None
                and label[0] != judge.FAITHFUL
                and "all known vulnerabilities" in note
            )
        if kind.name == "missed successor":
            return (
                label is not None
                and label[0] != judge.FAITHFUL
                and ("successor" in note or "replacement" in note)
                and ("no " in note or "not " in note)
            )
        if kind.name == "retrieval made it worse":
            other = by_pair.get((row.item_id, "A"))
            return (
                row.condition == "C"
                and not row.answer_given
                and row.correct is False
                and other is not None
                and other.correct is True
            )
        if kind.name == "README-only retrieval":
            shown = _shown(record)
            return (
                row.condition == "B"
                and row.ecosystem == "pypi"
                and bool(shown)
                and all(c.get("source_kind") == "readme" for c in shown)
                and row.precision_at_k == 0
            )
        raise SupplementError(f"No rule for {kind.name!r}.")  # pragma: no cover

    found: list[Example] = []
    ordered = sorted(rows, key=lambda row: (row.item_id, row.condition))
    for kind in KINDS:
        for row in ordered:
            if matches(kind, row):
                found.append(
                    Example(
                        kind,
                        row,
                        records[(row.item_id, row.condition)],
                        items[row.item_id],
                        label_of(row),
                        labelled.get((row.item_id, row.condition)),
                    )
                )
                break
    return found


def render_examples(found: Sequence[Example]) -> str:
    lines = [
        "# S3 qualitative slice",
        "",
        "One example per kind of outcome (File C §3.4.9). Each is the first item, by "
        "id, that meets its kind's definition, so the selection is a rule rather than "
        "a choice. Faithfulness labels are the human's (WP-9); the judge is not "
        "validated (kappa 0.134).",
        "",
    ]
    for number, example in enumerate(found, 1):
        row, record, item = example.row, example.record, example.item
        target = item["target"]
        generation = record.get("generation") or {}
        lines += [
            f"## {number}. {example.kind.name[0].upper()}{example.kind.name[1:]}",
            "",
            f"*Rule: {example.kind.definition}.*",
            "",
            f"- **Item:** `{row.item_id}`, condition **{row.condition}**, {row.ecosystem}, "
            f"`{row.case_type}`"
            + (f", WP-9 `{example.packet_id}`" if example.packet_id else ""),
            f"- **Dependency:** `{target.get('package')}@{target.get('current_version')}`; "
            f"latest {target.get('latest_version')}; deprecated "
            f"{'yes' if target.get('deprecated') else 'no'}"
            + (
                f' ("{target.get("deprecation_reason")}")'
                if target.get("deprecation_reason")
                else ""
            ),
            "- **Advisories (fixed in):** " + _advisories(target),
            f"- **Ground truth:** {_truth(item)}",
            f"- **Outcome:** correct {row.correct} ({row.correctness_reason}); grounding "
            + (
                "n/a (condition A retrieves nothing)"
                if row.condition == "A"
                else f"{row.grounding}; branch {row.branch}"
            )
            + f"; TARGET shows the answer: {'yes' if row.answer_given else 'no'}",
        ]
        shown = _shown(record)
        lines.append(
            "- **Passages shown:** "
            + (
                ", ".join(
                    f"`{c.get('source_path')}` ({c.get('source_kind')}, sim "
                    f"{float(c.get('similarity') or 0):.2f})"
                    for c in shown
                )
                or "none"
            )
        )
        if example.label:
            lines.append(
                f"- **Human label:** {example.label[0]}"
                + (f" — {example.label[1]}" if example.label[1] else "")
            )
        lines += [
            "",
            "**The plan's summary:**",
            "",
            "> " + str(generation.get("summary_md") or "").strip().replace("\n", "\n> "),
            "",
            "| Fix | Target version | Replacement |",
            "|---|---|---|",
        ]
        for fix in generation.get("fixes") or []:
            lines.append(
                f"| {fix.get('fix_type')} | {fix.get('target_version') or ''} | "
                f"{fix.get('replacement_package') or ''} |"
            )
        lines.append("")
    return "\n".join(lines)


def _truth(item: dict) -> str:
    truth = item.get("ground_truth") or {}
    if truth.get("target_version"):
        return f"upgrade to {truth['target_version']} or later"
    successor = truth.get("successor") or truth.get("replacement_package")
    if successor:
        return f"replace with `{successor}`"
    return json.dumps(truth, sort_keys=True)[:120]


def _advisories(target: dict) -> str:
    """Each advisory once, by its CVE id where it has one, with its fix."""
    seen: dict[str, str] = {}
    for advisory in target.get("advisories") or []:
        name = advisory.get("cve_id") or advisory.get("osv_id") or "no id"
        seen.setdefault(name, advisory.get("fixed_version") or "no fix recorded")
    return ", ".join(f"{name} ({fixed})" for name, fixed in seen.items()) or "none"


# ── The run, and its files ────────────────────────────────────────────────


#: The export files the supplement reads; their digests travel with its output.
INPUT_FILES_FIXED: tuple[str, ...] = (
    "judge_validation/judge_validation_packet.md",
    "judge_validation/wp9_judge_labels.csv",
    "runs/analysis/metrics.csv",
    "runs/ground_truth/labelled_set.jsonl",
)

FILES: tuple[str, ...] = (
    "inputs.json",
    "supplement.md",
    "human_faithfulness.csv",
    "interaction.csv",
    "examples.md",
    "wp9_kappa.md",
    "judge_validation_key_rebuilt.json",
)


def input_digests(export: Path) -> dict[str, str]:
    manifest = json.loads((export / "MANIFEST.json").read_text(encoding="utf-8"))
    recorded = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    wanted = list(INPUT_FILES_FIXED) + sorted(
        path
        for path in recorded
        if path.startswith("runs/") and path.endswith("/" + runner.ITEMS_FILENAME)
    )
    missing = [name for name in wanted if name not in recorded]
    if missing:
        raise SupplementError(f"The export's manifest lists no {', '.join(missing)}.")
    return {name: recorded[name] for name in wanted}


def same_inputs(export: Path, committed: Path) -> bool:
    recorded = committed / "inputs.json"
    if not recorded.exists():
        return False
    digests = json.loads(recorded.read_text(encoding="utf-8")).get("inputs", {})
    return digests == input_digests(export)


@dataclass
class Supplement:
    kappa: judge_validation.KappaResult
    faithfulness: list[judge_validation.LabelCounts]
    interactions: list[Interaction]
    examples: list[Example]
    key: dict[str, dict]
    seed: int
    iterations: int
    inputs_digest: dict[str, str]


def run(
    rows: Sequence[ItemMetrics],
    records: dict[tuple[str, str], dict],
    items: dict[str, dict],
    labels: dict[str, tuple[str, str]],
    key: dict[str, dict],
    *,
    seed: int = 42,
    iterations: int = 2000,
    inputs_digest: dict[str, str] | None = None,
) -> Supplement:
    return Supplement(
        kappa=judge_validation.kappa(labels, key),
        faithfulness=judge_validation.human_faithfulness(labels, key),
        interactions=interactions(rows, iterations=iterations, seed=seed),
        examples=examples(rows, records, items, labels, key),
        key=key,
        seed=seed,
        iterations=iterations,
        inputs_digest=dict(inputs_digest or {}),
    )


INTERACTION_COLUMNS: tuple[str, ...] = (
    "stratum",
    "first",
    "second",
    "npm_n",
    "pypi_n",
    "npm_effect",
    "pypi_effect",
    "difference",
    "ci_low",
    "ci_high",
)


def _f(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def write(result: Supplement, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "inputs.json").write_text(
        json.dumps(
            {
                "seed": result.seed,
                "bootstrap": result.iterations,
                "inputs": result.inputs_digest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with (out / "human_faithfulness.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["condition", "ecosystem", "n"]
            + [f"human_{v}" for v in judge.VERDICTS]
            + [f"judge_{v}" for v in judge.VERDICTS]
            + ["unsupported_rate", "unsupported_low", "unsupported_high"]
            + ["major_rate", "major_low", "major_high"]
        )
        for row in result.faithfulness:
            unsupported = judge_validation.wilson_interval(row.unsupported, row.n)
            major = judge_validation.wilson_interval(row.human[judge.MAJOR], row.n)
            writer.writerow(
                [row.condition, row.ecosystem, row.n]
                + [row.human[v] for v in judge.VERDICTS]
                + [row.judge[v] for v in judge.VERDICTS]
                + [_f(row.unsupported / row.n), _f(unsupported[0]), _f(unsupported[1])]
                + [_f(row.human[judge.MAJOR] / row.n), _f(major[0]), _f(major[1])]
            )
    with (out / "interaction.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(INTERACTION_COLUMNS)
        for i in result.interactions:
            writer.writerow(
                [
                    i.stratum,
                    i.first,
                    i.second,
                    i.npm_n,
                    i.pypi_n,
                    _f(i.npm_effect),
                    _f(i.pypi_effect),
                    _f(i.difference),
                    _f(i.low),
                    _f(i.high),
                ]
            )
    (out / "examples.md").write_text(render_examples(result.examples), encoding="utf-8")
    (out / "wp9_kappa.md").write_text(
        judge_validation.kappa_report(result.kappa), encoding="utf-8"
    )
    (out / "judge_validation_key_rebuilt.json").write_text(
        json.dumps(
            {
                "note": "Rebuilt from the committed runs and packet and checked against "
                "the packet verbatim (decisions §15.3). Judge verdicts are as recorded "
                "in metrics.csv; the judge's notes were not recorded there.",
                "items": result.key,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "supplement.md").write_text(render(result), encoding="utf-8")
    return [out / name for name in FILES]


def render(result: Supplement) -> str:
    k = result.kappa
    lines = [
        "# S3 supplementary analyses",
        "",
        "Generated by `apps.research.experiment.supplement` from the replication "
        f"export, seed {result.seed}, {result.iterations} bootstrap resamples.",
        "",
        "## 1. The judge, recomputed (File C §3.4.1)",
        "",
        f"WP-9's answer key, rebuilt from the runs and checked against the packet "
        f"verbatim: Cohen's kappa **{k.kappa:.3f}**, linearly weighted "
        f"{k.weighted_kappa:.3f}, raw agreement {k.agreement:.0%} over {k.n} items. "
        "Below 0.50, so the judge's faithfulness verdicts are not used for S3's "
        "claims; faithfulness comes from the human labels (decisions §15.3).",
        "",
        "## 2. Faithfulness from the human labels",
        "",
        "One human label per sampled generation, stratified by condition x "
        "ecosystem and not paired across conditions, so the groups are compared "
        "descriptively. Intervals are Wilson 95%.",
        "",
        judge_validation.human_faithfulness_table(result.faithfulness),
        "",
        "## 3. Condition x ecosystem interaction (File C §3.4.6)",
        "",
        "Effect = paired change in correctness rate from the first condition to "
        "the second, per ecosystem; difference = npm effect - PyPI effect. "
        "Positive: the change helps npm more (or hurts PyPI more). Interval: 95% "
        "bootstrap resampling items within each ecosystem.",
        "",
        "| Stratum | Pair | npm n | npm effect | PyPI n | PyPI effect | Difference | 95% interval |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i in result.interactions:
        lines.append(
            f"| {i.stratum} | {i.first} -> {i.second} | {i.npm_n} | {i.npm_effect:+.3f} | "
            f"{i.pypi_n} | {i.pypi_effect:+.3f} | {i.difference:+.3f} | "
            f"[{i.low:+.3f}, {i.high:+.3f}] |"
        )
    lines += [
        "",
        "## 4. The qualitative slice",
        "",
        f"{len(result.examples)} examples, one per kind: `examples.md`.",
        "",
        "| # | Kind | Item | Condition | Ecosystem |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {n} | {e.kind.name} | `{e.row.item_id}` | {e.row.condition} | {e.row.ecosystem} |"
        for n, e in enumerate(result.examples, 1)
    ]
    lines.append("")
    return "\n".join(lines)
