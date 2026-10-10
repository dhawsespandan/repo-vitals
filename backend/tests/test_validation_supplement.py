"""S1's supplementary analyses (File C §1.3, §2.4.6, §2.4.7).

Panels here are built by hand, with no database: every number the supplement
reports is a recomputation through the shipped engine over a panel, so a panel
of a few repositories whose scores can be worked out on paper is the most
direct test of what it computes.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal

import pytest

from apps.research.validation import stats, supplement
from apps.research.validation.panel import CorpusPanel, Occurrence, PanelRepository
from apps.scoring.normalize import Signals
from apps.scoring.weights import load_weights

CLEAN = Signals(staleness_days=0)
CRITICAL = Signals(vulnerability_count=3, cvss_max=Decimal("9.8"), staleness_days=10)
DEPRECATED = Signals(is_deprecated=True, staleness_days=900)


def repository(name, ecosystem, signals, weight=1.0) -> PanelRepository:
    return PanelRepository(
        scan_history_id=name,
        github_repo_id=hash(name) % 10**6,
        full_name=name,
        owner=name.split("/")[0],
        ecosystems=ecosystem,
        sampling_weight=weight,
        stored_score=Decimal("0"),
        stored_classification="safe",
        stored_version="v1",
        occurrences=[Occurrence(ecosystem, False, s) for s in signals],
    )


def panel(*repositories) -> CorpusPanel:
    return CorpusPanel(snapshot_date=date(2026, 10, 7), repositories=list(repositories))


# ── strata and the roll-up's tail ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("assessed", "label"),
    [
        (0, "0"),
        (1, "1-5"),
        (5, "1-5"),
        (6, "6-15"),
        (40, "16-40"),
        (100, "41-100"),
        (101, "101+"),
    ],
)
def test_strata_are_inclusive_at_both_ends(assessed, label):
    assert supplement.stratum_of(assessed) == label


def test_the_tail_share_is_what_the_decayed_terms_add():
    """Two equal penalties at decay 0.5: the second adds half the first, so a
    third of the deduction is the roll-up's tail."""
    v2 = load_weights("v2")
    one = repository("a/one", "npm", [CRITICAL])
    two = repository("a/two", "npm", [CRITICAL, CRITICAL])
    clean = repository("a/clean", "npm", [CLEAN])

    rows = {r.full_name: r for r in supplement.facts(panel(one, two, clean), v2)}

    assert rows["a/one"].tail_share == 0
    assert rows["a/two"].tail_share == pytest.approx(1 / 3, abs=0.01)
    assert rows["a/clean"].deduction == 0
    assert rows["a/clean"].tail_share is None
    assert rows["a/two"].score < rows["a/one"].score


def test_a_repository_with_nothing_assessed_is_its_own_stratum():
    v2 = load_weights("v2")
    empty = repository("a/empty", "npm", [])

    (row,) = supplement.facts(panel(empty), v2)

    assert row.assessed == 0 and row.stratum == supplement.NO_ASSESSED
    assert row.score == 100


# ── §1.3: weighted shares ─────────────────────────────────────────────────


def test_a_share_is_weighted_by_the_frame_and_counted_beside_it():
    v2 = load_weights("v2")
    safe = repository("a/safe", "pypi", [CLEAN], weight=3.0)
    risky = repository("a/risky", "pypi", [CRITICAL, DEPRECATED], weight=1.0)

    shares = supplement.class_shares("v2", supplement.facts(panel(safe, risky), v2))
    pypi = {s.classification: s for s in shares if s.group == "pypi"}

    assert pypi["safe"].repositories == 1 and pypi["safe"].share == 0.5
    assert pypi["safe"].weighted_share == 0.75
    assert pypi["high_alert"].weighted_share == 0.25
    assert {s.group for s in shares} == {"all", "pypi"}


# ── RQ2 with dependency count partialled out ──────────────────────────────


def test_partial_spearman_removes_a_shared_driver():
    """x and y both follow z exactly: their correlation is all z, and nothing
    is left once z is partialled out."""
    z = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    x = [10.0, 21.0, 29.0, 42.0, 50.0, 61.0]
    y = [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0]

    assert stats.spearman(x, y) == pytest.approx(-1.0)
    assert supplement.partial_spearman(x, y, z) is None  # z explains both


def test_partial_spearman_matches_the_textbook_formula():
    x = [1.0, 3.0, 2.0, 5.0, 4.0, 6.0, 8.0, 7.0]
    y = [2.0, 1.0, 4.0, 3.0, 6.0, 5.0, 7.0, 8.0]
    z = [1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0]
    r_xy, r_xz, r_yz = stats.spearman(x, y), stats.spearman(x, z), stats.spearman(y, z)
    expected = (r_xy - r_xz * r_yz) / ((1 - r_xz**2) * (1 - r_yz**2)) ** 0.5

    assert supplement.partial_spearman(x, y, z) == pytest.approx(expected)


# ── RQ5: the gate's decisions ─────────────────────────────────────────────


def strata_row(stratum, ecosystem, n, shares, tail):
    return supplement.StratumRow(
        version="v2",
        stratum=stratum,
        ecosystem=ecosystem,
        repositories=n,
        shares=shares,
        weighted_shares=shares,
        median_score=50.0,
        median_tail_share=tail,
    )


def spread_facts(ecosystem: str, n: int = 30) -> list[supplement.RepoFacts]:
    """`n` repositories spread evenly over 0-100, a third in each class."""
    out = []
    for index in range(n):
        score = 100 * index / (n - 1)
        out.append(
            supplement.RepoFacts(
                full_name=f"{ecosystem}/{index}",
                ecosystem=ecosystem,
                weight=1.0,
                score=score,
                classification=(
                    "safe" if score >= 80 else "medium" if score >= 50 else "high_alert"
                ),
                assessed=index + 1,
                deduction=100 - score,
                top_term=(100 - score) / 2,
            )
        )
    return out


THREE = {"safe": 0.3, "medium": 0.3, "high_alert": 0.4}
ONE = {"safe": 0.0, "medium": 0.0, "high_alert": 1.0}
ANCHORS = [
    supplement.AnchorClass(
        "https://github.com/a/py", "pypi", "x@1", True, {"v2": "high_alert"}
    ),
    supplement.AnchorClass("https://github.com/a/js", "npm", "y@1", True, {"v2": "safe"}),
]


def gate(strata, anchors=ANCHORS, rho=None):
    rows = spread_facts("pypi") + spread_facts("npm")
    return supplement.trust_gate(
        "v2", rows, strata, anchors, rho or {"npm": -0.4, "pypi": -0.3}
    )


def test_the_gate_passes_when_every_part_holds():
    checks = gate(
        [
            strata_row("16-40", "npm", 20, THREE, 0.40),
            strata_row("16-40", "pypi", 20, THREE, 0.50),
        ]
    )

    assert supplement.gate_passes(checks, "v2"), [c for c in checks if not c.passed]
    # An npm anchor is not the PyPI gate's business, even when it is Safe.
    assert any(c.part == "G2" and c.observed == "1/1" for c in checks)


def test_a_wider_tail_gap_than_allowed_fails_g3():
    checks = gate(
        [
            strata_row("16-40", "npm", 20, THREE, 0.20),
            strata_row("16-40", "pypi", 20, THREE, 0.40),
        ]
    )

    failed = [c for c in checks if not c.passed]
    assert [c.part for c in failed] == ["G3"] and "tail share" in failed[0].criterion


def test_one_populated_class_fails_g3():
    checks = gate(
        [
            strata_row("16-40", "npm", 20, THREE, 0.4),
            strata_row("16-40", "pypi", 20, ONE, 0.4),
        ]
    )

    assert not supplement.gate_passes(checks, "v2")


def test_a_thin_stratum_is_not_compared_and_none_compared_fails():
    checks = gate(
        [
            strata_row("16-40", "npm", 20, THREE, 0.1),
            strata_row("16-40", "pypi", 14, ONE, 0.9),
        ]
    )

    g3 = [c for c in checks if c.part == "G3"]
    assert [c.passed for c in g3] == [False, True]  # none compared; the slope holds
    assert "0 of 5 strata compared" in g3[0].observed


def test_a_safe_pypi_anchor_fails_g2():
    anchors = [
        supplement.AnchorClass(
            "https://github.com/a/py", "pypi", "x@1", True, {"v2": "safe"}
        )
    ]
    checks = gate(
        [
            strata_row("6-15", "npm", 20, THREE, 0.4),
            strata_row("6-15", "pypi", 20, THREE, 0.4),
        ],
        anchors=anchors,
    )

    (g2,) = [c for c in checks if c.part == "G2"]
    assert not g2.passed and "a/py" in g2.observed


def test_a_rising_score_in_one_ecosystem_fails_g3():
    checks = gate(
        [
            strata_row("6-15", "npm", 20, THREE, 0.4),
            strata_row("6-15", "pypi", 20, THREE, 0.4),
        ],
        rho={"npm": -0.4, "pypi": 0.1},
    )

    assert not supplement.gate_passes(checks, "v2")


# ── the run and its files, on a small export-shaped folder ────────────────


def write_rows(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def export(tmp_path):
    report = tmp_path / "validation_report"
    write_rows(
        report / "scores.csv",
        ["repository", "scorecard", "scorecard_status"],
        [
            ["n/a", "4.1", "ok"],
            ["n/b", "", "not_found"],
            ["p/a", "6.0", "ok"],
            ["p/b", "2.0", "ok"],
        ],
    )
    write_rows(
        tmp_path / "anchors" / "wp2_anchor_set.csv",
        ["repo_url", "ecosystem"],
        [["https://github.com/p/a", "pypi"]],
    )
    write_rows(
        report / "anchors.csv",
        ["repo_url", "is_known_anchor", "anchor_package", "anchor_seen", "class_v1",
         "class_v2-candidate (AHP)", "verdict"],
        [["https://github.com/p/a", "True", "x@1", "True", "medium", "high_alert", "pass"]],
    )  # fmt: skip
    write_rows(
        report / "weights_comparison.csv",
        ["formula", "ecosystem", "deprecation", "severity", "count", "staleness"],
        [
            ["v1", "npm", ".46", ".28", ".16", ".10"],
            ["v1", "pypi", ".32", ".35", ".16", ".17"],
            ["v2-candidate (AHP)", "npm", ".272", ".483", ".157", ".088"],
            ["v2-candidate (AHP)", "pypi", ".19", ".524", ".157", ".129"],
            ["entropy", "npm", ".288", ".305", ".340", ".066"],
            ["entropy", "pypi", ".515", ".196", ".214", ".075"],
            ["ahp_eigenvector", "", ".272", ".483", ".157", ".088"],
        ],
    )
    write_rows(
        report / "correlation.csv",
        ["formula", "reference", "group", "covered", "repositories", "method", "weighted",
         "value", "ci_low", "ci_high"],
        [["v2-candidate (AHP)", "scorecard", "all", "3", "4", "spearman", "False",
          "0.047", "-0.077", "0.169"]],
    )  # fmt: skip
    write_rows(
        report / "sensitivity.csv",
        [
            "formula",
            "parameter",
            "change",
            "flips",
            "repositories",
            "rate",
            "by_ecosystem",
        ],
        [["v2-candidate (AHP)", "weight:staleness", "+20%", "1", "4", "0.047", "{}"]],
    )
    return tmp_path


def small_panel():
    return panel(
        repository("n/a", "npm", [CRITICAL, CLEAN]),
        repository("n/b", "npm", [CLEAN]),
        repository("p/a", "pypi", [CRITICAL, DEPRECATED, CLEAN]),
        repository("p/b", "pypi", [CLEAN, CLEAN]),
    )


def test_the_supplement_writes_every_file_and_names_its_verdicts(export, tmp_path):
    inputs = supplement.read_inputs(export, small_panel())
    assert inputs.scorecards == {"n/a": 4.1, "p/a": 6.0, "p/b": 2.0}
    assert [a.ecosystem for a in inputs.anchors] == ["pypi"]

    result = supplement.run(
        inputs, {"v1": load_weights("v1"), "v2": load_weights("v2")}, iterations=50
    )
    written = supplement.write(result, tmp_path / "out")

    assert [path.name for path in written] == list(supplement.FILES)
    text = (tmp_path / "out" / "supplement.md").read_text(encoding="utf-8")
    assert "RQ5: the PyPI trust gate" in text and "### `v1`" in text
    hypotheses = {(h.hypothesis[:2], h.version): h for h in result.hypotheses}
    assert hypotheses[("H2", "v2")].supported is False  # 0.047 is outside [0.3, 0.6]
    assert hypotheses[("H2", "v1")].supported is None  # not in this correlation.csv
    assert hypotheses[("H3", "v2")].observed == "max 4.7%"
    assert hypotheses[("H4", "v1")].supported and hypotheses[("H4", "v2")].supported
    assert result.sweep_v1 and result.sweep_v1[0].vector == "v1"


def test_the_supplement_is_deterministic(export, tmp_path):
    inputs = supplement.read_inputs(export, small_panel())
    weights = {"v1": load_weights("v1"), "v2": load_weights("v2")}

    for name in ("one", "two"):
        supplement.write(supplement.run(inputs, weights, iterations=50), tmp_path / name)

    for file in supplement.FILES:
        assert (tmp_path / "one" / file).read_bytes() == (
            tmp_path / "two" / file
        ).read_bytes()


def test_a_committed_copy_is_compared_only_against_its_own_inputs(export, tmp_path):
    files = [
        {"path": name, "sha256": f"{index:064x}", "source": "x", "bytes": 1}
        for index, name in enumerate(supplement.INPUT_FILES)
    ]
    (export / "MANIFEST.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    digests = supplement.input_digests(export)
    inputs = supplement.read_inputs(export, small_panel())
    result = supplement.run(
        inputs, {"v2": load_weights("v2")}, iterations=20, inputs_digest=digests
    )
    supplement.write(result, tmp_path / "committed")

    assert supplement.same_inputs(export, tmp_path / "committed")
    files[0]["sha256"] = "f" * 64
    (export / "MANIFEST.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    assert not supplement.same_inputs(export, tmp_path / "committed")
    assert not supplement.same_inputs(export, tmp_path / "nothing-here")


def test_a_scorecard_for_a_repository_outside_the_panel_is_refused(export):
    with pytest.raises(supplement.SupplementError, match="not in the panel"):
        supplement.read_inputs(export, panel(repository("n/a", "npm", [CLEAN])))
