"""S3's metrics. Correctness is a program; faithfulness and relevance are judged.

§10 Phase 13: "**correctness = deterministic, no LLM** — recommended version
satisfies the ground-truth fixed range (PEP 440 / semver) or replacement name
matches".

**What a recommendation is.** The structured fix the §5.8 schema already
forces, not the prose: the generation's highest-priority fix for the item's
package. A version mentioned only in `summary_md` is not a recommendation a
coding agent could act on (§5.8: "the JSON download is a machine-parseable
task handoff"), so it is not scored as one.

**`cve_fix` is correct when the recommended version escapes every advisory in
the item.** Any safe upgrade counts, not only the minimum (`groundtruth`
explains why). The model's spelling is forgiven where it is unambiguous —
`^4.17.21`, `>=4.17.21`, `v4.17.21` — and nothing else: `latest` and `4.x` are
unreadable, and an unreadable recommendation is not a correct one. A fix that
replaces or removes the package where an upgrade exists is incorrect for this
case type.

**`deprecation_replacement` is correct when the named replacement is the
successor**, compared under the ecosystem's own name normalization (PEP 503 for
PyPI).

**Abstention is counted, and is not correct.** "Insufficient information" is
the designed behaviour on thin evidence (§5.9), and the judge scores it
faithful; but it does not remediate anything, so correctness is false and
`declared_insufficient` is reported beside it for File C §3.4.7's calibration
table.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .groundtruth import (
    CVE_FIX,
    DEPRECATION_REPLACEMENT,
    AdvisoryRanges,
    answer_given,
    is_safe_version,
    normalize_name,
    version_key,
)

_OPERATORS = re.compile(r"^[\s^~=<>!]+")

#: The opening the ungrounded prompt requires (§5.9), and the phrasings a
#: grounded answer uses when its sources do not cover the question.
_INSUFFICIENT = re.compile(
    r"could not retrieve enough|insufficient information|not enough (?:documentation|information)"
    r"|does not (?:provide|contain) enough|no (?:source|documentation) (?:was|were) (?:retrieved|found)",
    re.IGNORECASE,
)


def clean_version(ecosystem: str, text: str | None) -> str | None:
    """The version a recommendation names, if it names exactly one readably."""
    if not text:
        return None
    candidate = _OPERATORS.sub("", str(text)).strip()
    candidate = candidate.split(",")[0].split()[0] if candidate.split() else ""
    candidate = candidate.rstrip(".;:)")
    if ecosystem == "npm":
        candidate = candidate.lstrip("vV")
    return candidate if version_key(ecosystem, candidate) is not None else None


def recommended_fix(item: dict, generation: dict) -> dict | None:
    """The highest-priority fix for the item's own package, if there is one."""
    own = normalize_name(item["ecosystem"], item["package"])
    fixes = [
        fix
        for fix in generation.get("fixes") or []
        if isinstance(fix, dict)
        and normalize_name(item["ecosystem"], str(fix.get("package") or "")) == own
    ]
    if not fixes:
        return None
    return min(fixes, key=lambda fix: fix.get("priority") or 99)


@dataclass(frozen=True)
class Correctness:
    correct: bool
    reason: str
    recommended_version: str | None = None
    recommended_replacement: str | None = None


def correctness(item: dict, generation: dict) -> Correctness:
    fix = recommended_fix(item, generation)
    if fix is None:
        return Correctness(False, "no_fix_for_this_package")
    ecosystem = item["ecosystem"]
    truth = item["ground_truth"]

    if item["case_type"] == CVE_FIX:
        if fix.get("fix_type") in ("replace", "remove"):
            return Correctness(
                False,
                "not_an_upgrade",
                recommended_replacement=fix.get("replacement_package"),
            )
        version = clean_version(ecosystem, fix.get("target_version"))
        if version is None:
            reason = (
                "no_version" if not fix.get("target_version") else "unreadable_version"
            )
            return Correctness(
                False, reason, recommended_version=fix.get("target_version")
            )
        advisories = [
            AdvisoryRanges.from_json(entry) for entry in truth.get("advisories") or []
        ]
        safe = is_safe_version(ecosystem, version, item["resolved_version"], advisories)
        if safe is None:
            return Correctness(False, "unreadable_version", recommended_version=version)
        return Correctness(
            safe, "escapes_every_advisory" if safe else "still_affected_or_not_an_upgrade",
            recommended_version=version,
        )  # fmt: skip

    if item["case_type"] == DEPRECATION_REPLACEMENT:
        replacement = fix.get("replacement_package")
        if not replacement:
            return Correctness(False, "no_replacement")
        matches = (
            normalize_name(ecosystem, str(replacement)) == truth["successor_normalized"]
        )
        return Correctness(
            matches,
            "successor_named" if matches else "different_replacement",
            recommended_replacement=str(replacement),
        )

    raise ValueError(f"unknown case type {item['case_type']!r}")


def declared_insufficient(generation: dict) -> bool:
    return bool(_INSUFFICIENT.search(str(generation.get("summary_md") or "")))


@dataclass
class ItemMetrics:
    """Everything the analysis needs about one (item, condition)."""

    item_id: str
    condition: str
    ecosystem: str
    case_type: str
    #: TARGET already shows a value that, copied, is correct (decisions §13.13).
    answer_given: bool
    status: str
    grounding: str
    branch: str
    correct: bool | None
    correctness_reason: str
    declared_insufficient: bool | None
    faithfulness: str | None
    stated_verdict: str | None
    precision_at_k: float | None
    k: int | None

    def as_json(self) -> dict:
        return asdict(self)


def measure(record: dict, item: dict, judgments: dict | None = None) -> ItemMetrics:
    """One record's metrics; the judged ones are None until judged."""
    judgments = judgments or {}
    faith = judgments.get("faithfulness") or {}
    relevance = judgments.get("relevance") or {}
    ok = record.get("status") == "ok"
    found = correctness(item, record.get("generation") or {}) if ok else None
    return ItemMetrics(
        item_id=record["item_id"],
        condition=record["condition"],
        ecosystem=item["ecosystem"],
        case_type=item["case_type"],
        answer_given=answer_given(item),
        status=record.get("status", ""),
        grounding=record.get("grounding", ""),
        branch=record.get("branch", ""),
        correct=found.correct if found else None,
        correctness_reason=found.reason if found else "generation_failed",
        declared_insufficient=declared_insufficient(record.get("generation") or {})
        if ok
        else None,
        faithfulness=faith.get("verdict"),
        stated_verdict=faith.get("stated_verdict"),
        precision_at_k=relevance.get("precision_at_k"),
        k=relevance.get("k"),
    )
