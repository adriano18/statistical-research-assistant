"""Guarded ordinary least squares for one or several quantitative predictors.

Each observation is one independent row. No causal interpretation is implied.
"""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan

from variable_rules import looks_like_identifier


@dataclass
class RegressionCoefficient:
    name: str
    b: float
    se: float
    t: float
    p: float
    ci_low: float
    ci_high: float
    vif: float | None


@dataclass
class RegressionResult:
    outcome: str
    predictors: list[str]
    n_total: int
    n_complete: int
    r_squared: float
    adjusted_r_squared: float
    f_value: float
    f_p: float
    model_df: int
    residual_df: int
    robust_hc3: bool
    coefficients: list[RegressionCoefficient]
    bp_p: float | None
    shapiro_p: float | None
    high_cook_count: int
    fitted: np.ndarray
    observed: np.ndarray
    residuals: np.ndarray
    warnings: list[str]


def analyze_regression(
    df: pd.DataFrame,
    outcome: str,
    predictors: list[str],
    assumptions_confirmed: bool = False,
    robust_hc3: bool = False,
) -> RegressionResult:
    """OLS with intercept and optional HC3 coefficient SEs.

    Select numerical scale predictors only; nominal variables must first be
    meaningfully dummy coded outside this prototype. Use complete cases.
    """
    if not assumptions_confirmed:
        raise ValueError("Review independence, linearity, outliers and predictor scales first.")
    if not predictors or len(predictors) > 5:
        raise ValueError("Select between one and five quantitative predictors.")
    if len(predictors) != len(set(predictors)):
        raise ValueError("A predictor was selected more than once.")
    names = [outcome, *predictors]
    if outcome in predictors:
        raise ValueError("The outcome cannot also be a predictor.")
    for name in names:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers cannot be used as regression variables.")

    raw = df[names]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    if (raw.notna() & numeric.isna()).any().any():
        raise ValueError("Selected variables contain non-numeric responses.")
    if not np.isfinite(numeric.to_numpy(dtype=float)[~numeric.isna().to_numpy()]).all():
        raise ValueError("Infinite values are not supported.")
    complete = numeric.dropna()
    n = len(complete)
    p = len(predictors)
    if n < max(15, 5 * (p + 1)):
        raise ValueError(
            "Not enough complete cases for this prototype: need at least "
            f"{max(15, 5 * (p + 1))}."
        )

    y = complete[outcome].to_numpy(dtype=float)
    x_raw = complete[predictors].to_numpy(dtype=float)
    if np.unique(y).size < 3:
        raise ValueError("The quantitative outcome needs meaningful variation.")
    if any(np.unique(x_raw[:, j]).size < 3 for j in range(p)):
        raise ValueError("Each quantitative predictor needs meaningful variation.")
    x = np.column_stack((np.ones(n), x_raw))
    if np.linalg.matrix_rank(x) != p + 1:
        raise ValueError("Predictors are perfectly collinear. Remove redundant columns.")

    model = sm.OLS(y, x).fit()
    inferred = (
        model.get_robustcov_results(cov_type="HC3", use_t=True)
        if robust_hc3 else model
    )
    intervals = np.asarray(inferred.conf_int(alpha=0.05))
    coefs = []
    for j, name in enumerate(["Intercept", *predictors]):
        if j == 0 or p == 1:
            vif = None
        else:
            # VIF = 1 / (1-R²), from the centered auxiliary regression.
            others = np.delete(x_raw, j - 1, axis=1)
            target = x_raw[:, j - 1]
            auxiliary = sm.OLS(target, sm.add_constant(others)).fit()
            vif = 1 / (1 - float(auxiliary.rsquared))
        coefs.append(RegressionCoefficient(
            name=name, b=float(inferred.params[j]),
            se=float(inferred.bse[j]), t=float(inferred.tvalues[j]),
            p=float(inferred.pvalues[j]),
            ci_low=float(intervals[j, 0]),
            ci_high=float(intervals[j, 1]),
            vif=vif,
        ))

    residuals = np.asarray(model.resid, dtype=float)
    fitted = np.asarray(model.fittedvalues, dtype=float)
    shapiro = stats.shapiro(residuals)
    shapiro_p = float(shapiro.pvalue)
    bp = het_breuschpagan(residuals, x)
    bp_p = float(bp[1])
    cooks = np.asarray(model.get_influence().cooks_distance[0], dtype=float)
    high_cook = int(np.sum(cooks > 4 / n))

    numbers = [
        model.rsquared, model.rsquared_adj,
        model.fvalue, model.f_pvalue, bp_p, shapiro_p,
    ]
    for coef in coefs:
        numbers.extend((coef.b, coef.se, coef.t, coef.p, coef.ci_low, coef.ci_high))
        if coef.vif is not None:
            numbers.append(coef.vif)
    if not all(math.isfinite(float(v)) for v in numbers):
        raise ValueError("Regression returned non-finite estimates; inspect the data.")

    warnings = [
        "OLS estimates associations conditional on the included predictors, NOT causal effects.",
        "Confirm linearity, independent observations, measurement scales, and study design.",
        "Residual normality matters for small-sample inference, not for OLS coefficients alone.",
        "A nonsignificant assumption test does not prove its assumption holds.",
        "Predictors are treated as quantitative; category codes are NOT automatically dummy-coded.",
    ]
    if n != len(df):
        warnings.append(f"Excluded {len(df) - n} rows with missing values (listwise).")
    if robust_hc3:
        warnings.append(
            "HC3 heteroskedasticity-robust standard errors and t-based confidence "
            "intervals apply to coefficients; model F remains the conventional OLS F."
        )
    if shapiro_p < 0.05:
        warnings.append("Residual Shapiro–Wilk p < .05; examine the Q–Q plot.")
    if bp_p < 0.05:
        warnings.append("Breusch–Pagan p < .05 suggests nonconstant residual variance.")
    if high_cook:
        warnings.append(
            f"{high_cook} observations have Cook's D > 4/N; review influence, "
            "do not automatically delete them."
        )
    if any(c.vif is not None and c.vif > 5 for c in coefs):
        warnings.append("One or more predictors have VIF > 5; inspect multicollinearity.")
    if n < 50:
        warnings.append("Small sample; estimates and assumption tests may be unstable.")

    return RegressionResult(
        outcome=outcome, predictors=list(predictors),
        n_total=len(df), n_complete=n,
        r_squared=float(model.rsquared),
        adjusted_r_squared=float(model.rsquared_adj),
        f_value=float(model.fvalue), f_p=float(model.f_pvalue),
        model_df=p, residual_df=n - p - 1,
        robust_hc3=bool(robust_hc3), coefficients=coefs,
        bp_p=bp_p, shapiro_p=shapiro_p, high_cook_count=high_cook,
        fitted=fitted, observed=y, residuals=residuals,
        warnings=warnings,
    )
