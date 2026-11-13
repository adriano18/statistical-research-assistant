"""Item diagnostics of one questionnaire scale (Stage 36.3, docs/STAGE36_SPEC.md §7).

:func:`diagnose_items` describes the items of ONE scale and the scale's
internal consistency, reusing the validated engines:

- Cronbach's α, its 95% interval and α if an item were deleted come from
  :func:`reliability.analyze_cronbach`, computed in-house from the published
  formulas (:mod:`cronbach`; Feldt's F-based interval, bounds rounded to
  three decimals as earlier versions reported them; α if deleted for scales
  of at least four items). pingouin is only a test oracle.
- McDonald's ω total comes from :func:`omega_analysis.analyze_omega`: a
  one-factor maximum-likelihood model of the Pearson correlations of the
  complete cases (3–12 items, at least max(30, 5k) complete respondents).
  Its assumptions are stated in every result (:data:`OMEGA_ASSUMPTIONS`).
  The optional interval is the nonparametric percentile bootstrap of
  :func:`omega_bootstrap.bootstrap_omega` (fixed seed).
- ω if an item were deleted refits the same model without the item on the
  same complete cases; with fewer than three remaining items, or when the
  refit fails, it is unavailable and says why.

Decisions:

- One sample for everything: every item statistic uses the listwise
  complete respondents that α and ω use (as SPSS RELIABILITY does); only
  the missing counts use all rows.
- The corrected item–total correlation is the Pearson correlation of the
  item with the sum of the OTHER items.
- Skewness and kurtosis are the bias-adjusted G1 and G2 of
  :func:`stat_results.describe_quantitative`.
- Floor and ceiling percentages are the shares of answers at the lowest and
  highest possible code: given by the researcher, or else the smallest and
  largest code observed in any selected item (the result says which).
- Nothing is recoded and nothing is deleted. A negative item–total
  correlation or loading is flagged "possibly reverse-keyed and not
  recoded — check the scoring key". Items the researcher lists as
  reverse-keyed (from a confirmed scoring definition, see
  :func:`confirmed_reverse_keys`) are reported as apparently recoded,
  apparently not recoded or unclear. α and ω if an item were deleted are
  information, not advice: removing an item changes what the scale
  measures (content validity).
- Total or derived scores are not item responses (defect D5).
  :func:`item_response_problems` tells them apart with stated heuristics,
  and :func:`diagnose_items` refuses to compute a fictitious α from them
  unless the researcher confirms the columns are item responses.

:func:`make_item_diagnostics_chart` draws the corrected item–total
correlations and α if item deleted as a deterministic PNG.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from io import BytesIO
import math
import sys
import textwrap
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from stat_results import Quantity, StructuredResult, Table, _provenance, describe_quantitative
from variable_rules import looks_like_identifier

ENGINE_VERSION = "stage36.3"
METHOD_ID = "item_diagnostics"
DEFAULT_SEED = 20261103                 # the omega_bootstrap default
DEFAULT_RESAMPLES = 300                 # the omega_bootstrap default
FLOOR_CEILING_PERCENT = 15.0            # a common convention for floor/ceiling effects
WEAK_ITEM_TOTAL = 0.10                  # |r| below this: the item's direction is unclear
OMEGA_MAX_ITEMS = 12

# Heuristics telling item responses from total or derived scores (D5).
MAX_ITEM_CATEGORIES = 11                # e.g. a 0–10 rating has 11 codes
MAX_ITEM_RANGE = 10                     # largest code minus smallest code
TOTAL_REASONS = ("non_integer", "many_values", "wide_range")

TOTALS_MESSAGE = (
    "Reliability needs the separate answers to the items of the scale. These columns look "
    "like total or derived scores, not item responses: {names}. Import the item-level data "
    "(one column per item). If they really are item responses (for example 0–100 ratings), "
    "confirm that explicitly.")

OMEGA_ASSUMPTIONS = (
    "Unidimensional: one common factor underlies all items.",
    "Congeneric: items may have different loadings (α, by contrast, assumes essentially "
    "tau-equivalent items).",
    "Uncorrelated errors: the items share nothing beyond the common factor (no correlated "
    "residuals from wording, method or item pairs).",
    "Estimation: maximum-likelihood one-factor analysis (statsmodels Factor, method 'ml') of "
    "the Pearson correlation matrix of the listwise-complete respondents; ω total = (Σλ)² / "
    "((Σλ)² + Σψ) for the unit-weighted sum of standardized items.",
    "Answer codes are treated as interval numbers; no polychoric (ordinal) ω is calculated.",
    "Obtaining a value of ω does not test these assumptions.",
)

CONTENT_NOTE = (
    "Nothing was deleted or recoded. α and ω if an item were deleted are shown for "
    "information only: removing an item changes what the scale measures (content validity), "
    "so a higher coefficient without it is not by itself a reason to remove it.")
CONSISTENCY_NOTE = ("α and ω describe internal consistency, not validity, unidimensionality or "
                    "clinical accuracy.")


# ------------------------------------------------- items vs. total scores (D5)
@dataclass(frozen=True)
class ItemResponseProblem:
    """Why a column does not look like the answers to one item."""

    name: str
    reasons: tuple[str, ...]       # not_numeric, no_values, non_integer, many_values, wide_range
    distinct: int
    minimum: float | None
    maximum: float | None
    text: str

    @property
    def looks_like_total(self) -> bool:
        """A total or derived score rather than an item response."""
        return any(reason in TOTAL_REASONS for reason in self.reasons)


def _num(value: float) -> str:
    return f"{float(value):g}"


def item_response_problems(df: pd.DataFrame, names: Iterable[str]) -> list[ItemResponseProblem]:
    """Columns among ``names`` that do not look like item responses.

    Heuristics (documented in docs/STAGE36_STATISTICAL_VALIDATION.md):
    item responses are a few whole-number codes in a bounded range, such as
    1–5, 0–4, 1–7 or 0–10: at most 11 distinct values (MAX_ITEM_CATEGORIES)
    and at most 10 between the smallest and largest code (MAX_ITEM_RANGE).
    A column with non-integer values (a mean score), more distinct values
    or a wider range looks like a total or derived score
    (``looks_like_total``). Non-numeric and empty columns are reported too
    but are not called totals.

    Limitations: the rule reads values, not meaning. A total of a few
    binary items (0–3) looks like an item; transformed item scores (0, 25,
    …, 100) and visual-analogue items look like totals. The researcher can
    always confirm otherwise. Unknown column names are skipped.
    """
    problems: list[ItemResponseProblem] = []
    for name in names:
        if name not in df.columns:
            continue
        raw = df[name]
        if isinstance(raw.dtype, pd.CategoricalDtype):
            raw = raw.astype(object)
        values = pd.to_numeric(raw, errors="coerce").astype("float64")
        values = values.where(np.isfinite(values))
        reasons: list[str] = []
        if bool((raw.notna() & values.isna()).any()):
            reasons.append("not_numeric")
        clean = values.dropna()
        if clean.empty:
            reasons.append("no_values")
            problems.append(ItemResponseProblem(
                str(name), tuple(reasons), 0, None, None,
                f"{name} has no numeric values; item responses must be coded as numbers."))
            continue
        distinct = int(clean.nunique())
        low, high = float(clean.min()), float(clean.max())
        if not bool((clean == clean.round()).all()):
            reasons.append("non_integer")
        if distinct > MAX_ITEM_CATEGORIES:
            reasons.append("many_values")
        if high - low > MAX_ITEM_RANGE:
            reasons.append("wide_range")
        if not reasons:
            continue
        found = []
        if "non_integer" in reasons:
            found.append("values that are not whole numbers")
        if "many_values" in reasons:
            found.append(f"{distinct} different values")
        if "wide_range" in reasons:
            found.append(f"a range from {_num(low)} to {_num(high)}")
        if "not_numeric" in reasons:
            found.append("non-numeric values")
        what = ("a total or derived score" if any(r in TOTAL_REASONS for r in reasons)
                else "not a numerically coded item")
        problems.append(ItemResponseProblem(
            str(name), tuple(reasons), distinct, low, high,
            f"{name} has {', '.join(found)}; item responses use a few whole-number codes "
            f"(at most {MAX_ITEM_CATEGORIES}, spanning at most {MAX_ITEM_RANGE}). It looks like "
            f"{what}."))
    return problems


# ------------------------------------- reverse keys from confirmed definitions
@dataclass(frozen=True)
class ReverseKeys:
    """Reverse-keyed columns taken ONLY from a confirmed scoring definition."""

    items: tuple[str, ...]          # reverse-keyed columns (empty when nothing is confirmed)
    confirmed: bool                 # a confirmed definition covers these columns
    source: str                     # where the keys come from ("" when nothing is confirmed)
    note: str                       # what was found, or why nothing is returned


def _questions_of(questionnaire) -> tuple[str, list[dict]]:
    if isinstance(questionnaire, dict):
        return str(questionnaire.get("title", "")), list(questionnaire.get("questions") or ())
    questions = getattr(questionnaire, "questions", None)
    if questions is not None:
        return str(getattr(questionnaire, "title", "")), list(questions)
    return "", list(questionnaire)


def confirmed_reverse_keys(columns: Sequence[str], *, questionnaire=None,
                           instrument=None) -> ReverseKeys:
    """Reverse-keyed items among ``columns`` from a confirmed scoring definition.

    ``instrument`` is an imported questionnaire under review
    (``scientific_survey_import.InstrumentCandidate``): only a shared scale
    whose reverse scoring the researcher confirmed (``reverse_confirmed``,
    which requires confirmed structure and codes; see
    ``shared_scales.review_scheme``) contributes its ``reverse_items``.
    Proposed keys, documented scoring groups (``scoring_evidence``) and the
    parser's guesses never do.

    ``questionnaire`` is a saved questionnaire (``SurveyDefinition``, its
    codebook dict or its question list). Its ``reverse_scored`` flags are
    set only by the researcher (builder) or from a confirmed review, so a
    flagged item counts as confirmed. An unflagged item is not evidence
    that no item is reversed, so no flag at all returns nothing.

    Columns are matched to questions by their variable key. Nothing is
    recoded here; the result only lists the items.
    """
    columns = [str(c) for c in columns]
    if instrument is not None:
        title = str(getattr(instrument, "title", "") or "the imported questionnaire")
        rows = list(getattr(instrument, "questions", ()))
        covered, keyed = [], []
        for scheme in getattr(instrument, "schemes", ()):
            linked = {row.question.get("key"): row for row in rows
                      if row.scheme_id == scheme.id and row.question.get("key") in columns}
            if not linked or not scheme.reverse_confirmed:
                continue
            covered += list(linked)
            keyed += [key for key, row in linked.items() if row.number in scheme.reverse_items]
        if covered:
            items = tuple(c for c in columns if c in keyed)
            rest = [c for c in columns if c not in covered]
            listed = ", ".join(items) if items else "no reverse-keyed items among these columns"
            note = f"Reverse scoring confirmed in the review of “{title}”: {listed}."
            if rest:
                note += f" Not covered by a confirmed scale: {', '.join(rest)}."
            return ReverseKeys(items, True, f"confirmed reverse scoring of “{title}”", note)
        return ReverseKeys((), False, "", (
            f"“{title}” has no confirmed reverse scoring for these columns; nothing is "
            "returned. Confirm the reverse-keyed items in the scale review, or check the "
            "scoring key."))
    if questionnaire is not None:
        title, questions = _questions_of(questionnaire)
        title = title or "the saved questionnaire"
        by_key = {str(q.get("key")): q for q in questions if isinstance(q, dict)}
        present = [c for c in columns if c in by_key]
        if not present:
            return ReverseKeys((), False, "", f"“{title}” does not contain these columns; "
                               "reverse-keyed items are not known.")
        items = tuple(c for c in present if by_key[c].get("reverse_scored") is True)
        if items:
            rest = [c for c in columns if c not in by_key]
            return ReverseKeys(items, True, f"reverse-scored flags saved with “{title}”", (
                f"“{title}” marks {', '.join(items)} as reverse-keyed (metadata only; the "
                "answers are not reversed)."
                + (f" Not in the questionnaire: {', '.join(rest)}." if rest else "")))
        return ReverseKeys((), False, "", (
            f"“{title}” marks none of these items as reverse-keyed; that does not confirm that "
            "none is. Check the scoring key."))
    return ReverseKeys((), False, "", (
        "No confirmed scoring definition is linked to these columns, so reverse-keyed items "
        "are not known. Check the questionnaire's scoring key."))


# ------------------------------------------------------------------ results
@dataclass(frozen=True)
class ItemRow:
    """Diagnostics of one item; every statistic uses the ``n`` complete respondents."""

    name: str
    n: int
    missing: int                   # empty answers among all rows
    missing_percent: float
    mean: float
    sd: float
    item_total_r: Quantity         # corrected: item with the sum of the other items
    alpha_if_deleted: Quantity
    alpha_change: Quantity         # α if deleted − α
    omega_if_deleted: Quantity
    omega_change: Quantity         # ω if deleted − ω
    loading: Quantity              # standardized one-factor loading
    skewness: Quantity
    kurtosis: Quantity
    floor_percent: float           # answers at the lowest possible code
    ceiling_percent: float         # answers at the highest possible code
    categories_used: int
    categories_possible: int | None
    out_of_range: int              # values outside the stated codes (all rows)
    possibly_reverse: bool         # negative item–total r or loading
    documented_reverse: bool       # listed as reverse-keyed by the researcher
    recoding: str = ""             # documented: appears_recoded, appears_not_recoded, unclear
    flags: tuple[str, ...] = ()    # possible_reverse, not_recoded, floor, ceiling, out_of_range
    notes: tuple[str, ...] = ()

    QUANTITIES = ("item_total_r", "alpha_if_deleted", "alpha_change", "omega_if_deleted",
                  "omega_change", "loading", "skewness", "kurtosis")

    def to_dict(self) -> dict:
        data = {name: getattr(self, name) for name in self.__dataclass_fields__}
        for name in self.QUANTITIES:
            data[name] = getattr(self, name).to_dict()
        data["flags"], data["notes"] = list(self.flags), list(self.notes)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ItemRow":
        values = {name: data.get(name) for name in cls.__dataclass_fields__ if name in data}
        for name in cls.QUANTITIES:
            values[name] = Quantity.from_dict(data[name])
        values["flags"] = tuple(data.get("flags", ()))
        values["notes"] = tuple(data.get("notes", ()))
        return cls(**values)


@dataclass(frozen=True)
class ItemDiagnostics:
    """Item diagnostics and internal consistency of one scale (JSON-serialisable)."""

    items: tuple[str, ...]
    n_total: int
    n_complete: int
    alpha: Quantity
    omega: Quantity
    rows: tuple[ItemRow, ...]
    scale_min: float
    scale_max: float
    scale_min_source: str          # "given" | "observed"
    scale_max_source: str
    reverse_keyed: tuple[str, ...] = ()
    reverse_source: str = ""
    omega_assumptions: tuple[str, ...] = OMEGA_ASSUMPTIONS
    omega_fit: tuple[Quantity, ...] = ()
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    options: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    version: str = ENGINE_VERSION

    def row(self, name: str) -> ItemRow:
        for row in self.rows:
            if row.name == name:
                return row
        raise KeyError(name)

    @property
    def flagged_reverse(self) -> tuple[str, ...]:
        """Items with a negative item–total correlation or loading (never recoded)."""
        return tuple(row.name for row in self.rows if row.possibly_reverse)

    @property
    def bounds_text(self) -> str:
        """The codes used for floor and ceiling, and where they come from."""
        how = _bounds_how(self.scale_min_source, self.scale_max_source)
        return f"{_num(self.scale_min)}–{_num(self.scale_max)} ({how})"

    def table(self) -> Table:
        columns = ("Item", "M", "SD", "Missing", "r (item–total, corrected)", "α if deleted",
                   "Δα", "ω if deleted", "Δω", "Loading", "Skewness", "Kurtosis", "Floor %",
                   "Ceiling %", "Codes used", "Flags")
        rows = []
        for row in self.rows:
            used = (f"{row.categories_used} of {row.categories_possible}"
                    if row.categories_possible else str(row.categories_used))
            rows.append((
                row.name, f"{row.mean:.2f}", f"{row.sd:.2f}",
                f"{row.missing} ({row.missing_percent:.1f}%)", _coef(row.item_total_r),
                _coef(row.alpha_if_deleted), _change(row.alpha_change),
                _coef(row.omega_if_deleted), _change(row.omega_change), _coef(row.loading),
                row.skewness.text(2), row.kurtosis.text(2), f"{row.floor_percent:.1f}",
                f"{row.ceiling_percent:.1f}", used, ", ".join(FLAG_TEXT[f] for f in row.flags)))
        return Table(f"Item diagnostics: {len(self.items)} items, N = {self.n_complete} complete "
                     "respondents", columns, tuple(rows))

    def structured(self) -> StructuredResult:
        quantities = [self.alpha, self.omega]
        diagnostics = list(self.omega_fit)
        for row in self.rows:
            name = row.name
            quantities += [
                Quantity(f"mean:{name}", f"Mean: {name}", row.mean),
                Quantity(f"sd:{name}", f"SD: {name}", row.sd, note="sample SD (n - 1)"),
                Quantity(f"missing:{name}", f"Missing: {name}", row.missing, integer=True,
                         note=f"{row.missing_percent:.1f}% of {self.n_total} rows"),
                row.item_total_r, row.alpha_if_deleted, row.alpha_change,
                row.omega_if_deleted, row.omega_change, row.loading,
                Quantity(f"floor:{name}", f"Floor %: {name}", row.floor_percent,
                         note=f"answers at {_num(self.scale_min)}"),
                Quantity(f"ceiling:{name}", f"Ceiling %: {name}", row.ceiling_percent,
                         note=f"answers at {_num(self.scale_max)}"),
                Quantity(f"categories:{name}", f"Codes used: {name}", row.categories_used,
                         integer=True, note=(f"of {row.categories_possible} possible"
                                             if row.categories_possible else "")),
            ]
            diagnostics += [row.skewness, row.kurtosis]
        return StructuredResult(
            METHOD_ID, f"Item diagnostics: {len(self.items)} items",
            {"n_total": self.n_total, "n_used": self.n_complete,
             "n_excluded": self.n_total - self.n_complete},
            {"variables": list(self.items), "options": dict(self.options)},
            tuple(quantities), tuple(diagnostics),
            warnings=(*self.warnings, *self.notes),
            tables=(self.table(),), provenance=dict(self.provenance),
            method_version=self.version)

    def to_dict(self) -> dict:
        return {
            "version": self.version, "items": list(self.items), "n_total": self.n_total,
            "n_complete": self.n_complete, "alpha": self.alpha.to_dict(),
            "omega": self.omega.to_dict(), "rows": [row.to_dict() for row in self.rows],
            "scale_min": self.scale_min, "scale_max": self.scale_max,
            "scale_min_source": self.scale_min_source, "scale_max_source": self.scale_max_source,
            "reverse_keyed": list(self.reverse_keyed), "reverse_source": self.reverse_source,
            "omega_assumptions": list(self.omega_assumptions),
            "omega_fit": [q.to_dict() for q in self.omega_fit],
            "warnings": list(self.warnings), "notes": list(self.notes),
            "options": dict(self.options), "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ItemDiagnostics":
        return cls(
            items=tuple(data["items"]), n_total=data["n_total"], n_complete=data["n_complete"],
            alpha=Quantity.from_dict(data["alpha"]), omega=Quantity.from_dict(data["omega"]),
            rows=tuple(ItemRow.from_dict(row) for row in data["rows"]),
            scale_min=data["scale_min"], scale_max=data["scale_max"],
            scale_min_source=data["scale_min_source"],
            scale_max_source=data["scale_max_source"],
            reverse_keyed=tuple(data.get("reverse_keyed", ())),
            reverse_source=data.get("reverse_source", ""),
            omega_assumptions=tuple(data.get("omega_assumptions", OMEGA_ASSUMPTIONS)),
            omega_fit=tuple(Quantity.from_dict(q) for q in data.get("omega_fit", ())),
            warnings=tuple(data.get("warnings", ())), notes=tuple(data.get("notes", ())),
            options=dict(data.get("options", {})), provenance=dict(data.get("provenance", {})),
            version=data.get("version", ENGINE_VERSION))


FLAG_TEXT = {
    "possible_reverse": "possibly reverse-keyed, not recoded",
    "not_recoded": "listed as reverse-keyed, appears not recoded",
    "floor": "floor effect",
    "ceiling": "ceiling effect",
    "out_of_range": "values outside the stated codes",
}


def _coef(quantity: Quantity, digits: int = 2) -> str:
    """Coefficients bounded by 1 without the leading zero (APA)."""
    if not quantity.ok:
        return quantity.text()
    text = f"{float(quantity.value):.{digits}f}"
    return text.replace("0.", ".", 1) if abs(float(quantity.value)) < 1 else text


def _change(quantity: Quantity) -> str:
    if not quantity.ok:
        return quantity.text()
    value = float(quantity.value)
    return ("+" if value > 0 else "") + _coef(quantity, 3)


# ------------------------------------------------------------------ engine
def _check_inputs(df, items, reverse_keyed, scale_min, scale_max, resamples, seed):
    items = [str(item) for item in items]
    if len(items) != len(set(items)):
        raise ValueError("Choose each item only once.")
    if len(items) < 3:
        raise ValueError("Choose at least three items of the same scale.")
    unknown = [item for item in items if item not in df.columns]
    if unknown:
        raise ValueError(f"Unknown columns: {', '.join(unknown)}")
    if any(looks_like_identifier(item) for item in items):
        raise ValueError("Identifiers cannot be used as questionnaire items.")
    if isinstance(reverse_keyed, str):
        raise ValueError("List the reverse-keyed items as a list of column names.")
    reverse = tuple(dict.fromkeys(str(item) for item in reverse_keyed))
    outside = [item for item in reverse if item not in items]
    if outside:
        raise ValueError(f"Reverse-keyed items must be among the selected items: "
                         f"{', '.join(outside)}")
    for value, what in ((scale_min, "The lowest possible code"),
                        (scale_max, "The highest possible code")):
        if value is not None and (isinstance(value, bool) or not isinstance(
                value, (int, float, np.integer, np.floating)) or not math.isfinite(float(value))):
            raise ValueError(f"{what} must be a finite number.")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or not (
            resamples == 0 or 100 <= resamples <= 3000):
        raise ValueError("Bootstrap resamples for the ω interval: 0 (none) or 100–3000.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 32:
        raise ValueError("The seed must be an unsigned 32-bit integer.")
    return items, reverse


def _bounds_how(low_source: str, high_source: str) -> str:
    if low_source == high_source == "given":
        return "given by the researcher"
    if low_source == high_source == "observed":
        return "observed in these items; the possible range may be wider"
    return f"minimum {low_source}, maximum {high_source}"


def _bounds(numeric: pd.DataFrame, scale_min, scale_max):
    observed = numeric.to_numpy(dtype=float)
    observed = observed[np.isfinite(observed)]
    low = float(scale_min) if scale_min is not None else float(observed.min())
    high = float(scale_max) if scale_max is not None else float(observed.max())
    if not low < high:
        raise ValueError("The lowest possible code must be below the highest possible code.")
    return (low, "given" if scale_min is not None else "observed",
            high, "given" if scale_max is not None else "observed")


NOT_CONVERGED = ("statsmodels did not report convergence of the maximum-likelihood fit; the "
                 "solution passed the engine's checks, but treat the value as approximate")


def _fit_omega(frame: pd.DataFrame, items: list[str]):
    """``analyze_omega`` and whether its ML fit reported convergence.

    The validated engine accepts an admissible solution even when statsmodels
    warns that the optimiser did not converge; the diagnostics keep the value
    (so they agree with the ω analysis) and say so. Other warnings are passed on.
    """
    import warnings

    from omega_analysis import analyze_omega
    from statsmodels.tools.sm_exceptions import ConvergenceWarning

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        result = analyze_omega(frame, items)
    converged = True
    for warning in caught:
        if issubclass(warning.category, ConvergenceWarning):
            converged = False
        else:
            warnings.warn_explicit(warning.message, warning.category, warning.filename,
                                   warning.lineno)
    return result, converged


def _omega_full(df, items, n, ci, resamples, seed):
    """(ω quantity, OmegaResult or None, warnings)."""
    from omega_bootstrap import bootstrap_omega

    label = "McDonald’s ω total (one factor)"
    k = len(items)
    needed = max(30, 5 * k)
    if k > OMEGA_MAX_ITEMS:
        return Quantity.missing("omega", label, "not_calculated", (
            f"the validated one-factor ω accepts 3–{OMEGA_MAX_ITEMS} items; estimate ω for "
            "each documented subscale")), None, []
    if n < needed:
        return Quantity.missing("omega", label, "unavailable", (
            f"needs at least {needed} complete respondents for {k} items; {n} available")), \
            None, []
    try:
        result, converged = _fit_omega(df, items)
    except ValueError as error:
        return Quantity.missing("omega", label, "failed", str(error)), None, [
            f"ω could not be estimated: {error}"]
    warnings = [] if converged else [f"ω of all items: {NOT_CONVERGED}."]
    ci_fields = {}
    if ci and resamples:
        try:
            interval = bootstrap_omega(df, items, n_resamples=resamples, seed=seed)
            ci_fields = dict(ci_low=interval.lower, ci_high=interval.upper,
                             ci_level=interval.level, ci_method=(
                                 f"nonparametric percentile bootstrap of complete cases; "
                                 f"{interval.successful}/{interval.requested} valid refits; "
                                 f"seed {interval.seed}"))
        except ValueError as error:
            warnings.append(f"The ω interval is not available: {error}")
    note = (f"standardized one-factor ω total (ML on Pearson correlations); complete cases "
            f"N = {n}")
    if ci and not resamples:
        note += "; no interval (0 bootstrap resamples requested)"
    if not converged:
        note += f"; {NOT_CONVERGED}"
    return Quantity("omega", label, float(result.omega), note=note, **ci_fields), result, warnings


def _omega_without(complete: pd.DataFrame, items: list[str], item: str, full) -> Quantity:
    key, label = f"omega_if_deleted:{item}", f"ω if deleted: {item}"
    if full is None:
        return Quantity.missing(key, label, "not_calculated",
                                "ω of the full scale is not available")
    rest = [name for name in items if name != item]
    if len(rest) < 3:
        return Quantity.missing(key, label, "unavailable", "fewer than 3 items would remain")
    try:
        refit, converged = _fit_omega(complete[rest], rest)
    except ValueError as error:
        return Quantity.missing(key, label, "unavailable", f"the refit without {item} failed: "
                                f"{error}")
    note = f"one-factor model refitted without {item} on the same {len(complete)} complete cases"
    return Quantity(key, label, float(refit.omega),
                    note=note if converged else f"{note}; {NOT_CONVERGED}")


def _change_of(key: str, label: str, value: Quantity, reference: Quantity) -> Quantity:
    if value.ok and reference.ok:
        return Quantity(key, label, float(value.value) - float(reference.value),
                        note="if deleted − all items")
    status = value.status if not value.ok else reference.status
    return Quantity.missing(key, label, status, value.note if not value.ok else reference.note)


def _recoding(r: Quantity, loading: Quantity) -> str:
    """Documented reverse-keyed item: does it already run with the other items?"""
    if not r.ok or abs(float(r.value)) < WEAK_ITEM_TOTAL:
        return "unclear"
    if loading.ok and (float(loading.value) > 0) != (float(r.value) > 0):
        return "unclear"
    return "appears_not_recoded" if float(r.value) < 0 else "appears_recoded"


def _apa(value: float) -> str:
    text = f"{value:.2f}"
    return text.replace("0.", ".", 1) if abs(value) < 1 else text


def diagnose_items(df: pd.DataFrame, items: Sequence[str], *,
                   reverse_keyed: Iterable[str] = (), scale_min: float | None = None,
                   scale_max: float | None = None, ci: bool = True, seed: int = DEFAULT_SEED,
                   resamples: int = DEFAULT_RESAMPLES, reverse_source: str = "",
                   items_confirmed: bool = False,
                   floor_ceiling_percent: float = FLOOR_CEILING_PERCENT) -> ItemDiagnostics:
    """Item diagnostics, α and ω of one scale; nothing in ``df`` is changed.

    ``reverse_keyed`` lists items known to be reverse-keyed (from a
    confirmed scoring definition, :func:`confirmed_reverse_keys`, named in
    ``reverse_source``); they are checked, never recoded. ``scale_min`` and
    ``scale_max`` are the lowest and highest possible codes (else the
    observed codes are used, and the result says so). ``ci`` adds Feldt's
    interval for α and, with ``resamples`` > 0, a percentile bootstrap
    interval for ω (``seed``). Columns that look like total or derived
    scores are refused unless ``items_confirmed`` records the researcher's
    confirmation that they are item responses.
    """
    from reliability import analyze_cronbach

    items, reverse = _check_inputs(df, items, reverse_keyed, scale_min, scale_max, resamples,
                                   seed)
    problems = item_response_problems(df, items)
    totals = [p.name for p in problems if p.looks_like_total]
    if totals and not items_confirmed:
        raise ValueError(TOTALS_MESSAGE.format(names=", ".join(totals)))
    numeric = df[items].apply(pd.to_numeric, errors="coerce")
    if bool((df[items].notna() & numeric.isna()).any().any()):
        raise ValueError("Selected items contain non-numeric responses; recode them first.")
    complete = numeric.dropna()
    if len(complete) >= 2:
        constant = [item for item in items if complete[item].nunique() < 2]
        if constant:
            raise ValueError(f"No variation among the complete answers to {', '.join(constant)}; "
                             "these items cannot be analysed.")
    reliability = analyze_cronbach(df, items)
    n, k, n_total = len(complete), len(items), len(df)
    low, low_source, high, high_source = _bounds(numeric, scale_min, scale_max)
    warnings: list[str] = []

    alpha_ci = dict(ci_low=reliability.ci_low, ci_high=reliability.ci_high, ci_level=0.95,
                    ci_method="Feldt (F distribution), computed by this program from the "
                              "published formula; bounds rounded to 3 decimals") if ci else {}
    alpha = Quantity("alpha", "Cronbach’s α", float(reliability.alpha),
                     note=f"raw α of {k} items; complete cases N = {n}", **alpha_ci)
    omega, full, omega_warnings = _omega_full(df, items, n, ci, resamples, seed)
    warnings += omega_warnings
    loadings = ({d.name: d.standardized_loading for d in full.diagnostics} if full else {})

    x = complete.to_numpy(dtype=float)
    total = x.sum(axis=1)
    integral = float(low).is_integer() and float(high).is_integer()
    rows = []
    for j, item in enumerate(items):
        values = x[:, j]
        rest = total - values
        if np.std(rest) > 0:
            r = Quantity(f"item_total_r:{item}", f"Corrected item–total r: {item}",
                         float(np.corrcoef(values, rest)[0, 1]),
                         note="Pearson r of the item with the sum of the other items")
        else:
            r = Quantity.missing(f"item_total_r:{item}", f"Corrected item–total r: {item}",
                                 "unavailable", "the sum of the other items has no variation")
        if item in reliability.alpha_if_deleted:
            a_del = Quantity(f"alpha_if_deleted:{item}", f"α if deleted: {item}",
                             float(reliability.alpha_if_deleted[item]),
                             note=f"α of the other {k - 1} items, same complete cases")
        elif k < 4:
            a_del = Quantity.missing(f"alpha_if_deleted:{item}", f"α if deleted: {item}",
                                     "not_applicable", "needs at least four items")
        else:
            a_del = Quantity.missing(f"alpha_if_deleted:{item}", f"α if deleted: {item}",
                                     "unavailable", "the other items have no variation")
        o_del = _omega_without(complete, items, item, full)
        if item in loadings:
            loading = Quantity(f"loading:{item}", f"Loading: {item}", float(loadings[item]),
                               note="standardized one-factor loading (ML); sign set so that "
                                    "most loadings are positive")
        else:
            loading = Quantity.missing(f"loading:{item}", f"Loading: {item}", omega.status,
                                       "no one-factor model was fitted")
        shape = describe_quantitative(complete[item], item)
        skew = replace(shape.quantity("skewness"), key=f"skewness:{item}",
                       label=f"Skewness (G1): {item}")
        kurt = replace(shape.quantity("kurtosis"), key=f"kurtosis:{item}",
                       label=f"Excess kurtosis (G2): {item}")
        column = numeric[item]
        out_of_range = int(((column < low) | (column > high)).sum())
        missing = int(df[item].isna().sum())
        floor = 100.0 * float(np.mean(values == low))
        ceiling = 100.0 * float(np.mean(values == high))
        possibly_reverse = bool((r.ok and r.value < 0) or (loading.ok and loading.value < 0))
        documented = item in reverse
        recoding = _recoding(r, loading) if documented else ""
        flags, notes = [], []
        r_text = f"r = {_apa(float(r.value))}" if r.ok else "r unavailable"
        if possibly_reverse and not documented:
            flags.append("possible_reverse")
            notes.append(f"Negative corrected item–total correlation or loading ({r_text}): "
                         "possibly reverse-keyed and not recoded — check the scoring key. "
                         "Nothing was recoded.")
        if documented:
            if recoding == "appears_not_recoded":
                flags.append("not_recoded")
                notes.append(f"Listed as reverse-keyed, and its answers still run against the "
                             f"other items ({r_text}): it appears NOT recoded. Recode it (Data → "
                             "Prepare → reverse item) before reporting α or ω.")
            elif recoding == "appears_recoded":
                notes.append(f"Listed as reverse-keyed; its answers run with the other items "
                             f"({r_text}): it appears recoded.")
            else:
                notes.append(f"Listed as reverse-keyed; its direction is unclear ({r_text}). "
                             "Check whether it was recoded.")
        if floor >= floor_ceiling_percent:
            flags.append("floor")
            notes.append(f"Floor effect: {floor:.1f}% of answers at the lowest code "
                         f"{_num(low)}.")
        if ceiling >= floor_ceiling_percent:
            flags.append("ceiling")
            notes.append(f"Ceiling effect: {ceiling:.1f}% of answers at the highest code "
                         f"{_num(high)}.")
        if out_of_range:
            flags.append("out_of_range")
            notes.append(f"{out_of_range} value(s) outside the codes {_num(low)}–{_num(high)}; "
                         "possibly missing-value codes. They were analysed as numbers.")
        rows.append(ItemRow(
            name=item, n=n, missing=missing, missing_percent=100.0 * missing / n_total,
            mean=float(values.mean()), sd=float(values.std(ddof=1)), item_total_r=r,
            alpha_if_deleted=a_del,
            alpha_change=_change_of(f"alpha_change:{item}", f"Δα if deleted: {item}", a_del,
                                    alpha),
            omega_if_deleted=o_del,
            omega_change=_change_of(f"omega_change:{item}", f"Δω if deleted: {item}", o_del,
                                    omega),
            loading=loading, skewness=skew, kurtosis=kurt, floor_percent=floor,
            ceiling_percent=ceiling, categories_used=int(np.unique(values).size),
            categories_possible=int(high - low + 1) if integral else None,
            out_of_range=out_of_range, possibly_reverse=possibly_reverse,
            documented_reverse=documented, recoding=recoding, flags=tuple(flags),
            notes=tuple(notes)))

    warnings += _scale_warnings(rows, alpha, omega, full, n, n_total, totals, low, high,
                                floor_ceiling_percent)
    notes = [CONTENT_NOTE, CONSISTENCY_NOTE,
             f"Floor and ceiling use the codes {_num(low)}–{_num(high)} "
             f"({_bounds_how(low_source, high_source)})."]
    if reverse:
        notes.append(f"Reverse-keyed items listed by {reverse_source or 'the researcher'}: "
                     f"{', '.join(reverse)}. They were checked, not recoded.")
    else:
        notes.append("No reverse-keyed items were listed. Negative correlations or loadings are "
                     "flagged so that the scoring key can be checked; nothing is recoded.")
    options = {"reverse_keyed": list(reverse), "reverse_source": reverse_source,
               "scale_min": low, "scale_max": high, "scale_min_source": low_source,
               "scale_max_source": high_source, "ci": bool(ci), "resamples": resamples,
               "seed": seed, "floor_ceiling_percent": float(floor_ceiling_percent),
               "items_confirmed": bool(items_confirmed)}
    provenance = _provenance(
        engine=ENGINE_VERSION,
        statsmodels=str(getattr(sys.modules.get("statsmodels"), "__version__", "")),
        alpha="reliability.analyze_cronbach (in-house: cronbach.py)",
        omega="omega_analysis.analyze_omega",
        omega_interval="omega_bootstrap.bootstrap_omega" if ci and resamples else "")
    omega_fit = ()
    if full is not None:
        omega_fit = (
            Quantity("largest_residual", "Largest residual correlation",
                     float(full.largest_residual_corr),
                     note="largest |observed − reproduced| off-diagonal correlation"),
            Quantity("first_eigenvalue", "First eigenvalue of the item correlations",
                     float(full.first_eigenvalue)),
            Quantity("second_eigenvalue", "Second eigenvalue of the item correlations",
                     float(full.second_eigenvalue)),
        )
    return ItemDiagnostics(
        items=tuple(items), n_total=n_total, n_complete=n, alpha=alpha, omega=omega,
        rows=tuple(rows), scale_min=low, scale_max=high, scale_min_source=low_source,
        scale_max_source=high_source, reverse_keyed=reverse, reverse_source=reverse_source,
        omega_fit=omega_fit, warnings=tuple(warnings), notes=tuple(notes), options=options,
        provenance=provenance)


def _scale_warnings(rows, alpha, omega, full, n, n_total, totals, low, high,
                    floor_ceiling_percent) -> list[str]:
    warnings = []
    if totals:
        warnings.append(f"The researcher confirmed that {', '.join(totals)} are item responses "
                        "although they look like total or derived scores.")
    if n < n_total:
        warnings.append(f"{n_total - n} respondent(s) with a missing answer were left out "
                        f"(listwise); every statistic uses the same {n} complete respondents.")
    if n < 50:
        warnings.append("Small sample: α, ω and the item statistics may be unstable.")
    elif full is not None and n < 100:
        warnings.append("Fewer than 100 complete respondents: loadings and ω may be unstable.")
    flagged = [row.name for row in rows if "possible_reverse" in row.flags]
    if flagged:
        warnings.append(f"Possibly reverse-keyed and not recoded: {', '.join(flagged)} (negative "
                        "corrected item–total correlation or loading). Check the scoring key; "
                        "nothing was recoded, so α and ω use the answers as they are.")
    stale = [row.name for row in rows if "not_recoded" in row.flags]
    if stale:
        warnings.append(f"Listed as reverse-keyed but apparently not recoded: {', '.join(stale)}. "
                        "Recode them before reporting α or ω.")
    if alpha.ok and alpha.value < 0:
        warnings.append("Negative α suggests contradictory item covariances or a coding problem.")
    if alpha.ok and alpha.value > 0.95:
        warnings.append("A very high α can indicate redundant items; inspect the item content.")
    if not omega.ok:
        warnings.append(f"ω is not reported: {omega.note}.")
    unsettled = [row.name for row in rows if NOT_CONVERGED in row.omega_if_deleted.note]
    if unsettled:
        warnings.append(f"ω if deleted for {', '.join(unsettled)}: {NOT_CONVERGED}.")
    if full is not None:
        if full.second_eigenvalue > 1:
            warnings.append(f"The second eigenvalue of the item correlations is "
                            f"{full.second_eigenvalue:.2f} (> 1): explore the dimensionality "
                            "(EFA) before assuming one factor.")
        if full.largest_residual_corr > 0.15:
            warnings.append(f"A residual correlation of {full.largest_residual_corr:.2f} (> .15) "
                            "suggests that the one-factor model may fit poorly.")
    for flag, word, code in (("floor", "Floor", low), ("ceiling", "Ceiling", high)):
        names = [row.name for row in rows if flag in row.flags]
        if names:
            warnings.append(f"{word} effect (≥ {floor_ceiling_percent:g}% of answers at "
                            f"{_num(code)}, a common convention): {', '.join(names)}.")
    outside = [f"{row.name} ({row.out_of_range})" for row in rows if row.out_of_range]
    if outside:
        warnings.append(f"Values outside the codes {_num(low)}–{_num(high)}: "
                        f"{', '.join(outside)}; check for missing-value codes.")
    return warnings


# ------------------------------------------------------------------- chart
BLUE, VERMILLION, INK, GRID = "#0072B2", "#D55E00", "#222222", "#D9D9D9"   # Okabe–Ito


def _minus(text: str) -> str:
    return text.replace("-", "−")


def describe_chart(result: ItemDiagnostics) -> str:
    """Alt text of :func:`make_item_diagnostics_chart`."""
    negative = [row.name for row in result.rows
                if row.item_total_r.ok and row.item_total_r.value < 0]
    rising = [row.name for row in result.rows
              if row.alpha_change.ok and row.alpha_change.value > 0]
    alpha = _apa(float(result.alpha.value)) if result.alpha.ok else "unavailable"
    return (f"Two panels for {len(result.items)} items (N = {result.n_complete}). Left: corrected "
            f"item–total correlations; negative for {', '.join(negative) or 'no item'}. Right: "
            f"α if each item were deleted against α = {alpha} for all items; α would rise "
            f"without {', '.join(rising) or 'no item'}.")


def make_item_diagnostics_chart(result: ItemDiagnostics, *, dpi: int = 110) -> bytes:
    """Deterministic PNG: corrected item–total r (negatives hatched and coloured)
    and α if item deleted against the overall α (rising items drawn as
    triangles). Colour-blind-safe (Okabe–Ito) and never colour alone."""
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    names = [row.name for row in result.rows]
    k = len(names)
    y = np.arange(k)
    style = {"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": INK,
             "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
             "hatch.linewidth": 1.0}
    with matplotlib.rc_context(style):
        figure = Figure(figsize=(10.5, max(3.8, 1.9 + 0.38 * k)), dpi=dpi)
        FigureCanvasAgg(figure)
        left, right = figure.subplots(1, 2, sharey=True)
        for index, row in enumerate(result.rows):
            q = row.item_total_r
            if not q.ok:
                left.text(0, index, "  unavailable", va="center", ha="left", fontsize=8)
                continue
            value = float(q.value)
            negative = value < 0
            left.barh(index, value, height=0.62, color=VERMILLION if negative else BLUE,
                      hatch="///" if negative else None, edgecolor=INK if negative else BLUE,
                      linewidth=0.6)
            label = _minus(_apa(value)) + (" (check key)" if negative else "")
            left.text(value + (0.03 if value >= 0 else -0.03), index, label, va="center",
                      ha="left" if value >= 0 else "right", fontsize=8, color=INK)
        left.axvline(0, color=INK, linewidth=0.9)
        left.set_xlim(-1.15, 1.15)
        left.set_xlabel("Corrected item–total correlation (item vs. sum of the other items)")
        left.set_yticks(y, labels=names)
        left.invert_yaxis()
        left.grid(axis="x", color=GRID, linewidth=0.6)
        left.set_axisbelow(True)
        left.legend(handles=[Patch(facecolor=BLUE, edgecolor=BLUE, label="positive"),
                             Patch(facecolor=VERMILLION, edgecolor=INK, hatch="///",
                                   label="negative: possibly reverse-keyed, not recoded")],
                    loc="lower left", fontsize=7.5, frameon=False,
                    bbox_to_anchor=(0, 1.0), ncol=2)

        values = [float(row.alpha_if_deleted.value) for row in result.rows
                  if row.alpha_if_deleted.ok]
        reference = float(result.alpha.value) if result.alpha.ok else None
        span = values + ([reference] if reference is not None else [])
        for index, row in enumerate(result.rows):
            q = row.alpha_if_deleted
            if not q.ok:
                right.text(0.5, index, q.text(), va="center", ha="center", fontsize=8,
                           transform=right.get_yaxis_transform())
                continue
            rises = row.alpha_change.ok and row.alpha_change.value > 0
            right.plot([float(q.value)], [index], marker="^" if rises else "o", markersize=7,
                       color=VERMILLION if rises else BLUE, markeredgecolor=INK,
                       markeredgewidth=0.6, linestyle="none")
            right.annotate(_minus(_apa(float(q.value))), (float(q.value), index),
                           xytext=(7, 0), textcoords="offset points", va="center", fontsize=8,
                           color=INK)
        if reference is not None:
            right.axvline(reference, color=INK, linestyle="--", linewidth=1.0)
        if span:
            low, high = min(span), max(span)
            pad = max(0.03, (high - low) * 0.15)
            right.set_xlim(low - pad, high + pad)
        right.set_xlabel("α if the item were deleted (nothing is deleted)")
        right.grid(axis="x", color=GRID, linewidth=0.6)
        right.set_axisbelow(True)
        handles = [Line2D([], [], marker="^", color=VERMILLION, markeredgecolor=INK,
                          linestyle="none", label="α would rise"),
                   Line2D([], [], marker="o", color=BLUE, markeredgecolor=INK,
                          linestyle="none", label="α would fall or stay")]
        if reference is not None:
            handles.append(Line2D([], [], color=INK, linestyle="--",
                                  label=f"α, all items = {_minus(_apa(reference))}"))
        right.legend(handles=handles, loc="lower left", fontsize=7.5, frameon=False,
                     bbox_to_anchor=(0, 1.0), ncol=3)
        figure.suptitle("Item diagnostics", x=0.01, ha="left", fontsize=11, fontweight="bold")
        note = (f"N = {result.n_complete} complete respondents. Hatched bars: negative "
                "correlation (check the scoring key). Triangles: α would be higher without the "
                "item; removing an item changes what the scale measures. Nothing was deleted "
                "or recoded.")
        figure.text(0.01, 0.01, textwrap.fill(note, 150), fontsize=7.5, va="bottom", ha="left",
                    color=INK)
        figure.tight_layout(rect=(0, 0.07, 1, 0.95))
        buffer = BytesIO()
        figure.savefig(buffer, format="png", dpi=dpi, facecolor="white", metadata={
            "Software": None, "Title": "Item diagnostics",
            "Description": describe_chart(result)})
    return buffer.getvalue()


__all__ = [
    "ENGINE_VERSION", "METHOD_ID", "OMEGA_ASSUMPTIONS", "MAX_ITEM_CATEGORIES", "MAX_ITEM_RANGE",
    "ItemResponseProblem", "item_response_problems", "ReverseKeys", "confirmed_reverse_keys",
    "ItemRow", "ItemDiagnostics", "diagnose_items", "make_item_diagnostics_chart",
    "describe_chart",
]
