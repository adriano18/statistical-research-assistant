"""Pearson chi-square test of independence for two categorical variables."""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


@dataclass
class ChiSquareResult:
    variable_a: str
    variable_b: str
    row_labels: list[str]
    column_labels: list[str]
    observed: np.ndarray
    expected: np.ndarray
    n_total: int
    n_complete: int
    chi2: float
    df: int
    p_value: float
    cramers_v: float
    fisher_p: float | None
    sparse: bool
    warnings: list[str]


def analyze_chi_square(
    df: pd.DataFrame,
    variable_a: str,
    variable_b: str,
    independence_confirmed: bool = False,
) -> ChiSquareResult:
    """Test association, never causality. Complete-case contingency table."""
    if variable_a == variable_b:
        raise ValueError("Choose two different categorical variables.")
    for name in (variable_a, variable_b):
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers cannot be analyzed as categories.")
    if not independence_confirmed:
        raise ValueError(
            "Confirm categorical measurement scales and independent observations."
        )

    raw = df[[variable_a, variable_b]].dropna()
    n = len(raw)
    if n < 10:
        raise ValueError("At least ten complete observations are required.")

    # Use strings for numeric-coded and text categories alike. Never treat
    # the numeric codes as continuous scores.
    first = raw[variable_a].map(str)
    second = raw[variable_b].map(str)
    contingency = pd.crosstab(first, second)
    rows, columns = contingency.shape
    if not (2 <= rows <= 10 and 2 <= columns <= 10):
        raise ValueError(
            "Each variable must have 2 to 10 observed categories."
        )

    observed = contingency.to_numpy(dtype=int)
    calculation = stats.chi2_contingency(observed, correction=False)
    expected = calculation.expected_freq.astype(float)
    chi2 = float(calculation.statistic)
    p_value = float(calculation.pvalue)
    degrees = int(calculation.dof)
    v = math.sqrt(chi2 / (n * min(rows - 1, columns - 1)))
    if not all(math.isfinite(z) for z in [chi2, p_value, v]):
        raise ValueError("Cannot calculate finite association statistics.")

    small = int(np.count_nonzero(expected < 5))
    sparse = small > 0
    fisher = None
    if sparse and (rows, columns) == (2, 2):
        fisher = float(
            stats.fisher_exact(observed, alternative="two-sided").pvalue
        )

    warnings = [
        "Pearson's χ² evaluates association, not causation or group mean differences.",
        "Expected counts, independent observations, and study sampling require review.",
        "Pearson's χ² uses the asymptotic p-value without Yates' continuity correction.",
        "Cramér's V describes association strength, not its direction or causality.",
    ]
    if n < len(df):
        warnings.append(
            f"Excluded {len(df) - n} records missing either category."
        )
    if sparse:
        warnings.append(
            f"{small} of {expected.size} expected counts are below 5. "
            "The asymptotic chi-square p-value may be unreliable."
        )
        if np.any(expected < 1):
            warnings.append("At least one expected count is below 1.")
        if fisher is not None:
            warnings.append(
                "For this sparse 2×2 table, consider the separate two-sided "
                "Fisher exact p-value shown below."
            )
        else:
            warnings.append(
                "Consider collapsing defensibly similar categories or an "
                "exact/resampling approach; never merge groups solely to obtain significance."
            )

    return ChiSquareResult(
        variable_a=variable_a,
        variable_b=variable_b,
        row_labels=list(map(str, contingency.index)),
        column_labels=list(map(str, contingency.columns)),
        observed=observed,
        expected=expected,
        n_total=len(df),
        n_complete=n,
        chi2=chi2,
        df=degrees,
        p_value=p_value,
        cramers_v=v,
        fisher_p=fisher,
        sparse=sparse,
        warnings=warnings,
    )
