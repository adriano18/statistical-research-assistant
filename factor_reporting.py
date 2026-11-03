"""Concise APA-style PCA and principal-axis EFA output."""

from correlation_reporting import apa_p_value


def factor_main(result) -> str:
    method = (
        "Principal component analysis (PCA)"
        if result.method == "pca"
        else "Principal-axis exploratory factor analysis (EFA)"
    )
    return (
        f"{method} | Complete N = {result.n_complete}/{result.n_total}\n"
        f"Items = {len(result.items)} | Retained = {result.n_components}\n"
        f"KMO = {result.kmo:.3f} | "
        f"Bartlett χ²({result.bartlett_df}) = "
        f"{result.bartlett_chi2:.2f}, {apa_p_value(result.bartlett_p)}\n"
        f"PCA parallel-analysis heuristic: {result.parallel_count} "
        "eigenvalue(s) exceed simulated 95th percentiles."
    )


def format_factor_report(result) -> str:
    heading = (
        "Exploratory PCA on Pearson correlation matrix"
        if result.method == "pca"
        else "Exploratory principal-axis common factor analysis "
             f"({result.rotation} rotation)"
    )
    rows = [
        "APA-style exploratory factor/component report (researcher review required)",
        heading,
        f"Complete observations N = {result.n_complete}/{result.n_total}",
        f"Variables ({len(result.items)}): " + ", ".join(result.items),
        factor_main(result),
        "",
        "Correlation matrix eigenvalues / simulated 95th percentiles:",
    ]
    for i, (eigen, threshold) in enumerate(
        zip(result.eigenvalues, result.parallel_threshold), 1
    ):
        rows.append(f"Component {i} | {eigen:.3f} | {threshold:.3f}")
    rows.extend([
        "",
        "Pattern/loadings matrix (unthresholded):",
        "Variable | " + " | ".join(
            f"{'PC' if result.method == 'pca' else 'Factor'} {i+1}"
            for i in range(result.n_components)
        ) + (" | Uniqueness" if result.uniqueness is not None else " | MSA (item KMO)"),
    ])
    for j, name in enumerate(result.items):
        numbers = [f"{v:+.3f}" for v in result.loadings[j, :]]
        extra = (
            result.uniqueness[j] if result.uniqueness is not None
            else result.item_kmo[j]
        )
        rows.append(f"{name} | " + " | ".join(numbers) + f" | {extra:.3f}")
    if result.component_variance_share is not None:
        rows.extend([
            "",
            "PCA proportion of TOTAL standardized variance explained:",
        ])
        for j, proportion in enumerate(result.component_variance_share, 1):
            rows.append(f"PC{j}: {proportion:.3f}")
        rows.append(
            f"Cumulative: {sum(result.component_variance_share):.3f}"
        )
    rows.extend([
        "",
        "Important limitations:",
        *result.warnings,
    ])
    return "\n".join(rows)
