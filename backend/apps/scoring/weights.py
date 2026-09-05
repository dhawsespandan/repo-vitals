"""The versioned weights registry — §5.4, and the mechanism D5 rests on.

D5's promise is that swapping `v1` for `v2` requires zero code change. That is
only true if nothing outside this module ever hard-codes a weight, a cap, a
threshold or the decay — so every one of those lives in
`backend/weights/weights_<version>.yaml`, `WEIGHTS_VERSION` selects the file,
and the rest of the codebase asks this module.

**Validation is strict and happens at load.** A weights file is configuration
that silently changes every number the product reports; the failure mode of a
lenient loader is not a crash but a plausible wrong answer, published with the
same confidence as a right one. So: per-ecosystem weights must sum to 1 within
±0.001, caps must be positive, thresholds must be ordered inside 0-100, decay
must sit in (0, 1] and `max_terms` at 1 or more, and every one of the four
Tier-1 signals (D3) must be named explicitly. A file that fails any of these
raises `ImproperlyConfigured` at first use rather than scoring anything.

**The version tag is read from inside the file, not from the env var.** They
are normally the same string, and `load_weights` insists on it — but the tag
written into `scan_runs.scoring_formula_version` and `scan_history` has to be
the one the file states about itself, because that is the string a research
run will later hand back to `rescore` to reproduce the number.

Files are read once per process and cached: they are immutable artifacts on
disk, checked into git, and a scan should not pay a file read per occurrence.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .normalize import EPSS, SIGNAL_NAMES

#: Every ecosystem that must carry a vector (D1: both are in scope from the
#: start, even though the PyPI adapter itself lands in Phase 6). A weights file
#: missing the `pypi` block would score Phase 6's first Python repository under
#: npm's vector without saying so.
REQUIRED_ECOSYSTEMS: tuple[str, ...] = ("npm", "pypi")

#: How far a per-ecosystem vector may drift from 1 and still be accepted.
#: §5.4's tolerance: WP-1's own npm vector is truncated to two decimals, so an
#: exact-equality check would reject the delivered file.
SUM_TOLERANCE = Decimal("0.001")


class WeightsError(ImproperlyConfigured):
    """A weights file that cannot be trusted to score anything."""


@dataclass(frozen=True)
class Normalization:
    cve_count_cap: int
    staleness_cap_days: int


@dataclass(frozen=True)
class Thresholds:
    safe_min: Decimal
    medium_min: Decimal


@dataclass(frozen=True)
class Rollup:
    decay: Decimal
    max_terms: int


@dataclass(frozen=True)
class WeightSet:
    """One immutable weights version, validated."""

    version: str
    derivation: str
    normalization: Normalization
    stale_flag_days: int
    thresholds: Thresholds
    rollup: Rollup
    weights: dict[str, dict[str, Decimal]]
    epss_enabled: bool
    epss_weight: Decimal
    #: Where it was read from, so an error message can name the file.
    path: Path

    @property
    def signal_order(self) -> tuple[str, ...]:
        """The canonical order every breakdown is rendered in.

        Fixed by D3 rather than taken from the YAML's key order: two
        repositories' breakdown panels have to list their signals in the same
        sequence to be comparable at a glance, and a reordered key in a future
        weights file must not silently reorder the UI.
        """
        return (*SIGNAL_NAMES, EPSS) if self.epss_enabled else SIGNAL_NAMES

    def for_ecosystem(self, ecosystem: str) -> dict[str, Decimal]:
        """This file's vector for one ecosystem, EPSS appended when enabled.

        An unknown ecosystem raises rather than falling back to npm's vector:
        scoring a PyPI occurrence under npm's weights would be wrong in a way
        no output could reveal.
        """
        vector = self.weights.get(ecosystem)
        if vector is None:
            raise WeightsError(
                f"{self.path.name} has no weight vector for ecosystem "
                f"'{ecosystem}'; it defines {sorted(self.weights)}."
            )
        if self.epss_enabled:
            return {**vector, EPSS: self.epss_weight}
        return dict(vector)


# ── reading and validating ─────────────────────────────────────────────────


def weights_dir() -> Path:
    return Path(settings.BASE_DIR) / "weights"


def _decimal(value, field: str, path: Path) -> Decimal:
    # str() first: `Decimal(0.46)` from a YAML float carries the binary
    # expansion (0.4599999...) into every score it touches.
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise WeightsError(f"{path.name}: {field} is not a number ({value!r}).") from exc


def _positive_int(value, field: str, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WeightsError(f"{path.name}: {field} must be a positive integer.")
    return value


def _section(document: dict, key: str, path: Path) -> dict:
    section = document.get(key)
    if not isinstance(section, dict):
        raise WeightsError(f"{path.name}: missing or malformed '{key}' section.")
    return section


def parse_weights(document: dict, path: Path, expected_version: str) -> WeightSet:
    """Turn a parsed YAML document into a validated `WeightSet`."""
    if not isinstance(document, dict):
        raise WeightsError(f"{path.name}: expected a YAML mapping at the top level.")

    version = str(document.get("version") or "").strip()
    if not version:
        raise WeightsError(f"{path.name}: no 'version' tag.")
    if version != expected_version:
        raise WeightsError(
            f"{path.name}: declares version '{version}' but was loaded as "
            f"'{expected_version}'. The tag written into every score row and "
            f"the file it came from must agree."
        )

    derivation = str(document.get("derivation") or "").strip()
    if not derivation:
        raise WeightsError(f"{path.name}: no 'derivation' tag.")

    norm_section = _section(document, "normalization", path)
    normalization = Normalization(
        cve_count_cap=_positive_int(
            norm_section.get("cve_count_cap"), "normalization.cve_count_cap", path
        ),
        staleness_cap_days=_positive_int(
            norm_section.get("staleness_cap_days"),
            "normalization.staleness_cap_days",
            path,
        ),
    )

    flag_section = _section(document, "flag_rule", path)
    stale_flag_days = _positive_int(
        flag_section.get("stale_flag_days"), "flag_rule.stale_flag_days", path
    )

    threshold_section = _section(document, "thresholds", path)
    thresholds = Thresholds(
        safe_min=_decimal(threshold_section.get("safe_min"), "thresholds.safe_min", path),
        medium_min=_decimal(
            threshold_section.get("medium_min"), "thresholds.medium_min", path
        ),
    )
    if not (0 <= thresholds.medium_min < thresholds.safe_min <= 100):
        raise WeightsError(
            f"{path.name}: thresholds must satisfy "
            f"0 ≤ medium_min < safe_min ≤ 100; got "
            f"medium_min={thresholds.medium_min}, safe_min={thresholds.safe_min}."
        )

    rollup_section = _section(document, "rollup", path)
    decay = _decimal(rollup_section.get("decay"), "rollup.decay", path)
    if not (Decimal(0) < decay <= Decimal(1)):
        # decay ≤ 0 makes the roll-up "worst occurrence only" and throws away
        # breadth; decay > 1 makes it diverge, so the twentieth-worst
        # dependency would outweigh the worst.
        raise WeightsError(f"{path.name}: rollup.decay must be in (0, 1]; got {decay}.")
    rollup = Rollup(
        decay=decay,
        max_terms=_positive_int(
            rollup_section.get("max_terms"), "rollup.max_terms", path
        ),
    )

    epss_section = document.get("epss")
    if not isinstance(epss_section, dict):
        raise WeightsError(f"{path.name}: missing or malformed 'epss' section.")
    epss_enabled = bool(epss_section.get("enabled", False))
    epss_weight = _decimal(epss_section.get("weight", 0), "epss.weight", path)
    if not epss_enabled and epss_weight != Decimal(0):
        raise WeightsError(
            f"{path.name}: epss.weight is {epss_weight} but epss.enabled is false. "
            f"A weight that is not applied is a claim the formula does not make."
        )
    if epss_weight < Decimal(0):
        raise WeightsError(f"{path.name}: epss.weight must not be negative.")

    weight_section = _section(document, "weights", path)
    vectors: dict[str, dict[str, Decimal]] = {}
    for ecosystem in REQUIRED_ECOSYSTEMS:
        raw = weight_section.get(ecosystem)
        if not isinstance(raw, dict):
            raise WeightsError(f"{path.name}: no weight vector for '{ecosystem}'.")

        missing = [name for name in SIGNAL_NAMES if name not in raw]
        if missing:
            raise WeightsError(
                f"{path.name}: {ecosystem} vector is missing {', '.join(missing)}. "
                f"D3 fixes the Tier-1 signal set at four; an omitted signal is "
                f"a silent zero."
            )
        unknown = [name for name in raw if name not in SIGNAL_NAMES]
        if unknown:
            raise WeightsError(
                f"{path.name}: {ecosystem} vector names unknown signal(s) "
                f"{', '.join(sorted(unknown))}. EPSS belongs in the 'epss' "
                f"section, not in a per-ecosystem vector."
            )

        vector = {
            name: _decimal(raw[name], f"weights.{ecosystem}.{name}", path)
            for name in SIGNAL_NAMES
        }
        negative = sorted(name for name, weight in vector.items() if weight < 0)
        if negative:
            raise WeightsError(
                f"{path.name}: {ecosystem} vector has negative weight(s) "
                f"{', '.join(negative)}."
            )

        # §5.4's Σw = 1, with EPSS inside the budget rather than bolted on top:
        # a fifth term funded from outside the vector would push the maximum
        # penalty past 100 and break the 0-100 bound the whole product states.
        total = sum(vector.values(), Decimal(0)) + (
            epss_weight if epss_enabled else Decimal(0)
        )
        if abs(total - Decimal(1)) > SUM_TOLERANCE:
            raise WeightsError(
                f"{path.name}: {ecosystem} weights sum to {total}, not 1 "
                f"(±{SUM_TOLERANCE})."
                + (
                    " EPSS is enabled, so its weight counts toward the sum."
                    if epss_enabled
                    else ""
                )
            )
        vectors[ecosystem] = vector

    return WeightSet(
        version=version,
        derivation=derivation,
        normalization=normalization,
        stale_flag_days=stale_flag_days,
        thresholds=thresholds,
        rollup=rollup,
        weights=vectors,
        epss_enabled=epss_enabled,
        epss_weight=epss_weight,
        path=path,
    )


@functools.lru_cache(maxsize=8)
def load_weights(version: str) -> WeightSet:
    """`weights/weights_<version>.yaml`, parsed, validated and cached."""
    if not version or "/" in version or "\\" in version or version.startswith("."):
        # The version reaches this from an environment variable and, in
        # `rescore`, from a command line. Neither should be able to name a path.
        raise WeightsError(f"'{version}' is not a valid weights version name.")

    path = weights_dir() / f"weights_{version}.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        available = sorted(
            entry.stem.removeprefix("weights_")
            for entry in weights_dir().glob("weights_*.yaml")
        )
        raise WeightsError(
            f"No weights file for version '{version}' ({path}). "
            f"Available: {', '.join(available) or 'none'}."
        ) from exc
    except OSError as exc:
        raise WeightsError(f"Could not read {path}: {exc}") from exc

    try:
        # safe_load, never load: a weights file is data, and the loader must
        # not be able to construct Python objects out of it.
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WeightsError(f"{path.name} is not valid YAML: {exc}") from exc

    return parse_weights(document, path, version)


def active_weights() -> WeightSet:
    """The version `WEIGHTS_VERSION` selects (§6)."""
    return load_weights(settings.WEIGHTS_VERSION)


def available_versions() -> list[str]:
    return sorted(
        entry.stem.removeprefix("weights_")
        for entry in weights_dir().glob("weights_*.yaml")
    )
