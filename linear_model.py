"""Linear model with categorical covariates (Stage 37, Issue #66; review S3).

``Y = b0 + Σ b·X (quantitative) + Σ dummy codes + Σ products + e``, fitted by
ordinary least squares (statsmodels) on the listwise-complete cases.

* Quantitative predictors enter as numbers.
* A nominal variable — or an ordinal one the researcher wants treated as
  categories — enters only as dummy codes: one 0/1 column per category
  other than the reference category. The reference category is stated in
  every result. The rule is the researcher's (``first``: lowest code or first
  label; ``last``; ``most_frequent``) or a category named per variable.
* Product terms are formed only between two predictors the researcher
  names. Quantitative × quantitative gives one column, quantitative ×
  categorical one column per dummy code, categorical × categorical one per
  pair of dummy codes. The quantitative components may be mean-centred.
* Standardized β = b·SD(X)/SD(Y) for quantitative predictors only; not
  defined for the constant, dummy codes and products.
* Optional HC3 coefficient standard errors (t-based p and intervals, as
  :mod:`regression_analysis` does); model F and block ΔR² tests are classical,
  with the HC3 Wald F of each block added when HC3 is used.
* Each categorical variable and each product is also tested as a block (all
  its columns together): ΔR², F, p and f² = ΔR²/(1 − R²).
* Diagnostics: residual Shapiro–Wilk and Q–Q, Breusch–Pagan (Koenker),
  Cook's distance, leverage and VIF of every column.

The existing ``regression_analysis`` engine is unchanged. No causal
interpretation is implied: coefficients are conditional associations.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan

from stat_results import Quantity, StructuredResult, Table, _provenance
from variable_rules import looks_like_identifier

ENGINE_VERSION = "stage37.1"
REFERENCE_RULES = ("first", "last", "most_frequent")
MAX_CATEGORIES = 12
SMALL_CATEGORY = 5


@dataclass(frozen=True)
class LinearSpec:
    outcome: str
    predictors: tuple[str, ...] = ()            # quantitative
    factors: tuple[str, ...] = ()               # categorical: dummy codes only
    reference: str = "first"
    references: tuple[tuple[str, str], ...] = ()   # (factor, category) named by the researcher
    products: tuple[tuple[str, str], ...] = ()
    center: bool = False
    hc3: bool = False
    level: float = 0.95

    def variables(self) -> list[str]:
        return [self.outcome, *self.predictors, *self.factors]


@dataclass(frozen=True)
class Column:
    key: str            # "x:<name>", "d:<factor>=<category>", "p:<a>*<b>"
    label: str          # display
    kind: str           # quantitative | dummy | product
    source: tuple[str, ...]   # the variables it comes from


@dataclass(frozen=True)
class LinearCoefficient:
    term: str
    key: str
    kind: str           # constant | quantitative | dummy | product
    b: float
    se: float
    t: float
    p: float
    ci_low: float
    ci_high: float
    beta: float | None
    vif: float | None


@dataclass(frozen=True)
class BlockTest:
    name: str           # the factor, or the product "A × B"
    kind: str           # factor | product
    columns: tuple[str, ...]
    delta_r2: float
    f_value: float
    df1: int
    df2: int
    p: float
    f2: float
    robust_f: float | None = None
    robust_p: float | None = None


@dataclass
class LinearModelResult:
    spec: LinearSpec
    n_total: int
    n: int
    coefficients: tuple[LinearCoefficient, ...]
    r_squared: float
    adj_r_squared: float
    f_value: float
    df_model: int
    df_resid: int
    f_p: float
    blocks: tuple[BlockTest, ...]
    references: dict                     # factor -> reference category (text)
    categories: dict                     # factor -> ((category, n), ...)
    centering: dict                      # predictor -> constant subtracted
    missing: tuple[tuple[str, int], ...]
    shapiro_p: float | None
    bp_p: float
    cooks_max: float
    cooks_over: int
    leverage_max: float
    leverage_over: int
    warnings: tuple[str, ...]
    residuals: np.ndarray = field(repr=False, default=None)
    fitted: np.ndarray = field(repr=False, default=None)
    observed: np.ndarray = field(repr=False, default=None)
    cov: np.ndarray = field(repr=False, default=None)
    design: pd.DataFrame | None = field(repr=False, default=None)

    @property
    def outcome(self) -> str:
        return self.spec.outcome

    @property
    def n_complete(self) -> int:
        return self.n

    def coefficient(self, key: str) -> LinearCoefficient:
        for coefficient in self.coefficients:
            if coefficient.key == key or coefficient.term == key:
                return coefficient
        raise KeyError(key)

    def structured(self) -> StructuredResult:
        return structured_result(self)


# ------------------------------------------------------------------ helpers
def _code_text(value) -> str:
    """A category as text: 1 for 1.0, the label otherwise."""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _categories(values: pd.Series) -> list:
    """Distinct values in their natural order (numeric when all are numbers)."""
    present = values.dropna().unique().tolist()
    numeric = pd.to_numeric(pd.Series(present), errors="coerce")
    if len(present) and numeric.notna().all():
        return [v for _, v in sorted(zip(numeric.tolist(), present), key=lambda t: t[0])]
    return sorted(present, key=lambda v: str(v).casefold())


def check_spec(spec: LinearSpec) -> LinearSpec:
    if not spec.outcome:
        raise ValueError("Choose the outcome.")
    predictors = tuple(str(p) for p in spec.predictors or ())
    factors = tuple(str(f) for f in spec.factors or ())
    if not predictors and not factors:
        raise ValueError("Choose at least one quantitative predictor or categorical covariate.")
    names = [spec.outcome, *predictors, *factors]
    if len(names) != len(set(names)):
        raise ValueError("A variable was chosen twice (a variable has one role in the model).")
    if spec.reference not in REFERENCE_RULES:
        raise ValueError("The reference category rule must be first, last or most_frequent.")
    references = tuple((str(f), str(c)) for f, c in spec.references or ())
    for factor, _ in references:
        if factor not in factors:
            raise ValueError(f"{factor} is not a categorical covariate of the model.")
    products = []
    for pair in spec.products or ():
        a, b = (str(v) for v in pair)
        if a == b:
            raise ValueError("A product needs two different predictors.")
        for name in (a, b):
            if name not in predictors and name not in factors:
                raise ValueError(f"{name} is in a product but not in the model; add it as a "
                                 "predictor or a categorical covariate.")
        products.append((a, b))
    if len({frozenset(p) for p in products}) != len(products):
        raise ValueError("The same product was requested twice.")
    if not 0.5 < float(spec.level) < 1:
        raise ValueError("The interval level must be between 0.5 and 1.")
    return replace(spec, predictors=predictors, factors=factors, references=references,
                   products=tuple(products), center=bool(spec.center), hc3=bool(spec.hc3),
                   level=float(spec.level))


def _vifs(matrix: np.ndarray) -> list[float | None]:
    k = matrix.shape[1] - 1
    if k < 2:
        return [None] * k
    out: list[float | None] = []
    for j in range(1, k + 1):
        fit = sm.OLS(matrix[:, j], np.delete(matrix, j, axis=1)).fit()
        r2 = float(fit.rsquared)
        out.append(float("inf") if r2 >= 1 else 1.0 / (1.0 - r2))
    return out


# ------------------------------------------------------------------ the fit
def fit_linear_model(df: pd.DataFrame, spec: LinearSpec) -> LinearModelResult:
    spec = check_spec(spec)
    names = spec.variables()
    for name in names:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if looks_like_identifier(name):
            raise ValueError(f"{name} looks like an identifier, not a measurement.")
    quantitative = [spec.outcome, *spec.predictors]
    raw = df[names].copy()
    numeric = raw[quantitative].apply(pd.to_numeric, errors="coerce")
    bad = [n for n in quantitative if bool((raw[n].notna() & numeric[n].isna()).any())]
    if bad:
        raise ValueError(f"Non-numeric values in {', '.join(bad)}; a quantitative variable "
                         "needs numbers (a category variable belongs among the categorical "
                         "covariates).")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values[~np.isnan(values)]).all():
        raise ValueError("Infinite values are not supported.")
    frame = pd.concat([numeric, raw[list(spec.factors)]], axis=1)
    missing = tuple((name, int(frame[name].isna().sum())) for name in names)
    complete = frame.dropna().reset_index(drop=True)
    n = len(complete)
    y = complete[spec.outcome].to_numpy(dtype=float)
    if np.unique(y).size < 3:
        raise ValueError("The outcome needs a quantitative variable with at least three values "
                         "(a 0/1 outcome needs logistic regression).")

    columns: list[Column] = []
    arrays: dict[str, np.ndarray] = {}
    centering: dict[str, float] = {}
    in_products = {name for pair in spec.products for name in pair}
    for name in spec.predictors:
        values = complete[name].to_numpy(dtype=float)
        if np.unique(values).size < 2:
            raise ValueError(f"{name} has no variation among the complete cases.")
        if spec.center and name in in_products:
            centering[name] = float(values.mean())
            values = values - centering[name]
        key = f"x:{name}"
        columns.append(Column(key, name, "quantitative", (name,)))
        arrays[key] = values
    references: dict[str, str] = {}
    categories: dict[str, tuple] = {}
    dummies: dict[str, list[str]] = {}
    explicit = dict(spec.references)
    warnings: list[str] = []
    for factor in spec.factors:
        series = complete[factor]
        levels = _categories(series)
        if len(levels) < 2:
            raise ValueError(f"{factor} has only one category among the complete cases.")
        if len(levels) > MAX_CATEGORIES:
            raise ValueError(f"{factor} has {len(levels)} categories; at most {MAX_CATEGORIES} "
                             "can be dummy-coded here. Is it really a category variable?")
        texts = [_code_text(v) for v in levels]
        counts = {text: int((series.map(_code_text) == text).sum()) for text in texts}
        if factor in explicit:
            if explicit[factor] not in texts:
                raise ValueError(f"{explicit[factor]} is not a category of {factor} "
                                 f"({', '.join(texts)}).")
            reference = explicit[factor]
        elif spec.reference == "last":
            reference = texts[-1]
        elif spec.reference == "most_frequent":
            reference = max(texts, key=lambda t: (counts[t], -texts.index(t)))
        else:
            reference = texts[0]
        references[factor] = reference
        categories[factor] = tuple((text, counts[text]) for text in texts)
        small = [f"{text} ({counts[text]})" for text in texts if counts[text] < SMALL_CATEGORY]
        if small:
            warnings.append(f"{factor}: categories with fewer than {SMALL_CATEGORY} cases: "
                            f"{', '.join(small)}; their coefficients are imprecise.")
        coded = series.map(_code_text)
        dummies[factor] = []
        for text in texts:
            if text == reference:
                continue
            key = f"d:{factor}={text}"
            columns.append(Column(key, f"{factor} = {text} (vs {reference})", "dummy",
                                  (factor,)))
            arrays[key] = (coded == text).to_numpy(dtype=float)
            dummies[factor].append(key)

    def parts(name: str) -> list[tuple[str, str]]:
        """(column key, label part) of one product component."""
        if name in spec.predictors:
            return [(f"x:{name}", name)]
        return [(key, f"{name}={key.split('=', 1)[1]}") for key in dummies[name]]

    product_columns: dict[str, list[str]] = {}
    for a, b in spec.products:
        keys = []
        for key_a, label_a in parts(a):
            for key_b, label_b in parts(b):
                key = f"p:{key_a}*{key_b}"
                columns.append(Column(key, f"{label_a} × {label_b}", "product", (a, b)))
                arrays[key] = arrays[key_a] * arrays[key_b]
                keys.append(key)
        product_columns[f"{a} × {b}"] = keys

    matrix = np.column_stack([np.ones(n), *(arrays[c.key] for c in columns)])
    p = matrix.shape[1]
    needed = max(15, 5 * p)
    if n < needed:
        raise ValueError(f"Not enough complete cases: {n}; this model with {p - 1} columns "
                         f"needs at least {needed}.")
    if np.linalg.matrix_rank(matrix) < p:
        raise ValueError("The model's columns are perfectly collinear (for example a category "
                         "that occurs only together with another); remove a redundant term.")
    model = sm.OLS(y, matrix).fit()
    inferred = model.get_robustcov_results(cov_type="HC3", use_t=True) if spec.hc3 else model
    params = np.asarray(inferred.params, dtype=float)
    bse = np.asarray(inferred.bse, dtype=float)
    tvalues = np.asarray(inferred.tvalues, dtype=float)
    pvalues = np.asarray(inferred.pvalues, dtype=float)
    intervals = np.asarray(inferred.conf_int(alpha=1 - spec.level), dtype=float)
    vifs = _vifs(matrix)
    sd_y = float(np.std(y, ddof=1))
    coefficients = [LinearCoefficient("Constant", "const", "constant", float(params[0]),
                                      float(bse[0]), float(tvalues[0]), float(pvalues[0]),
                                      float(intervals[0, 0]), float(intervals[0, 1]), None, None)]
    for j, column in enumerate(columns, start=1):
        beta = None
        if column.kind == "quantitative" and sd_y > 0:
            beta = float(params[j] * float(np.std(arrays[column.key], ddof=1)) / sd_y)
        coefficients.append(LinearCoefficient(
            column.label, column.key, column.kind, float(params[j]), float(bse[j]),
            float(tvalues[j]), float(pvalues[j]), float(intervals[j, 0]),
            float(intervals[j, 1]), beta, vifs[j - 1]))

    keys = [c.key for c in columns]
    blocks: list[BlockTest] = []
    groups = [(factor, "factor", cols) for factor, cols in dummies.items()]
    groups += [(name, "product", cols) for name, cols in product_columns.items()]
    for name, kind, cols in groups:
        removed = list(cols)
        if kind == "factor":
            # Marginality: a factor that forms a product is tested together
            # with its products (the block says so).
            with_products = [k for k in keys if k.startswith("p:")
                             and any(f"{c}*" in k or k.endswith(f"*{c}") for c in cols)]
            if with_products:
                removed += with_products
                name = f"{name} (with its products)"
        keep = [0] + [1 + keys.index(k) for k in keys if k not in removed]
        reduced = sm.OLS(y, matrix[:, keep]).fit()
        q = p - len(keep)
        delta = float(model.rsquared - reduced.rsquared)
        f_value = (delta / q) / ((1 - model.rsquared) / model.df_resid)
        robust_f = robust_p = None
        if spec.hc3:
            restriction = np.zeros((len(removed), p))
            for row, key in enumerate(removed):
                restriction[row, 1 + keys.index(key)] = 1.0
            test = inferred.f_test(restriction)
            robust_f, robust_p = float(np.squeeze(test.fvalue)), float(np.squeeze(test.pvalue))
        blocks.append(BlockTest(name, kind, tuple(removed), delta, float(f_value), q,
                                int(round(model.df_resid)),
                                float(stats.f.sf(f_value, q, model.df_resid)),
                                float(delta / (1 - model.rsquared)), robust_f, robust_p))

    residuals = np.asarray(model.resid, dtype=float)
    influence = model.get_influence()
    cooks = np.asarray(influence.cooks_distance[0], dtype=float)
    leverage = np.asarray(influence.hat_matrix_diag, dtype=float)
    shapiro_p = float(stats.shapiro(residuals).pvalue) if 3 <= n <= 5000 else None
    bp_p = float(het_breuschpagan(residuals, matrix)[1])
    numbers = [model.rsquared, model.fvalue, *params, *bse]
    if not all(math.isfinite(float(v)) for v in numbers):
        raise ValueError("The model returned non-finite estimates; inspect the data.")

    warnings = [
        "Coefficients are conditional associations given the other terms, not causal effects.",
        *warnings,
    ]
    if n < len(df):
        warnings.append(f"{len(df) - n} of {len(df)} rows were left out because a model "
                        "variable was missing (listwise deletion).")
    for factor, reference in references.items():
        warnings.append(f"{factor} is dummy-coded; reference category {reference} "
                        f"(rule: {'named by the researcher' if factor in explicit else spec.reference}).")
    if spec.hc3:
        warnings.append("HC3 standard errors apply to the coefficients; model F and block ΔR² "
                        "tests are the classical OLS tests (the HC3 Wald F is shown with them).")
    if shapiro_p is not None and shapiro_p < 0.05:
        warnings.append("Residual Shapiro–Wilk p < .05; examine the Q–Q plot.")
    if bp_p < 0.05:
        warnings.append("Breusch–Pagan p < .05 suggests non-constant residual variance; HC3 "
                        "standard errors are an option.")
    over = int(np.sum(cooks > 4 / n))
    if over:
        warnings.append(f"{over} case(s) have Cook's distance above 4/N; review them, do not "
                        "delete them automatically.")
    high = [c.term for c in coefficients if c.vif is not None and c.vif > 5]
    if high:
        warnings.append(f"VIF above 5: {', '.join(high)}. Products of uncentred variables are "
                        "collinear with their components by construction.")
    if n < 50:
        warnings.append("Small sample; estimates and assumption tests may be unstable.")
    design = pd.DataFrame(matrix, columns=["const", *keys])
    return LinearModelResult(
        spec=spec, n_total=len(df), n=n, coefficients=tuple(coefficients),
        r_squared=float(model.rsquared), adj_r_squared=float(model.rsquared_adj),
        f_value=float(model.fvalue), df_model=int(round(model.df_model)),
        df_resid=int(round(model.df_resid)), f_p=float(model.f_pvalue), blocks=tuple(blocks),
        references=references, categories=categories, centering=centering, missing=missing,
        shapiro_p=shapiro_p, bp_p=bp_p, cooks_max=float(np.max(cooks)), cooks_over=over,
        leverage_max=float(np.max(leverage)),
        leverage_over=int(np.sum(leverage > 2 * p / n)), warnings=tuple(warnings),
        residuals=residuals, fitted=np.asarray(model.fittedvalues, dtype=float), observed=y,
        cov=np.asarray(inferred.cov_params(), dtype=float), design=design)


# ------------------------------------------------------------------ tables and texts
def _num(value) -> str:
    from process_reporting import num

    return num(value)


def linear_tables(result: LinearModelResult) -> tuple[Table, ...]:
    from process_reporting import ci, fixed, p_cell

    rows = tuple((c.term, _num(c.b), _num(c.se), f"{c.t:.2f}", p_cell(c.p),
                  ci(c.ci_low, c.ci_high),
                  _num(c.beta) if c.beta is not None else
                  ("—" if c.kind == "constant" else "not defined"),
                  "—" if c.vif is None else f"{c.vif:.2f}") for c in result.coefficients)
    tables = [Table(f"Linear model: {result.outcome}",
                    ("Term", "b", "SE", "t", "p", "95% CI", "β", "VIF"), rows)]
    if result.blocks:
        tables.append(Table("Blocks of terms (ΔR² when the block is removed)",
                            ("Block", "Kind", "Columns", "ΔR²", "F", "df", "p", "f²"),
                            tuple((b.name, b.kind, str(len(b.columns)), fixed(b.delta_r2),
                                   f"{b.f_value:.2f}", f"{b.df1}, {b.df2}", p_cell(b.p),
                                   fixed(b.f2)) for b in result.blocks)))
    if result.references:
        tables.append(Table("Dummy coding of categorical covariates",
                            ("Variable", "Reference category", "Categories (n)"),
                            tuple((factor, reference, ", ".join(f"{text} ({count})" for text, count
                                                                in result.categories[factor]))
                                  for factor, reference in result.references.items())))
    tables.append(Table("Residual diagnostics",
                        ("N", "R²", "Adjusted R²", "F", "df", "p", "Shapiro–Wilk p",
                         "Breusch–Pagan p", "Max Cook’s D", "Cook’s D > 4/N", "Max leverage"),
                        ((str(result.n), fixed(result.r_squared), fixed(result.adj_r_squared),
                          f"{result.f_value:.2f}", f"{result.df_model}, {result.df_resid}",
                          p_cell(result.f_p), p_cell(result.shapiro_p), p_cell(result.bp_p),
                          _num(result.cooks_max), str(result.cooks_over),
                          _num(result.leverage_max)),)))
    tables.append(Table("Missing data (listwise deletion)", ("Variable", "Missing"),
                        tuple((name, str(count)) for name, count in result.missing)))
    return tuple(tables)


def format_linear_report(result: LinearModelResult) -> str:
    from correlation_reporting import apa_p_value

    spec = result.spec
    terms = [*spec.predictors, *(f"C({f}, reference {result.references[f]})"
                                 for f in spec.factors),
             *(f"{a} × {b}" for a, b in spec.products)]
    lines = [
        "APA 7-style reporting (researcher review required)",
        f"Linear model: {spec.outcome} ~ " + " + ".join(terms),
        f"Complete cases: N = {result.n}/{result.n_total} (listwise).",
        f"R² = {result.r_squared:.3f}, adjusted R² = {result.adj_r_squared:.3f}; "
        f"F({result.df_model}, {result.df_resid}) = {result.f_value:.2f}, "
        f"{apa_p_value(result.f_p)}.",
        ("Coefficient inference uses HC3 robust standard errors (t-based 95% CI)."
         if spec.hc3 else "Coefficient inference uses classical OLS standard errors (95% CI)."),
        "Categorical covariates enter only as dummy codes (0/1 per category against the stated "
        "reference category); β is defined for quantitative predictors only.",
    ]
    if result.centering:
        lines.append("Mean-centred before forming products: " + ", ".join(
            f"{name} (mean {value:.3f})" for name, value in result.centering.items()) + ".")
    lines.append("")
    for table in linear_tables(result):
        lines += [table.title, " | ".join(table.columns)]
        lines += [" | ".join(row) for row in table.rows]
        lines.append("")
    lines += ["Notes:", *result.warnings]
    return "\n".join(lines)


def structured_result(result: LinearModelResult) -> StructuredResult:
    level = result.spec.level
    quantities = tuple(
        Quantity(f"b:{c.key}", f"{c.term} (b)", c.b, note=f"SE = {c.se:.4f}", ci_low=c.ci_low,
                 ci_high=c.ci_high, ci_level=level, ci_method="t distribution", p=c.p,
                 p_method="t test of the coefficient")
        for c in result.coefficients if c.kind != "constant")
    blocks = tuple(Quantity(f"delta_r2:{b.name}", f"ΔR² of {b.name}", b.delta_r2,
                            note=f"F({b.df1}, {b.df2}) = {b.f_value:.3f}; f² = {b.f2:.4f}",
                            p=b.p, p_method="F test of the R² change")
                   for b in result.blocks)
    diagnostics = (Quantity("r2", "R²", result.r_squared, p=result.f_p,
                            p_method=f"F({result.df_model}, {result.df_resid})"),
                   Quantity("adj_r2", "Adjusted R²", result.adj_r_squared))
    return StructuredResult(
        "linear_model", f"Linear model: {result.outcome}",
        {"n_total": result.n_total, "n_used": result.n, "n_missing": result.n_total - result.n},
        {"variables": {"outcome": result.outcome, "predictors": list(result.spec.predictors),
                       "factors": list(result.spec.factors),
                       "products": [list(p) for p in result.spec.products]},
         "options": {"reference": result.spec.reference, "references": dict(result.references),
                     "center": result.spec.center, "hc3": result.spec.hc3,
                     "missing": "listwise"}},
        quantities + blocks, diagnostics, result.warnings, linear_tables(result),
        _provenance(engine=ENGINE_VERSION, statsmodels=str(getattr(sm, "__version__", ""))),
        method_version=ENGINE_VERSION)
