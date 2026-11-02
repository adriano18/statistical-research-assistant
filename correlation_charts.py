"""Scatterplots for Pearson and Spearman correlation results."""

from io import BytesIO
import textwrap
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
        # Slight visual-only jitter reveals tied ordinal response pairs.
        # All statistics still use the original, unmodified observations.
        repeated = len(np.unique(np.column_stack((x, y)), axis=0)) < len(x)
        jittered = result.method == "spearman" and repeated
        if jittered:
            rng = np.random.default_rng(2026)
            x_step = np.min(np.diff(np.unique(x))) if len(np.unique(x)) > 1 else 1.0
            y_step = np.min(np.diff(np.unique(y))) if len(np.unique(y)) > 1 else 1.0
            plot_x = x + rng.uniform(-0.09, 0.09, len(x)) * x_step
            plot_y = y + rng.uniform(-0.09, 0.09, len(y)) * y_step
        else:
            plot_x, plot_y = x, y
        ax.scatter(plot_x, plot_y, alpha=0.7, s=45,
                   edgecolors="black", linewidths=0.3)

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
        if result.method == "pearson":
            note = (
                "Note. Each dot represents a complete pair. The dashed linear "
                "trend is descriptive, not causal."
            )
        elif jittered:
            note = (
                "Note. Tied response pairs are slightly jittered for display only. "
                "The reported ρ is calculated from the original data. "
                "Correlation does not establish causation."
            )
        else:
            note = (
                "Note. Each dot represents a complete pair. "
                "Spearman’s ρ measures monotonic association, not causation."
            )

        fig.text(0.08, 0.045, textwrap.fill(note, width=105),
                 fontsize=8.5, va="bottom")
        fig.tight_layout(rect=(0.03, 0.115, 0.98, 0.86))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
