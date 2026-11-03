"""Descriptive group fit vs first covariate and adjusted mean confidence intervals."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_ancova_chart(result) -> bytes:
    fig, axes = plt.subplots(
        1, 2, figsize=(12.3, 5.5),
        gridspec_kw={"width_ratios": [1.35, 1]},
    )
    try:
        ax, means_ax = axes
        for item in result.groups:
            mask = result.plot_group == item.label
            scatter = ax.scatter(
                result.plot_covariate[mask], result.plot_outcome[mask],
                alpha=0.4, s=21, label=f"{item.label} (n={item.n})",
            )
            ax.plot(
                result.plot_x,
                result.plot_lines[item.label],
                color=scatter.get_facecolors()[0],
                linewidth=2,
            )
        ax.set_title(
            "Fitted group lines " +
            ("(common slopes)" if result.mode == "ancova" else "(interactions)")
        )
        ax.set_xlabel(result.covariates[0])
        ax.set_ylabel(result.outcome)
        ax.legend(fontsize=8)
        ax.grid(alpha=.16)
        if len(result.covariates) > 1:
            ax.text(
                .02, .02, "Other covariates held at complete-case means",
                transform=ax.transAxes, fontsize=8,
            )

        x = np.arange(len(result.groups))
        predicted = np.asarray([g.adjusted_mean for g in result.groups])
        low = np.asarray([g.ci_low for g in result.groups])
        high = np.asarray([g.ci_high for g in result.groups])
        raw = np.asarray([g.raw_mean for g in result.groups])
        means_ax.errorbar(
            x, predicted, yerr=[predicted-low, high-predicted],
            fmt="o", capsize=5, markersize=8,
            color="#2563eb", label="Adjusted mean ± 95% CI",
        )
        means_ax.scatter(
            x + .12, raw, marker="x", s=55,
            color="#b45309", label="Raw mean",
        )
        means_ax.set_xticks(x, labels=[g.label for g in result.groups])
        means_ax.set_ylabel(result.outcome)
        means_ax.set_title("Adjusted and unadjusted group means")
        means_ax.legend(fontsize=8)
        means_ax.grid(axis="y", alpha=.16)

        fig.text(
            .055, .985, "Figure 12",
            weight="bold", fontsize=11, va="top",
        )
        fig.text(
            .055, .944, "Covariate-Adjusted Group Comparisons",
            fontsize=11, style="italic", va="top",
        )
        note = (
            "Note. Adjusted means refer to the COMPLETE-CASE grand means of "
            "all covariates. Displayed 95% group CIs are individual, "
            "not multiplicity-adjusted. In the interaction model, group "
            "contrasts vary with covariate values. Inspect overlap before "
            "interpreting adjusted values; association is not causality."
        )
        fig.text(
            .055, .023, textwrap.fill(note, 137),
            fontsize=8.0, va="bottom",
        )
        fig.tight_layout(rect=(.02, .11, .99, .87))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
