"""WP-9: is the judge measuring what S3 says it measures?

§10 Phase 13: "`judge_validation_packet` (WP-9): stratified 50 generations,
judge verdicts hidden, rubric attached; `judge_validation_kappa`: labels in ->
Cohen's kappa + disagreement listing."

**The packet is blind in three ways.** It shows each generation with the
dependency it is about and the exact passages its author was shown — and not
the judge's verdict, not the condition that produced it, and not the
grounding flag, because a labeller who knows "this one had retrieval" reads
the answer differently. The mapping back to run, item, condition and verdict
is a separate key file the labeller is never sent.

**Ids are `ITEM-001` ... `ITEM-050`, from the packet.** The 2026-09-24 review
told the teammate exactly that, after a template invented its own ids; the CSV
template is written with them filled in and the label column empty.

**Only judged generations are sampled.** Kappa compares two labels per item,
so an item the judge has not scored yet cannot be in the packet. The sample is
stratified across condition x ecosystem, proportionally, with every non-empty
cell represented, and seeded.

**The decision rule is File C's, printed with the number.** §3.4.1: kappa ≥
0.70 -> verdicts used as-is; 0.5-0.7 -> faithfulness also reported on the
human-labelled 50 and claims softened; < 0.5 -> tighten the rubric, re-judge,
re-validate.
"""

from __future__ import annotations

import csv
import io
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from apps.research.validation import stats

from . import judge, runner

PACKET_FILENAME = "judge_validation_packet.md"
TEMPLATE_FILENAME = "wp9_judge_labels_template.csv"
KEY_FILENAME = "judge_validation_key.json"
LABEL_COLUMNS: tuple[str, ...] = ("item_id", "label", "note")
DEFAULT_SIZE = 50

#: File C §3.4.1's bands.
USE_AS_IS = 0.70
SOFTEN = 0.50


class ValidationPacketError(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    run_id: str
    record: dict
    item: dict
    judgment: dict


def judged_candidates(
    run_dirs: list[Path], items: dict[str, dict], cache: judge.JudgeCache
) -> list[Candidate]:
    """Every successful generation whose faithfulness verdict is in the cache."""
    found: list[Candidate] = []
    for directory in run_dirs:
        for record in runner.latest_records(directory / runner.ITEMS_FILENAME).values():
            item = items.get(record["item_id"])
            if record.get("status") != "ok" or item is None:
                continue
            shown_ids = set(record.get("shown_chunk_ids") or [])
            shown = [
                c
                for c in record.get("retrieved") or []
                if str(c.get("chunk_id")) in shown_ids
            ]
            key = judge.cache_key(
                judge.FAITHFULNESS,
                record["item_id"],
                record["condition"],
                {
                    "target": item["target"],
                    "generation": record.get("generation") or {},
                    "shown": shown,
                },
            )
            entry = cache.get(key)
            if entry is not None:
                found.append(
                    Candidate(directory.name, record, item, {**entry, "shown": shown})
                )
    return found


def stratified(candidates: list[Candidate], size: int, seed: int) -> list[Candidate]:
    """Proportional across condition x ecosystem, every non-empty cell at least once."""
    cells: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for candidate in sorted(candidates, key=lambda c: (c.run_id, c.record["item_id"])):
        cells[(candidate.record["condition"], candidate.item["ecosystem"])].append(
            candidate
        )
    rng = random.Random(seed)  # noqa: S311 - sampling, not crypto
    for pool in cells.values():
        rng.shuffle(pool)
    total = sum(len(pool) for pool in cells.values())
    size = min(size, total)
    quota = {
        cell: max(1, round(size * len(pool) / total)) for cell, pool in cells.items()
    }
    # Trim or top up to exactly `size`, largest cells first, never past a pool.
    order = sorted(cells, key=lambda cell: (-len(cells[cell]), cell))
    while sum(quota.values()) > size:
        for cell in order:
            if sum(quota.values()) > size and quota[cell] > 1:
                quota[cell] -= 1
    while sum(quota.values()) < size:
        grown = False
        for cell in order:
            if sum(quota.values()) < size and quota[cell] < len(cells[cell]):
                quota[cell] += 1
                grown = True
        if not grown:
            break
    chosen = [candidate for cell in order for candidate in cells[cell][: quota[cell]]]
    rng.shuffle(chosen)
    return chosen


#: How each measured field is named for the labeller, in the order shown. The
#: judge is given the *whole* `target` record as MEASURED DATA
#: (`judge.faithfulness_prompt`), so the packet must show the whole record too:
#: a labeller missing a field the judge had is answering a different question.
#: The first packet showed four of the fifteen fields every item carries, so the
#: human and the judge were labelling against different evidence (decisions
#: §13.16). A field not in this table is still shown, under its own name.
MEASURED_LABELS: dict[str, str] = {
    "current_version": "Version in use",
    "declared_specifier": "Declared specifier",
    "version_source": "Where that version came from",
    "manifest_path": "Manifest",
    "group": "Dependency group",
    "latest_version": "Latest release on the registry",
    "versions_behind": "Versions behind the latest release",
    "days_since_release": "Days since the package's latest release",
    "deprecated": "Deprecated on the registry",
    "deprecation_reason": "Registry deprecation message",
    "advisory_count": "Advisories affecting this version (scanner's count)",
    "highest_severity": "Highest advisory severity",
    "flag_reasons": "Why it was flagged",
}


def _format_measured(value) -> str:
    if value is None or value == "":
        return "not recorded"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return ", ".join(
            f"{key} {_format_measured(inner)}" for key, inner in value.items()
        )
    if isinstance(value, list):
        return ", ".join(_format_measured(inner) for inner in value) or "none"
    return str(value)


def measured_lines(target: dict) -> list[str]:
    """Every field of the record the judge sees as MEASURED DATA, readable."""
    lines = [
        f"**Dependency:** `{target.get('package')}` ({target.get('ecosystem')})",
        "",
        "**Measured data** (all of it counts as evidence):",
        "",
    ]
    rendered = {"package", "ecosystem", "advisories"}
    ordered = [key for key in MEASURED_LABELS if key in target]
    ordered += sorted(
        key for key in target if key not in MEASURED_LABELS and key not in rendered
    )
    for key in ordered:
        label = MEASURED_LABELS.get(key, key)
        lines.append(f"- {label}: {_format_measured(target[key])}")
    advisories = target.get("advisories") or []
    lines.append(
        f"- Advisories in detail (highest CVSS first): {len(advisories) or 'none'}"
    )
    for advisory in advisories:
        ids = " / ".join(
            str(advisory[key]) for key in ("cve_id", "osv_id") if advisory.get(key)
        )
        extra = {
            key: value
            for key, value in advisory.items()
            if key not in ("cve_id", "osv_id", "severity", "cvss", "fixed_version")
        }
        lines.append(
            f"  - {ids or 'no id'}: severity {_format_measured(advisory.get('severity'))}, "
            f"CVSS {_format_measured(advisory.get('cvss'))}, fixed in "
            f"{advisory.get('fixed_version') or 'unknown'}"
            + "".join(
                f", {key} {_format_measured(value)}" for key, value in extra.items()
            )
        )
    return lines


def _render_item(number: str, candidate: Candidate) -> list[str]:
    target = candidate.item["target"]
    generation = candidate.record.get("generation") or {}
    lines = [f"## {number}", "", *measured_lines(target)]
    lines += [
        "",
        "### Remediation to label",
        "",
        str(generation.get("summary_md") or "").strip(),
        "",
        "| Package | Fix | Target version | Replacement |",
        "|---|---|---|---|",
    ]
    for fix in generation.get("fixes") or []:
        lines.append(
            f"| {fix.get('package')} | {fix.get('fix_type')} | "
            f"{fix.get('target_version') or ''} | {fix.get('replacement_package') or ''} |"
        )
    lines += ["", "### Source passages the author was shown", ""]
    shown = candidate.judgment.get("shown") or []
    if not shown:
        lines.append("_None. The author was shown no passages for this item._")
    for chunk in shown:
        lines += [
            f"**Passage `{chunk.get('chunk_id')}`** — from `{chunk.get('source_path')}`",
            "",
            "```",
            str(chunk.get("text") or "").strip(),
            "```",
            "",
        ]
    lines += ["", "---", ""]
    return lines


RUBRIC = """\
Label each item `faithful`, `minor_unsupported` or `major_unsupported`, judging
the remediation **only** against the dependency facts and the passages shown with
it — not your own knowledge, not the internet (File B, WP-9).

- **faithful** — every material claim is stated by, or directly follows from, the
  facts or passages shown. "Insufficient information to recommend…" over thin
  sources is faithful.
- **minor_unsupported** — at most one peripheral claim is unsupported; the core
  recommendation is supported.
- **major_unsupported** — a core claim (the recommended version, the replacement
  package, a breaking-change assertion) is not in what was shown. Empty or
  unreadable source with a specific recommendation is major.

Version numbers, package names and migration steps all count as claims. Write a
one-line note naming the offending claim for every label that is not
`faithful`. One sitting; no conferring; no skipped items.
"""


def build_packet(
    run_dirs: list[Path],
    items: dict[str, dict],
    cache: judge.JudgeCache,
    out_dir: Path,
    *,
    size: int = DEFAULT_SIZE,
    seed: int = 42,
) -> list[Path]:
    candidates = judged_candidates(run_dirs, items, cache)
    if not candidates:
        raise ValidationPacketError(
            "No judged generations to sample from. Run a condition with a "
            "GEMINI_API_KEY set, or `analyze_experiment --judge`, first."
        )
    chosen = stratified(candidates, size, seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    packet = [
        "# WP-9 judge-validation packet",
        "",
        f"{len(chosen)} items. Label them in `{TEMPLATE_FILENAME}`.",
        "",
        "## Rubric",
        "",
        RUBRIC,
        "---",
        "",
    ]
    key: dict[str, dict] = {}
    template = io.StringIO()
    writer = csv.writer(template, lineterminator="\n")
    writer.writerow(LABEL_COLUMNS)
    for index, candidate in enumerate(chosen, 1):
        number = f"ITEM-{index:03d}"
        packet += _render_item(number, candidate)
        writer.writerow([number, "", ""])
        key[number] = {
            "run_id": candidate.run_id,
            "item_id": candidate.record["item_id"],
            "condition": candidate.record["condition"],
            "ecosystem": candidate.item["ecosystem"],
            "case_type": candidate.item["case_type"],
            "judge_verdict": candidate.judgment.get("verdict"),
            "judge_note": candidate.judgment.get("note"),
            "judge_version": candidate.judgment.get("judge_version"),
        }

    written = [
        out_dir / PACKET_FILENAME,
        out_dir / TEMPLATE_FILENAME,
        out_dir / KEY_FILENAME,
    ]
    written[0].write_text("\n".join(packet), encoding="utf-8")
    written[1].write_text(template.getvalue(), encoding="utf-8")
    written[2].write_text(
        json.dumps(
            {
                "note": "KEEP PRIVATE. Do not send to the labeller: it holds the judge's verdicts.",
                "seed": seed,
                "candidates_available": len(candidates),
                "items": key,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return written


# ── the labels coming back ─────────────────────────────────────────────────


@dataclass
class KappaResult:
    n: int
    kappa: float | None
    weighted_kappa: float | None
    agreement: float
    matrix: list[list[int]]
    disagreements: list[dict]
    missing_notes: list[str]

    @property
    def decision(self) -> str:
        if self.kappa is None:
            return "undefined: every label in one category on both sides"
        if self.kappa >= USE_AS_IS:
            return "kappa >= 0.70: judge verdicts used as-is (File C §3.4.1)"
        if self.kappa >= SOFTEN:
            return (
                "0.50 <= kappa < 0.70: faithfulness also reported on the human-labelled "
                "50, and claims softened (File C §3.4.1)"
            )
        return "kappa < 0.50: tighten the rubric, re-judge and re-validate before any S3 claim"


def read_labels(path: Path, key: dict) -> dict[str, tuple[str, str]]:
    """`{packet id: (label, note)}`, or a refusal saying which row is wrong."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ValidationPacketError(f"No labels at {path}.") from exc
    reader = csv.reader(io.StringIO(text))
    header = tuple(cell.strip() for cell in next(reader, []))
    if header != LABEL_COLUMNS:
        raise ValidationPacketError(
            f"The header must be exactly {', '.join(LABEL_COLUMNS)} (File B, WP-9)."
        )
    labels: dict[str, tuple[str, str]] = {}
    for line, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        cells = [cell.strip() for cell in row] + ["", "", ""]
        number, label, note = cells[0], cells[1], cells[2]
        if number not in key:
            raise ValidationPacketError(
                f"Line {line}: {number!r} is not a packet item id."
            )
        if number in labels:
            raise ValidationPacketError(f"Line {line}: {number} is labelled twice.")
        if label not in judge.VERDICTS:
            raise ValidationPacketError(
                f"Line {line}: {number} is labelled {label!r}; the labels are "
                f"{', '.join(judge.VERDICTS)}."
            )
        labels[number] = (label, note)
    missing = sorted(set(key) - set(labels))
    if missing:
        raise ValidationPacketError(
            f"{len(missing)} item(s) unlabelled: {', '.join(missing[:10])}. File B: no "
            f"skipped items."
        )
    return labels


def kappa(labels: dict[str, tuple[str, str]], key: dict) -> KappaResult:
    numbers = sorted(labels)
    human = [labels[number][0] for number in numbers]
    machine = [key[number]["judge_verdict"] for number in numbers]
    matrix = stats.confusion(human, machine, judge.VERDICTS)
    agreement = sum(1 for a, b in zip(human, machine, strict=True) if a == b) / len(
        numbers
    )
    return KappaResult(
        n=len(numbers),
        kappa=stats.cohen_kappa(matrix),
        weighted_kappa=stats.weighted_kappa(matrix),
        agreement=agreement,
        matrix=matrix,
        disagreements=[
            {
                "id": number,
                "human": labels[number][0],
                "judge": key[number]["judge_verdict"],
                "human_note": labels[number][1],
                "judge_note": key[number].get("judge_note") or "",
                "condition": key[number]["condition"],
                "ecosystem": key[number]["ecosystem"],
            }
            for number in numbers
            if labels[number][0] != key[number]["judge_verdict"]
        ],
        missing_notes=[
            number
            for number in numbers
            if labels[number][0] != judge.FAITHFUL and not labels[number][1]
        ],
    )


def kappa_report(result: KappaResult) -> str:
    lines = [
        "# WP-9: judge validation",
        "",
        f"- Items: {result.n}",
        f"- Cohen's kappa (human vs judge): **{'n/a' if result.kappa is None else f'{result.kappa:.3f}'}**",
        f"- Linearly weighted kappa (ordinal): "
        f"{'n/a' if result.weighted_kappa is None else f'{result.weighted_kappa:.3f}'}",
        f"- Raw agreement: {result.agreement:.1%}",
        f"- **Decision:** {result.decision}",
        "",
        "## Confusion (rows: human, columns: judge)",
        "",
        "| | " + " | ".join(judge.VERDICTS) + " |",
        "|---|---|---|---|",
    ]
    for name, row in zip(judge.VERDICTS, result.matrix, strict=True):
        lines.append(f"| {name} | " + " | ".join(str(value) for value in row) + " |")
    lines += ["", "## Disagreements", ""]
    if not result.disagreements:
        lines.append("None.")
    else:
        lines += [
            "| Item | Human | Judge | Condition | Ecosystem | Human note | Judge note |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in result.disagreements:
            lines.append(
                f"| {row['id']} | {row['human']} | {row['judge']} | {row['condition']} | "
                f"{row['ecosystem']} | {row['human_note']} | {row['judge_note']} |"
            )
    if result.missing_notes:
        lines += [
            "",
            f"**Labels without the required note** (WP-9 step 3): {', '.join(result.missing_notes)}.",
        ]
    lines.append("")
    return "\n".join(lines)
