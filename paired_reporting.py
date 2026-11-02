"""APA 7-style text for within-participant comparisons."""

from correlation_reporting import apa_p_value
from reliability_reporting import apa_coefficient


def format_paired_report(result) -> str:
    """Keep leading zero for t, W, means, SDs, and Cohen's dz."""
    b, a = result.before_name, result.after_name
    lines = [
        "APA 7-style reporting",
        f"Repeated measurements: {b} → {a}",
        (
            f"Before: M = {result.before_mean:.2f}, "
            f"SD = {result.before_sd:.2f}, Mdn = {result.before_median:.2f}"
        ),
        (
            f"After: M = {result.after_mean:.2f}, "
            f"SD = {result.after_sd:.2f}, Mdn = {result.after_median:.2f}"
        ),
        f"Complete pairs: {result.n_complete}/{result.n_total}.",
        "",
    ]
    if result.method == "paired_t":
        lines += [
            (
                f"A two-sided paired-samples t-test found "
                f"t({result.df:.0f}) = {result.statistic:.2f}, "
                f"{apa_p_value(result.p_value)}."
            ),
            (
                f"Mean change (after − before) = {result.mean_change:.2f}, "
                f"95% CI [{result.ci_low:.2f}, {result.ci_high:.2f}]."
            ),
            f"Cohen’s dz = {result.effect_size:.2f}.",
        ]
    else:
        lines += [
            (
                f"A two-sided Wilcoxon signed-rank test yielded "
                f"W = {result.statistic:.2f}, {apa_p_value(result.p_value)}."
            ),
            (
                f"Median paired change (after − before) = "
                f"{result.median_change:.2f} (descriptive)."
            ),
            (
                f"Matched-pairs rank-biserial r = "
                f"{apa_coefficient(result.effect_size)}."
            ),
            f"Unchanged pairs: {result.n_unchanged} (removed from ranks).",
        ]
    lines += [
        f"Test method: {result.p_method}.",
        (
            "Result is statistically significant at .05 under the test assumptions."
            if result.p_value < 0.05
            else "Result is not significant at .05; this does not establish equivalence."
        ),
        "Design, assumptions and practical meaning need independent review.",
    ]
    return "\n".join(lines)
