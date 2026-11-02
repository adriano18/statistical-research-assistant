"""Exploratory boxplots and careful diagnostic checks for quantitative data."""

from dataclasses import dataclass
from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


@dataclass
class ExploreResult:
    variable: str
    group: str | None
    labels: list[str]
    samples: list[np.ndarray]
    n_total: int
    n_complete: int
    shapiro_w: float | None
    shapiro_p: float | None
    levene_w: float | None
    levene_p: float | None
    warnings: list[str]


def explore_quantitative(
    df: pd.DataFrame, variable: str, group: str | None = None
) -> ExploreResult:
    """Show Q–Q, boxplot, and descriptive assumption checks.

    Normality of a whole outcome is NOT the same assumption as normality of
    ANOVA residuals or paired difference scores. This is an exploratory aid.
    """
    if variable not in df.columns:
        raise ValueError("Unknown quantitative variable.")
    if looks_like_identifier(variable):
        raise ValueError("Identifiers are not measurements.")
    if group and group not in df.columns:
        raise ValueError("Unknown grouping variable.")
    if group and (group == variable or looks_like_identifier(group)):
        raise ValueError("Choose a distinct grouping variable, not an identifier.")

    original = df[variable]
    numeric = pd.to_numeric(original, errors="coerce")
    if (original.notna() & numeric.isna()).any():
        raise ValueError("The selected outcome contains non-numeric values.")
    if not np.isfinite(numeric.dropna().to_numpy(dtype=float)).all():
        raise ValueError("Infinite values are not supported.")

    good = numeric.notna()
    if group:
        good &= df[group].notna()
    valid = df.loc[good].copy()
    valid[variable] = numeric.loc[good].astype(float)

    if len(valid) < 5:
        raise ValueError("At least five valid observations are required.")

    if group:
        label_source = valid[group].map(str)
        labels = sorted(label_source.unique().tolist())
        if not 2 <= len(labels) <= 8:
            raise ValueError("Select a grouping variable with 2–8 groups.")
        samples = [
            valid.loc[label_source == name, variable].to_numpy(dtype=float)
            for name in labels
        ]
        if any(len(arr) < 3 for arr in samples):
            raise ValueError("Each group needs at least three observations.")
    else:
        labels = ["All observations"]
        samples = [valid[variable].to_numpy(dtype=float)]

    if all(np.unique(x).size < 2 for x in samples):
        raise ValueError("The selected outcome has no variation.")

    # Shapiro is useful for small samples, but a binary pass/fail test of
    # normality is not sufficient to choose inferential procedures.
    # For grouped data, it is applied to deviations from group means.
    if group:
        residuals = np.concatenate([x - x.mean() for x in samples])
    else:
        residuals = samples[0]
    shapiro_w = shapiro_p = None
    warnings = [
        "Visual checks and study design matter more than a single p-value.",
        "A nonsignificant Shapiro result does not prove normality.",
        "For paired tests examine WITHIN-PARTICIPANT difference scores separately.",
    ]
    if len(residuals) >= 3 and np.unique(residuals).size > 1:
        shapiro = stats.shapiro(residuals)
        shapiro_w, shapiro_p = float(shapiro.statistic), float(shapiro.pvalue)
        if len(residuals) > 5000:
            warnings.append(
                "Shapiro p-value may be inaccurate for more than 5,000 values."
            )
    else:
        warnings.append("Shapiro–Wilk cannot be evaluated on constant values.")
    if group:
        warnings.append(
            "Shapiro–Wilk here uses group-mean-centered residuals "
            "as an exploratory check; dependence and design assumptions remain."
        )

    levene_w = levene_p = None
    if group:
        result = stats.levene(*samples, center="median")
        if np.isfinite(result.statistic) and np.isfinite(result.pvalue):
            levene_w, levene_p = float(result.statistic), float(result.pvalue)
        else:
            warnings.append("Brown–Forsythe/Levene could not be calculated.")
        warnings.append(
            "Median-centered Levene (Brown–Forsythe) checks group spread; "
            "nonsignificance does not establish equal variances."
        )

    if len(valid) < len(df):
        warnings.append(
            f"Excluded {len(df) - len(valid)} rows missing the outcome or group."
        )
    return ExploreResult(
        variable=variable, group=group,
        labels=labels, samples=samples,
        n_total=len(df), n_complete=len(valid),
        shapiro_w=shapiro_w, shapiro_p=shapiro_p,
        levene_w=levene_w, levene_p=levene_p,
        warnings=warnings,
    )


def format_explore_report(result: ExploreResult) -> str:
    lines = [
        "Exploratory diagnostics (not automatic test selection)",
        f"Variable: {result.variable}",
        f"Grouping: {result.group or 'none'}",
        f"Complete observations: {result.n_complete}/{result.n_total}",
        "",
        "Descriptive statistics:",
    ]
    for label, values in zip(result.labels, result.samples):
        lines.append(
            f"{label}: n = {len(values)}, M = {np.mean(values):.2f}, "
            f"SD = {np.std(values, ddof=1):.2f}, "
            f"Mdn = {np.median(values):.2f}, "
            f"IQR = {np.percentile(values, 75) - np.percentile(values, 25):.2f}"
        )
    if result.shapiro_w is not None:
        lines.append(
            f"Shapiro–Wilk W = {result.shapiro_w:.3f}, "
            f"p = {result.shapiro_p:.3f}"
        )
    if result.levene_w is not None:
        lines.append(
            f"Median-centered Levene (Brown–Forsythe) = "
            f"{result.levene_w:.3f}, p = {result.levene_p:.3f}"
        )
    lines.append("")
    lines.extend(result.warnings)
    return "\n".join(lines)


def make_explore_chart(result: ExploreResult) -> bytes:
    """Two-panel chart: group boxplots + normal Q–Q of pooled residuals."""
    fig, (box_ax, qq_ax) = plt.subplots(1, 2, figsize=(11.4, 5.2))
    try:
        rng = np.random.default_rng(2026)
        box_ax.boxplot(
            result.samples, tick_labels=result.labels,
            showfliers=True, patch_artist=False,
        )
        for pos, values in enumerate(result.samples, 1):
            x = pos + rng.uniform(-0.10, 0.10, len(values))
            box_ax.scatter(x, values, alpha=0.55, s=18)
        box_ax.set_title("Boxplot and individual observations")
        box_ax.set_ylabel(result.variable)
        box_ax.tick_params(axis="x", labelrotation=20)

        residuals = np.concatenate([
            s - s.mean() for s in result.samples
        ]) if result.group else result.samples[0]
        stats.probplot(residuals, dist="norm", plot=qq_ax)
        qq_ax.set_title("Normal Q–Q plot")
        qq_ax.set_ylabel("Observed values / residuals")

        fig.text(0.05, 0.98, "Figure 8", weight="bold", fontsize=11, va="top")
        fig.text(
            0.05, 0.937, "Exploratory Boxplots and Distribution Diagnostics",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. Boxplots show medians, IQR, whiskers and outliers. Q–Q compares "
            "the outcome (or group-mean-centered residuals) with a normal distribution. "
            "These diagnostics do not validate a statistical model by themselves."
        )
        fig.text(
            0.05, 0.035, textwrap.fill(note, 125),
            fontsize=8.1, va="bottom",
        )
        fig.tight_layout(rect=(0.02, 0.11, 0.98, 0.86))
        buff = BytesIO()
        fig.savefig(buff, format="png", dpi=115)
        return buff.getvalue()
    finally:
        plt.close(fig)
