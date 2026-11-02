"""Create a readable exploratory heatmap with coefficients and pairwise N."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reliability_reporting import apa_coefficient


def make_correlation_matrix_chart(result) -> bytes:
    k = len(result.names)
    fig_size = max(7.5, 1.05 * k + 3.4)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size * 0.83))
    try:
        data = np.ma.masked_invalid(result.coefficients)
        cmap = plt.get_cmap("coolwarm").with_extremes(bad="#e5e7eb")
        plot = ax.imshow(data, cmap=cmap, vmin=-1, vmax=1)

        ax.set_xticks(range(k), labels=result.names, rotation=35, ha="right")
        ax.set_yticks(range(k), labels=result.names)
        ax.set_xlim(-0.5, k - 0.5)
        ax.set_ylim(k - 0.5, -0.5)

        for row in range(k):
            for col in range(k):
                value = result.coefficients[row, col]
                n = result.pair_counts[row, col]
                label = (
                    f"{apa_coefficient(value)}\nN = {n}"
                    if np.isfinite(value) else f"N/A\nN = {n}"
                )
                color = "white" if np.isfinite(value) and abs(value) > 0.65 else "black"
                ax.text(col, row, label, ha="center", va="center",
                        color=color, fontsize=9)

        ax.set_xticks(np.arange(-0.5, k, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, k, 1), minor=True)
        ax.grid(which="minor", linewidth=0.8, color="white")
        ax.tick_params(which="minor", bottom=False, left=False)
        fig.colorbar(plot, ax=ax, shrink=0.8, label="Correlation coefficient")

        title_method = "Pearson’s r" if result.method == "pearson" else "Spearman’s ρ"
        fig.text(0.06, 0.985, "Figure 3", weight="bold", fontsize=11, va="top")
        fig.text(0.06, 0.945, f"Exploratory {title_method} Correlation Matrix",
                 style="italic", fontsize=11, va="top")
        note = (
            "Note. N is the number of complete paired observations in each cell. "
            "N/A indicates insufficient data or a constant variable. "
            "No significance tests are displayed. The colors show associations, not causation."
        )
        fig.text(
            0.06, 0.025, textwrap.fill(note, width=115),
            fontsize=8.5, va="bottom",
        )
        fig.tight_layout(rect=(0.03, 0.085, 0.98, 0.86))
        image = BytesIO()
        fig.savefig(image, format="png", dpi=110)
        return image.getvalue()
    finally:
        plt.close(fig)
