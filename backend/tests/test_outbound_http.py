"""`apps.common.http` — the single outbound path (§10 Phase 2, §11 SSRF).

These tests exist because the allowlist is the only thing standing between a
pasted URL and an arbitrary outbound request. The redirect cases matter most:
a check that runs once, on the first URL, is not a control at all.
"""

from __future__ import annotations

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from apps.common import http


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    """Exercise the retry paths without spending their backoff in real time."""
    slept: list[float] = []
    monkeypatch.setattr(http, "_sleep", slept.append)
    return slept


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    """`responses` patches the adapter, so a session cached across tests lies."""
    monkeypatch.setattr(http, "_local", type(http._local)())


class TestAllowlist:
    def test_a_host_outside_the_allowlist_is_refused(self):
        with pytest.raises(http.DisallowedHost):
            http.get_json("https://evil.example.com/repos/o/r")

    def test_plain_http_is_refused_even_on_an_allowlisted_host(self):
        with pytest.raises(http.DisallowedHost):
            http.get_json("http://api.github.com/repos/o/r")

    @responses.activate
    def test_a_redirect_off_the_allowlist_is_refused(self):
        """The whole reason redirects are followed by hand.

        `requests` would follow this transparently and hand back the attacker's
        response as though it came from GitHub.
        """
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            status=302,
            headers={"Location": "https://evil.example.com/steal"},
        )

        with pytest.raises(http.DisallowedHost):
            http.get_json("https://api.github.com/repos/o/r")

    @responses.activate
    def test_a_redirect_within_the_allowlist_is_followed(self):
        """Renamed repositories legitimately 301, so refusing outright is wrong."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/old/name",
            status=301,
            headers={"Location": "https://api.github.com/repos/new/name"},
        )
        responses.add(
            responses.GET,
            "https://api.github.com/repos/new/name",
            json={"id": 1},
            status=200,
        )

        assert http.get_json("https://api.github.com/repos/old/name").data == {"id": 1}

    @responses.activate
    def test_a_redirect_loop_gives_up(self):
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            status=302,
            headers={"Location": "https://api.github.com/repos/o/r"},
        )

        with pytest.raises(http.UpstreamUnavailable):
            http.get_json("https://api.github.com/repos/o/r")


class TestStatusMapping:
    @responses.activate
    def test_404_is_not_found(self):
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={}, status=404
        )
        with pytest.raises(http.UpstreamNotFound):
            http.get_json("https://api.github.com/repos/o/r")

    @responses.activate
    def test_409_is_conflict(self):
        """GitHub's answer for a repository with no commits."""
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={}, status=409
        )
        with pytest.raises(http.UpstreamConflict):
            http.get_json("https://api.github.com/repos/o/r")

    @responses.activate
    def test_a_plain_403_is_forbidden_not_a_rate_limit(self):
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={}, status=403
        )
        with pytest.raises(http.UpstreamForbidden):
            http.get_json("https://api.github.com/repos/o/r")


class TestRateLimits:
    @responses.activate
    def test_the_primary_limit_is_a_403_with_remaining_zero(self):
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            json={},
            status=403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1756500000"},
        )

        with pytest.raises(http.UpstreamRateLimited):
            http.get_json("https://api.github.com/repos/o/r")

    @responses.activate
    def test_a_secondary_limit_is_a_403_carrying_retry_after(self):
        """No remaining counter — GitHub signals this one with Retry-After."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            json={},
            status=403,
            headers={"Retry-After": "600"},
        )

        with pytest.raises(http.UpstreamRateLimited) as caught:
            http.get_json("https://api.github.com/repos/o/r")
        assert caught.value.retry_after == 600

    @responses.activate
    def test_a_long_retry_after_is_not_waited_out(self, no_real_sleeping):
        """A worker thread must not be parked for ten minutes (§3, §8)."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            json={},
            status=429,
            headers={"Retry-After": "600"},
        )

        with pytest.raises(http.UpstreamRateLimited):
            http.get_json("https://api.github.com/repos/o/r")
        assert no_real_sleeping == []

    @responses.activate
    def test_a_short_retry_after_is_waited_out_and_retried(self, no_real_sleeping):
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            json={},
            status=429,
            headers={"Retry-After": "1"},
        )
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={"id": 7}, status=200
        )

        assert http.get_json("https://api.github.com/repos/o/r").data == {"id": 7}
        assert no_real_sleeping == [1.0]


class TestRetries:
    @responses.activate
    def test_a_5xx_is_retried_then_reported_unavailable(self, no_real_sleeping):
        for _ in range(http.MAX_RETRIES + 1):
            responses.add(
                responses.GET, "https://api.github.com/repos/o/r", json={}, status=502
            )

        with pytest.raises(http.UpstreamUnavailable):
            http.get_json("https://api.github.com/repos/o/r")
        assert len(no_real_sleeping) == http.MAX_RETRIES

    @responses.activate
    def test_a_transient_5xx_recovers(self):
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={}, status=503
        )
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={"id": 3}, status=200
        )

        assert http.get_json("https://api.github.com/repos/o/r").data == {"id": 3}

    @responses.activate
    def test_a_connection_error_is_retried(self, no_real_sleeping):
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            body=RequestsConnectionError("dns failure"),
        )
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={"id": 5}, status=200
        )

        assert http.get_json("https://api.github.com/repos/o/r").data == {"id": 5}
        assert no_real_sleeping == [http.BACKOFF_BASE_SECONDS]

    @responses.activate
    def test_a_404_is_never_retried(self):
        """A 4xx is an answer, not a failure — retrying it just spends quota."""
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={}, status=404
        )

        with pytest.raises(http.UpstreamNotFound):
            http.get_json("https://api.github.com/repos/o/r")
        assert len(responses.calls) == 1


class TestRequestShape:
    @responses.activate
    def test_the_token_travels_as_a_bearer_header_and_is_never_in_the_url(self):
        responses.add(
            responses.GET, "https://api.github.com/repos/o/r", json={"id": 1}, status=200
        )

        http.get_json("https://api.github.com/repos/o/r", token="gho_secrettoken")

        request = responses.calls[0].request
        assert request.headers["Authorization"] == "Bearer gho_secrettoken"
        assert "gho_secrettoken" not in request.url

    @responses.activate
    def test_a_non_json_body_is_reported_rather_than_returned(self):
        responses.add(
            responses.GET,
            "https://api.github.com/repos/o/r",
            body="<html>maintenance</html>",
            status=200,
        )

        with pytest.raises(http.UpstreamUnavailable):
            http.get_json("https://api.github.com/repos/o/r")
