"""Friedman and one-factor repeated-measures ANOVA for wide-format data.

One row represents one participant; selected columns represent 3–8 ordered
measurement occasions of the SAME construct. Complete cases only.

Classical RM ANOVA uses a Greenhouse–Geisser correction for the reported
primary inferential p-value. Sphericity is not presumed or declared verified.
"""

from dataclasses import dataclass
from itertools import combinations
import math

import numpy as np
import pandas as pd
from scipy import stats

from posthoc_analysis import holm_adjust
from variable_rules import looks_like_identifier


@dataclass
class RepeatedPair:
    before: str
    after: str
    estimate: float
    statistic: float | None
    p_raw: float
    p_holm: float
    effect_size: float | None


@dataclass
class RepeatedResult:
    columns: list[str]
    method: str
    n_total: int
    n_complete: int
    values: np.ndarray
    statistic: float
    df1: float
    df2: float | None
    p_uncorrected: float
    p_primary: float
    epsilon_gg: float | None
    effect_name: str
    effect_size: float
    pairs: list[RepeatedPair]
    warnings: list[str]


def analyze_repeated(
    df: pd.DataFrame,
    columns: list[str],
    method: str,
    scale: str,
    same_people_confirmed: bool = False,
    assumptions_confirmed: bool = False,
) -> RepeatedResult:
    """Perform one-factor within-subject analysis with corrected pairwise tests."""
    if not same_people_confirmed:
        raise ValueError("Confirm all selected columns refer to the SAME participants.")
    if not assumptions_confirmed:
        raise ValueError("Confirm that you reviewed repeated-measures assumptions.")
    if not 3 <= len(columns) <= 8 or len(set(columns)) != len(columns):
        raise ValueError("Choose 3–8 distinct repeated-measure columns.")
    if method not in {"friedman", "rm_anova"}:
        raise ValueError("Choose Friedman or repeated-measures ANOVA.")
    if scale not in {"ordinal", "scale"}:
        raise ValueError("Confirm ordinal or quantitative measurement scale.")
    if method == "rm_anova" and scale != "scale":
        raise ValueError("Repeated-measures ANOVA requires a quantitative outcome.")

    for name in columns:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError("Identifiers are not repeated outcome measurements.")

    raw = df[columns]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    if (raw.notna() & numeric.isna()).any().any():
        raise ValueError("Repeated measurements contain non-numeric responses.")
    finite_data = numeric.to_numpy(dtype=float)
    if np.isinf(finite_data).any():
        raise ValueError("Infinite measurements are not supported.")
    complete = numeric.dropna()
    n = len(complete)
    k = len(columns)
    if n < 8:
        raise ValueError("At least eight complete participants are required.")
    values = complete.to_numpy(dtype=float)
    if np.unique(values).size < 2:
        raise ValueError("Measurements contain no variation.")

    warnings = [
        "Each row must contain aligned measurements from ONE participant; participants must be independent of each other.",
        "Columns must measure the same construct with comparable scoring and known occasion order.",
        "Missing values are removed listwise; review missingness and potential bias.",
        "Differences alone cannot establish a causal treatment effect.",
        "Post-hoc comparisons use Holm correction across all selected occasion pairs.",
    ]
    if n != len(df):
        warnings.append(
            f"{len(df)-n} of {len(df)} participants were excluded due to incomplete measurements."
        )
    if n < 30:
        warnings.append("Small repeated-measures sample; review distributions and precision.")

    if method == "friedman":
        omnibus = stats.friedmanchisquare(*[values[:, i] for i in range(k)])
        statistic, p_uncorrected = float(omnibus.statistic), float(omnibus.pvalue)
        df1, df2 = float(k - 1), None
        p_primary = p_uncorrected
        epsilon = None
        effect = statistic / (n * (k - 1))
        effect_name = "Kendall’s W"
        warnings.extend([
            "Friedman compares within-person ranks, not automatically the original score means.",
            "Its p-value uses the asymptotic chi-square approximation; ties are corrected in SciPy.",
        ])
    else:
        grand_mean = float(values.mean())
        subject_means = values.mean(axis=1)
        occasion_means = values.mean(axis=0)
        ss_total = float(np.square(values - grand_mean).sum())
        ss_subject = float(k * np.square(subject_means - grand_mean).sum())
        ss_occasion = float(n * np.square(occasion_means - grand_mean).sum())
        ss_error = max(0.0, ss_total - ss_subject - ss_occasion)

        df1 = float(k - 1)
        df2 = float((n - 1) * (k - 1))
        if ss_error <= 1e-12 or ss_occasion < 0:
            raise ValueError("Cannot estimate within-subject error variance.")
        statistic = (ss_occasion / df1) / (ss_error / df2)
        p_uncorrected = float(stats.f.sf(statistic, df1, df2))
        effect = ss_occasion / (ss_occasion + ss_error)
        effect_name = "Partial η²"

        covariance = np.cov(values, rowvar=False, ddof=1)
        center = np.eye(k) - np.ones((k, k)) / k
        matrix = center @ covariance @ center
        denom = (k - 1) * float(np.square(matrix).sum())
        if denom <= 1e-15:
            raise ValueError("Cannot estimate Greenhouse–Geisser epsilon.")
        raw_epsilon = float(np.trace(matrix) ** 2 / denom)
        epsilon = float(np.clip(raw_epsilon, 1 / (k - 1), 1))
        p_primary = float(stats.f.sf(statistic, epsilon * df1, epsilon * df2))
        warnings.extend([
            "The primary RM ANOVA p-value uses Greenhouse–Geisser degrees-of-freedom correction.",
            "Uncorrected p is shown for transparency, not as the default inference.",
            "Mauchly’s sphericity test is not implemented and is NOT claimed to be passed.",
            "Review within-person difference distributions, influential observations and design.",
        ])

    if not all(math.isfinite(x) for x in
               [statistic, p_uncorrected, p_primary, effect]):
        raise ValueError("The repeated-measures test returned non-finite results.")

    preliminary = []
    pvalues = []
    for i, j in combinations(range(k), 2):
        diff = np.round(values[:, j] - values[:, i], decimals=10)
        if method == "friedman":
            nonzero = diff[diff != 0]
            if len(nonzero) == 0:
                test_stat, p_raw, effect_pair = None, 1.0, None
            else:
                test = stats.wilcoxon(
                    diff, zero_method="wilcox",
                    alternative="two-sided", method="auto",
                )
                test_stat, p_raw = float(test.statistic), float(test.pvalue)
                ranks = stats.rankdata(np.abs(nonzero), method="average")
                pos = float(ranks[nonzero > 0].sum())
                neg = float(ranks[nonzero < 0].sum())
                effect_pair = (pos - neg) / (pos + neg)
            estimate = float(np.median(diff))
        else:
            sd = float(np.std(diff, ddof=1))
            if sd <= 1e-12:
                raise ValueError(
                    "At least one occasion pair has constant difference scores; "
                    "paired t post-hoc results are undefined for that pair."
                )
            test = stats.ttest_rel(
                values[:, j], values[:, i], alternative="two-sided"
            )
            test_stat, p_raw = float(test.statistic), float(test.pvalue)
            estimate = float(np.mean(diff))
            effect_pair = estimate / sd

        if not math.isfinite(p_raw):
            raise ValueError("A pairwise comparison produced an invalid p-value.")
        pvalues.append(p_raw)
        preliminary.append((i, j, estimate, test_stat, p_raw, effect_pair))

    pairs = []
    for (i, j, estimate, test_stat, p_raw, effect_pair), adj in zip(
        preliminary, holm_adjust(pvalues)
    ):
        pairs.append(RepeatedPair(
            before=columns[i], after=columns[j],
            estimate=estimate, statistic=test_stat,
            p_raw=p_raw, p_holm=adj, effect_size=effect_pair,
        ))

    warnings.append(
        "Holm-adjusted post-hoc p-values do not supply multiplicity-adjusted "
        "confidence intervals; none are reported."
    )
    if method == "friedman":
        warnings.append(
            "The Wilcoxon post-hoc effect is matched-pairs rank-biserial r; "
            "zero differences are omitted from ranking."
        )
    else:
        warnings.append(
            "Paired t post-hoc effect sizes are Cohen’s dz, with after minus before as direction."
        )
    return RepeatedResult(
        columns=list(columns), method=method, n_total=len(df),
        n_complete=n, values=values,
        statistic=statistic, df1=df1, df2=df2,
        p_uncorrected=p_uncorrected, p_primary=p_primary,
        epsilon_gg=epsilon, effect_name=effect_name,
        effect_size=float(effect), pairs=pairs, warnings=warnings,
    )
