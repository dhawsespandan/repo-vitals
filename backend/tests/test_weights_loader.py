"""The weights registry — §5.4's validation rules, and the files we ship.

A weights file changes every number this product reports and is edited by
hand. The failure mode of a lenient loader is therefore not a crash but a
plausible wrong answer published with full confidence, so each rejection rule
gets a test that proves the bad file is actually refused.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from apps.scoring.normalize import COUNT, DEPRECATION, SEVERITY, STALENESS
from apps.scoring.weights import (
    REQUIRED_ECOSYSTEMS,
    WeightsError,
    available_versions,
    load_weights,
    parse_weights,
    weights_dir,
)

VALID = {
    "version": "test",
    "derivation": "unit-test",
    "normalization": {"cve_count_cap": 10, "staleness_cap_days": 1095},
    "flag_rule": {"stale_flag_days": 730},
    "thresholds": {"safe_min": 80, "medium_min": 50},
    "rollup": {"decay": 0.5, "max_terms": 20},
    "weights": {
        "npm": {"deprecation": 0.25, "severity": 0.25, "count": 0.25, "staleness": 0.25},
        "pypi": {
            "deprecation": 0.25,
            "severity": 0.25,
            "count": 0.25,
            "staleness": 0.25,
        },
    },
    "epss": {"enabled": False, "weight": 0.0},
}

FAKE_PATH = Path("weights_test.yaml")


def parse(**overrides):
    document = copy.deepcopy(VALID)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(document.get(key), dict):
            document[key] = {**document[key], **value}
        else:
            document[key] = value
    return parse_weights(document, FAKE_PATH, document["version"])


class TestShippedFiles:
    """Both registered versions must load — they are what production runs."""

    def test_every_file_in_the_registry_loads(self):
        versions = available_versions()
        assert set(versions) >= {"v0_equal", "v1"}
        for version in versions:
            assert load_weights(version).version == version

    def test_wp1_vectors_are_the_delivered_numbers(self):
        v1 = load_weights("v1")
        assert v1.derivation == "informal-pairwise"
        assert v1.for_ecosystem("npm") == {
            DEPRECATION: Decimal("0.46"),
            SEVERITY: Decimal("0.28"),
            COUNT: Decimal("0.16"),
            STALENESS: Decimal("0.10"),
        }
        assert v1.for_ecosystem("pypi") == {
            DEPRECATION: Decimal("0.32"),
            SEVERITY: Decimal("0.35"),
            COUNT: Decimal("0.16"),
            STALENESS: Decimal("0.17"),
        }

    def test_the_shipped_file_matches_the_wp1_deliverable_exactly(self):
        """The registry copy must not drift from the teammate's artifact.

        `weights/weights_v1.yaml` is a copy of `wp/wp-1/wp1_tier1_weights.yaml`
        with a provenance header prepended. If someone edits one of the two
        numbers in place, the paper and the product stop agreeing — and it is
        the paper's numbers that get published.
        """
        delivered = yaml.safe_load(
            (
                Path(__file__).resolve().parents[2] / "wp/wp-1/wp1_tier1_weights.yaml"
            ).read_text(encoding="utf-8")
        )
        shipped = yaml.safe_load(
            (weights_dir() / "weights_v1.yaml").read_text(encoding="utf-8")
        )
        assert shipped == delivered

    def test_v0_equal_is_the_naive_baseline(self):
        v0 = load_weights("v0_equal")
        for ecosystem in REQUIRED_ECOSYSTEMS:
            assert set(v0.for_ecosystem(ecosystem).values()) == {Decimal("0.25")}

    def test_the_active_version_is_the_one_settings_names(self, settings):
        settings.WEIGHTS_VERSION = "v0_equal"
        from apps.scoring.weights import active_weights

        assert active_weights().version == "v0_equal"


class TestValidation:
    def test_a_valid_document_parses(self):
        weights = parse()
        assert weights.rollup.decay == Decimal("0.5")
        assert weights.thresholds.safe_min == Decimal("80")
        assert weights.stale_flag_days == 730

    def test_weights_that_do_not_sum_to_one_are_refused(self):
        with pytest.raises(WeightsError, match="sum to"):
            parse(
                weights={
                    "npm": {
                        "deprecation": 0.5,
                        "severity": 0.25,
                        "count": 0.25,
                        "staleness": 0.25,
                    },
                    "pypi": VALID["weights"]["pypi"],
                }
            )

    def test_a_vector_within_the_tolerance_is_accepted(self):
        # WP-1's npm vector truncates 0.4673 to 0.46, so the sum is not exactly
        # 1 in general; §5.4's +-0.001 is what makes the delivered file loadable.
        weights = parse(
            weights={
                "npm": {
                    "deprecation": 0.2505,
                    "severity": 0.25,
                    "count": 0.25,
                    "staleness": 0.2490,
                },
                "pypi": VALID["weights"]["pypi"],
            }
        )
        assert weights.for_ecosystem("npm")[DEPRECATION] == Decimal("0.2505")

    def test_a_missing_signal_is_refused(self):
        with pytest.raises(WeightsError, match="missing staleness"):
            parse(
                weights={
                    "npm": {"deprecation": 0.4, "severity": 0.4, "count": 0.2},
                    "pypi": VALID["weights"]["pypi"],
                }
            )

    def test_an_unknown_signal_is_refused(self):
        with pytest.raises(WeightsError, match="unknown signal"):
            parse(
                weights={
                    "npm": {**VALID["weights"]["npm"], "popularity": 0.0},
                    "pypi": VALID["weights"]["pypi"],
                }
            )

    def test_a_missing_ecosystem_is_refused(self):
        document = copy.deepcopy(VALID)
        document["weights"] = {"npm": VALID["weights"]["npm"]}
        with pytest.raises(WeightsError, match="no weight vector for 'pypi'"):
            parse_weights(document, FAKE_PATH, "test")

    def test_a_negative_weight_is_refused(self):
        with pytest.raises(WeightsError, match="negative weight"):
            parse(
                weights={
                    "npm": {
                        "deprecation": -0.1,
                        "severity": 0.5,
                        "count": 0.3,
                        "staleness": 0.3,
                    },
                    "pypi": VALID["weights"]["pypi"],
                }
            )

    @pytest.mark.parametrize(
        "thresholds",
        [
            {"safe_min": 50, "medium_min": 80},  # inverted
            {"safe_min": 80, "medium_min": 80},  # not strictly ordered
            {"safe_min": 120, "medium_min": 50},  # outside 0-100
            {"safe_min": 80, "medium_min": -1},
        ],
    )
    def test_unordered_thresholds_are_refused(self, thresholds):
        with pytest.raises(WeightsError, match="thresholds"):
            parse(thresholds=thresholds)

    @pytest.mark.parametrize("cap", [0, -5, 2.5, "ten", None])
    def test_non_positive_caps_are_refused(self, cap):
        with pytest.raises(WeightsError, match="cve_count_cap"):
            parse(normalization={"cve_count_cap": cap})

    @pytest.mark.parametrize("decay", [0, -0.5, 1.5])
    def test_decay_outside_zero_to_one_is_refused(self, decay):
        with pytest.raises(WeightsError, match="decay"):
            parse(rollup={"decay": decay})

    def test_decay_of_exactly_one_is_allowed(self):
        # A legitimate sensitivity-sweep setting (WP-6): no decay at all, every
        # occurrence undiminished.
        assert parse(rollup={"decay": 1}).rollup.decay == Decimal("1")

    def test_zero_max_terms_is_refused(self):
        with pytest.raises(WeightsError, match="max_terms"):
            parse(rollup={"max_terms": 0})

    def test_a_version_tag_that_disagrees_with_the_filename_is_refused(self):
        document = copy.deepcopy(VALID)
        with pytest.raises(WeightsError, match="must agree"):
            parse_weights(document, FAKE_PATH, "v9")

    def test_a_missing_derivation_is_refused(self):
        with pytest.raises(WeightsError, match="derivation"):
            parse(derivation="")

    @pytest.mark.parametrize(
        "section", ["normalization", "flag_rule", "thresholds", "rollup", "epss"]
    )
    def test_a_missing_section_is_refused(self, section):
        document = copy.deepcopy(VALID)
        del document[section]
        with pytest.raises(WeightsError, match=section):
            parse_weights(document, FAKE_PATH, "test")


class TestEpss:
    """The optional fifth term (D3), and the bound it must not break."""

    def test_a_weight_set_while_disabled_is_refused(self):
        with pytest.raises(WeightsError, match="not applied"):
            parse(epss={"enabled": False, "weight": 0.1})

    def test_an_enabled_epss_weight_counts_toward_the_sum(self):
        # Funding a fifth term from outside the vector would push the maximum
        # penalty past 100 and break the 0-100 bound the product states.
        with pytest.raises(WeightsError, match="EPSS is enabled"):
            parse(epss={"enabled": True, "weight": 0.1})

    def test_an_enabled_epss_term_inside_the_budget_is_accepted(self):
        weights = parse(
            epss={"enabled": True, "weight": 0.2},
            weights={
                "npm": {
                    "deprecation": 0.4,
                    "severity": 0.2,
                    "count": 0.1,
                    "staleness": 0.1,
                },
                "pypi": {
                    "deprecation": 0.2,
                    "severity": 0.3,
                    "count": 0.2,
                    "staleness": 0.1,
                },
            },
        )
        assert weights.epss_enabled
        assert "epss" in weights.for_ecosystem("npm")
        assert weights.signal_order[-1] == "epss"


class TestLoading:
    def test_an_unknown_version_names_what_is_available(self):
        with pytest.raises(WeightsError, match="Available: "):
            load_weights("v99")

    @pytest.mark.parametrize("version", ["../secrets", "a/b", "", ".hidden"])
    def test_a_version_cannot_name_a_path(self, version):
        # It arrives from an environment variable and from `rescore`'s command
        # line; neither should be able to point the loader outside weights/.
        with pytest.raises(WeightsError):
            load_weights(version)

    def test_an_unknown_ecosystem_raises_rather_than_defaulting(self):
        with pytest.raises(WeightsError, match="no weight vector for ecosystem"):
            load_weights("v1").for_ecosystem("cargo")
