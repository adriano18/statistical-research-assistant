"""Reproducible complete-case nonparametric percentile intervals for omega.

Participants (rows) are resampled with replacement; every sample refits the
same one-common-factor ML model. This does not validate the factor model.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from omega_analysis import analyze_omega


@dataclass(frozen=True)
class OmegaBootstrapCI:
    lower: float
    upper: float
    level: float
    successful: int
    requested: int
    failed: int
    seed: int
    method: str = "nonparametric percentile"


def bootstrap_omega(
    df: pd.DataFrame,
    item_names: list[str],
    n_resamples: int = 300,
    seed: int = 20261103,
    level: float = .95,
) -> OmegaBootstrapCI:
    """Percentile CI from independent participant resamples.

    Fails closed rather than silently reporting an unstable interval when
    fewer than 90% of bootstrap refits converge to valid one-factor fits.
    """
    if not isinstance(n_resamples, int) or not 100 <= n_resamples <= 3000:
        raise ValueError("Bootstrap replications must be 100–3000.")
    if not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("Seed must be an unsigned 32-bit integer.")
    if not .8 <= level < 1:
        raise ValueError("Confidence level must be between .80 and 1.")

    # Reuse all existing source-data and one-factor model checks first.
    original = analyze_omega(df, item_names)
    items = original.items
    complete = df[items].apply(pd.to_numeric, errors="raise").dropna()
    observations = complete.to_numpy(dtype=float)
    n = len(observations)
    rng = np.random.default_rng(seed)
    estimates = []

    for _ in range(n_resamples):
        draw = rng.integers(0, n, size=n)
        resampled = pd.DataFrame(observations[draw], columns=items)
        try:
            estimate = analyze_omega(resampled, items).omega
            if np.isfinite(estimate):
                estimates.append(estimate)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            # Some bootstrap resamples create singular/inadmissible factor fits.
            # They must not enter the percentile calculation.
            continue

    successful = len(estimates)
    if successful < max(100, int(np.ceil(.9*n_resamples))):
        raise ValueError(
            "Bootstrap CI not reliable: too many model refits failed "
            f"({successful}/{n_resamples} successful). "
            "Review factorability, sample size and coding."
        )
    alpha = (1 - level) / 2
    low, high = np.quantile(estimates, (alpha, 1-alpha))
    if not np.isfinite([low, high]).all():
        raise ValueError("Invalid bootstrap quantiles.")
    return OmegaBootstrapCI(
        lower=float(low), upper=float(high), level=level,
        successful=successful, requested=n_resamples,
        failed=n_resamples-successful, seed=seed,
    )
