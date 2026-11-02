"""Copyable APA-style regression summaries, with conditional interpretation."""

from correlation_reporting import apa_p_value


def format_regression_report(result) -> str:
    label = "Simple" if len(result.predictors) == 1 else "Multiple"
    lines = [
        "APA 7-style reporting (researcher review required)",
        f"{label} linear regression: {result.outcome} ~ " + " + ".join(result.predictors),
        f"Complete cases: N = {result.n_complete}/{result.n_total}",
        (
            f"R² = {result.r_squared:.3f}, adjusted R² = "
            f"{result.adjusted_r_squared:.3f}"
        ),
        (
            f"Model F({result.model_df}, {result.residual_df}) = "
            f"{result.f_value:.2f}, {apa_p_value(result.f_p)}."
        ),
        (
            "Coefficient inference uses HC3 robust standard errors "
            "(t-based 95% CI)." if result.robust_hc3 else
            "Coefficient inference uses classical OLS standard errors (95% CI)."
        ),
        "",
        "Coefficient | B | SE | t | p | 95% CI | VIF",
    ]
    for c in result.coefficients:
        lines.append(
            f"{c.name} | {c.b:.3f} | {c.se:.3f} | {c.t:.2f} | "
            f"{apa_p_value(c.p)} | [{c.ci_low:.3f}, {c.ci_high:.3f}] | "
            f"{c.vif:.2f}" if c.vif is not None else
            f"{c.name} | {c.b:.3f} | {c.se:.3f} | {c.t:.2f} | "
            f"{apa_p_value(c.p)} | [{c.ci_low:.3f}, {c.ci_high:.3f}] | —"
        )
    lines.extend([
        "",
        (
            f"Residual Shapiro–Wilk p = {result.shapiro_p:.3f}; "
            f"Breusch–Pagan p = {result.bp_p:.3f}; "
            f"Cook's D > 4/N in {result.high_cook_count} cases."
        ),
        "Notes:",
        *result.warnings,
    ])
    return "\n".join(lines)


def regression_brief(result) -> str:
    phrase = (
        "The fitted model explains "
        f"{100 * result.r_squared:.1f}% of variation in this sample."
    )
    if result.f_p < 0.05:
        return (
            phrase + " The overall classical OLS F test is significant "
            "at .05, but does not establish causality or validate assumptions."
        )
    return (
        phrase + " The overall classical OLS F test is not significant "
        "at .05; this does not prove that the predictors have no association."
    )
