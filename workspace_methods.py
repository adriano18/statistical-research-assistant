"""Method catalog and deterministic guided advisor (no Flet imports).

``METHODS`` describes every classic analysis area once: variable roles,
options and the researcher confirmations the engine requires. The Guided
and All-methods modes both build their forms from it and both execute
through :func:`run_method`, which calls ``analysis_runs`` — the same
calculations the classic screens perform.

:func:`advise` maps a research goal, chosen variables and *researcher-
confirmed* measurement levels to a method. It never reads a p value and
never uses a normality test to choose: the rules follow the design
(independent vs. repeated), the measurement level and the number of
groups, and every recommendation lists alternatives and the checks the
researcher still has to make.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

import analysis_runs as runs

# ------------------------------------------------------------ catalog model


@dataclass(frozen=True)
class Role:
    key: str
    label: str                     # workspace_text key
    levels: tuple[str, ...]        # accepted confirmed levels
    multiple: bool = False
    minimum: int = 1
    optional: bool = False
    binary: bool = False           # numeric 0/1 required
    maximum: int | None = None     # engine limit for multiple roles


@dataclass(frozen=True)
class Option:
    key: str
    label: str                     # classic English label
    choices: tuple[tuple[str, str], ...]
    default: str


@dataclass(frozen=True)
class Confirmation:
    key: str
    label: str                     # classic English label, shown verbatim
    applies_to: tuple[str, ...] = ()   # option values it is required for ('' = always)


@dataclass(frozen=True)
class MethodSpec:
    key: str
    section: str                   # classic screen key
    family: str
    title: str                     # English method title (catalog)
    summary: str
    roles: tuple[Role, ...]
    options: tuple[Option, ...] = ()
    confirmations: tuple[Confirmation, ...] = ()
    runner: Callable | None = field(default=None, compare=False)


ORDERED = ("ordinal", "scale")
CATEGORICAL = ("nominal", "ordinal")
ANY = ("nominal", "ordinal", "scale")

INDEPENDENT = Confirmation(
    "independent", "I confirm that the two groups contain independent observations")
OMNI_INDEPENDENT = Confirmation(
    "independent", "I confirm the groups contain independent participants")


def _level(session, name):
    return session.level(name)


def _common_level(session, names):
    levels = {session.level(n) for n in names}
    if len(levels) != 1:
        raise ValueError("Repeated measurements must share one confirmed measurement level.")
    return levels.pop()


def _run_descriptive(df, roles, options, confirms, session):
    return runs.run_descriptive(df, roles["variable"], _level(session, roles["variable"]))


def _run_explore(df, roles, options, confirms, session):
    return runs.run_explore(df, roles["variable"], roles.get("group") or None)


def _run_alpha(df, roles, options, confirms, session):
    return runs.run_alpha(df, roles["items"], confirms.get("construct", False))


def _run_omega(df, roles, options, confirms, session):
    return runs.run_omega(df, roles["items"], confirms.get("construct", False),
                          int(options.get("ci", "0")))


def _run_factor(df, roles, options, confirms, session):
    return runs.run_factor(df, roles["items"], options["method"], int(options["count"]),
                           options["rotation"], confirms.get("design", False))


def _run_correlation(df, roles, options, confirms, session):
    return runs.run_correlation(
        df, roles["x"], roles["y"], options["method"], _level(session, roles["x"]),
        _level(session, roles["y"]), confirms.get("pearson", False))


def _run_batch_correlation(df, roles, options, confirms, session):
    return runs.run_batch_correlation(
        df, roles["x"], list(roles["ys"]), options["method"], options["adjust"],
        options["spearman_p"], confirms.get("pearson", False), language=_language(session))


def _run_batch_groups(df, roles, options, confirms, session):
    outcomes = list(roles["outcomes"])
    scale = "scale" if all(session.level(n) == "scale" for n in outcomes) else "ordinal"
    if not confirms.get("independent", False):
        raise ValueError("Confirm independent participants and group membership.")
    return runs.run_batch_groups(
        df, roles["group"], outcomes, scale=scale, two_group_method=options["two_group_method"],
        adjust=options["adjust"], assumptions_confirmed=confirms.get("assumptions", False),
        language=_language(session))


def _language(session) -> str:
    return getattr(session, "language", "en") or "en"


def _run_matrix(df, roles, options, confirms, session):
    return runs.run_matrix(df, roles["items"], options["method"], confirms.get("scales", False))


def _run_groups(df, roles, options, confirms, session):
    return runs.run_groups(df, roles["group"], roles["outcome"], options["method"],
                           _level(session, roles["outcome"]),
                           confirms.get("independent", False),
                           confirms.get("assumptions", False))


def _run_paired(df, roles, options, confirms, session):
    names = [roles["before"], roles["after"]]
    return runs.run_paired(df, names[0], names[1], options["method"],
                           _common_level(session, names),
                           confirms.get("same_people", False),
                           confirms.get("assumptions", False))


def _run_chi(df, roles, options, confirms, session):
    return runs.run_chi_square(df, roles["a"], roles["b"], confirms.get("categorical", False))


def _run_omnibus(df, roles, options, confirms, session):
    return runs.run_omnibus(df, roles["group"], roles["outcome"], options["method"],
                            _level(session, roles["outcome"]),
                            confirms.get("independent", False),
                            confirms.get("assumptions", False))


def _run_repeated(df, roles, options, confirms, session):
    items = list(roles["measures"])
    return runs.run_repeated(df, items, options["method"], _common_level(session, items),
                             confirms.get("same_people", False),
                             confirms.get("assumptions", False))


def _run_regression(df, roles, options, confirms, session):
    return runs.run_regression(df, roles["outcome"], list(roles["predictors"]),
                               confirms.get("model", False), options.get("hc3") == "yes")


def _run_logistic(df, roles, options, confirms, session):
    return runs.run_logistic(df, roles["outcome"], list(roles["predictors"]),
                             confirms.get("model", False))


def _run_ancova(df, roles, options, confirms, session):
    return runs.run_ancova(df, roles["outcome"], roles["group"],
                           list(roles.get("covariates") or []), options["mode"],
                           confirms.get("model", False))


METHODS: dict[str, MethodSpec] = {spec.key: spec for spec in (
    MethodSpec(
        "descriptive", "descriptive", "describe", "Descriptive statistics",
        "Frequencies or mean, median and SD with a chart that suits the measurement level.",
        (Role("variable", "role.variable", ANY),), runner=_run_descriptive),
    MethodSpec(
        "explore", "descriptive", "describe", "Explore distributions (boxplot, Q–Q)",
        "Boxplot, normal Q–Q plot and assumption diagnostics, optionally by group.",
        (Role("variable", "role.variable", ("scale",)),
         Role("group", "role.group_optional", CATEGORICAL, optional=True)),
        runner=_run_explore),
    MethodSpec(
        "alpha", "reliability", "measurement", "Cronbach’s α",
        "Internal consistency of items intended to measure one construct.",
        (Role("items", "role.items", ORDERED, multiple=True, minimum=3),),
        confirmations=(Confirmation(
            "construct",
            "I checked that the items measure one construct and reversed items are recoded"),),
        runner=_run_alpha),
    MethodSpec(
        "omega", "reliability", "measurement", "McDonald’s ω + item analysis",
        "One-factor omega with item–rest correlations, loadings and optional bootstrap CI.",
        (Role("items", "role.items", ORDERED, multiple=True, minimum=3, maximum=12),),
        options=(Option("ci", "Omega 95% bootstrap CI",
                        (("0", "Off (fast)"), ("200", "200 resamples (exploratory)"),
                         ("500", "500 resamples (more stable)")), "0"),),
        confirmations=(Confirmation(
            "construct",
            "I checked that the items measure one construct and reversed items are recoded"),),
        runner=_run_omega),
    MethodSpec(
        "factor", "factor", "measurement", "Exploratory factor / component analysis",
        "Factorability, retention (scree, parallel analysis) and loadings for EFA or PCA.",
        (Role("items", "role.items", ORDERED, multiple=True, minimum=3, maximum=12),),
        options=(
            Option("method", "Exploratory method",
                   (("efa", "Principal-axis factors (EFA)"),
                    ("pca", "Principal components (PCA)")), "efa"),
            Option("count", "Number of factors/components",
                   tuple((str(n), str(n)) for n in range(1, 6)), "1"),
            Option("rotation", "Factor rotation",
                   (("none", "None"), ("varimax", "Varimax (orthogonal EFA)"),
                    ("oblimin", "Oblimin (correlated factors)")), "none"),
        ),
        confirmations=(Confirmation(
            "design",
            "I checked the study design, measurement scales, independence and suitability"),),
        runner=_run_factor),
    MethodSpec(
        "correlation", "correlation", "relationships", "Correlation (Pearson / Spearman)",
        "Association between two ordinal or quantitative variables, with a scatterplot.",
        (Role("x", "role.x", ORDERED), Role("y", "role.y", ORDERED)),
        options=(Option("method", "Correlation method",
                        (("spearman", "Spearman’s ρ"), ("pearson", "Pearson’s r")),
                        "spearman"),),
        confirmations=(Confirmation(
            "pearson",
            "For Pearson only: I reviewed linearity, outliers, independence and "
            "suitability of the variables", applies_to=("pearson",)),),
        runner=_run_correlation),
    MethodSpec(
        "matrix", "matrix", "relationships", "Correlation matrix",
        "Exploratory pairwise coefficients with pairwise N, as a heatmap (no p values).",
        (Role("items", "role.items", ORDERED, multiple=True, minimum=2, maximum=8),),
        options=(Option("method", "Matrix method",
                        (("spearman", "Spearman’s ρ"), ("pearson", "Pearson’s r")),
                        "spearman"),),
        confirmations=(Confirmation(
            "scales",
            "I confirmed the measurement scales and study assumptions (Pearson: "
            "quantitative and linear; Spearman: ordinal or quantitative)"),),
        runner=_run_matrix),
    MethodSpec(
        "chi", "chi", "relationships", "Chi-square test of independence",
        "Association between two categorical variables with observed and expected counts.",
        (Role("a", "role.a", CATEGORICAL), Role("b", "role.b", CATEGORICAL)),
        confirmations=(Confirmation(
            "categorical",
            "I confirmed two categorical scales and independent observations"),),
        runner=_run_chi),
    MethodSpec(
        "groups", "groups", "differences", "Two independent groups (Welch t / Mann–Whitney U)",
        "Compare an ordinal or quantitative outcome between two independent groups.",
        (Role("outcome", "role.outcome", ORDERED), Role("group", "role.group", CATEGORICAL)),
        options=(Option("method", "Statistical method",
                        (("mannwhitney", "Mann–Whitney U"), ("welch", "Welch’s independent t")),
                        "mannwhitney"),),
        confirmations=(
            INDEPENDENT,
            Confirmation("assumptions",
                         "For Welch only: I reviewed outcome distributions, outliers and "
                         "suitability of mean comparisons", applies_to=("welch",)),
        ),
        runner=_run_groups),
    MethodSpec(
        "omnibus", "omnibus", "differences",
        "Three or more groups (ANOVA / Welch ANOVA / Kruskal–Wallis)",
        "Omnibus comparison of 3–8 independent groups, with Holm-adjusted post-hoc pairs.",
        (Role("outcome", "role.outcome", ORDERED), Role("group", "role.group", CATEGORICAL)),
        options=(Option("method", "Omnibus method",
                        (("kruskal", "Kruskal–Wallis H"), ("welch", "Welch ANOVA"),
                         ("anova", "One-way ANOVA")), "kruskal"),),
        confirmations=(
            OMNI_INDEPENDENT,
            Confirmation("assumptions",
                         "I reviewed distributions, outliers and assumptions of the chosen test"),
        ),
        runner=_run_omnibus),
    MethodSpec(
        "paired", "paired", "differences", "Two paired measurements (paired t / Wilcoxon)",
        "Within-person change between two measurements of the same people.",
        (Role("before", "role.x", ORDERED), Role("after", "role.y", ORDERED)),
        options=(Option("method", "Paired test",
                        (("wilcoxon", "Wilcoxon signed-rank"),
                         ("paired_t", "Paired-samples t-test")), "wilcoxon"),),
        confirmations=(
            Confirmation("same_people",
                         "Each row contains two measurements from the SAME participant"),
            Confirmation("assumptions",
                         "I reviewed difference scores, their symmetry/normality as "
                         "appropriate, outliers and independence between participants"),
        ),
        runner=_run_paired),
    MethodSpec(
        "repeated", "repeated", "differences",
        "Three or more repeated measurements (RM ANOVA / Friedman)",
        "Change across 3+ occasions of the same people, with Holm-adjusted pairs.",
        (Role("measures", "role.measures", ORDERED, multiple=True, minimum=3, maximum=8),),
        options=(Option("method", "Repeated-measures method",
                        (("friedman", "Friedman test"),
                         ("rm_anova", "Repeated-measures ANOVA")), "friedman"),),
        confirmations=(
            Confirmation("same_people",
                         "Selected columns measure the same construct in the SAME participants"),
            Confirmation("assumptions",
                         "I reviewed measurement scales, difference scores, outliers and "
                         "design assumptions"),
        ),
        runner=_run_repeated),
    MethodSpec(
        "regression", "regression", "models", "Linear regression",
        "Quantitative outcome explained by quantitative predictors, with diagnostics.",
        (Role("outcome", "role.outcome", ("scale",)),
         Role("predictors", "role.predictors", ("scale",), multiple=True, maximum=5)),
        options=(Option("hc3", "Use HC3 heteroskedasticity-robust coefficient standard errors",
                        (("no", "No"), ("yes", "Yes")), "no"),),
        confirmations=(Confirmation(
            "model", "I reviewed linearity, independence, outliers and predictor scales"),),
        runner=_run_regression),
    MethodSpec(
        "logistic", "logistic", "models", "Binary logistic regression",
        "0/1 outcome explained by quantitative predictors: odds ratios, ROC and calibration.",
        (Role("outcome", "role.outcome", ("nominal",), binary=True),
         Role("predictors", "role.predictors", ("scale",), multiple=True, maximum=5)),
        confirmations=(Confirmation(
            "model",
            "I confirmed independent observations, outcome coding, quantitative "
            "predictors and logit-linearity assumptions"),),
        runner=_run_logistic),
    MethodSpec(
        "ancova", "ancova", "models", "ANCOVA / general linear model",
        "Group differences adjusted for quantitative covariates (or group × covariate GLM).",
        (Role("outcome", "role.outcome", ("scale",)),
         Role("group", "role.group", CATEGORICAL),
         Role("covariates", "role.covariates", ("scale",), multiple=True, maximum=3)),
        options=(Option("mode", "Model",
                        (("ancova", "ANCOVA (common slopes)"),
                         ("interaction", "GLM (group × covariate interactions)")), "ancova"),),
        confirmations=(Confirmation(
            "model",
            "I reviewed independent observations, quantitative covariates, group design, "
            "covariate timing, linearity and outliers"),),
        runner=_run_ancova),
    MethodSpec(
        "batch_correlation", "batch_correlation", "relationships",
        "Correlations: one variable with several",
        "Pearson, Spearman or Kendall between one variable and several others in one run, "
        "with N per pair, intervals and a multiple-comparison adjustment.",
        (Role("x", "role.x", ORDERED),
         Role("ys", "role.y_many", ORDERED, multiple=True, minimum=2, maximum=40)),
        options=(Option("method", "Correlation method",
                        (("spearman", "Spearman’s ρ"), ("pearson", "Pearson’s r"),
                         ("kendall", "Kendall’s τ-b")), "spearman"),
                 Option("adjust", "Multiple-comparison adjustment",
                        (("holm", "Holm (familywise error)"),
                         ("bh", "Benjamini–Hochberg (false discovery rate)"),
                         ("bonferroni", "Bonferroni (familywise error)"),
                         ("none", "None (raw p only)")), "holm"),
                 Option("spearman_p", "Spearman p-value",
                        (("permutation", "Permutation (as the single analysis)"),
                         ("asymptotic", "t approximation (as SPSS reports)")), "permutation")),
        confirmations=(Confirmation(
            "pearson",
            "For Pearson only: I reviewed linearity, outliers, independence and "
            "suitability of the variables", applies_to=("pearson",)),),
        runner=_run_batch_correlation),
    MethodSpec(
        "batch_groups", "batch_groups", "differences", "Groups compared on several outcomes",
        "Kruskal–Wallis for 3–8 groups or a two-group test, on several outcomes in one run, "
        "with a multiple-comparison adjustment.",
        (Role("group", "role.group", CATEGORICAL),
         Role("outcomes", "role.outcomes", ORDERED, multiple=True, minimum=2, maximum=40)),
        options=(Option("adjust", "Multiple-comparison adjustment",
                        (("holm", "Holm (familywise error)"),
                         ("bh", "Benjamini–Hochberg (false discovery rate)"),
                         ("bonferroni", "Bonferroni (familywise error)"),
                         ("none", "None (raw p only)")), "holm"),
                 Option("two_group_method", "Test for two groups",
                        (("mannwhitney", "Mann–Whitney U"), ("welch", "Welch’s independent t")),
                        "mannwhitney")),
        confirmations=(
            INDEPENDENT,
            Confirmation("assumptions",
                         "I reviewed the outcome distributions, outliers and group sizes")),
        runner=_run_batch_groups),
)}

FAMILIES = ("describe", "measurement", "relationships", "differences", "models")


def default_options(spec: MethodSpec) -> dict[str, str]:
    return {option.key: option.default for option in spec.options}


def required_confirmations(spec: MethodSpec, options: dict) -> tuple[Confirmation, ...]:
    values = set(options.values())
    return tuple(c for c in spec.confirmations if not c.applies_to or values & set(c.applies_to))


def role_problems(spec: MethodSpec, roles: dict, session) -> list[tuple[str, dict]]:
    """(text key, params) for missing or unsuitable variables."""
    problems: list[tuple[str, dict]] = []
    chosen = []
    for role in spec.roles:
        value = roles.get(role.key)
        names = list(value or []) if role.multiple else ([value] if value else [])
        if not names:
            if not role.optional:
                problems.append(("block.choose", {"role": role.label}))
            continue
        if role.multiple and len(names) < role.minimum:
            problems.append(("block.need_items", {"count": role.minimum}))
        if role.multiple and role.maximum and len(names) > role.maximum:
            problems.append(("block.max_items", {"count": role.maximum}))
        for name in names:
            info = session.variables.get(name)
            chosen.append(name)
            if info is None:
                problems.append(("block.unknown_variable", {"name": name}))
            elif info.confirmed == "id" or info.suggested == "id":
                problems.append(("block.identifier", {"name": name}))
            elif info.confirmed == "unknown":
                problems.append(("design.confirm_level", {"name": name}))
            elif info.confirmed not in role.levels:
                problems.append(("block.level_for_role", {
                    "name": name, "level": f"level.{info.confirmed}", "role": role.label,
                    "allowed": allowed_levels(role.levels)}))
            elif role.binary and not info.binary:
                problems.append(("block.binary", {"name": name}))
    if len(chosen) != len(set(chosen)):
        problems.append(("block.same_variable", {}))
    if spec.key == "omnibus" and roles.get("group") and session.has_data:
        problems += group_count_problems(roles["group"], session)
    return problems


def group_count_problems(group: str, session) -> list[tuple[str, dict]]:
    """Explained before Run: a 3–8 group method needs 3–8 groups (Stage 36)."""
    labels = session.group_labels(group)
    if len(labels) == 2:
        return [("block.two_groups_for_omnibus", {"name": group, "labels": ", ".join(labels)})]
    if len(labels) > 8:
        return [("block.group_count", {"name": group, "count": len(labels)})]
    return []


def small_group_note(group: str, outcome: str, session) -> str:
    """Groups with fewer than five complete values for this outcome."""
    from batch_groups import group_sizes

    sizes = group_sizes(session.df, group, outcome)
    return ", ".join(f"{label} ({n})" for label, n in sizes.items() if n < 5)


class RoleProblems(ValueError):
    """Variables that do not suit a method: (text key, params) pairs for the
    interface to explain in the researcher's language (never shown raw)."""

    def __init__(self, problems: list[tuple[str, dict]]):
        self.problems = list(problems)
        super().__init__("; ".join(k for k, _ in self.problems))


def run_method(key: str, session, roles: dict, options: dict, confirms: dict):
    spec = METHODS[key]
    if not session.has_data:
        raise ValueError("Open a dataset first.")
    problems = role_problems(spec, roles, session)
    if problems:
        raise RoleProblems(problems)
    return spec.runner(session.df, roles, {**default_options(spec), **options}, confirms, session)


# ------------------------------------------------------------ guided advice
GOALS = ("compare", "change", "relate", "associate", "predict", "scale", "structure", "describe")

GOAL_ROLES: dict[str, tuple[Role, ...]] = {
    # Optional covariates turn the comparison into ANCOVA (adjusted means).
    "compare": (Role("outcome", "role.outcomes", ANY, multiple=True),
                Role("group", "role.group", CATEGORICAL),
                Role("covariates", "role.adjust_for", ("scale",), multiple=True, optional=True,
                     maximum=3)),
    "change": (Role("measures", "role.measures", ORDERED, multiple=True, minimum=2, maximum=8),),
    "relate": (Role("x", "role.x", ANY), Role("y", "role.y_many", ANY, multiple=True)),
    "associate": (Role("a", "role.a", CATEGORICAL), Role("b", "role.b", CATEGORICAL)),
    "predict": (Role("outcome", "role.outcome", ANY),
                Role("predictors", "role.predictors", ANY, multiple=True, maximum=5)),
    "scale": (Role("items", "role.items", ORDERED, multiple=True, minimum=3),),
    "structure": (Role("items", "role.items", ORDERED, multiple=True, minimum=3, maximum=12),),
    "describe": (Role("variable", "role.variable", ANY),
                 Role("group", "role.group_optional", CATEGORICAL, optional=True)),
}


@dataclass(frozen=True)
class Alternative:
    method: str
    options: dict
    note: str          # workspace_text key


@dataclass(frozen=True)
class Advice:
    method: str | None = None
    options: dict = field(default_factory=dict)
    roles: dict = field(default_factory=dict)        # mapped onto the method's roles
    reasons: tuple[tuple[str, dict], ...] = ()
    alternatives: tuple[Alternative, ...] = ()
    blockers: tuple[tuple[str, dict], ...] = ()
    design_checks: tuple[str, ...] = ()              # confirmation keys to ask in step 3

    @property
    def ready(self) -> bool:
        return self.method is not None and not self.blockers


def _names(value) -> list[str]:
    if not value:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def allowed_levels(levels) -> str:
    """Text keys of the levels a role accepts, joined for the interface."""
    return " / ".join(f"level.{level}" for level in levels)


def _level_blockers(session, names) -> list[tuple[str, dict]]:
    blockers = []
    for name in names:
        info = session.variables.get(name)
        if info is None:
            blockers.append(("block.unknown_variable", {"name": name}))
        elif info.suggested == "id" or info.confirmed == "id":
            blockers.append(("block.identifier", {"name": name}))
        elif info.confirmed == "unknown":
            blockers.append(("design.confirm_level", {"name": name}))
    return blockers


def advise(goal: str, selection: dict, session) -> Advice:
    """Deterministic recommendation from design + confirmed levels only."""
    if goal not in GOALS:
        return Advice(blockers=(("block.goal", {}),))
    roles = GOAL_ROLES[goal]
    names: list[str] = []
    missing = []
    for role in roles:
        chosen = _names(selection.get(role.key))
        if not chosen and not role.optional:
            missing.append(("block.choose", {"role": role.label}))
        if role.multiple and chosen and len(chosen) < role.minimum:
            missing.append(("block.need_items", {"count": role.minimum}))
        if role.multiple and role.maximum and len(chosen) > role.maximum:
            missing.append(("block.max_items", {"count": role.maximum}))
        names += chosen
    if missing:
        return Advice(blockers=tuple(missing))
    if len(names) != len(set(names)):
        return Advice(blockers=(("block.same_variable", {}),))
    blockers = _level_blockers(session, names)
    if blockers:
        return Advice(blockers=tuple(blockers))
    level = session.level
    advice = {
        "compare": _compare, "change": _change, "relate": _relate,
        "associate": _associate, "predict": _predict, "scale": _scale,
        "structure": _structure, "describe": _describe,
    }[goal](selection, session, level)
    if advice.blockers:
        return advice           # the question's own, most specific explanation
    for role in roles:          # each question accepts certain measurement levels
        for name in _names(selection.get(role.key)):
            confirmed = session.variables[name].confirmed
            if confirmed not in role.levels:
                blockers.append(("block.level_for_role", {
                    "name": name, "level": f"level.{confirmed}", "role": role.label,
                    "allowed": allowed_levels(role.levels)}))
    if blockers:
        return Advice(blockers=tuple(blockers))
    if advice.method:
        # Never offer a method its own variable checks would refuse.
        problems = role_problems(METHODS[advice.method], advice.roles, session)
        if problems:
            return replace(advice, blockers=tuple(problems))
    return advice


def _compare(sel, session, level):
    outcomes, group = _names(sel["outcome"]), sel["group"]
    labels = session.group_labels(group)
    count = len(labels)
    if level(group) == "scale":
        return Advice(blockers=(("block.group_quantitative", {"name": group}),))
    if len(outcomes) > 1:
        return _compare_many(outcomes, group, labels, sel, session, level)
    outcome = outcomes[0]
    out_level = level(outcome)
    covariates = _names(sel.get("covariates"))
    if covariates:
        return _compare_adjusted(outcome, group, covariates, labels, out_level)
    if out_level == "nominal":
        return Advice(
            "chi", {}, {"a": group, "b": outcome},
            reasons=(("why.nominal_outcome", {"outcome": outcome}),),
            design_checks=("categorical",))
    if count < 2 or count > 8:
        return Advice(blockers=(("block.group_count", {"name": group, "count": count}),))
    facts = ("design.groups_found", {"name": group, "count": count,
                                     "labels": ", ".join(labels[:8])})
    if count == 2:
        if out_level == "ordinal":
            return Advice(
                "groups", {"method": "mannwhitney"}, {"outcome": outcome, "group": group},
                reasons=(facts, ("why.two_groups", {}), ("why.ordinal_rank", {"outcome": outcome})),
                design_checks=("independent",))
        return Advice(
            "groups", {"method": "welch"}, {"outcome": outcome, "group": group},
            reasons=(facts, ("why.two_groups", {}), ("why.welch", {"outcome": outcome})),
            alternatives=(Alternative("groups", {"method": "mannwhitney"}, "alt.mannwhitney"),),
            design_checks=("independent", "assumptions"))
    small = small_group_note(group, outcome, session)
    if small:
        return Advice(
            "omnibus", {"method": "kruskal"}, {"outcome": outcome, "group": group},
            reasons=(facts, ("why.many_groups", {}), ("why.small_groups_rank",
                                                       {"name": group, "groups": small})),
            design_checks=("independent", "assumptions"))
    if out_level == "ordinal":
        return Advice(
            "omnibus", {"method": "kruskal"}, {"outcome": outcome, "group": group},
            reasons=(facts, ("why.many_groups", {}), ("why.ordinal_rank", {"outcome": outcome})),
            design_checks=("independent", "assumptions"))
    return Advice(
        "omnibus", {"method": "welch"}, {"outcome": outcome, "group": group},
        reasons=(facts, ("why.many_groups", {}), ("why.welch_anova", {"outcome": outcome})),
        alternatives=(Alternative("omnibus", {"method": "anova"}, "alt.anova"),
                      Alternative("omnibus", {"method": "kruskal"}, "alt.kruskal")),
        design_checks=("independent", "assumptions"))



def _compare_many(outcomes, group, labels, sel, session, level) -> Advice:
    """The same groups on several outcomes (Stage 36): one family."""
    if _names(sel.get("covariates")):
        return Advice(blockers=(("block.batch_with_covariates", {}),))
    levels = [level(o) for o in outcomes]
    if "nominal" in levels:
        return Advice(blockers=(("block.batch_nominal_outcomes", {}),))
    count = len(labels)
    if count < 2 or count > 8:
        return Advice(blockers=(("block.group_count", {"name": group, "count": count}),))
    roles = {"group": group, "outcomes": list(outcomes)}
    facts = ("design.groups_found", {"name": group, "count": count,
                                     "labels": ", ".join(labels[:8])})
    family = ("why.batch_family", {"count": len(outcomes)})
    if count == 2:
        if "ordinal" in levels:
            return Advice("batch_groups", {"two_group_method": "mannwhitney"}, roles,
                          reasons=(facts, family, ("why.two_groups", {})),
                          design_checks=("independent",))
        return Advice("batch_groups", {"two_group_method": "welch"}, roles,
                      reasons=(facts, family, ("why.two_groups", {})),
                      alternatives=(Alternative("batch_groups", {"two_group_method": "mannwhitney"},
                                                "alt.mannwhitney"),),
                      design_checks=("independent", "assumptions"))
    small = ", ".join(sorted({note for o in outcomes
                              for note in [small_group_note(group, o, session)] if note}))
    reasons = (facts, family, ("why.many_groups", {}), ("why.batch_kruskal", {}))
    if small:
        reasons += (("why.small_groups_rank", {"name": group, "groups": small}),)
    return Advice("batch_groups", {}, roles, reasons=reasons,
                  design_checks=("independent", "assumptions"))

def _compare_adjusted(outcome, group, covariates, labels, out_level) -> Advice:
    """Groups compared on adjusted means (ANCOVA): a hypothesis test whose
    assumptions are about the design, not only about the data."""
    count = len(labels)
    if out_level != "scale":
        return Advice(blockers=(("block.adjust_outcome", {"name": outcome,
                                                          "level": f"level.{out_level}"}),))
    if count < 2 or count > 6:
        return Advice(blockers=(("block.group_count_adjusted", {"name": group, "count": count}),))
    facts = ("design.groups_found", {"name": group, "count": count,
                                     "labels": ", ".join(labels[:8])})
    unadjusted = (Alternative("groups", {"method": "welch"}, "alt.unadjusted") if count == 2 else
                  Alternative("omnibus", {"method": "welch"}, "alt.unadjusted"))
    return Advice(
        "ancova", {"mode": "ancova"},
        {"outcome": outcome, "group": group, "covariates": list(covariates)},
        reasons=(facts, ("why.ancova_adjusted", {"outcome": outcome, "group": group,
                                                "covariates": ", ".join(covariates)}),
                 ("why.ancova_design", {})),
        alternatives=(Alternative("ancova", {"mode": "interaction"}, "alt.interaction"),
                      unadjusted),
        design_checks=("model",))


def _change(sel, session, level):
    items = list(sel["measures"])
    levels = {level(n) for n in items}
    if len(levels) != 1:
        return Advice(blockers=(("block.mixed_levels", {}),))
    common = levels.pop()
    if common == "nominal":
        return Advice(blockers=(("block.nominal_repeated", {}),))
    if len(items) == 2:
        roles = {"before": items[0], "after": items[1]}
        if common == "ordinal":
            return Advice("paired", {"method": "wilcoxon"}, roles,
                          reasons=(("why.paired", {}), ("why.wilcoxon", {})),
                          design_checks=("same_people", "assumptions"))
        return Advice("paired", {"method": "paired_t"}, roles,
                      reasons=(("why.paired", {}), ("why.paired_t", {})),
                      alternatives=(Alternative("paired", {"method": "wilcoxon"}, "alt.wilcoxon"),),
                      design_checks=("same_people", "assumptions"))
    roles = {"measures": items}
    if common == "ordinal":
        return Advice("repeated", {"method": "friedman"}, roles,
                      reasons=(("why.repeated", {"count": len(items)}), ("why.friedman", {})),
                      design_checks=("same_people", "assumptions"))
    return Advice("repeated", {"method": "rm_anova"}, roles,
                  reasons=(("why.repeated", {"count": len(items)}), ("why.rm_anova", {})),
                  alternatives=(Alternative("repeated", {"method": "friedman"}, "alt.friedman"),),
                  design_checks=("same_people", "assumptions"))


def _relate(sel, session, level):
    x, ys = sel["x"], _names(sel["y"])
    if len(ys) > 1:
        return _relate_many(x, ys, level)
    y = ys[0]
    lx, ly = level(x), level(y)
    if lx == "nominal" or ly == "nominal":
        if lx in CATEGORICAL and ly in CATEGORICAL:
            return Advice("chi", {}, {"a": x, "b": y},
                          reasons=(("why.categories", {}),), design_checks=("categorical",))
        return Advice(blockers=(("block.nominal_relation", {}),),
                      alternatives=(Alternative("groups", {}, "alt.compare_instead"),))
    if "ordinal" in (lx, ly):
        return Advice("correlation", {"method": "spearman"}, {"x": x, "y": y},
                      reasons=(("why.spearman", {}),))
    return Advice("correlation", {"method": "pearson"}, {"x": x, "y": y},
                  reasons=(("why.pearson", {}),),
                  alternatives=(Alternative("correlation", {"method": "spearman"}, "alt.spearman"),),
                  design_checks=("pearson",))



def _relate_many(x, ys, level) -> Advice:
    """One variable with several (Stage 36): the same rules as for one pair,
    applied to the whole family; nominal variables need another question."""
    levels = [level(x), *[level(y) for y in ys]]
    if "nominal" in levels:
        return Advice(blockers=(("block.nominal_relation", {}),),
                      alternatives=(Alternative("groups", {}, "alt.compare_instead"),))
    roles = {"x": x, "ys": list(ys)}
    facts = ("why.batch_family", {"count": len(ys)})
    if "ordinal" in levels:
        return Advice("batch_correlation", {"method": "spearman"}, roles,
                      reasons=(facts, ("why.spearman", {})),
                      alternatives=(Alternative("batch_correlation", {"method": "kendall"},
                                                "alt.kendall"),))
    return Advice("batch_correlation", {"method": "pearson"}, roles,
                  reasons=(facts, ("why.pearson", {})),
                  alternatives=(Alternative("batch_correlation", {"method": "spearman"},
                                            "alt.spearman"),
                                Alternative("batch_correlation", {"method": "kendall"},
                                            "alt.kendall")),
                  design_checks=("pearson",))

def _associate(sel, session, level):
    return Advice("chi", {}, {"a": sel["a"], "b": sel["b"]},
                  reasons=(("why.categories", {}),), design_checks=("categorical",))


def _predict(sel, session, level):
    outcome = sel["outcome"]
    predictors = list(sel["predictors"])
    info = session.variables[outcome]
    quantitative = [p for p in predictors if level(p) == "scale"]
    categorical = [p for p in predictors if level(p) in CATEGORICAL]
    if info.binary and level(outcome) == "nominal":
        if categorical:
            return Advice(blockers=(("block.categorical_predictors", {}),))
        return Advice("logistic", {}, {"outcome": outcome, "predictors": quantitative},
                      reasons=(("why.logistic", {"outcome": outcome}),),
                      design_checks=("model",))
    if level(outcome) != "scale":
        return Advice(blockers=(("block.outcome_scale", {"name": outcome}),))
    if len(categorical) == 1 and quantitative:
        group = categorical[0]
        count = len(session.group_labels(group))
        if 2 <= count <= 6:
            return Advice("ancova", {"mode": "ancova"},
                          {"outcome": outcome, "group": group, "covariates": quantitative},
                          reasons=(("why.ancova", {"group": group}),),
                          alternatives=(Alternative("ancova", {"mode": "interaction"},
                                                    "alt.interaction"),),
                          design_checks=("model",))
    if categorical:
        return Advice(blockers=(("block.categorical_predictors", {}),))
    return Advice("regression", {"hc3": "no"}, {"outcome": outcome, "predictors": quantitative},
                  reasons=(("why.regression", {"outcome": outcome}),),
                  alternatives=(Alternative("regression", {"hc3": "yes"}, "alt.hc3"),),
                  design_checks=("model",))


def _scale(sel, session, level):
    items = list(sel["items"])
    if len(items) <= 12:
        return Advice("omega", {"ci": "0"}, {"items": items},
                      reasons=(("why.omega", {}),),
                      alternatives=(Alternative("alpha", {}, "alt.alpha"),),
                      design_checks=("construct",))
    # The validated one-factor omega accepts 3–12 items.
    return Advice("alpha", {}, {"items": items},
                  reasons=(("why.alpha_many", {"count": len(items)}),),
                  design_checks=("construct",))


def _structure(sel, session, level):
    return Advice("factor", {"method": "efa", "count": "1", "rotation": "none"},
                  {"items": list(sel["items"])},
                  reasons=(("why.efa", {}),),
                  alternatives=(Alternative("factor", {"method": "pca"}, "alt.pca"),),
                  design_checks=("design",))


def _describe(sel, session, level):
    variable = sel["variable"]
    group = sel.get("group") or None
    if level(variable) == "scale" and group:
        return Advice("explore", {}, {"variable": variable, "group": group},
                      reasons=(("why.explore", {}),),
                      alternatives=(Alternative("descriptive", {}, "alt.descriptive"),))
    return Advice("descriptive", {}, {"variable": variable},
                  reasons=(("why.describe", {"level": level(variable)}),),
                  alternatives=(() if level(variable) != "scale" else
                                (Alternative("explore", {}, "alt.explore"),)))
