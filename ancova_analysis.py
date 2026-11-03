"""One-factor ANCOVA and interaction GLM (Gaussian general linear models).

This is NOT a generalized linear model. The outcome must be quantitative.
A common-slope ANCOVA is blocked when a joint group-by-covariate interaction
check is significant. Interaction GLM reports GROUP contrasts only at the
sample-grand-mean covariate reference, not a universal treatment effect.
"""

from dataclasses import dataclass
from itertools import combinations
import math

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

from posthoc_analysis import holm_adjust
from variable_rules import looks_like_identifier


@dataclass
class AdjustedGroup:
    label: str
    n: int
    raw_mean: float
    adjusted_mean: float
    se: float
    ci_low: float
    ci_high: float


@dataclass
class AdjustedPair:
    first: str
    second: str
    difference: float
    t: float
    p_raw: float
    p_holm: float
    ci_low: float
    ci_high: float


@dataclass
class AncovaResult:
    outcome: str
    group: str
    covariates: list[str]
    mode: str
    reference_values: dict[str, float]
    n_total: int
    n_complete: int
    df_group: int
    df_error: int
    f_group: float
    p_group: float
    eta_squared_partial: float
    f_interaction: float
    p_interaction: float
    df_interaction: int
    r_squared: float
    residual_shapiro_p: float
    residual_levene_p: float
    high_cook_count: int
    groups: list[AdjustedGroup]
    pairs: list[AdjustedPair]
    plot_group: np.ndarray
    plot_covariate: np.ndarray
    plot_outcome: np.ndarray
    plot_lines: dict[str, np.ndarray]
    plot_x: np.ndarray
    warnings: list[str]


def analyze_ancova(
    df: pd.DataFrame,
    outcome: str,
    group: str,
    covariates: list[str],
    mode: str = "ancova",
    assumptions_confirmed: bool = False,
) -> AncovaResult:
    """Fit a group factor and 1–3 covariates, with an optional interaction.

    Reference is the observed grand mean of EACH covariate across complete
    cases. Pairwise p-values use Holm correction; pair CIs are unadjusted 95%.
    """
    if not assumptions_confirmed:
        raise ValueError(
            "Confirm independent participants, quantitative measurements, "
            "covariate timing, group design and checked assumptions first."
        )
    if mode not in {"ancova", "interaction"}:
        raise ValueError("Choose ANCOVA or the interaction general linear model.")
    if not 1 <= len(covariates) <= 3 or len(set(covariates)) != len(covariates):
        raise ValueError("Choose one to three distinct quantitative covariates.")
    names = [outcome, group, *covariates]
    if len(set(names)) != len(names):
        raise ValueError("Outcome, group and covariates must be different variables.")
    for name in names:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers cannot be used as study variables.")

    numeric = df[[outcome, *covariates]].apply(
        pd.to_numeric, errors="coerce"
    )
    original = df[[outcome, *covariates]]
    if (original.notna() & numeric.isna()).any().any():
        raise ValueError("Outcome and covariates must contain quantitative numeric data.")
    if np.isinf(numeric.to_numpy(dtype=float)).any():
        raise ValueError("Infinite values are not supported.")

    complete_mask = numeric.notna().all(axis=1) & df[group].notna()
    sample = numeric.loc[complete_mask]
    labels = df.loc[complete_mask, group].map(str)
    categories = sorted(labels.unique().tolist())
    k = len(categories)
    if not 2 <= k <= 6:
        raise ValueError("Grouping factor must contain 2–6 observed categories.")
    if len(set(categories)) < k:
        raise ValueError("Group labels must uniquely identify observed groups.")
    counts = np.array([(labels == cat).sum() for cat in categories])
    if counts.min() < 8:
        raise ValueError("At least eight complete participants per group are required.")

    n = len(sample)
    q = len(covariates)
    full_parameter_count = k * (q + 1)
    if n < max(40, 6 * full_parameter_count):
        raise ValueError(
            "Not enough complete cases for the group-by-covariate check: "
            f"need at least {max(40, 6 * full_parameter_count)}."
        )

    y = sample[outcome].to_numpy(dtype=float)
    if np.unique(y).size < 4:
        raise ValueError("Quantitative outcome needs meaningful variation.")
    cov_values = sample[covariates].to_numpy(dtype=float)
    if any(np.unique(cov_values[:, j]).size < 4 for j in range(q)):
        raise ValueError("Each covariate needs at least four distinct values.")
    reference = cov_values.mean(axis=0)
    centered = cov_values - reference

    dummies = np.column_stack([
        (labels.to_numpy() == cat).astype(float)
        for cat in categories[1:]
    ])
    additive = np.column_stack([np.ones(n), dummies, centered])
    interaction_cols = [
        dummies[:, i] * centered[:, j]
        for i in range(k - 1) for j in range(q)
    ]
    full = np.column_stack([additive, *interaction_cols])

    if np.linalg.matrix_rank(full) != full.shape[1]:
        raise ValueError(
            "Model is rank deficient. Group covariate ranges may have insufficient "
            "variation or covariates may be collinear."
        )

    additive_fit = sm.OLS(y, additive).fit()
    full_fit = sm.OLS(y, full).fit()
    comparison = full_fit.compare_f_test(additive_fit)
    f_interaction = float(comparison[0])
    p_interaction = float(comparison[1])
    df_interaction = int(comparison[2])
    if not all(math.isfinite(x) for x in (f_interaction, p_interaction)):
        raise ValueError("The homogeneity-of-slopes check is not estimable.")

    if mode == "ancova" and p_interaction < .05:
        raise ValueError(
            "Group-by-covariate interaction detected (p < .05). "
            "Common-slope ANCOVA is not reported as valid here. "
            "Review plots and fit the Interaction GLM to report effects "
            "at specified covariate reference values."
        )

    fitted = additive_fit if mode == "ancova" else full_fit
    n_params = fitted.model.exog.shape[1]
    df_error = int(fitted.df_resid)
    if df_error < 8:
        raise ValueError("Insufficient residual degrees of freedom.")

    # With centered covariates, group coefficients are differences between
    # groups at the observed grand means. This is a conditional F in GLM mode.
    restriction = np.zeros((k - 1, n_params))
    for j in range(k - 1):
        restriction[j, 1 + j] = 1
    f_test = fitted.f_test(restriction)
    f_group = float(np.asarray(f_test.fvalue).item())
    p_group = float(np.asarray(f_test.pvalue).item())
    df_group = k - 1
    partial_eta = f_group * df_group / (f_group * df_group + df_error)

    inv_cov = np.asarray(fitted.cov_params(), dtype=float)
    critical = float(stats.t.ppf(.975, df_error))
    def vector_for_group(index: int) -> np.ndarray:
        vector = np.zeros(n_params)
        vector[0] = 1.
        if index > 0:
            vector[index] = 1.
        return vector

    group_rows = []
    for i, cat in enumerate(categories):
        vector = vector_for_group(i)
        mean = float(vector @ fitted.params)
        se = float(np.sqrt(vector @ inv_cov @ vector))
        original_mean = float(y[labels.to_numpy() == cat].mean())
        group_rows.append(AdjustedGroup(
            label=cat, n=int(counts[i]), raw_mean=original_mean,
            adjusted_mean=mean, se=se,
            ci_low=mean-critical*se, ci_high=mean+critical*se,
        ))

    # Pairwise comparisons refer to the identical covariate reference, even
    # in an interaction model. 95% CI is deliberately labelled unadjusted.
    tmp_pairs, p_values = [], []
    for i, j in combinations(range(k), 2):
        contrast = vector_for_group(j) - vector_for_group(i)
        difference = float(contrast @ fitted.params)
        se = float(np.sqrt(contrast @ inv_cov @ contrast))
        if se <= 0:
            raise ValueError("Adjusted group contrast has zero standard error.")
        t_value = difference / se
        p = float(2 * stats.t.sf(abs(t_value), df_error))
        tmp_pairs.append((
            categories[i], categories[j], difference, t_value,
            p, difference-critical*se, difference+critical*se,
        ))
        p_values.append(p)

    pairs = [
        AdjustedPair(
            first=a, second=b, difference=diff, t=t_value,
            p_raw=p, p_holm=p_adj, ci_low=low, ci_high=high,
        )
        for (a, b, diff, t_value, p, low, high), p_adj
        in zip(tmp_pairs, holm_adjust(p_values))
    ]

    residuals = np.asarray(fitted.resid, dtype=float)
    shapiro_p = float(stats.shapiro(residuals).pvalue) if n <= 5000 else float("nan")
    levene = stats.levene(*[
        residuals[labels.to_numpy() == cat]
        for cat in categories
    ], center="median")
    levene_p = float(levene.pvalue)
    cooks = np.asarray(fitted.get_influence().cooks_distance[0])
    high_cook_count = int(np.sum(cooks > 4 / n))

    # Curves vary in their slopes only in interaction mode. Other covariates
    # stay centered at zero (the sample grand mean).
    main_covariate = cov_values[:, 0]
    plot_x = np.linspace(float(main_covariate.min()), float(main_covariate.max()), 80)
    lines = {}
    for i, cat in enumerate(categories):
        base = vector_for_group(i)
        curves = []
        for x_value in plot_x:
            row = base.copy()
            row[k] = x_value - reference[0]  # first covariate column
            if mode == "interaction" and i > 0:
                interaction_offset = k + q
                row[interaction_offset + (i - 1) * q] = x_value - reference[0]
            curves.append(float(row @ fitted.params))
        lines[cat] = np.asarray(curves)

    notes = [
        "General Linear Model means an identity-link Gaussian linear model, NOT generalized linear models.",
        "Grouping is a categorical factor; covariates are treated as quantitative.",
        "All group contrasts and adjusted means are estimated at the COMPLETE-CASE grand mean of each covariate.",
        "Interpretation depends on independent observations, linearity, appropriate residual errors, covariate timing and study design.",
        "Holm-adjusted pairwise p-values control familywise error; individual 95% CIs are NOT multiplicity-adjusted.",
        "A nonsignificant diagnostic does NOT prove any assumption holds.",
        "Neither statistical significance nor adjusted group differences demonstrate causality.",
    ]
    if mode == "interaction":
        notes.append(
            "Group effects are CONDITIONAL on reference covariates; nonparallel "
            "slopes prevent interpreting them as a constant group difference."
        )
    else:
        notes.append(
            "Common-slope ANCOVA was retained because the joint interaction "
            "check was not significant. This does not prove parallel slopes."
        )
    if n < len(df):
        notes.append(f"{len(df)-n} rows excluded listwise due to missing values.")
    if shapiro_p < .05:
        notes.append("Residual Shapiro–Wilk p < .05; inspect residual Q–Q plot.")
    if levene_p < .05:
        notes.append(
            "Median-centered Levene p < .05 suggests unequal residual spreads."
        )
    if high_cook_count:
        notes.append(
            f"{high_cook_count} observations have Cook’s D > 4/N; "
            "review influence before reporting."
        )
    for j, name in enumerate(covariates):
        low = max(float(cov_values[labels.to_numpy() == cat, j].min())
                  for cat in categories)
        high = min(float(cov_values[labels.to_numpy() == cat, j].max())
                   for cat in categories)
        if high <= low:
            notes.append(
                f"Covariate {name} has no common observed range across groups. "
                "Adjusted comparisons can require EXTRAPOLATION."
            )
        elif not low <= reference[j] <= high:
            notes.append(
                f"Reference for {name} lies outside the common group range. "
                "Adjusted means extrapolate for at least one group."
            )
    if n < 80:
        notes.append("Modest sample size; inference and interaction tests may be fragile.")

    all_statistics = [
        f_group, p_group, partial_eta, f_interaction, p_interaction,
        float(fitted.rsquared), levene_p,
    ]
    for g in group_rows:
        all_statistics.extend((g.adjusted_mean, g.se, g.ci_low, g.ci_high))
    if not all(math.isfinite(z) for z in all_statistics):
        raise ValueError("ANCOVA/GLM returned non-finite statistics.")

    return AncovaResult(
        outcome=outcome, group=group, covariates=list(covariates),
        mode=mode, reference_values=dict(zip(covariates, map(float, reference))),
        n_total=len(df), n_complete=n, df_group=df_group,
        df_error=df_error, f_group=f_group, p_group=p_group,
        eta_squared_partial=float(partial_eta),
        f_interaction=f_interaction, p_interaction=p_interaction,
        df_interaction=df_interaction, r_squared=float(fitted.rsquared),
        residual_shapiro_p=shapiro_p,
        residual_levene_p=levene_p,
        high_cook_count=high_cook_count,
        groups=group_rows, pairs=pairs,
        plot_group=labels.to_numpy(),
        plot_covariate=main_covariate, plot_outcome=y,
        plot_lines=lines, plot_x=plot_x,
        warnings=notes,
    )
