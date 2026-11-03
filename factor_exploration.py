"""Exploratory PCA and common-factor EFA with Pearson suitability diagnostics.

PCA explains total standardized variable variance. Principal-axis EFA
models shared variance and uniqueness. These are NOT interchangeable.
Parallel analysis in this MVP compares raw PCA correlation eigenvalues
against independent standard-normal simulated data (95th percentile).
It is a heuristic, not a formal model selection or EFA dimensionality test.
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
class FactorExplorationResult:
    method: str
    rotation: str
    items: list[str]
    n_total: int
    n_complete: int
    n_components: int
    loadings: np.ndarray
    uniqueness: np.ndarray | None
    factor_correlations: np.ndarray | None
    structure_loadings: np.ndarray | None
    kmo: float
    item_kmo: np.ndarray
    bartlett_chi2: float
    bartlett_df: int
    bartlett_p: float
    eigenvalues: np.ndarray
    parallel_threshold: np.ndarray
    parallel_count: int
    component_variance_share: np.ndarray | None
    warnings: list[str]


def _factorability(corr: np.ndarray, n: int):
    k = corr.shape[0]
    inverse = np.linalg.inv(corr)
    denominator = np.sqrt(np.outer(np.diag(inverse), np.diag(inverse)))
    partial = -inverse / denominator
    np.fill_diagonal(partial, 0)
    raw = corr.copy()
    np.fill_diagonal(raw, 0)
    raw_sq = raw**2
    partial_sq = partial**2
    numerator = raw_sq.sum(axis=0)
    total = numerator + partial_sq.sum(axis=0)
    if np.any(total <= 1e-12):
        raise ValueError(
            "KMO is undefined: an item has no usable association "
            "with the remaining selected items."
        )
    kmo_items = numerator / total
    kmo = float(raw_sq.sum() / (raw_sq.sum()+partial_sq.sum()))
    sign, logdet = np.linalg.slogdet(corr)
    if sign != 1:
        raise ValueError("Correlation determinant must be positive.")
    correction = n - 1 - (2*k + 5)/6
    chi2 = -correction * logdet
    degrees = k*(k-1)//2
    pvalue = float(stats.chi2.sf(chi2, degrees))
    return kmo, kmo_items, float(chi2), int(degrees), pvalue


def _parallel_eigenvalues(n: int, k: int, simulations: int, seed: int):
    generator = np.random.default_rng(seed)
    eigen = np.zeros((simulations, k))
    for rep in range(simulations):
        noise = generator.normal(size=(n, k))
        simulated = np.corrcoef(noise, rowvar=False)
        eigen[rep] = np.linalg.eigvalsh(simulated)[::-1]
    return np.percentile(eigen, 95, axis=0)


def analyze_factor_exploration(
    df: pd.DataFrame,
    item_names: list[str],
    method: str = "pca",
    n_components: int = 2,
    rotation: str = "none",
    assumptions_confirmed: bool = False,
) -> FactorExplorationResult:
    if not assumptions_confirmed:
        raise ValueError(
            "Confirm suitable quantitative item coding, independent rows, "
            "study design and a meaningful correlation matrix first."
        )
    items = list(item_names)
    k = len(items)
    if not 3 <= k <= 12 or len(set(items)) != k:
        raise ValueError("Select 3–12 distinct numeric research items.")
    if any(name not in df.columns for name in items):
        raise ValueError("Unknown variable in the selected items.")
    if any(looks_like_identifier(name) for name in items):
        raise ValueError("Identifiers cannot be used in EFA/PCA.")
    if method not in {"pca", "efa"}:
        raise ValueError("Choose PCA or principal-axis EFA.")
    if not 1 <= n_components <= min(5, k-1):
        raise ValueError("Choose 1–5 factors/components, fewer than the item count.")
    if rotation not in {"none", "varimax", "oblimin"}:
        raise ValueError("Choose none, varimax (orthogonal), or oblimin (oblique).")
    if rotation == "oblimin" and n_components < 2:
        raise ValueError("Oblimin requires at least two factors.")
    if method == "pca" and rotation != "none":
        raise ValueError("PCA is reported without rotation in this version.")

    raw = df[items]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    if (raw.notna() & numeric.isna()).any().any():
        raise ValueError("Selected research items contain non-numeric responses.")
    if np.isinf(numeric.to_numpy(dtype=float)).any():
        raise ValueError("Infinite values are not supported.")
    complete = numeric.dropna()
    n = len(complete)
    if n < max(60, 8*k):
        raise ValueError(
            f"Need at least {max(60, 8*k)} listwise complete participants "
            "for this exploratory implementation."
        )
    values = complete.to_numpy(dtype=float)
    deviations = values.std(axis=0, ddof=1)
    if np.any(deviations <= 0):
        raise ValueError("Constant items cannot be used in factor analysis.")

    corr = np.corrcoef(values, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(corr)
    if eigenvalues[0] <= 1e-8:
        raise ValueError(
            "Correlation matrix is singular or nearly singular. "
            "Check duplicated or linearly dependent items."
        )
    eigenvalues = eigenvalues[::-1]
    eigenvectors = eigenvectors[:, ::-1]
    kmo, item_kmo, bartlett, df_b, p_b = _factorability(corr, n)
    parallel = _parallel_eigenvalues(n, k, simulations=150, seed=20261103)
    parallel_count = int(np.sum(eigenvalues > parallel))

    uniqueness = None
    variance_share = None
    factor_correlations = None
    structure_loadings = None
    if method == "pca":
        loadings = eigenvectors[:, :n_components] * np.sqrt(
            eigenvalues[:n_components]
        )
        variance_share = eigenvalues[:n_components]/k
        for j in range(n_components):
            if loadings[:, j].sum() < 0:
                loadings[:, j] *= -1
    else:
        try:
            with warnings.catch_warnings(record=True) as fitted_warnings:
                warnings.simplefilter("always")
                solution = Factor(
                    corr=corr, n_factor=n_components, method="pa",
                    nobs=n,
                ).fit()
                if rotation in {"varimax", "oblimin"} and n_components > 1:
                    solution.rotate(rotation)
            loadings = np.asarray(solution.loadings, dtype=float)
            if rotation == "oblimin":
                # Statsmodels documents Phi = T.T @ T for the oblique
                # transformation stored in FactorResults.rotation_matrix.
                transformation = np.asarray(
                    solution.rotation_matrix, dtype=float
                )
                factor_correlations = transformation.T @ transformation
                factor_correlations = (
                    factor_correlations + factor_correlations.T
                ) / 2
                if (
                    not np.isfinite(factor_correlations).all()
                    or not np.allclose(
                        np.diag(factor_correlations), 1, atol=1e-4
                    )
                    or np.linalg.eigvalsh(factor_correlations)[0] <= 0
                ):
                    raise ValueError(
                        "Invalid oblique factor correlation matrix."
                    )
                structure_loadings = loadings @ factor_correlations
            uniqueness = np.asarray(solution.uniqueness, dtype=float)
            if any("did not converge" in str(w.message).lower()
                   for w in fitted_warnings):
                raise ValueError("Principal-axis model did not converge.")
        except (ValueError, np.linalg.LinAlgError, RuntimeError) as error:
            raise ValueError(
                "Principal-axis EFA estimation failed. "
                "Try fewer factors, inspect correlations or increase N."
            ) from error
        if not np.isfinite(uniqueness).all() or (
            (uniqueness < 1e-6) | (uniqueness > 1 + 1e-5)
        ).any():
            raise ValueError(
                "EFA produced an improper uniqueness / Heywood-like solution."
            )

    if not np.isfinite(loadings).all():
        raise ValueError("Non-finite factor/component loadings.")
    notes = [
        "Exploratory only: factor retention, item content and model fit "
        "require substantive researcher review.",
        "Pearson item correlations approximate Likert answers as numeric. "
        "This is not polychoric/ordinal EFA.",
        "KMO and Bartlett are factorability diagnostics, not guarantees "
        "that the selected factor structure is valid.",
        "Parallel analysis compares CORRELATION PCA eigenvalues with the "
        "95th percentile of 150 independent normal simulations (fixed seed). "
        "It is guidance, not automatic EFA factor-number determination.",
        "Selected number of factors/components was specified by the researcher.",
        "PCA components summarize TOTAL variance and do not represent "
        "latent common factors or correct for item error.",
        "EFA principal axes describe SHARED item variance and uniqueness; "
        "varimax assumes independent factors, whereas oblimin allows "
        "correlated factors.",
        "No factor-score predictions, polychoric ordinal correlations, "
        "confirmatory fit or cross-sample validation are provided.",
        "Neither scree plot nor loadings alone establish scale validity.",
    ]
    if n != len(df):
        notes.append(
            f"{len(df)-n} rows excluded listwise due to missing item responses."
        )
    if kmo < .6:
        notes.append("KMO below .60: factorability may be weak; inspect individual item KMO.")
    if any(item_kmo < .5):
        notes.append("At least one item KMO below .50: review potentially unsuitable items.")
    if p_b >= .05:
        notes.append("Bartlett p ≥ .05; evidence for non-identity correlations is limited.")
    if n_components > parallel_count:
        notes.append(
            "Chosen factor/component number exceeds this PCA parallel-analysis "
            "heuristic; verify the number substantively."
        )
    if method == "efa" and n_components > 1 and rotation == "oblimin":
        largest_offdiag = float(np.max(np.abs(
            factor_correlations - np.eye(n_components)
        )))
        notes.append(
            f"Oblimin factor correlations: largest absolute off-diagonal "
            f"association = {largest_offdiag:.3f}. Inspect the pattern "
            "and structure matrices separately."
        )
        if np.any((np.abs(loadings) >= .30).sum(axis=1) > 1):
            notes.append(
                "Some items have absolute pattern loadings >= .30 on "
                "multiple factors (descriptive cross-loadings). "
                "These are not automatic exclusion decisions."
            )
    if method == "efa" and n_components > 1 and rotation == "none":
        notes.append(
            "Multiple unrotated EFA factors can be hard to interpret. "
            "Consider an appropriate rotation."
        )

    return FactorExplorationResult(
        method=method, rotation=rotation,
        items=items, n_total=len(df), n_complete=n,
        n_components=n_components,
        loadings=loadings,
        uniqueness=uniqueness,
        factor_correlations=factor_correlations,
        structure_loadings=structure_loadings,
        kmo=kmo,
        item_kmo=item_kmo,
        bartlett_chi2=bartlett,
        bartlett_df=df_b, bartlett_p=p_b,
        eigenvalues=eigenvalues,
        parallel_threshold=parallel,
        parallel_count=parallel_count,
        component_variance_share=variance_share,
        warnings=notes,
    )
