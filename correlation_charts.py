"""Scatterplots for Pearson and Spearman correlation results."""

from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reliability_reporting import apa_coefficient


def make_correlation_chart(result) -> bytes:
    fig, ax = plt.subplots(figsize=(9, 5.6))
    try:
        x = result.x_values
        y = result.y_values
        ax.scatter(x, y, alpha=0.68, s=45, edgecolors="black", linewidths=0.3)

        if result.method == "pearson":
            # Exploratory least-squares line; not proof of causation.
            slope, intercept = np.polyfit(x, y, 1)
            line_x = np.linspace(min(x), max(x), 100)
            ax.plot(
                line_x, slope * line_x + intercept,
                linewidth=1.5, linestyle="--",
                label="Linear trend (descriptive)",
            )
            ax.legend(loc="best")

        ax.set_xlabel(result.x_name)
        ax.set_ylabel(result.y_name)
        symbol = "r" if result.method == "pearson" else "ρ"
        ax.text(
            0.98, 0.97,
            f"{symbol} = {apa_coefficient(result.coefficient)}; N = {result.n_complete}",
            transform=ax.transAxes,
            ha="right", va="top",
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
        )
        fig.text(0.08, 0.97, "Figure 2", weight="bold", fontsize=11, va="top")
        fig.text(
            0.08, 0.927,
            f"{result.method.title()} Correlation Between "
            f"{result.x_name} and {result.y_name}",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. Each dot represents a complete pair. "
            "Overlapping points can occur for ordinal responses. "
            "The dashed line is descriptive, not causal."
            if result.method == "pearson" else
            "Note. Each dot represents a complete pair. "
            "Overlapping points are expected with tied ranks. "
            "Spearman’s ρ assesses monotonic association."
        )
        fig.text(0.08, 0.035, note, fontsize=8.5)
        fig.tight_layout(rect=(0.03, 0.09, 0.98, 0.86))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
