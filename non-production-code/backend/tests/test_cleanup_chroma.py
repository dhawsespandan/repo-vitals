"""`manage.py cleanup_chroma` — §10 Phase 9's orphan sweep.

Acceptance names "cleanup idempotency", which is the property that matters most
for a command whose failure mode is deleting something still in use: running it
twice must be indistinguishable from running it once.

These run against a **real embedded Chroma** in a temporary directory rather
than a mock. The whole command is a conversation with that library — what
`list_collections` returns has changed shape across releases, and a mock would
assert only that this code agrees with itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from io import StringIO

import pytest
from django.core.management import call_command

from apps.reports.models import ReportStatus, ReportType
from apps.reports.rag import chroma_store
from apps.scanning.models import ScanStatus
from tests.factories import (
    DependencyOccurrenceFactory,
    ManifestFileFactory,
    ReportFactory,
    RepositoryFactory,
    ScanRunFactory,
)

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class Chunk:
    """The shape `add_chunks` reads. The chunker's output, minus the parts the
    store does not touch."""

    chunk_id: str
    text: str = "release notes"
    source_path: str = "CHANGELOG.md"
    source_sha: str = "abc123"
    source_kind: str = "changelog"
    heading: str = "1.0.0"
    index: int = 0


@pytest.fixture
def store(tmp_path, settings):
    """A real Chroma, in a directory this test owns."""
    settings.CHROMA_DIR = str(tmp_path / "chroma")
    chroma_store.reset_for_tests()
    yield chroma_store
    chroma_store.reset_for_tests()


def write_chunks(scan_id, package: str = "lodash") -> None:
    chroma_store.add_chunks(
        scan_id=scan_id,
        ecosystem="npm",
        package_name=package,
        resolved_version="4.17.19",
        chunks=[Chunk(chunk_id=f"{scan_id}-{package}-0")],
        # 384 dimensions, the MiniLM width `rag.embeddings` asserts (D7).
        vectors=[[0.1] * 384],
    )


def completed_scan(user):
    scan = ScanRunFactory(
        repository=RepositoryFactory(user=user),
        triggered_by=user,
        status=ScanStatus.COMPLETED.value,
    )
    DependencyOccurrenceFactory(manifest=ManifestFileFactory(scan=scan))
    return scan


def sweep(*args) -> str:
    out = StringIO()
    call_command("cleanup_chroma", *args, stdout=out)
    return out.getvalue()


def test_a_collection_whose_scan_is_gone_is_dropped(store, user):
    """The ordinary orphan: §5.7's retention deleted the scan, and no cascade
    reaches a collection, because the collection is not in Postgres."""
    orphan = uuid.uuid4()
    write_chunks(orphan)

    output = sweep()

    assert str(orphan) in output
    assert "its scan is gone" in output
    assert store.list_scan_ids() == []


def test_a_collection_nothing_is_generating_against_is_dropped(store, user):
    """ "Whose reports all persisted" — §5.9 already deleted the chunks of every
    report that finished, so what is left is an index nothing will read."""
    scan = completed_scan(user)
    ReportFactory(scan=scan)
    write_chunks(scan.pk)

    sweep()

    assert store.list_scan_ids() == []


def test_a_collection_with_a_generation_in_flight_is_left_alone(store, user):
    """The one case that must not be swept: a running graph is still reading."""
    scan = completed_scan(user)
    ReportFactory(scan=scan, status=ReportStatus.RUNNING.value, generated_at=None)
    write_chunks(scan.pk)

    output = sweep()

    assert "a generation is in flight" in output
    assert store.list_scan_ids() == [str(scan.pk)]


def test_a_queued_generation_counts_as_in_flight(store, user):
    """It has not started reading yet, and it is about to."""
    scan = completed_scan(user)
    ReportFactory(scan=scan, status=ReportStatus.QUEUED.value, generated_at=None)
    write_chunks(scan.pk)

    sweep()

    assert store.list_scan_ids() == [str(scan.pk)]


def test_a_failed_generation_does_not_protect_its_collection(store, user):
    """Retrying re-fetches one changelog; `ensure_corpus` is idempotent.

    The alternative is a keep rule with two clauses, one of which nobody can
    state without reading the retry path.
    """
    scan = completed_scan(user)
    ReportFactory(scan=scan, status=ReportStatus.FAILED.value, generated_at=None)
    write_chunks(scan.pk)

    sweep()

    assert store.list_scan_ids() == []


def test_running_it_twice_is_running_it_once(store, user):
    """The acceptance criterion, stated as the property it protects."""
    live = completed_scan(user)
    ReportFactory(scan=live, status=ReportStatus.RUNNING.value, generated_at=None)
    write_chunks(live.pk)
    write_chunks(uuid.uuid4())

    first = sweep()
    second = sweep()

    assert "1 collection(s) dropped" in first
    assert "0 collection(s) dropped" in second
    assert store.list_scan_ids() == [str(live.pk)]


def test_a_dry_run_drops_nothing(store, user):
    write_chunks(uuid.uuid4())

    output = sweep("--dry-run")

    assert "would drop" in output
    assert len(store.list_scan_ids()) == 1


def test_an_empty_store_is_not_an_error(store):
    assert "holds no scan collections" in sweep()


def test_it_leaves_directories_it_did_not_write(store, user):
    """A cleanup that deleted what it could not identify would have an
    unbounded blast radius — `CHROMA_DIR` is ours, and that is not a licence."""
    store._get_client().get_or_create_collection(
        name="someone-elses-index", embedding_function=None
    )
    write_chunks(uuid.uuid4())

    sweep()

    names = [
        entry if isinstance(entry, str) else entry.name
        for entry in store._get_client().list_collections()
    ]
    assert names == ["someone-elses-index"]


def test_the_sweep_writes_nothing_to_the_database(store, user):
    """D10 in miniature: a research command that touched operational rows would
    be a research command that could damage the product."""
    scan = completed_scan(user)
    report = ReportFactory(scan=scan)
    write_chunks(scan.pk)

    sweep()

    report.refresh_from_db()
    scan.refresh_from_db()
    assert report.status == ReportStatus.COMPLETED.value
    assert scan.status == ScanStatus.COMPLETED.value


def test_two_dependencies_of_one_scan_share_its_collection(store, user):
    """A collection is per scan, not per dependency (§5.9), so the sweep is too.

    Worth pinning: a sweep that reasoned per dependency would drop the
    collection out from under the second generation of a scan whose first one
    had just finished.
    """
    scan = completed_scan(user)
    occurrence = DependencyOccurrenceFactory(
        manifest=ManifestFileFactory(scan=scan, manifest_path="api/package.json"),
        is_flagged=True,
    )
    ReportFactory(scan=scan)
    ReportFactory(
        scan=scan,
        dependency=occurrence,
        report_type=ReportType.PER_DEPENDENCY.value,
        status=ReportStatus.RUNNING.value,
        generated_at=None,
    )
    write_chunks(scan.pk, package="lodash")
    write_chunks(scan.pk, package="express")

    sweep()

    assert store.list_scan_ids() == [str(scan.pk)]
