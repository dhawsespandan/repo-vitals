"""`export_research_data`: every file File C reads, in one folder, with its digest.

§10 Phase 14: "parquet/CSV dumps — `exports/scan_history.parquet`,
`exports/dependency_history.parquet`, `exports/agent_traces.parquet`, plus
corpus manifest, weights files, run outputs; File B deliverables archived under
`research_data/deliverables/` as received. These filenames are the interface
File C consumes."

**Two sources, each the authoritative one for what it holds.** The three
permanent tables come from the database `DATABASE_URL` points at — the
research database with WP-5's dump restored (D8). Everything else comes from
the *signed* deliverables in `wp/`, not from the working copies under
`research_data/` on the research machine: `research_data/runs/` also holds the
judge cache, abandoned attempts and the pilot, and a working copy can move
after its sign-off where a committed deliverable cannot. What File C analyses
is what was signed.

**The tables are exact.** Decimals are written as Parquet `decimal128` at the
column's own precision and as their exact text in the CSV, never as floats:
`scores reproduce exactly from the stored signals` (D6, File C §1.1) has to
stay true of the exported copy, and `0.1 + 0.2` is not how a stored cvss_max
of 7.5 should come back. Rows are ordered on a stable key, so two exports of
one database are the same rows in the same order.

**Corpus rows only, unless asked.** File C §1.2: "All research analysis runs
on `corpus_scan` rows; `live_scan` rows ... are never pooled into a corpus
estimate." A live row also names a RepoVitals user and possibly a private
repository, which a replication package has no business carrying by
accident, so `live_scan` rows are exported only when `--source` says so — and
`agent_execution_traces`, which every live per-dependency report writes and
nothing research-side does (§13.4: the experiment runner writes no trace),
counts as live data. With the default, `agent_traces.parquet` is still
written, with its full schema and no rows, so the interface's file exists and
says what it would hold.

**Reads only.** The whole export runs inside `guards.no_writes`: D10's guard
with an empty allowlist. A file set describing a database is wrong the moment
the export writes a row of it.

**`MANIFEST.json` is the receipt.** Every file with its sha256, size and
source; row counts per table broken down by data source, snapshot date and
formula version; the git commit the export ran at. `replication.verify_export`
checks a folder against it before any notebook reads a byte.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.db import connection, models
from django.db.models import F
from django.db.models.functions import Collate

from apps.research.models import (
    AgentExecutionTrace,
    DataSource,
    DependencyHistory,
    ScanHistory,
)
from apps.scoring.weights import weights_dir

MANIFEST_FILENAME = "MANIFEST.json"
#: Bumped when the layout below changes in a way a reader would notice.
EXPORT_FORMAT = 1
#: Rows per Parquet row group and per buffered CSV write. The research database
#: is tens of thousands of rows today; the compose file allows for millions.
BATCH = 10_000

#: A folder of File B's (`wp/wp-4`), archived as received.
DELIVERABLE_DIR = re.compile(r"^wp-\d+$")


class ExportError(Exception):
    """An export that cannot be made as asked; the message says what to change."""


# ── the tables ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TableSpec:
    name: str
    model: type[models.Model]
    order_by: tuple[str, ...]
    #: Live data by construction (see the module docstring), so exported only
    #: when `live_scan` is among the sources.
    live_only: bool = False

    def columns(self) -> list[models.Field]:
        return list(self.model._meta.concrete_fields)


TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        "scan_history",
        ScanHistory,
        ("data_source", "snapshot_date", "repo_full_name", "scan_history_id"),
    ),
    TableSpec(
        "dependency_history",
        DependencyHistory,
        ("scan_history_id", "manifest_path", "package_name", "dependency_history_id"),
    ),
    TableSpec(
        "agent_traces", AgentExecutionTrace, ("created_at", "trace_id"), live_only=True
    ),
)


def _queryset(spec: TableSpec, sources: tuple[str, ...]) -> models.QuerySet:
    manager = spec.model.objects
    if spec.live_only and DataSource.LIVE_SCAN.value not in sources:
        return manager.none()
    if spec.model is ScanHistory:
        found = manager.filter(data_source__in=sources)
    elif spec.model is DependencyHistory:
        found = manager.filter(scan_history__data_source__in=sources)
    else:
        found = manager.all()
    return found.order_by(*_ordering(spec))


def _ordering(spec: TableSpec) -> list:
    """The order keys, with text compared byte-wise on PostgreSQL.

    A text `ORDER BY` follows the database's collation, and `en_US.utf8`
    (Docker's `postgres:16`) and `C.UTF-8` sort `repo_full_name` differently
    (decisions §14). Under the `C` collation the export's row order, and so its
    files' sha256, is the same whichever locale the research database was
    created with. SQLite's default comparison is already byte-wise.
    """
    by_attname = {column.attname: column for column in spec.columns()}
    keys = []
    for name in spec.order_by:
        text = _internal_type(by_attname[name]) in ("TextField", "CharField")
        if text and connection.vendor == "postgresql":
            keys.append(Collate(F(name), "C").asc())
        else:
            keys.append(F(name).asc())
    return keys


def _internal_type(column: models.Field) -> str:
    if column.is_relation:
        return column.target_field.get_internal_type()
    return column.get_internal_type()


def arrow_type(column: models.Field):
    """The Parquet type for a Django column, exact for every type used here."""
    import pyarrow as pa

    kind = _internal_type(column)
    if kind == "DecimalField":
        return pa.decimal128(column.max_digits, column.decimal_places)
    simple = {
        "UUIDField": pa.string(),
        "TextField": pa.string(),
        "CharField": pa.string(),
        "JSONField": pa.string(),
        "BigIntegerField": pa.int64(),
        "IntegerField": pa.int32(),
        "BooleanField": pa.bool_(),
        "DateField": pa.date32(),
        "DateTimeField": pa.timestamp("us", tz="UTC"),
    }
    if kind not in simple:  # pragma: no cover - a guard for the next migration
        raise ExportError(
            f"{column.model._meta.db_table}.{column.column} is a {kind}, which "
            f"the export has no exact Parquet type for. Add one to arrow_type."
        )
    return simple[kind]


def _cell(value, kind: str):
    """A database value as the export stores it: JSON as text, UUIDs as text."""
    if value is None:
        return None
    if kind == "JSONField":
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, UUID):
        return str(value)
    if kind == "DateTimeField" and isinstance(value, datetime) and value.tzinfo is None:
        # SQLite hands naive datetimes back; Postgres hands aware ones. Both
        # are UTC under USE_TZ, and the export says so either way.
        return value.replace(tzinfo=UTC)
    return value


def _csv_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


@dataclass
class TableResult:
    name: str
    rows: int = 0
    by_data_source: Counter = field(default_factory=Counter)
    by_snapshot: Counter = field(default_factory=Counter)
    by_version: Counter = field(default_factory=Counter)
    files: list[Path] = field(default_factory=list)

    def as_json(self) -> dict:
        found = {"rows": self.rows, "files": [path.name for path in self.files]}
        if self.by_data_source:
            found["by_data_source"] = dict(sorted(self.by_data_source.items()))
        if self.by_snapshot:
            found["by_snapshot_date"] = dict(sorted(self.by_snapshot.items()))
        if self.by_version:
            found["by_formula_version"] = dict(sorted(self.by_version.items()))
        return found


def _batches(rows: Iterable[tuple], size: int) -> Iterator[list[tuple]]:
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def export_table(spec: TableSpec, sources: tuple[str, ...], out: Path) -> TableResult:
    """One table to `<name>.parquet` and `<name>.csv`, streamed in batches."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    columns = spec.columns()
    names = [column.column for column in columns]
    kinds = [_internal_type(column) for column in columns]
    schema = pa.schema(
        [
            pa.field(column.column, arrow_type(column), nullable=column.null)
            for column in columns
        ]
    )
    result = TableResult(spec.name)
    parquet_path = out / f"{spec.name}.parquet"
    csv_path = out / f"{spec.name}.csv"
    index = {name: position for position, name in enumerate(names)}

    rows = (
        _queryset(spec, sources)
        .values_list(*[column.attname for column in columns])
        .iterator(chunk_size=BATCH)
    )
    with (
        csv_path.open("w", encoding="utf-8", newline="") as handle,
        pq.ParquetWriter(parquet_path, schema) as parquet,
    ):
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(names)
        for batch in _batches(rows, BATCH):
            cells = [
                [_cell(value, kind) for value, kind in zip(row, kinds, strict=True)]
                for row in batch
            ]
            writer.writerows([[_csv_text(value) for value in row] for row in cells])
            parquet.write_table(
                pa.Table.from_pylist(
                    [dict(zip(names, row, strict=True)) for row in cells], schema=schema
                )
            )
            result.rows += len(cells)
            for row in cells:
                if "data_source" in index:
                    result.by_data_source[row[index["data_source"]]] += 1
                if "snapshot_date" in index:
                    found = row[index["snapshot_date"]]
                    result.by_snapshot[found.isoformat() if found else "none"] += 1
                if "scoring_formula_version" in index:
                    result.by_version[row[index["scoring_formula_version"]]] += 1
        if result.rows == 0:
            # An empty table is still a file with the table's schema in it, so
            # a reader learns the columns rather than a missing-file error.
            parquet.write_table(schema.empty_table())
    result.files = [parquet_path, csv_path]
    return result


# ── the documents ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Document:
    """A file or folder of a signed deliverable, copied to a fixed export path."""

    target: str
    source: str
    what: str


#: The interface File C reads (its §0.1 inventory), and where each piece was
#: signed. Paths are relative to the deliverables root (`wp/`) and to the export
#: folder. `runs/` keeps `research_data/runs/`'s own layout, so the analysis
#: code reads an export exactly as it reads the research machine's folder.
DOCUMENTS: tuple[Document, ...] = (
    Document(
        "corpus/corpus_manifest.json",
        "wp-4/corpus_manifest.json",
        "WP-4: the sampling frame, seed, grid and per-repository sampling weights",
    ),
    Document(
        "corpus/strata_report.md",
        "wp-4/strata_report.md",
        "WP-4: the strata report",
    ),
    Document(
        "corpus/corpus_report.md",
        "wp-5/corpus_report.md",
        "WP-5: the corpus figures' report (S1's descriptive figures)",
    ),
    Document(
        "corpus/score_histogram.png",
        "wp-5/score_histogram.png",
        "WP-5: score histogram per ecosystem",
    ),
    Document(
        "corpus/flagged_rate_by_stratum.png",
        "wp-5/flagged_rate_by_stratum.png",
        "WP-5: flagged rate by stratum",
    ),
    Document(
        "anchors/wp2_anchor_set.csv",
        "wp-2/wp2_anchor_set.csv",
        "WP-2: the anchor set",
    ),
    Document(
        "ahp/wp3_matrix_final.csv",
        "wp-3/wp3_matrix_final.csv",
        "WP-3: the AHP matrix (a single judgment; WP_review)",
    ),
    Document(
        "ahp/wp3_session_notes.md",
        "wp-3/wp3_session_notes.md",
        "WP-3: the session notes",
    ),
    Document(
        "validation_report",
        "wp-6/validation_report",
        "WP-6: validate_formula's report folder, unedited, with its deps.dev "
        "answers and anchor scan as observed",
    ),
    Document(
        "runs/ground_truth/labelled_set.jsonl",
        "wp-8/labelled_set.jsonl",
        "Phase 13: the frozen S3 labelled set",
    ),
    Document(
        "runs/ground_truth/labelled_set_meta.json",
        "wp-8/labelled_set_meta.json",
        "Phase 13: the labelled set's quotas and coverage",
    ),
    Document(
        "runs/ground_truth/extraction_report.md",
        "wp-8/extraction_report.md",
        "Phase 13: the extraction coverage report",
    ),
    Document(
        "runs",
        "wp-8/runs",
        "WP-8: the A/B/C run folders and analyze_experiment's tables",
    ),
    Document(
        "runs/wp8_run_log.md",
        "wp-8/wp8_run_log.md",
        "WP-8: the run log",
    ),
    Document(
        "judge_validation/wp9_judge_labels.csv",
        "wp-9/wp9_judge_labels.csv",
        "WP-9: the human labels (the answer key is withheld: decisions §13.17)",
    ),
)

#: Everything under `weights/` in the backend, which is code rather than a
#: deliverable but which File C names in the same inventory.
WEIGHTS_TARGET = "weights"


def missing_documents(deliverables: Path) -> list[str]:
    return [
        document.source
        for document in DOCUMENTS
        if not (deliverables / document.source).exists()
    ]


def _copy(source: Path, target: Path) -> list[tuple[Path, Path]]:
    """Copy a file or a folder; return every `(source, target)` file pair, sorted."""
    if source.is_dir():
        pairs = []
        for path in sorted(source.rglob("*")):
            if path.is_file():
                pairs.extend(_copy(path, target / path.relative_to(source)))
        return pairs
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return [(source, target)]


# ── the receipt ────────────────────────────────────────────────────────────


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit(directory: Path) -> dict:
    """The commit the export ran at, and whether the tree had local changes."""
    git = shutil.which("git")
    if git is None:
        return {"commit": None, "dirty": None}
    try:
        commit = subprocess.run(  # noqa: S603 - fixed argv, no shell, no input
            [git, "rev-parse", "HEAD"],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        status = subprocess.run(  # noqa: S603
            [git, "status", "--porcelain", "--untracked-files=no"],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit or None, "dirty": bool(status)}


@dataclass
class ExportResult:
    out: Path
    archive: Path | None
    tables: list[TableResult]
    files: list[dict]
    archived: int
    manifest: Path


def planned_paths(out: Path) -> list[Path]:
    """Every top-level path an export writes under `out`, in a fixed order."""
    paths = [
        out / f"{spec.name}.{suffix}" for spec in TABLES for suffix in ("parquet", "csv")
    ]
    paths += [out / document.target for document in DOCUMENTS]
    paths += [out / WEIGHTS_TARGET, out / MANIFEST_FILENAME]
    return paths


def _clear_previous_export(out: Path, overwrite: bool) -> None:
    """Make room for this export without touching anything it did not write.

    `research_data/exports/` is shared: on the research machine it already
    holds WP-5's dump and the materialized `v2` rescore panel (§12.19). So an
    export never empties the folder. It refuses when any path it writes is
    already there, and `--overwrite` removes exactly the files the previous
    export's own `MANIFEST.json` lists — then copies over the rest.
    """
    existing = [path for path in planned_paths(out) if path.exists()]
    if existing and not overwrite:
        shown = ", ".join(path.name for path in existing[:6])
        raise ExportError(
            f"{out} already holds an export ({shown}). Pass --overwrite to replace "
            f"it; only the files its MANIFEST.json lists are removed, and nothing "
            f"else in the folder is touched."
        )
    previous = out / MANIFEST_FILENAME
    if overwrite and previous.exists():
        listed = json.loads(previous.read_text(encoding="utf-8")).get("files", [])
        for entry in listed:
            target = (out / entry["path"]).resolve()
            # A manifest names paths inside its own folder; anything else in
            # one is not a file this command wrote.
            if out.resolve() in target.parents:
                target.unlink(missing_ok=True)
        previous.unlink()
    out.mkdir(parents=True, exist_ok=True)


def _deliverable_folders(deliverables: Path) -> list[Path]:
    return [
        folder
        for folder in sorted(deliverables.iterdir())
        if folder.is_dir() and DELIVERABLE_DIR.match(folder.name)
    ]


def _archive_conflicts(deliverables: Path, archive: Path) -> None:
    present = [
        folder.name
        for folder in _deliverable_folders(deliverables)
        if (archive / folder.name).exists()
    ]
    if present:
        raise ExportError(
            f"{archive} already holds {', '.join(present)}. Pass --overwrite to copy "
            f"over them (nothing in the archive is ever deleted), or --no-archive."
        )


def _archive(deliverables: Path, archive: Path) -> int:
    """Copy each `wp-N` folder into `archive`; never delete anything there.

    File B: "Never edit a deliverable after handoff — send a v2 zip instead."
    The archive is additive by the same rule, and may already hold the zips as
    they were received.
    """
    return sum(
        len(_copy(folder, archive / folder.name))
        for folder in _deliverable_folders(deliverables)
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def export_research_data(
    out: Path,
    deliverables: Path,
    *,
    archive: Path | None,
    sources: tuple[str, ...] = (DataSource.CORPUS_SCAN.value,),
    overwrite: bool = False,
    progress=None,
) -> ExportResult:
    """Write the export folder and (optionally) the deliverables archive."""
    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise ExportError(
            "The Parquet files need pyarrow, a research-only dependency: "
            "pip install -r requirements-research.txt"
        ) from exc

    unknown = sorted(set(sources) - set(DataSource.values))
    if unknown or not sources:
        raise ExportError(
            f"Unknown data source(s) {', '.join(unknown) or '(none given)'}; "
            f"choose from {', '.join(DataSource.values)}."
        )
    if not deliverables.is_dir():
        raise ExportError(
            f"No deliverables folder at {deliverables}. Point --deliverables at "
            f"the repository's wp/ folder."
        )
    missing = missing_documents(deliverables)
    if missing:
        raise ExportError(
            "The export needs every signed deliverable File C reads, and these "
            f"are missing under {deliverables}: {', '.join(missing)}."
        )

    if archive is not None and not overwrite:
        # Refuse before anything is removed or written, not halfway through.
        _archive_conflicts(deliverables, archive)
    _clear_previous_export(out, overwrite)
    root = Path(settings.BASE_DIR).parent

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    tables = []
    for spec in TABLES:
        found = export_table(spec, sources, out)
        say(f"{spec.name}: {found.rows} row(s)")
        tables.append(found)

    entries: list[dict] = []
    for found in tables:
        for path in found.files:
            entries.append({"path": path.name, "source": f"database:{found.name}"})
    for document in DOCUMENTS:
        for source, target in _copy(
            deliverables / document.source, out / document.target
        ):
            entries.append(
                {"path": _relative(target, out), "source": _relative(source, root)}
            )
    for source, target in _copy(weights_dir(), out / WEIGHTS_TARGET):
        entries.append(
            {"path": _relative(target, out), "source": _relative(source, root)}
        )
    say(f"documents: {len(entries) - 2 * len(tables)} file(s) from the deliverables")

    # A later document can land inside an earlier folder (`runs/wp8_run_log.md`
    # inside `runs/`); the manifest lists each path once, last copy winning.
    by_path = {entry["path"]: entry for entry in entries}
    files = []
    for path_text in sorted(by_path):
        path = out / path_text
        files.append(
            {
                **by_path[path_text],
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    archived = 0
    if archive is not None:
        archived = _archive(deliverables, archive)
        say(f"deliverables: {archived} file(s) archived to {archive}")

    database = settings.DATABASES["default"]
    manifest = {
        "export_format": EXPORT_FORMAT,
        "generated_at": datetime.now(UTC).isoformat(),
        "git": git_commit(root),
        "database": {
            "vendor": connection.vendor,
            # The name only: a URL would carry the password.
            "name": os.path.basename(str(database.get("NAME") or "")),
        },
        "sources": list(sources),
        "tables": {found.name: found.as_json() for found in tables},
        "documents": [
            {"target": document.target, "source": document.source, "what": document.what}
            for document in DOCUMENTS
        ],
        "files": files,
        "deliverables_archive": None
        if archive is None
        else {"path": _relative(archive, root), "files": archived},
        "notes": [
            "Scores are recomputed from these signals, never read (D6, File C §1.1).",
            "agent_traces holds live product traces only; S3's generations are "
            "runs/*/items.jsonl (decisions §13.4).",
            "The WP-9 answer key and the judge cache are withheld until the "
            "§13.17 decision; faithfulness verdicts per item are in "
            "runs/analysis/metrics.csv.",
        ],
    }
    manifest_path = out / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ExportResult(
        out=out,
        archive=archive,
        tables=tables,
        files=files,
        archived=archived,
        manifest=manifest_path,
    )
