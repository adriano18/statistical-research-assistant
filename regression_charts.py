"""Fitted/observed scores, residual diagnostic, and normal Q–Q plot."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


def make_regression_chart(result) -> bytes:
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8))
    try:
        ax1, ax2, ax3 = axes
        ax1.scatter(result.fitted, result.observed, alpha=0.65, s=27)
        low = float(min(np.min(result.fitted), np.min(result.observed)))
        high = float(max(np.max(result.fitted), np.max(result.observed)))
        ax1.plot([low, high], [low, high], linestyle="--", color="gray")
        ax1.set(xlabel="Fitted outcome", ylabel="Observed outcome",
                title="Observed vs fitted")
        ax2.scatter(result.fitted, result.residuals, alpha=0.65, s=27)
        ax2.axhline(0, linestyle="--", color="gray")
        ax2.set(xlabel="Fitted outcome", ylabel="Residual",
                title="Residuals vs fitted")
        stats.probplot(result.residuals, dist="norm", plot=ax3)
        ax3.set_title("Residual normal Q–Q")

        fig.text(0.055, 0.985, "Figure 9", weight="bold", fontsize=11, va="top")
        fig.text(
            0.055, 0.942, "Ordinary Least Squares Model Diagnostics",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. Diagonal in the left panel indicates perfect predictions; "
            "the middle panel helps inspect variance and nonlinearity. "
            "The right panel shows residual departures from normality. "
            "Diagnostics do not establish causality or independence."
        )
        fig.text(0.055, 0.032, textwrap.fill(note, 146),
                 fontsize=8, va="bottom")
        fig.tight_layout(rect=(0.02, 0.115, 0.99, 0.85))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
