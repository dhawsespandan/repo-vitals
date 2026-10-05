"""The anchors (RQ4), the report, and `validate_formula` as WP-6 will type it.

§10 Phase 12's acceptance, as far as a suite can carry it: "`validate_formula`
runs end-to-end ... in one command; anchors pass". The rest — real WP-5 data,
a real anchor set — is WP-6's run.

Every command test runs under `responses` with nothing registered unless the
test registers it, so a network call nobody expected fails the test rather
than reaching the internet. That is how "the anchor scan is reused" and "deps.dev
is not asked under --skip-reference" are asserted, not just claimed.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO

import pytest
import responses
import yaml
from django.core.management import CommandError, call_command

from apps.common import http
from apps.research.models import DependencyHistory, ScanHistory
from apps.research.validation import anchors
from apps.scanning.models import DependencyOccurrence, ScanRun
from apps.scoring.weights import active_weights, parse_weights
from tests.corpus_rows import corpus_repository
from tests.test_corpus_scan import (
    REPO_API,
    mock_github,
    mock_osv,
    mock_registry,
)

HEADER = (
    "repo_url,ecosystem,bucket_seeded,is_known_anchor,anchor_package,"
    "approx_dep_count,has_lockfile,why_this_bucket\n"
)

RECONCILED = (
    ",Deprecation,Severity,Count,Staleness\n"
    "Deprecation,1,1.4142,3,2.8284\n"
    "Severity,,1,2.8284,3\n"
    "Count,,,1,2\n"
    "Staleness,,,,1\n"
)

CIRCULAR = (
    ",Deprecation,Severity,Count,Staleness\n"
    "Deprecation,1,9,1/9,1\n"
    "Severity,,1,9,1\n"
    "Count,,,1,1\n"
    "Staleness,,,,1\n"
)


@pytest.fixture(autouse=True)
def quiet_network(monkeypatch, settings):
    monkeypatch.setattr(http, "_local", type(http._local)())
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)
    settings.GITHUB_API_PAT = "ghp_research_token"


# ── the CSV ────────────────────────────────────────────────────────────────


class TestTheAnchorSet:
    def test_a_well_formed_row(self):
        rows = anchors.parse_anchor_set(
            HEADER
            + 'https://github.com/acme/shop,npm,risky,true,lodash@4.17.19,5,true,"lockfile pins it, flagged"\n'
        )
        row = rows[0]
        assert (row.owner, row.name, row.bucket) == ("acme", "shop", "risky")
        assert (row.anchor_package, row.anchor_version) == ("lodash", "4.17.19")
        assert row.is_known_anchor and row.has_lockfile

    def test_a_scoped_npm_package_keeps_its_scope(self):
        assert anchors.split_anchor_package("@babel/core@7.0.0") == (
            "@babel/core",
            "7.0.0",
        )

    def test_file_bs_spaced_header_is_accepted(self):
        spaced = HEADER.replace(",", ", ")
        rows = anchors.parse_anchor_set(
            spaced + "https://github.com/a/b,pypi,healthy,false,,3,false,fine\n"
        )
        assert rows[0].bucket == "healthy"

    @pytest.mark.parametrize(
        ("row", "message"),
        [
            (
                "https://gitlab.com/a/b,npm,risky,false,,1,false,x",
                "github.com/owner/name",
            ),
            ("https://github.com/a/b,ruby,risky,false,,1,false,x", "ecosystem"),
            ("https://github.com/a/b,npm,bad,false,,1,false,x", "bucket_seeded"),
            ("https://github.com/a/b,npm,risky,yes,,1,false,x", "true or false"),
            ("https://github.com/a/b,npm,risky,true,,1,false,x", "needs anchor_package"),
            (
                "https://github.com/a/b,npm,risky,true,request,1,false,x",
                "name@exact-version",
            ),
            ("https://github.com/a/b,npm,risky,false,,many,false,x", "whole number"),
            ("https://github.com/a/b,npm,risky,false,,1,false,x,extra", "9 values"),
            ("# a comment,,,,,,,", "comment lines"),
        ],
    )
    def test_rows_that_break_the_format_are_refused(self, row, message):
        with pytest.raises(anchors.AnchorSetError, match=message):
            anchors.parse_anchor_set(HEADER + row + "\n")

    def test_the_header_must_be_file_bs(self):
        with pytest.raises(
            anchors.AnchorSetError, match="exactly File B's eight columns"
        ):
            anchors.parse_anchor_set("repo,eco\nx,y\n")

    def test_a_repository_listed_twice_is_refused(self):
        line = "https://github.com/a/b,npm,risky,false,,1,false,x\n"
        with pytest.raises(anchors.AnchorSetError, match="listed twice"):
            anchors.parse_anchor_set(HEADER + line + line.replace("/b,", "/B,"))

    def test_the_quality_checks_use_the_reviews_ranges(self):
        rows = anchors.parse_anchor_set(
            HEADER + "https://github.com/a/b,npm,risky,true,x@1.0.0,1,false,y\n"
        )
        checks = {check.check: check for check in anchors.anchor_set_checks(rows)}
        assert not checks["rows (40-50)"].ok
        assert not checks["known anchors (>= 7)"].ok
        assert checks["both ecosystems"].value == "npm"


# ── scanning, through the corpus pipeline ──────────────────────────────────

GOLDEN_ROW = (
    HEADER
    + "https://github.com/acme/shop,npm,risky,true,lodash@4.17.19,5,true,lock pins lodash\n"
    + "https://github.com/ghost/gone,npm,healthy,false,,3,false,deleted since\n"
)


def mock_metadata() -> None:
    responses.add(
        responses.GET,
        REPO_API,
        json={
            "id": 778899,
            "full_name": "acme/shop",
            "default_branch": "main",
            "archived": True,
            "pushed_at": "2019-01-01T00:00:00Z",
            "owner": {"login": "acme", "id": 4242},
        },
    )
    responses.add(responses.GET, "https://api.github.com/repos/ghost/gone", status=404)


@pytest.mark.django_db
class TestScanningAnchors:
    @responses.activate
    def test_an_anchor_is_scanned_and_seen_and_nothing_is_registered(self, tmp_path):
        mock_metadata()
        mock_github()
        mock_registry()
        mock_osv()
        from apps.research.github import ResearchClient

        source = tmp_path / "wp2.csv"
        source.write_text(GOLDEN_ROW, encoding="utf-8")
        rows = anchors.read_anchor_set(source)

        scan = anchors.scan_anchor_set(
            rows, ResearchClient.from_settings(), tmp_path / "anchors", source=source
        )

        shop, gone = scan["repositories"]
        assert shop["status"] == anchors.STATUS_OK
        assert shop["archived"] is True
        assert gone["status"] == anchors.STATUS_NOT_FOUND
        assert scan["anchor_set_sha256"] == anchors.file_digest(source)
        # The vendored node_modules manifest is not read, as in a product scan.
        assert all(
            not o["manifest_path"].startswith("node_modules") for o in shop["occurrences"]
        )
        # Archived like build_corpus archives, so the scan is evidence.
        assert (tmp_path / "anchors" / "blobs" / "ro" / "root-manifest").exists()
        assert ScanRun.objects.count() == 0
        assert DependencyOccurrence.objects.count() == 0
        assert ScanHistory.objects.count() == 0

        results = anchors.evaluate(rows, scan, active_weights())
        shop_result = results[0]
        assert shop_result.anchor_occurrence["resolution"] == "lockfile"
        assert {"deprecated", "vulnerable"} <= set(shop_result.anchor_flags)
        assert shop_result.classification != "safe"
        assert shop_result.verdict == anchors.VERDICT_PASS
        assert results[1].verdict is None  # not a known anchor
        assert not results[1].scanned


def hand_scan(occurrences: list[dict], url: str = "https://github.com/a/b") -> dict:
    return {
        "schema": anchors.SCAN_SCHEMA,
        "repositories": [
            {
                "repo_url": url,
                "full_name": "a/b",
                "status": anchors.STATUS_OK,
                "github_repo_id": 1,
                "lockfiles_read": [],
                "occurrences": [
                    {
                        "ecosystem": "npm",
                        "package": "x",
                        "manifest_path": "package.json",
                        "resolved_version": "1.0.0",
                        "resolution": "pinned",
                        "is_unassessable": False,
                        "is_deprecated": False,
                        "vulnerability_count": 0,
                        "cvss_max": None,
                        "staleness_days": 10,
                        **occurrence,
                    }
                    for occurrence in occurrences
                ],
            }
        ],
    }


class TestVerdicts:
    rows = anchors.parse_anchor_set(
        HEADER + "https://github.com/a/b,npm,risky,true,request@2.88.2,1,false,x\n"
    )

    def test_a_known_bad_repository_that_scores_safe_fails(self):
        """File B: "Any known-bad anchor scoring Safe = automatic fail"."""
        scan = hand_scan([{"package": "request", "resolved_version": "2.88.2"}])
        result = anchors.evaluate(self.rows, scan, active_weights())[0]
        assert result.classification == "safe"
        assert result.verdict == anchors.VERDICT_FAIL

    def test_medium_without_the_anchor_is_an_invalid_anchor_not_a_pass(self):
        """The review's finding: a repository can land in Medium for reasons
        that have nothing to do with the named package. That certifies nothing."""
        scan = hand_scan([{"package": "left-pad", "is_deprecated": True}])
        result = anchors.evaluate(self.rows, scan, active_weights())[0]
        assert result.classification in ("medium", "high_alert")
        assert result.anchor_occurrence is None
        assert result.verdict == anchors.VERDICT_INVALID

    def test_the_anchor_at_another_version_is_not_the_anchor(self):
        scan = hand_scan(
            [{"package": "request", "resolved_version": "2.88.0", "is_deprecated": True}]
        )
        assert anchors.evaluate(self.rows, scan, active_weights())[0].verdict == (
            anchors.VERDICT_INVALID
        )

    def test_seen_flagged_and_at_least_medium_passes(self):
        scan = hand_scan(
            [{"package": "request", "resolved_version": "2.88.2", "is_deprecated": True}]
        )
        result = anchors.evaluate(self.rows, scan, active_weights())[0]
        assert result.anchor_flags == ("deprecated",)
        assert result.verdict == anchors.VERDICT_PASS

    def test_pypi_names_compare_normalised(self):
        rows = anchors.parse_anchor_set(
            HEADER + "https://github.com/a/b,pypi,risky,true,Django@1.4.22,1,false,x\n"
        )
        scan = hand_scan(
            [
                {
                    "ecosystem": "pypi",
                    "package": "django",
                    "resolved_version": "1.4.22",
                    "vulnerability_count": 3,
                    "cvss_max": "9.8",
                }
            ]
        )
        assert anchors.evaluate(rows, scan, active_weights())[0].verdict == (
            anchors.VERDICT_PASS
        )

    def test_an_unscanned_anchor_says_so(self):
        scan = {"schema": anchors.SCAN_SCHEMA, "repositories": []}
        assert anchors.evaluate(self.rows, scan, active_weights())[0].verdict == (
            anchors.VERDICT_NOT_SCANNED
        )


# ── validate_formula, as WP-6 types it ─────────────────────────────────────


def build_corpus_rows() -> None:
    corpus_repository("o/clean", [{"staleness": 5}, {"staleness": 40}])
    corpus_repository("o/vulnerable", [{"vulns": 2, "cvss": 9.8}, {"staleness": 900}])
    corpus_repository("o/deprecated", [{"deprecated": True}, {"staleness": 100}])
    corpus_repository("o/stale", [{"staleness": 2000}, {"staleness": 1500}])
    corpus_repository(
        "p/py-one", [{"ecosystem": "pypi", "vulns": 1, "cvss": 5.3}], sampling_weight=2.0
    )
    corpus_repository("p/py-two", [{"ecosystem": "pypi", "staleness": 10}])
    corpus_repository(
        "p/py-three", [{"ecosystem": "pypi", "deprecated": True, "staleness": 1200}]
    )


def anchor_files(tmp_path, out):
    source = tmp_path / "wp2_anchor_set.csv"
    source.write_text(
        HEADER + "https://github.com/a/b,npm,risky,true,request@2.88.2,1,false,x\n",
        encoding="utf-8",
    )
    scan = hand_scan(
        [{"package": "request", "resolved_version": "2.88.2", "is_deprecated": True}]
    )
    scan["anchor_set_sha256"] = anchors.file_digest(source)
    scan["scanned_at"] = "2026-10-05T00:00:00+00:00"
    (out / "anchors").mkdir(parents=True)
    (out / "anchors" / anchors.SCAN_FILENAME).write_text(
        json.dumps(scan), encoding="utf-8"
    )
    return source


@pytest.mark.django_db
class TestValidateFormula:
    @responses.activate
    def test_one_command_writes_the_whole_folder_and_no_row(self, tmp_path):
        build_corpus_rows()
        matrix = tmp_path / "wp3_matrix_reconciled.csv"
        matrix.write_text(RECONCILED, encoding="utf-8")
        out = tmp_path / "validation_report"
        source = anchor_files(tmp_path, out)
        before = (ScanHistory.objects.count(), DependencyHistory.objects.count())

        stdout = StringIO()
        call_command(
            "validate_formula",
            "--ahp", str(matrix),
            "--anchors", str(source),
            "--out", str(out),
            "--skip-reference",
            "--bootstrap", "40",
            "--pypi-shift", "deprecation=-0.14,severity=+0.07,staleness=+0.07",
            stdout=stdout,
        )  # fmt: skip

        assert len(responses.calls) == 0  # the saved anchor scan was reused
        assert (ScanHistory.objects.count(), DependencyHistory.objects.count()) == before
        for name in (
            "report.md",
            "inputs.json",
            "weights_v2_candidate.yaml",
            "scores.csv",
            "correlation.csv",
            "confusion.csv",
            "sensitivity.csv",
            "entropy.csv",
            "weights_comparison.csv",
            "anchors.csv",
        ):
            assert (out / name).exists(), name

        text = (out / "report.md").read_text(encoding="utf-8")
        assert "## WP-6 sign-off checklist" in text
        assert "| 1 | Reconciled matrix CR < 0.10 | **ok** |" in text
        assert "| 2 | Every known anchor ≥ Medium | **ok** |" in text
        assert "**not run** | --skip-reference was given" in text
        assert "All 7 stored repository scores reproduce exactly" in text
        # The circular reference's caveat sits right above its number.
        assert "Circular reference: OSV supplies two of the formula's four" in text
        assert "WP-6 checklist: 1 ok, 2 ok" in stdout.getvalue()

    @responses.activate
    def test_the_candidate_file_is_one_the_product_would_load(self, tmp_path):
        build_corpus_rows()
        matrix = tmp_path / "rec.csv"
        matrix.write_text(RECONCILED, encoding="utf-8")
        out = tmp_path / "report"
        call_command(
            "validate_formula", "--ahp", str(matrix), "--out", str(out),
            "--skip-reference", "--bootstrap", "0", stdout=StringIO(),
        )  # fmt: skip

        text = (out / "weights_v2_candidate.yaml").read_text(encoding="utf-8")
        loaded = parse_weights(yaml.safe_load(text), out / "weights_v2.yaml", "v2")
        assert loaded.derivation == "ahp-candidate-pending-wp6"
        assert loaded.weights["npm"]["deprecation"] == Decimal("0.4026")
        assert sum(loaded.weights["pypi"].values()) == Decimal(1)
        assert "NOT ACTIVE" in text
        # Without a PyPI rule, PyPI takes the npm vector, and the report says so.
        assert loaded.weights["pypi"] == loaded.weights["npm"]
        assert "no --pypi-shift was given" in (out / "report.md").read_text(
            encoding="utf-8"
        )

    def test_an_inconsistent_matrix_is_refused_before_anything_is_written(self, tmp_path):
        """File B: "the tool refuses otherwise — a refusal is a WP-3 revisit"."""
        matrix = tmp_path / "rec.csv"
        matrix.write_text(CIRCULAR, encoding="utf-8")
        out = tmp_path / "report"
        with pytest.raises(CommandError) as refused:
            call_command(
                "validate_formula", "--ahp", str(matrix), "--out", str(out),
                stdout=StringIO(),
            )  # fmt: skip
        assert "Re-think these triads" in str(refused.value)
        assert not out.exists()

    def test_two_snapshots_need_a_date(self, tmp_path):
        from datetime import date

        corpus_repository("o/a", [{}], snapshot=date(2026, 9, 26))
        corpus_repository("o/a", [{}], snapshot=date(2026, 9, 27))
        matrix = tmp_path / "rec.csv"
        matrix.write_text(RECONCILED, encoding="utf-8")
        with pytest.raises(CommandError, match="more than one corpus snapshot"):
            call_command(
                "validate_formula", "--ahp", str(matrix), "--out", str(tmp_path / "r"),
                "--skip-reference", stdout=StringIO(),
            )  # fmt: skip

    def test_a_five_signal_matrix_is_sent_to_ahp_check(self, tmp_path):
        build_corpus_rows()
        matrix = tmp_path / "epss.csv"
        matrix.write_text(
            ",Deprecation,Severity,Count,Staleness,EPSS\n"
            "Deprecation,1,2,3,4,2\nSeverity,,1,2,3,1\nCount,,,1,2,1/2\n"
            "Staleness,,,,1,1/3\nEPSS,,,,,1\n",
            encoding="utf-8",
        )
        with pytest.raises(CommandError, match="ahp_check"):
            call_command(
                "validate_formula", "--ahp", str(matrix), "--out", str(tmp_path / "r"),
                "--skip-reference", stdout=StringIO(),
            )  # fmt: skip

    @responses.activate
    def test_deps_dev_is_asked_once_per_repository_and_then_cached(
        self, tmp_path, monkeypatch
    ):
        from apps.research.validation import reference

        # The pacing interval is a default argument, bound at import (§7.11),
        # so the sleep it calls is what a test replaces.
        monkeypatch.setattr(reference, "_sleep", lambda _seconds: None)
        build_corpus_rows()
        for name in ScanHistory.objects.values_list("repo_full_name", flat=True):
            owner, _, repo = name.lower().partition("/")
            responses.add(
                responses.GET,
                f"https://api.deps.dev/v3/projects/github.com%2F{owner}%2F{repo}",
                json={"scorecard": {"overallScore": 3.0 + len(repo) / 2, "checks": []}},
            )
        matrix = tmp_path / "rec.csv"
        matrix.write_text(RECONCILED, encoding="utf-8")
        out = tmp_path / "report"
        args = [
            "validate_formula",
            "--ahp",
            str(matrix),
            "--out",
            str(out),
            "--bootstrap",
            "20",
        ]

        call_command(*args, stdout=StringIO())
        first = len(responses.calls)
        call_command(*args, stdout=StringIO())

        assert first == 7
        assert len(responses.calls) == 7
        text = (out / "report.md").read_text(encoding="utf-8")
        assert "| v2-candidate (AHP) | Scorecard (independent) | all | 7/7 |" in text
        assert "deps.dev coverage: ok 7." in text


@pytest.mark.django_db
class TestScanAnchorsCommand:
    @responses.activate
    def test_it_reports_what_a_wp2_reviewer_checks_and_no_score(self, tmp_path):
        mock_metadata()
        mock_github()
        mock_registry()
        mock_osv()
        source = tmp_path / "wp2.csv"
        source.write_text(GOLDEN_ROW, encoding="utf-8")
        out = StringIO()

        call_command(
            "scan_anchors",
            "--anchors",
            str(source),
            "--out",
            str(tmp_path / "a"),
            stdout=out,
        )

        text = out.getvalue()
        assert (
            "acme/shop: lodash@4.17.19: seen in package.json (lockfile); flags: deprecated, vulnerable"
            in text
        )
        assert "[CHECK] repositories scanned: 1 of 2 (not: ghost/gone)" in text
        # File B's anchoring rule: no score, no classification.
        assert "safe" not in text.lower()
        assert "high_alert" not in text
        assert (tmp_path / "a" / anchors.SCAN_FILENAME).exists()

    def test_it_needs_the_research_token(self, tmp_path, settings):
        settings.GITHUB_API_PAT = ""
        source = tmp_path / "wp2.csv"
        source.write_text(GOLDEN_ROW, encoding="utf-8")
        with pytest.raises(CommandError, match="GITHUB_API_PAT"):
            call_command("scan_anchors", "--anchors", str(source), stdout=StringIO())
