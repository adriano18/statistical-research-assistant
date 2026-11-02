"""APA 7-style text and concise summaries for three-plus group tests."""

from correlation_reporting import apa_p_value
from reliability_reporting import apa_coefficient


def format_omnibus_summary(result) -> str:
    if result.method == "kruskal":
        stat = f"H({int(result.df1)}) = {result.statistic:.2f}"
    else:
        df2 = f"{result.df2:.2f}" if result.method == "welch" else f"{int(result.df2)}"
        stat = f"F({int(result.df1)}, {df2}) = {result.statistic:.2f}"
    return (
        f"{result.p_method}\n"
        f"{stat}  |  {apa_p_value(result.p_value)}\n"
        f"{result.effect_name} = {apa_coefficient(result.effect_size)}"
        f"  |  N = {result.n_complete}  |  Groups = {len(result.labels)}"
    )


def interpret_omnibus(result) -> str:
    if result.p_value < 0.05:
        return (
            "The overall group-difference test is statistically significant "
            "at .05. This does NOT show which specific groups differ. "
            "Post-hoc comparisons with multiplicity adjustment are needed."
        )
    return (
        "No statistically significant overall group difference was detected "
        "at .05. This does not prove the groups are equivalent."
    )


def format_omnibus_report(result) -> str:
    lines = [
        "APA 7-style reporting",
        f"Outcome: {result.outcome_name} | Grouping variable: {result.group_name}",
        f"Complete cases: {result.n_complete}/{result.n_total}.",
        "",
        "Group descriptives (mean, SD, median):",
    ]
    for name, values in zip(result.labels, result.samples):
        import numpy as np
        lines.append(
            f"{name}: n = {len(values)}, M = {np.mean(values):.2f}, "
            f"SD = {np.std(values, ddof=1):.2f}, Mdn = {np.median(values):.2f}"
        )
    lines += [
        "",
        format_omnibus_summary(result),
        interpret_omnibus(result),
        "",
        "Note. Reported p-values are omnibus results only. "
        "Run the separate post-hoc comparisons for pairwise-adjusted p-values "
        "when group assumptions support that analysis.",
    ]
    return "\n".join(lines)
