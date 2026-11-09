"""One grouping variable, several outcomes, one run (Stage 36, spec §6).

Kruskal–Wallis H for every outcome, as one family of tests (Holm by
default; raw p kept). How each p-value was obtained is stated:

- the tie-corrected H statistic (SciPy ``kruskal``) with its asymptotic
  χ² p-value (df = k − 1);
- a Monte Carlo permutation p-value (group labels permuted, ranks fixed,
  9,999 permutations with a fixed seed; p = (exceedances + 1)/(B + 1)).
  When any group has fewer than five observations the χ² approximation
  is unreliable, and the permutation p is the primary p-value.

Effect sizes, both with their definitions (Tomczak & Tomczak, 2014):

- η²_H = (H − k + 1) / (N − k), truncated at 0 (the estimate the single
  Kruskal–Wallis analysis reports);
- ε²_R = H / (N − 1)  (= H / ((N² − 1)/(N + 1))).

Pairwise Dunn tests with Holm adjustment within each outcome reuse
``posthoc_analysis.dunn_pairs``; pairs involving a group under five carry
a warning.

``check_grouping`` explains problems before anything runs: a grouping
variable with two categories (offer the two-group comparison instead),
more than eight groups, a group too small to rank (fewer than 2), and
small or very unequal groups (warnings, not refusals).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from batch_correlation import _text_only
from multiple_comparisons import adjust as adjust_family
from posthoc_analysis import dunn_pairs
from stat_results import ENGINE_VERSION, Quantity, StructuredResult, Table, _provenance
from variable_rules import looks_like_identifier

DEFAULT_SEED = 36
DEFAULT_PERMUTATIONS = 9999
SMALL_GROUP = 5
MIN_GROUP = 2


@dataclass(frozen=True)
class Problem:
    key: str              # text key in workspace_text
    params: dict
    blocking: bool


@dataclass(frozen=True)
class PairRow:
    first: str
    second: str
    mean_rank_difference: float
    z: float
    p_raw: float
    p_adjusted: float
    warning: str = ""


@dataclass(frozen=True)
class GroupRow:
    outcome: str
    group: str
    labels: tuple[str, ...]
    ns: tuple[int, ...]
    n: int
    n_excluded: int
    status: str = "ok"
    note: str = ""
    statistic: float | None = None           # H (tie-corrected)
    df: int | None = None
    p_asymptotic: float | None = None
    p_permutation: float | None = None
    p_primary: float | None = None
    p_method: str = ""
    p_adjusted: float | None = None
    eta2_h: float | None = None
    epsilon2_r: float | None = None
    medians: tuple[float, ...] = ()
    mean_ranks: tuple[float, ...] = ()
    pairs: tuple[PairRow, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupFamily:
    group: str
    method: str
    rows: tuple[GroupRow, ...]
    adjustment: str
    adjustment_text: str
    family_size: int
    alpha: float
    permutations: int
    seed: int
    warnings: tuple[str, ...]
    provenance: dict = field(default_factory=dict)

    def row(self, outcome: str) -> GroupRow:
        for row in self.rows:
            if row.outcome == outcome:
                return row
        raise KeyError(outcome)

    def table(self) -> Table:
        adjusted_label = {"holm": "p (Holm)", "bh": "p (BH)", "bonferroni": "p (Bonferroni)",
                          "none": "p (unadjusted)"}[self.adjustment]
        rows = []
        for row in self.rows:
            ns = ", ".join(f"{label}: {n}" for label, n in zip(row.labels, row.ns))
            if row.status != "ok":
                rows.append((row.outcome, ns, "Calculation failed", "", "", "", "", ""))
                continue
            rows.append((row.outcome, ns, f"{row.statistic:.2f}", str(row.df),
                         _p(row.p_primary), _p(row.p_adjusted), f"{row.eta2_h:.3f}",
                         f"{row.epsilon2_r:.3f}"))
        return Table(f"Kruskal–Wallis: {len(self.rows)} outcomes by {self.group}",
                     ("Outcome", "n per group", "H", "df", "p", adjusted_label, "η²_H", "ε²_R"),
                     tuple(rows))

    def structured(self) -> StructuredResult:
        quantities = []
        for row in self.rows:
            key, label = f"H:{row.outcome}", f"Kruskal–Wallis H: {row.outcome} by {row.group}"
            if row.status != "ok":
                quantities.append(Quantity.missing(key, label, "failed", row.note))
                continue
            quantities.append(Quantity(key, label, row.statistic, p=row.p_primary,
                                       p_method=row.p_method,
                                       note=f"df = {row.df}; adjusted p = {_p(row.p_adjusted)}"))
            quantities.append(Quantity(f"eta2_h:{row.outcome}", f"η²_H: {row.outcome}",
                                       row.eta2_h, note="(H − k + 1)/(N − k), truncated at 0"))
            quantities.append(Quantity(f"epsilon2_r:{row.outcome}", f"ε²_R: {row.outcome}",
                                       row.epsilon2_r, note="H/(N − 1)"))
        return StructuredResult(
            "batch_kruskal", self.table().title,
            {"groups": {row.outcome: dict(zip(row.labels, row.ns)) for row in self.rows}},
            {"variables": [self.group, *[row.outcome for row in self.rows]],
             "options": {"method": self.method, "adjustment": self.adjustment,
                         "permutations": self.permutations, "seed": self.seed,
                         "alpha": self.alpha}},
            tuple(quantities), warnings=self.warnings, tables=(self.table(),),
            provenance=self.provenance)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "GroupFamily":
        rows = []
        for row in data["rows"]:
            pairs = tuple(PairRow(**pair) for pair in row.get("pairs", ()))
            rows.append(GroupRow(**{**row, "labels": tuple(row["labels"]), "ns": tuple(row["ns"]),
                                    "medians": tuple(row.get("medians", ())),
                                    "mean_ranks": tuple(row.get("mean_ranks", ())),
                                    "pairs": pairs, "warnings": tuple(row.get("warnings", ()))}))
        return cls(**{**data, "rows": tuple(rows), "warnings": tuple(data.get("warnings", ())),
                      "provenance": dict(data.get("provenance", {}))})


def _p(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return "< .001" if value < 0.001 else f"{value:.3f}".replace("0.", ".", 1)


def _ordered_labels(values: pd.Series) -> list:
    unique = list(pd.unique(values))
    try:
        return sorted(unique, key=float)
    except (TypeError, ValueError):
        return sorted(unique, key=str)


def group_sizes(df: pd.DataFrame, group: str, outcome: str | None = None) -> dict[str, int]:
    """Complete-case group sizes, labels in a natural order."""
    frame = df[[group] + ([outcome] if outcome else [])].copy()
    if outcome:
        frame[outcome] = pd.to_numeric(frame[outcome], errors="coerce")
    frame = frame.dropna()
    labels = _ordered_labels(frame[group])
    counts = frame[group].value_counts()
    return {str(label): int(counts[label]) for label in labels}


def check_grouping(df: pd.DataFrame, group: str, outcomes: list[str] | None = None,
                   method: str = "kruskal") -> list[Problem]:
    """What to explain BEFORE running a 3–8 group comparison."""
    if group not in df.columns:
        return [Problem("block.unknown_variable", {"name": group}, True)]
    sizes = group_sizes(df, group)
    count = len(sizes)
    problems: list[Problem] = []
    if count == 2:
        problems.append(Problem("block.two_groups_for_omnibus",
                                {"name": group, "count": count,
                                 "labels": ", ".join(sizes)}, True))
        return problems
    if count < 2 or count > 8:
        problems.append(Problem("block.group_count", {"name": group, "count": count}, True))
        return problems
    minimum = MIN_GROUP if method == "kruskal" else SMALL_GROUP
    for outcome in outcomes or [None]:
        per_outcome = group_sizes(df, group, outcome) if outcome else sizes
        tiny = {label: n for label, n in per_outcome.items() if n < minimum}
        if tiny:
            problems.append(Problem("block.group_too_small", {
                "name": group, "outcome": outcome or "", "minimum": minimum,
                "groups": ", ".join(f"{label} ({n})" for label, n in tiny.items())}, True))
    small = {label: n for label, n in sizes.items() if n < SMALL_GROUP}
    if small and method == "kruskal":
        problems.append(Problem("warn.small_groups_permutation", {
            "name": group, "groups": ", ".join(f"{label} ({n})" for label, n in small.items())},
            False))
    elif small:
        problems.append(Problem("block.small_groups_parametric", {
            "name": group, "groups": ", ".join(f"{label} ({n})" for label, n in small.items())},
            True))
    if sizes and max(sizes.values()) >= 4 * max(1, min(sizes.values())):
        problems.append(Problem("warn.unequal_groups", {
            "name": group, "sizes": ", ".join(f"{label}: {n}" for label, n in sizes.items())},
            False))
    return problems


def _h_statistic(rank_sums: np.ndarray, ns: np.ndarray, n: int, tie: float) -> np.ndarray:
    h = 12.0 / (n * (n + 1)) * np.sum(rank_sums ** 2 / ns, axis=-1) - 3 * (n + 1)
    return h / tie


def kruskal_permutation_p(samples: list[np.ndarray], *, permutations: int, seed: int,
                          observed: float) -> float:
    """Monte Carlo permutation p of the tie-corrected H (labels permuted)."""
    values = np.concatenate(samples)
    n = values.size
    ranks = stats.rankdata(values)
    _, counts = np.unique(values, return_counts=True)
    tie = 1.0 - np.sum(counts.astype(float) ** 3 - counts) / (n ** 3 - n)
    if tie <= 0:
        raise ValueError("No rank variation.")
    ns = np.array([len(s) for s in samples], dtype=float)
    labels = np.repeat(np.arange(len(samples)), ns.astype(int))
    rng = np.random.default_rng(seed)
    exceed = 0
    tolerance = 1e-9 * max(1.0, abs(observed))
    chunk = 2000
    done = 0
    while done < permutations:
        size = min(chunk, permutations - done)
        shuffled = rng.permuted(np.broadcast_to(labels, (size, n)), axis=1)
        sums = np.stack([(shuffled == g) @ ranks for g in range(len(samples))], axis=1)
        h = _h_statistic(sums, ns, n, tie)
        exceed += int(np.count_nonzero(h >= observed - tolerance))
        done += size
    return (exceed + 1) / (permutations + 1)


def compare_many(df: pd.DataFrame, group: str, outcomes: list[str], *, method: str = "kruskal",
                 adjust: str = "holm", alpha: float = 0.05,
                 permutations: int = DEFAULT_PERMUTATIONS, seed: int = DEFAULT_SEED,
                 posthoc: bool = True) -> GroupFamily:
    """Kruskal–Wallis for each outcome by ``group``, as one family."""
    if method != "kruskal":
        raise ValueError("The batch group comparison uses Kruskal–Wallis.")
    if permutations < 999:
        raise ValueError("Use at least 999 permutations.")
    outcomes = list(outcomes)
    if not outcomes or len(set(outcomes)) != len(outcomes) or group in outcomes:
        raise ValueError("Choose each outcome once, and not the grouping variable.")
    for name in [group, *outcomes]:
        if name not in df.columns:
            raise ValueError(f"Unknown variable: {name}")
        if name != group and _text_only(df[name]):
            raise ValueError(f"{name} holds text, not numbers (an identifier?); it cannot be "
                             "analysed as an outcome.")
        if looks_like_identifier(name):
            raise ValueError(f"{name} is an identifier, not a research variable.")
    blocking = [p for p in check_grouping(df, group, None, method) if p.blocking]
    if blocking:
        raise ValueError(blocking[0].key)
    rows = [_outcome_row(df, group, outcome, permutations, seed, posthoc) for outcome in outcomes]
    adjustment = adjust_family([row.p_primary if row.status == "ok" else None for row in rows],
                               adjust)
    rows = [GroupRow(**{**asdict(row), "pairs": row.pairs, "p_adjusted": value})
            for row, value in zip(rows, adjustment.adjusted)]
    warnings = [
        "Kruskal–Wallis compares rank distributions; reading it as a comparison of medians "
        "needs similarly shaped distributions.",
        f"The outcomes form one family ({adjustment.description}; {adjustment.family_size} "
        "tests); raw p-values are kept.",
        "Group differences do not establish causation; a non-significant result does not show "
        "that the groups are equal.",
    ]
    sizes = group_sizes(df, group)
    if any(n < SMALL_GROUP for n in sizes.values()):
        warnings.append("Small groups: the permutation p-value is primary and pairwise results "
                        "involving them are exploratory.")
    return GroupFamily(group, method, tuple(rows), adjust, adjustment.description,
                       adjustment.family_size, alpha, permutations, seed, tuple(warnings),
                       _provenance(seed=seed, permutations=permutations, engine=ENGINE_VERSION))


def _outcome_row(df, group, outcome, permutations, seed, posthoc) -> GroupRow:
    frame = df[[group, outcome]].copy()
    frame[outcome] = pd.to_numeric(frame[outcome], errors="coerce")
    complete = frame.dropna()
    excluded = int(len(frame) - len(complete))
    labels = _ordered_labels(complete[group])
    samples = [complete.loc[complete[group] == label, outcome].to_numpy(dtype=float)
               for label in labels]
    ns = tuple(int(s.size) for s in samples)
    text_labels = tuple(str(label) for label in labels)
    warnings: list[str] = []
    if excluded:
        warnings.append(f"{excluded} record(s) without a group or value were left out.")
    try:
        if not 3 <= len(samples) <= 8:
            raise ValueError(f"{len(samples)} groups with values; Kruskal–Wallis here compares 3–8.")
        if min(ns) < MIN_GROUP:
            raise ValueError("Every group needs at least two values.")
        values = np.concatenate(samples)
        if np.unique(values).size < 2:
            raise ValueError("The outcome has no variation.")
        result = stats.kruskal(*samples)
        h, p_asym = float(result.statistic), float(result.pvalue)
        n, k = int(values.size), len(samples)
        p_perm = kruskal_permutation_p(samples, permutations=permutations,
                                       seed=seed, observed=h)
        small = [f"{label} ({size})" for label, size in zip(text_labels, ns) if size < SMALL_GROUP]
        if small:
            primary = p_perm
            method_text = (f"Monte Carlo permutation p ({permutations:,} permutations, seed {seed}); "
                           f"asymptotic χ² p = {_p(p_asym)} is unreliable with groups of "
                           f"{', '.join(small)}")
            warnings.append(f"Groups with fewer than {SMALL_GROUP} values: {', '.join(small)}. "
                            "The χ² approximation of H is unreliable; the permutation p is used.")
        else:
            primary = p_asym
            method_text = (f"asymptotic χ² p (df = {k - 1}), tie-corrected H; "
                           f"permutation p = {_p(p_perm)}")
        if max(ns) >= 4 * min(ns):
            warnings.append("Very unequal group sizes: the test is dominated by the largest group.")
        ranks = stats.rankdata(values)
        mean_ranks, start = [], 0
        for size in ns:
            mean_ranks.append(float(ranks[start:start + size].mean()))
            start += size
        pairs: tuple[PairRow, ...] = ()
        if posthoc:
            pairs = tuple(
                PairRow(pair.first, pair.second, pair.estimate, pair.statistic, pair.p_raw,
                        pair.p_adjusted,
                        "a group with fewer than 5 values: exploratory" if (
                            ns[text_labels.index(pair.first)] < SMALL_GROUP
                            or ns[text_labels.index(pair.second)] < SMALL_GROUP) else "")
                for pair in dunn_pairs(samples, list(text_labels)))
        return GroupRow(
            outcome, group, text_labels, ns, n, excluded, statistic=h, df=k - 1,
            p_asymptotic=p_asym, p_permutation=p_perm, p_primary=primary,
            p_method=method_text, eta2_h=max(0.0, (h - k + 1) / (n - k)),
            epsilon2_r=h / (n - 1), medians=tuple(float(np.median(s)) for s in samples),
            mean_ranks=tuple(mean_ranks), pairs=pairs, warnings=tuple(warnings))
    except ValueError as error:
        return GroupRow(outcome, group, text_labels, ns, int(sum(ns)), excluded,
                        status="failed", note=str(error), warnings=tuple(warnings))
