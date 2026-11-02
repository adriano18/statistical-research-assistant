"""One-way ANOVA, Welch ANOVA and Kruskal–Wallis for independent groups."""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


@dataclass
class OmnibusResult:
    group_name: str
    outcome_name: str
    method: str
    labels: list[str]
    samples: list[np.ndarray]
    n_total: int
    n_complete: int
    statistic: float
    df1: float
    df2: float | None
    p_value: float
    effect_name: str
    effect_size: float
    p_method: str
    warnings: list[str]


def recommend_omnibus_test(scale: str, independent: bool) -> str:
    """Offer conditional guidance, not an automatic test selection."""
    if not independent:
        return (
            "This section requires independent groups. Repeated measurements "
            "need repeated-measures ANOVA or Friedman instead."
        )
    if scale == "ordinal":
        return (
            "Kruskal–Wallis is a candidate for ordinal outcomes. "
            "Inspect shapes and ranks; it does not always compare medians."
        )
    if scale == "scale":
        return (
            "For a quantitative outcome, Welch ANOVA is often a useful default "
            "when group variances differ. Ordinary ANOVA additionally assumes "
            "approximately equal variances. Review distributions and outliers."
        )
    return "Confirm ordinal or quantitative outcome measurement first."


def analyze_omnibus(
    df: pd.DataFrame,
    group_name: str,
    outcome_name: str,
    method: str,
    scale: str,
    independent_confirmed: bool = False,
    assumptions_confirmed: bool = False,
) -> OmnibusResult:
    """Compare 3–8 independent groups using complete cases.

    All tests are omnibus: a significant result does NOT locate specific
    pairwise differences. Post-hoc tests require another step.
    """
    if group_name == outcome_name:
        raise ValueError("Choose different grouping and outcome variables.")
    for name in (group_name, outcome_name):
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers cannot be treated as study variables.")
    if not independent_confirmed:
        raise ValueError("Confirm independent participants and group membership.")
    if not assumptions_confirmed:
        raise ValueError("Confirm that you reviewed test assumptions and outliers.")
    if method not in {"anova", "welch", "kruskal"}:
        raise ValueError("Choose ANOVA, Welch ANOVA or Kruskal–Wallis.")
    if scale not in {"scale", "ordinal"}:
        raise ValueError("Confirm an ordinal or quantitative outcome scale.")
    if method in {"anova", "welch"} and scale != "scale":
        raise ValueError("ANOVA methods require a quantitative outcome.")

    original = df[[group_name, outcome_name]]
    numeric = pd.to_numeric(original[outcome_name], errors="coerce")
    if (original[outcome_name].notna() & numeric.isna()).any():
        raise ValueError("The outcome contains non-numeric responses.")
    if not np.isfinite(numeric.dropna().to_numpy(dtype=float)).all():
        raise ValueError("Infinite outcome values are not supported.")

    complete = original.loc[
        original[group_name].notna() & numeric.notna()
    ].copy()
    complete[outcome_name] = numeric.loc[complete.index].astype(float)

    # Do not silently merge different category values such as 1 and "1".
    unique_labels = complete[group_name].unique()
    labels = sorted(str(x) for x in unique_labels)
    k = len(labels)
    if not 3 <= k <= 8 or len(set(labels)) != k:
        raise ValueError("Choose a grouping variable with 3 to 8 distinct groups.")

    group_text = complete[group_name].map(str)
    samples = [
        complete.loc[group_text == label, outcome_name].to_numpy(dtype=float)
        for label in labels
    ]
    ns = np.asarray([len(x) for x in samples], dtype=int)
    if np.min(ns) < 5:
        raise ValueError("At least five complete observations per group are required.")
    n = int(np.sum(ns))
    combined = np.concatenate(samples)
    if np.unique(combined).size < 2:
        raise ValueError("The outcome has no variation.")

    df1 = float(k - 1)
    df2 = None
    means = np.asarray([np.mean(x) for x in samples])
    variances = np.asarray([np.var(x, ddof=1) for x in samples])

    if method == "anova":
        if np.any(variances <= 0):
            raise ValueError("Each ANOVA group needs nonzero within-group variation.")
        test = stats.f_oneway(*samples, equal_var=True)
        statistic, p_value = float(test.statistic), float(test.pvalue)
        df2 = float(n - k)
        p_method = "Classical one-way ANOVA (SciPy, equal variances)"
    elif method == "welch":
        if np.any(variances <= 0):
            raise ValueError("Each Welch group needs nonzero within-group variation.")
        test = stats.f_oneway(*samples, equal_var=False)
        statistic, p_value = float(test.statistic), float(test.pvalue)
        weights = ns / variances
        proportions = weights / weights.sum()
        adjustment = np.sum((1 - proportions) ** 2 / (ns - 1))
        df2 = float((k**2 - 1) / (3 * adjustment))
        p_method = "Welch one-way ANOVA (SciPy, unequal variances)"
    else:
        test = stats.kruskal(*samples)
        statistic, p_value = float(test.statistic), float(test.pvalue)
        p_method = "Tie-corrected Kruskal–Wallis H (SciPy asymptotic p-value)"

    if method in {"anova", "welch"}:
        grand_mean = float(np.mean(combined))
        ss_between = float(np.sum(ns * (means - grand_mean) ** 2))
        ss_total = float(np.sum((combined - grand_mean) ** 2))
        effect_name = "Descriptive η²"
        effect = ss_between / ss_total if ss_total > 0 else float("nan")
    else:
        # Conventional nonnegative rank-based epsilon-squared estimate.
        effect_name = "Rank ε² (truncated at 0)"
        effect = max(0.0, (statistic - k + 1) / (n - k))

    numbers = [statistic, p_value, effect, df1]
    if df2 is not None:
        numbers.append(df2)
    if not all(math.isfinite(v) for v in numbers):
        raise ValueError("The test could not produce finite results.")

    warnings = [
        "These are omnibus tests; even a significant p-value does not identify which groups differ.",
        "Independence, outcome scale, sampling design and influential outliers need review.",
        "Post-hoc comparisons are separate; use the dedicated button to calculate adjusted pairwise p-values.",
        "Association or group differences do not establish causality.",
    ]
    if n < len(df):
        warnings.append(
            f"Excluded {len(df) - n} records missing a group or outcome."
        )
    if np.min(ns) < 10:
        warnings.append("Small groups can make estimates and assumptions fragile.")
    if method == "anova":
        warnings.append(
            "Classical ANOVA assumes appropriate residual distributions and "
            "approximately equal variances across groups."
        )
    elif method == "welch":
        warnings.append(
            "Welch adjusts for unequal variances, but does not eliminate "
            "concerns about extreme outliers or markedly nonnormal small samples."
        )
        warnings.append(
            "η² is descriptive between-group variation, NOT an effect size "
            "derived from the Welch-weighted F statistic."
        )
    else:
        warnings.append(
            "Kruskal–Wallis tests rank/distribution differences; interpreting "
            "it as a test of medians requires additional distributional conditions."
        )
        warnings.append(
            "Its p-value uses a chi-square approximation; group sizes should "
            "not be too small."
        )

    return OmnibusResult(
        group_name=group_name,
        outcome_name=outcome_name,
        method=method,
        labels=labels,
        samples=samples,
        n_total=len(df),
        n_complete=n,
        statistic=statistic,
        df1=df1,
        df2=df2,
        p_value=p_value,
        effect_name=effect_name,
        effect_size=float(effect),
        p_method=p_method,
        warnings=warnings,
    )
