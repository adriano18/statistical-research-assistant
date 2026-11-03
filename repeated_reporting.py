"""APA-style summary of one-factor repeated measures and Holm pairwise tests."""

import numpy as np

from correlation_reporting import apa_p_value


def repeated_main(result) -> str:
    if result.method == "friedman":
        return (
            f"Friedman χ²({int(result.df1)}, N = {result.n_complete}) "
            f"= {result.statistic:.2f}, {apa_p_value(result.p_primary)}\n"
            f"Kendall’s W = {result.effect_size:.3f} | "
            f"Occasions = {len(result.columns)}"
        )
    return (
        f"Repeated-measures ANOVA F({result.df1 * result.epsilon_gg:.2f}, "
        f"{result.df2 * result.epsilon_gg:.2f}) = {result.statistic:.2f}, "
        f"{apa_p_value(result.p_primary)} [Greenhouse–Geisser]\n"
        f"Uncorrected F({int(result.df1)}, {int(result.df2)}) "
        f"p = {result.p_uncorrected:.4f}; "
        f"εGG = {result.epsilon_gg:.3f}, partial η² = {result.effect_size:.3f}"
    )


def repeated_brief(result) -> str:
    if result.p_primary < 0.05:
        return (
            "An overall change across the repeated occasions was detected "
            "at .05 under the selected test assumptions. Inspect Holm-adjusted "
            "pairwise tests to locate differences. Causation is not established."
        )
    return (
        "No significant overall change was detected at .05. "
        "This does not establish that the occasions are equivalent."
    )


def format_repeated_report(result) -> str:
    lines = [
        "APA 7-style repeated-measures summary (researcher review required)",
        (
            "Method: Friedman (ordinal/rank-based)"
            if result.method == "friedman" else
            "Method: One-factor repeated-measures ANOVA"
        ),
        f"Complete participants N = {result.n_complete}/{result.n_total}",
        "",
        "Occasion descriptives:",
    ]
    for i, name in enumerate(result.columns):
        arr = result.values[:, i]
        lines.append(
            f"{name}: M = {np.mean(arr):.2f}, SD = {np.std(arr, ddof=1):.2f}, "
            f"Mdn = {np.median(arr):.2f}"
        )
    lines.extend([
        "", repeated_main(result), repeated_brief(result), "",
        "Pairwise comparisons (after − before; two-sided, Holm-adjusted):"
    ])
    if result.method == "friedman":
        lines.append(
            "Pair | Median paired change | W | Raw p | Adjusted p | Rank-biserial r"
        )
    else:
        lines.append(
            "Pair | Mean paired change | t | Raw p | Adjusted p | Cohen’s dz"
        )
    for p in result.pairs:
        stat = f"{p.statistic:.2f}" if p.statistic is not None else "N/A"
        effect = f"{p.effect_size:+.3f}" if p.effect_size is not None else "N/A"
        lines.append(
            f"{p.before} → {p.after} | {p.estimate:+.2f} | {stat} | "
            f"{apa_p_value(p.p_raw)} | {apa_p_value(p.p_holm)} | {effect}"
        )
    lines.extend(["", "Assumptions and cautions:", *result.warnings])
    return "\n".join(lines)
