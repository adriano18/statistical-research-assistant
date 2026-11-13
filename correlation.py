"""Pearson and Spearman correlation with explicit measurement-scale safeguards."""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


@dataclass
class CorrelationResult:
    x_name: str
    y_name: str
    method: str
    n_total: int
    n_complete: int
    coefficient: float
    p_value: float
    ci_low: float | None
    ci_high: float | None
    p_method: str
    warnings: list[str]
    x_values: np.ndarray
    y_values: np.ndarray


def recommend_method(scale_x: str, scale_y: str) -> str:
    """Explain plausible choices, never infer measurement scale from dtype."""
    valid = {"ordinal", "scale"}
    if scale_x not in valid or scale_y not in valid:
        return "Confirm ordinal or quantitative scales for both variables first."
    if scale_x == "ordinal" or scale_y == "ordinal":
        return (
            "Consider Spearman’s ρ for ordered responses and a monotonic relationship. "
            "Check the scatterplot and interpretation of coded categories."
        )
    return (
        "Pearson’s r is appropriate for an approximately linear quantitative "
        "relationship if assumptions are satisfied. Spearman’s ρ is an "
        "alternative for monotonic relationships or problematic outliers."
    )


def analyze_correlation(
    df: pd.DataFrame,
    x_name: str,
    y_name: str,
    method: str,
    scale_x: str,
    scale_y: str,
    pearson_checked: bool = False,
) -> CorrelationResult:
    """Calculate a two-sided correlation using only complete paired rows.

    Spearman's p value uses a reproducible 1999-resample permutation estimate
    for n <= 500. No unvalidated confidence interval is reported for Spearman.
    """
    if x_name == y_name:
        raise ValueError("Choose two different variables.")
    for name in (x_name, y_name):
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers cannot be correlated as research scores.")
    if scale_x not in {"ordinal", "scale"} or scale_y not in {"ordinal", "scale"}:
        raise ValueError("Confirm ordinal or quantitative measurement scales.")
    if method not in {"pearson", "spearman"}:
        raise ValueError("Choose Pearson or Spearman.")
    if method == "pearson" and (
        scale_x != "scale" or scale_y != "scale"
    ):
        raise ValueError("Pearson requires both variables to be quantitative.")
    if method == "pearson" and not pearson_checked:
        raise ValueError("Confirm the Pearson linearity/outlier assumptions first.")

    selected = df[[x_name, y_name]].copy()
    numeric = selected.apply(pd.to_numeric, errors="coerce")
    if (selected.notna() & numeric.isna()).any().any():
        raise ValueError("One or both variables contain non-numeric responses.")
    if not np.isfinite(numeric.to_numpy(dtype=float)[~numeric.isna().to_numpy()]).all():
        raise ValueError("Infinite values are not supported.")

    complete = numeric.dropna()
    n = len(complete)
    if n < 5:
        raise ValueError("At least five complete pairs are required for this prototype.")

    x = complete[x_name].to_numpy(dtype=float)
    y = complete[y_name].to_numpy(dtype=float)
    if np.unique(x).size < 2 or np.unique(y).size < 2:
        raise ValueError("Both variables must have variation.")

    ci_low = ci_high = None
    if method == "pearson":
        result = stats.pearsonr(x, y, alternative="two-sided")
        coeff, p_value = float(result.statistic), float(result.pvalue)
        ci = result.confidence_interval(confidence_level=0.95)
        if math.isfinite(float(ci.low)) and math.isfinite(float(ci.high)):
            ci_low, ci_high = float(ci.low), float(ci.high)
        p_method = "Two-sided Pearson test (SciPy)"
    else:
        result = stats.spearmanr(x, y)
        coeff = float(result.statistic)

        if n <= 500:
            # Use an approximate permutation p instead of the asymptotic
            # Spearman p for small/moderate samples. Fix the random seed.
            perm = stats.permutation_test(
                (x,),
                lambda shuffled: stats.spearmanr(shuffled, y).statistic,
                permutation_type="pairings",
                alternative="two-sided",
                n_resamples=1999,
                rng=np.random.default_rng(2026),
            )
            p_value = float(perm.pvalue)
            p_method = "Two-sided permutation estimate (1,999 resamples, fixed seed)"
        else:
            p_value = float(result.pvalue)
            p_method = "Two-sided asymptotic Spearman test (SciPy)"

    if not all(math.isfinite(v) for v in (coeff, p_value)):
        raise ValueError("Could not calculate a finite correlation and p-value.")

    warnings = [
        "Correlation does not demonstrate causation.",
        "Check the scatterplot, study design, outliers and independence of observations.",
        "The chosen measurement scales must be verified by the researcher.",
    ]
    if len(df) > n:
        warnings.append(
            f"Pairwise-complete analysis excluded {len(df) - n} records "
            "with missing values in either selected variable."
        )
    if n < 30:
        warnings.append("Small sample: correlation estimates and significance may be unstable.")
    if method == "pearson":
        warnings.append(
            "Pearson inference assumes an appropriate study design and "
            "approximately linear association; check influential outliers."
        )
        if ci_low is None:
            warnings.append("Pearson 95% CI could not be estimated.")
    else:
        warnings.append(
            "Spearman’s ρ describes monotonic association; its 95% CI is "
            "not implemented in this version."
        )
        if n <= 500:
            warnings.append(
                "The permutation p-value is a Monte Carlo estimate with "
                "1,999 resamples; it can vary slightly with the chosen seed."
            )
            # Stage 37 (review S10): the Monte Carlo floor is made visible.
            if p_value <= 2 / 2000 + 1e-12:
                warnings.append(
                    "This p (.001) is the smallest a two-sided permutation estimate "
                    "with 1,999 resamples can give: the true p may be much smaller. "
                    "The t approximation that SPSS reports has no such floor (the "
                    "Spearman p-value option of “Correlations: one variable with "
                    "several”)."
                )

    return CorrelationResult(
        x_name=x_name,
        y_name=y_name,
        method=method,
        n_total=len(df),
        n_complete=n,
        coefficient=coeff,
        p_value=p_value,
        ci_low=ci_low,
        ci_high=ci_high,
        p_method=p_method,
        warnings=warnings,
        x_values=x,
        y_values=y,
    )
