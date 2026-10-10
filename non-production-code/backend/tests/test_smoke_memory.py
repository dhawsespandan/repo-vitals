"""The memory smoke test has to keep working, so it gets a test of its own.

Its whole value is being runnable in week one and again in Phase 8 with Chroma
loaded (§8). A command that quietly rots between those two runs answers the
feasibility question with a stale number. The network and model steps are
skipped here; CI is not the place to download an ONNX model.

Since §8.15 the command reports two numbers, and the distinction is the reason
Phase 8's first production generation was killed: the highest *settled* mark is
what it used to report as a peak, and the observed *peak* is what a memory cap
actually acts on. Both are asserted, because a command that silently stopped
sampling would read exactly like one whose peak happened to equal its settled
figure.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.common.http import UpstreamUnavailable


def offline(monkeypatch) -> None:
    """Keep CI off the network.

    Patched at `smoke_memory`'s own reference to the client rather than inside
    `apps.common.http`: the command reaches the registry through that module
    from Phase 9 (§9.9), and patching the shared client would silence every
    other test in the process that expects `responses` to be the thing
    refusing.
    """
    import apps.accounts.management.commands.smoke_memory as smoke

    def refuse(*args, **kwargs):
        raise UpstreamUnavailable("network disabled in tests")

    monkeypatch.setattr(smoke.http, "get_json", refuse)


@pytest.mark.django_db
def test_smoke_memory_runs_and_reports_a_peak(monkeypatch):
    offline(monkeypatch)

    out = StringIO()
    call_command("smoke_memory", "--skip-embedding", stdout=out)
    output = out.getvalue()

    assert "baseline (django loaded)" in output
    assert "after request cycle" in output
    assert "after background thread" in output
    assert "highest settled:" in output
    assert "observed peak:" in output
    # Every mark line carries the running peak, so a dead sampler is visible
    # rather than merely unmentioned.
    assert "(peak so far" in output


@pytest.mark.django_db
def test_smoke_memory_emits_machine_readable_marks(monkeypatch):
    import json

    offline(monkeypatch)

    out = StringIO()
    call_command("smoke_memory", "--skip-embedding", "--json", stdout=out)
    output = out.getvalue()
    payload = json.loads(output[output.index("\n{\n") :])

    assert payload["peak_mb"] > 0
    assert payload["highest_settled_mb"] > 0
    # The peak can never be below the highest settled mark: it is sampled
    # continuously and the marks are a subset of what it saw.
    assert payload["peak_mb"] >= payload["highest_settled_mb"]
    assert "baseline (django loaded)" in payload["marks_mb"]


def test_the_embedded_corpus_is_a_changelog_s_worth_of_tokens():
    """§14.15: the corpus used to be forty copies of "release note text", about
    210 tokens a chunk, and passed at a batch size that a real changelog took
    over 512 MB. The peak follows tokens, not characters, so the corpus has to
    be as dense as `request`'s release notes: chunker-sized passages of PR-link
    lines, and as many of them as that changelog has."""
    from apps.accounts.management.commands.smoke_memory import _changelog_chunk
    from apps.reports.rag.chunker import TARGET_CHARS

    chunk = _changelog_chunk(7)

    assert abs(len(chunk) - TARGET_CHARS) <= 100
    assert chunk.count("https://github.com/") == 12
    assert len({_changelog_chunk(index) for index in range(100)}) == 100
