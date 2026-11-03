"""APA 7-style logistic model summary with OR confidence intervals."""

from correlation_reporting import apa_p_value


def logistic_main(result) -> str:
    return (
        f"Binary logistic regression | N = {result.n_complete}\n"
        f"Events (1) = {result.events} | Non-events (0) = {result.non_events}\n"
        f"Likelihood-ratio χ²({len(result.predictors)}) = {result.llr:.2f}, "
        f"{apa_p_value(result.llr_p)}\n"
        f"McFadden pseudo-R² = {result.mcfadden_r2:.3f} | "
        f"Training-data ROC AUC = {result.roc_auc:.3f}"
    )


def logistic_brief(result) -> str:
    if result.llr_p < .05:
        conclusion = (
            "The overall logistic model improves the likelihood fit relative "
            "to the intercept-only model at the .05 level."
        )
    else:
        conclusion = (
            "The overall likelihood-ratio test is not significant at .05; "
            "this does not demonstrate that predictors are unrelated to the event."
        )
    return (
        conclusion + " ORs are changes in odds per unit, not risk ratios. "
        "ROC AUC is in-sample only; it must not be treated as validated accuracy."
    )


def format_logistic_report(result) -> str:
    lines = [
        "APA 7-style binary logistic regression (researcher review required)",
        f"Outcome: {result.outcome} (0 = no event, 1 = event)",
        "Quantitative predictors: " + ", ".join(result.predictors),
        f"Complete observations: {result.n_complete}/{result.n_total}",
        f"Events: {result.events}; non-events: {result.non_events}",
        "",
        logistic_main(result),
        f"AIC = {result.aic:.2f}",
        logistic_brief(result),
        "",
        "Coefficients (Wald inference; 95% CI for odds ratio):",
        "Variable | B | SE | z | p | OR | OR 95% CI",
    ]
    for coef in result.coefficients:
        lines.append(
            f"{coef.name} | {coef.b:.3f} | {coef.se:.3f} | "
            f"{coef.z:.2f} | {apa_p_value(coef.p)} | "
            f"{coef.odds_ratio:.3f} | "
            f"[{coef.or_low:.3f}, {coef.or_high:.3f}]"
        )
    lines += [
        "",
        "Note. OR is odds ratio, not risk ratio. McFadden pseudo-R² "
        "is not the same as linear regression R².",
        "ROC AUC comes from the model's training observations and is not "
        "an external validation or a clinical decision rule.",
        "",
        "Assumptions and cautions:",
        *result.warnings,
    ]
    return "\n".join(lines)
