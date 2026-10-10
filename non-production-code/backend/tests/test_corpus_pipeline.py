"""The three commands, run end to end — Phase 11's pilot, in miniature.

Everything else in this phase's suite calls the library functions directly.
That leaves the layer WP-4 and WP-5 actually type at untested: argument
parsing, path resolution, the `--out` default, where the guard is wrapped, and
whether the three commands' file contracts line up — `build_corpus` writes a
manifest that `scan_corpus` opens, and `corpus_report` joins strata back to
it. A break in any of those passes every unit test and fails the first real
run, an hour and several thousand API calls in.

So this runs the pipeline the way §10 Phase 11's acceptance describes it:
`build_corpus` over a small frame, `scan_corpus` over what it admitted,
`corpus_report` over what that scored. Three repositories rather than twenty,
against stubbed HTTP rather than GitHub — the shape is the same and the live
20-repo run is still WP-4's.
"""

from __future__ import annotations

import base64
import json
import pathlib
from io import StringIO

import pytest
import responses
from django.core.management import call_command

from apps.common import http
from apps.research import github as github_module
from apps.research.charts import FLAGGED_RATE_FILENAME, HISTOGRAM_FILENAME
from apps.research.corpus import MANIFEST_FILENAME, STRATA_REPORT_FILENAME
from apps.research.corpus_scan import REPORT_FILENAME
from apps.research.models import DataSource, DependencyHistory, ScanHistory
from apps.scanning.models import DependencyOccurrence, ManifestFile, Package, ScanRun
from tests.test_corpus_report import MATPLOTLIB_ERROR

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

#: One language, one star band, one pushed band, one created band — one cell.
#: The grid's combinatorics are `test_corpus_builder.py`'s subject; what this
#: file is about is the three commands agreeing on their files.
PILOT_FRAME = """
languages:
  - {name: javascript, ecosystem: npm, qualifier: "language:JavaScript"}
stars:
  - {name: "5-20", min: 5, max: 20}
pushed:
  - {name: "lt6", min_months: 0, max_months: 6, oversample: 1.0}
created:
  - {name: "le2015", min_year: null, max_year: 2015}
qualifiers: ["fork:false", "archived:false"]
search: {sort: stars, order: desc, per_page: 10, results_cap: 50}
verification: {registry_probe_limit: 1}
admission:
  candidate_multiplier: 1.0
  ecosystem_share: {npm: 1.0}
"""

MANIFESTS = {
    "sha-alpha": {"express": "^4.17.0", "lodash": "^4.17.0"},
    "sha-beta": {"react": "^18.0.0"},
    "sha-gamma": {"typescript": "^5.0.0", "left-pad": "^1.3.0"},
}
REPOS = [
    ("alpha", "sha-alpha"),
    ("beta", "sha-beta"),
    ("gamma", "sha-gamma"),
]


@pytest.fixture(autouse=True)
def fresh_session(monkeypatch):
    monkeypatch.setattr(http, "_local", type(http._local)())


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    monkeypatch.setattr(http, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(github_module, "_sleep", lambda _seconds: None)


@pytest.fixture(autouse=True)
def research_pat(settings):
    settings.GITHUB_API_PAT = "ghp_research_token"


def _blob(payload: bytes) -> dict:
    return {
        "encoding": "base64",
        "size": len(payload),
        "content": base64.b64encode(payload).decode(),
    }


def mock_github() -> None:
    """Search, tree and blob for three repositories, plus the registries."""
    items = [
        {
            "id": 1000 + index,
            "name": name,
            "full_name": f"corpus/{name}",
            "owner": {"login": "corpus", "id": 77},
            "default_branch": "main",
            "stargazers_count": 10 + index,
            "pushed_at": "2026-08-01T00:00:00Z",
            "created_at": "2014-01-01T00:00:00Z",
        }
        for index, (name, _) in enumerate(REPOS)
    ]

    def search(request):
        return (
            200,
            {},
            json.dumps({"total_count": len(items), "items": items}),
        )

    responses.add_callback(
        responses.GET,
        "https://api.github.com/search/repositories",
        callback=search,
        content_type="application/json",
    )

    for (name, sha), _item in zip(REPOS, items, strict=True):
        responses.add(
            responses.GET,
            f"https://api.github.com/repos/corpus/{name}/git/trees/main",
            json={
                "truncated": False,
                "tree": [
                    {
                        "path": "package.json",
                        "type": "blob",
                        "sha": sha,
                        "size": 200,
                    }
                ],
            },
            status=200,
            headers={"x-ratelimit-remaining": "4900", "x-ratelimit-reset": "0"},
        )
        payload = json.dumps({"name": name, "dependencies": MANIFESTS[sha]}).encode()
        responses.add(
            responses.GET,
            f"https://api.github.com/repos/corpus/{name}/git/blobs/{sha}",
            json=_blob(payload),
            status=200,
            headers={"x-ratelimit-remaining": "4900", "x-ratelimit-reset": "0"},
        )

    for package in ("express", "lodash", "react", "typescript", "left-pad"):
        responses.add(
            responses.GET,
            f"https://registry.npmjs.org/{package}",
            json=json.loads(
                (FIXTURES / f"npm/{package}.json").read_text(encoding="utf-8")
            ),
            status=200,
        )

    def osv(request):
        queries = json.loads(request.body)["queries"]
        return (200, {}, json.dumps({"results": [{} for _ in queries]}))

    responses.add_callback(
        responses.POST,
        "https://api.osv.dev/v1/querybatch",
        callback=osv,
        content_type="application/json",
    )


@pytest.fixture
def frame(tmp_path):
    path = tmp_path / "pilot_frame.yaml"
    path.write_text(PILOT_FRAME, encoding="utf-8")
    return path


@pytest.mark.django_db
class TestThePilotRun:
    @responses.activate
    def test_build_corpus_hands_a_manifest_to_scan_corpus(self, tmp_path, frame):
        """§10 Phase 11's acceptance, at pilot scale: a corpus is built and
        every admitted repository is scored, with the second command finding
        the first one's output where it expects."""
        corpus_dir = tmp_path / "corpus"
        mock_github()

        out = StringIO()
        call_command(
            "build_corpus",
            "--config",
            str(frame),
            "--seed",
            "42",
            "--target",
            "3",
            "--out",
            str(corpus_dir),
            stdout=out,
        )

        manifest_path = corpus_dir / MANIFEST_FILENAME
        assert manifest_path.exists()
        assert (corpus_dir / STRATA_REPORT_FILENAME).exists()
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert document["counts"]["admitted"] == len(REPOS)
        assert "Admitted 3 of 3" in out.getvalue()

        out = StringIO()
        call_command(
            "scan_corpus",
            "--corpus",
            str(manifest_path),
            "--snapshot-date",
            "2026-09-16",
            stdout=out,
        )

        assert ScanHistory.objects.count() == len(REPOS)
        assert (corpus_dir / REPORT_FILENAME).exists()
        assert "Scanned 3 repositor(ies)" in out.getvalue()

    @responses.activate
    @pytest.mark.skipif(
        bool(MATPLOTLIB_ERROR),
        reason=f"matplotlib will not load here: {MATPLOTLIB_ERROR}",
    )
    def test_corpus_report_draws_from_what_the_scan_wrote(self, tmp_path, frame):
        """The third hand-off, split out because it is the only step that needs
        matplotlib. A machine that cannot load it still verifies the two
        commands that matter for the dataset (see `MATPLOTLIB_ERROR`)."""
        corpus_dir = tmp_path / "corpus"
        mock_github()
        call_command(
            "build_corpus",
            "--config",
            str(frame),
            "--seed",
            "42",
            "--target",
            "3",
            "--out",
            str(corpus_dir),
            stdout=StringIO(),
        )
        manifest_path = corpus_dir / MANIFEST_FILENAME
        call_command("scan_corpus", "--corpus", str(manifest_path), stdout=StringIO())

        out = StringIO()
        call_command(
            "corpus_report",
            "--corpus",
            str(manifest_path),
            "--out",
            str(corpus_dir / "figures"),
            stdout=out,
        )

        figures = corpus_dir / "figures"
        assert (figures / HISTOGRAM_FILENAME).exists()
        assert (figures / FLAGGED_RATE_FILENAME).exists()
        assert "Charted 3 corpus repositor(ies)" in out.getvalue()

    @responses.activate
    def test_the_whole_pipeline_writes_no_operational_row(self, tmp_path, frame):
        """D10, over the commands rather than the functions — the guard has to
        be wrapped where the work happens, and a `with` block in the wrong
        place is invisible to a unit test of what it wraps."""
        mock_github()
        corpus_dir = tmp_path / "corpus"
        call_command(
            "build_corpus",
            "--config",
            str(frame),
            "--seed",
            "42",
            "--target",
            "3",
            "--out",
            str(corpus_dir),
            stdout=StringIO(),
        )
        call_command(
            "scan_corpus",
            "--corpus",
            str(corpus_dir / MANIFEST_FILENAME),
            stdout=StringIO(),
        )

        assert ScanRun.objects.count() == 0
        assert ManifestFile.objects.count() == 0
        assert DependencyOccurrence.objects.count() == 0
        assert Package.objects.count() == 0
        assert ScanHistory.objects.count() == len(REPOS)
        assert DependencyHistory.objects.count() == 5  # 2 + 1 + 2 declared

    @responses.activate
    def test_a_resumed_pilot_adds_nothing_and_skips_everything(self, tmp_path, frame):
        """The acceptance's resume clause, through the CLI. The second run
        must be a no-op, not a second snapshot."""
        mock_github()
        corpus_dir = tmp_path / "corpus"
        call_command(
            "build_corpus",
            "--config",
            str(frame),
            "--seed",
            "42",
            "--target",
            "3",
            "--out",
            str(corpus_dir),
            stdout=StringIO(),
        )
        manifest_path = corpus_dir / MANIFEST_FILENAME
        for _ in range(2):
            out = StringIO()
            call_command(
                "scan_corpus",
                "--corpus",
                str(manifest_path),
                "--snapshot-date",
                "2026-09-16",
                "--resume",
                stdout=out,
            )

        assert ScanHistory.objects.count() == len(REPOS)
        assert "skipped 3 already-scanned repo(s)" in out.getvalue()

    @responses.activate
    def test_the_corpus_rows_carry_their_frame(self, tmp_path, frame):
        """Every row is tagged, dated and weighted, which is what makes it
        usable as a stratified sample rather than as a pile of scans."""
        mock_github()
        corpus_dir = tmp_path / "corpus"
        call_command(
            "build_corpus",
            "--config",
            str(frame),
            "--seed",
            "42",
            "--target",
            "3",
            "--out",
            str(corpus_dir),
            stdout=StringIO(),
        )
        call_command(
            "scan_corpus",
            "--corpus",
            str(corpus_dir / MANIFEST_FILENAME),
            "--snapshot-date",
            "2026-09-16",
            stdout=StringIO(),
        )

        for row in ScanHistory.objects.all():
            assert row.data_source == DataSource.CORPUS_SCAN.value
            assert row.snapshot_date.isoformat() == "2026-09-16"
            assert row.sampling_weight is not None
            assert row.github_username == "corpus"

    @responses.activate
    def test_corpus_report_refuses_rather_than_drawing_an_empty_chart(
        self, tmp_path, frame
    ):
        """Running the figures before the scan is an ordinary mistake, and an
        empty PNG would look like a finding about the corpus."""
        from django.core.management.base import CommandError

        mock_github()
        corpus_dir = tmp_path / "corpus"
        call_command(
            "build_corpus",
            "--config",
            str(frame),
            "--seed",
            "42",
            "--target",
            "3",
            "--out",
            str(corpus_dir),
            stdout=StringIO(),
        )

        with pytest.raises(CommandError, match="scan_corpus"):
            call_command(
                "corpus_report",
                "--corpus",
                str(corpus_dir / MANIFEST_FILENAME),
                stdout=StringIO(),
            )
