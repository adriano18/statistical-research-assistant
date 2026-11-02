"""APA-style display helpers for reliability estimates.

The numerical cutoffs below are common rough conventions, NOT APA 7 rules
and NOT tests of scale validity. Context and measurement purpose matter.
"""

import math


ALPHA_GUIDE = (
    "Interpretive guide (approximate, not an APA 7 standard):\n"
    "α < .60  Low internal consistency\n"
    ".60 ≤ α < .70  Questionable\n"
    ".70 ≤ α < .80  Often considered acceptable\n"
    ".80 ≤ α < .90  Good\n"
    ".90 ≤ α ≤ .95  Very high / excellent\n"
    "α > .95  Very high; check possible item redundancy\n"
    "These are guidelines, not pass/fail validity cutoffs."
)


def apa_coefficient(value: float, decimals: int = 2) -> str:
    """Format an alpha/CI coefficient with APA-style decimal notation."""
    if not math.isfinite(value):
        raise ValueError("Cannot report a non-finite coefficient.")
    value = float(value)
    # Avoid displaying negative zero after rounding.
    if round(value, decimals) == 0:
        value = 0.0
    text = f"{value:.{decimals}f}"
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text


def interpret_alpha(value: float) -> str:
    """Return a tentative description, not a validity judgment."""
    if not math.isfinite(value):
        raise ValueError("Alpha must be finite.")
    if value < 0:
        return "Negative; check item coding and covariances"
    if value < 0.60:
        return "Low"
    if value < 0.70:
        return "Questionable"
    if value < 0.80:
        return "Often acceptable"
    if value < 0.90:
        return "Good"
    if value <= 0.95:
        return "Very high / excellent"
    return "Very high; check possible item redundancy"


def apa_reliability_report(analysis) -> str:
    """Copyable reporting text, followed by item-deletion diagnostics."""
    alpha = apa_coefficient(analysis.alpha)
    low = apa_coefficient(analysis.ci_low)
    high = apa_coefficient(analysis.ci_high)
    k = len(analysis.items)

    lines = [
        "APA 7-style reporting",
        (
            f"Internal consistency for the {k}-item scale was estimated as "
            f"Cronbach’s α = {alpha}, 95% CI [{low}, {high}], "
            f"N = {analysis.n_complete} complete cases."
        ),
        f"Interpretation (guideline only): {interpret_alpha(analysis.alpha)}.",
        (
            f"Data: {analysis.n_total} records, "
            f"{analysis.n_total - analysis.n_complete} excluded for missing item responses."
        ),
        "",
        "α if item deleted (same complete-case sample)",
    ]
    if analysis.alpha_if_deleted:
        for name, score in analysis.alpha_if_deleted.items():
            lines.append(f"{name}: {apa_coefficient(score)}")
    else:
        lines.append("Not available for this selection.")

    return "\n".join(lines)
