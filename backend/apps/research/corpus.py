"""The sampling frame — §10 Phase 11's `build_corpus`, D14's corpus.

What this produces is not "a thousand repositories". It is a thousand
repositories *plus the frame they were drawn from*, and the second half is
what makes S1 a study rather than a collection of anecdotes: a reader can ask
which populations are represented, how heavily, and what was thrown away.

Five properties carry that, and each is here because the obvious cheaper
version quietly destroys it.

**Partitioned, because the Search API caps every query at 1,000 results**
(§8). A single "all JavaScript repositories" query cannot reach past its first
thousand hits however many pages are requested, so a sample drawn from it is a
sample of GitHub's ranking function, not of GitHub. The grid cuts the space
into cells small enough to enumerate honestly, and `_split_stars` keeps
cutting any cell that is still over the cap.

**Stale cells are deliberately oversampled** (D14). The repositories this
product exists to find are the abandoned ones, and they are rare — a
proportional sample would put a handful of them in a corpus of a thousand and
S1 would have no power where it matters most. So the allocation is tilted
toward the old and unpushed, and `sampling_weight` records the tilt so any
population estimate can undo it.

**Verification is per candidate and its outcome is recorded either way.** A
repository that has no manifest, or whose manifest names nothing a registry
can describe, would enter `scan_corpus` as a zero-dependency scan scoring 100
— indistinguishable in the data from a genuinely clean project. The admission
rate is a number the strata report prints, because WP-4's reviewer is asked to
flag it if it is far from the ~50% this design expects.

**Near-duplicates are excluded by dependency set, not by name.** GitHub is
full of course scaffolds and `create-react-app` output: different names,
different owners, the same forty packages. They would inflate the corpus's
apparent size while adding no information, and — worse for S1 — they would
concentrate whatever quirks that scaffold has. The control is a hash of the
sorted dependency names, which is what "near-duplicate" actually means here.

**Everything is checkpointed.** An hour-long paced run that dies at minute
fifty must not start again at zero, and WP-4 tells the teammate to rerun with
`--resume`. Cells and candidates are appended to JSONL as they complete, and a
resumed run replays them rather than re-asking GitHub.

The output `corpus_manifest.json` is an interface: WP-4 delivers it, WP-5's
`scan_corpus` consumes it, and Phase 12's analysis joins strata through it.
Its fields are named in §10 Phase 11 and are not free to drift.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from apps.common import http
from apps.scanning import adapters
from apps.scanning.scanner import (
    MAX_MANIFEST_BYTES,
    adopt_workspace_lockfiles,
    plan_manifests,
    tree_manifest_paths,
)

from .github import ResearchClient

logger = logging.getLogger(__name__)

#: Days per month, for turning "18 months since last push" into the absolute
#: date GitHub's `pushed:` qualifier wants. Approximate on purpose: a stratum
#: boundary is a design choice, not a measurement, and 30.44 would suggest a
#: precision the band does not have. The resolved dates are written into the
#: manifest so the frame is reproducible whatever this constant is.
DAYS_PER_MONTH = 30

#: §8: the Search API will not return past the thousandth result of a query,
#: whatever `page` says.
RESULTS_CAP = 1000

#: How far `_split_stars` will subdivide before admitting the cell is still
#: over the cap. Six halvings turn a 64,000-repository band into 1,000; past
#: that the band is a single star value and splitting cannot help.
MAX_SPLIT_DEPTH = 6

#: Filenames the run writes, relative to the corpus directory. Named here
#: because WP-4 and WP-5 both quote them and `scan_corpus` opens the first one
#: by default.
MANIFEST_FILENAME = "corpus_manifest.json"
STRATA_REPORT_FILENAME = "strata_report.md"
BLOB_DIRNAME = "blobs"
CHECKPOINT_DIRNAME = ".checkpoint"
CELLS_CHECKPOINT = "cells.jsonl"
CANDIDATES_CHECKPOINT = "candidates.jsonl"

#: Why a candidate was not admitted. Codes rather than sentences, for the same
#: reason §5.6's outcomes are: the strata report counts them and a reworded
#: sentence must not become a new category.
REJECT_NO_MANIFEST = "no_supported_manifest"
REJECT_UNREADABLE = "manifests_unreadable"
REJECT_NO_DEPENDENCIES = "no_declared_dependencies"
REJECT_NO_RESOLVABLE = "no_registry_resolvable_dependency"
REJECT_DUPLICATE_DEPSET = "duplicate_dependency_set"
REJECT_UNREACHABLE = "repository_unreachable"

REJECT_REASONS: tuple[str, ...] = (
    REJECT_NO_MANIFEST,
    REJECT_UNREADABLE,
    REJECT_NO_DEPENDENCIES,
    REJECT_NO_RESOLVABLE,
    REJECT_DUPLICATE_DEPSET,
    REJECT_UNREACHABLE,
)


class CorpusConfigError(Exception):
    """The grid YAML is not a usable sampling frame."""


# ── the grid ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Language:
    name: str
    ecosystem: str
    qualifier: str


@dataclass(frozen=True)
class StarBand:
    name: str
    min: int
    max: int | None

    def qualifier(self) -> str:
        return _star_qualifier(self.min, self.max)


@dataclass(frozen=True)
class PushedBand:
    """Months since the last push, resolved to dates against the run date.

    `oversample` is D14's tilt: the multiplier this band's cells get when the
    target is allocated. 1.0 is neutral; the stale bands carry more.
    """

    name: str
    min_months: int
    max_months: int | None
    oversample: float = 1.0

    def qualifier(self, today: date) -> str:
        # `min_months` is *at least* this long ago, so it is the later bound in
        # calendar terms. Getting these the wrong way round produces a query
        # that silently returns nothing, which reads exactly like an empty cell.
        newest = today - timedelta(days=self.min_months * DAYS_PER_MONTH)
        if self.max_months is None:
            return f"pushed:<={newest.isoformat()}"
        oldest = today - timedelta(days=self.max_months * DAYS_PER_MONTH)
        if self.min_months == 0:
            return f"pushed:>={oldest.isoformat()}"
        return f"pushed:{oldest.isoformat()}..{newest.isoformat()}"


@dataclass(frozen=True)
class CreatedBand:
    name: str
    min_year: int | None
    max_year: int | None

    def qualifier(self) -> str:
        if self.min_year is None and self.max_year is not None:
            return f"created:<={self.max_year}-12-31"
        if self.max_year is None and self.min_year is not None:
            return f"created:>={self.min_year}-01-01"
        return f"created:{self.min_year}-01-01..{self.max_year}-12-31"


@dataclass(frozen=True)
class GridConfig:
    languages: tuple[Language, ...]
    stars: tuple[StarBand, ...]
    pushed: tuple[PushedBand, ...]
    created: tuple[CreatedBand, ...]
    qualifiers: tuple[str, ...]
    sort: str
    order: str
    per_page: int
    results_cap: int
    registry_probe_limit: int
    candidate_multiplier: float
    ecosystem_share: dict[str, float]


def _require(document: dict, key: str, path: Path) -> Any:
    if key not in document:
        raise CorpusConfigError(f"{path}: the frame is missing '{key}'.")
    return document[key]


def load_grid(path: Path) -> GridConfig:
    """Read the frame YAML. Every field is required or has a stated default."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CorpusConfigError(f"No sampling frame at {path}.") from exc
    except yaml.YAMLError as exc:
        raise CorpusConfigError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(document, dict):
        raise CorpusConfigError(f"{path} must be a mapping.")

    languages = tuple(
        Language(
            name=entry["name"], ecosystem=entry["ecosystem"], qualifier=entry["qualifier"]
        )
        for entry in _require(document, "languages", path)
    )
    unsupported = {
        language.ecosystem
        for language in languages
        if language.ecosystem not in adapters.supported_ecosystems()
    }
    if unsupported:
        raise CorpusConfigError(
            f"{path} samples {sorted(unsupported)}, which no adapter can parse. "
            f"Supported: {list(adapters.supported_ecosystems())}."
        )

    stars = tuple(
        StarBand(name=entry["name"], min=int(entry["min"]), max=entry.get("max"))
        for entry in _require(document, "stars", path)
    )
    pushed = tuple(
        PushedBand(
            name=entry["name"],
            min_months=int(entry["min_months"]),
            max_months=entry.get("max_months"),
            oversample=float(entry.get("oversample", 1.0)),
        )
        for entry in _require(document, "pushed", path)
    )
    created = tuple(
        CreatedBand(
            name=entry["name"],
            min_year=entry.get("min_year"),
            max_year=entry.get("max_year"),
        )
        for entry in _require(document, "created", path)
    )

    search = document.get("search") or {}
    verification = document.get("verification") or {}
    admission = document.get("admission") or {}

    shares = admission.get("ecosystem_share") or {}
    ecosystems = {language.ecosystem for language in languages}
    if not shares:
        shares = dict.fromkeys(ecosystems, 1.0 / len(ecosystems))
    missing = ecosystems - set(shares)
    if missing:
        raise CorpusConfigError(
            f"{path}: admission.ecosystem_share does not cover {sorted(missing)}."
        )

    return GridConfig(
        languages=languages,
        stars=stars,
        pushed=pushed,
        created=created,
        qualifiers=tuple(document.get("qualifiers") or ()),
        sort=str(search.get("sort", "stars")),
        order=str(search.get("order", "desc")),
        per_page=int(search.get("per_page", 100)),
        results_cap=int(search.get("results_cap", RESULTS_CAP)),
        registry_probe_limit=int(verification.get("registry_probe_limit", 3)),
        candidate_multiplier=float(admission.get("candidate_multiplier", 2.5)),
        ecosystem_share={key: float(value) for key, value in shares.items()},
    )


@dataclass
class Cell:
    """One partition of the frame, and everything the run learned about it."""

    key: str
    language: str
    ecosystem: str
    stars: str
    stars_min: int
    stars_max: int | None
    pushed: str
    created: str
    query: str
    #: The frame's own cap, carried on the cell so `available` does not have to
    #: reach for a module constant that a test frame may have lowered.
    results_cap: int = RESULTS_CAP
    #: `total_count` as GitHub reported it, or 0 for an infeasible cell that
    #: was never asked about.
    total_count: int = 0
    #: True when the band could not be split below the results cap; the frame
    #: for this cell is then the first `results_cap` by the configured sort,
    #: and `sampling_weight` says so by being computed from the capped count.
    capped: bool = False
    #: True when the created and pushed bands cannot both hold: a repository
    #: created in 2023 cannot have gone unpushed for four years. Recorded
    #: rather than silently dropped, so WP-4's "no stratum cell empty" check
    #: is not tripped by arithmetic.
    infeasible: bool = False
    allocation: int = 0
    #: Candidates actually *verified* for this cell — which is the number the
    #: sampling weight divides by. A cell that fills its allocation early stops
    #: examining, and the candidates it drew but never looked at are not part
    #: of the sample and must not be in the denominator.
    examined: int = 0
    admitted: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    sampling_weight: float | None = None

    @property
    def available(self) -> int:
        """How many of this cell's repositories the Search API will hand over."""
        return min(self.total_count, self.results_cap)


def _is_infeasible(pushed: PushedBand, created: CreatedBand, today: date) -> bool:
    """Whether the two bands describe an empty intersection by construction.

    A repository cannot have been last pushed before it existed. If the
    earliest possible creation date in this created-band is *later* than the
    newest push this pushed-band allows, nothing can be in both.
    """
    if created.min_year is None:
        return False
    earliest_creation = date(created.min_year, 1, 1)
    newest_push = today - timedelta(days=pushed.min_months * DAYS_PER_MONTH)
    return earliest_creation > newest_push


def build_cells(grid: GridConfig, today: date) -> list[Cell]:
    """Every cell of the frame, with its query string resolved against `today`."""
    cells: list[Cell] = []
    for language in grid.languages:
        for star in grid.stars:
            for pushed in grid.pushed:
                for created in grid.created:
                    qualifiers = [
                        language.qualifier,
                        star.qualifier(),
                        pushed.qualifier(today),
                        created.qualifier(),
                        *grid.qualifiers,
                    ]
                    cells.append(
                        Cell(
                            key=f"{language.name}|{star.name}|{pushed.name}|{created.name}",
                            language=language.name,
                            ecosystem=language.ecosystem,
                            stars=star.name,
                            stars_min=star.min,
                            stars_max=star.max,
                            pushed=pushed.name,
                            created=created.name,
                            query=" ".join(qualifiers),
                            results_cap=grid.results_cap,
                            infeasible=_is_infeasible(pushed, created, today),
                        )
                    )
    return cells


def _star_qualifier(low: int, high: int | None) -> str:
    return f"stars:>={low}" if high is None else f"stars:{low}..{high}"


def split_star_range(low: int, high: int | None) -> tuple[tuple[int, int | None], ...]:
    """Cut one star range in two, geometrically.

    Geometric rather than arithmetic because star counts are heavy-tailed:
    the arithmetic midpoint of 51..200 is 125, and almost every repository in
    that band sits below it, so the "split" would leave one half still over
    the cap and the other nearly empty. An open-ended band is cut at three
    times its floor for the same reason, and can be cut again.

    Returns an empty tuple when the range is a single star value and there is
    nothing left to cut.
    """
    if high is None:
        return ((low, low * 3 - 1), (low * 3, None))
    if high <= low:
        return ()
    midpoint = int((low * high) ** 0.5)
    midpoint = max(low, min(midpoint, high - 1))
    return ((low, midpoint), (midpoint + 1, high))


def _replace_star_qualifier(query: str, low: int, high: int | None) -> str:
    return " ".join(
        _star_qualifier(low, high) if part.startswith("stars:") else part
        for part in query.split(" ")
    )


def enumerate_cell(
    cell: Cell, client: ResearchClient, grid: GridConfig, depth: int = 0
) -> list[Cell]:
    """Count a cell, splitting its star band until each piece fits the cap.

    Returns the cells to actually sample from — `[cell]` when one enumeration
    was enough, or its split descendants. An infeasible cell is returned
    un-enumerated and costs no request: asking GitHub to confirm that nothing
    was created in 2023 and left unpushed since 2021 is a search call spent on
    arithmetic.
    """
    if cell.infeasible:
        return [cell]

    payload = client.search_repositories(
        cell.query, page=1, per_page=1, sort=grid.sort, order=grid.order
    )
    cell.total_count = int(payload.get("total_count") or 0)

    if cell.total_count <= grid.results_cap:
        return [cell]

    pieces = split_star_range(cell.stars_min, cell.stars_max)
    if depth >= MAX_SPLIT_DEPTH or not pieces:
        # A single star value with more than a thousand repositories in it.
        # Nothing left to cut; the cell's frame becomes its first `results_cap`
        # by the configured sort, and the manifest says `capped: true` so no
        # analysis mistakes it for a simple random sample of the whole cell.
        cell.capped = True
        logger.info(
            "Cell %s still holds %d repositories at depth %d; capping at %d.",
            cell.key,
            cell.total_count,
            depth,
            grid.results_cap,
        )
        return [cell]

    split: list[Cell] = []
    for low, high in pieces:
        child = Cell(
            key=f"{cell.key}+{low}-{high if high is not None else 'inf'}",
            language=cell.language,
            ecosystem=cell.ecosystem,
            stars=f"{low}..{high if high is not None else '+'}",
            stars_min=low,
            stars_max=high,
            pushed=cell.pushed,
            created=cell.created,
            query=_replace_star_qualifier(cell.query, low, high),
            results_cap=cell.results_cap,
        )
        split.extend(enumerate_cell(child, client, grid, depth + 1))
    return split


# ── allocation ─────────────────────────────────────────────────────────────


def allocate(cells: list[Cell], target: int, grid: GridConfig) -> None:
    """Spread `target` admissions across the cells, tilted toward the stale ones.

    Equal-per-cell within an ecosystem, multiplied by the pushed band's
    `oversample`, then clipped to what each cell actually holds and the
    leftover redistributed. Equal allocation rather than proportional is the
    design: proportional allocation would spend the corpus on the populous
    young cells and leave the abandoned ones — the ones this product exists
    to find — with two repositories each.

    Writes `allocation` and `sampling_weight` onto each cell in place.
    """
    oversample = {band.name: band.oversample for band in grid.pushed}

    by_ecosystem: dict[str, list[Cell]] = {}
    for cell in cells:
        if cell.infeasible or cell.available == 0:
            continue
        by_ecosystem.setdefault(cell.ecosystem, []).append(cell)

    for ecosystem, group in by_ecosystem.items():
        share = grid.ecosystem_share.get(ecosystem, 0.0)
        budget = round(target * share)
        weights = [oversample.get(cell.pushed, 1.0) for cell in group]
        total_weight = sum(weights) or 1.0

        for cell, weight in zip(group, weights, strict=True):
            cell.allocation = min(cell.available, round(budget * weight / total_weight))

        # Cells that could not absorb their share hand it back. One pass is
        # enough in practice and a loop risks not terminating on a frame where
        # every cell is small; the shortfall is reported rather than hidden.
        shortfall = budget - sum(cell.allocation for cell in group)
        if shortfall > 0:
            headroom = [cell for cell in group if cell.available > cell.allocation]
            for index, cell in enumerate(headroom):
                extra = shortfall // len(headroom) + (
                    1 if index < shortfall % len(headroom) else 0
                )
                cell.allocation = min(cell.available, cell.allocation + extra)

        logger.info(
            "Allocated %d of %d %s admissions across %d cell(s).",
            sum(cell.allocation for cell in group),
            budget,
            ecosystem,
            len(group),
        )

    # The weight is deliberately *not* set here. It divides by the number of
    # candidates actually examined, and a cell that fills its allocation early
    # stops examining — so the denominator is not known until verification has
    # run. `finalize_weights` sets it.


def finalize_weights(cells: list[Cell]) -> None:
    """Set each cell's expansion weight from the candidates it actually examined.

    One admitted repository stands for `available / examined` in the frame.

    The denominator is candidates **examined**, not candidates admitted.
    Verification is a filter on the cell, so the admitted repositories are a
    uniform random sample of the cell's *admissible* subpopulation, whose size
    is itself estimated by `available x admitted/examined`. The expansion
    weight is `(available x admitted/examined) / admitted`, and the two
    `admitted` terms cancel.

    It is also not the number *drawn*. A cell that fills its allocation stops
    verifying, and the candidates it drew but never looked at were never part
    of the sample — counting them would inflate every estimate from that
    stratum in proportion to how early it filled.
    """
    for cell in cells:
        cell.sampling_weight = (cell.available / cell.examined) if cell.examined else None


def _candidates_wanted(cell: Cell, grid: GridConfig) -> int:
    """How many candidates to draw so `allocation` of them survive verification.

    §10 Phase 11 expects ~50% admission and says to oversample accordingly.
    Clipped to what the cell holds: a cell with six repositories cannot yield
    fifteen candidates however much the multiplier asks for.
    """
    if cell.allocation <= 0:
        return 0
    return min(cell.available, round(cell.allocation * grid.candidate_multiplier))


# ── sampling ───────────────────────────────────────────────────────────────


def sample_indices(cell: Cell, grid: GridConfig, seed: int) -> list[int]:
    """Which result positions to draw from this cell, seeded and reproducible.

    Seeded per cell rather than from one run-wide stream, so that a resumed
    run — which replays some cells from the checkpoint and enumerates others —
    draws the same positions as an uninterrupted one. A single shared `Random`
    would make the sample depend on the order cells happened to complete in,
    which is the one thing a seed is supposed to rule out.
    """
    wanted = _candidates_wanted(cell, grid)
    if wanted <= 0:
        return []
    rng = random.Random(f"{seed}:{cell.key}")  # noqa: S311 - sampling, not crypto
    return sorted(rng.sample(range(cell.available), wanted))


def draw_candidates(
    cell: Cell, client: ResearchClient, grid: GridConfig, seed: int
) -> list[dict]:
    """Fetch exactly the pages holding this cell's sampled positions.

    Pages are the unit GitHub sells, so drawing positions 3, 140 and 890 costs
    three pages rather than nine — and a cell allocated four repositories
    typically costs one.
    """
    indices = sample_indices(cell, grid, seed)
    if not indices:
        return []

    pages: dict[int, list[dict]] = {}
    drawn: list[dict] = []
    for index in indices:
        page = index // grid.per_page + 1
        offset = index % grid.per_page
        if page not in pages:
            payload = client.search_repositories(
                cell.query,
                page=page,
                per_page=grid.per_page,
                sort=grid.sort,
                order=grid.order,
            )
            items = payload.get("items")
            pages[page] = items if isinstance(items, list) else []
        items = pages[page]
        if offset < len(items) and isinstance(items[offset], dict):
            drawn.append(items[offset])

    # Shuffled, and that is load-bearing rather than tidy. The positions were
    # sampled at random but are fetched in ascending order, and position
    # correlates with the cell's sort (`stars desc`). Verifying in that order
    # and stopping at the allocation would take the highest-starred candidates
    # of every cell — a quota sample of the head of the ranking, wearing a
    # random sample's weights. Shuffling first makes the examined set a
    # uniform random subset of the drawn set, whatever the stop.
    random.Random(f"{seed}:{cell.key}:order").shuffle(drawn)  # noqa: S311
    return drawn


# ── verification ───────────────────────────────────────────────────────────


@dataclass
class ManifestRecord:
    """One manifest of an admitted repository, as `scan_corpus` will read it.

    Carries the resolved plan, lockfile inheritance included: whether a
    workspace member borrows the root lockfile depends on what the root
    *declares*, which is knowable only with the bytes in hand. `build_corpus`
    has them; `scan_corpus` would have to re-derive it. Recording the resolved
    answer makes the manifest a complete account of what was scanned.
    """

    path: str
    sha: str
    size: int
    ecosystem: str
    parser_name: str
    blob_path: str | None = None
    lockfile_path: str | None = None
    lockfile_sha: str | None = None
    lockfile_size: int = 0


@dataclass
class Candidate:
    """One repository considered, admitted or not, with the reason either way."""

    full_name: str
    github_repo_id: int
    owner_login: str
    owner_id: int
    default_branch: str
    cell: str
    ecosystem: str
    admitted: bool
    reason: str | None = None
    stars: int = 0
    pushed_at: str | None = None
    created_at: str | None = None
    sampling_weight: float | None = None
    dependency_set_hash: str | None = None
    dependency_count: int = 0
    manifests: list[ManifestRecord] = field(default_factory=list)
    skipped_manifest_count: int = 0


def dependency_set_hash(names: set[tuple[str, str]]) -> str:
    """D14's near-duplicate control: a hash of the sorted dependency names.

    Names only — not versions. Two checkouts of the same scaffold a year apart
    pin different versions of the same forty packages, and a hash over the
    versions would call them distinct, which is exactly the duplicate the
    control exists to catch. The ecosystem is in the key because `requests`
    means different things in npm and PyPI.
    """
    joined = "\n".join(f"{ecosystem}:{name}" for ecosystem, name in sorted(names))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _registry_resolvable(
    specs_by_ecosystem: dict[str, list[adapters.DepSpec]], limit: int
) -> bool:
    """Whether at least one declared dependency is one a registry knows.

    §10 Phase 11 asks for "≥1 registry-resolvable dependency", and it is a real
    lookup rather than an inference from the specifier: a repository whose
    every dependency is a private or deleted package parses perfectly and
    would enter the corpus as a scan with nothing assessable in it — scoring
    100, indistinguishable from a healthy project.

    At most `limit` lookups per ecosystem. The check is "does anything here
    resolve", so the first success ends it, and a repository whose first three
    packages are all unknown is not one this corpus wants anyway.
    """
    for ecosystem, specs in specs_by_ecosystem.items():
        assessable = [spec for spec in specs if not spec.is_unassessable]
        if not assessable:
            continue
        client = adapters.get_adapter(ecosystem).registry_client()
        for spec in assessable[:limit]:
            try:
                facts = client.facts(spec.name, spec.resolved_version)
            except http.UpstreamError:
                continue
            if not facts.not_found and not facts.unavailable:
                return True
    return False


def verify_candidate(
    item: dict,
    cell: Cell,
    client: ResearchClient,
    grid: GridConfig,
    seen_hashes: dict[str, str],
    blob_dir: Path,
) -> Candidate:
    """One tree call, then the manifests, then the four admission checks.

    Fork and archive status are not checked here: the query carried
    `fork:false archived:false`, which is both cheaper and stricter than a
    per-candidate check, because it also keeps them out of `total_count` and
    therefore out of the sampling weights.
    """
    owner = item.get("owner") or {}
    candidate = Candidate(
        full_name=str(item.get("full_name") or ""),
        github_repo_id=int(item.get("id") or 0),
        owner_login=str(owner.get("login") or ""),
        owner_id=int(owner.get("id") or 0),
        default_branch=str(item.get("default_branch") or "main"),
        cell=cell.key,
        ecosystem=cell.ecosystem,
        admitted=False,
        stars=int(item.get("stargazers_count") or 0),
        pushed_at=item.get("pushed_at"),
        created_at=item.get("created_at"),
        # Left None here, and stamped by `build_corpus` once the run knows how
        # many candidates this cell actually examined. A weight copied at
        # verification time would be the weight of a cell that had not finished
        # being sampled.
        sampling_weight=None,
    )

    try:
        tree = client.tree(
            candidate.owner_login, item.get("name") or "", candidate.default_branch
        )
    except http.UpstreamError:
        # Renamed, deleted, or briefly unreachable. Recorded as a rejection so
        # the admission rate has an honest denominator.
        candidate.reason = REJECT_UNREACHABLE
        return candidate

    plans = plan_manifests(tree)
    if not plans:
        candidate.reason = REJECT_NO_MANIFEST
        return candidate
    candidate.skipped_manifest_count = max(0, len(tree_manifest_paths(tree)) - len(plans))

    sources: dict[str, bytes] = {}
    for plan in plans:
        if plan.size > MAX_MANIFEST_BYTES:
            candidate.skipped_manifest_count += 1
            continue
        try:
            blob = client.blob(
                candidate.owner_login,
                item.get("name") or "",
                plan.sha,
                MAX_MANIFEST_BYTES,
            )
        except http.UpstreamError:
            blob = None
        if blob is None:
            candidate.skipped_manifest_count += 1
            continue
        sources[plan.path] = blob

    if not sources:
        candidate.reason = REJECT_UNREADABLE
        return candidate

    # Exactly the product's rule, from the product's function: a workspace
    # member inherits the root lockfile only where the root's globs name it.
    adopt_workspace_lockfiles(plans, sources)

    specs_by_ecosystem: dict[str, list[adapters.DepSpec]] = {}
    names: set[tuple[str, str]] = set()
    records: list[ManifestRecord] = []
    for plan in plans:
        manifest_bytes = sources.get(plan.path)
        if manifest_bytes is None:
            continue
        try:
            # Parsed without the lockfile: admission is about *what* a
            # repository declares, and a lockfile changes only which version
            # each declaration resolves to. `scan_corpus` reads the lockfile,
            # from the sha recorded here, because the version is exactly what
            # it is measuring.
            specs = plan.adapter.parse(manifest_bytes, None)
        except adapters.ManifestParseError:
            candidate.skipped_manifest_count += 1
            continue

        specs_by_ecosystem.setdefault(plan.adapter.ecosystem, []).extend(specs)
        names.update((plan.adapter.ecosystem, spec.name) for spec in specs)
        records.append(
            ManifestRecord(
                path=plan.path,
                sha=plan.sha,
                size=plan.size,
                ecosystem=plan.adapter.ecosystem,
                parser_name=plan.adapter.parser_name,
                blob_path=_archive_blob(blob_dir, plan.sha, manifest_bytes),
                lockfile_path=plan.lockfile_path,
                lockfile_sha=plan.lockfile_sha,
                lockfile_size=plan.lockfile_size,
            )
        )

    if not names:
        candidate.reason = REJECT_NO_DEPENDENCIES
        return candidate

    digest = dependency_set_hash(names)
    if digest in seen_hashes:
        candidate.dependency_set_hash = digest
        candidate.reason = REJECT_DUPLICATE_DEPSET
        return candidate

    if not _registry_resolvable(specs_by_ecosystem, grid.registry_probe_limit):
        candidate.reason = REJECT_NO_RESOLVABLE
        return candidate

    candidate.admitted = True
    candidate.dependency_set_hash = digest
    candidate.dependency_count = len(names)
    candidate.manifests = records
    return candidate


def _archive_blob(blob_dir: Path, sha: str, content: bytes) -> str:
    """Store one manifest under its sha, and return the path the manifest records.

    Sharded two characters deep because a thousand repositories is a few
    thousand files and a flat directory of them is unpleasant on every
    filesystem this project runs on. Content-addressed, so the identical
    `package.json` in forty scaffolds is stored once and the dedup control has
    a second, incidental witness.

    Only *manifests* are archived. A lockfile can be megabytes, `scan_corpus`
    re-fetches it by the sha recorded beside it, and archiving a thousand of
    them would turn a 6 MB directory into a gigabyte for no gain.
    """
    relative = Path(BLOB_DIRNAME) / sha[:2] / sha
    absolute = blob_dir.parent / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    if not absolute.exists():
        absolute.write_bytes(content)
    return relative.as_posix()


# ── checkpointing ──────────────────────────────────────────────────────────


def append_jsonl(path: Path, payload: dict, *, fsync: bool = False) -> None:
    """Append one JSON object as a line, terminating any torn line before it.

    **The terminating newline is the part that matters.** A process killed
    mid-write leaves a fragment with no newline at the end of the file. An
    append that did not check would glue its own object onto that fragment,
    producing one unparseable line where there had been one — so the crash
    would cost not just the record in flight but the next one written, and the
    loss would be silent because `read_jsonl` discards both together. The cost
    of the check is a one-byte read per record.

    `fsync` is for the corpus *scan* checkpoint, where a line stands for a
    database transaction that has already committed and a lost line means work
    redone against the network. The builder's lines are cheap to redo, so it
    settles for a flush.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = path.exists() and path.stat().st_size > 0
    if needs_newline:
        with path.open("rb") as probe:
            probe.seek(-1, os.SEEK_END)
            needs_newline = probe.read(1) != b"\n"

    with path.open("a", encoding="utf-8") as handle:
        if needs_newline:
            handle.write("\n")
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        if fsync:
            os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict]:
    """Every intact record in a checkpoint, skipping any line a kill -9 tore.

    Everything before a torn line is still good, and the work that line
    recorded is simply redone — which is the whole property `--resume` rests
    on (§10 Phase 11's "kill -9 mid-run -> --resume completes without
    duplicate rows").
    """
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Discarding a truncated checkpoint line in %s.", path.name)
    return rows


@dataclass
class Checkpoint:
    """Append-only JSONL beside the corpus, replayed by `--resume`.

    Two files rather than one because they are written at different times and
    read for different questions: cells answer "has this partition been
    counted and allocated", candidates answer "has this repository been
    looked at". A run interrupted between the two resumes from the first.

    Each line is flushed as it is written. A checkpoint that is only durable
    at process exit is not a checkpoint — the process this one protects
    against is the one that does not exit cleanly.
    """

    directory: Path

    def __post_init__(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.directory / name

    def append(self, name: str, payload: dict) -> None:
        append_jsonl(self._path(name), payload)

    def read(self, name: str) -> list[dict]:
        return read_jsonl(self._path(name))

    def clear(self) -> None:
        for name in (CELLS_CHECKPOINT, CANDIDATES_CHECKPOINT):
            self._path(name).unlink(missing_ok=True)


# ── the run ────────────────────────────────────────────────────────────────


@dataclass
class BuildResult:
    manifest_path: Path
    report_path: Path
    admitted: int
    candidates: int
    cells: list[Cell]
    rejected: dict[str, int]


def _cell_from_checkpoint(payload: dict) -> Cell:
    """Replay an enumerated cell, without its tallies.

    `examined`, `admitted` and `rejected` are deliberately dropped and recomputed
    from the candidate checkpoint. They are derived from it, and restoring
    both would count every candidate of the previous run twice — an error that
    is invisible in the run itself and shows up as an impossible admission
    rate in the strata report.
    """
    counters = {"examined", "admitted", "rejected", "allocation", "sampling_weight"}
    known = set(Cell.__dataclass_fields__) - counters
    return Cell(**{key: value for key, value in payload.items() if key in known})


def build_corpus(
    *,
    out_dir: Path,
    grid: GridConfig,
    seed: int,
    target: int,
    client: ResearchClient,
    resume: bool = False,
    today: date | None = None,
    progress=None,
) -> BuildResult:
    """Enumerate, allocate, sample, verify, and write the two deliverables.

    `progress` is an optional callable taking one line of text — the
    management command passes `stdout.write`, and a test passes nothing.
    """
    today = today or datetime.now(UTC).date()
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = Checkpoint(out_dir / CHECKPOINT_DIRNAME)
    if not resume:
        checkpoint.clear()

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    # ── enumerate ──
    recorded_cells = {row["key"]: row for row in checkpoint.read(CELLS_CHECKPOINT)}
    cells: list[Cell] = []
    for cell in build_cells(grid, today):
        replayed = [
            _cell_from_checkpoint(row)
            for key, row in recorded_cells.items()
            if key == cell.key or key.startswith(f"{cell.key}+")
        ]
        if replayed:
            cells.extend(replayed)
            continue
        produced = enumerate_cell(cell, client, grid)
        for child in produced:
            checkpoint.append(CELLS_CHECKPOINT, asdict(child))
        cells.extend(produced)
    say(f"Enumerated {len(cells)} cell(s) from {len(grid.languages)} language(s).")

    allocate(cells, target, grid)

    # ── sample and verify ──
    done = checkpoint.read(CANDIDATES_CHECKPOINT)
    seen_repo_ids = {row.get("github_repo_id") for row in done}
    seen_hashes: dict[str, str] = {
        row["dependency_set_hash"]: row["full_name"]
        for row in done
        if row.get("admitted") and row.get("dependency_set_hash")
    }
    candidates: list[Candidate] = [_candidate_from_checkpoint(row) for row in done]

    by_key = {cell.key: cell for cell in cells}
    for row in done:
        cell = by_key.get(row.get("cell", ""))
        if cell is None:
            continue
        cell.examined += 1
        if row.get("admitted"):
            cell.admitted += 1
        elif row.get("reason"):
            cell.rejected[row["reason"]] = cell.rejected.get(row["reason"], 0) + 1

    blob_dir = out_dir / BLOB_DIRNAME
    for cell in cells:
        if cell.allocation <= 0:
            continue
        if cell.admitted >= cell.allocation:
            # Filled on an earlier run. Nothing to draw and nothing to verify.
            continue
        if cell.examined >= _candidates_wanted(cell, grid):
            # Every candidate this cell was ever going to draw has been looked
            # at; it simply did not fill. Re-running `draw_candidates` would
            # spend search calls re-fetching pages only to discard every item —
            # on a resume near the end of a run, that is most of the frame.
            continue

        for item in draw_candidates(cell, client, grid, seed):
            if cell.admitted >= cell.allocation:
                # The quota is met. Every remaining candidate goes unexamined,
                # which is what keeps the corpus the size it was asked for:
                # verifying all of them and admitting every passer overshoots
                # the target by the margin `candidate_multiplier` adds.
                break
            if item.get("id") in seen_repo_ids:
                continue
            seen_repo_ids.add(item.get("id"))
            cell.examined += 1
            candidate = verify_candidate(item, cell, client, grid, seen_hashes, blob_dir)
            checkpoint.append(CANDIDATES_CHECKPOINT, _candidate_payload(candidate))
            candidates.append(candidate)
            if candidate.admitted:
                cell.admitted += 1
                seen_hashes[candidate.dependency_set_hash or ""] = candidate.full_name
            elif candidate.reason:
                cell.rejected[candidate.reason] = (
                    cell.rejected.get(candidate.reason, 0) + 1
                )
        say(
            f"{cell.key}: {cell.admitted}/{cell.allocation} admitted "
            f"from {cell.examined} examined."
        )

    finalize_weights(cells)
    # Only now can a candidate carry its weight: the denominator is what its
    # cell examined, which is not known while the cell is still being examined.
    # Stamped on every candidate, admitted or not, so a rejected row in the
    # checkpoint still says which cell's sampling it came out of.
    for candidate in candidates:
        cell = by_key.get(candidate.cell)
        if cell is not None:
            candidate.sampling_weight = cell.sampling_weight

    admitted = [candidate for candidate in candidates if candidate.admitted]
    rejected: dict[str, int] = {}
    for candidate in candidates:
        if not candidate.admitted and candidate.reason:
            rejected[candidate.reason] = rejected.get(candidate.reason, 0) + 1

    manifest_path = out_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(
            _manifest_document(
                grid=grid,
                seed=seed,
                target=target,
                today=today,
                cells=cells,
                admitted=admitted,
                candidates=candidates,
                client=client,
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report_path = out_dir / STRATA_REPORT_FILENAME
    report_path.write_text(
        strata_report(
            grid=grid,
            seed=seed,
            target=target,
            today=today,
            cells=cells,
            admitted=admitted,
            candidates=candidates,
            rejected=rejected,
        ),
        encoding="utf-8",
    )

    return BuildResult(
        manifest_path=manifest_path,
        report_path=report_path,
        admitted=len(admitted),
        candidates=len(candidates),
        cells=cells,
        rejected=rejected,
    )


def _candidate_payload(candidate: Candidate) -> dict:
    payload = asdict(candidate)
    payload["manifests"] = [asdict(record) for record in candidate.manifests]
    return payload


def _candidate_from_checkpoint(row: dict) -> Candidate:
    known = set(Candidate.__dataclass_fields__)
    data = {key: value for key, value in row.items() if key in known}
    data["manifests"] = [
        ManifestRecord(
            **{
                key: value
                for key, value in record.items()
                if key in ManifestRecord.__dataclass_fields__
            }
        )
        for record in row.get("manifests") or []
    ]
    return Candidate(**data)


def _manifest_document(
    *,
    grid: GridConfig,
    seed: int,
    target: int,
    today: date,
    cells: list[Cell],
    admitted: list[Candidate],
    candidates: list[Candidate],
    client: ResearchClient,
) -> dict:
    """`corpus_manifest.json` — the fields §10 Phase 11 names, and their provenance.

    The grid, seed and timestamp travel with the data rather than in a
    separate note, because a corpus whose frame has to be looked up somewhere
    else is a corpus whose frame will eventually be lost.
    """
    return {
        "schema": "repovitals/corpus_manifest@1",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_date": today.isoformat(),
        "seed": seed,
        "target": target,
        "grid": {
            "languages": [asdict(language) for language in grid.languages],
            "stars": [asdict(band) for band in grid.stars],
            "pushed": [asdict(band) for band in grid.pushed],
            "created": [asdict(band) for band in grid.created],
            "qualifiers": list(grid.qualifiers),
            "ecosystem_share": grid.ecosystem_share,
            "candidate_multiplier": grid.candidate_multiplier,
            "registry_probe_limit": grid.registry_probe_limit,
        },
        "search": {
            "sort": grid.sort,
            "order": grid.order,
            "per_page": grid.per_page,
            "results_cap": grid.results_cap,
            "calls": client.search_calls,
        },
        "counts": {
            "cells": len(cells),
            "cells_infeasible": sum(1 for cell in cells if cell.infeasible),
            "cells_empty": sum(
                1 for cell in cells if not cell.infeasible and cell.total_count == 0
            ),
            "cells_capped": sum(1 for cell in cells if cell.capped),
            "candidates": len(candidates),
            "admitted": len(admitted),
            "by_ecosystem": {
                ecosystem: sum(1 for c in admitted if c.ecosystem == ecosystem)
                for ecosystem in sorted({c.ecosystem for c in admitted})
            },
        },
        "cells": [asdict(cell) for cell in cells],
        "repositories": [
            {
                "full_name": candidate.full_name,
                "github_repo_id": candidate.github_repo_id,
                "owner_login": candidate.owner_login,
                "owner_id": candidate.owner_id,
                "default_branch": candidate.default_branch,
                "ecosystem": candidate.ecosystem,
                "cell": candidate.cell,
                "sampling_weight": candidate.sampling_weight,
                "stars": candidate.stars,
                "pushed_at": candidate.pushed_at,
                "created_at": candidate.created_at,
                "dependency_set_hash": candidate.dependency_set_hash,
                "dependency_count": candidate.dependency_count,
                "skipped_manifest_count": candidate.skipped_manifest_count,
                "checks": {
                    "not_fork": True,
                    "not_archived": True,
                    "supported_manifest": True,
                    "registry_resolvable_dependency": True,
                    "dependency_set_unique": True,
                },
                "manifests": [asdict(record) for record in candidate.manifests],
            }
            for candidate in admitted
        ],
    }


def strata_report(
    *,
    grid: GridConfig,
    seed: int,
    target: int,
    today: date,
    cells: list[Cell],
    admitted: list[Candidate],
    candidates: list[Candidate],
    rejected: dict[str, int],
) -> str:
    """`strata_report.md` — WP-4's review checklist, already computed.

    The teammate is asked to confirm six things (File B, WP-4): the admitted
    total, the ecosystem split, that no stratum cell is empty, the admission
    rate, that the dedup discard count is above zero, and that the
    reproducibility fields are present. Each is a line here, with the number
    beside it, so the review is reading rather than arithmetic — and so that a
    run which fails one of them fails it visibly rather than in a spreadsheet
    nobody built.
    """
    total = len(admitted)
    by_ecosystem: dict[str, int] = {}
    for candidate in admitted:
        by_ecosystem[candidate.ecosystem] = by_ecosystem.get(candidate.ecosystem, 0) + 1

    considered = len(candidates)
    admission_rate = (total / considered) if considered else 0.0
    live_cells = [cell for cell in cells if not cell.infeasible]
    empty = [cell for cell in live_cells if cell.total_count == 0]
    unfilled = [cell for cell in live_cells if cell.allocation > cell.admitted]
    stale_bands = {band.name for band in grid.pushed if band.oversample > 1.0}
    empty_stale = [cell for cell in empty if cell.pushed in stale_bands]

    lines: list[str] = [
        "# Corpus strata report",
        "",
        "Generated by `manage.py build_corpus` (§10 Phase 11, D14). Every number",
        "below is computed from the run that wrote `corpus_manifest.json` beside",
        "this file; nothing here is entered by hand.",
        "",
        "## Reproducibility",
        "",
        f"- Seed: `{seed}`",
        f"- Run date (the frame's `pushed:` and `created:` bounds resolve against it): `{today.isoformat()}`",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        f"- Target admissions: {target}",
        f"- Search sort/order: `{grid.sort}`/`{grid.order}`, results cap {grid.results_cap}",
        f"- Candidate multiplier: {grid.candidate_multiplier}x (expects ~50% admission)",
        "",
        "## WP-4 review checklist",
        "",
        f"- **Total admitted:** {total} (target {target})",
        "- **Ecosystem split:** "
        + ", ".join(
            f"{ecosystem} {count} ({count / total:.0%})"
            if total
            else f"{ecosystem} {count}"
            for ecosystem, count in sorted(by_ecosystem.items())
        ),
        f"- **Admission rate:** {admission_rate:.0%} ({total} of {considered} candidates)",
        f"- **Dedup discards:** {rejected.get(REJECT_DUPLICATE_DEPSET, 0)}",
        f"- **Empty cells:** {len(empty)} of {len(live_cells)} feasible "
        f"({sum(1 for cell in cells if cell.infeasible)} more are infeasible by construction "
        "— a created-year band that cannot overlap its pushed band)",
        f"- **Empty *stale* cells:** {len(empty_stale)}"
        + ("  ← flag these" if empty_stale else ""),
        f"- **Cells that did not fill their allocation:** {len(unfilled)}",
        f"- **Cells still over the results cap after splitting:** "
        f"{sum(1 for cell in cells if cell.capped)}",
        "",
        "## Why a candidate was rejected",
        "",
        "| Reason | Count |",
        "|---|---|",
    ]
    for reason in REJECT_REASONS:
        lines.append(f"| `{reason}` | {rejected.get(reason, 0)} |")

    lines += [
        "",
        "## Cells",
        "",
        "`weight` is the expansion weight recorded on every admitted repository",
        "in this cell: one admitted repository stands for this many in the frame.",
        "It is the cell's available population over the number of candidates",
        "*examined*, so verification's own attrition is already inside it. A",
        "cell that filled its allocation stopped examining, and the candidates",
        "it never looked at are correctly absent from the denominator.",
        "",
        "| Cell | Ecosystem | Population | Allocated | Examined | Admitted | Weight | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cell in sorted(cells, key=lambda c: c.key):
        notes: list[str] = []
        if cell.infeasible:
            notes.append("infeasible")
        if cell.capped:
            notes.append("capped")
        if not cell.infeasible and cell.total_count == 0:
            notes.append("empty")
        lines.append(
            f"| `{cell.key}` | {cell.ecosystem} | {cell.total_count} | "
            f"{cell.allocation} | {cell.examined} | {cell.admitted} | "
            f"{'' if cell.sampling_weight is None else f'{cell.sampling_weight:.1f}'} | "
            f"{', '.join(notes)} |"
        )

    lines += [
        "",
        "## What this frame cannot say",
        "",
        "- Cells marked `capped` hold more repositories than the Search API will",
        "  enumerate (§8: 1,000 results per query, hard). Their sample is drawn",
        f"  from the first {grid.results_cap} by `{grid.sort}` order, so it is a sample of that",
        "  ranked head and not of the whole cell. The weight is computed from the",
        "  capped count, so weighted totals under-count those cells rather than",
        "  silently over-stating their precision.",
        "- The corpus is a **cross-section as of the run date** (D14). Every",
        "  repository is scanned once; nothing here supports a claim about change",
        "  over time.",
        "- Admission requires a parseable manifest with at least one",
        "  registry-resolvable dependency. The population this corpus represents",
        "  is therefore repositories *with assessable dependencies*, not all",
        "  repositories in the cell — which is what the weight's denominator",
        "  (candidates examined, not admitted) accounts for.",
        "",
    ]
    return "\n".join(lines)
