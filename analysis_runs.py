"""UI-independent runs of the validated statistical engine.

Each ``run_*`` function performs exactly the calculation, chart and report
composition that the classic workspace callbacks in ``research_app.py``
perform, and returns one :class:`AnalysisRun`. The Stage 33 workspace uses
these functions, so the new interface cannot drift from validated results:
``tests/test_analysis_runs.py`` drives the classic callbacks and these runs
on the same data and requires identical reports and result values.

Nothing here formats numbers on its own; numbers come from the engine's
reporting modules. Tables mirror the classic on-screen tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from correlation import analyze_correlation
from correlation_charts import make_correlation_chart
from correlation_matrix import analyze_correlation_matrix
from correlation_matrix_charts import make_correlation_matrix_chart
from correlation_reporting import apa_p_value, format_correlation_report
from descriptive_charts import make_descriptive_chart
from explore_analysis import explore_quantitative, format_explore_report, make_explore_chart
from factor_charts import make_factor_chart
from factor_exploration import analyze_factor_exploration
from factor_reporting import factor_main, format_factor_report
from group_comparison import compare_independent_groups
from group_comparison_charts import make_group_comparison_chart
from group_comparison_reporting import format_group_comparison
from interpretation_wizard import AnalysisEvidence, build_analysis_evidence
from logistic_analysis import binary_logistic_regression
from logistic_charts import make_logistic_chart
from logistic_reporting import format_logistic_report, logistic_brief, logistic_main
from omega_analysis import analyze_omega
from omega_bootstrap import bootstrap_omega
from omega_charts import make_omega_chart
from omega_reporting import format_omega_report, omega_summary
from omnibus_analysis import analyze_omnibus
from omnibus_charts import make_omnibus_chart
from omnibus_reporting import format_omnibus_report, format_omnibus_summary, interpret_omnibus
from paired_analysis import analyze_paired
from paired_charts import make_paired_chart
from paired_presentation import paired_descriptives, paired_interpretation, paired_main_result
from paired_reporting import format_paired_report
from posthoc_analysis import analyze_posthoc
from posthoc_reporting import format_posthoc_report
from regression_analysis import analyze_regression
from regression_charts import make_regression_chart
from regression_reporting import format_regression_report, regression_brief
from reliability import analyze_cronbach
from stat_results import describe_categorical, describe_quantitative
from reliability_charts import make_reliability_chart
from reliability_reporting import ALPHA_GUIDE, apa_reliability_report
from repeated_analysis import analyze_repeated
from repeated_charts import make_repeated_chart
from repeated_reporting import format_repeated_report, repeated_brief, repeated_main
from ancova_analysis import analyze_ancova
from ancova_charts import make_ancova_chart
from ancova_reporting import ancova_brief, ancova_main, format_ancova_report
from chi_square import analyze_chi_square
from chi_square_charts import make_chi_square_chart
from chi_square_reporting import format_chi_square_report, interpret_chi_square, summarize_chi_square
from variable_rules import looks_like_identifier


@dataclass(frozen=True)
class ResultTable:
    """A table exactly as the classic workspace displays it."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class AnalysisRun:
    """One completed calculation with everything needed to present it."""

    section: str                       # classic screen key, e.g. "groups"
    title: str                         # classic output title
    report: str                        # classic report text (copy/TXT/Word source)
    png: bytes | None
    result: Any = None                 # engine result object (verified values)
    summary: str = ""                  # classic "main result" line(s)
    interpretation: str = ""           # classic plain-language brief
    descriptives: str = ""
    guide: str = ""
    warnings: tuple[str, ...] = ()
    tables: tuple[ResultTable, ...] = ()
    inputs: dict = field(default_factory=dict)  # provenance: variables, options

    def evidence(self) -> AnalysisEvidence:
        """Interpretation evidence pulled from the verified result object."""
        return build_analysis_evidence(
            self.section, self.title, self.report, self.png, self.result,
        )


def _join_warnings(warnings) -> str:
    return "\n".join(warnings)


def _p_cell(p: float) -> str:
    return f"{p:.3f}" if p >= 0.001 else "< .001"


# ---------------------------------------------------------------- describe
def run_descriptive(df: pd.DataFrame, variable: str, scale: str) -> AnalysisRun:
    """Single-variable summary + chart (classic ``analyze_variable``)."""
    if variable not in df.columns:
        raise ValueError(f"Unknown variable: {variable}")
    if looks_like_identifier(variable) or scale == "id":
        raise ValueError("An identifier is not a research measurement.")
    if scale not in ("scale", "nominal", "ordinal"):
        raise ValueError("Confirm the measurement scale before analysis.")
    values = df[variable]
    missing = int(values.isna().sum())
    png = make_descriptive_chart(values, scale)
    if scale == "scale":
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        std = f"{numeric.std():.2f}" if len(numeric) > 1 else "N/A"
        text = (
            f"{variable} | N = {len(numeric)} | Missing = {missing}\n"
            f"Mean = {numeric.mean():.2f} | Median = {numeric.median():.2f}\n"
            f"SD = {std} | Min = {numeric.min():.2f} | "
            f"Max = {numeric.max():.2f}"
        )
        guide = (
            "Interpretation: these numbers describe the loaded sample only. "
            "The histogram shows the observed distribution; it does not "
            "prove normality or population-level conclusions."
        )
    else:
        counts = (
            values.astype("string").fillna("(missing)").value_counts().head(15)
        )
        lines = [f"{variable} | {scale} | Missing = {missing}"]
        lines += [f"{label}: {count}" for label, count in counts.items()]
        if values.nunique(dropna=False) > 15:
            lines.append("Showing only 15 most common categories.")
        text = "\n".join(lines)
        guide = (
            "Interpretation: the bars show response frequencies, not "
            "evidence of differences between groups. For ordinal data, "
            "response order matters; for nominal data, categories have no "
            "natural numeric distance."
        )
    # Stage 36 (spec §8): the numbers also come as a structured result, so
    # the evidence table shows N, missing, M, SD, median, IQR, min and max
    # instead of "Not captured".
    structured = (describe_quantitative(values, variable) if scale == "scale"
                  else describe_categorical(values, variable, scale))
    return AnalysisRun(
        "descriptive", f"Descriptive: {variable}", text + "\n\n" + guide, png,
        result=structured, summary=text, guide=guide,
        inputs={"variable": variable, "scale": scale},
    )


def run_explore(df: pd.DataFrame, variable: str, group: str | None = None) -> AnalysisRun:
    investigation = explore_quantitative(df, variable, group)
    png = make_explore_chart(investigation)
    report = format_explore_report(investigation)
    return AnalysisRun(
        "descriptive", f"Explore: {variable}", report, png, investigation,
        summary=report, inputs={"variable": variable, "group": group},
    )


# ------------------------------------------------------------- reliability
CONSTRUCT_MESSAGE = "Confirm common construct and consistent scoring direction first."


def run_alpha(df: pd.DataFrame, items: list[str], construct_confirmed: bool) -> AnalysisRun:
    if not construct_confirmed:
        raise ValueError(CONSTRUCT_MESSAGE)
    analysis = analyze_cronbach(df, list(items))
    text = apa_reliability_report(analysis)
    warnings = _join_warnings(analysis.warnings)
    png = make_reliability_chart(analysis)
    return AnalysisRun(
        "reliability", "Cronbach alpha", text + "\n\n" + warnings, png, analysis,
        summary=text, guide=ALPHA_GUIDE, warnings=tuple(analysis.warnings),
        inputs={"items": list(items)},
    )


def run_omega(df: pd.DataFrame, items: list[str], construct_confirmed: bool,
              ci_repetitions: int = 0) -> AnalysisRun:
    if not construct_confirmed:
        raise ValueError(
            "Confirm common construct and correctly keyed reverse "
            "scoring before computing omega."
        )
    result = analyze_omega(df, list(items))
    ci = None
    extra_warning = ""
    if int(ci_repetitions):
        try:
            ci = bootstrap_omega(df, list(items), int(ci_repetitions))
        except ValueError as bootstrap_error:
            extra_warning = "Bootstrap CI not available: " + str(bootstrap_error)
    report = format_omega_report(result, ci)
    if extra_warning:
        report += "\n\n" + extra_warning
    png = make_omega_chart(result, ci)
    warnings = (*result.warnings, *([extra_warning] if extra_warning else []))
    table = ResultTable(
        "Item diagnostics",
        ("Item", "M", "SD", "Missing", "Unique", "Rest Pearson r",
         "Rest Spearman ρ", "Loading", "Uniqueness"),
        tuple(
            (item.name, f"{item.mean:.2f}", f"{item.sd:.2f}", str(item.missing),
             str(item.unique_answers), f"{item.corrected_item_rest_r:.2f}",
             f"{item.rank_item_rest_r:.2f}", f"{item.standardized_loading:.2f}",
             f"{item.uniqueness:.2f}")
            for item in result.diagnostics
        ),
    )
    return AnalysisRun(
        "reliability", "McDonald omega and item diagnostics", report, png, result,
        summary=omega_summary(result, ci), warnings=tuple(warnings), tables=(table,),
        inputs={"items": list(items), "ci_repetitions": int(ci_repetitions)},
    )


def run_factor(df: pd.DataFrame, items: list[str], method: str, count: int,
               rotation: str, confirmed: bool) -> AnalysisRun:
    result = analyze_factor_exploration(
        df, list(items), method, int(count), rotation, bool(confirmed),
    )
    png = make_factor_chart(result)
    report = format_factor_report(result)
    columns = (
        "Variable",
        *[f"{'PC' if result.method == 'pca' else 'F'}{j + 1}"
          for j in range(result.n_components)],
        "Uniqueness" if result.uniqueness is not None else "Item KMO",
    )
    extras = result.uniqueness if result.uniqueness is not None else result.item_kmo
    table = ResultTable(
        "Component / factor loading matrix", columns,
        tuple(
            (name, *[f"{x:+.3f}" for x in result.loadings[j, :]], f"{extras[j]:.3f}")
            for j, name in enumerate(result.items)
        ),
    )
    return AnalysisRun(
        "factor", "Exploratory PCA / EFA", report, png, result,
        summary=factor_main(result), warnings=tuple(result.warnings), tables=(table,),
        inputs={"items": list(items), "method": method, "count": int(count),
                "rotation": rotation},
    )


# ----------------------------------------------------------- relationships
def run_correlation(df: pd.DataFrame, x: str, y: str, method: str, scale_x: str,
                    scale_y: str, confirmed: bool) -> AnalysisRun:
    analysis = analyze_correlation(df, x, y, method, scale_x, scale_y, bool(confirmed))
    text = format_correlation_report(analysis)
    warnings = _join_warnings(analysis.warnings)
    png = make_correlation_chart(analysis)
    return AnalysisRun(
        "correlation", "Bivariate correlation", text + "\n\n" + warnings, png, analysis,
        summary=text, warnings=tuple(analysis.warnings),
        inputs={"x": x, "y": y, "method": method, "scale_x": scale_x, "scale_y": scale_y},
    )


def run_matrix(df: pd.DataFrame, items: list[str], method: str, confirmed: bool) -> AnalysisRun:
    analysis = analyze_correlation_matrix(df, list(items), method, bool(confirmed))
    label = "Pearson’s r" if analysis.method == "pearson" else "Spearman’s ρ"
    text = (
        f"Exploratory {label} matrix with {len(analysis.names)} variables.\n"
        "Each cell shows a coefficient and its pairwise-complete N.\n"
        "No significance tests or p-values are calculated for this matrix."
    )
    warnings = _join_warnings(analysis.warnings)
    png = make_correlation_matrix_chart(analysis)
    rows = ["\t".join(["Variable", *analysis.names])]
    cells = []
    for name, row in zip(analysis.names, analysis.coefficients):
        values = [f"{value:.3f}" if pd.notna(value) else "N/A" for value in row]
        rows.append("\t".join([name, *values]))
        cells.append((name, *values))
    table = ResultTable("Correlation matrix", ("Variable", *analysis.names), tuple(cells))
    return AnalysisRun(
        "matrix", "Exploratory correlation matrix",
        text + "\n\n" + "\n".join(rows) + "\n\n" + warnings, png, analysis,
        summary=text, warnings=tuple(analysis.warnings), tables=(table,),
        inputs={"items": list(items), "method": method},
    )


def run_chi_square(df: pd.DataFrame, a: str, b: str, confirmed: bool) -> AnalysisRun:
    analysis = analyze_chi_square(df, a, b, bool(confirmed))
    png = make_chi_square_chart(analysis)
    report = format_chi_square_report(analysis)
    return AnalysisRun(
        "chi", "Chi-square independence",
        report + "\n\n" + _join_warnings(analysis.warnings), png, analysis,
        summary=summarize_chi_square(analysis),
        interpretation=interpret_chi_square(analysis),
        warnings=tuple(analysis.warnings), inputs={"a": a, "b": b},
    )


# ------------------------------------------------------- group differences
def run_groups(df: pd.DataFrame, group: str, outcome: str, method: str, scale: str,
               independent: bool, assumptions: bool) -> AnalysisRun:
    comparison = compare_independent_groups(
        df, group, outcome, method, scale, bool(independent), bool(assumptions),
    )
    text = format_group_comparison(comparison)
    png = make_group_comparison_chart(comparison)
    return AnalysisRun(
        "groups", "Independent-group comparison",
        text + "\n\n" + _join_warnings(comparison.warnings), png, comparison,
        summary=text, warnings=tuple(comparison.warnings),
        inputs={"group": group, "outcome": outcome, "method": method, "scale": scale},
    )


def run_paired(df: pd.DataFrame, before: str, after: str, method: str, scale: str,
               same_people: bool, assumptions: bool) -> AnalysisRun:
    analysis = analyze_paired(
        df, before, after, method, scale, bool(same_people), bool(assumptions),
    )
    report = format_paired_report(analysis)
    png = make_paired_chart(analysis)
    return AnalysisRun(
        "paired", "Paired comparison",
        report + "\n\n" + _join_warnings(analysis.warnings), png, analysis,
        summary=paired_main_result(analysis),
        descriptives=paired_descriptives(analysis),
        interpretation=paired_interpretation(analysis),
        warnings=tuple(analysis.warnings),
        inputs={"before": before, "after": after, "method": method, "scale": scale},
    )


def run_omnibus(df: pd.DataFrame, group: str, outcome: str, method: str, scale: str,
                independent: bool, assumptions: bool) -> AnalysisRun:
    analysis = analyze_omnibus(
        df, group, outcome, method, scale, bool(independent), bool(assumptions),
    )
    png = make_omnibus_chart(analysis)
    report = format_omnibus_report(analysis)
    return AnalysisRun(
        "omnibus", "ANOVA / Kruskal–Wallis",
        report + "\n\n" + _join_warnings(analysis.warnings), png, analysis,
        summary=format_omnibus_summary(analysis),
        interpretation=interpret_omnibus(analysis),
        warnings=tuple(analysis.warnings),
        inputs={"group": group, "outcome": outcome, "method": method, "scale": scale},
    )


def run_posthoc(omnibus: AnalysisRun) -> AnalysisRun:
    """Pairwise follow-up of a completed omnibus run (classic composition)."""
    if omnibus.section != "omnibus" or omnibus.result is None:
        raise ValueError("Run the omnibus test first.")
    comparisons = analyze_posthoc(omnibus.result)
    text_report = format_posthoc_report(comparisons)
    if comparisons.omnibus_method == "kruskal":
        columns = ("Pair", "Rank diff.", "z", "p adj.", "Sig.")
        rows = tuple(
            (f"{p.first} - {p.second}", f"{p.estimate:+.2f}", f"{p.statistic:.2f}",
             _p_cell(p.p_adjusted), "Yes" if p.p_adjusted < 0.05 else "No")
            for p in comparisons.pairs
        )
    else:
        columns = ("Pair", "Mean diff.", "95% CI", "p adj.", "Sig.")
        rows = tuple(
            (f"{p.first} - {p.second}", f"{p.estimate:+.2f}",
             f"[{p.ci_low:.2f}, {p.ci_high:.2f}]", _p_cell(p.p_adjusted),
             "Yes" if p.p_adjusted < 0.05 else "No")
            for p in comparisons.pairs
        )
    report = (
        format_omnibus_report(omnibus.result)
        + "\n\n" + text_report
        + "\n\nAssumptions and limitations:\n"
        + "\n".join(comparisons.warnings)
    )
    summary = (
        f"{comparisons.method}: "
        f"{sum(p.p_adjusted < 0.05 for p in comparisons.pairs)} of "
        f"{len(comparisons.pairs)} pairs have adjusted p < .05."
    )
    return AnalysisRun(
        "omnibus", "ANOVA / Kruskal–Wallis with post-hoc", report, omnibus.png,
        omnibus.result, summary=omnibus.summary + "\n" + summary,
        interpretation=omnibus.interpretation,
        warnings=(*omnibus.warnings, *comparisons.warnings),
        tables=(ResultTable("Post-hoc pairwise comparisons", columns, rows),),
        inputs={**omnibus.inputs, "posthoc": comparisons.method},
    )


def run_repeated(df: pd.DataFrame, items: list[str], method: str, scale: str,
                 same_people: bool, assumptions: bool) -> AnalysisRun:
    result = analyze_repeated(
        df, list(items), method, scale, bool(same_people), bool(assumptions),
    )
    png = make_repeated_chart(result)
    report = format_repeated_report(result)
    table = ResultTable(
        "Holm-adjusted pairwise comparisons",
        ("Pair", "Change", "Statistic", "p (Holm)", "Sig."),
        tuple(
            (f"{pair.before} → {pair.after}", f"{pair.estimate:+.2f}",
             f"{pair.statistic:.2f}" if pair.statistic is not None else "N/A",
             "< .001" if pair.p_holm < .001 else f"{pair.p_holm:.3f}",
             "Yes" if pair.p_holm < .05 else "No")
            for pair in result.pairs
        ),
    )
    return AnalysisRun(
        "repeated", "Repeated measurements", report, png, result,
        summary=repeated_main(result), interpretation=repeated_brief(result),
        warnings=tuple(result.warnings), tables=(table,),
        inputs={"items": list(items), "method": method, "scale": scale},
    )


# ------------------------------------------------------------------ models
def run_regression(df: pd.DataFrame, outcome: str, predictors: list[str],
                   confirmed: bool, hc3: bool = False) -> AnalysisRun:
    chosen = [name for name in predictors if name != outcome]
    result = analyze_regression(df, outcome, chosen, bool(confirmed), bool(hc3))
    png = make_regression_chart(result)
    report = format_regression_report(result)
    summary = (
        f"N = {result.n_complete} | R² = {result.r_squared:.3f} | "
        f"Adjusted R² = {result.adjusted_r_squared:.3f}\n"
        f"F({result.model_df}, {result.residual_df}) = "
        f"{result.f_value:.2f}, {apa_p_value(result.f_p)}"
    )
    return AnalysisRun(
        "regression", "Linear regression", report, png, result,
        summary=summary, interpretation=regression_brief(result),
        warnings=tuple(result.warnings),
        inputs={"outcome": outcome, "predictors": chosen, "hc3": bool(hc3)},
    )


def run_logistic(df: pd.DataFrame, outcome: str, predictors: list[str],
                 confirmed: bool) -> AnalysisRun:
    chosen = [name for name in predictors if name != outcome]
    result = binary_logistic_regression(df, outcome, chosen, bool(confirmed))
    png = make_logistic_chart(result)
    report = format_logistic_report(result)
    table = ResultTable(
        "Odds ratios and 95% confidence intervals",
        ("Variable", "B", "OR", "OR 95% CI", "p"),
        tuple(
            (c.name, f"{c.b:+.3f}", f"{c.odds_ratio:.3f}",
             f"[{c.or_low:.3f}, {c.or_high:.3f}]", apa_p_value(c.p))
            for c in result.coefficients
        ),
    )
    return AnalysisRun(
        "logistic", "Binary logistic regression", report, png, result,
        summary=logistic_main(result), interpretation=logistic_brief(result),
        warnings=tuple(result.warnings), tables=(table,),
        inputs={"outcome": outcome, "predictors": chosen},
    )


def run_ancova(df: pd.DataFrame, outcome: str, group: str, covariates: list[str],
               mode: str, confirmed: bool) -> AnalysisRun:
    result = analyze_ancova(df, outcome, group, list(covariates), mode, bool(confirmed))
    png = make_ancova_chart(result)
    report = format_ancova_report(result)
    means = ResultTable(
        "Adjusted group means at covariate reference",
        ("Group", "N", "Raw mean", "Adjusted mean", "95% CI"),
        tuple(
            (g.label, str(g.n), f"{g.raw_mean:.2f}", f"{g.adjusted_mean:.2f}",
             f"[{g.ci_low:.2f}, {g.ci_high:.2f}]")
            for g in result.groups
        ),
    )
    pairs = ResultTable(
        "Holm-adjusted group comparisons",
        ("Pair", "Adjusted diff.", "t", "Holm p", "Sig."),
        tuple(
            (f"{p.first} → {p.second}", f"{p.difference:+.2f}", f"{p.t:.2f}",
             apa_p_value(p.p_holm), "Yes" if p.p_holm < .05 else "No")
            for p in result.pairs
        ),
    )
    return AnalysisRun(
        "ancova", "ANCOVA / General Linear Model", report, png, result,
        summary=ancova_main(result), interpretation=ancova_brief(result),
        warnings=tuple(result.warnings), tables=(means, pairs),
        inputs={"outcome": outcome, "group": group, "covariates": list(covariates),
                "mode": mode},
    )


# ------------------------------------------------------------ Stage 36 batches
def _family_report(table, interpretation, method_lines, warnings) -> str:
    lines = [table.title, "", " | ".join(table.columns)]
    lines += [" | ".join(row) for row in table.rows]
    lines += ["", "Interpretation:", *interpretation, "", "Methods:", *method_lines, "",
              "Notes:", *warnings]
    return "\n".join(lines)


def run_batch_correlation(df: pd.DataFrame, focal: str, others: list[str], method: str,
                          adjust: str = "holm", spearman_p: str = "permutation",
                          pearson_confirmed: bool = False, language: str = "en") -> AnalysisRun:
    """One variable against several (Stage 36, spec §4–5)."""
    from batch_charts import correlation_forest
    from batch_correlation import correlate_many

    family = correlate_many(df, focal, list(others), method=method, adjust=adjust,
                            spearman_p=spearman_p,
                            pearson_assumptions_confirmed=pearson_confirmed)
    table = family.table()
    first = next((row for row in family.rows if row.status == "ok"), None)
    method_lines = [f"Coefficient: {family.method_label}; complete pairs per pair (N per row)."]
    if first is not None:
        method_lines += [f"p-values: {first.p_method}.", f"Intervals: {first.ci_method}."]
    method_lines.append(f"Adjustment: {family.adjustment_text}; {family.family_size} tests.")
    if family.magnitude_rule != "none" and family.method != "kendall":
        from batch_correlation import MAGNITUDE_RULES

        method_lines.append(f"Magnitude labels: {MAGNITUDE_RULES[family.magnitude_rule][0]}.")
    interpretation = family.interpretation(language)
    report = _family_report(table, interpretation, method_lines, family.warnings)
    return AnalysisRun(
        "batch_correlation", table.title, report, correlation_forest(family), result=family,
        summary="\n".join(interpretation), interpretation="\n".join(interpretation),
        guide="\n".join(method_lines), warnings=tuple(family.warnings),
        tables=(ResultTable(table.title, table.columns, table.rows),),
        inputs={"focal": focal, "others": list(others), "method": method, "adjust": adjust,
                "spearman_p": spearman_p, "seed": family.seed, "resamples": family.resamples})


def run_batch_groups(df: pd.DataFrame, group: str, outcomes: list[str], *, scale: str,
                     two_group_method: str = "mannwhitney", adjust: str = "holm",
                     assumptions_confirmed: bool = False, language: str = "en") -> AnalysisRun:
    """The same groups compared on several outcomes (Stage 36, spec §6):
    Kruskal–Wallis for 3–8 groups, a two-group test for 2 groups."""
    from batch_charts import group_boxplots
    from batch_groups import compare_many, compare_two_many, group_sizes

    count = len(group_sizes(df, group))
    if count == 2:
        family = compare_two_many(df, group, list(outcomes), method=two_group_method,
                                  scale=scale, adjust=adjust,
                                  assumptions_confirmed=assumptions_confirmed)
        first = next((row for row in family.rows if row.status == "ok"), None)
        method_lines = [f"Test: {first.p_method if first else two_group_method}.",
                        f"Effect size: {first.effect_name if first else ''}."]
    else:
        family = compare_many(df, group, list(outcomes), adjust=adjust)
        first = next((row for row in family.rows if row.status == "ok"), None)
        method_lines = ["Test: Kruskal–Wallis H, tie-corrected.",
                        "Effect sizes: η²_H = (H − k + 1)/(N − k), truncated at 0; "
                        "ε²_R = H/(N − 1).",
                        "Pairwise: Dunn z tests with Holm adjustment within each outcome."]
        if first is not None:
            method_lines.insert(1, f"p-values: {first.p_method}.")
    method_lines.append(f"Adjustment across outcomes: {family.adjustment_text}; "
                        f"{family.family_size} tests.")
    from batch_groups import interpret_groups

    table = family.table()
    interpretation = interpret_groups(family, language)
    report = _family_report(table, interpretation, method_lines, family.warnings)
    return AnalysisRun(
        "batch_groups", table.title, report, group_boxplots(df, family), result=family,
        summary="\n".join(interpretation), interpretation="\n".join(interpretation),
        guide="\n".join(method_lines), warnings=tuple(family.warnings),
        tables=(ResultTable(table.title, table.columns, table.rows),),
        inputs={"group": group, "outcomes": list(outcomes), "adjust": adjust,
                "two_group_method": two_group_method if count == 2 else None})
