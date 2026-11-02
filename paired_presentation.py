"""Short companion summaries for paired tests (APA report stays separate)."""

from correlation_reporting import apa_p_value
from reliability_reporting import apa_coefficient


def paired_main_result(result) -> str:
    if result.method == "paired_t":
        return (
            f"Paired t-test | t({result.df:.0f}) = {result.statistic:.2f}\n"
            f"{apa_p_value(result.p_value)}  |  Cohen’s dz = "
            f"{result.effect_size:.2f}  |  N = {result.n_complete}\n"
            f"95% CI for mean change "
            f"[{result.ci_low:.2f}, {result.ci_high:.2f}]"
        )
    return (
        f"Wilcoxon signed-rank | W = {result.statistic:.2f}\n"
        f"{apa_p_value(result.p_value)}  |  Matched-pairs rank-biserial "
        f"r = {apa_coefficient(result.effect_size)}  |  "
        f"N = {result.n_complete}"
    )


def paired_descriptives(result) -> str:
    return (
        f"Before: M = {result.before_mean:.2f}, SD = {result.before_sd:.2f}, "
        f"Mdn = {result.before_median:.2f}\n"
        f"After:  M = {result.after_mean:.2f}, SD = {result.after_sd:.2f}, "
        f"Mdn = {result.after_median:.2f}\n"
        f"Mean change (after − before) = {result.mean_change:+.2f}; "
        f"median paired change = {result.median_change:+.2f}"
    )


def paired_interpretation(result) -> str:
    if result.p_value >= 0.05:
        return (
            "No statistically significant paired change detected at .05. "
            "This does not demonstrate equivalence or absence of change."
        )
    direction = "decrease" if result.mean_change < 0 else "increase"
    if result.method == "paired_t":
        return (
            f"Statistically significant {direction} in mean scores "
            "(after versus before), under the paired t-test assumptions. "
            "This does not establish causation."
        )
    if result.effect_size == 0:
        return (
            "Wilcoxon detected a signed-rank difference, but its direction "
            "is unclear. Review individual changes and the distribution."
        )
    rank_direction = "lower" if result.effect_size < 0 else "higher"
    return (
        f"Wilcoxon detected a statistically significant shift toward "
        f"{rank_direction} after-scores under the signed-rank assumptions. "
        "This is not automatically a test of mean or median change."
    )
