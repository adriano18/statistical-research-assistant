"""Tables, report, summary and interpretation of the path models (Stage 37).

Every number comes from a :class:`process_models.ProcessResult` (or its
:class:`process_models.Sensitivity`); nothing is recomputed here. Texts come
from :mod:`process_text` in English, Latvian or Russian (LV/RU drafts). The
report body (``format_process_report``) is English like every engine report;
the tables, the summary, the interpretation and the methods text follow the
researcher's language.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from process_text import columns as _columns
from process_text import t as _t

LANGUAGES = ("en", "lv", "ru")


@dataclass(frozen=True)
class ProcessTable:
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


# ------------------------------------------------------------------ numbers
def num(value, digits: int = 3) -> str:
    """A coefficient as shown: 3 decimals; very small non-zero values keep
    three significant digits (never a misleading 0.000)."""
    if value is None:
        return "—"
    value = float(value)
    if not math.isfinite(value):
        return "—"
    if value != 0 and abs(value) < 10 ** -digits:
        return f"{value:.2e}"
    text = f"{value:.{digits}f}"
    return text[1:] if text.startswith("-") and float(text) == 0 else text


def fixed(value, digits: int = 3) -> str:
    """A proportion (R², ΔR², f²) with fixed decimals; −0.000 is shown as 0.000."""
    if value is None or not math.isfinite(float(value)):
        return "—"
    text = f"{float(value):.{digits}f}"
    return text[1:] if text.startswith("-") and float(text) == 0 else text


def p_cell(p) -> str:
    if p is None or not math.isfinite(float(p)):
        return "—"
    p = min(max(float(p), 0.0), 1.0)
    return "< .001" if p < 0.001 else f"{p:.3f}".replace("0.", ".", 1)


def p_text(p) -> str:
    cell = p_cell(p)
    return "p " + cell if cell.startswith("<") else "p = " + cell


def ci(low, high, digits: int = 3) -> str:
    if low is None or high is None:
        return "—"
    return f"[{num(low, digits)}, {num(high, digits)}]"


def _language(language: str) -> str:
    return language if language in LANGUAGES else "en"


def _outcome_label(result, equation, language: str) -> str:
    if equation.key == "total":
        return _t(language, "cell.total_eq", outcome=equation.outcome)
    return equation.outcome


def _term(result, key: str, language: str) -> str:
    from process_models import term_name

    return term_name(result.spec, key, language)


# ------------------------------------------------------------------ tables
def process_tables(result, language: str = "en", sensitivity=None) -> tuple[ProcessTable, ...]:
    """Every table of the result, titles and columns in ``language``."""
    language = _language(language)
    model = result.spec.model
    tables: list[ProcessTable] = []

    rows = []
    for equation in result.equations:
        outcome = _outcome_label(result, equation, language)
        for c in equation.coefficients:
            beta = (num(c.beta) if c.beta is not None else
                    "—" if c.key == "const" else _t(language, "cell.not_defined"))
            rows.append((outcome, _term(result, c.key, language), num(c.b), num(c.se),
                         f"{c.t:.2f}", p_cell(c.p), ci(c.ci_low, c.ci_high), beta,
                         "—" if c.vif is None else f"{c.vif:.2f}"))
    tables.append(ProcessTable(_t(language, "table.paths", model=model),
                               _columns(language, "table.paths.columns"), tuple(rows)))

    tables.append(ProcessTable(
        _t(language, "table.fit", model=model), _columns(language, "table.fit.columns"),
        tuple((_outcome_label(result, e, language), str(e.n), fixed(e.r_squared),
               fixed(e.adj_r_squared), f"{e.f_value:.2f}", f"{e.df_model}, {e.df_resid}",
               p_cell(e.f_p)) for e in result.equations)))

    binary_x = ("warn.binary_x", {}) in result.notes
    if model == "4":
        effects = [e for e in result.effects if e.key in ("direct", "total")]
        tables.append(ProcessTable(
            _t(language, "table.effects", model=model),
            _columns(language, "table.effects.columns"),
            tuple((_effect_label(e, language), num(e.value), num(e.se), f"{e.t:.2f}",
                   p_cell(e.p), ci(e.ci_low, e.ci_high)) for e in effects)))
        tables.append(ProcessTable(
            _t(language, "table.indirect", model=model),
            _columns(language, "table.indirect.columns"),
            tuple((_effect_label(e, language, binary_x), num(e.value), num(e.se),
                   ci(e.ci_low, e.ci_high)) for e in result.indirect)))
    if result.interactions:
        tables.append(ProcessTable(
            _t(language, "table.interaction", model=model),
            _columns(language, "table.interaction.columns"),
            tuple((test.product, test.equation, fixed(test.delta_r2), f"{test.f_value:.2f}",
                   f"{test.df1}, {test.df2}", p_cell(test.p), fixed(test.f2))
                  for test in result.interactions)))
    if result.conditional:
        by_table: dict[str, list] = {}
        for e in result.conditional:
            by_table.setdefault(e.key.split("@")[0], []).append(e)
        for key, estimates in by_table.items():
            focal = (result.spec.x if key in ("cond:x",) or key.startswith("cond:a:")
                     else estimates[0].mediator)
            outcome = (result.spec.y if not key.startswith("cond:a:")
                       else estimates[0].mediator)
            tables.append(ProcessTable(
                _t(language, "table.conditional", model=model, focal=f"{focal} → {outcome}"),
                _columns(language, "table.conditional.columns"),
                tuple((num(e.w), _t(language, e.where), num(e.value), num(e.se), f"{e.t:.2f}",
                       p_cell(e.p), ci(e.ci_low, e.ci_high)) for e in estimates)))
    jn = result.johnson_neyman
    if jn is not None:
        if jn.points:
            jn_rows = tuple((num(point), f"{100 * below:.1f}%", f"{100 * above:.1f}%",
                             num(effect), num(se), p_cell(p))
                            for point, below, above, (effect, se, p)
                            in zip(jn.points, jn.below, jn.above, jn.effects))
        else:
            state = ("jn.state.significant" if jn.significant_everywhere
                     else "jn.state.not_significant")
            jn_rows = ((_t(language, "jn.none", state=_t(language, state),
                           alpha=f"{jn.alpha:g}"), "", "", "", "", ""),)
        tables.append(ProcessTable(_t(language, "table.jn"),
                                   _columns(language, "table.jn.columns"), jn_rows))
    if model in ("7", "14"):
        index = [e for e in result.indirect if e.key.startswith("index:")]
        tables.append(ProcessTable(
            _t(language, "table.index", model=model), _columns(language, "table.index.columns"),
            tuple((e.mediator, num(e.value), num(e.se), ci(e.ci_low, e.ci_high))
                  for e in index)))
        conditional = [e for e in result.indirect if e.key.startswith("cond_indirect:")]
        tables.append(ProcessTable(
            _t(language, "table.cond_indirect", model=model),
            _columns(language, "table.cond_indirect.columns"),
            tuple((e.mediator, num(e.w), _t(language, e.where), num(e.value), num(e.se),
                   ci(e.ci_low, e.ci_high)) for e in conditional)))
        direct = [e for e in result.effects if e.key == "direct"]
        tables.append(ProcessTable(
            _t(language, "table.effects", model=model),
            _columns(language, "table.effects.columns"),
            tuple((_effect_label(e, language), num(e.value), num(e.se), f"{e.t:.2f}",
                   p_cell(e.p), ci(e.ci_low, e.ci_high)) for e in direct)))

    tables.append(ProcessTable(
        _t(language, "table.diagnostics", model=model),
        _columns(language, "table.diagnostics.columns"),
        tuple((_outcome_label(result, e, language), p_cell(e.shapiro_p), p_cell(e.bp_p),
               num(e.cooks_max), str(e.cooks_over), num(e.leverage_max), str(e.leverage_over),
               "—" if e.max_vif is None else f"{e.max_vif:.2f}")
              for e in result.equations)))

    missing = result.missing
    tables.append(ProcessTable(
        _t(language, "table.missing"), _columns(language, "table.missing.columns"),
        tuple((name, str(count), f"{100 * count / missing.n_total:.1f}")
              for name, count in missing.by_variable)))
    if missing.comparison_meaningful:
        tables.append(ProcessTable(
            _t(language, "table.excluded"), _columns(language, "table.excluded.columns"),
            tuple((name, str(n_in), f"{num(m_in, 2)} ({num(sd_in, 2)})", str(n_out),
                   "—" if not math.isfinite(m_out) else f"{num(m_out, 2)} ({num(sd_out, 2)})",
                   num(smd, 2))
                  for name, n_in, m_in, sd_in, n_out, m_out, sd_out, smd in missing.comparison)))
    if sensitivity is not None:
        tables.append(sensitivity_table(result, sensitivity, language))
    return tuple(tables)


def sensitivity_table(result, sensitivity, language: str = "en") -> ProcessTable:
    language = _language(language)
    rows = []
    for row in sensitivity.rows:
        label = _focal_label(result, row, language)
        rows.append((label, f"{row.assumed:.2f}", str(row.n), str(row.replications),
                     f"{row.power:.3f}", f"{row.mc_se:.3f}"))
    return ProcessTable(_t(language, "table.sensitivity"),
                        _columns(language, "table.sensitivity.columns"), tuple(rows))


def _focal_label(result, row, language: str) -> str:
    spec = result.spec
    if row.focal_key == "interaction":
        return _t(language, "sensitivity.focal.interaction", product=_term(result, "x*w",
                                                                           language))
    key = {"4": "sensitivity.focal.indirect", "7": "sensitivity.focal.index7",
           "14": "sensitivity.focal.index14"}[spec.model]
    return _t(language, key, m=row.mediator)


def sensitivity_note(result, sensitivity, language: str = "en") -> str:
    language = _language(language)
    test = (_t(language, "sensitivity.test.t", alpha=f"{sensitivity.alpha:g}")
            if sensitivity.test == "t" else _t(language, "sensitivity.test.mc"))
    return _t(language, "sensitivity.note", test=test, replications=sensitivity.replications,
              seed=sensitivity.seed)


def _effect_label(estimate, language: str, binary_x: bool = False) -> str:
    """The label of a model quantity in ``language`` (from its key)."""
    key, mediator = estimate.key, estimate.mediator
    if key == "direct":
        return _t(language, "q.direct")
    if key == "total":
        return _t(language, "q.total")
    if key.startswith("indirect_std:"):
        return _t(language, "q.indirect_pstd" if binary_x else "q.indirect_std", m=mediator)
    if key == "indirect_std_total":
        return _t(language, "q.indirect_pstd_total" if binary_x else "q.indirect_std_total")
    if key.startswith("indirect:"):
        return _t(language, "q.indirect", m=mediator)
    if key == "indirect_total":
        return _t(language, "q.indirect_total")
    if key.startswith("index:"):
        return _t(language, "q.index", m=mediator)
    return estimate.label


# ------------------------------------------------------------------ texts
def model_title(result, language: str = "en") -> str:
    return _t(_language(language), f"model.{result.spec.model}")


def roles_line(result) -> str:
    spec = result.spec
    parts = [f"X = {spec.x}"]
    if spec.mediators:
        parts.append("M = " + ", ".join(spec.mediators))
    if spec.w:
        parts.append(f"W = {spec.w}")
    parts.append(f"Y = {spec.y}")
    if spec.covariates:
        parts.append("covariates: " + ", ".join(spec.covariates))
    return "; ".join(parts)


def methods_text(result, language: str = "en") -> str:
    """How the result was computed, in ``language`` (the 'methods' paragraph)."""
    language = _language(language)
    spec = result.spec
    covariates = (_t(language, "methods.covariates", names=", ".join(spec.covariates))
                  if spec.covariates else "")
    se = _t(language, "methods.se.hc3" if spec.hc3 else "methods.se.ols")
    parts = [_t(language, "methods", model=spec.model, n=result.n,
                excluded=result.missing.excluded, total=result.missing.n_total,
                covariates=covariates, se=se)]
    if result.bootstrap is not None:
        parts.append(_t(language, "methods.boot", level=f"{spec.level:.0%}",
                        resamples=result.bootstrap.resamples, seed=result.bootstrap.seed,
                        valid=result.bootstrap.valid))
    if spec.w:
        binary = any(p.where in ("w.low", "w.high") for p in result.w_points)
        parts.append(_t(language, "methods.w_binary" if binary else "methods.w_values"))
    if result.centering:
        parts.append(_t(language, "methods.center",
                        names=", ".join(_term(result, key, language)
                                        for key in result.centering)))
    elif spec.model in ("1", "7", "14"):
        parts.append(_t(language, "methods.nocenter"))
    if result.johnson_neyman is not None:
        parts.append(_t(language, "methods.jn", alpha=f"{result.johnson_neyman.alpha:g}"))
    return " ".join(parts)


def process_summary(result, language: str = "en") -> str:
    """The main result lines (numbers from the result only)."""
    language = _language(language)
    lines = [model_title(result, language) + " — " + roles_line(result),
             _t(language, "summary.n", n=result.n, total=result.missing.n_total)]
    model = result.spec.model
    if model == "4":
        for e in result.indirect:
            if e.key.startswith("indirect:") or e.key == "indirect_total":
                lines.append(_t(language, "summary.indirect",
                                m=e.mediator or _t(language, "q.indirect_total"),
                                est=num(e.value), low=num(e.ci_low), high=num(e.ci_high)))
    if model == "1":
        e = result.estimate("interaction")
        test = result.interactions[0]
        lines.append(_t(language, "summary.interaction", product=_term(result, "x*w", language),
                        est=num(e.value), low=num(e.ci_low), high=num(e.ci_high),
                        p=p_text(e.p), dr2=fixed(test.delta_r2)))
    if model in ("7", "14"):
        for e in result.indirect:
            if e.key.startswith("index:"):
                lines.append(_t(language, "summary.index", m=e.mediator, est=num(e.value),
                                low=num(e.ci_low), high=num(e.ci_high)))
    return "\n".join(lines)


def process_interpretation(result, language: str = "en") -> list[str]:
    """Cautious sentences: what the intervals show, never causal."""
    language = _language(language)
    model = result.spec.model
    out = []
    if model == "4":
        for e in result.indirect:
            if e.key.startswith("indirect:"):
                key = ("interp.indirect.excludes" if e.excludes_zero
                       else "interp.indirect.includes")
                out.append(_t(language, key, m=e.mediator, est=num(e.value)))
    if model in ("1",):
        e = result.estimate("interaction")
        key = "interp.interaction.yes" if e.p < 1 - result.spec.level else "interp.interaction.no"
        out.append(_t(language, key, focal=result.spec.x, outcome=result.spec.y,
                      p=p_text(e.p)))
    if model in ("7", "14"):
        for e in result.indirect:
            if e.key.startswith("index:"):
                key = "interp.index.excludes" if e.excludes_zero else "interp.index.includes"
                out.append(_t(language, key, m=e.mediator, est=num(e.value)))
    out += inconsistent_mediation(result, language)
    out.append(_t(language, "interp.not_causal"))
    if model in ("4", "7", "14"):
        out.append(_t(language, "interp.cross_sectional"))
    return out


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def inconsistent_mediation(result, language: str = "en") -> list[str]:
    """The wording guard of review S5: an indirect effect whose sign differs
    from the direct or the total effect is called inconsistent mediation
    (suppression; MacKinnon, Krull & Lockwood, 2000). The program never
    labels any pattern "partial" or "full" mediation."""
    language = _language(language)
    model = result.spec.model
    out: list[str] = []
    if model == "4":
        direct = result.estimate("direct").value
        total = result.estimate("total").value
        for e in result.indirect:
            if not (e.key.startswith("indirect:") or e.key == "indirect_total"):
                continue
            sign = _sign(e.value)
            if not sign:
                continue
            against_direct = _sign(direct) == -sign
            against_total = _sign(total) == -sign
            key = ("interp.inconsistent.both" if against_direct and against_total else
                   "interp.inconsistent.direct" if against_direct else
                   "interp.inconsistent.total" if against_total else None)
            if key:
                out.append(_t(language, key, m=e.mediator or _t(language, "q.indirect_total"),
                              ab=num(e.value), direct=num(direct), total=num(total)))
    elif model in ("7", "14"):
        direct = result.estimate("direct").value
        by_mediator: dict[str, list[str]] = {}
        for e in result.indirect:
            if e.key.startswith("cond_indirect:") and _sign(e.value) == -_sign(direct) != 0:
                by_mediator.setdefault(e.mediator, []).append(num(e.w))
        for mediator, values in by_mediator.items():
            out.append(_t(language, "interp.inconsistent.conditional", m=mediator,
                          values=", ".join(dict.fromkeys(values)), direct=num(direct)))
    return out


def notes(result, language: str = "en") -> list[str]:
    language = _language(language)
    return [_t(language, key, **params) for key, params in result.notes]


def render_table(table: ProcessTable) -> list[str]:
    lines = [table.title, " | ".join(table.columns)]
    lines += [" | ".join(row) for row in table.rows]
    return lines


def format_process_report(result, sensitivity=None, language: str = "en") -> str:
    """The copyable report: methods, tables, interpretation and notes."""
    language = _language(language)
    lines = [_t(language, "report.header"),
             model_title(result, language) + " — " + roles_line(result),
             "", methods_text(result, language), ""]
    for table in process_tables(result, language, sensitivity):
        lines += render_table(table) + [""]
    if sensitivity is not None:
        lines += [sensitivity_note(result, sensitivity, language), ""]
    lines.append(_t(language, "report.interpretation"))
    lines += process_interpretation(result, language)
    lines += ["", _t(language, "report.notes")]
    lines += notes(result, language)
    return "\n".join(lines)
