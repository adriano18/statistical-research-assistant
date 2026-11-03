"""Binary outcome fitted probabilities, in-sample ROC and calibration plot."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_logistic_chart(result) -> bytes:
    y = result.actual
    prob = result.probabilities
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))

    order = np.argsort(-prob, kind="stable")
    scores = prob[order]
    truth = y[order]
    cumulative_true = np.cumsum(truth == 1)
    cumulative_false = np.cumsum(truth == 0)
    last_ties = np.r_[np.flatnonzero(np.diff(scores) != 0), len(scores) - 1]
    tpr = np.r_[0., cumulative_true[last_ties] / n_pos]
    fpr = np.r_[0., cumulative_false[last_ties] / n_neg]

    fig, axes = plt.subplots(1, 3, figsize=(13.8, 5))
    try:
        left, middle, right = axes
        left.plot(fpr, tpr, linewidth=2, color="#2563eb")
        left.plot([0, 1], [0, 1], linestyle="--", color="#7a8798")
        left.set(xlabel="False-positive rate", ylabel="True-positive rate",
                 title=f"Training-data ROC | AUC = {result.roc_auc:.3f}")
        left.set_xlim(0, 1)
        left.set_ylim(0, 1)
        left.grid(alpha=.16)

        middle.hist(
            [prob[y == 0], prob[y == 1]],
            bins=np.linspace(0, 1, 12), color=["#7ca8ce", "#dd8f5b"],
            alpha=.75, label=["Outcome 0", "Outcome 1"],
        )
        middle.set(
            xlabel="Fitted event probability",
            ylabel="Observations",
            title="In-sample predicted probabilities",
        )
        middle.legend(fontsize=8)

        # Equal-count probability bins give a descriptive calibration picture.
        indices = np.argsort(prob, kind="stable")
        bins = np.array_split(indices, min(8, max(2, len(prob) // 15)))
        predicted = [float(np.mean(prob[b])) for b in bins if len(b)]
        observed = [float(np.mean(y[b])) for b in bins if len(b)]
        right.plot(predicted, observed, "o-", color="#2563eb")
        right.plot([0, 1], [0, 1], linestyle="--", color="#7a8798")
        right.set(
            xlabel="Mean predicted probability",
            ylabel="Observed event rate",
            title="Descriptive training-data calibration",
        )
        right.set_xlim(0, 1)
        right.set_ylim(0, 1)
        right.grid(alpha=.16)

        fig.text(.055, .986, "Figure 11", fontsize=11, weight="bold", va="top")
        fig.text(
            .055, .947, "Binary Logistic Regression: Internal Diagnostics",
            fontsize=11, style="italic", va="top",
        )
        note = (
            "Note. ROC AUC, score distributions and calibration use the SAME "
            "observations that fitted the model. They may be optimistic; "
            "there is no cross-validation or external test set. "
            "No classification threshold or causal claim is implied."
        )
        fig.text(
            .055, .022, textwrap.fill(note, 142),
            va="bottom", fontsize=8.1,
        )
        fig.tight_layout(rect=(.02, .11, .99, .86))
        output = BytesIO()
        fig.savefig(output, format="png", dpi=115)
        return output.getvalue()
    finally:
        plt.close(fig)
