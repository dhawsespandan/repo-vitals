"""The anchor set: do repositories known to be bad classify as at least Medium? (RQ4)

§10 Phase 12: "`anchors.py` + `scan_anchors` command: research-side
current-state scan of the WP-2 CSV (fetch manifests with PAT -> signals ->
score; **no product registration**) -> assert known-bad anchors ≥ Medium;
outlier report." File B: "If the formula doesn't flag the known-bad ones as at
least Medium, it fails regardless of any correlation numbers."

**An anchor is scanned by the corpus pipeline, literally.** The tree is planned
by the scanner's `plan_manifests`, workspace lockfiles are adopted by the
scanner's own rule, the manifests are archived exactly as `build_corpus`
archives them, and the repository is then measured by
`corpus_scan.measure` — the same adapters, registries and OSV enrichment as a
corpus repository and a product scan (§11.1). Nothing is registered, nothing
is written to a database, and the result is a JSON file holding every
occurrence's stored signals, so the anchors can be re-scored offline under
any weights version the way the corpus is (D6).

**A known anchor passes only if the scan actually saw the anchor.** The
2026-09-24 review found that none of the five delivered anchors would have
been visible to the scanner: a transitive dependency, a package not declared
at all, a range scored against the registry's latest release. A repository
like that can still land in Medium for unrelated reasons, and counting it as
a pass would certify the formula on a case it never examined. So each known
anchor is looked for — the named package, at the named version, among the
occurrences the scan read — and a repository that classifies ≥ Medium
without it is reported as an *invalid anchor* (a WP-2 problem), not as a pass.

**Scores are kept out of `scan_anchors`' own output.** File B's anchoring rule
says the teammate's bucket judgements must be formed before seeing the
formula's output. `scan_anchors` prints what a WP-2 reviewer needs — does the
repository exist, is the anchor package there, pinned or locked, flagged and
why — and the numbers appear only in the validation report.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from apps.common import http
from apps.research.corpus import BLOB_DIRNAME, _archive_blob
from apps.research.corpus_scan import CorpusRepository, measure
from apps.research.github import ResearchClient
from apps.scanning import osv
from apps.scanning.adapters import pep440, semver
from apps.scanning.scanner import (
    MAX_MANIFEST_BYTES,
    ScanFailed,
    adopt_workspace_lockfiles,
    derive_signals,
    plan_manifests,
    tree_manifest_paths,
)
from apps.scoring.engine import flag_reasons, score_occurrence
from apps.scoring.normalize import Signals
from apps.scoring.weights import WeightSet

from .panel import CorpusPanel, Occurrence, PanelRepository, score_panel

logger = logging.getLogger(__name__)

#: File B's eight columns, in order, and the 2026-09-24 review's rule 8: "Keep
#: the exact 8-column header ... No extra columns."
COLUMNS: tuple[str, ...] = (
    "repo_url",
    "ecosystem",
    "bucket_seeded",
    "is_known_anchor",
    "anchor_package",
    "approx_dep_count",
    "has_lockfile",
    "why_this_bucket",
)
BUCKETS: tuple[str, ...] = ("healthy", "in_between", "risky")
ECOSYSTEMS: tuple[str, ...] = ("npm", "pypi", "mixed")

#: The class each seeded bucket would ideally land in, for the outlier report.
#: Only the hard rule (known anchors ≥ Medium) is a pass/fail; this mapping is
#: descriptive.
EXPECTED_CLASS = {"healthy": "safe", "in_between": "medium", "risky": "high_alert"}

SCAN_FILENAME = "anchor_scan.json"
SCAN_SCHEMA = "repovitals/anchor_scan@1"

STATUS_OK = "ok"
STATUS_NOT_FOUND = "not_found"
STATUS_NO_MANIFEST = "no_manifest"
STATUS_FAILED = "failed"

#: The verdicts a known anchor can get.
VERDICT_PASS = "pass"  # noqa: S105 - a verdict, not a credential
VERDICT_FAIL = "fail"
VERDICT_INVALID = "anchor_not_observed"
VERDICT_NOT_SCANNED = "not_scanned"

_GITHUB_URL = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})/"
    r"(?P<name>[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$"
)


class AnchorSetError(Exception):
    """`wp2_anchor_set.csv` is not in File B's format; the message says where."""


# ── reading the CSV ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnchorRow:
    line: int
    repo_url: str
    owner: str
    name: str
    ecosystem: str
    bucket: str
    is_known_anchor: bool
    anchor_package: str | None
    anchor_version: str | None
    approx_dep_count: int | None
    has_lockfile: bool
    why: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def _boolean(value: str, column: str, line: int) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    raise AnchorSetError(
        f"Line {line}: {column} must be true or false, not {value!r} (review rule 8)."
    )


def split_anchor_package(text: str) -> tuple[str, str]:
    """`request@2.88.2` -> ("request", "2.88.2"); `@babel/core@7.0.0` keeps its scope."""
    at = text.rfind("@")
    if at <= 0 or at == len(text) - 1:
        raise ValueError(text)
    return text[:at].strip(), text[at + 1 :].strip()


def parse_anchor_set(text: str) -> list[AnchorRow]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration as exc:
        raise AnchorSetError("The anchor set is empty.") from exc
    if tuple(header) != COLUMNS:
        raise AnchorSetError(
            "The header must be exactly File B's eight columns, in order: "
            f"{', '.join(COLUMNS)}. Found: {', '.join(header)}."
        )

    rows: list[AnchorRow] = []
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        if cells[0].lstrip().startswith("#"):
            raise AnchorSetError(
                f"Line {line}: comment lines are not allowed (review rule 8)."
            )
        if len(cells) != len(COLUMNS):
            raise AnchorSetError(
                f"Line {line}: {len(cells)} values for {len(COLUMNS)} columns. A "
                f"comma inside why_this_bucket needs the field quoted."
            )
        values = dict(zip(COLUMNS, (cell.strip() for cell in cells), strict=True))

        match = _GITHUB_URL.match(values["repo_url"])
        if match is None:
            raise AnchorSetError(
                f"Line {line}: {values['repo_url']!r} is not a "
                f"https://github.com/owner/name URL."
            )
        ecosystem = values["ecosystem"].lower()
        if ecosystem not in ECOSYSTEMS:
            raise AnchorSetError(
                f"Line {line}: ecosystem {values['ecosystem']!r} is not one of "
                f"{', '.join(ECOSYSTEMS)}."
            )
        bucket = values["bucket_seeded"].lower().replace("-", "_").replace(" ", "_")
        if bucket not in BUCKETS:
            raise AnchorSetError(
                f"Line {line}: bucket_seeded {values['bucket_seeded']!r} is not one of "
                f"{', '.join(BUCKETS)}."
            )
        known = _boolean(values["is_known_anchor"], "is_known_anchor", line)

        package = version = None
        if values["anchor_package"]:
            try:
                package, version = split_anchor_package(values["anchor_package"])
            except ValueError as exc:
                raise AnchorSetError(
                    f"Line {line}: anchor_package {values['anchor_package']!r} must "
                    f"be name@exact-version (review rule 2f)."
                ) from exc
        if known and package is None:
            raise AnchorSetError(
                f"Line {line}: a known anchor needs anchor_package as "
                f"name@exact-version (File B, WP-2)."
            )

        count: int | None = None
        if values["approx_dep_count"]:
            try:
                count = int(values["approx_dep_count"])
            except ValueError as exc:
                raise AnchorSetError(
                    f"Line {line}: approx_dep_count {values['approx_dep_count']!r} "
                    f"is not a whole number."
                ) from exc

        rows.append(
            AnchorRow(
                line=line,
                repo_url=values["repo_url"],
                owner=match.group("owner"),
                name=match.group("name"),
                ecosystem=ecosystem,
                bucket=bucket,
                is_known_anchor=known,
                anchor_package=package,
                anchor_version=version,
                approx_dep_count=count,
                has_lockfile=_boolean(values["has_lockfile"], "has_lockfile", line),
                why=values["why_this_bucket"],
            )
        )
    if not rows:
        raise AnchorSetError("The anchor set has a header and no rows.")
    duplicates = sorted(
        {
            row.full_name.lower()
            for row in rows
            if sum(r.full_name.lower() == row.full_name.lower() for r in rows) > 1
        }
    )
    if duplicates:
        raise AnchorSetError(f"Repositories listed twice: {', '.join(duplicates)}.")
    return rows


def read_anchor_set(path: Path) -> list[AnchorRow]:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise AnchorSetError(f"No anchor set at {path}.") from exc
    return parse_anchor_set(text)


def file_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── scanning ───────────────────────────────────────────────────────────────


def _occurrence_record(pooled) -> dict:
    signals = derive_signals(pooled)
    return {
        "ecosystem": pooled.ecosystem,
        "package": pooled.spec.name,
        "manifest_path": pooled.plan.path,
        "declared_specifier": signals.declared_specifier,
        "resolved_version": signals.resolved_version,
        "resolution": signals.resolution,
        "latest_version": signals.latest_version,
        "is_unassessable": signals.is_unassessable,
        "unassessable_reason": signals.unassessable_reason,
        "is_deprecated": signals.is_deprecated,
        "deprecation_reason": signals.deprecation_reason,
        "vulnerability_count": signals.vulnerability_count,
        "highest_severity": signals.highest_severity,
        "cvss_max": str(signals.cvss_max) if signals.cvss_max is not None else None,
        "staleness_days": signals.staleness_days,
    }


def scan_anchor(
    row: AnchorRow,
    client: ResearchClient,
    directory: Path,
    *,
    registry_memo: dict | None = None,
    osv_client: osv.OsvClient | None = None,
) -> dict:
    """One anchor repository, as it is today, through the corpus pipeline."""
    result: dict = {
        "line": row.line,
        "repo_url": row.repo_url,
        "full_name": row.full_name,
        "status": STATUS_FAILED,
        "occurrences": [],
    }
    try:
        meta = client.repository(row.owner, row.name)
    except http.UpstreamNotFound:
        result["status"] = STATUS_NOT_FOUND
        result["error"] = (
            "GitHub answers 404: the repository does not exist or is private."
        )
        return result
    except http.UpstreamError as exc:
        result["error"] = f"GitHub did not answer: {exc}"
        return result

    owner = meta.get("owner") or {}
    full_name = str(meta.get("full_name") or row.full_name)
    owner_login, _, name = full_name.partition("/")
    branch = str(meta.get("default_branch") or "main")
    result.update(
        {
            "full_name": full_name,
            "github_repo_id": int(meta.get("id") or 0),
            "default_branch": branch,
            "archived": bool(meta.get("archived")),
            "pushed_at": meta.get("pushed_at"),
        }
    )

    try:
        tree = client.tree(owner_login, name, branch)
    except http.UpstreamError as exc:
        result["error"] = f"The tree could not be read: {exc}"
        return result

    plans = plan_manifests(tree)
    result["manifests_in_tree"] = len(tree_manifest_paths(tree))
    if not plans:
        result["status"] = STATUS_NO_MANIFEST
        result["error"] = "No manifest any adapter reads is in the default branch."
        return result

    sources: dict[str, bytes] = {}
    for plan in plans:
        if plan.size > MAX_MANIFEST_BYTES:
            continue
        try:
            blob = client.blob(owner_login, name, plan.sha, MAX_MANIFEST_BYTES)
        except http.UpstreamError:
            blob = None
        if blob is not None:
            sources[plan.path] = blob
    adopt_workspace_lockfiles(plans, sources)

    blob_dir = directory / BLOB_DIRNAME
    records = [
        {
            "path": plan.path,
            "sha": plan.sha,
            "size": plan.size,
            "ecosystem": plan.adapter.ecosystem,
            "parser_name": plan.adapter.parser_name,
            "blob_path": _archive_blob(blob_dir, plan.sha, sources[plan.path]),
            "lockfile_path": plan.lockfile_path,
            "lockfile_sha": plan.lockfile_sha,
            "lockfile_size": plan.lockfile_size,
        }
        for plan in plans
        if plan.path in sources
    ]
    repository = CorpusRepository(
        full_name=full_name,
        github_repo_id=result["github_repo_id"],
        owner_login=owner_login,
        owner_id=int(owner.get("id") or 0),
        default_branch=branch,
        ecosystem=row.ecosystem,
        cell="anchor",
        sampling_weight=None,
        manifests=tuple(records),
    )
    try:
        measured = measure(
            repository,
            directory,
            client,
            registry_memo=registry_memo,
            osv_client=osv_client,
        )
    except (ScanFailed, http.UpstreamError) as exc:
        result["error"] = str(exc)
        return result

    result["status"] = STATUS_OK
    result["manifests"] = records
    result["manifests_read"] = measured.manifests_read
    result["manifests_skipped"] = measured.manifests_skipped
    result["lockfiles_read"] = sorted(
        {
            plan.lockfile_path
            for plan in (p.plan for p in measured.pool)
            if plan.lockfile_path
        }
    )
    result["occurrences"] = [_occurrence_record(pooled) for pooled in measured.pool]
    return result


def scan_anchor_set(
    rows: list[AnchorRow],
    client: ResearchClient,
    directory: Path,
    *,
    source: Path | None = None,
    progress=None,
) -> dict:
    """Every anchor, scanned; written to `directory/anchor_scan.json` and returned."""
    directory.mkdir(parents=True, exist_ok=True)
    registry_memo: dict = {}
    osv_client = osv.OsvClient()
    repositories = []
    for row in rows:
        scanned = scan_anchor(
            row, client, directory, registry_memo=registry_memo, osv_client=osv_client
        )
        repositories.append(scanned)
        if progress is not None:
            progress(f"{row.full_name}: {scanned['status']}")
    document = {
        "schema": SCAN_SCHEMA,
        "scanned_at": datetime.now(UTC).isoformat(),
        "anchor_set": source.name if source else None,
        "anchor_set_sha256": file_digest(source) if source else None,
        "repositories": repositories,
    }
    (directory / SCAN_FILENAME).write_text(
        json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return document


def load_scan(path: Path) -> dict | None:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return document if document.get("schema") == SCAN_SCHEMA else None


# ── evaluating ─────────────────────────────────────────────────────────────


def _signals(record: dict) -> Signals:
    cvss = record.get("cvss_max")
    return Signals(
        is_deprecated=bool(record.get("is_deprecated")),
        vulnerability_count=int(record.get("vulnerability_count") or 0),
        cvss_max=Decimal(cvss) if cvss is not None else None,
        staleness_days=record.get("staleness_days"),
    )


def _same_package(ecosystem: str, first: str, second: str) -> bool:
    if ecosystem == "pypi":
        return pep440.normalize_name(first) == pep440.normalize_name(second)
    return first.strip().lower() == second.strip().lower()


def _same_version(ecosystem: str, first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    if first.strip() == second.strip():
        return True
    parse = pep440.parse if ecosystem == "pypi" else semver.parse
    a, b = parse(first), parse(second)
    return a is not None and b is not None and a.sort_key() == b.sort_key()


@dataclass
class AnchorResult:
    row: AnchorRow
    scan: dict
    score: Decimal | None = None
    classification: str | None = None
    anchor_occurrence: dict | None = None
    anchor_flags: tuple[str, ...] = ()
    observed_dependencies: int = 0
    top_contributors: list[tuple[str, Decimal]] = field(default_factory=list)

    @property
    def scanned(self) -> bool:
        return self.scan.get("status") == STATUS_OK

    @property
    def verdict(self) -> str | None:
        """For a known anchor: pass, fail, anchor_not_observed or not_scanned."""
        if not self.row.is_known_anchor:
            return None
        if not self.scanned:
            return VERDICT_NOT_SCANNED
        if self.classification == "safe":
            return VERDICT_FAIL
        if self.anchor_occurrence is None or not self.anchor_flags:
            return VERDICT_INVALID
        return VERDICT_PASS

    @property
    def bucket_outlier(self) -> bool:
        """Seeded healthy but High-Alert, or seeded risky but Safe."""
        if self.classification is None:
            return False
        return (self.row.bucket, self.classification) in {
            ("healthy", "high_alert"),
            ("risky", "safe"),
        }


def evaluate(rows: list[AnchorRow], scan: dict, weights: WeightSet) -> list[AnchorResult]:
    """Score every scanned anchor under `weights` and look for each known anchor."""
    by_name = {
        str(entry.get("repo_url")): entry for entry in scan.get("repositories") or []
    }
    results = [
        AnchorResult(
            row=row, scan=by_name.get(row.repo_url, {"status": VERDICT_NOT_SCANNED})
        )
        for row in rows
    ]

    scanned = [result for result in results if result.scanned]
    panel = CorpusPanel(
        snapshot_date=datetime.now(UTC).date(),
        repositories=[
            PanelRepository(
                scan_history_id=str(result.row.line),
                github_repo_id=int(result.scan.get("github_repo_id") or 0),
                full_name=result.row.full_name,
                owner=result.row.owner,
                ecosystems=",".join(
                    sorted({o["ecosystem"] for o in result.scan["occurrences"]})
                ),
                sampling_weight=None,
                stored_score=Decimal(0),
                stored_classification="",
                stored_version="",
                occurrences=[
                    Occurrence(
                        ecosystem=record["ecosystem"],
                        is_unassessable=bool(record["is_unassessable"]),
                        signals=_signals(record),
                    )
                    for record in result.scan["occurrences"]
                ],
            )
            for result in scanned
        ],
    )
    for result, scored in zip(scanned, score_panel(panel, weights), strict=True):
        result.score = scored.score
        result.classification = scored.classification
        result.observed_dependencies = len(result.scan["occurrences"])
        contributions = []
        for record in result.scan["occurrences"]:
            if record["is_unassessable"]:
                continue
            penalty = score_occurrence(
                _signals(record), weights, record["ecosystem"]
            ).penalty
            if penalty > 0:
                contributions.append((record["package"], penalty))
        contributions.sort(key=lambda item: (-item[1], item[0]))
        result.top_contributors = contributions[:3]

        if result.row.is_known_anchor:
            for record in result.scan["occurrences"]:
                if record["is_unassessable"]:
                    continue
                if _same_package(
                    record["ecosystem"],
                    record["package"],
                    result.row.anchor_package or "",
                ) and _same_version(
                    record["ecosystem"],
                    record["resolved_version"],
                    result.row.anchor_version,
                ):
                    result.anchor_occurrence = record
                    result.anchor_flags = flag_reasons(_signals(record), weights)
                    break
    return results


@dataclass(frozen=True)
class SetCheck:
    """One line of WP-2's quality checklist, computed."""

    check: str
    value: str
    ok: bool


def anchor_set_checks(rows: list[AnchorRow], scan: dict | None = None) -> list[SetCheck]:
    """File B WP-2's quality checks, with the 2026-09-24 review's tightening.

    The review moved the row range to 40-50 (File B's 30-50 cannot hold its own
    bucket minimums) and the known-anchor minimum to 7 (5 plus spares). Given
    a scan, it also compares what the CSV claims about lockfiles and dependency
    counts against what was read — the two columns the review found wrong on
    14 and 6 rows.
    """
    buckets = {bucket: sum(row.bucket == bucket for row in rows) for bucket in BUCKETS}
    known = sum(row.is_known_anchor for row in rows)
    ecosystems = {row.ecosystem for row in rows}
    checks = [
        SetCheck("rows (40-50)", str(len(rows)), 40 <= len(rows) <= 50),
        SetCheck(
            "healthy (15-20)", str(buckets["healthy"]), 15 <= buckets["healthy"] <= 20
        ),
        SetCheck("risky (15-20)", str(buckets["risky"]), 15 <= buckets["risky"] <= 20),
        SetCheck(
            "in_between (10-15)",
            str(buckets["in_between"]),
            10 <= buckets["in_between"] <= 15,
        ),
        SetCheck("known anchors (>= 7)", str(known), known >= 7),
        SetCheck(
            "both ecosystems",
            ", ".join(sorted(ecosystems)),
            {"npm", "pypi"} <= ecosystems,
        ),
    ]
    if scan is not None:
        by_url = {
            entry.get("repo_url"): entry for entry in scan.get("repositories") or []
        }
        scanned = [by_url.get(row.repo_url) for row in rows]
        missing = [
            row.full_name
            for row, entry in zip(rows, scanned, strict=True)
            if not entry or entry.get("status") != STATUS_OK
        ]
        big = sum(
            1 for entry in scanned if entry and len(entry.get("occurrences") or []) >= 100
        )
        lockfile_mismatch = [
            row.full_name
            for row, entry in zip(rows, scanned, strict=True)
            if entry
            and entry.get("status") == STATUS_OK
            and bool(entry.get("lockfiles_read")) != row.has_lockfile
        ]
        checks += [
            SetCheck(
                "repositories scanned",
                f"{len(rows) - len(missing)} of {len(rows)}"
                + (f" (not: {', '.join(missing)})" if missing else ""),
                not missing,
            ),
            SetCheck("100+ declared dependencies (>= 5)", str(big), big >= 5),
            SetCheck(
                "has_lockfile matches a lockfile read",
                "all"
                if not lockfile_mismatch
                else f"differs on {len(lockfile_mismatch)}: {', '.join(lockfile_mismatch)}",
                not lockfile_mismatch,
            ),
        ]
    return checks
