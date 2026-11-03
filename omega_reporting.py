"""Researcher-reviewed APA-style reporting for one-factor omega and items."""

from reliability_reporting import apa_coefficient


def format_omega_report(result, ci=None) -> str:
    lines = [
        "APA 7-style scale reliability / item analysis (researcher review required)",
        f"Selected items: {len(result.items)} | "
        f"N = {result.n_complete}/{result.n_total} listwise complete cases",
        (
            "One-factor standardized McDonald’s ω = "
            f"{apa_coefficient(result.omega)} "
            "(maximum-likelihood Pearson factor model)."
        ),
        (
            f"First/second eigenvalues = {result.first_eigenvalue:.2f} / "
            f"{result.second_eigenvalue:.2f}; "
            "largest residual Pearson correlation magnitude = "
            f"{result.largest_residual_corr:.3f}."
        ),
        "This does not test or confirm unidimensionality or validity.",
        (
            f"95% bootstrap percentile CI [{apa_coefficient(ci.lower)}, "
            f"{apa_coefficient(ci.upper)}] "
            f"({ci.successful}/{ci.requested} valid case-resampling refits; "
            f"seed {ci.seed})."
            if ci else
            "No confidence interval calculated (bootstrap optional)."
        ),
        "",
        "Item diagnostics (on the same complete-case participants):",
        "Item | M | SD | Missing (all rows) | Unique | Corrected item-rest r | Spearman item-rest ρ | "
        "Standardized loading | Uniqueness",
    ]
    for item in result.diagnostics:
        lines.append(
            f"{item.name} | {item.mean:.2f} | {item.sd:.2f} | "
            f"{item.missing} | {item.unique_answers} | "
            f"{apa_coefficient(item.corrected_item_rest_r)} | "
            f"{apa_coefficient(item.rank_item_rest_r)} | "
            f"{apa_coefficient(item.standardized_loading)} | "
            f"{apa_coefficient(item.uniqueness)}"
        )
    lines.extend([
        "",
        "Assumptions and cautions:",
        *result.warnings,
    ])
    return "\n".join(lines)


def omega_summary(result, ci=None) -> str:
    return (
        f"McDonald’s ω = {apa_coefficient(result.omega)} | "
        f"Complete N = {result.n_complete}/{result.n_total} | "
        f"Items = {len(result.items)}\n"
        + (f"95% bootstrap CI [{apa_coefficient(ci.lower)}, "
           f"{apa_coefficient(ci.upper)}], "
           f"{ci.successful}/{ci.requested} successful refits.\n"
           if ci else "Bootstrap CI not requested.\n")
        "Standardized one-factor internal-consistency estimate, "
        "NOT evidence of validity or confirmed unidimensionality."
    )
