"""§10 Phase 12's acceptance clauses that span modules.

* "v1-vs-v2 spot-check: same stored signals differ only per weight deltas" —
  every occurrence's penalty under two vectors differs by exactly
  100 x Σ Δw_i·S_i, up to §5.2's per-term rounding, and nothing else moves.
* "corpus rescore completes fully offline (network assertion)" — `rescore` and
  `validate_formula` run with the socket layer itself refusing to connect, so
  "offline" is a property of the run, not of what a mock happened to cover.
* "`validate_formula` runs end-to-end on the WP-5 data in one command" — here
  the corpus row is written by `scan_corpus` itself, through Phase 11's mocked
  pipeline, so the harness is tested on rows of the shape WP-5 will hand over
  rather than only on rows a helper built.
"""

from __future__ import annotations

import csv
import json
import socket
from decimal import Decimal
from io import StringIO

import pytest
import responses
from django.core.management import call_command

from apps.research.models import ScanHistory
from apps.research.validation import candidates, panel
from apps.scoring.engine import score_occurrence
from apps.scoring.normalize import normalize
from apps.scoring.weights import active_weights, load_weights
from tests.corpus_rows import corpus_repository
from tests.test_corpus_scan import mock_everything, run, write_manifest

RECONCILED = (
    ",Deprecation,Severity,Count,Staleness\n"
    "Deprecation,1,1.4142,3,2.8284\n"
    "Severity,,1,2.8284,3\n"
    "Count,,,1,2\n"
    "Staleness,,,,1\n"
)


@pytest.fixture
def no_sockets(monkeypatch):
    """Any attempt to open a network connection fails the test outright."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"network access attempted: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ── v1 vs v2 ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_two_vectors_differ_only_by_their_weight_deltas():
    corpus_repository(
        "o/mixed",
        [
            {"vulns": 3, "cvss": 9.8, "staleness": 400},
            {"deprecated": True, "staleness": 2000},
            {"vulns": 1, "cvss": None, "staleness": 30},
            {"staleness": None, "vulns": 2, "cvss": 5.3},
            {"ecosystem": "pypi", "deprecated": True, "vulns": 1, "cvss": 7.5},
        ],
    )
    loaded = panel.load_panel()
    v1 = active_weights()
    v2 = candidates.weightset_from(
        v1,
        {
            "npm": {
                "deprecation": 0.40,
                "severity": 0.34,
                "count": 0.15,
                "staleness": 0.11,
            },
            "pypi": {
                "deprecation": 0.26,
                "severity": 0.43,
                "count": 0.15,
                "staleness": 0.16,
            },
        },
        version="v2",
        derivation="test",
    )

    for occurrence in loaded.repositories[0].occurrences:
        before = score_occurrence(occurrence.signals, v1, occurrence.ecosystem)
        after = score_occurrence(occurrence.signals, v2, occurrence.ecosystem)
        terms = normalize(
            occurrence.signals,
            cve_count_cap=v1.normalization.cve_count_cap,
            staleness_cap_days=v1.normalization.staleness_cap_days,
        ).terms

        def effective(weights, ecosystem, terms=terms):
            vector = weights.for_ecosystem(ecosystem)
            present = {name: vector[name] for name in terms}
            total = sum(present.values())
            return {name: weight / total for name, weight in present.items()}

        w1 = effective(v1, occurrence.ecosystem)
        w2 = effective(v2, occurrence.ecosystem)
        expected = Decimal(100) * sum(
            (w2[name] - w1[name]) * terms[name] for name in terms
        )
        # Each term is quantised to cents before it is summed (§5.2), so the
        # difference may be off the exact delta by at most a cent per term.
        assert abs((after.penalty - before.penalty) - expected) <= Decimal("0.01") * len(
            terms
        )
        # And nothing but the weights moved: same terms, same caps, same flags.
        assert [t.signal for t in after.terms] == [t.signal for t in before.terms]
        assert [t.normalized for t in after.terms] == [t.normalized for t in before.terms]


# ── offline ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_corpus_rescore_needs_no_network(tmp_path, no_sockets):
    for index in range(5):
        corpus_repository(
            f"o/r{index}", [{"vulns": index, "cvss": 7.0}, {"staleness": 100 * index}]
        )
    prefix = tmp_path / "exports" / "v0"
    call_command(
        "rescore", "--weights", "v0_equal", "--out", str(prefix), "--source", "corpus_scan",
        stdout=StringIO(),
    )  # fmt: skip
    manifest = json.loads(
        (tmp_path / "exports" / "v0_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["scan_history_rows"] == 5
    assert manifest["weights_version"] == "v0_equal"


@pytest.mark.django_db
def test_the_validation_itself_needs_no_network_when_told_not_to_ask(
    tmp_path, no_sockets
):
    for index in range(6):
        corpus_repository(
            f"o/r{index}",
            [{"vulns": index % 3, "cvss": 7.0}, {"deprecated": index == 2}],
        )
    matrix = tmp_path / "rec.csv"
    matrix.write_text(RECONCILED, encoding="utf-8")
    call_command(
        "validate_formula", "--ahp", str(matrix), "--out", str(tmp_path / "report"),
        "--skip-reference", "--bootstrap", "10", stdout=StringIO(),
    )  # fmt: skip
    assert (tmp_path / "report" / "report.md").exists()


# ── Phase 11 into Phase 12 ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestOnRowsScanCorpusWrote:
    @responses.activate
    def test_the_harness_reads_what_the_corpus_scan_writes(self, tmp_path, settings):
        settings.GITHUB_API_PAT = "ghp_research_token"
        mock_everything()
        outcome = run(tmp_path, manifest=write_manifest(tmp_path, archive=True))
        assert outcome.scanned == 1
        # A few more repositories, so the statistics have something to rank.
        for index in range(4):
            corpus_repository(
                f"o/r{index}",
                [{"vulns": index, "cvss": 6.5}, {"staleness": 300 * index}],
                snapshot=outcome.snapshot_date,
            )

        matrix = tmp_path / "rec.csv"
        matrix.write_text(RECONCILED, encoding="utf-8")
        out = tmp_path / "report"
        calls_before = len(responses.calls)
        call_command(
            "validate_formula", "--ahp", str(matrix), "--out", str(out),
            "--skip-reference", "--bootstrap", "20", stdout=StringIO(),
        )  # fmt: skip

        assert len(responses.calls) == calls_before
        text = (out / "report.md").read_text(encoding="utf-8")
        # D6 on a row the shipped pipeline wrote: recomputing under its own
        # version reproduces the score scan_corpus stored.
        assert "All 5 stored repository scores reproduce exactly" in text
        with (out / "scores.csv").open(encoding="utf-8") as handle:
            rows = {row["repository"]: row for row in csv.DictReader(handle)}
        shop = rows["acme/shop"]
        stored = ScanHistory.objects.get(repo_full_name="acme/shop").risk_score
        assert shop["stored_score"] == shop["score_v1"] == str(stored)
        assert shop["sampling_weight"] == "12.5"


def test_the_candidate_vector_of_the_reviewed_matrix():
    """The reconciled matrix the 2026-09-24 review recomputed gives 0.40 / 0.34 /
    0.15 / 0.11, and the candidate file states it to four places."""
    from apps.research.validation import ahp

    result = ahp.evaluate(ahp.parse_matrix(RECONCILED))
    built = candidates.weightset_from(
        load_weights("v1"),
        {"npm": result.weight_vector(), "pypi": result.weight_vector()},
        version="v2",
        derivation="t",
    )
    assert [
        str(built.weights["npm"][s])
        for s in ("deprecation", "severity", "count", "staleness")
    ] == [
        "0.4026",
        "0.3375",
        "0.1523",
        "0.1076",
    ]
