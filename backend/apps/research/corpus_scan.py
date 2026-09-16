"""`scan_corpus` — the corpus, measured by the code the product ships.

§10 Phase 11 states the point in one sentence: "The adapter-and-scorer
identity with the product is the point: it is what lets S1 claim the corpus
measures the shipped formula rather than a research reimplementation of it."

That claim is only worth making if it is literally true, so this module
contains no parsing, no registry logic, no severity arithmetic and no formula.
It reads the manifests `build_corpus` recorded and then calls, in order:

    adapters.adapter_for_path  ->  adapter.parse  ->  scanner.enrich_from_registries
      ->  scanner.enrich_from_osv  ->  scanner.derive_signals
      ->  scoring.score_occurrence / is_flagged  ->  scoring.roll_up / classify

Every one of those is the function a live scan calls, imported rather than
copied. What is different is only where the answer is written.

**Nothing operational is written, and the guard is below the ORM** (D10). A
live scan's measurement lands in `dependency_occurrences` and is summarised
into `dependency_history` afterwards by `history.record_scan`. A corpus scan
has no `scan_runs` row, no `repositories` row and no user, so it writes the
history rows directly — and `guards.no_operational_writes` refuses any
statement that touches a table outside §5.1's permanent three, including one
issued by code nobody here wrote.

**`github_user_id` is the repository's owner on GitHub.** On a live row those
columns name the RepoVitals user who ran the scan. There is no such person
here, and the honest analogue of "who does this repository belong to" is the
GitHub account that owns it. Nothing joins on them across the two sources —
every product read filters `data_source='live_scan'` first (§10.9) — and S1
needs to be able to ask how many corpus repositories share an owner.

**Resume is idempotent against the database, not only against the file.** §10
Phase 11's acceptance is "kill -9 mid-run -> --resume completes without
duplicate rows". A checkpoint line written after the commit is the normal
path; a process killed between the two would leave rows with no line. So
`--resume` also asks the database which repositories already have a
`corpus_scan` row for this snapshot date, and the checkpoint is only a
fast-path and a record of the failures.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from apps.common import http
from apps.scanning import adapters, osv
from apps.scanning.scanner import (
    MAX_LOCKFILE_BYTES,
    MAX_MANIFEST_BYTES,
    ManifestPlan,
    PooledOccurrence,
    ScanFailed,
    derive_signals,
    enrich_from_osv,
    enrich_from_registries,
)
from apps.scoring.engine import classify, is_flagged, roll_up, score_occurrence
from apps.scoring.signals import signals_for
from apps.scoring.weights import WeightSet, active_weights

from .corpus import BLOB_DIRNAME, append_jsonl, read_jsonl
from .github import ResearchClient
from .guards import no_operational_writes
from .history import INSERT_BATCH
from .models import DataSource, DependencyHistory, ScanHistory

logger = logging.getLogger(__name__)

#: Written beside `corpus_manifest.json`. One JSON object per repository
#: attempted, appended and flushed as each finishes.
CHECKPOINT_FILENAME = "scan_checkpoint.jsonl"
#: Written at the end of a run: WP-5's "completion report", which the teammate
#: is asked to read and sign off.
REPORT_FILENAME = "scan_corpus_report.md"

STATUS_OK = "ok"
STATUS_FAILED = "failed"


class CorpusManifestError(Exception):
    """`corpus_manifest.json` is absent or is not one."""


# ── the corpus manifest ────────────────────────────────────────────────────


@dataclass(frozen=True)
class CorpusRepository:
    """One admitted repository, as `build_corpus` recorded it."""

    full_name: str
    github_repo_id: int
    owner_login: str
    owner_id: int
    default_branch: str
    ecosystem: str
    cell: str
    sampling_weight: float | None
    manifests: tuple[dict, ...]

    @property
    def name(self) -> str:
        return self.full_name.partition("/")[2] or self.full_name


@dataclass(frozen=True)
class Corpus:
    path: Path
    run_date: str
    seed: int | None
    repositories: tuple[CorpusRepository, ...]

    @property
    def directory(self) -> Path:
        return self.path.parent


def load_corpus(path: Path) -> Corpus:
    """Read `corpus_manifest.json`, or refuse with a sentence naming the file."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CorpusManifestError(
            f"No corpus manifest at {path}. Run `manage.py build_corpus` first "
            f"(WP-4), or point --corpus at the one the teammate delivered."
        ) from exc
    except json.JSONDecodeError as exc:
        raise CorpusManifestError(f"{path} is not valid JSON: {exc}") from exc

    rows = document.get("repositories")
    if not isinstance(rows, list):
        raise CorpusManifestError(
            f"{path} has no 'repositories' array; it is not a corpus manifest."
        )

    repositories = tuple(
        CorpusRepository(
            full_name=str(row.get("full_name") or ""),
            github_repo_id=int(row.get("github_repo_id") or 0),
            owner_login=str(row.get("owner_login") or ""),
            owner_id=int(row.get("owner_id") or 0),
            default_branch=str(row.get("default_branch") or "main"),
            ecosystem=str(row.get("ecosystem") or ""),
            cell=str(row.get("cell") or ""),
            sampling_weight=row.get("sampling_weight"),
            manifests=tuple(row.get("manifests") or ()),
        )
        for row in rows
        if isinstance(row, dict)
    )
    return Corpus(
        path=path,
        run_date=str(document.get("run_date") or ""),
        seed=document.get("seed"),
        repositories=repositories,
    )


# ── reading one repository's manifests ─────────────────────────────────────


def _plan_from_record(record: dict) -> ManifestPlan | None:
    """Rebuild the scanner's plan from what `build_corpus` wrote down.

    The adapter is looked up by path through `adapters.adapter_for_path`, the
    same call the live scanner makes — including its vendor-directory
    exclusion, so a manifest that has since moved under `node_modules/` is
    dropped here exactly as it would be in a product scan.

    Lockfile inheritance is *replayed*, not re-derived: `build_corpus` ran
    `adopt_workspace_lockfiles` with the bytes in hand and recorded the answer.
    """
    path = str(record.get("path") or "")
    adapter = adapters.adapter_for_path(path)
    if adapter is None:
        return None
    return ManifestPlan(
        adapter=adapter,
        path=path,
        sha=str(record.get("sha") or ""),
        size=int(record.get("size") or 0),
        lockfile_path=record.get("lockfile_path"),
        lockfile_sha=record.get("lockfile_sha"),
        lockfile_size=int(record.get("lockfile_size") or 0),
    )


def _read_manifest(
    repository: CorpusRepository,
    record: dict,
    plan: ManifestPlan,
    corpus_dir: Path,
    client: ResearchClient,
) -> bytes | None:
    """The manifest bytes: from the archive if they are there, else from GitHub.

    `build_corpus` already fetched and stored every manifest it verified, so
    the common path costs no request and no quota — and it is the *same bytes*
    the admission decision was made on, which matters more than the saving: a
    repository that changed between WP-4 and WP-5 would otherwise be scanned
    as something other than the thing that was sampled.

    The GitHub fallback exists for a manifest recorded without an archive path
    (an older corpus, or one whose blob directory was not handed over).
    """
    blob_path = record.get("blob_path")
    if blob_path:
        archived = corpus_dir / blob_path
        if archived.exists():
            content = archived.read_bytes()
            return content if len(content) <= MAX_MANIFEST_BYTES else None

    fallback = corpus_dir / BLOB_DIRNAME / plan.sha[:2] / plan.sha
    if fallback.exists():
        content = fallback.read_bytes()
        return content if len(content) <= MAX_MANIFEST_BYTES else None

    return client.blob(
        repository.owner_login, repository.name, plan.sha, MAX_MANIFEST_BYTES
    )


# ── scanning one repository ────────────────────────────────────────────────


@dataclass
class RepositoryScan:
    """One corpus repository's measurement, before anything is written."""

    repository: CorpusRepository
    pool: list[PooledOccurrence] = field(default_factory=list)
    manifests_read: int = 0
    manifests_skipped: int = 0


def measure(
    repository: CorpusRepository,
    corpus_dir: Path,
    client: ResearchClient,
    *,
    registry_memo: dict | None = None,
    osv_client: osv.OsvClient | None = None,
) -> RepositoryScan:
    """Parse and enrich one repository — the product's pipeline, no database.

    Raises `ScanFailed` for the two conditions the live scanner raises it for
    (every registry lookup unavailable, OSV unreachable), because they mean the
    same thing here: the run is measuring the network rather than the corpus,
    and a repository recorded clean on that basis is worse than one recorded
    failed.
    """
    scan = RepositoryScan(repository=repository)

    plans: list[ManifestPlan] = []
    sources: dict[str, bytes] = {}
    for record in repository.manifests:
        plan = _plan_from_record(record)
        if plan is None:
            scan.manifests_skipped += 1
            continue
        try:
            manifest_bytes = _read_manifest(repository, record, plan, corpus_dir, client)
        except http.UpstreamError:
            manifest_bytes = None
        if manifest_bytes is None:
            scan.manifests_skipped += 1
            continue
        plans.append(plan)
        sources[plan.path] = manifest_bytes

    if not plans:
        raise ScanFailed("None of this repository's recorded manifests could be read.")

    # One fetch per distinct lockfile sha, exactly as `run_scan` does — a
    # workspaces monorepo points every member at the same root lockfile.
    lockfiles: dict[str, bytes | None] = {}
    for plan in plans:
        manifest_bytes = sources[plan.path]

        lockfile_bytes = None
        if plan.lockfile_sha and plan.lockfile_size <= MAX_LOCKFILE_BYTES:
            if plan.lockfile_sha not in lockfiles:
                try:
                    lockfiles[plan.lockfile_sha] = client.blob(
                        repository.owner_login,
                        repository.name,
                        plan.lockfile_sha,
                        MAX_LOCKFILE_BYTES,
                    )
                except http.UpstreamError:
                    lockfiles[plan.lockfile_sha] = None
            lockfile_bytes = lockfiles[plan.lockfile_sha]
        if lockfile_bytes is None:
            # Same rule as `run_scan`: claiming a lockfile that was never read
            # would make `resolution` say `lockfile` over an approximation.
            plan.lockfile_path = None

        try:
            specs = plan.adapter.parse(manifest_bytes, lockfile_bytes)
        except adapters.ManifestParseError:
            scan.manifests_skipped += 1
            continue

        scan.manifests_read += 1
        scan.pool.extend(
            PooledOccurrence(plan=plan, ecosystem=plan.adapter.ecosystem, spec=spec)
            for spec in specs
        )

    if not scan.manifests_read:
        raise ScanFailed("Every recorded manifest failed to parse.")

    enrich_from_registries(scan.pool, memo=registry_memo)
    enrich_from_osv(scan.pool, client=osv_client)
    return scan


# ── scoring and writing ────────────────────────────────────────────────────


@dataclass
class ScoredRepository:
    risk_score: Decimal
    classification: str
    dependency_count: int
    flagged_count: int
    assessed_count: int
    unassessable_count: int
    ecosystems: str
    rows: list[DependencyHistory]


def score(scan: RepositoryScan, weights: WeightSet) -> ScoredRepository:
    """§5.2 per occurrence and §5.3 over the repository, through the shipped engine.

    The `dependency_history` rows are built but not saved: the caller writes
    them inside one transaction with the `scan_history` row they belong to, so
    a failure cannot leave a parent with half its occurrences.
    """
    penalties: list[Decimal] = []
    flagged = 0
    unassessable = 0
    rows: list[DependencyHistory] = []
    ecosystems: set[str] = set()

    for pooled in scan.pool:
        ecosystems.add(pooled.ecosystem)
        signals = derive_signals(pooled)

        component: Decimal | None = None
        if signals.is_unassessable:
            # §5.2: not scored, not flagged, out of every denominator. Recorded
            # anyway — §5.1 says every occurrence, and a corpus that dropped
            # the unassessable ones could not report the rate at which this
            # product cannot answer, which is one of its own findings.
            unassessable += 1
        else:
            # `signals_for` is duck-typed over §5.1's four column names, and
            # `OccurrenceSignals` carries exactly those — so this is the same
            # call the live pipeline makes against a stored row.
            formula_input = signals_for(signals)
            result = score_occurrence(formula_input, weights, pooled.ecosystem)
            component = result.score
            penalties.append(result.penalty)
            flagged += int(is_flagged(formula_input, weights))

        rows.append(
            DependencyHistory(
                ecosystem=pooled.ecosystem,
                package_name=pooled.spec.name,
                manifest_path=pooled.plan.path,
                dependency_group=signals.dependency_group,
                declared_specifier=signals.declared_specifier,
                resolved_version=signals.resolved_version,
                resolution=signals.resolution,
                latest_version=signals.latest_version,
                staleness_days=signals.staleness_days,
                versions_behind_major=signals.versions_behind_major,
                versions_behind_minor=signals.versions_behind_minor,
                versions_behind_patch=signals.versions_behind_patch,
                is_deprecated=signals.is_deprecated,
                deprecation_reason=signals.deprecation_reason,
                vulnerability_count=signals.vulnerability_count,
                highest_severity=signals.highest_severity,
                cvss_max=signals.cvss_max,
                is_unassessable=signals.is_unassessable,
                risk_component_score=component,
            )
        )

    repository = roll_up(penalties, weights)
    return ScoredRepository(
        risk_score=repository.score,
        classification=classify(repository.score, weights),
        dependency_count=len(rows),
        flagged_count=flagged,
        assessed_count=len(penalties),
        unassessable_count=unassessable,
        ecosystems=",".join(sorted(ecosystems)),
        rows=rows,
    )


def persist(
    repository: CorpusRepository,
    scored: ScoredRepository,
    weights: WeightSet,
    snapshot_date: date,
) -> ScanHistory:
    """One `scan_history` row and its `dependency_history` rows, in one transaction.

    All-or-nothing for the same reason `scanner._persist` is: a parent claiming
    forty dependencies over a table holding eleven of them is a corpus row that
    silently under-reports, and nothing downstream could tell.
    """
    with transaction.atomic():
        entry = ScanHistory.objects.create(
            # No `scan_runs` row exists to name. The column is nullable for
            # exactly this (§5.1: traceability only, not a foreign key).
            source_scan_id=None,
            github_user_id=repository.owner_id,
            github_username=repository.owner_login,
            github_repo_id=repository.github_repo_id,
            repo_full_name=repository.full_name,
            ecosystems=scored.ecosystems or repository.ecosystem,
            risk_score=scored.risk_score,
            classification=scored.classification,
            dependency_count=scored.dependency_count,
            flagged_dependency_count=scored.flagged_count,
            scoring_formula_version=weights.version,
            data_source=DataSource.CORPUS_SCAN.value,
            snapshot_date=snapshot_date,
            sampling_weight=repository.sampling_weight,
            scanned_at=datetime.now(UTC),
        )
        for row in scored.rows:
            row.scan_history = entry
        DependencyHistory.objects.bulk_create(scored.rows, batch_size=INSERT_BATCH)
    return entry


# ── the run ────────────────────────────────────────────────────────────────


@dataclass
class Checkpoint:
    """One line per repository attempted, flushed and fsynced as it lands.

    Durable at the line, not at process exit: the process this protects
    against is the one that does not exit. `fsync` after every line is a real
    cost at a thousand repositories and a trivial one against the minutes each
    repository takes over the network — and unlike the builder's checkpoint,
    each line here stands for a database transaction that has already
    committed.
    """

    path: Path

    def read(self) -> list[dict]:
        return read_jsonl(self.path)

    def append(self, payload: dict) -> None:
        append_jsonl(self.path, payload, fsync=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


@dataclass
class RunOutcome:
    """What one `scan_corpus` invocation did, for the completion report."""

    snapshot_date: date
    weights_version: str
    attempted: int = 0
    scanned: int = 0
    skipped: int = 0
    failed: int = 0
    occurrences: int = 0
    unassessable: int = 0
    flagged: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    report_path: Path | None = None


def already_scanned(snapshot_date: date) -> set[int]:
    """GitHub repo ids that already hold a corpus row for this snapshot date.

    The half of `--resume` that survives a `kill -9` between the commit and
    the checkpoint write. Queried once per run rather than per repository: a
    thousand ids is a set, and a query per repository would be a thousand
    round trips against a database that is on the same laptop but still.
    """
    return set(
        ScanHistory.objects.filter(
            data_source=DataSource.CORPUS_SCAN.value, snapshot_date=snapshot_date
        ).values_list("github_repo_id", flat=True)
    )


def scan_corpus(
    *,
    corpus: Corpus,
    client: ResearchClient,
    weights: WeightSet | None = None,
    snapshot_date: date | None = None,
    resume: bool = False,
    only: str | None = None,
    limit: int | None = None,
    progress=None,
) -> RunOutcome:
    """Scan and score every admitted repository, writing research rows only.

    One registry memo and one OSV client for the whole run (D14: the corpus is
    a cross-section as of one date, so one observation per package is the more
    consistent measurement as well as the cheaper one).
    """
    weights = weights or active_weights()
    snapshot_date = snapshot_date or datetime.now(UTC).date()
    checkpoint = Checkpoint(corpus.directory / CHECKPOINT_FILENAME)
    if not resume:
        checkpoint.clear()

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    targets = list(corpus.repositories)
    if only:
        targets = [row for row in targets if row.full_name == only]
        if not targets:
            raise CorpusManifestError(
                f"{only!r} is not in {corpus.path.name}. `--repo` names a "
                f"repository the corpus admitted, as `owner/name`."
            )

    done_ids: set[int] = set()
    if resume:
        done_ids = already_scanned(snapshot_date)
        done_ids |= {
            int(row["github_repo_id"])
            for row in checkpoint.read()
            if row.get("status") == STATUS_OK and row.get("github_repo_id")
        }

    outcome = RunOutcome(snapshot_date=snapshot_date, weights_version=weights.version)
    registry_memo: dict = {}
    osv_client = osv.OsvClient()

    for repository in targets:
        if limit is not None and outcome.attempted >= limit:
            break
        if repository.github_repo_id in done_ids:
            outcome.skipped += 1
            continue

        outcome.attempted += 1
        try:
            measured = measure(
                repository,
                corpus.directory,
                client,
                registry_memo=registry_memo,
                osv_client=osv_client,
            )
            scored = score(measured, weights)
            entry = persist(repository, scored, weights, snapshot_date)
        except (ScanFailed, http.UpstreamError) as exc:
            # One repository's bad afternoon is not the run's. A corpus of a
            # thousand public repositories always contains some that were
            # renamed, emptied or made private between WP-4 and WP-5; WP-5's
            # checklist expects a handful and asks the teammate to flag fifty.
            outcome.failed += 1
            outcome.failures.append((repository.full_name, str(exc)))
            checkpoint.append(
                {
                    "full_name": repository.full_name,
                    "github_repo_id": repository.github_repo_id,
                    "status": STATUS_FAILED,
                    "error": str(exc),
                    "at": datetime.now(UTC).isoformat(),
                }
            )
            say(f"{repository.full_name}: failed - {exc}")
            continue

        outcome.scanned += 1
        outcome.occurrences += scored.dependency_count
        outcome.unassessable += scored.unassessable_count
        outcome.flagged += scored.flagged_count
        checkpoint.append(
            {
                "full_name": repository.full_name,
                "github_repo_id": repository.github_repo_id,
                "status": STATUS_OK,
                "scan_history_id": str(entry.pk),
                "risk_score": str(scored.risk_score),
                "classification": scored.classification,
                "occurrences": scored.dependency_count,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        say(
            f"{repository.full_name}: {scored.risk_score} ({scored.classification}) "
            f"over {scored.dependency_count} occurrence(s)"
        )

    outcome.report_path = corpus.directory / REPORT_FILENAME
    outcome.report_path.write_text(
        completion_report(corpus, outcome, client), encoding="utf-8"
    )
    return outcome


def run_guarded(**kwargs) -> RunOutcome:
    """`scan_corpus` with D10's write guard around the whole of it."""
    with no_operational_writes():
        return scan_corpus(**kwargs)


def completion_report(corpus: Corpus, outcome: RunOutcome, client: ResearchClient) -> str:
    """WP-5's completion report — the review checklist, already computed.

    File B asks the teammate to confirm four things: that at least 95% of the
    corpus completed, that the scored-occurrence count is in range, that the
    score distribution spreads, and that the unassessable rate is reported and
    not dominant. Three of them are numbers and are printed here; the fourth
    needs the charts, and the report says so and names the command.
    """
    total = len(corpus.repositories)
    completed = ScanHistory.objects.filter(
        data_source=DataSource.CORPUS_SCAN.value, snapshot_date=outcome.snapshot_date
    ).count()
    coverage = (completed / total) if total else 0.0
    unassessable_rate = (
        outcome.unassessable / outcome.occurrences if outcome.occurrences else 0.0
    )

    lines = [
        "# Corpus scan completion report",
        "",
        "Generated by `manage.py scan_corpus` (§10 Phase 11, D10/D14). Every",
        "number is counted from the research database this run wrote to.",
        "",
        "## This run",
        "",
        f"- Corpus manifest: `{corpus.path.name}` ({total} admitted repositories)",
        f"- Snapshot date (`snapshot_date` on every row written): `{outcome.snapshot_date.isoformat()}`",
        f"- Weights version: `{outcome.weights_version}`",
        f"- Attempted: {outcome.attempted} · scanned: {outcome.scanned} · "
        f"failed: {outcome.failed} · already done and skipped: {outcome.skipped}",
        f"- GitHub calls: {client.rest_calls} REST, {client.search_calls} search",
        f"- Rate-limit pauses: {client.budget.pauses} "
        f"({client.budget.waited_seconds:.0f}s waited)",
        "",
        "## WP-5 review checklist",
        "",
        f"- **Corpus coverage:** {completed} of {total} repositories have a "
        f"`corpus_scan` row for this date ({coverage:.0%})"
        + ("  ← below 95%, flag it" if total and coverage < 0.95 else ""),
        f"- **Scored occurrences written this run:** {outcome.occurrences}",
        f"- **Unassessable rate:** {unassessable_rate:.1%} of occurrences "
        f"({outcome.unassessable} of {outcome.occurrences})",
        f"- **Flagged occurrences:** {outcome.flagged}",
        "- **Score distribution:** ask the developer to run `manage.py "
        "corpus_report`; the histograms are the artefact this checklist item "
        "wants, and a corpus that lands almost entirely in one class is worth "
        "flagging.",
        "",
    ]

    if outcome.failures:
        lines += [
            "## Repositories that did not complete",
            "",
            "Renamed, deleted, emptied or made private between the two runs is",
            "the usual cause and is expected at this scale. Re-running with",
            "`--resume` retries only these.",
            "",
            "| Repository | Reason |",
            "|---|---|",
        ]
        for full_name, error in outcome.failures[:100]:
            lines.append(f"| `{full_name}` | {error} |")
        if len(outcome.failures) > 100:
            lines.append(f"| … | and {len(outcome.failures) - 100} more |")
        lines.append("")

    lines += [
        "## What these rows are",
        "",
        "- `data_source='corpus_scan'`, `snapshot_date` set, `sampling_weight`",
        "  carried from the frame. No product surface reads them: every product",
        "  query filters `live_scan` positively (§10.9).",
        "- Scored by the same adapters, the same enrichment and the same formula",
        "  the live product runs — imported, not reimplemented (§10 Phase 11).",
        "- A **cross-section as of the snapshot date** (D14). Every repository is",
        "  scanned once. Nothing here supports a claim about change over time.",
        "",
    ]
    return "\n".join(lines)


def outcome_as_dict(outcome: RunOutcome) -> dict:
    payload = asdict(outcome)
    payload["snapshot_date"] = outcome.snapshot_date.isoformat()
    payload["report_path"] = str(outcome.report_path) if outcome.report_path else None
    return payload
