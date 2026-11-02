"""Create local PNG charts from descriptive research data.

Only descriptive visualizations are produced. No assumptions or significance
tests are inferred from these plots.
"""

from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd

from variable_rules import looks_like_identifier


def make_descriptive_chart(values: pd.Series, scale: str) -> bytes:
    """Return PNG bytes for a histogram or category frequency chart."""
    if scale not in {"scale", "nominal", "ordinal"}:
        raise ValueError("Confirm a non-identifier measurement scale first.")

    if looks_like_identifier(values.name):
        raise ValueError("Identifiers should not be plotted as measurements.")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    try:
        if scale == "scale":
            numeric = pd.to_numeric(values, errors="coerce")
            if numeric.notna().sum() != values.notna().sum():
                raise ValueError("Some non-missing values are not numbers.")
            numeric = numeric.dropna()
            if numeric.empty:
                raise ValueError("No valid numerical observations.")

            # Small exploratory samples should not be shown with dozens of bins.
            bins = min(10, max(1, int(numeric.nunique())))
            ax.hist(numeric, bins=bins, edgecolor="black")
            ax.set_title(f"Distribution of {values.name}")
            ax.set_xlabel(str(values.name))
        else:
            counts = (
                values.astype("string")
                .fillna("(missing)")
                .value_counts()
                .head(15)
            )
            if counts.empty:
                raise ValueError("No values to plot.")
            ax.bar(counts.index.astype(str).tolist(), counts.to_numpy())
            ax.set_title(f"Frequencies of {values.name}")
            ax.set_xlabel(str(values.name))
            ax.tick_params(axis="x", labelrotation=30)
            if values.nunique(dropna=False) > 15:
                ax.set_title(f"Top 15 categories of {values.name}")

        ax.set_ylabel("Frequency")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        fig.tight_layout()

        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=110)
        return buffer.getvalue()
    finally:
        plt.close(fig)
