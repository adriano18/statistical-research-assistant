"""Render Cronbach alpha and item-deletion results as a local PNG."""

from io import BytesIO
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from reliability_reporting import apa_coefficient


def make_reliability_chart(analysis) -> bytes:
    """Create a figure with the full-scale 95% CI and item-deletion alphas.

    Individual item-deletion values have no confidence interval in this plot.
    All deletion statistics use the same complete-case respondents.
    """
    values = [analysis.alpha, *analysis.alpha_if_deleted.values()]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Cannot chart a non-finite reliability estimate.")

    labels = ["Full scale (95% CI)"] + [
        f"Without {name}" for name in analysis.alpha_if_deleted
    ]
    positions = list(range(len(labels)))
    height = max(4.2, 2.6 + 0.54 * len(labels))

    fig, ax = plt.subplots(figsize=(10, height))
    try:
        bars = ax.barh(positions, values, height=0.55)
        # The CI applies only to full-scale alpha, not the deletion estimates.
        ax.errorbar(
            analysis.alpha,
            positions[0],
            xerr=[
                [max(0, analysis.alpha - analysis.ci_low)],
                [max(0, analysis.ci_high - analysis.alpha)],
            ],
            fmt="o",
            color="black",
            capsize=5,
            linewidth=1.4,
            zorder=5,
        )

        for threshold in (0.70, 0.90):
            ax.axvline(threshold, linestyle="--", linewidth=1, alpha=0.65)

        low = min(0.0, analysis.ci_low, *values)
        high = max(1.0, analysis.ci_high, *values)
        pad = max(0.06, (high - low) * 0.08)
        ax.set_xlim(low - pad if low < 0 else 0, high + pad)
        ax.set_yticks(positions, labels=labels)
        ax.invert_yaxis()
        ax.set_xlabel("Cronbach’s α")
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda val, pos: apa_coefficient(val))
        )
        ax.set_title("Internal consistency and item-deletion estimates", pad=15)

        for bar, value in zip(bars, values):
            ax.text(
                value,
                bar.get_y() + bar.get_height() / 2,
                "  " + apa_coefficient(value),
                va="center",
                ha="left",
                fontsize=9,
            )

        fig.text(
            0.07, 0.035,
            "Note. Error bars indicate the 95% CI for the full scale only. "
            "Dashed lines mark common .70 and .90 heuristics, not validity cutoffs.",
            fontsize=8.5,
        )
        fig.tight_layout(rect=(0.03, 0.08, 0.99, 0.95))

        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
