"""Evidence-first interpretation wizard: never infer statistics from prose.

The current analysis result object is the *only* source of numeric facts.
Method choice and assumption review are visible human decisions. If an
estimate/CI was not calculated, show that explicitly instead of inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from statistical_guide import SCREEN_TERMS, SOURCES, TERMS


@dataclass(frozen=True)
class MethodProfile:
    rationale: str
    assumptions: tuple[str, ...]
    limitation: str


METHOD_PROFILES: dict[str, MethodProfile] = {
    "descriptive": MethodProfile(
        "Describe the variable using its confirmed measurement level; descriptive "
        "plots and summaries do not test causal or group hypotheses.",
        ("Confirm categorical, ordinal, or quantitative scale",
         "Inspect missing values and outliers", "Check that any grouping is meaningful"),
        "A distribution alone cannot establish causation or representativeness."),
    "reliability": MethodProfile(
        "Estimate internal consistency for items intended to measure the same construct.",
        ("Confirm theoretical coherence and dimensionality of items",
         "Reverse-score keyed items before estimation",
         "Check missingness, sample size and factor-model assumptions"),
        "Alpha or omega cannot establish validity or test–retest reliability."),
    "factor": MethodProfile(
        "Explore covariance structure (EFA) or total-variance components (PCA); "
        "they answer different methodological questions.",
        ("Verify sample adequacy and factorability",
         "Review dimensionality, retention and rotation decisions",
         "Check measurement level, outliers and interpretation of factors"),
        "Exploratory loadings are not confirmation of a measurement model."),
    "correlation": MethodProfile(
        "Evaluate an association between two variables. Pearson addresses "
        "linearity; Spearman addresses rank-monotonic association.",
        ("Confirm measurement levels and independence",
         "Inspect scatterplot, outliers and linearity/monotonicity",
         "Check how incomplete pairs were handled"),
        "A correlation is not causal evidence."),
    "matrix": MethodProfile(
        "Inspect several pairwise correlations with appropriate attention "
        "to multiple comparisons and changing pairwise sample sizes.",
        ("Review variable measurement levels",
         "Inspect missing data and pairwise sample sizes",
         "Account for multiple testing before confirmatory claims"),
        "A heatmap does not test causal structure."),
    "groups": MethodProfile(
        "Compare two independent groups with a test compatible with the outcome scale.",
        ("Confirm independent participants and grouping",
         "Review outcome scale, distributions and outliers",
         "Check missingness and variance assumptions where relevant"),
        "Differences do not automatically imply causal effects."),
    "paired": MethodProfile(
        "Compare two measurements from the same participants; independent "
        "samples require another analysis.",
        ("Verify subject-level matching and order of measurements",
         "Inspect paired differences and their distribution",
         "Check missing pairs and unusual changes"),
        "Within-person changes alone do not prove an intervention effect."),
    "chi": MethodProfile(
        "Test association between categorical variables using observed and "
        "expected cell counts.",
        ("Confirm nominal/ordinal categories and independent observations",
         "Check expected cell counts and sparse tables",
         "Consider exact tests when asymptotic assumptions fail"),
        "Statistical association is not causal evidence."),
    "omnibus": MethodProfile(
        "Compare three or more independent groups using ANOVA or a rank-based alternative.",
        ("Confirm independence and outcome scale",
         "Inspect group distributions and variance heterogeneity",
         "Define post-hoc comparison family and adjustment"),
        "An omnibus result does not identify which groups differ."),
    "regression": MethodProfile(
        "Estimate conditional associations between a continuous outcome "
        "and predictors with a linear model.",
        ("Inspect linearity, residual patterns and influential observations",
         "Check independence, multicollinearity and model specification",
         "Review heteroskedasticity and missing-data exclusions"),
        "In-sample explained variance does not imply external prediction or causality."),
    "logistic": MethodProfile(
        "Model conditional odds of an explicitly coded binary outcome.",
        ("Verify 0/1 outcome and events per predictor",
         "Inspect separation, influential cases and linearity in the logit",
         "Check calibration and external validation separately"),
        "Odds ratios are not risk ratios; in-sample ROC is not external validation."),
    "ancova": MethodProfile(
        "Estimate adjusted group contrasts at specified covariate values.",
        ("Review covariate measurement and group independence",
         "Check homogeneous slopes or use a justified interaction model",
         "Inspect residual assumptions and extrapolation"),
        "Adjusted means are conditional model estimates, not raw means."),
    "repeated": MethodProfile(
        "Compare three or more occasions within the same participants.",
        ("Verify a stable participant across each occasion",
         "Review missing complete cases and time ordering",
         "Check sphericity or justified correction for RM ANOVA"),
        "Repeated observations and temporal trends do not alone show causality."),
}


_METHOD_LABELS = {
    "welch": "Welch independent-samples t test",
    "mannwhitney": "Mann–Whitney U test",
    "paired_t": "Paired-samples t test",
    "wilcoxon": "Wilcoxon signed-rank test",
    "pearson": "Pearson product–moment correlation",
    "spearman": "Spearman rank correlation",
    "anova": "One-way analysis of variance",
    "welch_anova": "Welch analysis of variance",
    "kruskal": "Kruskal–Wallis test",
    "friedman": "Friedman repeated-ranks test",
    "rm_anova": "Repeated-measures analysis of variance",
    "pca": "Principal component analysis",
    "efa": "Exploratory factor analysis",
}


@dataclass(frozen=True)
class EvidenceRow:
    parameter: str
    estimate: str
    ci: str = "Not calculated"
    p: str = "Not calculated"


@dataclass(frozen=True)
class AnalysisEvidence:
    section: str
    title: str
    method: str
    rationale: str
    assumptions: tuple[str, ...]
    limitation: str
    rows: tuple[EvidenceRow, ...]
    warnings: tuple[str, ...]
    source_report: str
    figure_png: bytes | None
    has_structured_values: bool
    n_complete: int | None = None
    n_total: int | None = None


def _number(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    if isinstance(value, int):
        return str(value)
    clean = float(value)
    if round(clean, 3) == 0:
        clean = 0.
    text = f"{clean:.3f}"
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text


def _p(value: Any) -> str:
    number = _number(value)
    if number is None or float(value) < 0 or float(value) > 1:
        return "Not calculated"
    if float(value) < .001:
        return "< .001"
    return "= " + (number if number != ".000" else ".001")


def _ci(low: Any, high: Any) -> str:
    left, right = _number(low), _number(high)
    if left is None or right is None or float(low) > float(high):
        return "Not calculated"
    return f"[{left}, {right}]"


def _row(label: str, value: Any, *, low=None, high=None, p=None) -> EvidenceRow | None:
    number = _number(value)
    if number is None:
        return None
    return EvidenceRow(label, number, _ci(low, high),
                       _p(p) if p is not None else "Not calculated")


def _method_name(section: str, title: str, result: object | None) -> str:
    if result is None:
        return title
    explicit = getattr(result, "method", None)
    if explicit:
        return _METHOD_LABELS.get(str(explicit).lower(), str(explicit))
    if section == "reliability":
        return "McDonald’s omega" if hasattr(result, "omega") else "Cronbach’s alpha"
    return title


def build_analysis_evidence(
    section: str, title: str, report: str, png: bytes | None,
    result: object | None = None,
) -> AnalysisEvidence:
    """Pull *verified* numerical fields directly from a calculated result."""
    profile = METHOD_PROFILES.get(section)
    if profile is None:
        raise ValueError(f"No interpretation profile for {section!r}.")
    if not isinstance(report, str) or not report.strip():
        raise ValueError("Run a successful analysis before opening the wizard.")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("A completed analysis title is required.")
    rows: list[EvidenceRow] = []
    n_complete = getattr(result, "n_complete", None)
    n_total = getattr(result, "n_total", None)
    if section == "groups" and n_complete is None and result is not None:
        n_a, n_b = getattr(result, "n_a", None), getattr(result, "n_b", None)
        if all(isinstance(n, int) and n >= 0 for n in (n_a, n_b)):
            n_complete = n_a + n_b  # Verified retained group counts.
    for label, value in [("Complete observations (N)", n_complete),
                         ("Original records", n_total)]:
        row = _row(label, value)
        if row:
            rows.append(row)

    if result is not None:
        if section == "correlation":
            rows.extend(filter(None, [
                _row("Pearson r" if result.method == "pearson" else "Spearman ρ",
                     result.coefficient, low=result.ci_low, high=result.ci_high,
                     p=result.p_value)
            ]))
        elif section == "reliability":
            rows.extend(filter(None, [
                _row("Cronbach’s α", getattr(result, "alpha", None),
                     low=getattr(result, "ci_low", None),
                     high=getattr(result, "ci_high", None)),
                _row("McDonald’s ω", getattr(result, "omega", None)),
            ]))
        elif section == "chi":
            rows.extend(filter(None, [
                _row("χ²", getattr(result, "chi2", None), p=getattr(result, "p_value", None)),
                _row("Cramér’s V", getattr(result, "cramers_v", None)),
            ]))
        elif section in {"groups", "paired"}:
            # In these modules the CI belongs to a mean difference, NOT to
            # Cohen's d or an unrelated rank effect.
            rows.extend(filter(None, [
                _row("Test statistic", getattr(result, "statistic", None),
                     p=getattr(result, "p_value", None)),
                _row(str(getattr(result, "effect_name", "Effect size")),
                     getattr(result, "effect_size", None)),
                _row("Mean difference" if section == "groups" else "Mean change",
                     getattr(result, "mean_difference", None) if section == "groups"
                     else getattr(result, "mean_change", None),
                     low=getattr(result, "ci_low", None),
                     high=getattr(result, "ci_high", None)),
            ]))
        elif section in {"omnibus", "repeated"}:
            rows.extend(filter(None, [
                _row("Overall statistic", getattr(result, "statistic", None),
                     p=getattr(result, "p_primary", None) if section == "repeated"
                     else getattr(result, "p_value", None)),
                _row(str(getattr(result, "effect_name", "Effect size")),
                     getattr(result, "effect_size", None)),
            ]))
        elif section == "regression":
            rows.extend(filter(None, [
                _row("Model R²", getattr(result, "r_squared", None)),
                _row("Adjusted R²", getattr(result, "adjusted_r_squared", None)),
                _row("Model F", getattr(result, "f_value", None),
                     p=getattr(result, "f_p", None)),
            ]))
            for term in getattr(result, "coefficients", ()):
                rows.extend(filter(None, [
                    _row(f"B: {term.name}", term.b,
                         low=term.ci_low, high=term.ci_high, p=term.p)
                ]))
        elif section == "logistic":
            rows.extend(filter(None, [
                _row("McFadden R²", getattr(result, "mcfadden_r2", None)),
                _row("In-sample ROC AUC", getattr(result, "roc_auc", None)),
                _row("Likelihood-ratio χ²", getattr(result, "llr", None),
                     p=getattr(result, "llr_p", None)),
            ]))
            for term in getattr(result, "coefficients", ()):
                rows.extend(filter(None, [
                    _row(f"OR: {term.name}", term.odds_ratio,
                         low=term.or_low, high=term.or_high, p=term.p)
                ]))
        elif section == "ancova":
            rows.extend(filter(None, [
                _row("Adjusted group F", getattr(result, "f_group", None),
                     p=getattr(result, "p_group", None)),
                _row("Partial η²", getattr(result, "eta_squared_partial", None)),
                _row("Model R²", getattr(result, "r_squared", None)),
            ]))
            for group in getattr(result, "groups", ()):
                rows.extend(filter(None, [
                    _row(f"Adjusted mean: {group.label}", group.adjusted_mean,
                         low=group.ci_low, high=group.ci_high)
                ]))
        elif section == "factor":
            rows.extend(filter(None, [
                _row("Overall KMO", getattr(result, "kmo", None)),
                _row("Bartlett χ²", getattr(result, "bartlett_chi2", None),
                     p=getattr(result, "bartlett_p", None)),
                _row("Extracted factors/components",
                     getattr(result, "n_components", None)),
            ]))
        elif section == "descriptive":
            rows.extend(filter(None, [
                _row("Shapiro–Wilk W", getattr(result, "shapiro_w", None),
                     p=getattr(result, "shapiro_p", None)),
                _row("Levene W", getattr(result, "levene_w", None),
                     p=getattr(result, "levene_p", None)),
            ]))
        # matrix lacks a single defensible coefficient or common N: show the
        # full source report without inventing a representative estimate.

    warnings = tuple(
        str(value) for value in getattr(result, "warnings", ())
        if str(value).strip()
    ) if result is not None else ()
    if not rows:
        rows.append(EvidenceRow(
            "Structured numeric results", "Not captured",
            "Not calculated", "Not calculated",
        ))
    if not any(row.ci != "Not calculated" for row in rows):
        warnings += (
            "No confidence interval is available in this analysis summary. "
            "Do not infer one from the point estimate.",
        )
    if not any(
        any(token in row.parameter.lower() for token in (
            "effect", "cohen", "hedges", "eta", "cramér", "pearson",
            "spearman", "omega", "α", "r²", "or:", "mann", "rank"
        ))
        for row in rows
    ):
        warnings += (
            "A separate effect-size estimate is not available in the "
            "structured summary; consult the calculation output.",
        )
    return AnalysisEvidence(
        section=section, title=title, method=_method_name(section, title, result),
        rationale=profile.rationale, assumptions=profile.assumptions,
        limitation=profile.limitation, rows=tuple(rows), warnings=warnings,
        source_report=report, figure_png=png,
        has_structured_values=result is not None,
        n_complete=n_complete if isinstance(n_complete, int) else None,
        n_total=n_total if isinstance(n_total, int) else None,
    )


def source_references(section: str) -> tuple[str, ...]:
    """Only cite works relevant to the current method plus APA 7 itself."""
    source_ids = {"apa"}
    for key in SCREEN_TERMS.get(section, ()):
        source_ids.add(TERMS[key].source)
    return tuple(
        SOURCES[key].label + " " + SOURCES[key].url
        for key in sorted(source_ids)
    )


def interpretation_summary(
    evidence: AnalysisEvidence, reviewed: set[str] | tuple[str, ...],
    researcher_notes: str = "",
) -> str:
    """Conservative, editable narrative. Never equate p with truth/causality."""
    checks = set(reviewed) & set(evidence.assumptions)
    unreviewed = [item for item in evidence.assumptions if item not in checks]
    lines = [
        f"Method: {evidence.method}. {evidence.rationale}",
        "Verified calculation output:",
    ]
    for row in evidence.rows:
        detail = row.parameter + ": " + row.estimate
        if row.ci != "Not calculated":
            detail += f", 95% CI {row.ci}"
        if row.p != "Not calculated":
            detail += f", p {row.p}"
        lines.append(detail + ".")
    lines.append(
        "Assumptions: " + (
            "All listed checks have been reviewed by the researcher; this "
            "is not an automated confirmation that they hold."
            if not unreviewed else
            str(len(unreviewed)) + " check(s) remain unreviewed: "
            + "; ".join(unreviewed) + "."
        )
    )
    lines.append("Interpretive limitation: " + evidence.limitation)
    lines.extend("Caution: " + warning for warning in evidence.warnings)
    if researcher_notes.strip():
        lines.append("Researcher interpretation (editable, unverified): "
                     + researcher_notes.strip())
    return "\n".join(lines)
