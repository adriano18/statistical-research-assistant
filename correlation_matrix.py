"""Exploratory correlation matrix, without unverified significance claims."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


@dataclass
class CorrelationMatrixResult:
    names: list[str]
    method: str
    coefficients: np.ndarray
    pair_counts: np.ndarray
    warnings: list[str]


def analyze_correlation_matrix(
    df: pd.DataFrame,
    names: list[str],
    method: str,
    scales_confirmed: bool = False,
) -> CorrelationMatrixResult:
    """Return pairwise-complete coefficients and N for 2–8 variables.

    The caller confirms measurement scales. No p-values are calculated for
    this exploratory matrix, to avoid uncorrected multiple comparisons.
    """
    if not scales_confirmed:
        raise ValueError("Confirm the measurement scales before analysis.")
    if method not in ("pearson", "spearman"):
        raise ValueError("Choose Pearson or Spearman.")
    if not 2 <= len(names) <= 8:
        raise ValueError("Choose between two and eight variables.")
    if len(names) != len(set(names)):
        raise ValueError("Choose each variable only once.")
    if any(name not in df.columns for name in names):
        raise ValueError("One or more selected variables are missing.")
    if any(looks_like_identifier(name) for name in names):
        raise ValueError("Identifiers cannot be used in a correlation matrix.")

    raw = df[names]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    if (raw.notna() & numeric.isna()).any().any():
        raise ValueError("One or more selected variables contain non-numeric responses.")

    values = numeric.to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError("Infinite values are not supported.")

    count = len(names)
    coefficients = np.full((count, count), np.nan, dtype=float)
    pair_counts = np.zeros((count, count), dtype=int)

    for i in range(count):
        for j in range(i, count):
            pair = numeric[[names[i], names[j]]].dropna() if i != j else numeric[[names[i]]].dropna()
            n = len(pair)
            pair_counts[i, j] = pair_counts[j, i] = n

            if n < 5:
                continue

            x = pair[names[i]].to_numpy(dtype=float)
            if np.unique(x).size < 2:
                continue
            if i == j:
                coefficient = 1.0
            else:
                y = pair[names[j]].to_numpy(dtype=float)
                if np.unique(y).size < 2:
                    continue
                if method == "pearson":
                    coefficient = float(stats.pearsonr(x, y).statistic)
                else:
                    coefficient = float(stats.spearmanr(x, y).statistic)
            if np.isfinite(coefficient):
                coefficients[i, j] = coefficients[j, i] = coefficient

    warnings = [
        "Exploratory coefficients only. No p-values or significance stars are shown.",
        "Correlations do not establish causation. Check outliers, design and assumptions.",
        "Pairwise-complete N may differ between cells when values are missing.",
    ]
    if method == "pearson":
        warnings.append(
            "Pearson requires quantitative variables and approximately linear relationships."
        )
    else:
        warnings.append(
            "Spearman is intended for ordinal/quantitative variables with monotonic relationships."
        )
    if np.isnan(coefficients).any():
        warnings.append(
            "N/A cells have fewer than five paired observations or no variation."
        )
    if count >= 5:
        warnings.append(
            "Many correlations increase the risk of false positives if used for hypothesis testing."
        )

    return CorrelationMatrixResult(
        names=list(names),
        method=method,
        coefficients=coefficients,
        pair_counts=pair_counts,
        warnings=warnings,
    )
