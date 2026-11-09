"""Default figures of the Stage 36 batch analyses (APA style, PNG).

- Correlations: every coefficient with its interval (a forest plot), in
  the order the researcher chose; the line at zero is "no association".
- Group comparisons: one boxplot panel per outcome, split by the group.

Figures are drawn only from the stored family and the data columns;
nothing here recalculates a statistic. Chart Studio (36.4) offers other
views of the same data.
"""

from __future__ import annotations

from io import BytesIO
import math
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from batch_correlation import METHODS as CORRELATION_METHODS, SYMBOLS  # noqa: E402

ACCENT = "#1F5FAD"


def _png(fig) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=115, metadata={"Software": None})
    return buffer.getvalue()


def correlation_forest(family) -> bytes:
    rows = [row for row in family.rows if row.status == "ok"]
    height = max(3.2, 0.55 * len(rows) + 2.2)
    fig, ax = plt.subplots(figsize=(9, height))
    try:
        y = np.arange(len(rows))[::-1]
        for position, row in zip(y, rows):
            if row.ci_low is not None and row.ci_high is not None:
                ax.plot([row.ci_low, row.ci_high], [position, position], color=ACCENT, linewidth=2)
            ax.plot(row.estimate, position, "o", color=ACCENT, markersize=7)
        ax.axvline(0, color="#555555", linewidth=1, linestyle="--")
        ax.set_yticks(y)
        ax.set_yticklabels([row.y for row in rows])
        ax.set_xlim(-1, 1)
        symbol = SYMBOLS[family.method]
        ax.set_xlabel(f"{symbol} with {family.ci_level:.0%} interval")
        ax.grid(axis="x", color="#DDDDDD", linewidth=0.6)
        fig.text(0.08, 0.97, "Figure", weight="bold", fontsize=11, va="top")
        fig.text(0.08, 0.93, f"{CORRELATION_METHODS[family.method]} Between {family.focal} and "
                 f"{len(rows)} Variables", style="italic", fontsize=11, va="top")
        ci_note = rows[0].ci_method if rows else ""
        note = (f"Note. Dots are coefficients; lines are {family.ci_level:.0%} intervals "
                f"({ci_note}). The dashed line marks no association. Correlation does not "
                "establish causation.")
        fig.text(0.08, 0.02, textwrap.fill(note, width=110), fontsize=8.5, va="bottom")
        fig.tight_layout(rect=(0.03, 0.12, 0.98, 0.88))
        return _png(fig)
    finally:
        plt.close(fig)


def group_boxplots(df: pd.DataFrame, family) -> bytes:
    rows = [row for row in family.rows if row.status == "ok"]
    count = max(1, len(rows))
    columns = min(4, count)
    lines = math.ceil(count / columns)
    fig, axes = plt.subplots(lines, columns, figsize=(3.2 * columns + 1, 2.9 * lines + 1.6),
                             squeeze=False)
    try:
        for index, ax in enumerate(axes.flat):
            if index >= len(rows):
                ax.axis("off")
                continue
            row = rows[index]
            frame = df[[family.group, row.outcome]].copy()
            frame[row.outcome] = pd.to_numeric(frame[row.outcome], errors="coerce")
            frame = frame.dropna()
            data = [frame.loc[frame[family.group].astype(str) == label, row.outcome].to_numpy()
                    for label in row.labels]
            parts = ax.boxplot(data, patch_artist=True, widths=0.55)
            for box in parts["boxes"]:
                box.set_facecolor("#DCE8F7")
                box.set_edgecolor(ACCENT)
            ax.set_xticks(range(1, len(row.labels) + 1))
            ax.set_xticklabels([f"{label}\n(n={n})" for label, n in zip(row.labels, row.ns)],
                               fontsize=8)
            ax.set_title(row.outcome, fontsize=9)
            ax.tick_params(axis="y", labelsize=8)
        fig.text(0.02, 0.985, "Figure", weight="bold", fontsize=11, va="top")
        fig.text(0.02, 0.955, f"Outcomes by {family.group}", style="italic", fontsize=11,
                 va="top")
        fig.text(0.02, 0.01, textwrap.fill(
            "Note. Boxes show quartiles and medians; panels have their own scales. "
            "Group differences do not establish causation.", width=120),
            fontsize=8.5, va="bottom")
        fig.tight_layout(rect=(0.0, 0.05, 1.0, 0.93))
        return _png(fig)
    finally:
        plt.close(fig)
