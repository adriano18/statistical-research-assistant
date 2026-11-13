"""Path models of mediation and moderation (Stage 37, Issue #66).

Structures equivalent to PROCESS Models 1, 4, 7 and 14 (Hayes, 2022),
estimated by this program, not by the PROCESS macro:

* **Model 4** — X → M₁ … M_k → Y: simple (k = 1) or parallel mediation.
  ``M_j = a0_j + a_j X + C`` and ``Y = b0 + c′X + Σ b_j M_j + C``; the total
  effect equation is ``Y = c0 + c X + C``. Indirect effect ``a_j b_j``.
* **Model 1** — ``Y = b0 + b1 X + b2 W + b3 XW + C``: the conditional effect
  of X is ``b1 + b3 W`` (simple slopes) with Johnson–Neyman values of W.
* **Model 7** — W moderates X → M: ``M_j = a0 + a1 X + a2 W + a3 XW + C``,
  ``Y = b0 + c′X + Σ b_j M_j + C``. Conditional indirect effect
  ``(a1 + a3 w) b``; index of moderated mediation ``a3 b``.
* **Model 14** — W moderates M → Y: ``M_j = a0 + a X + C``,
  ``Y = b0 + c′X + Σ b1_j M_j + b2 W + Σ b3_j M_j W + C``. Conditional
  indirect effect ``a (b1 + b3 w)``; index ``a b3``.

Rules
-----
* The model number, the mediators and (for 7 and 14) the moderated path
  are the researcher's statements in :class:`ProcessSpec`. Nothing here
  chooses them, and nothing reads a p-value to decide what to estimate.
* Missing data: listwise deletion over every model variable; all equations
  use the same complete cases (:class:`MissingSummary` says how many and
  compares the cases left out with the cases analysed, descriptively).
* Every equation is an ordinary least squares regression fitted with
  statsmodels, with the researcher's covariates in every equation, and
  optional HC3 coefficient standard errors (t-based p and intervals, as
  :mod:`regression_analysis` does). Model F and ΔR² tests stay classical.
* Indirect effects, indices of moderated mediation and conditional indirect
  effects get percentile bootstrap intervals: ``resamples`` resamples of the
  complete cases, drawn by :func:`bootstrap_indices` from a fixed seed (both
  reported). Each resample is re-estimated by numpy least squares on the
  same design; resamples with a singular design are left out and counted.
  The interval is the (1 ± level)/2 quantile with linear interpolation
  (Hyndman–Fan type 7, numpy's default). Conditioning values of W stay
  fixed at the values of the analysis sample.
* Conditioning values of W: mean − 1 SD, mean, mean + 1 SD (sample SD,
  n − 1) and the 16th, 50th and 84th percentiles (type 7); a W with two
  values is evaluated at both. Values outside the observed range are kept
  and flagged as extrapolation.
* Mean-centring (optional) applies to the variables that form products,
  wherever they are predictors; conditional effects are always reported at
  W values in the original metric, so they do not depend on centring.
* Standardized coefficients β = b·SD(predictor)/SD(outcome) are given for
  quantitative predictors; they are not defined for the constant, for
  products and for 0/1 predictors.
* Effects are conditional associations. "Effect" is the conventional
  name of these quantities; nothing here establishes causation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import math
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan

from process_text import t as _t
from stat_results import Quantity, StructuredResult, Table, _provenance
from variable_rules import looks_like_identifier

ENGINE_VERSION = "stage37.1"
MODELS = ("1", "4", "7", "14")
MEDIATION_MODELS = ("4", "7", "14")
MODERATED_MODELS = ("1", "7", "14")
DEFAULT_RESAMPLES = 5000
DEFAULT_SEED = 37066
DEFAULT_LEVEL = 0.95
MAX_MEDIATORS = 4
MAX_COVARIATES = 8
SMALL_SAMPLE = 50
VIF_LIMIT = 5.0
MIN_LEFT_OUT = 2              # fewer left-out cases: no comparison with the analysed cases
W_PERCENTILES = (16.0, 50.0, 84.0)


# ------------------------------------------------------------------ specification
@dataclass(frozen=True)
class ProcessSpec:
    """What the researcher states: the model number, X, Y, the mediators, W,
    the covariates and the estimation options. Never inferred."""

    model: str
    x: str
    y: str
    mediators: tuple[str, ...] = ()
    w: str | None = None
    covariates: tuple[str, ...] = ()
    center: bool = False
    hc3: bool = False
    resamples: int = DEFAULT_RESAMPLES
    seed: int = DEFAULT_SEED
    level: float = DEFAULT_LEVEL
    w_values: tuple[float, ...] = ()        # extra conditioning values chosen by the researcher

    def variables(self) -> list[str]:
        """Every model variable, in a fixed order: X, mediators, W, Y, covariates."""
        names = [self.x, *self.mediators]
        if self.w:
            names.append(self.w)
        names.append(self.y)
        names += list(self.covariates)
        return names


def check_spec(spec: ProcessSpec) -> ProcessSpec:
    """The specification, normalised, or ValueError explaining what is missing."""
    model = str(spec.model).strip()
    if model not in MODELS:
        raise ValueError("State the model: 1, 4, 7 or 14. The program does not choose it.")
    mediators = tuple(str(m) for m in spec.mediators or ())
    covariates = tuple(str(c) for c in spec.covariates or ())
    w = str(spec.w) if spec.w else None
    if not spec.x or not spec.y:
        raise ValueError("Choose X and Y.")
    if model in MEDIATION_MODELS and not mediators:
        raise ValueError(f"Model {model} needs at least one mediator named by the researcher.")
    if model == "1" and mediators:
        raise ValueError("Model 1 has no mediator; use Model 4, 7 or 14 for a mediator.")
    if model in MODERATED_MODELS and not w:
        raise ValueError(f"Model {model} needs a moderator W.")
    if model == "4" and w:
        raise ValueError("Model 4 has no moderator; use Model 7 or 14 and state which path W "
                         "moderates.")
    if len(mediators) > MAX_MEDIATORS:
        raise ValueError(f"At most {MAX_MEDIATORS} parallel mediators.")
    if len(covariates) > MAX_COVARIATES:
        raise ValueError(f"At most {MAX_COVARIATES} covariates.")
    names = [spec.x, *mediators, *([w] if w else []), spec.y, *covariates]
    if len(names) != len(set(names)):
        raise ValueError("A variable has more than one role; every role needs its own variable.")
    if int(spec.resamples) < 200:
        raise ValueError("A percentile bootstrap needs at least 200 resamples (5000 is the "
                         "default).")
    if not 0.5 < float(spec.level) < 1:
        raise ValueError("The interval level must be between 0.5 and 1.")
    values = tuple(float(v) for v in spec.w_values or ())
    if values and not all(math.isfinite(v) for v in values):
        raise ValueError("Chosen values of W must be finite numbers.")
    return replace(spec, model=model, mediators=mediators, covariates=covariates, w=w,
                   resamples=int(spec.resamples), seed=int(spec.seed), level=float(spec.level),
                   w_values=values, center=bool(spec.center), hc3=bool(spec.hc3))


# ------------------------------------------------------------------ results
@dataclass(frozen=True)
class Coefficient:
    term: str               # display name ("Constant", a variable, "X × W")
    key: str                # internal term key ("const", "x", "w", "x*w", "m0", "m0*w", "c0")
    b: float
    se: float
    t: float
    p: float
    ci_low: float
    ci_high: float
    beta: float | None = None     # standardized coefficient where defined
    vif: float | None = None


@dataclass(frozen=True)
class EquationResult:
    key: str                # "m0", "y", "total"
    outcome: str
    terms: tuple[str, ...]  # term keys, constant first
    coefficients: tuple[Coefficient, ...]
    n: int
    r_squared: float
    adj_r_squared: float
    f_value: float
    df_model: int
    df_resid: int
    f_p: float
    mse: float              # residual variance (SSE / df_resid)
    se_type: str            # "OLS" or "HC3"
    shapiro_p: float | None
    bp_p: float | None
    cooks_max: float
    cooks_over: int         # Cook's D > 4/N
    leverage_max: float
    leverage_over: int      # leverage > 2p/N (p = parameters including the constant)
    max_vif: float | None
    residuals: np.ndarray = field(repr=False, compare=False, default=None)
    fitted: np.ndarray = field(repr=False, compare=False, default=None)
    cooks: np.ndarray = field(repr=False, compare=False, default=None)
    leverage: np.ndarray = field(repr=False, compare=False, default=None)
    cov: np.ndarray = field(repr=False, compare=False, default=None)   # of the coefficients

    def coefficient(self, key: str) -> Coefficient:
        for coefficient in self.coefficients:
            if coefficient.key == key:
                return coefficient
        raise KeyError(key)

    def index(self, key: str) -> int:
        return self.terms.index(key)


@dataclass(frozen=True)
class Estimate:
    """A model quantity with its interval (analytic or bootstrap)."""

    key: str
    label: str
    value: float
    se: float | None = None       # analytic SE, or the bootstrap SD for bootstrap estimates
    t: float | None = None
    p: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    ci_method: str = ""
    mediator: str = ""
    w: float | None = None
    where: str = ""               # key of the W position ("w.minus", "w.p16", ...)
    df: int | None = None

    @property
    def excludes_zero(self) -> bool:
        return (self.ci_low is not None and self.ci_high is not None
                and (self.ci_low > 0 or self.ci_high < 0))


@dataclass(frozen=True)
class WPoint:
    where: str                    # text key: w.minus, w.mean, w.plus, w.p16, w.p50, w.p84, ...
    value: float
    outside: bool                 # outside the observed range of W


@dataclass(frozen=True)
class InteractionTest:
    equation: str                 # outcome variable
    product: str                  # display name of the product(s)
    keys: tuple[str, ...]         # term keys of the product(s)
    delta_r2: float
    f_value: float
    df1: int
    df2: int
    p: float
    f2: float
    robust_f: float | None = None # HC3 Wald F of the product(s) when HC3 is used
    robust_p: float | None = None


@dataclass(frozen=True)
class JohnsonNeyman:
    points: tuple[float, ...]             # values of W in the observed range where p = alpha
    below: tuple[float, ...]              # share of the analysis sample below each point
    above: tuple[float, ...]
    effects: tuple[tuple[float, float, float], ...]   # (effect, se, p) at each point
    significant_everywhere: bool | None   # when there is no point: the state over the range
    w_min: float
    w_max: float
    alpha: float


@dataclass(frozen=True)
class MissingSummary:
    policy: str
    n_total: int
    n_complete: int
    by_variable: tuple[tuple[str, int], ...]
    comparison: tuple[tuple, ...]          # (name, n_in, mean_in, sd_in, n_out, mean_out, sd_out, smd)
    comparison_meaningful: bool

    @property
    def excluded(self) -> int:
        return self.n_total - self.n_complete


@dataclass(frozen=True)
class BootstrapInfo:
    resamples: int
    valid: int
    seed: int
    level: float
    method: str = "percentile bootstrap (linear interpolation, Hyndman–Fan type 7)"
    indices_sha256: str = ""


@dataclass
class ProcessResult:
    spec: ProcessSpec
    n_total: int
    n: int
    missing: MissingSummary
    equations: tuple[EquationResult, ...]
    effects: tuple[Estimate, ...]                  # analytic: paths, direct, total, interaction
    indirect: tuple[Estimate, ...]                 # bootstrap: indirect, standardized, index, conditional
    conditional: tuple[Estimate, ...]              # analytic conditional effects at W values
    interactions: tuple[InteractionTest, ...]
    w_points: tuple[WPoint, ...]
    johnson_neyman: JohnsonNeyman | None
    bootstrap: BootstrapInfo | None
    centering: dict                                 # variable -> constant subtracted
    sds: dict                                       # variable -> sample SD (n - 1)
    notes: tuple[tuple[str, dict], ...]             # (process_text key, params)
    samples: dict = field(default_factory=dict, repr=False)   # bootstrap draws by key
    indices: np.ndarray | None = field(default=None, repr=False)
    data: pd.DataFrame | None = field(default=None, repr=False)   # the complete cases

    # -- convenience
    @property
    def model(self) -> str:
        return self.spec.model

    @property
    def warnings(self) -> tuple[str, ...]:
        """The notes in English (stored with the run)."""
        return tuple(_t("en", key, **params) for key, params in self.notes)

    def equation(self, key: str) -> EquationResult:
        for equation in self.equations:
            if equation.key == key:
                return equation
        raise KeyError(key)

    def estimate(self, key: str) -> Estimate:
        for estimate in (*self.effects, *self.indirect, *self.conditional):
            if estimate.key == key:
                return estimate
        raise KeyError(key)

    def structured(self) -> StructuredResult:
        return structured_result(self)


# ------------------------------------------------------------------ helpers
def bootstrap_indices(n: int, resamples: int, seed: int) -> np.ndarray:
    """Row indices of every bootstrap resample: ``resamples`` × ``n`` draws
    with replacement from ``numpy.random.default_rng(seed)`` in one call."""
    rng = np.random.default_rng(int(seed))
    return rng.integers(0, int(n), size=(int(resamples), int(n)))


def percentile_interval(values: np.ndarray, level: float) -> tuple[float, float]:
    """The percentile interval: quantiles (1 − level)/2 and (1 + level)/2 with
    linear interpolation between order statistics (type 7)."""
    low, high = np.percentile(np.asarray(values, dtype=float),
                              [50.0 * (1 - level), 50.0 * (1 + level)])
    return float(low), float(high)


def _fmt(value: float, digits: int = 3) -> str:
    text = f"{float(value):.{digits}f}"
    return "0." + "0" * digits if text in ("-0." + "0" * digits,) else text


def _p_text(p: float) -> str:
    from correlation_reporting import apa_p_value

    return apa_p_value(min(max(float(p), 0.0), 1.0))


def _numeric(df: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    for name in names:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError(f"{name} looks like an identifier, not a measurement.")
    raw = df[names]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    bad = [n for n in names if bool((raw[n].notna() & numeric[n].isna()).any())]
    if bad:
        raise ValueError(f"Non-numeric values in {', '.join(bad)}; recode them first.")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values[~np.isnan(values)]).all():
        raise ValueError("Infinite values are not supported.")
    return numeric


def _missing_summary(numeric: pd.DataFrame, names: list[str]) -> MissingSummary:
    complete_mask = numeric[names].notna().all(axis=1).to_numpy()
    n_total, n_complete = len(numeric), int(complete_mask.sum())
    by_variable = tuple((name, int(numeric[name].isna().sum())) for name in names)
    left_out = numeric.loc[~complete_mask, names]
    analysed = numeric.loc[complete_mask, names]
    meaningful = len(left_out) >= MIN_LEFT_OUT
    rows = []
    if meaningful:
        for name in names:
            out = left_out[name].dropna()
            inside = analysed[name]
            sd_in = float(inside.std(ddof=1)) if len(inside) > 1 else float("nan")
            if len(out) >= MIN_LEFT_OUT:
                mean_out, sd_out = float(out.mean()), float(out.std(ddof=1))
                smd = (mean_out - float(inside.mean())) / sd_in if sd_in > 0 else float("nan")
            else:
                mean_out = sd_out = smd = float("nan")
            rows.append((name, int(len(inside)), float(inside.mean()), sd_in, int(len(out)),
                         mean_out, sd_out, smd))
    return MissingSummary("listwise", n_total, n_complete, by_variable, tuple(rows), meaningful)


def _distinct(values: np.ndarray) -> int:
    return int(np.unique(values).size)


def _terms(spec: ProcessSpec) -> dict[str, list[str]]:
    """Equation key -> predictor term keys (constant excluded), in order."""
    k = len(spec.mediators)
    covs = [f"c{i}" for i in range(len(spec.covariates))]
    mediators = [f"m{j}" for j in range(k)]
    equations: dict[str, list[str]] = {}
    if spec.model == "4":
        for j in range(k):
            equations[f"m{j}"] = ["x", *covs]
        equations["y"] = ["x", *mediators, *covs]
        equations["total"] = ["x", *covs]
    elif spec.model == "1":
        equations["y"] = ["x", "w", "x*w", *covs]
    elif spec.model == "7":
        for j in range(k):
            equations[f"m{j}"] = ["x", "w", "x*w", *covs]
        equations["y"] = ["x", *mediators, *covs]
    elif spec.model == "14":
        for j in range(k):
            equations[f"m{j}"] = ["x", *covs]
        equations["y"] = ["x", *mediators, "w", *[f"m{j}*w" for j in range(k)], *covs]
    return equations


def _outcome_key(spec: ProcessSpec, equation: str) -> str:
    return "y" if equation in ("y", "total") else equation


class _Design:
    """Column arrays of the complete cases, centred where products are formed."""

    def __init__(self, spec: ProcessSpec, frame: pd.DataFrame):
        self.spec = spec
        self.raw: dict[str, np.ndarray] = {"x": frame[spec.x].to_numpy(float),
                                           "y": frame[spec.y].to_numpy(float)}
        for j, name in enumerate(spec.mediators):
            self.raw[f"m{j}"] = frame[name].to_numpy(float)
        if spec.w:
            self.raw["w"] = frame[spec.w].to_numpy(float)
        for i, name in enumerate(spec.covariates):
            self.raw[f"c{i}"] = frame[name].to_numpy(float)
        self.n = len(frame)
        centred = []
        if spec.center:
            if spec.model in ("1", "7"):
                centred = ["x", "w"]
            elif spec.model == "14":
                centred = [*(f"m{j}" for j in range(len(spec.mediators))), "w"]
        self.centering = {key: float(self.raw[key].mean()) for key in centred}

    def predictor(self, key: str, rows: np.ndarray | None = None) -> np.ndarray:
        """A predictor column: centred if its variable forms a product."""
        if "*" in key:
            left, right = key.split("*")
            return self.predictor(left, rows) * self.predictor(right, rows)
        values = self.raw[key] if rows is None else self.raw[key][rows]
        return values - self.centering.get(key, 0.0)

    def matrix(self, terms: list[str], rows: np.ndarray | None = None) -> np.ndarray:
        n = self.n if rows is None else len(rows)
        return np.column_stack([np.ones(n), *(self.predictor(t, rows) for t in terms)])

    def outcome(self, key: str, rows: np.ndarray | None = None) -> np.ndarray:
        values = self.raw[key]
        return values if rows is None else values[rows]


def _term_name(spec: ProcessSpec, key: str, language: str = "en") -> str:
    if key == "const":
        return _t(language, "cell.constant")
    if "*" in key:
        left, right = key.split("*")
        return f"{_term_name(spec, left, language)} × {_term_name(spec, right, language)}"
    if key == "x":
        return spec.x
    if key == "y":
        return spec.y
    if key == "w":
        return spec.w or "W"
    if key.startswith("m"):
        return spec.mediators[int(key[1:])]
    if key.startswith("c"):
        return spec.covariates[int(key[1:])]
    return key


def term_name(spec: ProcessSpec, key: str, language: str = "en") -> str:
    """Display name of a term key (public for reporting)."""
    return _term_name(spec, key, language)


def _vifs(matrix: np.ndarray) -> list[float | None]:
    """VIF of every predictor column (constant excluded): 1 / (1 − R²) of the
    predictor regressed on the other predictors with a constant."""
    k = matrix.shape[1] - 1
    if k < 2:
        return [None] * k
    out: list[float | None] = []
    for j in range(1, k + 1):
        target = matrix[:, j]
        others = np.delete(matrix, j, axis=1)
        fit = sm.OLS(target, others).fit()
        r2 = float(fit.rsquared)
        out.append(float("inf") if r2 >= 1 else 1.0 / (1.0 - r2))
    return out


def _fit_equation(spec: ProcessSpec, design: _Design, key: str, terms: list[str],
                  sds: dict) -> tuple[EquationResult, object]:
    outcome_key = _outcome_key(spec, key)
    y = design.outcome(outcome_key)
    X = design.matrix(terms)
    if np.linalg.matrix_rank(X) < X.shape[1]:
        names = ", ".join(_term_name(spec, t) for t in terms)
        raise ValueError(f"The predictors of the {_term_name(spec, outcome_key)} equation "
                         f"({names}) are perfectly collinear; remove a redundant variable.")
    model = sm.OLS(y, X).fit()
    inferred = model.get_robustcov_results(cov_type="HC3", use_t=True) if spec.hc3 else model
    params = np.asarray(inferred.params, dtype=float)
    bse = np.asarray(inferred.bse, dtype=float)
    tvalues = np.asarray(inferred.tvalues, dtype=float)
    pvalues = np.asarray(inferred.pvalues, dtype=float)
    intervals = np.asarray(inferred.conf_int(alpha=1 - spec.level), dtype=float)
    cov = np.asarray(inferred.cov_params(), dtype=float)
    vifs = _vifs(X)
    keys = ["const", *terms]
    outcome_name = _term_name(spec, outcome_key)
    sd_outcome = sds[outcome_name]
    coefficients = []
    for j, term in enumerate(keys):
        beta = None
        if term != "const" and "*" not in term:
            values = design.raw[term]
            if _distinct(values) > 2 and sd_outcome > 0:
                beta = float(params[j] * float(np.std(values, ddof=1)) / sd_outcome)
        coefficients.append(Coefficient(
            term=_term_name(spec, term), key=term, b=float(params[j]), se=float(bse[j]),
            t=float(tvalues[j]), p=float(pvalues[j]), ci_low=float(intervals[j, 0]),
            ci_high=float(intervals[j, 1]), beta=beta, vif=None if j == 0 else vifs[j - 1]))
    residuals = np.asarray(model.resid, dtype=float)
    n = len(y)
    shapiro_p = float(stats.shapiro(residuals).pvalue) if 3 <= n <= 5000 else None
    bp_p = float(het_breuschpagan(residuals, X)[1])
    influence = model.get_influence()
    cooks = np.asarray(influence.cooks_distance[0], dtype=float)
    leverage = np.asarray(influence.hat_matrix_diag, dtype=float)
    p_params = X.shape[1]
    finite_vifs = [v for v in vifs if v is not None]
    result = EquationResult(
        key=key, outcome=outcome_name, terms=tuple(keys), coefficients=tuple(coefficients),
        n=n, r_squared=float(model.rsquared), adj_r_squared=float(model.rsquared_adj),
        f_value=float(model.fvalue), df_model=int(round(model.df_model)),
        df_resid=int(round(model.df_resid)), f_p=float(model.f_pvalue),
        mse=float(model.mse_resid), se_type="HC3" if spec.hc3 else "OLS",
        shapiro_p=shapiro_p, bp_p=bp_p, cooks_max=float(np.max(cooks)),
        cooks_over=int(np.sum(cooks > 4 / n)), leverage_max=float(np.max(leverage)),
        leverage_over=int(np.sum(leverage > 2 * p_params / n)),
        max_vif=max(finite_vifs) if finite_vifs else None, residuals=residuals,
        fitted=np.asarray(model.fittedvalues, dtype=float), cooks=cooks, leverage=leverage,
        cov=cov)
    numbers = [result.r_squared, result.f_value, *params, *bse]
    if not all(math.isfinite(v) for v in numbers):
        raise ValueError("The model returned non-finite estimates; inspect the data.")
    return result, inferred


def _from_coefficient(key: str, label: str, coefficient: Coefficient, df: int,
                      mediator: str = "") -> Estimate:
    return Estimate(key, label, coefficient.b, coefficient.se, coefficient.t, coefficient.p,
                    coefficient.ci_low, coefficient.ci_high, "t distribution", mediator=mediator,
                    df=df)


def _w_points(spec: ProcessSpec, w: np.ndarray) -> tuple[WPoint, ...]:
    low, high = float(np.min(w)), float(np.max(w))
    values = np.unique(w)
    points: list[tuple[str, float]] = []
    if values.size == 2:
        points = [("w.low", float(values[0])), ("w.high", float(values[1]))]
    else:
        mean, sd = float(np.mean(w)), float(np.std(w, ddof=1))
        points = [("w.minus", mean - sd), ("w.mean", mean), ("w.plus", mean + sd)]
        p16, p50, p84 = np.percentile(w, W_PERCENTILES)
        points += [("w.p16", float(p16)), ("w.p50", float(p50)), ("w.p84", float(p84))]
    points += [("w.chosen", float(v)) for v in spec.w_values]
    tolerance = 1e-12 * max(1.0, abs(low), abs(high))
    return tuple(WPoint(where, value, value < low - tolerance or value > high + tolerance)
                 for where, value in points)


def _linear(cov: np.ndarray, i: int, j: int, b_i: float, b_j: float, u: float) -> tuple[float, float]:
    """Value and SE of b_i + u·b_j from the coefficient covariance matrix."""
    value = b_i + u * b_j
    variance = cov[i, i] + u * u * cov[j, j] + 2 * u * cov[i, j]
    return value, math.sqrt(max(variance, 0.0))


def _conditional(spec, equation: EquationResult, focal: str, product: str, w_points,
                 centre_w: float, key: str, mediator: str, focal_name: str) -> list[Estimate]:
    """Conditional effects ``b_focal + b_product (w − centre)`` at each W value."""
    i, j = equation.index(focal), equation.index(product)
    b_i = equation.coefficients[i].b
    b_j = equation.coefficients[j].b
    t_crit = float(stats.t.ppf(0.5 + spec.level / 2, equation.df_resid))
    out = []
    for point in w_points:
        value, se = _linear(equation.cov, i, j, b_i, b_j, point.value - centre_w)
        t_value = value / se if se > 0 else float("nan")
        p = float(2 * stats.t.sf(abs(t_value), equation.df_resid)) if se > 0 else float("nan")
        label = _t("en", "q.cond", focal=focal_name, outcome=equation.outcome,
                   w=_fmt(point.value), where=_t("en", point.where))
        out.append(Estimate(f"{key}@{point.where}:{_fmt(point.value, 6)}", label, value, se,
                            t_value, p, value - t_crit * se, value + t_crit * se,
                            "t distribution", mediator=mediator, w=point.value,
                            where=point.where, df=equation.df_resid))
    return out


def _johnson_neyman(spec, equation: EquationResult, w: np.ndarray, centre_w: float,
                    alpha: float = 0.05) -> JohnsonNeyman:
    """Values of W where the conditional effect of X has p = alpha exactly.

    ``(b1 + b3 u)² = t² (v11 + 2u v13 + u² v33)`` with u = w − centre, i.e.
    ``A u² + B u + C = 0``: A = b3² − t² v33, B = 2(b1 b3 − t² v13),
    C = b1² − t² v11. Real roots inside the observed range of W are kept."""
    i, j = equation.index("x"), equation.index("x*w")
    b1, b3 = equation.coefficients[i].b, equation.coefficients[j].b
    v = equation.cov
    t2 = float(stats.t.ppf(1 - alpha / 2, equation.df_resid)) ** 2
    a_ = b3 * b3 - t2 * v[j, j]
    b_ = 2 * (b1 * b3 - t2 * v[i, j])
    c_ = b1 * b1 - t2 * v[i, i]
    roots: list[float] = []
    if abs(a_) > 1e-300:
        disc = b_ * b_ - 4 * a_ * c_
        if disc >= 0:
            sq = math.sqrt(disc)
            # Numerically stable quadratic roots.
            q = -0.5 * (b_ + math.copysign(sq, b_)) if b_ != 0 else -0.5 * sq
            candidates = [q / a_] + ([c_ / q] if q != 0 else [-q / a_])
            roots = sorted({float(r) for r in candidates})
    elif abs(b_) > 1e-300:
        roots = [-c_ / b_]
    low, high = float(np.min(w)), float(np.max(w))
    points = [r + centre_w for r in roots if low <= r + centre_w <= high]
    effects = []
    for point in points:
        value, se = _linear(v, i, j, b1, b3, point - centre_w)
        p = float(2 * stats.t.sf(abs(value / se), equation.df_resid)) if se > 0 else float("nan")
        effects.append((value, se, p))
    state = None
    if not points:
        value, se = _linear(v, i, j, b1, b3, (low + high) / 2 - centre_w)
        p = float(2 * stats.t.sf(abs(value / se), equation.df_resid)) if se > 0 else 1.0
        state = bool(p < alpha)
    n = len(w)
    return JohnsonNeyman(
        points=tuple(points), below=tuple(float(np.sum(w < p)) / n for p in points),
        above=tuple(float(np.sum(w > p)) / n for p in points), effects=tuple(effects),
        significant_everywhere=state, w_min=low, w_max=high, alpha=alpha)


def _interaction_test(spec, design: _Design, key: str, terms: list[str], products: list[str],
                      full: EquationResult, inferred) -> InteractionTest:
    reduced_terms = [t for t in terms if t not in products]
    outcome_key = _outcome_key(spec, key)
    y = design.outcome(outcome_key)
    reduced = sm.OLS(y, design.matrix(reduced_terms)).fit()
    delta = full.r_squared - float(reduced.rsquared)
    q = len(products)
    f_value = (delta / q) / ((1 - full.r_squared) / full.df_resid)
    p = float(stats.f.sf(f_value, q, full.df_resid))
    f2 = delta / (1 - full.r_squared)
    robust_f = robust_p = None
    if spec.hc3:
        restriction = np.zeros((q, len(full.terms)))
        for row, product in enumerate(products):
            restriction[row, full.index(product)] = 1.0
        test = inferred.f_test(restriction)
        robust_f = float(np.squeeze(test.fvalue))
        robust_p = float(np.squeeze(test.pvalue))
    product = "; ".join(_term_name(spec, t) for t in products)
    return InteractionTest(full.outcome, product, tuple(products), float(delta), float(f_value),
                           q, full.df_resid, p, float(f2), robust_f, robust_p)


# ------------------------------------------------------------------ bootstrap
def _solve(matrix: np.ndarray, outcome: np.ndarray) -> np.ndarray | None:
    coef, _, rank, _ = np.linalg.lstsq(matrix, outcome, rcond=None)
    return coef if rank == matrix.shape[1] else None


def _bootstrap(spec: ProcessSpec, design: _Design, equations: dict[str, list[str]],
               w_points, indices: np.ndarray) -> dict[str, np.ndarray]:
    """Bootstrap draws of every bootstrap quantity (NaN for singular resamples)."""
    k = len(spec.mediators)
    resamples = indices.shape[0]
    keys = _boot_keys(spec, w_points)
    out = {key: np.full(resamples, np.nan) for key in keys}
    centre_w = design.centering.get("w", 0.0)
    x_binary = _distinct(design.raw["x"]) == 2
    for r in range(resamples):
        rows = indices[r]
        coefs = {}
        failed = False
        for key, terms in equations.items():
            if key == "total":
                continue
            coef = _solve(design.matrix(terms, rows), design.outcome(_outcome_key(spec, key), rows))
            if coef is None:
                failed = True
                break
            coefs[key] = dict(zip(["const", *terms], coef))
        if failed:
            continue
        y_eq = coefs["y"]
        if spec.model == "4":
            sd_x = float(np.std(design.raw["x"][rows], ddof=1))
            sd_y = float(np.std(design.raw["y"][rows], ddof=1))
            scale = (sd_x / sd_y if not x_binary else 1.0 / sd_y) if sd_y > 0 else np.nan
            total = 0.0
            for j in range(k):
                value = coefs[f"m{j}"]["x"] * y_eq[f"m{j}"]
                out[f"indirect:m{j}"][r] = value
                out[f"indirect_std:m{j}"][r] = value * scale
                total += value
            if k > 1:
                out["indirect_total"][r] = total
                out["indirect_std_total"][r] = total * scale
        elif spec.model == "7":
            for j in range(k):
                m_eq = coefs[f"m{j}"]
                b = y_eq[f"m{j}"]
                out[f"index:m{j}"][r] = m_eq["x*w"] * b
                for point in w_points:
                    a_w = m_eq["x"] + m_eq["x*w"] * (point.value - centre_w)
                    out[_cond_key(j, point)][r] = a_w * b
        elif spec.model == "14":
            for j in range(k):
                a = coefs[f"m{j}"]["x"]
                out[f"index:m{j}"][r] = a * y_eq[f"m{j}*w"]
                for point in w_points:
                    b_w = y_eq[f"m{j}"] + y_eq[f"m{j}*w"] * (point.value - centre_w)
                    out[_cond_key(j, point)][r] = a * b_w
    return out


def _cond_key(j: int, point: WPoint) -> str:
    return f"cond_indirect:m{j}@{point.where}:{_fmt(point.value, 6)}"


def _boot_keys(spec: ProcessSpec, w_points) -> list[str]:
    k = len(spec.mediators)
    keys: list[str] = []
    if spec.model == "4":
        for j in range(k):
            keys += [f"indirect:m{j}", f"indirect_std:m{j}"]
        if k > 1:
            keys += ["indirect_total", "indirect_std_total"]
    elif spec.model in ("7", "14"):
        for j in range(k):
            keys.append(f"index:m{j}")
            keys += [_cond_key(j, point) for point in w_points]
    return keys


# ------------------------------------------------------------------ the fit
def fit_process(df: pd.DataFrame, spec: ProcessSpec, *,
                indices: np.ndarray | None = None) -> ProcessResult:
    """Fit the specified path model; ``indices`` may give the bootstrap rows
    (resamples × n, for an independent re-implementation to share)."""
    spec = check_spec(spec)
    names = spec.variables()
    numeric = _numeric(df, names)
    missing = _missing_summary(numeric, names)
    frame = numeric.dropna().reset_index(drop=True)
    n = len(frame)
    design = _Design(spec, frame)
    equations = _terms(spec)
    p_max = max(len(terms) + 1 for terms in equations.values())
    needed = max(20, 5 * p_max)
    if n < needed:
        raise ValueError(f"Not enough complete cases: {n}; this model needs at least {needed}.")
    for name in (spec.y, *spec.mediators):
        if _distinct(frame[name].to_numpy()) < 3:
            raise ValueError(f"{name} needs a quantitative outcome with at least three values "
                             "(a 0/1 outcome needs a logistic model, which this program does "
                             "not fit for path models).")
    for name in (spec.x, *([spec.w] if spec.w else []), *spec.covariates):
        if _distinct(frame[name].to_numpy()) < 2:
            raise ValueError(f"{name} has no variation among the complete cases.")
    sds = {name: float(frame[name].std(ddof=1)) for name in names}

    fitted: dict[str, EquationResult] = {}
    inferred: dict[str, object] = {}
    for key, terms in equations.items():
        fitted[key], inferred[key] = _fit_equation(spec, design, key, terms, sds)

    k = len(spec.mediators)
    effects: list[Estimate] = []
    conditional: list[Estimate] = []
    interactions: list[InteractionTest] = []
    notes: list[tuple[str, dict]] = []
    w_points: tuple[WPoint, ...] = ()
    jn = None
    centre_w = design.centering.get("w", 0.0)
    if spec.w:
        w_points = _w_points(spec, design.raw["w"])
    y_eq = fitted["y"]

    if spec.model == "4":
        for j, mediator in enumerate(spec.mediators):
            effects.append(_from_coefficient(f"a:m{j}", _t("en", "q.a", m=mediator),
                                             fitted[f"m{j}"].coefficient("x"),
                                             fitted[f"m{j}"].df_resid, mediator))
            effects.append(_from_coefficient(f"b:m{j}", _t("en", "q.b", m=mediator),
                                             y_eq.coefficient(f"m{j}"), y_eq.df_resid, mediator))
        effects.append(_from_coefficient("direct", _t("en", "q.direct"), y_eq.coefficient("x"),
                                         y_eq.df_resid))
        effects.append(_from_coefficient("total", _t("en", "q.total"),
                                         fitted["total"].coefficient("x"),
                                         fitted["total"].df_resid))
    elif spec.model == "1":
        effects += [
            _from_coefficient("b:x", f"{spec.x} (b1)", y_eq.coefficient("x"), y_eq.df_resid),
            _from_coefficient("b:w", f"{spec.w} (b2)", y_eq.coefficient("w"), y_eq.df_resid),
            _from_coefficient("interaction", _t("en", "q.interaction",
                                                product=_term_name(spec, "x*w")),
                              y_eq.coefficient("x*w"), y_eq.df_resid)]
        interactions.append(_interaction_test(spec, design, "y", equations["y"], ["x*w"],
                                              y_eq, inferred["y"]))
        conditional += _conditional(spec, y_eq, "x", "x*w", w_points, centre_w, "cond:x",
                                    "", spec.x)
        if _distinct(design.raw["w"]) > 2:
            jn = _johnson_neyman(spec, y_eq, design.raw["w"], centre_w, 1 - spec.level)
    elif spec.model == "7":
        for j, mediator in enumerate(spec.mediators):
            m_eq = fitted[f"m{j}"]
            effects.append(_from_coefficient(f"a:m{j}", _t("en", "q.a", m=mediator) + " (a1)",
                                             m_eq.coefficient("x"), m_eq.df_resid, mediator))
            effects.append(_from_coefficient(
                f"interaction:m{j}", _t("en", "q.interaction", product=_term_name(spec, "x*w"))
                + f" → {mediator} (a3)", m_eq.coefficient("x*w"), m_eq.df_resid, mediator))
            effects.append(_from_coefficient(f"b:m{j}", _t("en", "q.b", m=mediator),
                                             y_eq.coefficient(f"m{j}"), y_eq.df_resid, mediator))
            interactions.append(_interaction_test(spec, design, f"m{j}", equations[f"m{j}"],
                                                  ["x*w"], m_eq, inferred[f"m{j}"]))
            conditional += _conditional(spec, m_eq, "x", "x*w", w_points, centre_w,
                                        f"cond:a:m{j}", mediator, spec.x)
        effects.append(_from_coefficient("direct", _t("en", "q.direct"), y_eq.coefficient("x"),
                                         y_eq.df_resid))
    elif spec.model == "14":
        for j, mediator in enumerate(spec.mediators):
            m_eq = fitted[f"m{j}"]
            effects.append(_from_coefficient(f"a:m{j}", _t("en", "q.a", m=mediator),
                                             m_eq.coefficient("x"), m_eq.df_resid, mediator))
            effects.append(_from_coefficient(f"b:m{j}", _t("en", "q.b", m=mediator) + " (b1)",
                                             y_eq.coefficient(f"m{j}"), y_eq.df_resid, mediator))
            effects.append(_from_coefficient(
                f"interaction:m{j}", _t("en", "q.interaction",
                                        product=_term_name(spec, f"m{j}*w")) + " → Y (b3)",
                y_eq.coefficient(f"m{j}*w"), y_eq.df_resid, mediator))
            conditional += _conditional(spec, y_eq, f"m{j}", f"m{j}*w", w_points, centre_w,
                                        f"cond:b:m{j}", mediator, mediator)
        interactions.append(_interaction_test(spec, design, "y", equations["y"],
                                              [f"m{j}*w" for j in range(k)], y_eq,
                                              inferred["y"]))
        effects.append(_from_coefficient("direct", _t("en", "q.direct"), y_eq.coefficient("x"),
                                         y_eq.df_resid))

    # ------------------------------------------------------------ bootstrap
    indirect: list[Estimate] = []
    bootstrap = None
    samples: dict[str, np.ndarray] = {}
    used_indices = None
    if spec.model in MEDIATION_MODELS:
        if indices is None:
            used_indices = bootstrap_indices(n, spec.resamples, spec.seed)
        else:
            used_indices = np.asarray(indices)
            if used_indices.shape != (spec.resamples, n) or used_indices.min() < 0 \
                    or used_indices.max() >= n:
                raise ValueError("Bootstrap indices must be resamples × n row numbers.")
        samples = _bootstrap(spec, design, equations, w_points, used_indices)
        valid_mask = np.all(np.isfinite(np.column_stack(list(samples.values()))), axis=1)
        valid = int(valid_mask.sum())
        if valid < max(100, spec.resamples // 2):
            raise ValueError(f"Only {valid} of {spec.resamples} bootstrap resamples could be "
                             "estimated; the model is not stable enough for a bootstrap.")
        samples = {key: values[valid_mask] for key, values in samples.items()}
        digest = hashlib.sha256(np.ascontiguousarray(used_indices, dtype=np.int64)
                                .tobytes()).hexdigest()
        bootstrap = BootstrapInfo(spec.resamples, valid, spec.seed, spec.level,
                                  indices_sha256=digest)
        if valid < spec.resamples:
            notes.append(("warn.boot_invalid", {"invalid": spec.resamples - valid,
                                                "total": spec.resamples}))
        method = (f"percentile bootstrap, {valid} of {spec.resamples} resamples, seed "
                  f"{spec.seed}")

        def boot_estimate(key: str, label: str, value: float, mediator: str = "",
                          point: WPoint | None = None) -> Estimate:
            draws = samples[key]
            low, high = percentile_interval(draws, spec.level)
            return Estimate(key, label, float(value), float(np.std(draws, ddof=1)), None, None,
                            low, high, method, mediator=mediator,
                            w=None if point is None else point.value,
                            where="" if point is None else point.where)

        x_binary = _distinct(design.raw["x"]) == 2
        if spec.model == "4":
            sd_x, sd_y = sds[spec.x], sds[spec.y]
            scale = sd_x / sd_y if not x_binary else 1.0 / sd_y
            std_key = "q.indirect_std" if not x_binary else "q.indirect_pstd"
            total = 0.0
            for j, mediator in enumerate(spec.mediators):
                value = fitted[f"m{j}"].coefficient("x").b * y_eq.coefficient(f"m{j}").b
                total += value
                indirect.append(boot_estimate(f"indirect:m{j}",
                                              _t("en", "q.indirect", m=mediator), value, mediator))
            if k > 1:
                indirect.append(boot_estimate("indirect_total", _t("en", "q.indirect_total"),
                                              total))
            for j, mediator in enumerate(spec.mediators):
                value = fitted[f"m{j}"].coefficient("x").b * y_eq.coefficient(f"m{j}").b
                indirect.append(boot_estimate(f"indirect_std:m{j}",
                                              _t("en", std_key, m=mediator), value * scale,
                                              mediator))
            if k > 1:
                indirect.append(boot_estimate("indirect_std_total",
                                              _t("en", std_key + "_total"), total * scale))
            if x_binary:
                notes.append(("warn.binary_x", {}))
        else:
            for j, mediator in enumerate(spec.mediators):
                m_eq = fitted[f"m{j}"]
                if spec.model == "7":
                    index = m_eq.coefficient("x*w").b * y_eq.coefficient(f"m{j}").b
                else:
                    index = m_eq.coefficient("x").b * y_eq.coefficient(f"m{j}*w").b
                indirect.append(boot_estimate(f"index:m{j}", _t("en", "q.index", m=mediator),
                                              index, mediator))
                for point in w_points:
                    u = point.value - centre_w
                    if spec.model == "7":
                        value = (m_eq.coefficient("x").b + m_eq.coefficient("x*w").b * u) \
                            * y_eq.coefficient(f"m{j}").b
                    else:
                        value = m_eq.coefficient("x").b * (
                            y_eq.coefficient(f"m{j}").b + y_eq.coefficient(f"m{j}*w").b * u)
                    indirect.append(boot_estimate(
                        _cond_key(j, point), _t("en", "q.cond_indirect", m=mediator,
                                                w=_fmt(point.value), where=_t("en", point.where)),
                        value, mediator, point))

    # ------------------------------------------------------------ notes
    if missing.excluded:
        notes.insert(0, ("warn.listwise", {"excluded": missing.excluded, "total": missing.n_total,
                                           "n": n}))
        if not missing.comparison_meaningful:
            notes.append(("warn.excluded_few", {"count": missing.excluded}))
        else:
            notes.append(("warn.excluded_compare", {}))
    if n < SMALL_SAMPLE:
        notes.append(("warn.small_n", {"n": n}))
    for equation in fitted.values():
        if equation.key == "total":
            continue
        if equation.shapiro_p is not None and equation.shapiro_p < 0.05:
            notes.append(("warn.shapiro", {"outcome": equation.outcome,
                                           "p": _fmt(equation.shapiro_p)}))
        if equation.bp_p is not None and equation.bp_p < 0.05:
            notes.append(("warn.bp", {"outcome": equation.outcome, "p": _fmt(equation.bp_p)}))
        if equation.cooks_over:
            notes.append(("warn.cooks", {"outcome": equation.outcome,
                                         "count": equation.cooks_over}))
        if equation.leverage_over:
            notes.append(("warn.leverage", {"outcome": equation.outcome,
                                            "count": equation.leverage_over}))
        high = [c.term for c in equation.coefficients if c.vif is not None and c.vif > VIF_LIMIT]
        if high:
            notes.append(("warn.vif", {"outcome": equation.outcome, "terms": ", ".join(high)}))
    if spec.w:
        w = design.raw["w"]
        for point in w_points:
            if point.outside:
                notes.append(("warn.w_outside", {"value": _fmt(point.value),
                                                 "where": _t("en", point.where), "w": spec.w,
                                                 "low": _fmt(float(np.min(w))),
                                                 "high": _fmt(float(np.max(w)))}))
    if spec.hc3:
        notes.append(("warn.hc3", {}))
    if spec.model in MEDIATION_MODELS:
        notes += [("warn.no_screening", {}), ("warn.cross_sectional", {})]
    if spec.model in MODERATED_MODELS:
        notes.append(("warn.interaction", {}))
    notes.append(("warn.effect_word", {}))

    return ProcessResult(
        spec=spec, n_total=len(df), n=n, missing=missing,
        equations=tuple(fitted.values()), effects=tuple(effects), indirect=tuple(indirect),
        conditional=tuple(conditional), interactions=tuple(interactions), w_points=w_points,
        johnson_neyman=jn, bootstrap=bootstrap, centering=dict(design.centering), sds=sds,
        notes=tuple(notes), samples=samples, indices=used_indices, data=frame)


# ------------------------------------------------------------------ structured
def _quantity(estimate: Estimate, level: float) -> Quantity:
    note = estimate.ci_method
    return Quantity(estimate.key, estimate.label, float(estimate.value),
                    note=(f"SE = {estimate.se:.4f}; " if estimate.se is not None else "") + note,
                    ci_low=estimate.ci_low, ci_high=estimate.ci_high, ci_level=level,
                    ci_method=estimate.ci_method, p=estimate.p,
                    p_method="t test of the coefficient" if estimate.p is not None else "")


def structured_result(result: ProcessResult, language: str = "en") -> StructuredResult:
    """The result as a Stage 36 structured result (stored with the run)."""
    from process_reporting import process_tables

    spec = result.spec
    level = spec.level
    quantities = [_quantity(e, level) for e in (*result.effects, *result.indirect)]
    quantities += [_quantity(e, level) for e in result.conditional]
    for test in result.interactions:
        quantities.append(Quantity(f"delta_r2:{test.equation}:{test.product}",
                                   _t("en", "q.delta_r2", product=test.product,
                                      outcome=test.equation), test.delta_r2,
                                   note=f"F({test.df1}, {test.df2}) = {test.f_value:.3f}",
                                   p=test.p, p_method="F test of the R² change"))
        quantities.append(Quantity(f"f2:{test.equation}:{test.product}",
                                   _t("en", "q.f2", product=test.product, outcome=test.equation),
                                   test.f2, note="ΔR² / (1 − R² of the full equation)"))
    diagnostics = [Quantity(f"r2:{e.key}", _t("en", "q.r2", outcome=e.outcome) +
                            (" (total effect)" if e.key == "total" else ""), e.r_squared,
                            p=e.f_p, p_method=f"F({e.df_model}, {e.df_resid})")
                   for e in result.equations]
    tables = tuple(Table(t.title, tuple(t.columns), tuple(tuple(r) for r in t.rows))
                   for t in process_tables(result, language))
    provenance = _provenance(
        engine=ENGINE_VERSION, statsmodels=str(getattr(sm, "__version__", "")),
        model=f"PROCESS-equivalent Model {spec.model} (computed by this program)",
        seed=spec.seed if result.bootstrap else None,
        resamples=spec.resamples if result.bootstrap else None,
        valid_resamples=result.bootstrap.valid if result.bootstrap else None,
        bootstrap_indices_sha256=result.bootstrap.indices_sha256 if result.bootstrap else None)
    inputs = {"variables": {"x": spec.x, "y": spec.y, "mediators": list(spec.mediators),
                            "w": spec.w, "covariates": list(spec.covariates)},
              "options": {"model": spec.model, "center": spec.center, "hc3": spec.hc3,
                          "resamples": spec.resamples, "seed": spec.seed, "level": spec.level,
                          "w_values": list(spec.w_values), "missing": "listwise"}}
    return StructuredResult(
        f"process_model_{spec.model}", _t("en", f"model.{spec.model}"),
        {"n_total": result.n_total, "n_used": result.n, "n_missing": result.missing.excluded},
        inputs, tuple(quantities), tuple(diagnostics), result.warnings, tables, provenance,
        method_version=ENGINE_VERSION)


# ------------------------------------------------------------------ sensitivity
@dataclass(frozen=True)
class SensitivityRow:
    focal: str                 # English label of the focal quantity
    focal_key: str             # "interaction", "indirect:m0", "index:m0"
    mediator: str
    assumed: float             # assumed standardized value of the focal coefficient(s)
    n: int
    replications: int
    power: float
    mc_se: float


@dataclass(frozen=True)
class Sensitivity:
    model: str
    rows: tuple[SensitivityRow, ...]
    replications: int
    seed: int
    n: int
    alpha: float
    test: str                  # "t" or "mc"
    draws: int = 2000


DEFAULT_GRID = {"1": (0.0, 0.05, 0.10, 0.15, 0.20, 0.25),
                "4": (0.10, 0.14, 0.26, 0.39),
                "7": (0.0, 0.05, 0.10, 0.15, 0.20, 0.25),
                "14": (0.0, 0.05, 0.10, 0.15, 0.20, 0.25)}


def _ols(matrix: np.ndarray, outcome: np.ndarray, hc3: bool):
    """Coefficients, their covariance and residual df (numpy only)."""
    coef, _, rank, _ = np.linalg.lstsq(matrix, outcome, rcond=None)
    if rank < matrix.shape[1]:
        return None
    n, p = matrix.shape
    resid = outcome - matrix @ coef
    xtx_inv = np.linalg.inv(matrix.T @ matrix)
    if hc3:
        hat = np.einsum("ij,jk,ik->i", matrix, xtx_inv, matrix)
        weights = (resid / (1 - hat)) ** 2
        cov = xtx_inv @ (matrix.T * weights) @ matrix @ xtx_inv
    else:
        cov = xtx_inv * float(resid @ resid) / (n - p)
    return coef, cov, n - p


def sensitivity_simulation(result: ProcessResult, *, replications: int = 500,
                           grid: Sequence[float] | None = None, n: int | None = None,
                           seed: int | None = None, draws: int = 2000) -> Sensitivity:
    """Monte Carlo sensitivity of the specified model at N (clearly labelled
    as a simulation under assumed population values, never 'observed power').

    Population: the rows of the exogenous variables (X, W, covariates) are
    resampled from the analysis sample; every coefficient except the focal
    one(s) is the sample estimate; residuals are normal with the sample
    residual variance of their equation. The focal coefficient takes each
    assumed standardized value of ``grid``:

    * Model 1: the X × W coefficient, standardized as b3·SD(X)·SD(W)/SD(Y);
      detected when its two-sided p < 1 − level.
    * Model 4: every a_j and b_j path (standardized a·SD(X)/SD(M),
      b·SD(M)/SD(Y)); detected when the 95% Monte Carlo interval of a_j b_j
      excludes zero.
    * Model 7: X × W → M_j (a3, standardized as in Model 1) with b_j at its
      estimate; detected by the Monte Carlo interval of the index a3 b_j.
    * Model 14: M_j × W → Y (b3) with a_j at its estimate; index a_j b3.
    """
    spec = result.spec
    grid = tuple(DEFAULT_GRID[spec.model] if grid is None else grid)
    seed = spec.seed + 1 if seed is None else int(seed)
    n = result.n if n is None else int(n)
    replications = int(replications)
    if replications < 20:
        raise ValueError("At least 20 replications are needed.")
    rng = np.random.default_rng(seed)
    design = _Design(spec, result.data)
    equations = _terms(spec)
    fitted = {e.key: e for e in result.equations}
    alpha = 1 - spec.level
    sds = {key: float(np.std(design.raw[key], ddof=1)) for key in design.raw}
    exogenous = ["x", *(["w"] if spec.w else []),
                 *(f"c{i}" for i in range(len(spec.covariates)))]
    k = len(spec.mediators)
    rows: list[SensitivityRow] = []

    def coefficients(key: str) -> dict[str, float]:
        equation = fitted[key]
        return {c.key: c.b for c in equation.coefficients}

    base = {key: coefficients(key) for key in equations if key != "total"}
    focal_specs: list[tuple[str, str, str]] = []    # (focal_key, label, mediator)
    if spec.model == "1":
        focal_specs.append(("interaction", _t("en", "sensitivity.focal.interaction",
                                              product=_term_name(spec, "x*w")), ""))
    else:
        for j, mediator in enumerate(spec.mediators):
            key = {"4": "sensitivity.focal.indirect", "7": "sensitivity.focal.index7",
                   "14": "sensitivity.focal.index14"}[spec.model]
            focal_specs.append(((f"indirect:m{j}" if spec.model == "4" else f"index:m{j}"),
                                _t("en", key, m=mediator), mediator))
    for value in grid:
        population = {key: dict(coefs) for key, coefs in base.items()}
        if spec.model == "1":
            population["y"]["x*w"] = value * sds["y"] / (sds["x"] * sds["w"])
        for j in range(k):
            if spec.model == "4":
                population[f"m{j}"]["x"] = value * sds[f"m{j}"] / sds["x"]
                population["y"][f"m{j}"] = value * sds["y"] / sds[f"m{j}"]
            elif spec.model == "7":
                population[f"m{j}"]["x*w"] = value * sds[f"m{j}"] / (sds["x"] * sds["w"])
            elif spec.model == "14":
                population["y"][f"m{j}*w"] = value * sds["y"] / (sds[f"m{j}"] * sds["w"])
        detected = np.zeros(len(focal_specs))
        done = 0
        for _ in range(replications):
            rows_idx = rng.integers(0, result.n, size=n)
            sim = _SimDesign(design, rows_idx)
            # Endogenous variables in causal-model order: mediators, then Y.
            for j in range(k):
                key = f"m{j}"
                terms = equations[key]
                mean = sim.matrix(terms) @ np.array([population[key][t] for t in ["const", *terms]])
                sim.raw[key] = mean + rng.normal(0.0, math.sqrt(fitted[key].mse), n)
            terms = equations["y"]
            mean = sim.matrix(terms) @ np.array([population["y"][t] for t in ["const", *terms]])
            sim.raw["y"] = mean + rng.normal(0.0, math.sqrt(fitted["y"].mse), n)
            fits = {}
            failed = False
            for key in [*(f"m{j}" for j in range(k)), "y"]:
                if key.startswith("m") and spec.model == "1":
                    continue
                terms = equations[key]
                fit = _ols(sim.matrix(terms), sim.raw[_outcome_key(spec, key)], spec.hc3)
                if fit is None:
                    failed = True
                    break
                fits[key] = (fit, ["const", *terms])
            if failed:
                continue
            done += 1
            for position, (focal_key, _, _) in enumerate(focal_specs):
                if spec.model == "1":
                    (coef, cov, df_resid), terms = fits["y"]
                    i = terms.index("x*w")
                    t_value = coef[i] / math.sqrt(cov[i, i])
                    detected[position] += 2 * stats.t.sf(abs(t_value), df_resid) < alpha
                    continue
                j = int(focal_key.split(":m")[1])
                if spec.model == "4":
                    first, first_term = fits[f"m{j}"], "x"
                    second, second_term = fits["y"], f"m{j}"
                elif spec.model == "7":
                    first, first_term = fits[f"m{j}"], "x*w"
                    second, second_term = fits["y"], f"m{j}"
                else:
                    first, first_term = fits[f"m{j}"], "x"
                    second, second_term = fits["y"], f"m{j}*w"
                (c1, v1, _), t1 = first
                (c2, v2, _), t2 = second
                i1, i2 = t1.index(first_term), t2.index(second_term)
                product = (rng.normal(c1[i1], math.sqrt(v1[i1, i1]), draws)
                           * rng.normal(c2[i2], math.sqrt(v2[i2, i2]), draws))
                low, high = np.percentile(product, [2.5, 97.5])
                detected[position] += (low > 0) or (high < 0)
        for position, (focal_key, label, mediator) in enumerate(focal_specs):
            power = float(detected[position] / done) if done else float("nan")
            rows.append(SensitivityRow(label, focal_key, mediator, float(value), n, done, power,
                                       math.sqrt(power * (1 - power) / done) if done else
                                       float("nan")))
    return Sensitivity(spec.model, tuple(rows), replications, seed, n, alpha,
                       "t" if spec.model == "1" else "mc", draws)


class _SimDesign(_Design):
    """A simulated sample: exogenous rows resampled from the analysis sample,
    centred with the analysis sample's constants (as the fitted model)."""

    def __init__(self, design: _Design, rows: np.ndarray):
        self.spec = design.spec
        self.raw = {key: values[rows] for key, values in design.raw.items()}
        self.n = len(rows)
        self.centering = dict(design.centering)


# ------------------------------------------------------------------ missing-data sensitivity
def compare_estimates(first: ProcessResult, second: ProcessResult) -> list[tuple]:
    """Side by side the estimates two fits share (for a missing-data
    sensitivity comparison, e.g. complete cases against prorated scores):
    (key, label, first value, first CI, second value, second CI, difference)."""
    rows = []
    others = {e.key: e for e in (*second.effects, *second.indirect, *second.conditional)}
    for estimate in (*first.effects, *first.indirect, *first.conditional):
        other = others.get(estimate.key)
        if other is None:
            continue
        rows.append((estimate.key, estimate.label, estimate.value,
                     (estimate.ci_low, estimate.ci_high), other.value,
                     (other.ci_low, other.ci_high), other.value - estimate.value))
    return rows
