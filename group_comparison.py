"""Two independent-group comparisons with explicit assumptions and safeguards."""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


@dataclass
class GroupComparisonResult:
    group_name: str
    outcome_name: str
    group_a: str
    group_b: str
    method: str
    n_total: int
    n_a: int
    n_b: int
    mean_a: float
    mean_b: float
    sd_a: float
    sd_b: float
    median_a: float
    median_b: float
    statistic: float
    degrees_of_freedom: float | None
    p_value: float
    effect_name: str
    effect_size: float
    mean_difference: float | None
    ci_low: float | None
    ci_high: float | None
    p_method: str
    warnings: list[str]
    values_a: np.ndarray
    values_b: np.ndarray


def recommend_group_test(outcome_scale: str, independent: bool) -> str:
    """Explain candidate methods without claiming automatic assumption checking."""
    if not independent:
        return (
            "This section only supports two independent groups. "
            "Paired or repeated measurements need a different test."
        )
    if outcome_scale == "ordinal":
        return (
            "Mann–Whitney U is a candidate for two independent groups with "
            "ordinal outcomes. It compares ranks/distributions, not always medians."
        )
    if outcome_scale == "scale":
        return (
            "Welch’s t is a default candidate for two independent groups "
            "with a quantitative outcome when mean-based inference is appropriate. "
            "Review distributions, outliers and independence first. "
            "Mann–Whitney U answers a different rank-based question."
        )
    return "Confirm an ordinal or quantitative outcome scale first."


def compare_independent_groups(
    df: pd.DataFrame,
    group_name: str,
    outcome_name: str,
    method: str,
    outcome_scale: str,
    independent_checked: bool = False,
    assumptions_checked: bool = False,
) -> GroupComparisonResult:
    """Compare exactly two independent groups; drop rows missing either value."""
    if group_name == outcome_name:
        raise ValueError("Choose separate grouping and outcome variables.")
    for name in (group_name, outcome_name):
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers cannot be used as grouping or outcome variables.")
    if not independent_checked:
        raise ValueError("Confirm that the observations belong to independent groups.")
    if method not in {"welch", "mannwhitney"}:
        raise ValueError("Choose Welch’s t test or Mann–Whitney U.")
    if outcome_scale not in {"ordinal", "scale"}:
        raise ValueError("Confirm an ordinal or quantitative outcome scale.")
    if method == "welch":
        if outcome_scale != "scale":
            raise ValueError("Welch’s t test requires a quantitative outcome.")
        if not assumptions_checked:
            raise ValueError("Confirm review of distributions and influential outliers.")

    original = df[[group_name, outcome_name]].copy()
    numeric = pd.to_numeric(original[outcome_name], errors="coerce")
    if (original[outcome_name].notna() & numeric.isna()).any():
        raise ValueError("The outcome contains non-numeric responses.")
    nonmissing = numeric.dropna().to_numpy(dtype=float)
    if not np.isfinite(nonmissing).all():
        raise ValueError("Infinite outcome values are not supported.")

    # Keep exactly observed labels; do not silently merge/rename categories.
    complete = original.loc[
        original[group_name].notna() & numeric.notna()
    ].copy()
    complete[outcome_name] = numeric.loc[complete.index].astype(float)
    labels = sorted(str(v) for v in complete[group_name].unique())
    if len(labels) != 2:
        raise ValueError(
            "Exactly two non-empty groups with complete outcome data are required."
        )
    label_a, label_b = labels
    a = complete.loc[
        complete[group_name].map(str) == label_a, outcome_name
    ].to_numpy(dtype=float)
    b = complete.loc[
        complete[group_name].map(str) == label_b, outcome_name
    ].to_numpy(dtype=float)
    if len(a) < 3 or len(b) < 3:
        raise ValueError("At least three observations per group are required.")
    if np.unique(np.concatenate([a, b])).size < 2:
        raise ValueError("The outcome has no variation.")

    if method == "welch":
        res = stats.ttest_ind(a, b, equal_var=False, alternative="two-sided")
        statistic = float(res.statistic)
        p_value = float(res.pvalue)
        df_value = float(res.df)
        interval = res.confidence_interval(confidence_level=0.95)
        ci_low, ci_high = float(interval.low), float(interval.high)
        mean_difference = float(np.mean(a) - np.mean(b))
        # Pooled-SD standardized difference, with small-sample correction.
        pooled_var = (
            ((len(a) - 1) * np.var(a, ddof=1))
            + ((len(b) - 1) * np.var(b, ddof=1))
        ) / (len(a) + len(b) - 2)
        effect_size = (
            (mean_difference / math.sqrt(pooled_var))
            * (1 - 3 / (4 * (len(a) + len(b)) - 9))
            if pooled_var > 0 else math.nan
        )
        effect_name = "Hedges’ g (pooled-SD)"
        p_method = "Welch unequal-variance t test (two-sided, SciPy)"
    else:
        # SciPy's exact method does not account for ties. Use its
        # tie-corrected asymptotic method when repeated ranks are present.
        pooled = np.concatenate([a, b])
        ties = np.unique(pooled).size < len(pooled)
        calculation = (
            "asymptotic" if ties or min(len(a), len(b)) > 8 else "exact"
        )
        res = stats.mannwhitneyu(
            a, b, alternative="two-sided", method=calculation
        )
        statistic = float(res.statistic)
        p_value = float(res.pvalue)
        # Positive means group A tends to have higher ranks than group B.
        effect_size = 2 * statistic / (len(a) * len(b)) - 1
        effect_name = "Rank-biserial r"
        df_value = mean_difference = ci_low = ci_high = None
        p_method = (
            f"Two-sided Mann–Whitney U ({calculation}"
            f"{', tie-corrected' if ties else ''}, SciPy)"
        )

    values_to_check = [statistic, p_value, effect_size]
    if method == "welch":
        values_to_check.extend(
            [df_value, mean_difference, ci_low, ci_high]
        )
    if not all(math.isfinite(v) for v in values_to_check):
        raise ValueError(
            "The test could not produce finite estimates; "
            "check whether both groups have enough variation."
        )

    excluded = len(df) - len(complete)
    warnings = [
        "The result assumes independent observations and an appropriate sampling design.",
        "Statistical significance does not establish causation or practical importance.",
        "Confirm the outcome scale, group coding, and possible influential outliers.",
    ]
    if excluded:
        warnings.append(
            f"Excluded {excluded} records missing a group or outcome value."
        )
    if min(len(a), len(b)) < 10:
        warnings.append(
            "A small group can make estimates and p-values unstable."
        )
    if method == "welch":
        warnings.append(
            "Welch tests group means. Normality of residuals is especially "
            "relevant in small samples; a checkbox does not verify it."
        )
        warnings.append(
            "Hedges’ g is standardized using a pooled SD and is descriptive; "
            "its interpretation may be awkward if group variances differ strongly."
        )
    else:
        warnings.append(
            "Mann–Whitney U tests rank/distribution differences; it is "
            "not generally a test of median differences unless shapes are comparable."
        )
        warnings.append(
            "No confidence interval for the rank-biserial effect is reported "
            "in this version."
        )

    return GroupComparisonResult(
        group_name=group_name,
        outcome_name=outcome_name,
        group_a=label_a,
        group_b=label_b,
        method=method,
        n_total=len(df),
        n_a=len(a),
        n_b=len(b),
        mean_a=float(np.mean(a)),
        mean_b=float(np.mean(b)),
        sd_a=float(np.std(a, ddof=1)),
        sd_b=float(np.std(b, ddof=1)),
        median_a=float(np.median(a)),
        median_b=float(np.median(b)),
        statistic=statistic,
        degrees_of_freedom=df_value,
        p_value=p_value,
        effect_name=effect_name,
        effect_size=float(effect_size),
        mean_difference=mean_difference,
        ci_low=ci_low,
        ci_high=ci_high,
        p_method=p_method,
        warnings=warnings,
        values_a=a,
        values_b=b,
    )
