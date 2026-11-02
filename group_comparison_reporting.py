"""APA 7-style reporting for independent-group comparisons."""

from reliability_reporting import apa_coefficient
from correlation_reporting import apa_p_value


def number(value, digits=2):
    """Keep leading zero for unrestricted means, SDs, t, U and g."""
    return f"{value:.{digits}f}"


def format_group_comparison(result) -> str:
    """Report descriptive statistics, the chosen test and limitations."""
    a, b = result.group_a, result.group_b
    lines = [
        "APA 7-style reporting",
        f"Outcome: {result.outcome_name} | Grouping variable: {result.group_name}",
        (
            f"{a}: n = {result.n_a}, M = {number(result.mean_a)}, "
            f"SD = {number(result.sd_a)}, Mdn = {number(result.median_a)}"
        ),
        (
            f"{b}: n = {result.n_b}, M = {number(result.mean_b)}, "
            f"SD = {number(result.sd_b)}, Mdn = {number(result.median_b)}"
        ),
        "",
    ]

    if result.method == "welch":
        lines += [
            (
                f"A two-sided Welch’s independent-samples t test comparing "
                f"{a} and {b} yielded "
                f"t({number(result.degrees_of_freedom)}) = "
                f"{number(result.statistic)}, {apa_p_value(result.p_value)}."
            ),
            (
                f"Mean difference ({a} − {b}) = "
                f"{number(result.mean_difference)}, "
                f"95% CI [{number(result.ci_low)}, {number(result.ci_high)}]."
            ),
            (
                f"Hedges’ g (pooled SD) = {number(result.effect_size)} "
                "(descriptive standardized difference)."
            ),
        ]
    else:
        lines += [
            (
                f"A two-sided Mann–Whitney U test comparing "
                f"{a} and {b} yielded "
                f"U = {number(result.statistic)}, "
                f"{apa_p_value(result.p_value)}."
            ),
            (
                f"Rank-biserial r = {apa_coefficient(result.effect_size)}; "
                "positive values indicate higher ranks in the first group."
            ),
            (
                "This is a rank/distribution comparison, not automatically "
                "a test of medians."
            ),
        ]
    lines += [
        f"p-value method: {result.p_method}.",
        (
            f"Complete cases: {result.n_a + result.n_b}/{result.n_total}; "
            f"{result.n_total - result.n_a - result.n_b} excluded."
        ),
        (
            "At the conventional .05 level, there is evidence against "
            "the respective null hypothesis."
            if result.p_value < 0.05
            else
            "The result is not statistically significant at .05. "
            "This does not prove the groups are equivalent."
        ),
        "Assumptions and practical relevance require researcher review.",
    ]
    return "\n".join(lines)
