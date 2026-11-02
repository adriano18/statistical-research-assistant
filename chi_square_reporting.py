"""APA 7-style text and concise results for categorical associations."""

from correlation_reporting import apa_p_value
from reliability_reporting import apa_coefficient


def summarize_chi_square(result) -> str:
    return (
        f"Pearson χ²({result.df}) = {result.chi2:.2f}\n"
        f"{apa_p_value(result.p_value)}  |  "
        f"Cramér’s V = {apa_coefficient(result.cramers_v)}  |  "
        f"N = {result.n_complete}"
    )


def interpret_chi_square(result) -> str:
    if result.sparse:
        return (
            "Some expected counts are small. The Pearson χ² p-value may not "
            "be trustworthy; review Fisher's exact result where available."
        )
    if result.p_value < 0.05:
        return (
            "An association between the two categorical variables was detected "
            "at the .05 level. This does not establish causality."
        )
    return (
        "No statistically significant association was detected at .05. "
        "This is not evidence that the variables are independent."
    )


def format_chi_square_report(result) -> str:
    lines = [
        "APA 7-style reporting",
        (
            f"A Pearson chi-square test of independence between "
            f"{result.variable_a} and {result.variable_b} yielded "
            f"χ²({result.df}, N = {result.n_complete}) = {result.chi2:.2f}, "
            f"{apa_p_value(result.p_value)}, "
            f"Cramér’s V = {apa_coefficient(result.cramers_v)}."
        ),
        "Observed counts with expected counts in parentheses:",
    ]
    headers = " | ".join(result.column_labels)
    lines.append(f"{result.variable_a} / {result.variable_b} | {headers}")
    for i, name in enumerate(result.row_labels):
        cells = [
            f"{result.observed[i, j]} ({result.expected[i, j]:.2f})"
            for j in range(len(result.column_labels))
        ]
        lines.append(f"{name} | " + " | ".join(cells))
    if result.fisher_p is not None:
        lines.append(
            f"Fisher's exact test (two-sided, 2×2): "
            f"{apa_p_value(result.fisher_p)}."
        )
    lines.append(interpret_chi_square(result))
    lines.append(
        "Complete-case analysis; χ² without Yates' correction. "
        "Categorical measurements and independence require researcher review."
    )
    return "\n".join(lines)
