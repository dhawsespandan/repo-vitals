"""`run_experiment`: one condition over the labelled set, a day at a time.

§10 Phase 13: "`run_experiment --condition A|B|C|D --items … --resume`: per item
stores generation, retrieved chunks, branch, timings, model ids ->
`research_data/runs/{run_id}/items.jsonl`; checkpointed; Groq/Gemini pacing
with clean stop at daily caps (multi-day runs are normal)."

**A run is one condition, one labelled set, one model.** The run id is
`{condition}_{labelled-set digest}_{model}`, so re-typing WP-8's command after
a crash or a night's sleep finds the same run and continues it — and a Groq
model retired mid-study (§7.12 has happened once already) starts a *separate*
run rather than quietly mixing two models into one condition of a paired
design. The runner says when another run of the same condition exists.

**Checkpointed per item, durable per line.** Each finished item is one JSON
line, appended and fsynced (§11.7's torn-line rule applies). The last line for
an item wins, so `--retry-failed` can re-run the failures and append their new
results without rewriting history.

**A provider that stops answering ends the day, not the item.** Groq's free
tier stops at a daily token cap, and the client reports that as "did not
answer" after its one retry. Recording the item as failed would put the cap
into the data; so the item is not recorded, and after two consecutive
non-answers the run stops cleanly with a sentence telling the operator to
rerun the same command later. A configuration fault — no key, a rejected key,
a model the provider no longer serves — stops at once, because waiting a day
will not fix it. A payload the model cannot make valid even after the repair
retry *is* a result about the item, and is recorded as `failed`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings

from apps.reports.llm import groq_client
from apps.reports.llm.prompts import GROUNDED_SYSTEM_PROMPT, UNGROUNDED_SYSTEM_PROMPT
from apps.reports.rag import chroma_store
from apps.research.corpus import append_jsonl, read_jsonl
from apps.research.github import ResearchClient, research_token

from . import conditions, driver

logger = logging.getLogger(__name__)

ITEMS_FILENAME = "items.jsonl"
RUN_FILENAME = "run.json"

#: Two non-answers in a row, a cool-down apart, is a provider that has stopped
#: for the day, not a bad item: the client has already retried each once.
STOP_AFTER_UNANSWERED = 2

#: Groq's free tier for the generator: 8,000 tokens a minute (and 1,000
#: requests a day), read off its `x-ratelimit-*` headers on 2026-10-08. A call
#: books its prompt plus the `max_tokens` it asks for, so one generation is
#: ~6,000 tokens against the minute: §5.8's prompt with five chunks is under
#: 3,000, and the client asks for `MAX_OUTPUT_TOKENS`.
FREE_TIER_TOKENS_PER_MINUTE = 8000
TOKENS_PER_CALL = 3000 + groq_client.MAX_OUTPUT_TOKENS

#: Seconds between generations: one call's tokens spread over the minute, so a
#: run stays under the per-minute limit instead of meeting it every other call
#: (decisions §13.14: a three-second pace stopped the first pilot after 7 items).
DEFAULT_PACE_SECONDS = float(-(-60 * TOKENS_PER_CALL // FREE_TIER_TOKENS_PER_MINUTE))

#: After a non-answer, the wait before the same item is asked again: the
#: provider's per-minute window, with a margin.
COOL_DOWN_SECONDS = 65.0

#: Errors that waiting will not fix.
CONFIGURATION_ERRORS = (
    groq_client.LlmNotConfigured,
    groq_client.LlmRefused,
    groq_client.LlmModelUnavailable,
)


class RunError(Exception):
    """A run that cannot start; the message says why."""


def _sleep(seconds: float) -> None:
    """Indirection so tests pace without waiting."""
    time.sleep(seconds)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "model"


def load_items(path: Path) -> tuple[list[dict], str]:
    """The labelled set and its digest, or a refusal naming the problem."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise RunError(
            f"No labelled set at {path}. `extract_ground_truth` writes one."
        ) from exc
    items: list[dict] = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RunError(f"{path.name} line {number} is not JSON.") from exc
        missing = [
            key
            for key in (
                "item_id",
                "ecosystem",
                "package",
                "case_type",
                "target",
                "context_rows",
            )
            if key not in item
        ]
        if missing:
            raise RunError(f"{path.name} line {number} lacks {', '.join(missing)}.")
        items.append(item)
    ids = [item["item_id"] for item in items]
    if len(ids) != len(set(ids)):
        raise RunError(f"{path.name} lists an item twice.")
    if not items:
        raise RunError(f"{path.name} is empty.")
    return items, hashlib.sha256(raw).hexdigest()


def run_id_for(condition: str, items_digest: str, model: str) -> str:
    return f"{condition}_{items_digest[:8]}_{_slug(model)}"


def latest_records(path: Path) -> dict[str, dict]:
    """The last line written for each item: a retried item's new result wins."""
    found: dict[str, dict] = {}
    for record in read_jsonl(path):
        if record.get("item_id"):
            found[record["item_id"]] = record
    return found


@dataclass
class RunOutcome:
    run_id: str
    condition: str
    directory: Path
    items: int
    attempted: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    stopped: str | None = None
    other_runs: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return self.items - self.skipped - self.completed - self.failed


def _prompt_digest() -> str:
    return hashlib.sha256(
        (GROUNDED_SYSTEM_PROMPT + "\x00" + UNGROUNDED_SYSTEM_PROMPT).encode("utf-8")
    ).hexdigest()[:16]


def run_experiment(
    *,
    items_path: Path,
    condition_name: str,
    out_dir: Path,
    resume: bool = False,
    retry_failed: bool = False,
    limit: int | None = None,
    complete=None,
    pace_seconds: float = DEFAULT_PACE_SECONDS,
    cool_down_seconds: float = COOL_DOWN_SECONDS,
    issue_client_factory=None,
    after_item=None,
    progress=None,
) -> RunOutcome:
    """One condition over the labelled set, resumable at any line.

    `after_item(record)` runs after each recorded item — the judge, in the
    next commit — and may raise to stop the run cleanly the same way an
    unanswering generator does.
    """
    condition = conditions.get(condition_name)
    items, digest = load_items(items_path)
    model = groq_client.active_model()
    run_id = run_id_for(condition.name, digest, model)
    directory = out_dir / run_id
    items_file = directory / ITEMS_FILENAME
    outcome = RunOutcome(
        run_id=run_id, condition=condition.name, directory=directory, items=len(items)
    )

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    prefix = f"{condition.name}_{digest[:8]}_"
    if out_dir.exists():
        outcome.other_runs = sorted(
            entry.name
            for entry in out_dir.iterdir()
            if entry.is_dir() and entry.name.startswith(prefix) and entry.name != run_id
        )
    if items_file.exists() and not resume:
        raise RunError(
            f"Run {run_id} already has results in {items_file}. Re-run with --resume "
            f"to continue it; results are never overwritten."
        )

    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / RUN_FILENAME
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {
            "run_id": run_id,
            "condition": condition.name,
            "description": condition.description,
            "internal": condition.internal,
            "items_file": Path(items_path).name,
            "items_sha256": digest,
            "items": len(items),
            "generator_model": model,
            "temperature": 0,
            "embed_model": getattr(settings, "EMBED_MODEL", ""),
            "k": chroma_store.DEFAULT_K,
            "grounding_min_sim": getattr(settings, "GROUNDING_MIN_SIM", None),
            "grounding_min_chars": getattr(settings, "GROUNDING_MIN_CHARS", None),
            "prompt_digest": _prompt_digest(),
            "started_at": datetime.now(UTC).isoformat(),
            "sessions": [],
        }
    )
    session = {"started_at": datetime.now(UTC).isoformat()}
    manifest["sessions"].append(session)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    records = latest_records(items_file)
    cache = driver.DocsCache(out_dir)
    token = ""
    issue_client = None
    if condition.retrieval:
        token = research_token()
    if conditions.ISSUES in condition.sources:
        issue_client = (issue_client_factory or ResearchClient.from_settings)()

    # The client raises `LlmUnavailable` both when the provider does not answer
    # and when it answers with something that is not a JSON object. Only the
    # first is a reason to stop for the day; the second is a result about the
    # item. Counting the calls that *returned* tells them apart.
    base_complete = complete or groq_client.complete_json
    answered = [0]

    def counted_complete(system_prompt: str, user_prompt: str):
        call = base_complete(system_prompt, user_prompt)
        answered[0] += 1
        return call

    unanswered = 0
    last_call = 0.0
    try:
        for item in items:
            previous = records.get(item["item_id"])
            if previous is not None and not (
                retry_failed and previous.get("status") == driver.STATUS_FAILED
            ):
                outcome.skipped += 1
                continue
            if limit is not None and outcome.attempted >= limit:
                break

            # After a non-answer the same item is asked again, once the
            # provider's minute has passed; a second non-answer ends the day.
            result = None
            while result is None and outcome.stopped is None:
                if last_call and pace_seconds:
                    wait = pace_seconds - (time.monotonic() - last_call)
                    if wait > 0:
                        _sleep(wait)
                last_call = time.monotonic()
                outcome.attempted += 1
                answered_before = answered[0]
                try:
                    result = driver.run_item(
                        item,
                        condition,
                        run_id=run_id,
                        complete=counted_complete,
                        cache=cache,
                        token=token,
                        issue_client=issue_client,
                    )
                except CONFIGURATION_ERRORS as exc:
                    outcome.attempted -= 1
                    outcome.stopped = (
                        f"The generator refused the configuration ({exc}). Waiting "
                        f"will not fix this: check GROQ_API_KEY and GROQ_MODEL, then "
                        f"rerun."
                    )
                except groq_client.LlmError as exc:
                    if (
                        isinstance(exc, groq_client.LlmTruncated)
                        or answered[0] > answered_before
                    ):
                        # The provider answered; what it said was unusable.
                        result = _failed(item, condition, str(exc))
                        continue
                    outcome.attempted -= 1
                    unanswered += 1
                    say(f"{item['item_id']}: the generator did not answer ({unanswered})")
                    if unanswered >= STOP_AFTER_UNANSWERED:
                        outcome.stopped = (
                            "The generator stopped answering — most likely its daily "
                            "limit. Every finished item is saved; rerun the same "
                            "command later and it continues from here."
                        )
                    else:
                        say(
                            f"  waiting {cool_down_seconds:.0f}s for the provider's "
                            f"per-minute window, then asking again"
                        )
                        _sleep(cool_down_seconds)
                except Exception as exc:  # recorded, not swallowed: it is in the data
                    logger.exception(
                        "Item %s failed under condition %s.",
                        item["item_id"],
                        condition.name,
                    )
                    result = _failed(item, condition, f"{type(exc).__name__}: {exc}")
            if result is None:
                break

            unanswered = 0
            record = result.as_json()
            append_jsonl(items_file, record, fsync=True)
            if result.status == driver.STATUS_OK:
                outcome.completed += 1
            else:
                outcome.failed += 1
            say(f"{item['item_id']}: {result.status} ({result.grounding or '-'})")
            if after_item is not None:
                after_item(record, item)
    except StopRun as stop:
        outcome.stopped = str(stop)

    session["finished_at"] = datetime.now(UTC).isoformat()
    session["attempted"] = outcome.attempted
    session["stopped"] = outcome.stopped
    final = latest_records(items_file)
    manifest["completed"] = sum(
        1 for r in final.values() if r.get("status") == driver.STATUS_OK
    )
    manifest["failed"] = sum(
        1 for r in final.values() if r.get("status") == driver.STATUS_FAILED
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return outcome


class StopRun(Exception):
    """Raised by an `after_item` hook to end the session cleanly."""


class JudgeHook:
    """Judge each record as it lands, until the judge stops answering.

    The judge and the generator have separate free-tier budgets, so a judge
    that hits its daily limit switches judging off for the rest of the session
    and generation carries on; `analyze_experiment --judge` fills the gaps
    later from the same cache. A refused key or model is reported the same
    way — judging is optional at generation time, never a reason to lose a
    day's generations.
    """

    def __init__(self, judge, progress=None) -> None:
        self.judge = judge
        self.enabled = True
        self.stopped: str | None = None
        self.progress = progress

    def __call__(self, record: dict, item: dict) -> None:
        from .judge import JudgeRefused, JudgeUnavailable, JudgeUnusable

        if not self.enabled:
            return
        try:
            self.judge.judge(record, item)
        except (JudgeUnavailable, JudgeRefused) as exc:
            self.enabled = False
            self.stopped = (
                f"Judging stopped for this session ({exc}); generations continue. "
                f"Judge the rest later with `analyze_experiment --judge`."
            )
            if self.progress is not None:
                self.progress(self.stopped)
        except JudgeUnusable:
            logger.warning(
                "The judge could not be made to answer for %s.", record["item_id"]
            )


def _failed(item: dict, condition, error: str) -> driver.ItemResult:
    return driver.ItemResult(
        item_id=item["item_id"],
        condition=condition.name,
        ecosystem=item["ecosystem"],
        case_type=item["case_type"],
        status=driver.STATUS_FAILED,
        error=error,
        finished_at=datetime.now(UTC).isoformat(),
    )
