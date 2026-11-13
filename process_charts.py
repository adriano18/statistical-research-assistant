"""Figures of the path models and the linear model (Stage 37, Issue #66).

Deterministic PNGs drawn from the result objects only:

* Model 1: simple slopes (predicted Y over the observed X range at the
  conditioning values of W, covariates at their means) and the conditional
  effect of X across W with its 95% band and the Johnson–Neyman values;
* Model 4: a path diagram with the estimates and the indirect effects with
  their percentile bootstrap intervals;
* Models 7 and 14: simple slopes of the moderated path and the conditional
  indirect effects with their bootstrap intervals;
* every model: the normal Q–Q plot of the outcome equation's residuals and
  residuals against leverage (with Cook's distance as the marker size).
"""

from __future__ import annotations

from io import BytesIO
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

COLORS = ("#2755A1", "#C2410C", "#15803D", "#7C3AED", "#B91C1C", "#0E7490")
NOTE = ("Note. Estimates are conditional associations in the data as analysed; “effect” is "
        "the conventional name of these model quantities and does not establish causation.")


def _png(fig) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=110)
    plt.close(fig)
    return buffer.getvalue()


def _residual_panels(ax_qq, ax_lev, equation) -> None:
    stats.probplot(equation.residuals, dist="norm", plot=ax_qq)
    ax_qq.set_title(f"Residual normal Q–Q: {equation.outcome}", fontsize=10)
    ax_qq.get_lines()[0].set_markersize(3.5)
    size = 8 + 400 * np.asarray(equation.cooks) / max(float(np.max(equation.cooks)), 1e-12)
    ax_lev.scatter(equation.leverage, equation.residuals, s=size, alpha=0.55,
                   color=COLORS[0], edgecolor="none")
    ax_lev.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    n, p = len(equation.residuals), len(equation.coefficients)
    ax_lev.axvline(2 * p / n, color=COLORS[1], linestyle=":", linewidth=1,
                   label="leverage 2p/N")
    ax_lev.set(xlabel="Leverage", ylabel="Residual")
    ax_lev.set_title("Residuals vs leverage (size: Cook’s D)", fontsize=10)
    ax_lev.legend(fontsize=8, loc="best")


def _focal_lines(ax, result, equation, focal: str, product: str, focal_name: str) -> None:
    """Predicted outcome over the observed range of the focal predictor at the
    mean ± 1 SD values of W (or W's two values); every other predictor is held
    at its mean, and products are formed from those values."""
    from process_text import t

    coef = np.array([c.b for c in equation.coefficients])
    terms = list(equation.terms)[1:]
    simple = {key for term in terms for key in term.split("*")}
    means = {key: float(np.mean(_column(result, key))) for key in simple}
    focal_raw = _column(result, focal) + result.centering.get(focal, 0.0)
    grid = np.linspace(focal_raw.min(), focal_raw.max(), 50)
    centre_focal = result.centering.get(focal, 0.0)
    centre_w = result.centering.get("w", 0.0)
    points = [p for p in result.w_points if p.where in ("w.minus", "w.mean", "w.plus",
                                                        "w.low", "w.high")]
    for color, point in zip(COLORS, points):
        values = dict(means)
        values["w"] = point.value - centre_w
        predicted = []
        for value in grid:
            values[focal] = value - centre_focal
            row = [1.0]
            for term in terms:
                if "*" in term:
                    left, right = term.split("*")
                    row.append(values[left] * values[right])
                else:
                    row.append(values[term])
            predicted.append(float(np.asarray(row) @ coef))
        ax.plot(grid, predicted, color=color, linewidth=2,
                label=f"W = {point.value:.2f} ({t('en', point.where)})")
    ax.set(xlabel=focal_name, ylabel=f"Predicted {equation.outcome}")
    ax.legend(fontsize=8, loc="best")


def _column(result, key: str) -> np.ndarray:
    spec = result.spec
    if key == "x":
        values = result.data[spec.x]
    elif key == "w":
        values = result.data[spec.w]
    elif key.startswith("m"):
        values = result.data[spec.mediators[int(key[1:])]]
    else:
        values = result.data[spec.covariates[int(key[1:])]]
    return values.to_numpy(float) - result.centering.get(key, 0.0)


def _short_label(estimate) -> str:
    """A label that fits beside an interval: the mediator and, for a
    conditional indirect effect, the value of W and where it lies."""
    from process_text import t

    mediator = estimate.mediator if len(estimate.mediator) <= 24 else \
        estimate.mediator[:22] + "…"
    if estimate.key.startswith("index:"):
        return f"Index via {mediator}"
    if estimate.key.startswith("cond_indirect:"):
        return f"{mediator} at W = {estimate.w:.2f} ({t('en', estimate.where)})"
    if estimate.key == "indirect_total":
        return "Total indirect effect"
    if estimate.key.startswith("indirect:"):
        return f"Indirect via {mediator}"
    return estimate.label if len(estimate.label) < 60 else textwrap.shorten(estimate.label, 60)


def _intervals(ax, estimates, title: str) -> None:
    labels = [_short_label(e) for e in estimates]
    y = np.arange(len(estimates))[::-1]
    values = np.array([e.value for e in estimates])
    low = np.array([e.ci_low for e in estimates])
    high = np.array([e.ci_high for e in estimates])
    ax.errorbar(values, y, xerr=[values - low, high - values], fmt="o", color=COLORS[0],
                ecolor=COLORS[0], capsize=3)
    ax.axvline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([textwrap.fill(label, 34) for label in labels], fontsize=7.5)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Estimate with 95% percentile bootstrap interval")


def _path_diagram(ax, result) -> None:
    spec = result.spec
    ax.set_axis_off()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    k = len(spec.mediators)

    def box(x, y, text):
        ax.text(x, y, textwrap.fill(text, 16), ha="center", va="center", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#EEF2FA", edgecolor=COLORS[0]))

    box(1.4, 2.2, f"X: {spec.x}")
    box(8.6, 2.2, f"Y: {spec.y}")
    ys = np.linspace(8.4, 5.4, k) if k > 1 else [7.6]
    for j, (mediator, y) in enumerate(zip(spec.mediators, ys)):
        box(5.0, y, f"M: {mediator}")
        a = result.estimate(f"a:m{j}").value
        b = result.estimate(f"b:m{j}").value
        ax.annotate("", xy=(4.0, y - 0.3), xytext=(2.0, 2.9),
                    arrowprops=dict(arrowstyle="->", color="#333333"))
        ax.annotate("", xy=(8.0, 2.9), xytext=(6.0, y - 0.3),
                    arrowprops=dict(arrowstyle="->", color="#333333"))
        ax.text(2.7, (y + 2.9) / 2, f"a = {a:.3f}", fontsize=8, color=COLORS[1], ha="right")
        ax.text(7.3, (y + 2.9) / 2, f"b = {b:.3f}", fontsize=8, color=COLORS[1], ha="left")
    ax.annotate("", xy=(7.4, 2.2), xytext=(2.6, 2.2),
                arrowprops=dict(arrowstyle="->", color="#333333"))
    direct = result.estimate("direct").value
    ax.text(5.0, 1.5, f"c′ = {direct:.3f}", ha="center", fontsize=8, color=COLORS[1])
    if spec.model == "4":
        total = result.estimate("total").value
        ax.text(5.0, 0.6, f"(c = {total:.3f})", ha="center", fontsize=8, color="#555555")
    if spec.w:
        target = (3.0, 5.0) if spec.model == "7" else (7.0, 5.0)
        ax.text(target[0], target[1] - 1.6, f"W: {spec.w}", ha="center", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF7ED",
                          edgecolor=COLORS[1]))
        ax.annotate("", xy=target, xytext=(target[0], target[1] - 1.3),
                    arrowprops=dict(arrowstyle="->", color=COLORS[1]))
    ax.set_title(f"Model {spec.model} (PROCESS-equivalent structure)", fontsize=10)


def make_process_chart(result) -> bytes:
    spec = result.spec
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 9.2))
    (top_left, top_right), (bottom_left, bottom_right) = axes
    y_eq = result.equation("y")
    if spec.model == "1":
        _focal_lines(top_left, result, y_eq, "x", "x*w", spec.x)
        top_left.set_title("Simple slopes of X at W = mean ± 1 SD", fontsize=10)
        w = result.data[spec.w].to_numpy(float)
        grid = np.linspace(w.min(), w.max(), 200)
        i, j = y_eq.index("x"), y_eq.index("x*w")
        b1, b3 = y_eq.coefficients[i].b, y_eq.coefficients[j].b
        cov = y_eq.cov
        centre = result.centering.get("w", 0.0)
        u = grid - centre
        effect = b1 + b3 * u
        se = np.sqrt(np.maximum(cov[i, i] + u * u * cov[j, j] + 2 * u * cov[i, j], 0))
        t_crit = stats.t.ppf(0.5 + spec.level / 2, y_eq.df_resid)
        top_right.plot(grid, effect, color=COLORS[0], linewidth=2)
        top_right.fill_between(grid, effect - t_crit * se, effect + t_crit * se,
                               color=COLORS[0], alpha=0.18, label="95% CI")
        top_right.axhline(0, color="gray", linestyle="--", linewidth=0.8)
        jn = result.johnson_neyman
        if jn is not None:
            for point in jn.points:
                top_right.axvline(point, color=COLORS[1], linestyle=":",
                                  label=f"Johnson–Neyman W = {point:.3f}")
        top_right.plot(w, np.full_like(w, float(np.min(effect - t_crit * se))), "|",
                       color="#777777", markersize=6, alpha=0.5)
        top_right.set(xlabel=f"W: {spec.w}", ylabel=f"Conditional effect of {spec.x}")
        top_right.set_title("Conditional effect of X across W (Johnson–Neyman)", fontsize=10)
        top_right.legend(fontsize=8, loc="best")
    elif spec.model == "4":
        _path_diagram(top_left, result)
        estimates = [e for e in result.indirect if not e.key.startswith("indirect_std")]
        _intervals(top_right, estimates, "Indirect effects (percentile bootstrap)")
    else:
        if spec.model == "7":
            m_eq = result.equation("m0")
            _focal_lines(top_left, result, m_eq, "x", "x*w", spec.x)
            top_left.set_title(f"Simple slopes of X → {spec.mediators[0]} (a path) at W",
                               fontsize=10)
        else:
            _focal_lines(top_left, result, y_eq, "m0", "m0*w", spec.mediators[0])
            top_left.set_title(f"Simple slopes of {spec.mediators[0]} → Y (b path) at W",
                               fontsize=10)
        estimates = [e for e in result.indirect if e.key.startswith(("index:",
                                                                     "cond_indirect:"))]
        _intervals(top_right, estimates, "Index and conditional indirect effects")
    _residual_panels(bottom_left, bottom_right, y_eq)
    fig.text(0.02, 0.012, textwrap.fill(NOTE, 170), fontsize=8, va="bottom")
    fig.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    return _png(fig)


def make_linear_model_chart(result) -> bytes:
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.6))
    ax1, ax2, ax3 = axes
    ax1.scatter(result.fitted, result.observed, alpha=0.6, s=22, color=COLORS[0])
    low = float(min(np.min(result.fitted), np.min(result.observed)))
    high = float(max(np.max(result.fitted), np.max(result.observed)))
    ax1.plot([low, high], [low, high], linestyle="--", color="gray")
    ax1.set(xlabel="Fitted", ylabel="Observed", title="Observed vs fitted")
    ax2.scatter(result.fitted, result.residuals, alpha=0.6, s=22, color=COLORS[0])
    ax2.axhline(0, linestyle="--", color="gray")
    ax2.set(xlabel="Fitted", ylabel="Residual", title="Residuals vs fitted")
    stats.probplot(result.residuals, dist="norm", plot=ax3)
    ax3.set_title("Residual normal Q–Q")
    fig.text(0.02, 0.01, textwrap.fill(
        "Note. Categorical covariates enter as dummy codes against the stated reference "
        "category. Diagnostics are in-sample and do not establish causality.", 160),
        fontsize=8, va="bottom")
    fig.tight_layout(rect=(0.0, 0.06, 1.0, 1.0))
    return _png(fig)
