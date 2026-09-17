"""`build_corpus` — the sampling frame (§10 Phase 11, D14).

The fixtures are built so that the *wrong* implementations pass a naive test
and fail these ones:

* one cell reports 4,000 repositories, so a builder that pages past the Search
  API's 1,000-result cap instead of splitting its star band never enumerates
  honestly;
* two of the sampled repositories declare the same forty dependency names
  under different owners, so a builder that dedups by repository name admits a
  scaffold twice;
* one created-year band cannot overlap one pushed band, so a builder that asks
  GitHub about every cell spends a request confirming arithmetic — and a
  reviewer following WP-4's "no stratum cell empty" flags a cell that was
  never possible;
* the run is killed after the first cell, so a builder whose checkpoint is
  only durable at exit starts again from zero.

Every external call is stubbed; nothing here touches the network and nothing
touches the database, which is itself one of the assertions.
"""

from __future__ import annotations

import base64
import json
import pathlib
from datetime import date

import pytest

from apps.research import corpus as corpus_module
from apps.research import github as github_module
from apps.research.corpus import (
    CANDIDATES_CHECKPOINT,
    MANIFEST_FILENAME,
    REJECT_DUPLICATE_DEPSET,
    REJECT_NO_MANIFEST,
    REJECT_NO_RESOLVABLE,
    STRATA_REPORT_FILENAME,
    Cell,
    Checkpoint,
    CorpusConfigError,
    allocate,
    build_cells,
    build_corpus,
    dependency_set_hash,
    enumerate_cell,
    finalize_weights,
    load_grid,
    sample_indices,
    split_star_range,
)
from apps.research.github import Pacer, RateBudget, ResearchClient

#: The frame WP-4 actually runs, exercised here so a typo in it fails a test
#: rather than a deliverable.
FRAME = pathlib.Path(__file__).resolve().parent.parent / "corpus_frame.yaml"

#: Fixed, because the pushed-band qualifiers resolve against it and an
#: assertion on "six months ago" has to know when now is.
RUN_DATE = date(2026, 9, 16)


# ── a frame small enough to reason about ───────────────────────────────────

SMALL_FRAME = """
languages:
  - {name: javascript, ecosystem: npm, qualifier: "language:JavaScript"}
  - {name: python, ecosystem: pypi, qualifier: "language:Python"}
stars:
  - {name: "5-20", min: 5, max: 20}
  - {name: "1000+", min: 1001, max: null}
pushed:
  - {name: "lt6", min_months: 0, max_months: 6, oversample: 1.0}
  - {name: "gt48", min_months: 48, max_months: null, oversample: 3.0}
created:
  - {name: "le2015", min_year: null, max_year: 2015}
  - {name: "2024plus", min_year: 2024, max_year: null}
qualifiers: ["fork:false", "archived:false"]
search: {sort: stars, order: desc, per_page: 5, results_cap: 20}
verification: {registry_probe_limit: 2}
admission:
  candidate_multiplier: 2.0
  ecosystem_share: {npm: 0.5, pypi: 0.5}
"""


@pytest.fixture
def frame(tmp_path):
    path = tmp_path / "frame.yaml"
    path.write_text(SMALL_FRAME, encoding="utf-8")
    return load_grid(path)


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    """The pacer is real; the clock is not. §8's 2-second interval per search
    call would make this file take minutes to say nothing about correctness."""
    monkeypatch.setattr(github_module, "_sleep", lambda _seconds: None)


class FakeGitHub:
    """A Search API, a tree endpoint and a blob endpoint, driven by a script.

    Stands in for `ResearchClient` rather than for `requests`, because what
    these tests are about is the *sampling logic* — which cells get enumerated,
    which positions get drawn, which candidates get admitted — and stubbing at
    the HTTP layer would bury all three under base64 and pagination.
    `test_corpus_scan.py` goes through the real client and real `responses`.
    """

    def __init__(self, totals: dict, items: dict, trees: dict, blobs: dict) -> None:
        self.totals = totals
        self.items = items
        self.trees = trees
        self.blobs = blobs
        self.budget = RateBudget()
        self.search_pacer = Pacer(0.0)
        self.search_calls = 0
        self.rest_calls = 0
        self.queries: list[tuple[str, int]] = []
        self.wait_for_reset = True

    def search_repositories(self, query, *, page=1, per_page=100, sort, order):
        self.search_calls += 1
        self.queries.append((query, page))
        total = self.totals.get(query, 0)
        start = (page - 1) * per_page
        items = self.items.get(query, [])[start : start + per_page]
        return {"total_count": total, "items": items}

    def tree(self, owner, name, branch):
        self.rest_calls += 1
        return self.trees.get(f"{owner}/{name}", [])

    def blob(self, owner, name, sha, cap):
        self.rest_calls += 1
        return self.blobs.get(sha)


def repo_item(index: int, owner: str = "acme", name: str | None = None) -> dict:
    name = name or f"repo-{index}"
    return {
        "id": 900000 + index,
        "full_name": f"{owner}/{name}",
        "name": name,
        "owner": {"login": owner, "id": 4242},
        "default_branch": "main",
        "stargazers_count": 12,
        "pushed_at": "2026-01-01T00:00:00Z",
        "created_at": "2014-01-01T00:00:00Z",
    }


def tree_with(path: str, sha: str) -> list[dict]:
    return [{"path": path, "type": "blob", "sha": sha, "size": 300}]


def manifest_bytes(dependencies: dict) -> bytes:
    return json.dumps({"name": "x", "dependencies": dependencies}).encode()


# ── the grid ───────────────────────────────────────────────────────────────


class TestGrid:
    def test_the_shipped_frame_loads(self):
        """`corpus_frame.yaml` is what WP-4 actually runs; a typo in it is a
        broken deliverable, not a broken test."""
        grid = load_grid(FRAME)
        assert {language.ecosystem for language in grid.languages} == {"npm", "pypi"}
        assert len(grid.stars) == 5
        assert sum(grid.ecosystem_share.values()) == pytest.approx(1.0)

    def test_a_frame_naming_an_ecosystem_no_adapter_parses_is_refused(self, tmp_path):
        """The failure would otherwise be a corpus of a thousand repositories
        that `scan_corpus` cannot read a single manifest of — discovered an
        hour and several thousand API calls later."""
        path = tmp_path / "bad.yaml"
        path.write_text(
            SMALL_FRAME.replace("ecosystem: pypi", "ecosystem: cargo"), encoding="utf-8"
        )
        with pytest.raises(CorpusConfigError, match="cargo"):
            load_grid(path)

    def test_every_combination_becomes_a_cell(self, frame):
        cells = build_cells(frame, RUN_DATE)
        assert len(cells) == 2 * 2 * 2 * 2

    def test_a_pushed_band_resolves_to_dates_against_the_run_date(self, frame):
        cells = {cell.key: cell for cell in build_cells(frame, RUN_DATE)}
        recent = cells["javascript|5-20|lt6|le2015"]
        stale = cells["javascript|5-20|gt48|le2015"]
        # 6 months back from 2026-09-16 at 30 days/month.
        assert "pushed:>=2026-03-20" in recent.query
        assert "pushed:<=2022-10-07" in stale.query

    def test_the_qualifiers_that_do_the_filtering_are_in_every_query(self, frame):
        for cell in build_cells(frame, RUN_DATE):
            assert "fork:false" in cell.query
            assert "archived:false" in cell.query

    def test_a_cell_whose_bands_cannot_overlap_is_marked_infeasible(self, frame):
        """Created in 2022 or later *and* unpushed for four years is empty by
        arithmetic, not by finding. WP-4's reviewer is told to flag an empty
        stale cell, so a cell that was never possible must not look like one."""
        cells = {cell.key: cell for cell in build_cells(frame, RUN_DATE)}
        assert cells["javascript|5-20|gt48|2024plus"].infeasible
        assert not cells["javascript|5-20|gt48|le2015"].infeasible

    def test_an_infeasible_cell_costs_no_search_request(self, frame):
        client = FakeGitHub({}, {}, {}, {})
        cell = next(cell for cell in build_cells(frame, RUN_DATE) if cell.infeasible)
        assert enumerate_cell(cell, client, frame) == [cell]
        assert client.search_calls == 0


# ── the 1,000-result cap ───────────────────────────────────────────────────


class TestStarBandSplitting:
    def test_a_bounded_range_splits_geometrically(self):
        """Arithmetic would put the midpoint of 51..200 at 125, above almost
        every repository in the band — one half still over the cap and the
        other nearly empty. Star counts are heavy-tailed."""
        assert split_star_range(51, 200) == ((51, 100), (101, 200))

    def test_an_open_ended_range_can_always_be_cut_again(self):
        assert split_star_range(1001, None) == ((1001, 3002), (3003, None))

    def test_a_single_star_value_cannot_be_cut(self):
        assert split_star_range(7, 7) == ()

    def test_a_cell_over_the_cap_is_split_until_each_piece_fits(self, frame):
        query = build_cells(frame, RUN_DATE)[0].query
        low = query.replace("stars:5..20", "stars:5..10")
        high = query.replace("stars:5..20", "stars:11..20")
        client = FakeGitHub({query: 40, low: 12, high: 15}, {}, {}, {})

        produced = enumerate_cell(build_cells(frame, RUN_DATE)[0], client, frame)

        assert [cell.total_count for cell in produced] == [12, 15]
        assert all(not cell.capped for cell in produced)
        assert {cell.stars for cell in produced} == {"5..10", "11..20"}

    def test_a_cell_that_cannot_be_split_small_enough_says_so(self, frame, monkeypatch):
        """A single star value holding more than the cap. The sample is then
        drawn from the ranked head, which is a different claim, and the cell
        records `capped` so no analysis mistakes it for a simple random
        sample."""
        monkeypatch.setattr(corpus_module, "MAX_SPLIT_DEPTH", 0)
        query = build_cells(frame, RUN_DATE)[0].query
        client = FakeGitHub({query: 5000}, {}, {}, {})

        produced = enumerate_cell(build_cells(frame, RUN_DATE)[0], client, frame)

        assert len(produced) == 1
        assert produced[0].capped
        assert produced[0].available == frame.results_cap

    def test_the_weight_of_a_capped_cell_comes_from_what_is_reachable(self, frame):
        """Not from `total_count`. Weighting by a population the frame cannot
        reach would silently inflate that stratum in every weighted estimate."""
        cell = Cell(
            key="c",
            language="javascript",
            ecosystem="npm",
            stars="5-20",
            stars_min=5,
            stars_max=20,
            pushed="lt6",
            created="le2015",
            query="q",
            results_cap=20,
            total_count=5000,
            capped=True,
        )
        allocate([cell], target=4, grid=frame)
        cell.examined = 7
        finalize_weights([cell])

        assert cell.available == 20
        # 20 reachable over 7 looked at — not 5000 over 7.
        assert cell.sampling_weight == pytest.approx(20 / 7)


# ── allocation and sampling ────────────────────────────────────────────────


class TestAllocation:
    def _cells(self, frame, total=200):
        cells = build_cells(frame, RUN_DATE)
        for cell in cells:
            if not cell.infeasible:
                cell.total_count = total
        return cells

    def test_stale_cells_get_more_of_the_target(self, frame):
        """D14's "deliberate oversampling of stale cells". The `gt48` band
        carries a 3x multiplier in this frame, and the allocation has to show
        it — otherwise the corpus has no power where the product's whole
        premise lives."""
        cells = self._cells(frame)
        allocate(cells, target=100, grid=frame)

        recent = sum(cell.allocation for cell in cells if cell.pushed == "lt6")
        stale = sum(cell.allocation for cell in cells if cell.pushed == "gt48")
        assert stale > recent

    def test_the_ecosystem_split_follows_the_frame(self, frame):
        cells = self._cells(frame)
        allocate(cells, target=100, grid=frame)
        npm = sum(cell.allocation for cell in cells if cell.ecosystem == "npm")
        pypi = sum(cell.allocation for cell in cells if cell.ecosystem == "pypi")
        assert abs(npm - pypi) <= 2

    def test_a_cell_is_never_allocated_more_than_it_holds(self, frame):
        cells = self._cells(frame, total=3)
        allocate(cells, target=1000, grid=frame)
        assert all(cell.allocation <= cell.available for cell in cells)

    def test_an_infeasible_cell_is_allocated_nothing(self, frame):
        cells = self._cells(frame)
        allocate(cells, target=100, grid=frame)
        assert all(cell.allocation == 0 for cell in cells if cell.infeasible)

    def test_the_weight_is_the_expansion_factor_the_report_explains(self, frame):
        """One admitted repository stands for `available / examined` in the frame.

        The denominator is candidates *examined*, not candidates admitted:
        verification is a filter on the cell, so the admitted set estimates the
        admissible subpopulation, whose own size is estimated by
        `available x admitted/examined`. The two `admitted` terms cancel.

        And not candidates *drawn* either — a cell that fills its allocation
        stops examining, and the candidates it drew but never looked at were
        never part of the sample.
        """
        cells = self._cells(frame)
        allocate(cells, target=100, grid=frame)
        live = [cell for cell in cells if cell.allocation]

        # Nothing examined yet, so there is no weight to report.
        assert all(cell.sampling_weight is None for cell in live)

        for index, cell in enumerate(live):
            cell.examined = index + 1
        finalize_weights(cells)

        for index, cell in enumerate(live):
            assert cell.sampling_weight == pytest.approx(cell.available / (index + 1))


class TestSeededSampling:
    def _cell(self, frame, total=20):
        cell = build_cells(frame, RUN_DATE)[0]
        cell.total_count = total
        allocate([cell], target=4, grid=frame)
        return cell

    def test_the_same_seed_draws_the_same_positions(self, frame):
        cell = self._cell(frame)
        assert sample_indices(cell, frame, 42) == sample_indices(cell, frame, 42)

    def test_a_different_seed_draws_different_positions(self, frame):
        cell = self._cell(frame)
        assert sample_indices(cell, frame, 42) != sample_indices(cell, frame, 7)

    def test_the_draw_depends_on_the_cell_not_on_when_it_was_reached(self, frame):
        """Seeded per cell rather than from one run-wide stream. A resumed run
        replays some cells and enumerates others, so a shared `Random` would
        make the sample depend on the order cells happened to finish in — the
        one thing a seed exists to rule out."""
        first = self._cell(frame)
        second = self._cell(frame)
        second.key = "a-different-cell"
        assert sample_indices(first, frame, 42) != sample_indices(second, frame, 42)
        # And the first cell's draw is unchanged by the second existing.
        assert sample_indices(first, frame, 42) == sample_indices(
            self._cell(frame), frame, 42
        )

    def test_positions_never_run_past_what_the_api_will_serve(self, frame):
        cell = self._cell(frame, total=5000)
        assert max(sample_indices(cell, frame, 42)) < frame.results_cap


# ── verification ───────────────────────────────────────────────────────────


class TestDependencySetHash:
    def test_two_scaffolds_with_the_same_packages_collide(self):
        """The control D14 asks for. Different names, different owners, the
        same forty packages — they add no information and concentrate whatever
        quirks the scaffold has."""
        one = {("npm", "react"), ("npm", "lodash")}
        two = {("npm", "lodash"), ("npm", "react")}
        assert dependency_set_hash(one) == dependency_set_hash(two)

    def test_versions_are_deliberately_not_in_it(self):
        """Two checkouts of one scaffold a year apart pin different versions of
        the same packages. Hashing versions would call them distinct, which is
        exactly the duplicate this is meant to catch."""
        assert dependency_set_hash({("npm", "react")}) == dependency_set_hash(
            {("npm", "react")}
        )

    def test_the_ecosystem_is_part_of_the_key(self):
        assert dependency_set_hash({("npm", "requests")}) != dependency_set_hash(
            {("pypi", "requests")}
        )


@pytest.mark.django_db
class TestVerificationAndAdmission:
    """A full `build_corpus` over a two-cell frame, stubbed end to end."""

    def _run(self, tmp_path, frame, monkeypatch, *, items, trees, blobs, resolvable):
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: resolvable
        )
        totals = {}
        by_query = {}
        cells = build_cells(frame, RUN_DATE)
        live = [cell for cell in cells if not cell.infeasible]
        totals[live[0].query] = len(items)
        by_query[live[0].query] = items
        client = FakeGitHub(totals, by_query, trees, blobs)
        result = build_corpus(
            out_dir=tmp_path,
            grid=frame,
            seed=42,
            target=4,
            client=client,
            today=RUN_DATE,
        )
        return result, client

    def test_a_repository_with_no_supported_manifest_is_rejected(
        self, tmp_path, frame, monkeypatch
    ):
        items = [repo_item(i) for i in range(4)]
        trees = {item["full_name"]: tree_with("README.md", "x") for item in items}
        result, _ = self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=items,
            trees=trees,
            blobs={},
            resolvable=True,
        )
        assert result.admitted == 0
        assert result.rejected[REJECT_NO_MANIFEST] == len(items)

    def test_a_repository_whose_packages_no_registry_knows_is_rejected(
        self, tmp_path, frame, monkeypatch
    ):
        """Otherwise it enters the corpus as a scan with nothing assessable in
        it — scoring 100, indistinguishable from a healthy project."""
        items = [repo_item(i) for i in range(4)]
        trees = {
            item["full_name"]: tree_with("package.json", f"m{i}")
            for i, item in enumerate(items)
        }
        blobs = {f"m{i}": manifest_bytes({"private-thing": "^1.0.0"}) for i in range(4)}
        result, _ = self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=items,
            trees=trees,
            blobs=blobs,
            resolvable=False,
        )
        assert result.admitted == 0
        assert result.rejected[REJECT_NO_RESOLVABLE] == len(items)

    def test_the_second_copy_of_one_scaffold_is_discarded(
        self, tmp_path, frame, monkeypatch
    ):
        items = [
            repo_item(0, owner="alice", name="app"),
            repo_item(1, owner="bob", name="starter"),
        ]
        trees = {
            "alice/app": tree_with("package.json", "same"),
            "bob/starter": tree_with("package.json", "same"),
        }
        blobs = {"same": manifest_bytes({"react": "^18", "lodash": "^4"})}
        result, _ = self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=items,
            trees=trees,
            blobs=blobs,
            resolvable=True,
        )
        assert result.admitted == 1
        assert result.rejected[REJECT_DUPLICATE_DEPSET] == 1

    def test_an_admitted_repository_records_what_scan_corpus_will_need(
        self, tmp_path, frame, monkeypatch
    ):
        items = [repo_item(0)]
        trees = {"acme/repo-0": tree_with("package.json", "m0")}
        blobs = {"m0": manifest_bytes({"react": "^18"})}
        self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=items,
            trees=trees,
            blobs=blobs,
            resolvable=True,
        )

        document = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        entry = document["repositories"][0]
        assert entry["full_name"] == "acme/repo-0"
        assert entry["github_repo_id"] == 900000
        # The owner, which is what a corpus `scan_history` row records in place
        # of a RepoVitals user (there is none).
        assert entry["owner_login"] == "acme"
        assert entry["owner_id"] == 4242
        assert entry["sampling_weight"] is not None
        assert entry["manifests"][0]["path"] == "package.json"
        assert entry["manifests"][0]["sha"] == "m0"
        assert entry["manifests"][0]["parser_name"]

    def test_the_manifest_blob_is_archived_beside_the_manifest(
        self, tmp_path, frame, monkeypatch
    ):
        """`scan_corpus` reads these rather than re-fetching: same bytes, no
        quota, and — the part that matters — the repository is scanned as the
        thing that was actually sampled, not as whatever it became later."""
        items = [repo_item(0)]
        trees = {"acme/repo-0": tree_with("package.json", "m0")}
        content = manifest_bytes({"react": "^18"})
        self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=items,
            trees=trees,
            blobs={"m0": content},
            resolvable=True,
        )
        document = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        archived = tmp_path / document["repositories"][0]["manifests"][0]["blob_path"]
        assert archived.read_bytes() == content

    def test_nothing_is_written_to_the_database(self, tmp_path, frame, monkeypatch):
        """D10, and more than that: this command writes no row of any kind.
        The corpus does not exist in Postgres until `scan_corpus` scores it."""
        from apps.research.models import ScanHistory

        items = [repo_item(0)]
        self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=items,
            trees={"acme/repo-0": tree_with("package.json", "m0")},
            blobs={"m0": manifest_bytes({"react": "^18"})},
            resolvable=True,
        )
        assert ScanHistory.objects.count() == 0


# ── resume ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestResume:
    def test_a_resumed_run_does_not_re_verify_what_it_already_did(
        self, tmp_path, frame, monkeypatch
    ):
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: True
        )
        items = [repo_item(i) for i in range(4)]
        trees = {
            item["full_name"]: tree_with("package.json", f"m{i}")
            for i, item in enumerate(items)
        }
        blobs = {
            f"m{i}": manifest_bytes({f"pkg-{i}": "^1.0.0"}) for i in range(len(items))
        }
        cells = build_cells(frame, RUN_DATE)
        live = next(cell for cell in cells if not cell.infeasible)

        def run(resume):
            client = FakeGitHub(
                {live.query: len(items)}, {live.query: items}, trees, blobs
            )
            result = build_corpus(
                out_dir=tmp_path,
                grid=frame,
                seed=42,
                target=4,
                client=client,
                resume=resume,
                today=RUN_DATE,
            )
            return result, client

        first, _ = run(resume=False)
        second, second_client = run(resume=True)

        assert second.admitted == first.admitted
        assert second.candidates == first.candidates
        # Not one repository was looked at twice.
        assert second_client.rest_calls == 0

    def test_a_line_torn_in_half_by_a_kill_costs_only_its_own_work(
        self, tmp_path, frame, monkeypatch
    ):
        """A checkpoint is appended and flushed per candidate. A process killed
        mid-write leaves a partial JSON line; everything before it is still
        good, and the truncated one is simply redone.

        `target=8` so the cell's allocation is four and every candidate is
        examined. At a lower target the quota stop ends the cell after two
        admissions, which is correct behaviour and leaves nothing to tear.
        """
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: True
        )
        items = [repo_item(i) for i in range(4)]
        trees = {
            item["full_name"]: tree_with("package.json", f"m{i}")
            for i, item in enumerate(items)
        }
        blobs = {f"m{i}": manifest_bytes({f"pkg-{i}": "^1"}) for i in range(len(items))}
        cells = build_cells(frame, RUN_DATE)
        live = next(cell for cell in cells if not cell.infeasible)
        client = FakeGitHub({live.query: len(items)}, {live.query: items}, trees, blobs)
        build_corpus(
            out_dir=tmp_path,
            grid=frame,
            seed=42,
            target=8,
            client=client,
            today=RUN_DATE,
        )

        checkpoint = tmp_path / ".checkpoint" / CANDIDATES_CHECKPOINT
        lines = checkpoint.read_text(encoding="utf-8").splitlines()
        checkpoint.write_text(
            "\n".join(lines[:-1]) + "\n" + lines[-1][: len(lines[-1]) // 2],
            encoding="utf-8",
        )

        resumed_client = FakeGitHub(
            {live.query: len(items)}, {live.query: items}, trees, blobs
        )
        result = build_corpus(
            out_dir=tmp_path,
            grid=frame,
            seed=42,
            target=8,
            client=resumed_client,
            resume=True,
            today=RUN_DATE,
        )
        # Every candidate is accounted for exactly once: the torn line's work
        # was redone, and the intact lines were replayed rather than repeated.
        assert result.candidates == len(items)
        # Read it the way a resume does. The torn line is still in the file —
        # nothing rewrites it — and tolerating it is the behaviour under test.
        rows = Checkpoint(tmp_path / ".checkpoint").read(CANDIDATES_CHECKPOINT)
        ids = [row["github_repo_id"] for row in rows]
        assert len(ids) == len(set(ids)) == len(items)

    def test_a_run_without_resume_starts_over(self, tmp_path, frame, monkeypatch):
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: True
        )
        items = [repo_item(0)]
        trees = {"acme/repo-0": tree_with("package.json", "m0")}
        blobs = {"m0": manifest_bytes({"react": "^18"})}
        cells = build_cells(frame, RUN_DATE)
        live = next(cell for cell in cells if not cell.infeasible)

        for _ in range(2):
            client = FakeGitHub({live.query: 1}, {live.query: items}, trees, blobs)
            result = build_corpus(
                out_dir=tmp_path,
                grid=frame,
                seed=42,
                target=4,
                client=client,
                resume=False,
                today=RUN_DATE,
            )
        assert result.candidates == 1


@pytest.mark.django_db
class TestTheQuotaStop:
    """The corpus comes out the size it was asked for.

    `candidate_multiplier` oversamples so that attrition still leaves the
    allocation filled. Verifying *every* drawn candidate and admitting every
    passer therefore overshoots by exactly that margin — at the frame's 2.5x
    and §10 Phase 11's expected ~50% admission, a 1,000-repo target delivers
    ~1,250, outside WP-4's own "total admitted 900-1,100" check.
    """

    def _run(self, tmp_path, frame, monkeypatch, *, items, target):
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: True
        )
        trees = {
            item["full_name"]: tree_with("package.json", f"m{i}")
            for i, item in enumerate(items)
        }
        blobs = {f"m{i}": manifest_bytes({f"pkg-{i}": "^1"}) for i in range(len(items))}
        live = next(cell for cell in build_cells(frame, RUN_DATE) if not cell.infeasible)
        client = FakeGitHub({live.query: len(items)}, {live.query: items}, trees, blobs)
        return build_corpus(
            out_dir=tmp_path,
            grid=frame,
            seed=42,
            target=target,
            client=client,
            today=RUN_DATE,
        )

    def test_a_cell_stops_examining_once_its_allocation_is_filled(
        self, tmp_path, frame, monkeypatch
    ):
        """Ten admissible candidates, an allocation of two: two admitted, two
        examined, and eight left alone."""
        result = self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=[repo_item(i) for i in range(10)],
            target=4,
        )

        assert result.admitted == 2
        assert result.candidates == 2
        cell = next(c for c in result.cells if c.allocation)
        assert cell.examined == 2

    def test_the_weight_divides_by_what_was_examined_not_what_was_drawn(
        self, tmp_path, frame, monkeypatch
    ):
        """The other half of the same change. A cell that stopped early looked
        at two of the four it drew, and two is the denominator - dividing by
        four would halve that stratum's weight and under-count it in every
        weighted estimate."""
        result = self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=[repo_item(i) for i in range(10)],
            target=4,
        )

        cell = next(c for c in result.cells if c.allocation)
        assert cell.examined == 2
        assert cell.sampling_weight == pytest.approx(cell.available / 2)

        document = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        for entry in document["repositories"]:
            assert entry["sampling_weight"] == pytest.approx(cell.available / 2)

    def test_the_examined_candidates_are_not_the_top_of_the_ranking(
        self, tmp_path, frame, monkeypatch
    ):
        """Positions are sampled at random but fetched in ascending order, and
        position correlates with the cell's `stars desc` sort. Stopping at a
        quota without shuffling would take the highest-starred candidates of
        every cell - a quota sample of the head of the ranking, wearing a
        random sample's weights."""
        self._run(
            tmp_path,
            frame,
            monkeypatch,
            items=[repo_item(i) for i in range(10)],
            target=4,
        )

        admitted = {
            entry["github_repo_id"]
            for entry in json.loads(
                (tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8")
            )["repositories"]
        }
        # The first two positions of the drawn (ascending) order would be the
        # two lowest ids. The shuffle means that is not what came out.
        drawn_ascending = sorted(900000 + i for i in range(10))
        assert admitted != set(drawn_ascending[:2])


# ── the strata report ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestStrataReport:
    def test_it_answers_every_line_of_wp4s_checklist(self, tmp_path, frame, monkeypatch):
        """File B asks the teammate to confirm six things. Each is a line with
        its number beside it, so the review is reading rather than arithmetic."""
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: True
        )
        items = [
            repo_item(0, owner="alice", name="app"),
            repo_item(1, owner="bob", name="starter"),
            repo_item(2, owner="carol", name="tool"),
        ]
        trees = {
            "alice/app": tree_with("package.json", "a"),
            "bob/starter": tree_with("package.json", "a"),  # same dep set
            "carol/tool": tree_with("package.json", "c"),
        }
        blobs = {
            "a": manifest_bytes({"react": "^18"}),
            "c": manifest_bytes({"express": "^4"}),
        }
        cells = build_cells(frame, RUN_DATE)
        live = next(cell for cell in cells if not cell.infeasible)
        client = FakeGitHub({live.query: 3}, {live.query: items}, trees, blobs)

        build_corpus(
            out_dir=tmp_path,
            grid=frame,
            seed=42,
            target=4,
            client=client,
            today=RUN_DATE,
        )
        report = (tmp_path / STRATA_REPORT_FILENAME).read_text(encoding="utf-8")

        assert "**Total admitted:**" in report
        assert "**Ecosystem split:**" in report
        assert "**Admission rate:**" in report
        assert "**Dedup discards:** 1" in report
        assert "**Empty cells:**" in report
        assert "**Empty *stale* cells:**" in report
        # Reproducibility fields.
        assert "Seed: `42`" in report
        assert "2026-09-16" in report

    def test_it_separates_an_empty_cell_from_an_impossible_one(
        self, tmp_path, frame, monkeypatch
    ):
        """WP-4's reviewer is told a zero stale cell is worth flagging. A cell
        whose created and pushed bands cannot overlap is not a finding about
        GitHub, and the report must not present it as one."""
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: True
        )
        client = FakeGitHub({}, {}, {}, {})
        build_corpus(
            out_dir=tmp_path,
            grid=frame,
            seed=42,
            target=4,
            client=client,
            today=RUN_DATE,
        )
        report = (tmp_path / STRATA_REPORT_FILENAME).read_text(encoding="utf-8")
        assert "infeasible by construction" in report

    def test_it_states_what_a_capped_cell_cannot_say(self, tmp_path, frame, monkeypatch):
        monkeypatch.setattr(
            corpus_module, "_registry_resolvable", lambda specs, limit: True
        )
        build_corpus(
            out_dir=tmp_path,
            grid=frame,
            seed=42,
            target=4,
            client=FakeGitHub({}, {}, {}, {}),
            today=RUN_DATE,
        )
        report = (tmp_path / STRATA_REPORT_FILENAME).read_text(encoding="utf-8")
        assert "cross-section as of the run date" in report
        assert "capped" in report


# ── the credential ─────────────────────────────────────────────────────────


class TestResearchCredential:
    def test_an_unset_pat_names_the_variable_and_the_scope(self, settings):
        settings.GITHUB_API_PAT = ""
        with pytest.raises(github_module.ResearchCredentialMissing) as excinfo:
            ResearchClient.from_settings()
        assert "GITHUB_API_PAT" in str(excinfo.value)
        assert "public_repo" in str(excinfo.value)

    def test_a_set_pat_is_the_token_every_call_carries(self, settings):
        settings.GITHUB_API_PAT = "ghp_research_token"
        assert ResearchClient.from_settings().token == "ghp_research_token"


class TestRateBudget:
    def test_an_unknown_budget_is_not_an_exhausted_one(self):
        assert not RateBudget().is_low

    def test_the_budget_is_read_from_the_response_not_counted_locally(self):
        budget = RateBudget()
        budget.observe({"x-ratelimit-remaining": "17", "x-ratelimit-reset": "99"})
        assert budget.remaining == 17
        assert budget.reset_at == 99.0

    def test_a_low_budget_stops_rather_than_sleeps_when_asked_to(self):
        budget = RateBudget(remaining=3, reset_at=0)
        with pytest.raises(github_module.RateBudgetExhausted, match="--resume"):
            budget.pause_if_low(wait=False)

    def test_a_pause_is_recorded_so_a_slow_run_can_say_why(self, monkeypatch):
        monkeypatch.setattr(github_module, "_sleep", lambda _seconds: None)
        budget = RateBudget(remaining=0, reset_at=0)
        budget.pause_if_low()
        assert budget.pauses == 1
        # The window has rolled; nothing is known until the next answer.
        assert budget.remaining is None


class TestSearchPacing:
    def test_search_calls_are_paced_and_rest_calls_are_not(self, monkeypatch, settings):
        """§8: the Search API's limit is 30/minute and the REST one is
        5,000/hour. Pacing every call at the search interval would turn a
        three-hour corpus scan into a two-day one."""
        settings.GITHUB_API_PAT = "ghp_x"
        slept: list[float] = []
        monkeypatch.setattr(github_module, "_sleep", slept.append)

        client = ResearchClient.from_settings()
        monkeypatch.setattr(
            github_module.http,
            "get_json",
            lambda *a, **k: github_module.http.UpstreamResponse(200, {}, {}),
        )
        client.search_repositories("q", sort="stars", order="desc")
        client.search_repositories("q", sort="stars", order="desc")
        assert len(slept) == 1
        assert slept[0] == pytest.approx(
            github_module.SEARCH_MIN_INTERVAL_SECONDS, abs=0.2
        )

    def test_the_interval_is_the_one_the_free_tier_allows(self):
        assert github_module.SEARCH_MIN_INTERVAL_SECONDS == pytest.approx(2.0)


def test_a_blob_is_unwrapped_by_the_scanners_own_decoder(monkeypatch, settings):
    """Not by a second base64 path. `scanner.decode_blob` is what a live scan
    uses, including its size cap and its refusal of an inlineable encoding."""
    settings.GITHUB_API_PAT = "ghp_x"
    client = ResearchClient.from_settings()
    payload = {
        "encoding": "base64",
        "content": base64.b64encode(b"{}").decode(),
    }
    monkeypatch.setattr(
        github_module.http,
        "get_json",
        lambda *a, **k: github_module.http.UpstreamResponse(200, {}, payload),
    )
    assert client.blob("acme", "shop", "sha", 1024) == b"{}"
