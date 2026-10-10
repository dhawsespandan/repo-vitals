"""S3's judge: faithfulness and chunk relevance, by a different provider (D11).

§10 Phase 13: "**faithfulness** = Gemini judge, claim-level rubric ->
{faithful, minor_unsupported, major_unsupported}, cached by (item, condition,
judge-version); **retrieval precision@k** = judge chunk-relevance (B/C/D)."

**A different provider, at temperature 0, with JSON out.** D11: self-judging is
a known reviewer attack, so the generator is Groq and the judge is Gemini. The
key travels in Gemini's `x-goog-api-key` header, never in the URL, through the
same allowlisted client as every other call (`apps.common.http`).

**The judge lists claims; the verdict is computed from them.** File B's rubric
(WP-9 step 3, Appendix C) is a rule over claims: faithful when every material
claim is supported; minor when at most one peripheral claim is not and the
core recommendation is; major when a core claim — the recommended version, the
replacement package, a breaking-change assertion — is not. Asking the model
for claims and applying that rule here makes the verdict reproducible from the
cached claims, and lets the analysis count where the judge's own stated
verdict disagrees with its own claims. Two unsupported peripheral claims are
not "at most one", so they are major.

**Supported means by what the model was shown.** The judge sees the item's
TARGET (measured data, which supports the claims that restate it) and exactly
the passages the generation was shown — none for condition A, none on the
grounded agent's low-confidence path — never the passages that were retrieved
and withheld. Appendix C's last example is in the rubric verbatim in spirit:
"insufficient information" over thin sources is faithful.

**Cached by what was judged.** The key is the task, the item, the condition,
the judge version (model + rubric version) and a digest of the exact inputs, so
a re-run hits the cache (§10 Phase 13's acceptance) and a regenerated answer
does not silently inherit the old answer's verdict.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from django.conf import settings

from apps.common import http
from apps.research.corpus import append_jsonl, read_jsonl

logger = logging.getLogger(__name__)

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
JUDGE_TIMEOUT: tuple[float, float] = (5.0, 90.0)

#: The rubric WP-8's signed verdicts were made under, and the default. Each
#: rubric text has its own version, and the version is in every cache key: a
#: verdict under one rubric is not a verdict under another, and the cache must
#: not pretend otherwise. `JUDGE_RUBRIC` selects another (`RUBRICS`).
RUBRIC_VERSION = "rubric-v1"
#: decisions §13.17's tightened rubric, for the re-validation of §15.4.
RUBRIC_V2 = "rubric-v2"

FAITHFUL = "faithful"
MINOR = "minor_unsupported"
MAJOR = "major_unsupported"
VERDICTS: tuple[str, ...] = (FAITHFUL, MINOR, MAJOR)

FAITHFULNESS = "faithfulness"
RELEVANCE = "relevance"

CACHE_FILENAME = "judge_cache.jsonl"

#: Gemini's free tier counts requests per minute; one every 6.5 s stays under ten.
DEFAULT_PACE_SECONDS = 6.5

#: Waits before each retry of a judge that did not answer. Gemini answers 503
#: ("model overloaded") routinely on the free tier and then answers seconds
#: later — the first live call of this module did exactly that — so one 503
#: must not be read as the daily limit and switch judging off for a session.
UNAVAILABLE_BACKOFF_SECONDS: tuple[float, ...] = (10.0, 30.0)

#: The default judge, a pinned id (never a `-latest` alias, which would move
#: under a multi-day run), chosen on 2026-10-08 against the free tier's real
#: limits as AI Studio shows them, per project and per model: every 3.x Flash
#: allows 20 requests a day, which the pilot's condition A spent on its own;
#: Flash-Lite allows 500 and 15 a minute, enough for the pilot and for WP-8's
#: ~750 judge calls over two days. Checked by a real judge prompt, not by the
#: model list (`gemini-2.5-flash` is listed and refuses new keys). WP-9's kappa
#: is what says whether this judge is good enough (decisions §13.14).
DEFAULT_JUDGE_MODEL = "gemini-3.5-flash-lite"


class JudgeError(Exception):
    pass


class JudgeNotConfigured(JudgeError):
    """No `GEMINI_API_KEY`: judging is skipped, and can be done later."""


class JudgeRefused(JudgeError):
    """The key or the model was refused. Waiting will not help."""


class JudgeUnavailable(JudgeError):
    """No answer, or a rate limit: a reason to stop for now, not a verdict."""


class JudgeUnusable(JudgeError):
    """An answer that is not the JSON the task asked for."""


def judge_model() -> str:
    return getattr(settings, "JUDGE_MODEL", "") or DEFAULT_JUDGE_MODEL


def rubric_version() -> str:
    """The rubric in force: `JUDGE_RUBRIC`, or the one the signed runs used."""
    chosen = getattr(settings, "JUDGE_RUBRIC", "") or RUBRIC_VERSION
    if chosen not in RUBRICS:
        raise JudgeRefused(
            f"JUDGE_RUBRIC={chosen!r} is not a rubric; the rubrics are "
            f"{', '.join(sorted(RUBRICS))}."
        )
    return chosen


def faithfulness_system() -> str:
    return RUBRICS[rubric_version()]


def judge_version() -> str:
    return f"{judge_model()}|{rubric_version()}"


def is_configured() -> bool:
    return bool(getattr(settings, "GEMINI_API_KEY", ""))


def complete_judge(system_prompt: str, user_prompt: str) -> dict:
    """One Gemini generation, temperature 0, JSON out. Returns the parsed object."""
    key = getattr(settings, "GEMINI_API_KEY", "")
    if not key:
        raise JudgeNotConfigured("GEMINI_API_KEY is not set.")
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    try:
        response = http.post_json(
            f"{GEMINI_API}/{quote(judge_model(), safe='')}:generateContent",
            body,
            headers={"x-goog-api-key": key},
            timeout=JUDGE_TIMEOUT,
            retries=0,  # metered: every repeat is a decision made by the caller
        )
    except http.UpstreamNotFound as exc:
        raise JudgeRefused(
            f"The judge does not serve model {judge_model()!r}; set JUDGE_MODEL to a "
            f"current one."
        ) from exc
    except (http.UpstreamUnauthorized, http.UpstreamForbidden) as exc:
        raise JudgeRefused("The judge API key was refused.") from exc
    except http.UpstreamClientError as exc:
        # Gemini answers 400 for a malformed key as well as a malformed request;
        # either way, waiting will not change the answer.
        raise JudgeRefused(f"The judge refused the request: {exc}") from exc
    except (http.UpstreamRateLimited, http.UpstreamUnavailable) as exc:
        raise JudgeUnavailable("The judge did not answer.") from exc
    except http.UpstreamError as exc:
        raise JudgeUnavailable(f"The judge could not be reached: {exc}") from exc

    data = response.data if isinstance(response.data, dict) else {}
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise JudgeUnusable("The judge returned no text.") from exc
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise JudgeUnusable("The judge's answer was not JSON.") from exc
    if not isinstance(parsed, dict):
        raise JudgeUnusable("The judge's answer was not a JSON object.")
    return parsed


# ── the rubric ─────────────────────────────────────────────────────────────

FAITHFULNESS_SYSTEM = """\
You are an evaluator. You check a dependency-remediation report against the \
evidence its author was given, claim by claim. You never use outside knowledge.

You are given MEASURED DATA (facts a scanner recorded about the dependency), \
SOURCE (the passages the author was shown; it may be empty), and REPORT.

1. List every claim REPORT makes: each recommended version, replacement \
package, migration step, breaking-change assertion, and statement about what a \
release contains or fixes. Restating a fact from MEASURED DATA is a claim too.
2. For each claim decide "supported": true only if MEASURED DATA or SOURCE \
states it or directly entails it. Your own knowledge of the package does not \
count, even if you are sure the claim is true.
3. For each claim decide "core": true for the recommended version, the \
replacement package, and any assertion that something breaks; false for \
peripheral remarks.
4. A statement that there is not enough information to recommend something is \
supported when SOURCE is indeed empty or does not address it.

Answer with one JSON object and nothing else:
{"claims": [{"claim": string, "core": boolean, "supported": boolean, \
"evidence": string or null}], "verdict": "faithful" | "minor_unsupported" | \
"major_unsupported", "note": string}
"evidence" is the SOURCE passage id, "measured", or null. "note" names the \
unsupported claim that matters most, or is empty.
"""

#: decisions §13.17, step 1. WP-9 found the rubric-v1 judge lenient in four
#: ways (kappa 0.134 against a human on 50 items), and each change below closes
#: one of them; nothing else differs from rubric-v1:
#:
#: * rule 2 adds that a claim contradicted by MEASURED DATA or SOURCE is
#:   unsupported, even if the other is silent (misdescribed evidence);
#: * rule 3 makes an assurance that an upgrade is safe, compatible or needs no
#:   code changes a breaking-change claim, and so core;
#: * rule 4 checks MEASURED DATA as well as SOURCE before accepting "not enough
#:   information" or "no successor is known" — rubric-v1 accepted either
#:   whenever SOURCE was empty, so a deprecation message naming the successor
#:   went unread (items 025 and 026);
#: * rule 5 is new: "fixes all known vulnerabilities" is supported only when
#:   every advisory in MEASURED DATA has a fixed version at or below the target.
FAITHFULNESS_SYSTEM_V2 = """\
You are an evaluator. You check a dependency-remediation report against the \
evidence its author was given, claim by claim. You never use outside knowledge.

You are given MEASURED DATA (facts a scanner recorded about the dependency), \
SOURCE (the passages the author was shown; it may be empty), and REPORT.

1. List every claim REPORT makes: each recommended version, replacement \
package, migration step, breaking-change assertion, and statement about what a \
release contains or fixes. Restating a fact from MEASURED DATA is a claim too, \
and so is any description of what SOURCE or MEASURED DATA says.
2. For each claim decide "supported": true only if MEASURED DATA or SOURCE \
states it or directly entails it. A claim that MEASURED DATA or SOURCE \
contradicts is unsupported, even if the other is silent. Your own knowledge of \
the package does not count, even if you are sure the claim is true.
3. For each claim decide "core": true for the recommended version, the \
replacement package, and any assertion that something breaks or does not \
break. An assurance that an upgrade is safe, compatible, non-breaking or needs \
no code changes is a breaking-change assertion, so it is core. False for \
peripheral remarks.
4. A statement that there is not enough information to recommend something, \
or that no successor or fix is known, is supported only when neither SOURCE \
nor MEASURED DATA provides it. Read MEASURED DATA's deprecation message and \
advisories before accepting it: if either names a successor or a fixed \
version, the statement is unsupported.
5. A claim that the recommendation fixes all known vulnerabilities is supported \
only if every advisory in MEASURED DATA has a fixed version at or below the \
recommended version. An advisory with no recorded fix, or one fixed above the \
recommended version, makes the claim unsupported.

Answer with one JSON object and nothing else:
{"claims": [{"claim": string, "core": boolean, "supported": boolean, \
"evidence": string or null}], "verdict": "faithful" | "minor_unsupported" | \
"major_unsupported", "note": string}
"evidence" is the SOURCE passage id, "measured", or null. "note" names the \
unsupported claim that matters most, or is empty.
"""

#: Every faithfulness rubric by version. rubric-v1 stays as it was signed, so
#: WP-8's cached verdicts still match their keys.
RUBRICS: dict[str, str] = {
    RUBRIC_VERSION: FAITHFULNESS_SYSTEM,
    RUBRIC_V2: FAITHFULNESS_SYSTEM_V2,
}

RELEVANCE_SYSTEM = """\
You are an evaluator. For each PASSAGE, decide whether it helps answer \
QUESTION about the named dependency: it must bear on the remediation itself — \
which release fixes the problem, what replaces the package, or what changes \
when moving. A passage that is merely about the same package is not relevant.

Answer with one JSON object and nothing else:
{"passages": [{"id": string, "relevant": boolean}]}
List every passage id exactly as given.
"""


def verdict_from_claims(claims: list[dict]) -> str:
    """File B's rule: a core claim unsupported, or more than one peripheral, is major."""
    unsupported = [claim for claim in claims if not claim.get("supported")]
    if any(claim.get("core") for claim in unsupported):
        return MAJOR
    if len(unsupported) > 1:
        return MAJOR
    if len(unsupported) == 1:
        return MINOR
    return FAITHFUL


def _block(name: str, value) -> str:
    return f"BEGIN {name}\n{value}\nEND {name}\n"


def faithfulness_prompt(target: dict, generation: dict, shown: list[dict]) -> str:
    source = (
        "\n\n".join(
            f"[{chunk.get('chunk_id')}] from {chunk.get('source_path')}\n{chunk.get('text')}"
            for chunk in shown
        )
        or "(empty: the author was shown no passages)"
    )
    report = json.dumps(
        {"summary_md": generation.get("summary_md"), "fixes": generation.get("fixes")},
        ensure_ascii=False,
        indent=1,
    )
    return (
        _block(
            "MEASURED DATA",
            json.dumps(target, ensure_ascii=False, indent=1, sort_keys=True),
        )
        + _block("SOURCE", source)
        + _block("REPORT", report)
    )


def relevance_question(item: dict) -> str:
    """Neutral about the answer: the ground truth is never in the question."""
    package = item["package"]
    version = item["target"].get("current_version") or "the current version"
    if item["case_type"] == "deprecation_replacement":
        return f"What should replace {package}, and what does migrating away from it involve?"
    return (
        f"Which release of {package} fixes the vulnerabilities affecting {version}, "
        f"and what changes when upgrading to it?"
    )


def relevance_prompt(item: dict, chunks: list[dict]) -> str:
    passages = "\n\n".join(
        f"[{chunk.get('chunk_id')}]\n{chunk.get('text')}" for chunk in chunks
    )
    return (
        f"QUESTION: {relevance_question(item)}\nDEPENDENCY: {item['ecosystem']} "
        f"package {item['package']}\n\n" + _block("PASSAGES", passages)
    )


# ── the cache ──────────────────────────────────────────────────────────────


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def cache_key(task: str, item_id: str, condition: str, inputs) -> str:
    return _digest([task, item_id, condition, judge_version(), _digest(inputs)])


@dataclass
class JudgeCache:
    path: Path

    def __post_init__(self) -> None:
        self._entries = {
            row["key"]: row for row in read_jsonl(self.path) if row.get("key")
        }

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def put(self, key: str, entry: dict) -> None:
        entry = {"key": key, **entry}
        append_jsonl(self.path, entry, fsync=True)
        self._entries[key] = entry


@dataclass
class Judge:
    """Paced, cached judging of one run's records."""

    cache: JudgeCache
    complete: object = None
    pace_seconds: float = DEFAULT_PACE_SECONDS
    calls: int = 0
    hits: int = 0
    _last: float = 0.0

    def _ask(self, system_prompt: str, user_prompt: str) -> dict:
        if self._last and self.pace_seconds:
            wait = self.pace_seconds - (time.monotonic() - self._last)
            if wait > 0:
                _sleep(wait)
        self._last = time.monotonic()
        complete = self.complete or complete_judge
        for wait in (*UNAVAILABLE_BACKOFF_SECONDS, None):
            self.calls += 1
            try:
                return complete(system_prompt, user_prompt)
            except JudgeUnusable:
                # One repair attempt, as the generator gets (§10 Phase 7): a
                # formatting slip is cheaper to retry than to lose.
                self.calls += 1
                return complete(
                    system_prompt, user_prompt + "\nAnswer again: one JSON object only."
                )
            except JudgeUnavailable:
                if wait is None:
                    raise
                logger.info("The judge did not answer; retrying in %.0fs.", wait)
                _sleep(wait)
        raise JudgeUnavailable("unreachable")  # pragma: no cover - returns or raises

    def faithfulness(self, record: dict, item: dict) -> dict:
        shown_ids = set(record.get("shown_chunk_ids") or [])
        shown = [
            c
            for c in record.get("retrieved") or []
            if str(c.get("chunk_id")) in shown_ids
        ]
        inputs = {
            "target": item["target"],
            "generation": record.get("generation") or {},
            "shown": shown,
        }
        key = cache_key(FAITHFULNESS, record["item_id"], record["condition"], inputs)
        cached = self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        answer = self._ask(
            faithfulness_system(),
            faithfulness_prompt(item["target"], inputs["generation"], shown),
        )
        claims = [c for c in answer.get("claims") or [] if isinstance(c, dict)]
        stated = answer.get("verdict") if answer.get("verdict") in VERDICTS else None
        entry = {
            "task": FAITHFULNESS,
            "item_id": record["item_id"],
            "condition": record["condition"],
            "judge_version": judge_version(),
            "claims": claims,
            "verdict": verdict_from_claims(claims),
            "stated_verdict": stated,
            "note": str(answer.get("note") or ""),
        }
        self.cache.put(key, entry)
        return entry

    def relevance(self, record: dict, item: dict) -> dict | None:
        """Precision@k over everything retrieved; None when nothing was."""
        chunks = record.get("retrieved") or []
        if not chunks:
            return None
        inputs = {"question": relevance_question(item), "chunks": chunks}
        key = cache_key(RELEVANCE, record["item_id"], record["condition"], inputs)
        cached = self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        answer = self._ask(RELEVANCE_SYSTEM, relevance_prompt(item, chunks))
        verdicts = {
            str(entry.get("id")): bool(entry.get("relevant"))
            for entry in answer.get("passages") or []
            if isinstance(entry, dict)
        }
        ids = [str(chunk.get("chunk_id")) for chunk in chunks]
        relevant = [verdicts.get(chunk_id, False) for chunk_id in ids]
        entry = {
            "task": RELEVANCE,
            "item_id": record["item_id"],
            "condition": record["condition"],
            "judge_version": judge_version(),
            "relevant": dict(zip(ids, relevant, strict=True)),
            "unjudged": [chunk_id for chunk_id in ids if chunk_id not in verdicts],
            "precision_at_k": sum(relevant) / len(relevant),
            "k": len(relevant),
        }
        self.cache.put(key, entry)
        return entry

    def judge(self, record: dict, item: dict) -> dict:
        """Both tasks for one record. A failed generation has nothing to judge."""
        if record.get("status") != "ok":
            return {}
        return {
            FAITHFULNESS: self.faithfulness(record, item),
            RELEVANCE: self.relevance(record, item),
        }


def _sleep(seconds: float) -> None:
    time.sleep(seconds)
