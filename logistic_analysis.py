"""Guarded binary logistic regression for independent participant rows.

The binary outcome must explicitly contain 0 (no event) and 1 (event).
Predictors are treated as quantitative continuous variables, not numeric
category codes; categorical coding and clustered/repeated designs are excluded.
"""

from dataclasses import dataclass
import math
import warnings

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.tools.sm_exceptions import (
    ConvergenceWarning, PerfectSeparationError, PerfectSeparationWarning
)

from variable_rules import looks_like_identifier


@dataclass
class LogisticCoefficient:
    name: str
    b: float
    se: float
    z: float
    p: float
    ci_low: float
    ci_high: float
    odds_ratio: float
    or_low: float
    or_high: float


@dataclass
class LogisticResult:
    outcome: str
    predictors: list[str]
    n_total: int
    n_complete: int
    events: int
    non_events: int
    llr: float
    llr_p: float
    mcfadden_r2: float
    aic: float
    roc_auc: float
    coefficients: list[LogisticCoefficient]
    actual: np.ndarray
    probabilities: np.ndarray
    warnings: list[str]


def binary_logistic_regression(
    df: pd.DataFrame,
    outcome: str,
    predictors: list[str],
    design_confirmed: bool = False,
) -> LogisticResult:
    """Fit MLE Logit with a fixed intercept and Wald coefficient intervals.

    Conservative guards fail on known invalid designs and unstable fits.
    In-sample performance statistics are explicitly descriptive.
    """
    if not design_confirmed:
        raise ValueError(
            "Confirm a 0/1 outcome, independent observations, quantitative "
            "predictors, and study design before fitting the model."
        )
    if not predictors or len(predictors) > 5:
        raise ValueError("Select between one and five quantitative predictors.")
    if len(predictors) != len(set(predictors)):
        raise ValueError("Select each predictor only once.")
    if outcome in predictors:
        raise ValueError("The outcome cannot also be a predictor.")
    selected = [outcome, *predictors]
    for name in selected:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers cannot be logistic model variables.")

    raw = df[selected]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    if (raw.notna() & numeric.isna()).any().any():
        raise ValueError("Selected variables contain non-numeric responses.")
    nonmissing = numeric.to_numpy(dtype=float)
    if np.isinf(nonmissing).any():
        raise ValueError("Infinite values are not supported.")

    valid_y = set(numeric[outcome].dropna().unique().tolist())
    if valid_y != {0, 1}:
        raise ValueError(
            "The binary outcome must contain only 0 and 1, with both classes present. "
            "Recode other categories explicitly before analysis."
        )
    complete = numeric.dropna()
    n, p = len(complete), len(predictors)
    if n < max(50, 12 * (p + 1)):
        raise ValueError(
            f"Not enough complete observations: need at least "
            f"{max(50, 12 * (p + 1))}."
        )
    y = complete[outcome].to_numpy(dtype=float)
    positive = int(np.count_nonzero(y == 1))
    negative = int(np.count_nonzero(y == 0))
    if min(positive, negative) < max(10, 5 * p):
        raise ValueError(
            "Too few events or non-events for this introductory model. "
            "Increase sample size or reduce predictors."
        )

    values = complete[predictors].to_numpy(dtype=float)
    if any(np.unique(values[:, j]).size < 3 for j in range(p)):
        raise ValueError(
            "All selected predictors must represent varied quantitative "
            "measurements (at least three observed values). "
            "Categorical/dummy-coded predictors are not supported yet."
        )
    matrix = np.column_stack((np.ones(n), values))
    if np.linalg.matrix_rank(matrix) != p + 1:
        raise ValueError("Predictors are perfectly collinear. Remove redundant variables.")

    # This obvious one-variable separation check avoids an unstable MLE.
    if p == 1:
        zero = values[y == 0, 0]
        one = values[y == 1, 0]
        if one.min() > zero.max() or zero.min() > one.max():
            raise ValueError(
                "Perfect separation: a predictor completely distinguishes the "
                "outcome classes. Standard logistic MLE is not reliable."
            )

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            fitted = sm.Logit(y, matrix).fit(disp=False, maxiter=150)
        except (PerfectSeparationError, np.linalg.LinAlgError, OverflowError) as err:
            raise ValueError(
                "Logistic model could not be estimated. Check for (quasi-)perfect "
                "separation, collinearity and extreme predictors."
            ) from err

    if not fitted.mle_retvals.get("converged", False):
        raise ValueError(
            "Maximum likelihood did not converge; inspect separation, scale "
            "and sample adequacy."
        )
    if any(issubclass(w.category, (ConvergenceWarning, PerfectSeparationWarning))
           for w in captured):
        raise ValueError(
            "The fitting algorithm reported separation or convergence problems. "
            "Results would be unreliable."
        )

    coef_ci = np.asarray(fitted.conf_int(alpha=0.05), dtype=float)
    coefficients = []
    for j, name in enumerate(["Intercept", *predictors]):
        b = float(fitted.params[j])
        se = float(fitted.bse[j])
        low, high = (float(v) for v in coef_ci[j])
        if max(abs(b), abs(low), abs(high)) > 22 or se <= 0:
            raise ValueError(
                "Extreme coefficient/interval suggests unstable estimation or "
                "quasi-separation; revise the model."
            )
        coefficients.append(LogisticCoefficient(
            name=name, b=b, se=se, z=float(fitted.tvalues[j]),
            p=float(fitted.pvalues[j]), ci_low=low, ci_high=high,
            odds_ratio=math.exp(b), or_low=math.exp(low),
            or_high=math.exp(high),
        ))

    probabilities = np.asarray(fitted.predict(matrix), dtype=float)
    if not np.isfinite(probabilities).all() or not (
        (probabilities >= 0) & (probabilities <= 1)
    ).all():
        raise ValueError("Predicted probabilities are invalid.")
    ranks = stats.rankdata(probabilities, method="average")
    rank_sum = float(ranks[y == 1].sum())
    roc_auc = (rank_sum - positive * (positive + 1) / 2) / (positive * negative)

    llr = float(fitted.llr)
    llr_p = float(fitted.llr_pvalue)
    mcfadden_r2 = float(fitted.prsquared)
    aic = float(fitted.aic)
    numbers = [llr, llr_p, mcfadden_r2, aic, roc_auc]
    for coef in coefficients:
        numbers.extend([
            coef.b, coef.se, coef.z, coef.p,
            coef.ci_low, coef.ci_high, coef.odds_ratio,
            coef.or_low, coef.or_high,
        ])
    if not all(math.isfinite(v) for v in numbers):
        raise ValueError("Logistic model produced non-finite estimates.")

    notes = [
        "Outcome is coded 0 = no event, 1 = event. Check that 1 means the intended event.",
        "Odds ratios describe multiplicative changes in ODDS per one-unit predictor increase; they are not risk ratios.",
        "Only numerical quantitative predictors are supported; nominal categories need explicit coding.",
        "Independence of rows, the logit-linearity assumption, confounders and influential cases require researcher review.",
        "Maximum-likelihood Wald p-values and 95% confidence intervals are approximate, especially in small samples.",
        "McFadden's pseudo-R² is NOT the proportion of explained outcome variance.",
        "ROC AUC is calculated on the SAME data used to fit the model; it is optimistic and NOT validated predictive performance.",
        "No causal conclusions or clinical decision thresholds can be drawn from this analysis.",
    ]
    if n < len(df):
        notes.append(f"Excluded {len(df) - n} observations with missing values (listwise).")
    if min(positive, negative) < 10 * p:
        notes.append(
            "Limited events/non-events relative to predictors; estimates may "
            "be unstable. Events-per-predictor is only a rough heuristic."
        )
    if any(np.max(np.abs(values[:, j])) > 1e4 for j in range(p)):
        notes.append("Very large predictor magnitudes can affect numerical stability.")
    if np.min(probabilities) < .005 or np.max(probabilities) > .995:
        notes.append(
            "Some fitted probabilities are near 0 or 1; inspect possible "
            "quasi-separation and overfitting."
        )
    return LogisticResult(
        outcome=outcome, predictors=list(predictors),
        n_total=len(df), n_complete=n,
        events=positive, non_events=negative,
        llr=llr, llr_p=llr_p,
        mcfadden_r2=mcfadden_r2, aic=aic, roc_auc=float(roc_auc),
        coefficients=coefficients,
        actual=y.astype(int), probabilities=probabilities,
        warnings=notes,
    )
