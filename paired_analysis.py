"""Paired before/after comparisons: paired t and Wilcoxon signed-rank."""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


@dataclass
class PairedResult:
    before_name: str
    after_name: str
    method: str
    n_total: int
    n_complete: int
    n_unchanged: int
    before_mean: float
    after_mean: float
    before_sd: float
    after_sd: float
    before_median: float
    after_median: float
    mean_change: float
    median_change: float
    statistic: float
    df: float | None
    p_value: float
    effect_name: str
    effect_size: float
    ci_low: float | None
    ci_high: float | None
    p_method: str
    warnings: list[str]
    before_values: np.ndarray
    after_values: np.ndarray


def recommend_paired_test(outcome_scale: str, paired: bool) -> str:
    if not paired:
        return (
            "Confirm that each row contains two observations from the SAME "
            "participant. Independent groups require another analysis."
        )
    if outcome_scale == "ordinal":
        return (
            "Wilcoxon signed-rank is a candidate for ordinal paired responses. "
            "Review whether the distribution of nonzero differences is roughly symmetric."
        )
    if outcome_scale == "scale":
        return (
            "A paired t-test compares the mean within-participant change "
            "for a quantitative measure when the difference scores are suitable. "
            "Wilcoxon answers a different signed-rank question."
        )
    return "Confirm the outcome scale before choosing a test."


def analyze_paired(
    df: pd.DataFrame,
    before_name: str,
    after_name: str,
    method: str,
    scale: str,
    pairing_confirmed: bool = False,
    assumptions_confirmed: bool = False,
) -> PairedResult:
    """Analyze complete pairs. Change is AFTER minus BEFORE."""
    if before_name == after_name:
        raise ValueError("Choose different before and after columns.")
    for name in (before_name, after_name):
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers are not measurements.")
    if not pairing_confirmed:
        raise ValueError("Confirm that each row represents the same participant.")
    if scale not in {"ordinal", "scale"}:
        raise ValueError("Confirm an ordinal or quantitative measurement scale.")
    if method not in {"paired_t", "wilcoxon"}:
        raise ValueError("Choose paired t-test or Wilcoxon signed-rank.")
    if method == "paired_t" and scale != "scale":
        raise ValueError("A paired t-test requires a quantitative outcome.")
    if not assumptions_confirmed:
        raise ValueError("Confirm that you reviewed difference scores and assumptions.")

    original = df[[before_name, after_name]]
    numeric = original.apply(pd.to_numeric, errors="coerce")
    if (original.notna() & numeric.isna()).any().any():
        raise ValueError("Selected columns contain non-numeric values.")
    finite = numeric.to_numpy(dtype=float)
    if np.isinf(finite).any():
        raise ValueError("Infinite values are not supported.")

    complete = numeric.dropna()
    n = len(complete)
    if n < 5:
        raise ValueError("At least five complete paired observations are required.")

    before = complete[before_name].to_numpy(dtype=float)
    after = complete[after_name].to_numpy(dtype=float)
    diff = after - before
    zeros = int(np.count_nonzero(diff == 0))
    if np.count_nonzero(diff) < 5 and method == "wilcoxon":
        raise ValueError("Wilcoxon requires at least five nonzero differences in this prototype.")

    if method == "paired_t":
        sd_diff = float(np.std(diff, ddof=1))
        if sd_diff <= 0:
            raise ValueError("Difference scores have no variation for a paired t-test.")
        test = stats.ttest_rel(after, before, alternative="two-sided")
        statistic, p_value = float(test.statistic), float(test.pvalue)
        interval = test.confidence_interval(confidence_level=0.95)
        ci_low, ci_high = float(interval.low), float(interval.high)
        df_value = float(test.df)
        effect_name = "Cohen’s dz"
        effect_size = float(np.mean(diff) / sd_diff)
        p_method = "Two-sided paired Student t-test (SciPy)"
    else:
        # SciPy's auto choice accounts for ties and zero differences.
        # Compute differences first, so roundoff does not split tied ranks.
        rounded_diff = np.round(diff, decimals=10)
        test = stats.wilcoxon(
            rounded_diff,
            zero_method="wilcox",
            alternative="two-sided",
            method="auto",
        )
        statistic, p_value = float(test.statistic), float(test.pvalue)
        nz = rounded_diff[rounded_diff != 0]
        ranks = stats.rankdata(np.abs(nz), method="average")
        positive = float(np.sum(ranks[nz > 0]))
        negative = float(np.sum(ranks[nz < 0]))
        effect_size = (positive - negative) / (positive + negative)
        effect_name = "Matched-pairs rank-biserial r"
        ci_low = ci_high = df_value = None
        p_method = "Two-sided Wilcoxon signed-rank (SciPy auto; zeros removed)"

    numeric_values = [statistic, p_value, effect_size]
    if method == "paired_t":
        numeric_values += [ci_low, ci_high, df_value]
    if not all(math.isfinite(v) for v in numeric_values):
        raise ValueError("Test failed to produce finite statistics.")

    warnings = [
        "Row alignment must represent genuine repeated measurements of the same participant.",
        "The study design and independence BETWEEN participants must be assessed.",
        "Statistical significance does not demonstrate causation or clinical importance.",
    ]
    excluded = len(df) - n
    if excluded:
        warnings.append(
            f"Complete-case analysis excluded {excluded} participants with a missing measurement."
        )
    if n < 30:
        warnings.append("Small paired sample: estimates and inferential conclusions may be unstable.")
    if method == "paired_t":
        warnings.append(
            "Paired t-test inference concerns the mean difference; review the "
            "difference distribution and influential observations."
        )
    else:
        warnings.append(
            "Wilcoxon signed-rank uses nonzero differences and tests a symmetric "
            "signed-difference null, not automatically a median-change claim."
        )
        if zeros:
            warnings.append(
                f"{zeros} unchanged pairs were excluded from Wilcoxon ranking."
            )
        warnings.append(
            "Ties/zero differences affect exact inference. SciPy selects the "
            "p-value method automatically; no confidence interval is shown."
        )

    return PairedResult(
        before_name=before_name,
        after_name=after_name,
        method=method,
        n_total=len(df),
        n_complete=n,
        n_unchanged=zeros,
        before_mean=float(np.mean(before)),
        after_mean=float(np.mean(after)),
        before_sd=float(np.std(before, ddof=1)),
        after_sd=float(np.std(after, ddof=1)),
        before_median=float(np.median(before)),
        after_median=float(np.median(after)),
        mean_change=float(np.mean(diff)),
        median_change=float(np.median(diff)),
        statistic=statistic,
        df=df_value,
        p_value=p_value,
        effect_name=effect_name,
        effect_size=effect_size,
        ci_low=ci_low,
        ci_high=ci_high,
        p_method=p_method,
        warnings=warnings,
        before_values=before,
        after_values=after,
    )
