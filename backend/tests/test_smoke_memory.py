"""The memory smoke test has to keep working, so it gets a test of its own.

Its whole value is being runnable in week one and again in Phase 8 with Chroma
loaded (§8). A command that quietly rots between those two runs answers the
feasibility question with a stale number. The network and model steps are
skipped here; CI is not the place to download an ONNX model.
"""

from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_smoke_memory_runs_and_reports_a_peak(monkeypatch):
    # Keep CI offline: neuter the registry fetch, skip the embedding step.
    import apps.accounts.management.commands.smoke_memory as smoke

    monkeypatch.setattr(
        smoke.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(OSError("network disabled in tests")),
    )

    out = StringIO()
    call_command("smoke_memory", "--skip-embedding", stdout=out)
    output = out.getvalue()

    assert "baseline (django loaded)" in output
    assert "after request cycle" in output
    assert "after background thread" in output
    assert "peak RSS:" in output


@pytest.mark.django_db
def test_smoke_memory_emits_machine_readable_marks(monkeypatch):
    import json

    import apps.accounts.management.commands.smoke_memory as smoke

    monkeypatch.setattr(
        smoke.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(OSError("network disabled in tests")),
    )

    out = StringIO()
    call_command("smoke_memory", "--skip-embedding", "--json", stdout=out)
    output = out.getvalue()
    payload = json.loads(output[output.index("\n{\n") :])

    assert payload["peak_mb"] > 0
    assert "baseline (django loaded)" in payload["marks_mb"]
