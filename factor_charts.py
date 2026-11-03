"""APA-inspired scree/parallel plot and loadings matrix for PCA/EFA."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_factor_chart(result) -> bytes:
    fig, axes = plt.subplots(1, 2, figsize=(13.1, 6.3))
    try:
        ax, heat = axes
        k = len(result.items)
        x = np.arange(1, k+1)
        ax.plot(
            x, result.eigenvalues, "o-",
            linewidth=2, label="Observed PCA eigenvalues",
        )
        ax.plot(
            x, result.parallel_threshold,
            "s--", linewidth=1.6,
            label="Simulated null 95th percentile",
        )
        ax.axhline(1, linestyle=":", alpha=.5, color="#586474")
        ax.set(
            title="Correlation scree and PCA parallel analysis",
            xlabel="Component number",
            ylabel="Correlation eigenvalue",
        )
        ax.set_xticks(x)
        ax.grid(alpha=.15)
        ax.legend(fontsize=8)

        im = heat.imshow(
            result.loadings, cmap="coolwarm",
            vmin=-1, vmax=1, aspect="auto",
        )
        heat.set_xticks(
            range(result.n_components),
            labels=[
                f"{'PC' if result.method == 'pca' else 'F'}{i+1}"
                for i in range(result.n_components)
            ],
        )
        heat.set_yticks(range(k), labels=result.items)
        heat.set_title(
            "PCA loadings" if result.method == "pca"
            else f"Principal-axis EFA loadings ({result.rotation})"
        )
        for i in range(k):
            for j in range(result.n_components):
                value = float(result.loadings[i, j])
                heat.text(
                    j, i, f"{value:+.2f}",
                    ha="center", va="center", fontsize=8,
                    color="white" if abs(value) > .55 else "#1d2430",
                )
        fig.colorbar(im, ax=heat, shrink=.78, label="Loading")
        fig.text(.055, .985, "Figure 14", weight="bold", va="top", fontsize=11)
        fig.text(
            .055, .952,
            "Exploratory Structure and Factor Retention Diagnostics",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. Parallel analysis uses simulated independent-normal "
            "PCA eigenvalues (95th percentile, 150 replications, fixed seed). "
            "Shown loadings reflect the user-selected model; factors are not "
            "automatically retained. PCA is NOT common factor analysis. "
            "Correlations are Pearson, not polychoric."
        )
        fig.text(
            .055, .026, textwrap.fill(note, 145),
            fontsize=8, va="bottom",
        )
        fig.tight_layout(rect=(.02, .12, .995, .88))
        out = BytesIO()
        fig.savefig(out, format="png", dpi=120)
        return out.getvalue()
    finally:
        plt.close(fig)
