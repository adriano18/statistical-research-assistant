"""Readable, APA 7-style pairwise comparison tables."""

from correlation_reporting import apa_p_value


def format_posthoc_report(result) -> str:
    lines = [
        f"Post-hoc comparisons: {result.method}",
        (
            "Familywise-adjusted p-values; all pairwise group comparisons "
            f"for the {result.omnibus_method} omnibus analysis."
        ),
    ]
    if result.omnibus_method == "kruskal":
        lines.append(
            "Groups | Mean-rank difference (first − second) | z | "
            "Unadjusted p | Holm-adjusted p"
        )
        for pair in result.pairs:
            lines.append(
                f"{pair.first} – {pair.second} | {pair.estimate:+.2f} | "
                f"{pair.statistic:.2f} | "
                f"{apa_p_value(pair.p_raw)} | "
                f"{apa_p_value(pair.p_adjusted)}"
            )
    else:
        lines.append(
            "Groups | Mean difference (first − second) | "
            "95% simultaneous CI | Adjusted p"
        )
        for pair in result.pairs:
            lines.append(
                f"{pair.first} – {pair.second} | {pair.estimate:+.2f} | "
                f"[{pair.ci_low:.2f}, {pair.ci_high:.2f}] | "
                f"{apa_p_value(pair.p_adjusted)}"
            )

    lines.extend([
        "",
        (
            f"{sum(p.p_adjusted < 0.05 for p in result.pairs)} of "
            f"{len(result.pairs)} group pairs have adjusted p < .05."
        ),
        "Interpret differences in their scientific context; p-values are not effect sizes.",
    ])
    return "\n".join(lines)
