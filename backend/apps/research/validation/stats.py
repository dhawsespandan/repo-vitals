"""The statistics S1 reports, written out in plain Python.

Not SciPy, for two reasons that are both about trust rather than taste. A
viva examiner can read every formula here against a textbook in a few minutes,
which is not true of a compiled library's internals. And the research machine
has to run this without a new binary dependency: matplotlib's freshly
installed DLL was blocked by an Application Control policy on the development
machine within the hour (§11.22), and a validation harness that cannot import
its statistics package produces no report at all.

The sizes involved make that affordable. The corpus is about a thousand
repositories; a Spearman correlation over a thousand pairs is a sort, and two
thousand bootstrap resamples of it take seconds.

Conventions, fixed here so every caller agrees: ties get the average of the
ranks they span (the "fractional ranking" every Spearman definition assumes);
a weighted statistic treats each weight as a frequency, so integer weights
give exactly the answer of the replicated data; and any statistic that is
undefined on its input (a constant series has no correlation) returns None
rather than 0, because a zero would be a finding and None is the absence of
one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def cosine(first: Sequence[float], second: Sequence[float]) -> float | None:
    """Cosine similarity of two vectors; None if either is all zeros."""
    if len(first) != len(second):
        raise ValueError("cosine needs vectors of equal length")
    dot = sum(a * b for a, b in zip(first, second, strict=True))
    norm = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    if norm == 0:
        return None
    return dot / norm


def ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks, ties sharing the average of the positions they occupy."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2 + 1
        for index in order[position : end + 1]:
            result[index] = average
        position = end + 1
    return result


def _weights(n: int, weights: Sequence[float] | None) -> list[float]:
    if weights is None:
        return [1.0] * n
    if len(weights) != n:
        raise ValueError("one weight per observation")
    if any(weight < 0 for weight in weights):
        raise ValueError("weights must be non-negative")
    return [float(weight) for weight in weights]


def pearson(
    x: Sequence[float], y: Sequence[float], weights: Sequence[float] | None = None
) -> float | None:
    """Pearson's r, optionally with frequency weights. None if either is constant."""
    if len(x) != len(y):
        raise ValueError("pearson needs paired observations")
    if len(x) < 2:
        return None
    w = _weights(len(x), weights)
    total = sum(w)
    if total <= 0:
        return None
    mean_x = sum(wi * xi for wi, xi in zip(w, x, strict=True)) / total
    mean_y = sum(wi * yi for wi, yi in zip(w, y, strict=True)) / total
    sxy = sum(
        wi * (xi - mean_x) * (yi - mean_y) for wi, xi, yi in zip(w, x, y, strict=True)
    )
    sxx = sum(wi * (xi - mean_x) ** 2 for wi, xi in zip(w, x, strict=True))
    syy = sum(wi * (yi - mean_y) ** 2 for wi, yi in zip(w, y, strict=True))
    if sxx <= 0 or syy <= 0:
        return None
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def spearman(
    x: Sequence[float], y: Sequence[float], weights: Sequence[float] | None = None
) -> float | None:
    """Spearman's rho: Pearson's r over the ranks, ties averaged.

    With weights, the ranks are still the observations' own and the weights
    enter the Pearson step — the conventional "weighted Spearman" for survey
    data, and the one whose integer-weight case equals replicating the rows'
    *ranks*. It is reported beside the unweighted value, never instead of it.
    """
    if len(x) != len(y):
        raise ValueError("spearman needs paired observations")
    return pearson(ranks(x), ranks(y), weights)


def percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Linear-interpolation percentile of an already-sorted sequence."""
    if not sorted_values:
        raise ValueError("percentile of nothing")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = fraction * (len(sorted_values) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(sorted_values[low])
    share = position - low
    return float(sorted_values[low]) * (1 - share) + float(sorted_values[high]) * share
