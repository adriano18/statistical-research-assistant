"""APA-style contingency table visualization of observed/expected counts."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_chi_square_chart(result) -> bytes:
    rows, cols = result.observed.shape
    fig, ax = plt.subplots(
        figsize=(max(7.5, cols * 1.4 + 3.4), max(5.0, rows * 0.75 + 3.2))
    )
    try:
        heatmap = ax.imshow(result.observed, cmap="Blues", aspect="auto")
        ax.set_xticks(range(cols), labels=result.column_labels)
        ax.set_yticks(range(rows), labels=result.row_labels)
        ax.set_xlabel(result.variable_b)
        ax.set_ylabel(result.variable_a)
        ax.tick_params(axis="x", labelrotation=20)
        for i in range(rows):
            for j in range(cols):
                observed = result.observed[i, j]
                expected = result.expected[i, j]
                color = (
                    "white" if observed > result.observed.max() * 0.55
                    else "black"
                )
                ax.text(j, i, f"O = {observed}\nE = {expected:.1f}",
                        ha="center", va="center", fontsize=9, color=color)
        fig.colorbar(heatmap, ax=ax, shrink=0.78, label="Observed frequency")
        fig.text(0.07, 0.98, "Figure 6", weight="bold", fontsize=11, va="top")
        fig.text(
            0.07, 0.94, "Observed and Expected Categorical Frequencies",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. O denotes observed counts; E denotes expected counts under "
            "independence. Colors reflect frequencies, not effect size or causation. "
            "Small expected counts can invalidate the asymptotic test."
        )
        fig.text(
            0.07, 0.025, textwrap.fill(note, width=105),
            fontsize=8.5, va="bottom",
        )
        fig.tight_layout(rect=(0.03, 0.1, 0.98, 0.85))
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=115)
        return buf.getvalue()
    finally:
        plt.close(fig)
