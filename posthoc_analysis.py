"""Post-hoc comparisons matched to a completed independent-group omnibus test.

- Ordinary ANOVA: Tukey / Tukey-Kramer, familywise-adjusted p-values.
- Welch ANOVA: Games–Howell, familywise-adjusted p-values.
- Kruskal–Wallis: Dunn z tests, tie correction, Holm adjustment.

No comparisons are claimed causal. All methods reuse the same complete cases.
"""

from dataclasses import dataclass
from itertools import combinations
import math

import numpy as np
from scipy import stats


@dataclass
class PairwiseComparison:
    first: str
    second: str
    estimate: float
    statistic: float | None
    p_adjusted: float
    p_raw: float | None
    ci_low: float | None
    ci_high: float | None


@dataclass
class PosthocResult:
    method: str
    omnibus_method: str
    pairs: list[PairwiseComparison]
    warnings: list[str]


def holm_adjust(pvalues: list[float]) -> list[float]:
    """Step-down Holm adjustment, controlling familywise error probability."""
    if any(not math.isfinite(p) or p < 0 or p > 1 for p in pvalues):
        raise ValueError("p-values must be finite and within [0, 1].")
    m = len(pvalues)
    order = np.argsort(pvalues)
    adjusted = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[int(idx)]))
        adjusted[idx] = running
    return adjusted.tolist()


def dunn_pairs(samples, labels) -> list[PairwiseComparison]:
    """Dunn z tests between all pairs of groups, from the ranks of ALL groups,
    with the global tie correction and Holm-adjusted p-values (Dunn, 1964)."""
    all_values = np.concatenate(samples)
    n_total = len(all_values)
    ranks = stats.rankdata(all_values, method="average")
    _, counts = np.unique(all_values, return_counts=True)
    tie_sum = np.sum(counts.astype(float) ** 3 - counts)
    base_variance = (
        n_total * (n_total + 1) / 12
        - tie_sum / (12 * (n_total - 1))
    )
    if base_variance <= 0:
        raise ValueError("No rank variation for Dunn comparisons.")

    rank_means = []
    start = 0
    for values in samples:
        end = start + len(values)
        rank_means.append(float(np.mean(ranks[start:end])))
        start = end

    raw_p = []
    unfinished = []
    for i, j in combinations(range(len(labels)), 2):
        difference = rank_means[i] - rank_means[j]
        standard_error = math.sqrt(
            base_variance * (1 / len(samples[i]) + 1 / len(samples[j]))
        )
        z = difference / standard_error
        p = float(2 * stats.norm.sf(abs(z)))
        raw_p.append(p)
        unfinished.append((i, j, difference, z, p))

    adjusted = holm_adjust(raw_p)
    return [PairwiseComparison(first=labels[i], second=labels[j], estimate=difference,
                               statistic=z, p_adjusted=p_adj, p_raw=p,
                               ci_low=None, ci_high=None)
            for (i, j, difference, z, p), p_adj in zip(unfinished, adjusted)]


def analyze_posthoc(omnibus) -> PosthocResult:
    """Pairwise tests for an already-computed independent-group result."""
    method_map = {
        "anova": "Tukey HSD / Tukey–Kramer",
        "welch": "Games–Howell",
        "kruskal": "Dunn–Holm",
    }
    if omnibus.method not in method_map:
        raise ValueError("Unsupported omnibus method for post-hoc comparisons.")
    labels = omnibus.labels
    samples = omnibus.samples
    if not 3 <= len(labels) <= 8 or len(samples) != len(labels):
        raise ValueError("Post-hoc requires 3 to 8 valid groups.")
    if any(len(v) < 5 for v in samples):
        raise ValueError("Each group must contain at least five values.")

    pairs = []
    if omnibus.method in ("anova", "welch"):
        # SciPy returns multiplicity-adjusted p-values for the complete family
        # of all pairwise comparisons and simultaneous 95% confidence intervals.
        result = stats.tukey_hsd(
            *samples, equal_var=(omnibus.method == "anova")
        )
        ci = result.confidence_interval(confidence_level=0.95)
        for i, j in combinations(range(len(labels)), 2):
            difference = float(result.statistic[i, j])
            p = float(result.pvalue[i, j])
            low = float(ci.low[i, j])
            high = float(ci.high[i, j])
            if not all(math.isfinite(z) for z in (difference, p, low, high)):
                raise ValueError("Pairwise estimates are not finite.")
            pairs.append(PairwiseComparison(
                first=labels[i], second=labels[j], estimate=difference,
                statistic=None, p_adjusted=p, p_raw=None,
                ci_low=low, ci_high=high,
            ))
        warnings = [
            "Pairwise values are differences in group means (first minus second).",
            "The reported p-values control familywise error across all group pairs.",
            "Intervals are simultaneous 95% confidence intervals, not unadjusted intervals.",
            "Normality/independence/outliers and variance assumptions require review.",
        ]
    else:
        pairs = dunn_pairs(samples, labels)
        warnings = [
            "Dunn compares mean ranks based on ALL groups (first minus second).",
            "The z statistic uses the global tie correction and a normal approximation.",
            "Holm-adjusted p-values control familywise error for these comparisons.",
            "Confidence intervals are not implemented for Dunn comparisons.",
            "Rank differences do not automatically establish median differences.",
        ]

    if omnibus.p_value >= 0.05:
        warnings.append(
            "The omnibus test was not significant at .05; interpret these "
            "pairwise comparisons as exploratory, not as confirmed differences."
        )
    warnings.append(
        "Group membership, independent observations and scientific relevance "
        "must be verified; comparisons do not prove causality."
    )
    return PosthocResult(
        method=method_map[omnibus.method],
        omnibus_method=omnibus.method,
        pairs=pairs,
        warnings=warnings,
    )
