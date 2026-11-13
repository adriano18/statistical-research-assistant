"""Cronbach's α, Feldt's interval and α if an item is deleted (Stage 37).

Written from the published formulas, for complete (listwise) item responses:

* **α** (Cronbach, 1951): for k items with sample variances s²ᵢ and the
  sample variance s²_T of the total score (the sum of the k items),

      α = k / (k − 1) · (1 − Σ s²ᵢ / s²_T),

  with the n − 1 denominator for every variance.
* **Feldt's interval** (Feldt, 1965; Feldt, Woodruff & Salih, 1987): under
  the model behind α, (1 − α) / (1 − α̂) follows an F distribution with
  df₁ = n − 1 and df₂ = (n − 1)(k − 1). The two-sided interval of level
  1 − γ is

      [1 − (1 − α̂)·F₁₋γ/₂(df₁, df₂),  1 − (1 − α̂)·Fγ/₂(df₁, df₂)],

  where F_p is the p quantile of the F distribution.
* **α if an item is deleted**: α of the other k − 1 items on the same
  complete cases.

The application's reliability engine (``reliability.analyze_cronbach``) uses
these functions. ``tests/test_cronbach.py`` checks them against hand
calculations and, as a test-only oracle, against pingouin.

References: Cronbach, L. J. (1951). Coefficient alpha and the internal
structure of tests. Psychometrika, 16, 297–334. Feldt, L. S. (1965). The
approximate sampling distribution of Kuder–Richardson reliability
coefficient twenty. Psychometrika, 30, 357–370. Feldt, L. S., Woodruff,
D. J., & Salih, F. A. (1987). Statistical inference for coefficient alpha.
Applied Psychological Measurement, 11, 93–103.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def _matrix(values) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] < 2 or matrix.shape[0] < 2:
        raise ValueError("α needs at least two items and two complete responses.")
    if not np.isfinite(matrix).all():
        raise ValueError("α needs complete, finite responses (use listwise complete cases).")
    return matrix


def cronbach_alpha(values) -> float:
    """α of the columns of ``values`` (respondents × items, complete)."""
    matrix = _matrix(values)
    k = matrix.shape[1]
    item_variances = matrix.var(axis=0, ddof=1)
    total_variance = matrix.sum(axis=1).var(ddof=1)
    if total_variance <= 0:
        raise ValueError("The total score has no variation.")
    return float(k / (k - 1) * (1.0 - item_variances.sum() / total_variance))


def feldt_interval(alpha: float, n: int, k: int, level: float = 0.95) -> tuple[float, float]:
    """Feldt's F-based interval of α for ``n`` respondents and ``k`` items
    (bounds not rounded)."""
    if n < 2 or k < 2:
        raise ValueError("Feldt's interval needs n ≥ 2 and k ≥ 2.")
    if not 0 < level < 1:
        raise ValueError("The interval level lies between 0 and 1.")
    df1, df2 = n - 1, (n - 1) * (k - 1)
    gamma = 1.0 - level
    upper_quantile = stats.f.ppf(1.0 - gamma / 2.0, df1, df2)
    lower_quantile = stats.f.ppf(gamma / 2.0, df1, df2)
    return (float(1.0 - (1.0 - alpha) * upper_quantile),
            float(1.0 - (1.0 - alpha) * lower_quantile))


def alpha_if_deleted(values) -> list[float | None]:
    """α of the other items for each item (None when it cannot be computed:
    fewer than two items would remain, or the remaining total or an item has
    no variation)."""
    matrix = _matrix(values)
    out: list[float | None] = []
    for j in range(matrix.shape[1]):
        rest = np.delete(matrix, j, axis=1)
        if rest.shape[1] < 2 or (rest.var(axis=0, ddof=1) <= 0).any() \
                or rest.sum(axis=1).var(ddof=1) <= 0:
            out.append(None)
            continue
        out.append(cronbach_alpha(rest))
    return out
