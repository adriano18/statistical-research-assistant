"""Cronbach's alpha for multi-item scales, with cautious diagnostics."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pingouin as pg

from variable_rules import looks_like_identifier


@dataclass
class ReliabilityResult:
    alpha: float
    ci_low: float
    ci_high: float
    n_total: int
    n_complete: int
    items: list[str]
    alpha_if_deleted: dict[str, float]
    warnings: list[str]


def analyze_cronbach(df: pd.DataFrame, item_names: list[str]) -> ReliabilityResult:
    """Calculate raw Cronbach alpha using complete cases.

    The researcher must first confirm that selected items measure the same
    construct and reverse-scored items have already been recoded.
    """
    items = list(dict.fromkeys(item_names))
    if len(items) < 3:
        raise ValueError("Choose at least three items belonging to the same scale.")

    missing_columns = [name for name in items if name not in df.columns]
    if missing_columns:
        raise ValueError(f"Unknown columns: {', '.join(missing_columns)}")
    if any(looks_like_identifier(name) for name in items):
        raise ValueError("Identifiers cannot be used as questionnaire items.")

    original = df[items]
    numeric = original.apply(pd.to_numeric, errors="coerce")

    if (original.notna() & numeric.isna()).any().any():
        raise ValueError("Selected items contain non-numeric responses.")

    complete = numeric.dropna()
    if len(complete) < 5:
        raise ValueError("At least five complete responses are required in this prototype.")

    if (complete.var(ddof=1) <= 0).any():
        raise ValueError("One or more items have no variation.")
    if complete.sum(axis=1).var(ddof=1) <= 0:
        raise ValueError("The total score has no variation.")

    alpha, ci = pg.cronbach_alpha(data=complete, nan_policy="listwise")
    if not np.isfinite(alpha) or not np.all(np.isfinite(ci)):
        raise ValueError("Could not calculate a finite alpha and confidence interval.")

    alpha_if_deleted = {}
    if len(items) >= 4:
        for name in items:
            reduced = complete.drop(columns=name)
            if (reduced.sum(axis=1).var(ddof=1) > 0
                    and (reduced.var(ddof=1) > 0).all()):
                reduced_alpha, _ = pg.cronbach_alpha(
                    data=reduced, nan_policy="listwise"
                )
                if np.isfinite(reduced_alpha):
                    alpha_if_deleted[name] = float(reduced_alpha)

    warnings = [
        "Alpha describes internal consistency, not validity or unidimensionality.",
        "Confirm that the items measure one construct and that reverse-coded "
        "items were recoded before analysis.",
    ]
    if len(complete) < len(df):
        warnings.append(
            f"Listwise deletion excluded {len(df) - len(complete)} respondents "
            "with missing item responses."
        )
    if len(complete) < 50:
        warnings.append("This is a small sample; reliability estimates may be unstable.")
    if alpha < 0:
        warnings.append(
            "Negative alpha suggests contradictory item covariances or a coding problem."
        )
    if alpha > 0.95:
        warnings.append(
            "A very high alpha can indicate redundant items; inspect item content."
        )

    return ReliabilityResult(
        alpha=float(alpha),
        ci_low=float(ci[0]),
        ci_high=float(ci[1]),
        n_total=len(df),
        n_complete=len(complete),
        items=items,
        alpha_if_deleted=alpha_if_deleted,
        warnings=warnings,
    )
