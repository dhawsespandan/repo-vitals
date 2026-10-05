"""`validation/reference.py` — the two references and the cache that bounds them.

The deps.dev payloads here are trimmed from a live response
(`GET /v3/projects/github.com%2Fexpressjs%2Fexpress`, 2026-10-05): the
`scorecard` object carries `overallScore`, `date`, the Scorecard `version` and
a `checks` list, and an unknown project answers 404.
"""

from __future__ import annotations

import pytest
import responses

from apps.common import http
from apps.research.validation import panel, reference
from apps.scoring.normalize import Signals

API = "https://api.deps.dev/v3/projects"

EXPRESS = {
    "projectKey": {"id": "github.com/expressjs/express"},
    "starsCount": 69499,
    "scorecard": {
        "date": "2026-08-24T00:00:00Z",
        "repository": {"name": "github.com/expressjs/express"},
        "scorecard": {"version": "v5.5.1"},
        "checks": [
            {"name": "Maintained", "score": 10},
            {"name": "Code-Review", "score": 10},
        ],
        "overallScore": 8.5,
        "metadata": [],
    },
}


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(reference, "_sleep", lambda _seconds: None)


def client() -> reference.DepsDevClient:
    return reference.DepsDevClient(pace_seconds=0)


class TestTheClient:
    @responses.activate
    def test_a_scored_project(self):
        responses.add(
            responses.GET, f"{API}/github.com%2Fexpressjs%2Fexpress", json=EXPRESS
        )
        reading = client().project("expressjs/express")
        assert reading.status == reference.STATUS_OK
        assert reading.score == 8.5
        assert reading.scorecard_date == "2026-08-24T00:00:00Z"
        assert reading.scorecard_version == "v5.5.1"
        assert reading.checks == 2

    @responses.activate
    def test_the_key_is_lower_cased_and_encoded_as_one_segment(self):
        responses.add(
            responses.GET, f"{API}/github.com%2Fexpressjs%2Fexpress", json=EXPRESS
        )
        assert client().project("ExpressJS/Express").status == reference.STATUS_OK

    @responses.activate
    def test_a_project_deps_dev_has_not_scored(self):
        responses.add(
            responses.GET,
            f"{API}/github.com%2Fsmall%2Frepo",
            json={"projectKey": {"id": "github.com/small/repo"}},
        )
        assert client().project("small/repo").status == reference.STATUS_NO_SCORECARD

    @responses.activate
    def test_an_unknown_project(self):
        responses.add(responses.GET, f"{API}/github.com%2Fgone%2Frepo", status=404)
        assert client().project("gone/repo").status == reference.STATUS_NOT_FOUND

    @responses.activate
    def test_an_outage_is_not_a_fact_about_the_project(self):
        responses.add(responses.GET, f"{API}/github.com%2Fa%2Fb", status=503)
        assert client().project("a/b").status == reference.STATUS_UNAVAILABLE

    @responses.activate
    def test_a_name_that_is_not_owner_slash_repo_is_never_requested(self):
        reading = client().project("../../etc/passwd")
        assert reading.status == reference.STATUS_NOT_FOUND
        assert len(responses.calls) == 0

    def test_deps_dev_is_on_the_allowlist_and_nothing_wider_is(self):
        assert "api.deps.dev" in http.ALLOWED_HOSTS
        assert "deps.dev" not in http.ALLOWED_HOSTS


class TestTheCache:
    @responses.activate
    def test_a_second_run_asks_nothing(self, tmp_path):
        responses.add(
            responses.GET, f"{API}/github.com%2Fexpressjs%2Fexpress", json=EXPRESS
        )
        responses.add(responses.GET, f"{API}/github.com%2Fgone%2Frepo", status=404)
        cache = tmp_path / reference.CACHE_FILENAME
        names = ["expressjs/express", "gone/repo"]

        first = reference.fetch_scorecards(names, cache, client())
        calls = len(responses.calls)
        second = reference.fetch_scorecards(names, cache, client())

        assert calls == 2
        assert len(responses.calls) == 2
        assert first == second
        assert second["gone/repo"].status == reference.STATUS_NOT_FOUND

    @responses.activate
    def test_an_outage_is_retried_next_time(self, tmp_path):
        cache = tmp_path / reference.CACHE_FILENAME
        responses.add(responses.GET, f"{API}/github.com%2Fa%2Fb", status=503)
        assert reference.fetch_scorecards(["a/b"], cache, client())["a/b"].status == (
            reference.STATUS_UNAVAILABLE
        )

        responses.replace(responses.GET, f"{API}/github.com%2Fa%2Fb", json=EXPRESS)
        assert reference.fetch_scorecards(["a/b"], cache, client())["a/b"].score == 8.5

    @responses.activate
    def test_a_torn_cache_line_costs_only_that_line(self, tmp_path):
        cache = tmp_path / reference.CACHE_FILENAME
        responses.add(
            responses.GET, f"{API}/github.com%2Fexpressjs%2Fexpress", json=EXPRESS
        )
        reference.fetch_scorecards(["expressjs/express"], cache, client())
        with cache.open("a", encoding="utf-8") as handle:
            handle.write('{"full_name": "half/writ')

        again = reference.fetch_scorecards(["expressjs/express"], cache, client())
        assert again["expressjs/express"].score == 8.5
        assert len(responses.calls) == 1


def repo(*occurrences: tuple[bool, int, str | None]) -> panel.PanelRepository:
    from decimal import Decimal

    built = panel.PanelRepository(
        scan_history_id="x",
        github_repo_id=1,
        full_name="a/b",
        owner="a",
        ecosystems="npm",
        sampling_weight=1.0,
        stored_score=Decimal(0),
        stored_classification="safe",
        stored_version="v1",
    )
    built.occurrences = [
        panel.Occurrence(
            ecosystem="npm",
            is_unassessable=unassessable,
            signals=Signals(
                vulnerability_count=vulns,
                cvss_max=Decimal(cvss) if cvss is not None else None,
            ),
        )
        for unassessable, vulns, cvss in occurrences
    ]
    return built


class TestTheOsvRollup:
    def test_the_worst_advisory_wins(self):
        assert reference.osv_rollup(repo((False, 1, "5.3"), (False, 2, "9.8"))) == 9.8

    def test_a_clean_repository_rolls_up_to_zero(self):
        assert reference.osv_rollup(repo((False, 0, None))) == 0.0

    def test_an_unscored_advisory_counts_at_the_placeholder(self):
        """§5.2's 5.0, the same number the formula used for it."""
        assert reference.osv_rollup(repo((False, 1, None))) == 5.0

    def test_unassessable_rows_are_not_read(self):
        assert reference.osv_rollup(repo((True, 3, "9.8"))) == 0.0

    def test_health_runs_the_same_way_as_the_score(self):
        assert reference.osv_health(repo((False, 1, "9.8"))) == pytest.approx(0.2)
        assert reference.osv_health(repo()) == 10.0


def test_both_caveats_name_their_limitation():
    """File C L1 and L2 travel with the numbers, by name."""
    assert "L1" in reference.OSV_CAVEAT
    assert "Circular" in reference.OSV_CAVEAT
    assert "L2" in reference.SCORECARD_CAVEAT
