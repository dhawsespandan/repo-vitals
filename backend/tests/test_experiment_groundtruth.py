"""S3's ground truth (§10 Phase 13 commit 1, D15).

The extraction is checked where it can be wrong in a way nobody would see:
a successor that is an English word, a fix that a second advisory re-opens, a
later-but-safe version marked wrong, and a TARGET block that drifts from the
one the production graph builds.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
import responses
from django.core.management import CommandError, call_command

from apps.common import http
from apps.research.experiment import groundtruth as gt
from tests.corpus_rows import SNAPSHOT, corpus_repository

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def fixture(rel: str) -> dict:
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def quiet_network(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)


# ── successors ─────────────────────────────────────────────────────────────


class TestSuccessorParsing:
    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            ("Deprecated. Use `node-fetch` instead.", [("node-fetch", "use_x_instead")]),
            ("This package has been replaced by axios.", [("axios", "replaced_by_x")]),
            ("Please migrate to @babel/core", [("@babel/core", "migrate_to_x")]),
            ("Deprecated in favour of 'got'.", [("got", "in_favor_of_x")]),
            ("superseded by undici", [("undici", "superseded_by_x")]),
        ],
    )
    def test_file_as_phrasings_and_their_synonyms(self, reason, expected):
        assert gt.successor_candidates(reason, "npm", "old-lib") == expected

    @pytest.mark.parametrize(
        "reason",
        [
            "Use native fetch instead.",
            "use the URLSearchParams API instead",
            "request has been deprecated, see https://github.com/request/request/issues/3142",
            "Please migrate to 5.0.0",
            "this library is no longer supported",
            "Use old-lib instead",  # its own name
        ],
    )
    def test_things_that_are_not_successors(self, reason):
        assert gt.successor_candidates(reason, "npm", "old-lib") == []

    def test_npm_refuses_upper_case_names(self):
        assert gt.successor_candidates("Use Axios instead", "npm", "x") == []
        assert gt.successor_candidates("Use Requests instead", "pypi", "x") == [
            ("Requests", "use_x_instead")
        ]

    def test_pypi_names_compare_normalised(self):
        assert gt.successor_candidates("Migrate to old_pkg", "pypi", "Old-Pkg") == []
        assert gt.normalize_name("pypi", "Zope.Interface") == "zope-interface"


# ── OSV ranges ─────────────────────────────────────────────────────────────


def advisory(osv_id: str, *intervals: dict, versions=()) -> gt.AdvisoryRanges:
    return gt.AdvisoryRanges(
        osv_id=osv_id,
        cve_id=None,
        intervals=tuple(gt.Interval(**interval) for interval in intervals),
        versions=tuple(versions),
    )


class TestRanges:
    def test_events_become_intervals(self):
        found = gt.intervals_from_events(
            [
                {"introduced": "0"},
                {"fixed": "1.2.0"},
                {"introduced": "2.0.0"},
                {"last_affected": "2.1.0"},
                {"introduced": "3.0.0"},
            ]
        )
        assert found == [
            gt.Interval(introduced="0", fixed="1.2.0"),
            gt.Interval(introduced="2.0.0", last_affected="2.1.0"),
            gt.Interval(introduced="3.0.0"),
        ]

    @pytest.mark.parametrize(
        ("version", "inside"),
        [
            ("0.9.0", True),
            ("1.2.0", False),
            ("2.1.0", True),
            ("2.1.1", False),
            ("9.0.0", True),
        ],
    )
    def test_membership_honours_each_bound(self, version, inside):
        intervals = gt.intervals_from_events(
            [
                {"introduced": "0"},
                {"fixed": "1.2.0"},
                {"introduced": "2.0.0"},
                {"last_affected": "2.1.0"},
                {"introduced": "3.0.0"},
            ]
        )
        assert any(i.contains("npm", version) for i in intervals) is inside

    def test_an_unreadable_bound_is_unknown_not_false(self):
        assert (
            gt.Interval(introduced="0", fixed="banana").contains("npm", "1.0.0") is None
        )

    def test_only_this_packages_semver_and_ecosystem_ranges_count(self):
        document = {
            "id": "X",
            "affected": [
                {"package": {"name": "other"}, "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}]}]},
                {"package": {"name": "Django"}, "ranges": [
                    {"type": "GIT", "events": [{"introduced": "abc"}]},
                    {"type": "ECOSYSTEM", "events": [{"introduced": "1.4"}, {"fixed": "1.8.10"}]},
                ]},
            ],
        }  # fmt: skip
        found = gt.advisory_ranges(document, "pypi", "django")
        assert found.intervals == (gt.Interval(introduced="1.4", fixed="1.8.10"),)
        assert (
            gt.advisory_ranges({**document, "withdrawn": "2024-01-01"}, "pypi", "django")
            is None
        )


class TestTheAnswer:
    def test_the_minimum_fix_is_the_largest_advisory_fix(self):
        """lodash 4.17.19 under the two fixture advisories: fixed at 4.17.20 and
        at 4.17.21. Only 4.17.21 escapes both."""
        ranges = [
            gt.advisory_ranges(
                fixture("osv/vuln_lodash_command_injection.json"), "npm", "lodash"
            ),
            gt.advisory_ranges(
                fixture("osv/vuln_lodash_prototype_pollution.json"), "npm", "lodash"
            ),
        ]
        assert gt.minimum_fix("npm", "4.17.19", ranges) == ("4.17.21", None)

    def test_a_fix_another_advisory_reopens_is_not_the_answer(self):
        """B affects 1.0.0 (fixed in 1.1.0) and again from 1.2.0 to 1.3.0, so A's
        fix at 1.2.0 walks straight into B's second interval."""
        ranges = [
            advisory("A", {"introduced": "0", "fixed": "1.2.0"}),
            advisory(
                "B",
                {"introduced": "0", "fixed": "1.1.0"},
                {"introduced": "1.2.0", "fixed": "1.3.0"},
            ),
        ]
        assert gt.minimum_fix("npm", "1.0.0", ranges) == ("1.3.0", None)
        assert gt.is_safe_version("npm", "1.2.0", "1.0.0", ranges) is False

    def test_only_advisories_on_the_resolved_version_are_in_scope(self):
        """An advisory OSV does not return for the resolved version is not part
        of the item (File A: "minimum fixed version > resolved"), and TARGET
        never shows it to the model either. Recorded as a scope choice."""
        ranges = [
            advisory("A", {"introduced": "0", "fixed": "1.2.0"}),
            advisory("C", {"introduced": "1.2.0", "fixed": "1.3.0"}),
        ]
        assert gt.minimum_fix("npm", "1.0.0", ranges) == ("1.2.0", None)

    def test_no_fix_means_no_item(self):
        ranges = [
            gt.advisory_ranges(fixture("osv/vuln_no_severity.json"), "npm", "left-pad")
        ]
        assert gt.minimum_fix("npm", "1.3.0", ranges) == (None, gt.DROP_NO_FIX)

    def test_a_version_osv_no_longer_flags_is_dropped(self):
        ranges = [advisory("A", {"introduced": "0", "fixed": "1.0.0"})]
        assert gt.minimum_fix("npm", "2.0.0", ranges) == (None, gt.DROP_NOT_AFFECTED)

    @pytest.mark.parametrize(
        ("version", "safe"),
        [
            ("4.17.21", True),
            ("4.17.22", True),  # later and still safe: correct, not "not the minimum"
            ("4.17.20", False),  # escapes one advisory, not both
            ("4.17.18", False),  # a downgrade
            ("4.17.19", False),  # no change
            ("latest", None),  # unreadable
        ],
    )
    def test_any_safe_upgrade_is_correct(self, version, safe):
        ranges = [
            advisory("A", {"introduced": "0", "fixed": "4.17.21"}),
            advisory("B", {"introduced": "0", "fixed": "4.17.20"}),
        ]
        assert gt.is_safe_version("npm", version, "4.17.19", ranges) is safe

    def test_an_explicitly_listed_version_is_affected(self):
        ranges = [advisory("A", versions=["5.0.0"])]
        assert gt.is_safe_version("npm", "5.0.0", "4.0.0", ranges) is False
        assert gt.is_safe_version("npm", "5.0.1", "4.0.0", ranges) is True


# ── extraction over the corpus ─────────────────────────────────────────────

DJANGO_ADVISORY = {
    "id": "PYSEC-TEST-1",
    "aliases": ["CVE-2016-0001"],
    "summary": "test",
    "affected": [
        {
            "package": {"name": "Django", "ecosystem": "PyPI"},
            "ranges": [
                {
                    "type": "ECOSYSTEM",
                    "events": [{"introduced": "1.4"}, {"fixed": "1.8.10"}],
                }
            ],
        }
    ],
}


def mock_osv() -> None:
    found = {
        ("lodash", "4.17.19"): ["GHSA-35jh-r3h4-6jhm", "GHSA-p6mc-m468-83gg"],
        ("left-pad", "1.3.0"): ["GHSA-0000-0000-0000"],
        ("django", "1.4.22"): ["PYSEC-TEST-1"],
    }

    def answer(request):
        queries = json.loads(request.body)["queries"]
        results = []
        for query in queries:
            ids = found.get((query["package"]["name"], query["version"]), [])
            results.append({"vulns": [{"id": i} for i in ids]} if ids else {})
        return (200, {}, json.dumps({"results": results}))

    responses.add_callback(
        responses.POST, "https://api.osv.dev/v1/querybatch", callback=answer
    )
    for name in (
        "vuln_lodash_command_injection",
        "vuln_lodash_prototype_pollution",
        "vuln_no_severity",
    ):
        document = fixture(f"osv/{name}.json")
        responses.add(
            responses.GET, f"https://api.osv.dev/v1/vulns/{document['id']}", json=document
        )
    responses.add(
        responses.GET, "https://api.osv.dev/v1/vulns/PYSEC-TEST-1", json=DJANGO_ADVISORY
    )


def mock_registries() -> None:
    responses.add(
        responses.GET,
        "https://registry.npmjs.org/express",
        json=fixture("npm/express.json"),
    )
    responses.add(responses.GET, "https://registry.npmjs.org/ghost-lib", status=404)
    responses.add(
        responses.GET,
        "https://pypi.org/pypi/requests/json",
        json=fixture("pypi/requests.json"),
    )


def build_rows() -> None:
    corpus_repository(
        "o/one",
        [
            {"package": "lodash", "version": "4.17.19", "vulns": 2, "cvss": 9.1},
            {"package": "left-pad", "version": "1.3.0", "vulns": 1},
            {"package": "old-lib", "version": "1.0.0", "deprecated": True,
             "reason": "Deprecated. Use `express` instead."},
            {"package": "bad-lib", "version": "1.0.0", "deprecated": True, "reason": "replaced by ghost-lib"},
            {"package": "request", "version": "2.88.2", "deprecated": True,
             "reason": "request has been deprecated, see https://github.com/request/request/issues/3142"},
            {"package": "clean", "version": "1.0.0"},
        ],
    )  # fmt: skip
    corpus_repository(
        "o/two",
        [
            {"package": "lodash", "version": "4.17.19", "vulns": 2, "cvss": 9.1},
            {"ecosystem": "pypi", "package": "django", "version": "1.4.22", "vulns": 1, "cvss": 7.5},
            {"ecosystem": "pypi", "package": "oldpkg", "version": "1.0", "deprecated": True,
             "reason": "Please migrate to requests"},
        ],
    )  # fmt: skip


@pytest.mark.django_db
class TestExtraction:
    @responses.activate
    def test_both_case_types_with_every_drop_counted(self):
        build_rows()
        mock_osv()
        mock_registries()

        candidates = gt.corpus_candidates(SNAPSHOT)
        extraction = gt.extract(candidates, snapshot_date=SNAPSHOT)

        by_key = {(i["package"], i["case_type"]): i for i in extraction.items}
        lodash = by_key[("lodash", gt.CVE_FIX)]
        assert lodash["ground_truth"]["target_version"] == "4.17.21"
        assert lodash["corpus"]["repositories"] == 2  # pooled across the corpus
        assert (
            by_key[("django", gt.CVE_FIX)]["ground_truth"]["target_version"] == "1.8.10"
        )
        assert (
            by_key[("old-lib", gt.DEPRECATION_REPLACEMENT)]["ground_truth"]["successor"]
            == "express"
        )
        assert by_key[("oldpkg", gt.DEPRECATION_REPLACEMENT)]["ground_truth"][
            "pattern"
        ] == ("migrate_to_x")

        npm_cve = extraction.coverage[("npm", gt.CVE_FIX)]
        assert npm_cve == {"candidates": 2, "extracted": 1, gt.DROP_NO_FIX: 1}
        npm_rep = extraction.coverage[("npm", gt.DEPRECATION_REPLACEMENT)]
        assert npm_rep == {
            "candidates": 3,
            "extracted": 1,
            gt.DROP_NOT_IN_REGISTRY: 1,
            gt.DROP_NO_SUCCESSOR: 1,
        }

    @responses.activate
    def test_item_ids_are_stable(self):
        build_rows()
        mock_osv()
        mock_registries()
        first = gt.extract(gt.corpus_candidates(SNAPSHOT), snapshot_date=SNAPSHOT)
        second = gt.extract(gt.corpus_candidates(SNAPSHOT), snapshot_date=SNAPSHOT)
        assert [i["item_id"] for i in first.items] == [i["item_id"] for i in second.items]
        assert all(i["item_id"].startswith("S3-") for i in first.items)

    @responses.activate
    def test_the_target_block_is_the_one_production_builds(self, user):
        """Condition C is the production agent answering the production prompt
        only if TARGET has the same shape. Pinned to `graph.load_context`."""
        from apps.reports.agent import graph
        from apps.scanning.models import DependencyVulnerability
        from tests.factories import DependencyOccurrenceFactory

        build_rows()
        mock_osv()
        mock_registries()
        item = next(
            i
            for i in gt.extract(
                gt.corpus_candidates(SNAPSHOT), snapshot_date=SNAPSHOT
            ).items
            if i["package"] == "lodash"
        )

        occurrence = DependencyOccurrenceFactory(
            is_deprecated=True,
            deprecation_reason="x",
            vulnerability_count=1,
            staleness_days=10,
        )
        DependencyVulnerability.objects.create(dependency=occurrence, osv_id="GHSA-1")
        produced = graph.load_context({"occurrence": occurrence})

        lodash_target = {**item["target"], "deprecation_reason": "x"}
        assert set(lodash_target) == set(produced["target"])
        assert set(item["target"]["advisories"][0]) == set(
            produced["target"]["advisories"][0]
        )
        assert set(item["context_rows"][0]) == set(produced["context"]["rows"][0])
        # The fixed version is derived the way the scanner derives it.
        assert {a["fixed_version"] for a in item["target"]["advisories"]} == {
            "4.17.21",
            "4.17.20",
        }


# ── the sample ─────────────────────────────────────────────────────────────


def fake_items(ecosystem: str, case: str, count: int) -> list[dict]:
    return [
        {
            "item_id": f"S3-{ecosystem}-{case}-{n:03d}",
            "ecosystem": ecosystem,
            "case_type": case,
        }
        for n in range(count)
    ]


class TestTheSample:
    def test_half_per_ecosystem_and_the_share_within(self):
        items = (
            fake_items("npm", gt.CVE_FIX, 100)
            + fake_items("npm", gt.DEPRECATION_REPLACEMENT, 100)
            + fake_items("pypi", gt.CVE_FIX, 100)
            + fake_items("pypi", gt.DEPRECATION_REPLACEMENT, 100)
        )
        selected, quotas = gt.stratified_sample(
            items, size=150, replacement_share=0.4, seed=1
        )
        assert len(selected) == 150
        taken = {(q.ecosystem, q.case_type): q.taken for q in quotas}
        assert taken == {
            ("npm", gt.DEPRECATION_REPLACEMENT): 30,
            ("npm", gt.CVE_FIX): 45,
            ("pypi", gt.DEPRECATION_REPLACEMENT): 30,
            ("pypi", gt.CVE_FIX): 45,
        }

    def test_a_thin_stratum_hands_its_share_over_and_says_so(self):
        """PyPI's replacement stratum is expected to be thin (File C L7)."""
        items = (
            fake_items("npm", gt.CVE_FIX, 80)
            + fake_items("npm", gt.DEPRECATION_REPLACEMENT, 80)
            + fake_items("pypi", gt.CVE_FIX, 80)
            + fake_items("pypi", gt.DEPRECATION_REPLACEMENT, 4)
        )
        selected, quotas = gt.stratified_sample(items, size=150, seed=1)
        pypi = {q.case_type: q for q in quotas if q.ecosystem == "pypi"}
        assert pypi[gt.DEPRECATION_REPLACEMENT].taken == 4
        assert pypi[gt.DEPRECATION_REPLACEMENT].shortfall == 34
        assert pypi[gt.CVE_FIX].taken == 71
        assert len(selected) == 150

    def test_the_sample_is_seeded(self):
        items = fake_items("npm", gt.CVE_FIX, 200) + fake_items("pypi", gt.CVE_FIX, 200)
        first, _ = gt.stratified_sample(items, seed=3)
        second, _ = gt.stratified_sample(list(reversed(items)), seed=3)
        assert [i["item_id"] for i in first] == [i["item_id"] for i in second]


# ── the command ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTheCommand:
    @responses.activate
    def test_it_writes_the_set_the_meta_and_the_report(self, tmp_path):
        build_rows()
        mock_osv()
        mock_registries()
        out = tmp_path / "gt"
        stdout = StringIO()
        call_command(
            "extract_ground_truth", "--out", str(out), "--size", "4", stdout=stdout
        )

        labelled = [
            json.loads(line)
            for line in (out / "labelled_set.jsonl").read_text().splitlines()
        ]
        assert len(labelled) == 4
        meta = json.loads((out / "labelled_set_meta.json").read_text())
        assert meta["snapshot_date"] == SNAPSHOT.isoformat()
        report = (out / "extraction_report.md").read_text(encoding="utf-8")
        assert "| npm | cve_fix | 2 | 1 | 50% | no_fixed_version 1 |" in report
        assert "The answer is in TARGET" in report
        # decisions §13.13: npm's shown fix is the answer; PyPI's is not.
        assert "## Items whose answer TARGET already shows" in report
        assert "| npm | cve_fix | 1 | 1 | 0 |" in report
        assert "| pypi | cve_fix | 1 | 0 | 1 |" in report

    @responses.activate
    def test_a_frozen_set_is_not_overwritten(self, tmp_path):
        build_rows()
        out = tmp_path / "gt"
        out.mkdir()
        (out / "labelled_set.jsonl").write_text("{}\n")
        with pytest.raises(CommandError, match="frozen once WP-8 starts"):
            call_command("extract_ground_truth", "--out", str(out), stdout=StringIO())
        assert (out / "labelled_set.jsonl").read_text() == "{}\n"

    @responses.activate
    def test_a_sample_is_an_estimate_and_writes_no_set(self, tmp_path):
        build_rows()
        mock_osv()
        mock_registries()
        out = tmp_path / "gt"
        call_command(
            "extract_ground_truth", "--out", str(out), "--sample", "3", stdout=StringIO()
        )
        assert not (out / "labelled_set.jsonl").exists()
        assert "a seeded sample of 3" in (out / "extraction_report.md").read_text(
            encoding="utf-8"
        )

    @responses.activate
    def test_a_shortfall_is_flagged_early(self, tmp_path):
        build_rows()
        mock_osv()
        mock_registries()
        out = tmp_path / "gt"
        stdout = StringIO()
        call_command("extract_ground_truth", "--out", str(out), stdout=stdout)
        assert "SHORTFALL" in stdout.getvalue()
        assert "SHORTFALL" in (out / "extraction_report.md").read_text(encoding="utf-8")
