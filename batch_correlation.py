"""One variable against several others in one run (Stage 36, spec §4–5).

Example: UCLA against eight coping scales. Each pair is analysed on its own
complete cases (N per pair), and the pairs form one family of hypotheses
whose p-values are adjusted together (Holm by default; raw p kept).

Methods and how uncertainty is obtained (stated in every result):

- Pearson r: coefficient and two-sided p from the validated single-pair
  engine (``correlation.analyze_correlation``: t test of r); 95% CI by
  the Fisher z transformation (justified for Pearson's r under
  approximate bivariate normality).
- Spearman ρ: coefficient and p from the same engine (Monte Carlo
  permutation p, 1,999 resamples with a fixed seed, for n ≤ 500;
  asymptotic above). The CI is a percentile bootstrap over paired
  resamples with a fixed seed. Fisher z is NOT applied to ρ.
- Kendall τ-b: SciPy ``kendalltau``; the exact p when there are no ties
  and n < 50, otherwise the tie-corrected normal approximation; CI by the
  same percentile bootstrap.

Bootstrap resamples in which a variable has no variation cannot produce a
coefficient; they are counted as failed and left out. If more than 10% of
the resamples fail, no interval is reported (status "unavailable").

The coefficient is itself the effect size. A magnitude label is given only
under a named, configurable rule (default: Cohen's 1988 benchmarks for r
and ρ: .10 / .30 / .50); no rule is applied to τ. A p-value at or above α
is never reported as evidence of no association, and an association is
never reported as causation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from zlib import crc32

import numpy as np
import pandas as pd
from scipy import stats

from correlation import analyze_correlation
from multiple_comparisons import adjust as adjust_family
from stat_results import ENGINE_VERSION, Quantity, StructuredResult, Table, _provenance
from variable_rules import looks_like_identifier

METHODS = {"pearson": "Pearson r", "spearman": "Spearman ρ", "kendall": "Kendall τ-b"}
SYMBOLS = {"pearson": "r", "spearman": "ρ", "kendall": "τ"}
MAGNITUDE_RULES = {
    "cohen1988": ("Cohen (1988) benchmarks for r and ρ: |coefficient| < .10 negligible, "
                  ".10–.29 small, .30–.49 moderate, ≥ .50 large; context-dependent conventions, "
                  "not scientific thresholds",
                  ((0.10, "negligible"), (0.30, "small"), (0.50, "moderate"), (math.inf, "large"))),
    "none": ("No magnitude labels", ()),
}
MIN_PAIRS = 5
DEFAULT_SEED = 36
DEFAULT_RESAMPLES = 2000


@dataclass(frozen=True)
class CorrelationRow:
    x: str
    y: str
    n: int
    n_excluded: int
    estimate: float | None
    status: str = "ok"                       # ok | failed (with note)
    note: str = ""
    ci_low: float | None = None
    ci_high: float | None = None
    ci_method: str = ""
    failed_resamples: int = 0
    p_raw: float | None = None
    p_method: str = ""
    p_adjusted: float | None = None
    direction: str = ""
    magnitude: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorrelationFamily:
    method: str
    focal: str
    rows: tuple[CorrelationRow, ...]
    adjustment: str
    adjustment_text: str
    family_size: int
    alpha: float
    ci_level: float
    resamples: int
    seed: int
    magnitude_rule: str
    warnings: tuple[str, ...]
    provenance: dict = field(default_factory=dict)

    @property
    def method_label(self) -> str:
        return METHODS[self.method]

    def row(self, y: str) -> CorrelationRow:
        for row in self.rows:
            if row.y == y:
                return row
        raise KeyError(y)

    def table(self) -> Table:
        symbol = SYMBOLS[self.method]
        adjusted_label = {"holm": "p (Holm)", "bh": "p (BH)", "bonferroni": "p (Bonferroni)",
                          "none": "p (unadjusted)"}[self.adjustment]
        rows = []
        for row in self.rows:
            if row.status != "ok":
                rows.append((row.x, row.y, str(row.n), "Calculation failed", "", "", "", ""))
                continue
            ci = (f"[{row.ci_low:.2f}, {row.ci_high:.2f}]"
                  if row.ci_low is not None and row.ci_high is not None else "Unavailable")
            rows.append((row.x, row.y, str(row.n), _r(row.estimate), ci, _p(row.p_raw),
                         _p(row.p_adjusted), row.magnitude or "—"))
        return Table(f"{self.method_label}: {self.focal} with {len(self.rows)} variables",
                     ("Variable 1", "Variable 2", "N", symbol, f"{self.ci_level:.0%} CI",
                      "p (raw)", adjusted_label, "Magnitude"), tuple(rows))

    def interpretation(self, language: str = "en") -> list[str]:
        """One cautious sentence per pair (never causal, never 'no effect proven')."""
        return [interpret_row(self, row, language) for row in self.rows]

    def structured(self) -> StructuredResult:
        quantities = []
        for row in self.rows:
            key = f"{SYMBOLS[self.method]}:{row.y}"
            label = f"{METHODS[self.method]}: {row.x} – {row.y}"
            if row.status != "ok":
                quantities.append(Quantity.missing(key, label, "failed", row.note))
                continue
            quantities.append(Quantity(
                key, label, row.estimate, ci_low=row.ci_low, ci_high=row.ci_high,
                ci_level=self.ci_level if row.ci_low is not None else None,
                ci_method=row.ci_method, p=row.p_raw, p_method=row.p_method,
                note=f"N = {row.n}; adjusted p = {_p(row.p_adjusted)} ({self.adjustment})"))
        return StructuredResult(
            "batch_correlation", self.table().title,
            {"n_pairs": [row.n for row in self.rows]},
            {"variables": [self.focal, *[row.y for row in self.rows]],
             "options": {"method": self.method, "adjustment": self.adjustment,
                         "ci_level": self.ci_level, "resamples": self.resamples,
                         "seed": self.seed, "magnitude_rule": self.magnitude_rule,
                         "alpha": self.alpha}},
            tuple(quantities), warnings=self.warnings, tables=(self.table(),),
            provenance=self.provenance)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["rows"] = [asdict(row) for row in self.rows]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "CorrelationFamily":
        rows = tuple(CorrelationRow(**{**row, "warnings": tuple(row.get("warnings", ()))})
                     for row in data["rows"])
        return cls(**{**data, "rows": rows, "warnings": tuple(data.get("warnings", ())),
                      "provenance": dict(data.get("provenance", {}))})


def _text_only(values: pd.Series) -> bool:
    """A column with values, none of them numeric (codes such as 'P001')."""
    return bool(values.notna().any()) and bool(pd.to_numeric(values, errors="coerce").isna().all())


def _r(value: float) -> str:
    text = f"{value:.2f}"
    return text.replace("0.", ".", 1) if abs(value) < 1 else text


def _p(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return "< .001" if value < 0.001 else f"{value:.3f}".replace("0.", ".", 1)


def magnitude_label(value: float, method: str, rule: str) -> str:
    if rule == "none" or method == "kendall":
        return ""
    for limit, label in MAGNITUDE_RULES[rule][1]:
        if abs(value) < limit:
            return label
    return ""


def _pair_seed(seed: int, x: str, y: str) -> list[int]:
    """A seed for one pair that does not depend on the order of the pairs."""
    return [seed, crc32(x.encode("utf-8")), crc32(y.encode("utf-8"))]


def _rank_rows(matrix: np.ndarray) -> np.ndarray:
    return stats.rankdata(matrix, axis=1)


def bootstrap_ci(x: np.ndarray, y: np.ndarray, method: str, *, resamples: int, seed,
                 level: float) -> tuple[float | None, float | None, int, str]:
    """Percentile bootstrap CI of ρ or τ over paired resamples.

    Returns (low, high, failed resamples, method text); low/high are None
    when too many resamples failed."""
    rng = np.random.default_rng(seed)
    n = x.size
    index = rng.integers(0, n, size=(resamples, n))
    xs, ys = x[index], y[index]
    varied = (np.ptp(xs, axis=1) > 0) & (np.ptp(ys, axis=1) > 0)
    values = np.full(resamples, np.nan)
    if method == "spearman":
        rx, ry = _rank_rows(xs[varied]), _rank_rows(ys[varied])
        rx -= rx.mean(axis=1, keepdims=True)
        ry -= ry.mean(axis=1, keepdims=True)
        values[varied] = (rx * ry).sum(axis=1) / np.sqrt((rx ** 2).sum(axis=1) *
                                                         (ry ** 2).sum(axis=1))
    elif method == "kendall":
        for i in np.flatnonzero(varied):
            values[i] = stats.kendalltau(xs[i], ys[i], variant="b").statistic
    else:
        raise ValueError("The bootstrap interval is used for Spearman and Kendall only.")
    finite = values[np.isfinite(values)]
    failed = resamples - int(finite.size)
    text = (f"percentile bootstrap, {resamples:,} paired resamples, seed {seed[0]}"
            + (f"; {failed} resample(s) without variation left out" if failed else ""))
    if finite.size < 0.9 * resamples:
        return None, None, failed, text + "; too many failed resamples for an interval"
    low, high = np.percentile(finite, [100 * (1 - level) / 2, 100 * (1 + level) / 2])
    return float(low), float(high), failed, text


def _kendall(x: np.ndarray, y: np.ndarray) -> tuple[float, float, str]:
    ties = np.unique(x).size < x.size or np.unique(y).size < y.size
    if not ties and x.size < 50:
        result = stats.kendalltau(x, y, variant="b", method="exact")
        return float(result.statistic), float(result.pvalue), "two-sided exact p (no ties, n < 50)"
    result = stats.kendalltau(x, y, variant="b", method="asymptotic")
    return (float(result.statistic), float(result.pvalue),
            "two-sided p, normal approximation with tie correction")


def correlate_many(df: pd.DataFrame, focal: str, others: list[str], *, method: str = "spearman",
                   adjust: str = "holm", alpha: float = 0.05, ci_level: float = 0.95,
                   resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED,
                   magnitude_rule: str = "cohen1988",
                   pearson_assumptions_confirmed: bool = False,
                   spearman_p: str = "permutation") -> CorrelationFamily:
    """Correlate ``focal`` with each of ``others`` as one family of tests.

    ``spearman_p``: "permutation" (default, as the single-pair analysis) or
    "asymptotic" (the t approximation with n − 2 df that SPSS reports), so
    that published SPSS results can be reproduced; the method is stated in
    every row either way."""
    if method not in METHODS:
        raise ValueError("Choose Pearson, Spearman or Kendall.")
    if magnitude_rule not in MAGNITUDE_RULES:
        raise ValueError(f"Unknown magnitude rule: {magnitude_rule}")
    if not 0 < alpha < 1 or not 0 < ci_level < 1:
        raise ValueError("alpha and the CI level must lie between 0 and 1.")
    if resamples < 200:
        raise ValueError("Use at least 200 bootstrap resamples.")
    if spearman_p not in ("permutation", "asymptotic"):
        raise ValueError("Spearman p: permutation or asymptotic.")
    others = list(others)
    if not others:
        raise ValueError("Choose at least one variable to correlate with.")
    if len(set(others)) != len(others) or focal in others:
        raise ValueError("Choose each variable once, and not the focal variable itself.")
    for name in [focal, *others]:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if _text_only(df[name]):
            raise ValueError(f"{name} holds text, not numbers (an identifier?); it cannot be "
                             "analysed as a score.")
        if looks_like_identifier(name):
            raise ValueError(f"{name} is an identifier, not a research score.")
    if method == "pearson" and not pearson_assumptions_confirmed:
        raise ValueError("Confirm the Pearson linearity and outlier review first.")

    rows: list[CorrelationRow] = []
    for other in others:
        rows.append(_pair(df, focal, other, method, ci_level, resamples, seed, magnitude_rule,
                          spearman_p))
    adjustment = adjust_family([row.p_raw if row.status == "ok" else None for row in rows],
                               adjust)
    rows = [CorrelationRow(**{**asdict(row), "p_adjusted": adjusted})
            for row, adjusted in zip(rows, adjustment.adjusted)]
    warnings = [
        "Each coefficient is the effect size for its pair; the family shares one "
        f"multiple-comparison adjustment ({adjustment.description}; {adjustment.family_size} tests).",
        "Raw p-values are reported unchanged next to the adjusted ones.",
        "Correlation does not establish causation.",
        "A p-value at or above α is not evidence that there is no association.",
    ]
    if any(row.status != "ok" for row in rows):
        warnings.append("Pairs whose calculation failed are not part of the adjusted family.")
    warnings += unadjusted_warning(adjust, adjustment.family_size)
    return CorrelationFamily(
        method=method, focal=focal, rows=tuple(rows), adjustment=adjust,
        adjustment_text=adjustment.description, family_size=adjustment.family_size,
        alpha=alpha, ci_level=ci_level, resamples=resamples, seed=seed,
        magnitude_rule=magnitude_rule, warnings=tuple(warnings),
        provenance=_provenance(seed=seed, resamples=resamples,
                               seed_rule="per pair: [seed, crc32(x), crc32(y)]",
                               engine=ENGINE_VERSION))


def _pair(df, focal, other, method, ci_level, resamples, seed, rule,
          spearman_p="permutation") -> CorrelationRow:
    numeric = df[[focal, other]].apply(pd.to_numeric, errors="coerce")
    complete = numeric.dropna()
    n, excluded = int(len(complete)), int(len(df) - len(complete))
    warnings: list[str] = []
    if excluded:
        warnings.append(f"{excluded} record(s) without both values were left out of this pair.")
    try:
        if n < MIN_PAIRS:
            raise ValueError(f"At least {MIN_PAIRS} complete pairs are needed (found {n}).")
        x = complete[focal].to_numpy(dtype=float)
        y = complete[other].to_numpy(dtype=float)
        if np.unique(x).size < 2 or np.unique(y).size < 2:
            raise ValueError("Both variables need variation in the complete pairs.")
        ci_low = ci_high = None
        failed = 0
        if method == "kendall":
            estimate, p, p_method = _kendall(x, y)
            ci_low, ci_high, failed, ci_method = bootstrap_ci(
                x, y, "kendall", resamples=resamples, seed=_pair_seed(seed, focal, other),
                level=ci_level)
        else:
            single = analyze_correlation(df, focal, other, method, "scale", "scale",
                                         pearson_checked=(method == "pearson"))
            estimate, p, p_method = single.coefficient, single.p_value, single.p_method
            if method == "spearman" and spearman_p == "asymptotic":
                p = float(stats.spearmanr(x, y).pvalue)
                p_method = "two-sided t approximation with n − 2 df (as reported by SPSS)"
            if method == "pearson":
                ci_low, ci_high = single.ci_low, single.ci_high
                ci_method = "Fisher z transformation"
            else:
                ci_low, ci_high, failed, ci_method = bootstrap_ci(
                    x, y, "spearman", resamples=resamples, seed=_pair_seed(seed, focal, other),
                    level=ci_level)
        if n < 30:
            warnings.append("Small sample: the estimate and its interval are imprecise.")
        direction = "positive" if estimate > 0 else "negative" if estimate < 0 else "none"
        return CorrelationRow(focal, other, n, excluded, float(estimate), ci_low=ci_low,
                              ci_high=ci_high, ci_method=ci_method, failed_resamples=failed,
                              p_raw=float(p), p_method=p_method, direction=direction,
                              magnitude=magnitude_label(estimate, method, rule),
                              warnings=tuple(warnings))
    except ValueError as error:
        return CorrelationRow(focal, other, n, excluded, None, status="failed", note=str(error),
                              warnings=tuple(warnings))


TEMPLATES = {
    "en": {
        "assoc": "{x} and {y}: {sym} = {est}, {ci}, {plabel} = {padj}. A {direction} "
                 "{magnitude}association in this sample; it does not show causation.",
        "no_evidence": "{x} and {y}: {sym} = {est}, {ci}, {plabel} = {padj}. These data do "
                       "not provide evidence of an association at α = {alpha}; this does not "
                       "show that there is no association.",
        "failed": "{x} and {y}: not calculated — {note}",
        "positive": "positive", "negative": "negative", "none": "",
        "ci": "{level} CI [{low}, {high}]", "no_ci": "no interval",
    },
    "lv": {
        "assoc": "{x} un {y}: {sym} = {est}, {ci}, {plabel} = {padj}. Šajā izlasē {direction} "
                 "{magnitude}sakarība; tā nepierāda cēloņsakarību.",
        "no_evidence": "{x} un {y}: {sym} = {est}, {ci}, {plabel} = {padj}. Dati nesniedz "
                       "pierādījumus sakarībai pie α = {alpha}; tas nepierāda, ka sakarības nav.",
        "failed": "{x} un {y}: nav aprēķināts — {note}",
        "positive": "pozitīva", "negative": "negatīva", "none": "",
        "ci": "{level} TI [{low}, {high}]", "no_ci": "bez intervāla",
    },
    "ru": {
        "assoc": "{x} и {y}: {sym} = {est}, {ci}, {plabel} = {padj}. В этой выборке "
                 "{direction} {magnitude}связь; она не доказывает причинность.",
        "no_evidence": "{x} и {y}: {sym} = {est}, {ci}, {plabel} = {padj}. Данные не дают "
                       "оснований говорить о связи при α = {alpha}; это не доказывает, что "
                       "связи нет.",
        "failed": "{x} и {y}: не вычислено — {note}",
        "positive": "положительная", "negative": "отрицательная", "none": "",
        "ci": "{level} ДИ [{low}, {high}]", "no_ci": "без интервала",
    },
}
# The p-value a sentence reports, named by the procedure actually applied
# (Stage 36.8, review finding K4: "p(adjusted)" was written even when the
# researcher chose no adjustment). Shared with batch_groups.
P_LABELS = {
    "en": {"holm": "p (Holm)", "bh": "p (Benjamini–Hochberg)", "bonferroni": "p (Bonferroni)",
           "none": "p (unadjusted)"},
    "lv": {"holm": "p (Holma korekcija)", "bh": "p (Benjamini–Hohberga korekcija)",
           "bonferroni": "p (Bonferroni korekcija)", "none": "p (bez korekcijas)"},
    "ru": {"holm": "p (поправка Холма)", "bh": "p (поправка Бенджамини–Хохберга)",
           "bonferroni": "p (поправка Бонферрони)", "none": "p (без поправки)"},
}


def p_label(adjustment: str, language: str = "en") -> str:
    labels = P_LABELS.get(language, P_LABELS["en"])
    return labels.get(adjustment, P_LABELS["en"].get(adjustment, "p"))


def unadjusted_warning(adjustment: str, family_size: int) -> list[str]:
    """The risk of an unadjusted family, said once (review finding K4)."""
    if adjustment != "none" or family_size < 2:
        return []
    return [f"No multiple-comparison adjustment: {family_size} tests were run, so the chance "
            "of at least one false positive is higher than α. Report the p-values as unadjusted."]


MAGNITUDE_WORDS = {
    "en": {"negligible": "negligible ", "small": "small ", "moderate": "moderate ", "large": "large "},
    "lv": {"negligible": "niecīga ", "small": "vāja ", "moderate": "mērena ", "large": "cieša "},
    "ru": {"negligible": "пренебрежимо малая ", "small": "слабая ", "moderate": "умеренная ",
           "large": "сильная "},
}


def interpret_row(family: CorrelationFamily, row: CorrelationRow, language: str = "en") -> str:
    words = TEMPLATES.get(language, TEMPLATES["en"])
    if row.status != "ok":
        return words["failed"].format(x=row.x, y=row.y, note=row.note)
    ci = (words["ci"].format(level=f"{family.ci_level:.0%}", low=_r(row.ci_low),
                             high=_r(row.ci_high))
          if row.ci_low is not None else words["no_ci"])
    fields = dict(x=row.x, y=row.y, sym=SYMBOLS[family.method], est=_r(row.estimate), ci=ci,
                  padj=_p(row.p_adjusted), plabel=p_label(family.adjustment, language),
                  alpha=str(family.alpha).replace("0.", ".", 1),
                  direction=words[row.direction],
                  magnitude=MAGNITUDE_WORDS.get(language, MAGNITUDE_WORDS["en"]).get(
                      row.magnitude, ""))
    significant = row.p_adjusted is not None and row.p_adjusted < family.alpha
    return words["assoc" if significant else "no_evidence"].format(**fields)
