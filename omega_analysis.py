"""One-factor standardized McDonald's omega and corrected item-rest diagnostics.

Omega is estimated from an ML one-common-factor model on the Pearson
correlation matrix for a unit-weighted composite of standardized items.
Not hierarchical omega, not an ordinal/polychoric omega, and not a
confirmation of unidimensionality, model fit or construct validity.
"""

from dataclasses import dataclass
import math
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.multivariate.factor import Factor

from variable_rules import looks_like_identifier


@dataclass
class ItemDiagnostic:
    name: str
    missing: int
    mean: float
    sd: float
    corrected_item_rest_r: float
    standardized_loading: float
    uniqueness: float


@dataclass
class OmegaResult:
    omega: float
    n_total: int
    n_complete: int
    items: list[str]
    diagnostics: list[ItemDiagnostic]
    largest_residual_corr: float
    first_eigenvalue: float
    second_eigenvalue: float
    warnings: list[str]


def analyze_omega(df: pd.DataFrame, item_names: list[str]) -> OmegaResult:
    """Estimate standardized one-factor omega on listwise complete cases."""
    items = list(item_names)
    if not 3 <= len(items) <= 12 or len(set(items)) != len(items):
        raise ValueError("Select 3–12 DISTINCT items from ONE questionnaire scale.")
    if any(item not in df.columns for item in items):
        raise ValueError("Unknown questionnaire item column.")
    if any(looks_like_identifier(item) for item in items):
        raise ValueError("Identifiers cannot be used as questionnaire items.")

    source = df[items]
    numbers = source.apply(pd.to_numeric, errors="coerce")
    if (source.notna() & numbers.isna()).any().any():
        raise ValueError("Selected items contain non-numeric responses.")
    if np.isinf(numbers.to_numpy(dtype=float)).any():
        raise ValueError("Selected items contain infinite values.")

    complete = numbers.dropna()
    n, k = len(complete), len(items)
    if n < max(30, 5 * k):
        raise ValueError(
            f"At least {max(30, 5*k)} listwise complete participants "
            "are required for this introductory one-factor estimation."
        )
    x = complete.to_numpy(dtype=float)
    variances = x.var(axis=0, ddof=1)
    if np.any(variances <= 0):
        raise ValueError("One or more questionnaire items have no variation.")

    correlation = np.corrcoef(x, rowvar=False)
    eigvals = np.linalg.eigvalsh(correlation)
    if eigvals[0] < 1e-7:
        raise ValueError(
            "Item correlation matrix is singular or nearly singular; "
            "inspect duplicated or linearly dependent items."
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fit = Factor(
                corr=correlation, n_factor=1, method="ml", nobs=n,
            ).fit()
        loadings = np.asarray(fit.loadings, dtype=float).reshape(-1)
        uniqueness = np.asarray(fit.uniqueness, dtype=float).reshape(-1)
    except (ValueError, np.linalg.LinAlgError, RuntimeError, OverflowError) as error:
        raise ValueError(
            "One-factor model could not be fitted reliably. "
            "Check scale dimensionality, coding and data quality."
        ) from error

    if (
        not np.isfinite(loadings).all()
        or not np.isfinite(uniqueness).all()
        or np.any(uniqueness <= 1e-6)
        or np.any(uniqueness > 1 + 1e-5)
    ):
        raise ValueError(
            "Invalid uniqueness / Heywood-like model solution; "
            "do not report omega from this fit."
        )

    # The factor's sign is arbitrary. We retain individual loading
    # signs relative to the majority direction, never auto-reverse an item.
    if loadings.sum() < 0:
        loadings *= -1
    common = float(np.sum(loadings) ** 2)
    residual = float(np.sum(uniqueness))
    omega = common / (common + residual)
    if not math.isfinite(omega) or not 0 <= omega <= 1:
        raise ValueError("Computed omega is outside [0, 1].")

    reconstructed = np.outer(loadings, loadings)
    np.fill_diagonal(reconstructed, 1.0)
    discrepancy = correlation - reconstructed
    np.fill_diagonal(discrepancy, 0.0)
    max_residual = float(np.max(np.abs(discrepancy)))

    total = x.sum(axis=1)
    details = []
    for j, name in enumerate(items):
        rest = total - x[:, j]
        if np.std(rest, ddof=1) <= 0:
            raise ValueError(
                f"Rest-score for {name} has no variation; item diagnostics unavailable."
            )
        item_rest = float(stats.pearsonr(x[:, j], rest).statistic)
        details.append(ItemDiagnostic(
            name=name,
            missing=int(numbers[name].isna().sum()),
            mean=float(x[:, j].mean()),
            sd=float(x[:, j].std(ddof=1)),
            corrected_item_rest_r=item_rest,
            standardized_loading=float(loadings[j]),
            uniqueness=float(uniqueness[j]),
        ))

    cautions = [
        "This is standardized one-factor omega, estimated from Pearson "
        "correlations with maximum-likelihood common factor analysis.",
        "This coefficient assumes an approximately one-factor congeneric "
        "structure and uncorrelated item residuals; those assumptions are "
        "NOT established by obtaining a numerical omega.",
        "Raw Likert categories are treated as numeric for Pearson correlations. "
        "Ordinal/polychoric reliability is not calculated.",
        "Confirm that items describe ONE construct and have matching scoring "
        "direction; use Data preparation to reverse-code keyed items.",
        "Corrected item-rest correlations use the same listwise-complete cases "
        "as the omega fit. A low correlation invites item review, not automatic removal.",
        "No sampling confidence interval or formal factor-fit test is reported "
        "for omega in this version.",
        "Omega measures estimated internal consistency, NOT validity, "
        "unidimensionality or clinical diagnostic accuracy.",
    ]
    if n != len(df):
        cautions.append(
            f"{len(df)-n} participants excluded listwise for missing item data."
        )
    if n < 100:
        cautions.append(
            "Small complete sample; factor loadings and omega may be unstable."
        )
    if any(d.corrected_item_rest_r < 0 for d in details):
        cautions.append(
            "At least one corrected item-rest correlation is NEGATIVE. "
            "Check reverse coding and construct consistency before interpretation."
        )
    if any(d.standardized_loading < 0 for d in details):
        cautions.append(
            "At least one factor loading points opposite the main factor. "
            "Inspect the item; do not silently invert its score."
        )
    if max_residual > .15:
        cautions.append(
            "Large off-diagonal reproduced-correlation residual (> .15) "
            "suggests this one-factor approximation may fit poorly."
        )
    if eigvals[-2] > 1.0:
        cautions.append(
            "Second correlation eigenvalue exceeds 1; explore dimensionality "
            "with EFA rather than assuming a single factor."
        )

    return OmegaResult(
        omega=float(omega), n_total=len(df), n_complete=n,
        items=items, diagnostics=details,
        largest_residual_corr=max_residual,
        first_eigenvalue=float(eigvals[-1]),
        second_eigenvalue=float(eigvals[-2]),
        warnings=cautions,
    )
