"""Human-readable correlation reporting with APA 7-style notation."""

from reliability_reporting import apa_coefficient


def apa_p_value(value: float) -> str:
    """APA-style p value with three decimals, or < .001."""
    if not 0 <= value <= 1:
        raise ValueError("p-value must be in [0, 1].")
    if value < 0.001:
        return "p < .001"
    text = f"{value:.3f}"
    if text.startswith("0."):
        text = text[1:]
    return f"p = {text}"


def format_correlation_report(result) -> str:
    symbol = "r" if result.method == "pearson" else "ρ"
    title = "Pearson" if result.method == "pearson" else "Spearman"
    coeff = apa_coefficient(result.coefficient)
    direction = (
        "positive" if result.coefficient > 0
        else "negative" if result.coefficient < 0
        else "no observed"
    )
    ci_text = ""
    if result.ci_low is not None and result.ci_high is not None:
        ci_text = (
            f", 95% CI [{apa_coefficient(result.ci_low)}, "
            f"{apa_coefficient(result.ci_high)}]"
        )
    lines = [
        "APA 7-style reporting",
        (
            f"A two-sided {title} correlation between {result.x_name} and "
            f"{result.y_name} was {direction} "
            f"({symbol} = {coeff}{ci_text}, "
            f"{apa_p_value(result.p_value)}, N = {result.n_complete})."
        ),
        f"Method for p-value: {result.p_method}.",
        (
            f"Paired observations: {result.n_complete}/{result.n_total}; "
            f"{result.n_total - result.n_complete} omitted for missing values."
        ),
    ]
    if result.method == "spearman":
        lines.append(
            "No confidence interval for Spearman’s ρ is reported in this version."
        )
    if result.p_value < 0.05:
        lines.append(
            "At the conventional .05 level, the result provides evidence "
            "against zero association under the chosen test assumptions."
        )
    else:
        lines.append(
            "At the conventional .05 level, the result is not statistically "
            "significant. This is not proof of no association."
        )
    lines.append(
        "Interpretation: the coefficient describes association, not causation. "
        "Magnitude and practical meaning depend on research context."
    )
    return "\n".join(lines)
