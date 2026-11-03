"""Concise and APA-style output for Gaussian ANCOVA / interaction GLM."""

from correlation_reporting import apa_p_value


def ancova_main(result) -> str:
    method = (
        "ANCOVA (common slopes)" if result.mode == "ancova"
        else "Interaction GLM (conditional group effect)"
    )
    return (
        f"{method} | Complete N = {result.n_complete}/{result.n_total}\n"
        f"Group F({result.df_group}, {result.df_error}) = "
        f"{result.f_group:.2f}, {apa_p_value(result.p_group)}\n"
        f"Partial η² = {result.eta_squared_partial:.3f} | "
        f"R² = {result.r_squared:.3f}\n"
        f"Joint slope-interaction F({result.df_interaction}, "
        f"{result.n_complete - (len(result.groups) * (len(result.covariates) + 1))}) "
        f"= {result.f_interaction:.2f}, {apa_p_value(result.p_interaction)}"
    )


def ancova_brief(result) -> str:
    if result.mode == "interaction":
        scope = (
            "The group comparison is CONDITIONAL on the reported covariate "
            "reference values; it is not a constant group effect across all scores. "
        )
    else:
        scope = (
            "This adjusted comparison assumes common regression slopes; "
            "a nonsignificant interaction check does not prove them parallel. "
        )
    if result.p_group < .05:
        return (
            "There is evidence of a group difference at the covariate "
            "reference values at .05. " + scope +
            "Inspect Holm-adjusted pairs and the scientific design. "
            "This does not establish causality."
        )
    return (
        "No statistically significant group difference was detected at "
        "the reference covariate values at .05. " + scope +
        "This does not establish group equivalence."
    )


def format_ancova_report(result) -> str:
    lines = [
        "APA 7-style Gaussian general linear model (researcher review required)",
        "Method: " + (
            "ANCOVA with common covariate slopes" if result.mode == "ancova"
            else "Group-by-covariate interaction GLM"
        ),
        f"Outcome: {result.outcome} | Group factor: {result.group}",
        "Quantitative covariates: " + ", ".join(result.covariates),
        f"Complete cases: {result.n_complete}/{result.n_total}",
        "",
        "Covariate reference values (complete-case grand means):",
        *[
            f"{name} = {reference:.2f}"
            for name, reference in result.reference_values.items()
        ],
        "",
        ancova_main(result),
        ancova_brief(result),
        "",
        "Adjusted group means (at the covariate reference):",
        "Group | N | Raw mean | Adjusted mean | SE | Individual 95% CI",
    ]
    for g in result.groups:
        lines.append(
            f"{g.label} | {g.n} | {g.raw_mean:.2f} | "
            f"{g.adjusted_mean:.2f} | {g.se:.2f} | "
            f"[{g.ci_low:.2f}, {g.ci_high:.2f}]"
        )
    lines += [
        "",
        "Adjusted mean comparisons (second − first):",
        "Pair | Difference | t | Raw p | Holm-adjusted p | Unadjusted 95% CI",
    ]
    for p in result.pairs:
        lines.append(
            f"{p.first} → {p.second} | {p.difference:+.2f} | "
            f"{p.t:.2f} | {apa_p_value(p.p_raw)} | "
            f"{apa_p_value(p.p_holm)} | "
            f"[{p.ci_low:.2f}, {p.ci_high:.2f}]"
        )
    lines.extend([
        "",
        (
            f"Residual Shapiro–Wilk p = {result.residual_shapiro_p:.3f}; "
            f"median-centered Levene p = {result.residual_levene_p:.3f}; "
            f"{result.high_cook_count} observations have Cook's D > 4/N."
        ),
        "Assumptions and limitations:",
        *result.warnings,
    ])
    return "\n".join(lines)
