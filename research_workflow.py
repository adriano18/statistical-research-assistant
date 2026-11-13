"""Stage 37.0a: the hypothesis and research workflow (no Flet imports).

Pure functions over plain facts (docs/STAGE37_DESIGN.md §7):

* the question types and the drafts of H1 and H0 (text keys; the EN/LV/RU
  texts are in ``workspace_text``);
* :func:`task_steps`: the eight step statuses of a research task;
* :func:`hypothesis_checks`: the deterministic checks of a hypothesis against
  the analyses that test it, and :func:`fingerprint`, which binds an
  acknowledgement to the facts it was given for;
* :func:`designation_history`: a hypothesis's designation through the plan
  versions;
* :func:`next_action`: the one next step of a project.

The adapters at the end (``task_facts``, ``hypothesis_views``,
``project_facts``) read a ``ResearchSession`` and an open project; everything
above them takes plain data and is tested on its own.

Nothing here computes a statistic, compares a p-value with α or says that a
hypothesis is supported. A check compares what the plan says with what was
done, never blocks Run or an export, and decides nothing for the researcher:
it is resolved by the researcher's own record (an acknowledgement, a
deviation or a justification, each with a reason) or by changing the
analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

QUESTION_TYPES = ("compare", "change", "relate", "associate", "predict", "scale", "structure",
                  "describe")
# Question types whose hypotheses have an H0 and a direction (scale, structure
# and describe questions state expectations, the measurement layer of 37.1).
TESTABLE = ("compare", "change", "relate", "associate", "predict")
DIRECTIONS = ("two-sided", "greater", "less")
DESIGNATIONS = ("primary", "secondary", "exploratory")
STEP_KEYS = ("hypothesis", "variables", "design", "method", "result", "checks",
             "interpretation", "report")

# Every method of this version reports two-sided p-values only (no method has
# a sidedness option). Tests of three or more groups or occasions, and a
# chi-square test beyond 2 × 2, have no direction at all.
OMNIBUS_METHODS = ("omnibus", "repeated")
GROUP_METHODS = ("batch_groups", "chi")
FAMILY_METHODS = ("batch_correlation", "batch_groups")
CORRELATION_METHODS = ("batch_correlation", "correlation")
ENGINE_ALPHA = 0.05

CHECK_KEYS = ("H-NO-TASK", "H-DIR-TWOSIDED", "H-DIR-OMNIBUS", "H-FAMILY-UNCORRECTED", "H-ALPHA",
              "H-ASSUMPTIONS-OPEN", "H-RESULT-STALE", "H-ADDED-AFTER", "H-DESIGNATION-CHANGED",
              "H-METHOD-DIFFERS", "H-VARIABLES-DIFFER", "H-SPEC-CHANGED", "H-LINKED-LATE",
              "H-DIR-SIGN", "H-FAMILY-SPLIT")
# How a warning is resolved by a record of the researcher (kind of record).
ACKNOWLEDGE = ("H-DIR-TWOSIDED", "H-DIR-OMNIBUS", "H-FAMILY-UNCORRECTED", "H-FAMILY-SPLIT",
               "H-ALPHA")
DEVIATION = {"H-METHOD-DIFFERS": "method", "H-VARIABLES-DIFFER": "variables",
             "H-SPEC-CHANGED": "method"}
JUSTIFY = ("H-ADDED-AFTER", "H-DESIGNATION-CHANGED")
RECORD_KIND = {**{key: "acknowledgement" for key in ACKNOWLEDGE},
               **{key: "deviation" for key in DEVIATION},
               **{key: "justification" for key in JUSTIFY}}


# =============================================================== drafts
def draft_keys(question_type: str) -> tuple[str, str | None]:
    """(text key of the hint for H1, text key of the drafted H0 or None).

    H1 is never prefilled: its draft is a hint the researcher writes over,
    so a template can never be saved as a hypothesis. H0 is a complete,
    generic statement and is offered as text to keep or edit."""
    if question_type in TESTABLE:
        return f"hyp.draft.h1.{question_type}", f"hyp.draft.h0.{question_type}"
    return "hyp.draft.h1.other", None


# ================================================================ steps
@dataclass(frozen=True)
class Step:
    key: str        # one of STEP_KEYS
    state: str      # "done" | "current" | "todo" | "attention" | "skipped"


@dataclass(frozen=True)
class TaskFacts:
    """What the eight steps of a research task are derived from."""

    linked: bool = False               # the task tests a hypothesis
    hypothesis_in_plan: bool = True    # ... that is in the current plan
    variables_filled: bool = False     # every required role of the goal is filled
    variables_missing: bool = False    # a chosen variable is no longer in the dataset
    design_ready: bool = False         # no blocker; required confirmations hold (K1)
    method_chosen: bool = False        # a method is recommended or chosen
    result: str = "none"               # "none" | "current" | "stale"
    assumptions_total: int = 0
    assumptions_reviewed: int = 0
    note: bool = False
    note_skipped: bool = False
    report: str = "none"               # "none" | "current" | "older"


def task_steps(facts: TaskFacts) -> tuple[Step, ...]:
    """The eight steps of a task; the first one still to do is *current*."""
    f = facts
    states = {
        "hypothesis": ("done" if f.linked and f.hypothesis_in_plan else
                       "attention" if f.linked else "skipped"),
        "variables": ("attention" if f.variables_missing else
                      "done" if f.variables_filled else "todo"),
        "design": "done" if f.design_ready else "todo",
        "method": "done" if f.method_chosen else "todo",
        "result": ("attention" if f.result == "stale" else
                   "done" if f.result == "current" else "todo"),
        "checks": ("todo" if f.result == "none" else
                   "done" if f.assumptions_reviewed >= f.assumptions_total else "attention"),
        "interpretation": ("todo" if f.result == "none" else "done" if f.note else
                           "skipped" if f.note_skipped else "todo"),
        "report": ("done" if f.report == "current" else
                   "attention" if f.report == "older" else "todo"),
    }
    current = next((key for key in STEP_KEYS if states[key] == "todo"), None)
    return tuple(Step(key, "current" if key == current else states[key]) for key in STEP_KEYS)


def steps_complete(steps) -> int:
    """How many steps are finished: done, or skipped by choice."""
    return sum(1 for step in steps if step.state in ("done", "skipped"))


def next_step(steps) -> str | None:
    """The key of the step to do next (current or needing attention)."""
    return next((step.key for step in steps if step.state in ("current", "attention")), None)


# =============================================================== records
def active_records(records) -> tuple[dict, ...]:
    """The records that hold: withdrawals and what they withdrew drop out."""
    records = tuple(records or ())
    withdrawn = {r.get("supersedes") for r in records if r.get("kind") == "withdrawal"}
    return tuple(r for r in records if r.get("kind") != "withdrawal"
                 and r.get("id") not in withdrawn)


def fingerprint(check: str, hypothesis_id: str, task_id: str | None, facts: dict) -> str:
    """SHA-256 of the facts a check evaluated: an acknowledgement holds only
    while these facts are the same (it reopens when they change)."""
    payload = json.dumps({"check": check, "hypothesis": hypothesis_id or "",
                          "task": task_id or "", "facts": facts},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ================================================================ checks
@dataclass(frozen=True)
class ResultFacts:
    """One result of an analysis, as far as the checks need it."""

    key: str                           # the session's entry id, as text
    method: str
    options: dict = field(default_factory=dict)
    names: tuple[str, ...] = ()        # every variable the result used
    alpha: float = ENGINE_ALPHA
    stale: bool = False
    assumptions: tuple[str, ...] = ()
    reviewed: frozenset = frozenset()
    estimates: tuple[tuple[str, float], ...] = ()   # (label, signed coefficient)
    snapshot: dict | None = None       # provenance["hypothesis"]: what it was calculated for
    created: str = ""                  # ISO time, for the order of results
    in_report: bool = False
    note: str = ""


@dataclass(frozen=True)
class AnalysisFacts:
    """One research task that tests the hypothesis."""

    task_id: str
    title: str = ""
    goal: str = ""
    method: str = ""                   # the method key it runs ("" before one is chosen)
    options: dict = field(default_factory=dict)
    selection: dict = field(default_factory=dict)   # role → names, as the goal's roles
    family_size: int = 1               # tests in one batch family
    groups: int = 0                    # groups or categories of a group method (0: unknown)
    results: tuple[ResultFacts, ...] = ()           # oldest first


@dataclass(frozen=True)
class HypothesisFacts:
    id: str
    number: int = 1                    # H1 = 1
    text: str = ""
    direction: str = "two-sided"
    priority: str = "primary"
    alpha: float = ENGINE_ALPHA
    family: str = ""
    method_key: str = ""
    method_options: dict = field(default_factory=dict)
    roles: dict = field(default_factory=dict)
    standing: str = "new"              # confirmatory | added_after_results | exploratory | new
    runs_before: int = 0
    question_type: str = ""


@dataclass(frozen=True)
class Check:
    key: str                           # one of CHECK_KEYS
    severity: str                      # "warning" | "info" | "passed"
    state: str                         # "open" | "acknowledged" | "recorded" | "info" | "passed"
    text: str                          # text key
    params: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    fingerprint: str = ""
    resolution: str = ""               # acknowledge | deviation | justify | review | recalculate | create_task | ""
    task_id: str | None = None
    record_id: str | None = None       # the record that resolves it

    @property
    def needs_decision(self) -> bool:
        """A warning nobody has recorded a decision about."""
        return self.severity == "warning" and self.state == "open"


def _names(value) -> list[str]:
    if not value:
        return []
    return [str(v) for v in value] if isinstance(value, (list, tuple, set)) else [str(value)]


def _roles(selection: dict) -> dict:
    """role → sorted names, without empty roles (JSON-friendly, canonical)."""
    return {role: sorted(_names(value)) for role, value in sorted((selection or {}).items())
            if _names(value)}


def _spec(result: ResultFacts) -> dict:
    return {"method": result.method,
            "options": {k: str(v) for k, v in sorted((result.options or {}).items())},
            "variables": sorted(result.names)}


def _is_omnibus(analysis: AnalysisFacts) -> bool:
    if analysis.method in OMNIBUS_METHODS:
        return True
    return analysis.method in GROUP_METHODS and analysis.groups > 2


def _resolved(records, kind: str, check: str, hypothesis_id: str, task_id: str | None,
              print_: str) -> dict | None:
    for record in records:
        if (record.get("kind") == kind and record.get("check_key") == check
                and (record.get("hypothesis_id") or "") == hypothesis_id
                and (record.get("task_id") or None) == (task_id or None)
                and record.get("fingerprint") == print_):
            return record
    return None


def _check(key, severity, text, h, *, task_id=None, facts=None, params=None, resolution="",
           records=()) -> Check:
    """A check whose state comes from the researcher's records, if any."""
    facts = dict(facts or {})
    print_ = fingerprint(key, h.id, task_id, facts)
    state = {"warning": "open", "info": "info", "passed": "passed"}[severity]
    record = None
    kind = RECORD_KIND.get(key)
    if severity == "warning" and kind:
        record = _resolved(records, kind, key, h.id, task_id, print_)
        if record is not None:
            state = "acknowledged" if kind == "acknowledgement" else "recorded"
    return Check(key, severity, state, text, dict(params or {}), facts, print_, resolution,
                 task_id, record.get("id") if record else None)


def hypothesis_checks(h: HypothesisFacts, analyses=(), records=(), *, peers=(),
                      history=()) -> tuple[Check, ...]:
    """Every check of one hypothesis, deterministic and in the order of CHECK_KEYS.

    ``analyses``: the tasks that test it. ``records``: its protocol records
    (withdrawn ones are ignored). ``peers``: ``(hypothesis number,
    AnalysisFacts)`` of other hypotheses with the same family label.
    ``history``: :func:`designation_history` of the hypothesis."""
    records = active_records(records)
    analyses = tuple(analyses)
    one_sided = h.direction in ("greater", "less")
    out: list[Check] = []

    def add(*args, **kwargs):
        out.append(_check(*args, records=records, **kwargs))

    if not analyses:
        add("H-NO-TASK", "info" if h.priority == "exploratory" else "warning", "check.no_task", h,
            params={"h": h.number}, resolution="create_task")
    for a in analyses:
        tid = a.task_id
        latest = a.results[-1] if a.results else None
        if one_sided and a.method:
            if _is_omnibus(a):
                add("H-DIR-OMNIBUS", "warning", "check.dir_omnibus", h, task_id=tid,
                    facts={"direction": h.direction, "method": a.method, "groups": a.groups,
                           "test": str(a.options.get("method", ""))},
                    params={"h": h.number, "direction": h.direction, "method": a.method,
                            "test": str(a.options.get("method", "")), "groups": a.groups},
                    resolution="acknowledge")
            else:
                add("H-DIR-TWOSIDED", "warning", "check.dir_twosided", h, task_id=tid,
                    facts={"direction": h.direction, "method": a.method,
                           "test": str(a.options.get("method", ""))},
                    params={"h": h.number, "direction": h.direction, "method": a.method,
                            "test": str(a.options.get("method", ""))}, resolution="acknowledge")
        if a.method in FAMILY_METHODS and a.family_size >= 2:
            adjust = str(a.options.get("adjust", "holm"))
            facts = {"k": a.family_size, "adjust": adjust}
            if adjust == "none":
                add("H-FAMILY-UNCORRECTED", "warning", "check.family_uncorrected", h, task_id=tid,
                    facts=facts, params={"k": a.family_size}, resolution="acknowledge")
            else:
                add("H-FAMILY-UNCORRECTED", "passed", "check.family_ok", h, task_id=tid,
                    facts=facts, params={"k": a.family_size, "adjust": adjust})
        if a.method:
            alpha = latest.alpha if latest is not None else ENGINE_ALPHA
            if abs(float(h.alpha) - float(alpha)) > 1e-9:
                add("H-ALPHA", "warning", "check.alpha", h, task_id=tid,
                    facts={"plan": float(h.alpha), "analysis": float(alpha)},
                    params={"plan": h.alpha, "analysis": alpha}, resolution="acknowledge")
        if latest is not None:
            open_ = [x for x in latest.assumptions if x not in latest.reviewed]
            if open_:
                add("H-ASSUMPTIONS-OPEN", "warning", "check.assumptions_open", h, task_id=tid,
                    facts={"open": sorted(open_)}, params={"count": len(open_)},
                    resolution="review")
            else:
                add("H-ASSUMPTIONS-OPEN", "passed", "check.assumptions_ok", h, task_id=tid)
            if latest.stale:
                add("H-RESULT-STALE", "warning", "check.result_stale", h, task_id=tid,
                    resolution="recalculate")
            else:
                add("H-RESULT-STALE", "passed", "check.result_ok", h, task_id=tid)
    if h.standing == "added_after_results":
        facts = {"runs_before": h.runs_before}
        if h.priority == "exploratory":
            add("H-ADDED-AFTER", "info", "check.added_after_exploratory", h, facts=facts,
                params={"runs": h.runs_before})
        else:
            add("H-ADDED-AFTER", "warning", "check.added_after", h, facts=facts,
                params={"runs": h.runs_before}, resolution="justify")
    for entry in history:
        if not entry.get("changed") or not entry.get("runs_before"):
            continue
        facts = {"version": entry["version"], "from": entry["previous"], "to": entry["priority"]}
        params = {"from": entry["previous"], "to": entry["priority"],
                  "runs": entry["runs_before"], "version": entry["version"]}
        record = entry.get("record")
        if record is not None:
            # Recorded when the plan was saved: the reason is part of the history.
            out.append(Check("H-DESIGNATION-CHANGED", "warning", "recorded",
                             "check.designation_changed",
                             {**params, "reason": record.get("reason", "")}, facts,
                             fingerprint("H-DESIGNATION-CHANGED", h.id, None, facts), "", None,
                             record.get("id")))
        else:
            add("H-DESIGNATION-CHANGED", "warning", "check.designation_unexplained", h,
                facts=facts, params=params, resolution="justify")
    for a in analyses:
        tid = a.task_id
        if h.method_key and a.method:
            planned = {"method": h.method_key,
                       "options": {k: str(v) for k, v in sorted(h.method_options.items())}}
            actual = {"method": a.method,
                      "options": {k: str(a.options.get(k, "")) for k in sorted(h.method_options)}}
            if planned != actual:
                add("H-METHOD-DIFFERS", "warning", "check.method_differs", h, task_id=tid,
                    facts={"planned": planned, "actual": actual},
                    params={"planned": planned, "actual": actual}, resolution="deviation")
        if h.roles:
            planned, actual = _roles(h.roles), _roles(a.selection)
            differs = {role: names for role, names in planned.items()
                       if set(names) != set(actual.get(role, []))}
            if differs:
                missing = sorted({n for r, names in planned.items()
                                  for n in names if n not in actual.get(r, [])})
                extra = sorted({n for r, names in actual.items() if r in planned
                                for n in names if n not in planned[r]})
                add("H-VARIABLES-DIFFER", "warning", "check.variables_differ", h, task_id=tid,
                    facts={"planned": planned, "actual": actual},
                    params={"missing": ", ".join(missing) or "—", "extra": ", ".join(extra) or "—"},
                    resolution="deviation")
        mine = [r for r in a.results if (r.snapshot or {}).get("id") == h.id]
        if len(mine) > 1:
            first = _spec(mine[0])
            later = next((_spec(r) for r in mine[1:] if _spec(r) != first), None)
            if later is not None:
                add("H-SPEC-CHANGED", "warning", "check.spec_changed", h, task_id=tid,
                    facts={"first": first, "later": later}, params={"count": len(mine)},
                    resolution="deviation")
        late = [r for r in a.results if (r.snapshot or {}).get("id") != h.id]
        if late:
            add("H-LINKED-LATE", "info", "check.linked_late", h, task_id=tid,
                params={"count": len(late)})
        latest = a.results[-1] if a.results else None
        if one_sided and latest is not None and a.method in CORRELATION_METHODS:
            against = [label for label, value in latest.estimates
                       if (h.direction == "less" and value > 0)
                       or (h.direction == "greater" and value < 0)]
            if against:
                add("H-DIR-SIGN", "info", "check.dir_sign", h, task_id=tid,
                    params={"count": len(against), "total": len(latest.estimates),
                            "names": ", ".join(against), "direction": h.direction})
    family_tasks = [(h.number, a) for a in analyses
                    if a.method in FAMILY_METHODS and a.family_size >= 2]
    family_tasks += [(number, a) for number, a in peers
                     if a.method in FAMILY_METHODS and a.family_size >= 2]
    if len(family_tasks) >= 2:
        label = h.family.strip()
        tasks = sorted([a.task_id, a.family_size] for _, a in family_tasks)
        add("H-FAMILY-SPLIT", "warning", "check.family_split", h,
            facts={"label": label.casefold(), "tasks": tasks},
            params={"total": sum(a.family_size for _, a in family_tasks),
                    "count": len(family_tasks), "label": label or f"H{h.number}"},
            resolution="acknowledge")
    order = {key: index for index, key in enumerate(CHECK_KEYS)}
    return tuple(sorted(out, key=lambda c: order[c.key]))


def open_checks(checks) -> tuple[Check, ...]:
    """Warnings without a recorded decision (assumptions are reviewed, not
    acknowledged, and are counted apart)."""
    return tuple(c for c in checks if c.needs_decision and c.key != "H-ASSUMPTIONS-OPEN")


def method_title(key: str, options: dict | None = None) -> str:
    """The English title of a method, or of its chosen variant, as Analyze
    shows it (``Spearman’s ρ`` for a batch of Spearman correlations)."""
    from workspace_methods import METHODS

    spec = METHODS.get(key)
    if spec is None:
        return key or "—"
    for option in spec.options:
        if option.key == "method":
            value = (options or {}).get("method") or option.default
            return next((label for k, label in option.choices if k == value), spec.title)
    return spec.title


def _adjust_title(value: str) -> str:
    from workspace_methods import METHODS

    for key in FAMILY_METHODS:
        for option in METHODS[key].options:
            if option.key == "adjust":
                for choice, label in option.choices:
                    if choice == value:
                        return label
    return value


def _number(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def check_message(check: Check, language: str = "en") -> str:
    """The text of a check in one language, its values made readable:
    directions and designations by their labels, methods by their titles,
    α as a number."""
    from workspace_text import label, t

    params = check.params
    values = {}
    for name, value in params.items():
        if name == "direction":
            values[name] = t(language, f"plan.direction.{value}")
        elif name in ("from", "to"):
            values[name] = t(language, f"plan.priority.{value}") if value else "—"
        elif name in ("planned", "actual"):
            values[name] = label(language, method_title(value.get("method", ""),
                                                        value.get("options")))
        elif name == "method":
            test = params.get("test")
            values[name] = label(language, method_title(value, {"method": test} if test else {}))
        elif name == "adjust":
            values[name] = label(language, _adjust_title(str(value)))
        elif name in ("plan", "analysis"):
            values[name] = _number(value)
        else:
            values[name] = value
    return t(language, check.text, **values)


# ============================================================ designation
def designation_history(plan_history, records, hypothesis_id: str) -> tuple[dict, ...]:
    """Oldest first: each plan version that holds the hypothesis, with its
    designation, the results that existed, whether the designation changed in
    that version, and the record of the reason when one was given."""
    reasons = {r.get("plan_version"): r for r in active_records(records)
               if r.get("kind") == "designation" and r.get("hypothesis_id") == hypothesis_id}
    out, previous = [], None
    for version in sorted(plan_history or (), key=lambda v: v["version"]):
        hypothesis = next((x for x in version["plan"].get("hypotheses", [])
                           if x.get("id") == hypothesis_id), None)
        if hypothesis is None:
            continue
        priority = hypothesis.get("priority", "primary")
        changed = previous is not None and priority != previous
        out.append({"version": version["version"], "saved_at": version.get("saved_at", ""),
                    "priority": priority, "previous": previous,
                    "runs_before": int(version.get("runs_before", 0)), "changed": changed,
                    "record": reasons.get(version["version"]) if changed else None})
        previous = priority
    return tuple(out)


def hypothesis_snapshot(plan_entry: dict | None, status: dict, hypothesis_id: str | None) -> dict | None:
    """What a result records about the hypothesis it is calculated for: the
    plan version and the designation, direction and α at that moment."""
    if not plan_entry or not hypothesis_id:
        return None
    hypothesis = next((h for h in plan_entry["plan"].get("hypotheses", [])
                       if h.get("id") == hypothesis_id), None)
    if hypothesis is None:
        return None
    return {"id": hypothesis_id, "plan_version": int(plan_entry["version"]),
            "priority": hypothesis.get("priority", "primary"),
            "direction": hypothesis.get("direction", "two-sided"),
            "alpha": float(hypothesis.get("alpha", ENGINE_ALPHA)),
            "standing": (status or {}).get(hypothesis_id, {}).get("standing", ""),
            "question_id": hypothesis.get("question_id", "")}


# ============================================================ next action
@dataclass(frozen=True)
class Action:
    action: str          # what the button does
    label: str           # text key of the button
    data: str            # data key of the button
    target: str = ""     # the hypothesis, task or result it acts on
    primary: bool = True


@dataclass(frozen=True)
class NextAction:
    rule: str            # the rule that applied
    title: str           # text key
    body: str            # text key
    params: dict = field(default_factory=dict)
    actions: tuple[Action, ...] = ()
    why: tuple[tuple[bool, str, dict], ...] = ()


@dataclass(frozen=True)
class HypothesisProgress:
    id: str
    number: int
    priority: str = "primary"
    task_id: str | None = None
    steps: tuple[Step, ...] = ()
    open_checks: tuple[str, ...] = ()   # check keys to decide (not assumptions)
    result_id: int | None = None        # the latest result of its task


@dataclass(frozen=True)
class ProjectFacts:
    has_data: bool = False
    pending_levels: int = 0
    has_results: bool = False
    stale_results: int = 0
    report_count: int = 0
    exported: bool = False              # the report, as composed now, was exported
    questionnaire_draft: bool = False
    plan_started: bool = False          # a question or a hypothesis is written
    question_incomplete: int | None = None     # a started question without kind or text
    question_without_hypothesis: int | None = None  # a typed, testable question with none
    hypothesis_incomplete: int | None = None   # a hypothesis on screen without its text
    plan_dirty: bool = False            # the plan on screen differs from the saved version
    hypotheses: tuple[HypothesisProgress, ...] = ()


def _add_data(f: ProjectFacts, why) -> NextAction:
    actions = [Action("open_data", "data.open", "next-open-data"),
               Action("sample_data", "next.use_sample", "next-sample", primary=False),
               Action("questionnaire", "next.questionnaire", "next-questionnaire", primary=False)]
    if f.questionnaire_draft:
        actions.append(Action("continue_draft", "next.continue_draft", "next-draft",
                              primary=False))
    if not f.plan_started:
        actions.append(Action("write_question", "next.question_first", "next-question",
                              primary=False))
    return NextAction("add_data", "next.add_data", "next.add_data_body", {}, tuple(actions),
                      tuple(why))


def _tail(f: ProjectFacts, why) -> NextAction:
    """After the plan's hypotheses (and for work without a plan): results
    that need attention, the report, its export."""
    if f.stale_results:
        why.append((False, "next.why.results_current", {"count": f.stale_results}))
        return NextAction("stale", "next.stale", "next.stale_body", {"count": f.stale_results},
                          (Action("review_results", "next.review_results", "next-results"),),
                          tuple(why))
    if not f.report_count:
        why.append((False, "next.why.report_started", {}))
        return NextAction("report", "next.report", "next.report_body", {},
                          (Action("review_results", "next.review_results", "next-results"),),
                          tuple(why))
    if not f.exported:
        why.append((False, "next.why.report_exported", {}))
        return NextAction("export", "next.export", "next.export_body",
                          {"count": f.report_count},
                          (Action("open_report", "next.open_report", "next-report"),), tuple(why))
    why.append((True, "next.why.report_exported", {}))
    return NextAction("done", "next.done", "next.done_body", {},
                      (Action("open_report", "next.open_report", "next-report", primary=False),),
                      tuple(why))


def next_action(f: ProjectFacts) -> NextAction:
    """The one next step of the project. The first rule that applies wins.

    Without a plan the order is the Stage 34.5 one (data, levels, an
    analysis, results that need attention, the report, its export), with
    *start with the research question* offered beside the first step. Once a
    question or a hypothesis is written, the plan comes first: the question,
    a hypothesis, saving the plan before any result; then the data, the
    levels, and each saved hypothesis in designation order (primary,
    secondary, then exploratory ones that have an analysis)."""
    why: list[tuple[bool, str, dict]] = []
    if not f.plan_started:
        if not f.has_data:
            return _add_data(f, why)
        why.append((True, "next.why.data", {}))
        if f.pending_levels:
            why.append((False, "next.why.levels", {"count": f.pending_levels}))
            return NextAction("levels", "next.levels", "next.levels_body",
                              {"count": f.pending_levels},
                              (Action("review_levels", "next.review_levels", "next-levels"),),
                              tuple(why))
        why.append((True, "next.why.levels_done", {}))
        if not f.has_results:
            why.append((False, "next.why.results", {}))
            return NextAction("analyze", "next.analyze", "next.analyze_body", {},
                              (Action("choose_analysis", "next.choose_analysis", "next-analyze"),
                               Action("write_question", "next.question_first", "next-question",
                                      primary=False)), tuple(why))
        return _tail(f, why)
    if f.question_incomplete is not None:
        why.append((False, "next.why.question", {"q": f.question_incomplete}))
        return NextAction("N1", "next.question", "next.question_body",
                          {"q": f.question_incomplete}, (), tuple(why))
    if f.question_without_hypothesis is not None:
        why.append((False, "next.why.hypothesis", {"q": f.question_without_hypothesis}))
        return NextAction("N2", "next.add_hypothesis", "next.add_hypothesis_body",
                          {"q": f.question_without_hypothesis},
                          (Action("add_hypothesis", "next.add_hypothesis_button",
                                  "next-add-hypothesis", str(f.question_without_hypothesis)),),
                          tuple(why))
    if f.hypothesis_incomplete is not None:
        why.append((False, "next.why.hypothesis_text", {"h": f.hypothesis_incomplete}))
        return NextAction("N2", "next.write_hypothesis", "next.write_hypothesis_body",
                          {"h": f.hypothesis_incomplete}, (), tuple(why))
    if f.plan_dirty:
        why.append((False, "next.why.plan_saved", {}))
        return NextAction("N3", "next.save_plan", "next.save_plan_body", {},
                          (Action("save_plan", "plan.save", "next-save-plan"),), tuple(why))
    why.append((True, "next.why.plan_saved", {}))
    if not f.has_data:
        return _add_data(f, why)
    why.append((True, "next.why.data", {}))
    if f.pending_levels:
        why.append((False, "next.why.levels", {"count": f.pending_levels}))
        return NextAction("N5", "next.levels", "next.levels_body", {"count": f.pending_levels},
                          (Action("review_levels", "next.review_levels", "next-levels"),),
                          tuple(why))
    why.append((True, "next.why.levels_done", {}))
    rank = {"primary": 0, "secondary": 1, "exploratory": 2}
    for h in sorted(f.hypotheses, key=lambda x: (rank.get(x.priority, 3), x.number)):
        n = {"h": h.number}
        if h.task_id is None:
            if h.priority == "exploratory":
                continue
            why.append((False, "next.why.task", n))
            return NextAction("N6a", "next.create_analysis", "next.create_analysis_body", n,
                              (Action("create_analysis", "next.create_analysis_button",
                                      "next-create-analysis", h.id),), tuple(why))
        why.append((True, "next.why.task", n))
        state = {step.key: step.state for step in h.steps}
        if state.get("result") in ("todo", "current", None):
            why.append((False, "next.why.result", n))
            return NextAction("N6b", "next.run_analysis", "next.run_analysis_body", n,
                              (Action("open_task", "next.open_task", "next-open-task",
                                      h.task_id),), tuple(why))
        if state.get("result") == "attention":
            why.append((False, "next.why.result_current", n))
            return NextAction("N6c", "next.recalculate", "next.recalculate_body", n,
                              (Action("open_task", "next.open_task", "next-open-task",
                                      h.task_id),), tuple(why))
        why.append((True, "next.why.result_current", n))
        if h.open_checks:
            why.append((False, "next.why.checks", {**n, "count": len(h.open_checks)}))
            return NextAction("N6d", "next.decide", "next.decide_body",
                              {**n, "count": len(h.open_checks)},
                              (Action("show_checks", "next.show_checks", "next-show-check",
                                      h.id),), tuple(why))
        why.append((True, "next.why.checks", {**n, "count": 0}))
        if state.get("checks") == "attention":
            why.append((False, "next.why.reviewed", n))
            return NextAction("N6e", "next.review", "next.review_body", n,
                              (Action("review", "next.review_button", "next-review",
                                      str(h.result_id or "")),), tuple(why))
        if state.get("interpretation") in ("todo", "current"):
            why.append((False, "next.why.note", n))
            return NextAction("N6f", "next.note", "next.note_body", n,
                              (Action("write_note", "next.note_button", "next-note",
                                      str(h.result_id or "")),
                               Action("skip_note", "next.skip_note", "next-skip-note",
                                      h.task_id, primary=False)), tuple(why))
        if state.get("report") in ("todo", "current", "attention"):
            why.append((False, "next.why.in_report", n))
            return NextAction("N6g", "next.add_report", "next.add_report_body", n,
                              (Action("add_to_report", "results.add_report", "next-add-report",
                                      str(h.result_id or "")),), tuple(why))
        why.append((True, "next.why.in_report", n))
    if not f.has_results:
        why.append((False, "next.why.results", {}))
        return NextAction("analyze", "next.analyze", "next.analyze_body", {},
                          (Action("choose_analysis", "next.choose_analysis", "next-analyze"),),
                          tuple(why))
    return _tail(f, why)


# ================================================================ adapters
# These read the workspace session and an open project; the functions above
# take only their results.

def result_facts(entry) -> ResultFacts:
    """The facts of one session result (``workspace_state.ResultEntry``)."""
    names = []
    for value in (entry.roles or {}).values():
        for name in _names(value):
            if name not in names:
                names.append(name)
    structured = getattr(entry.run, "result", None)
    alpha = getattr(structured, "alpha", None)
    try:
        assumptions = tuple(entry.run.evidence().assumptions)
    except Exception:          # an unreadable result: nothing to tick
        assumptions = ()
    estimates = ()
    if entry.method == "batch_correlation" and structured is not None:
        estimates = tuple((str(row.y), float(row.estimate))
                          for row in getattr(structured, "rows", ())
                          if getattr(row, "estimate", None) is not None)
    return ResultFacts(
        key=str(entry.id), method=entry.method or "", options=dict(entry.options or {}),
        names=tuple(names), alpha=float(alpha) if isinstance(alpha, (int, float)) else ENGINE_ALPHA,
        stale=bool(entry.stale_reasons), assumptions=assumptions,
        reviewed=frozenset(entry.reviewed), estimates=estimates,
        snapshot=(entry.provenance or {}).get("hypothesis"),
        created=entry.created.isoformat() if entry.created else "", in_report=entry.in_report,
        note=entry.note or "")


def _advice(task, session, selection):
    from workspace_methods import GOAL_ROLES, advise

    if not session.has_data or task.goal not in GOAL_ROLES:
        return None
    try:
        return advise(task.goal, selection, session)
    except Exception:
        return None


def _family_size(goal: str, selection: dict) -> int:
    from workspace_methods import GOAL_ROLES

    for role in GOAL_ROLES.get(goal, ()):
        if role.multiple and not role.optional:
            return len(_names(selection.get(role.key)))
    return 1


def analysis_facts(task, session, *, selection: dict | None = None) -> AnalysisFacts:
    """One task as the checks see it: the method it runs (its last run, or the
    recommendation before one), its variables and its results."""
    from workspace_methods import GOAL_ROLES, METHODS, default_options

    selection = task.selection if selection is None else selection
    method, options = task.method or "", dict(task.options or {})
    if not method:
        advice = _advice(task, session, selection)
        if advice is not None and advice.ready:
            method, options = advice.method, dict(advice.options)
    if method in METHODS:
        options = {**default_options(METHODS[method]), **options}
    groups = 0
    if session.has_data:
        # Groups of a group variable, or the larger side of a contingency table.
        for role in GOAL_ROLES.get(task.goal, ()):
            if role.key in ("group", "a", "b") and selection.get(role.key):
                groups = max(groups, len(session.group_labels(str(selection.get(role.key)))))
    results = tuple(result_facts(e) for e in session.task_results(task.id))
    family = _family_size(task.goal, selection) if method in FAMILY_METHODS else 1
    return AnalysisFacts(task.id, task.title, task.goal, method, options, dict(selection),
                         family, groups, results)


def task_facts(task, session, *, plan_ids=frozenset(), selection: dict | None = None,
               method: str | None = None, options: dict | None = None) -> TaskFacts:
    """The facts of a task's steps. ``selection`` (and ``method``/``options``)
    are what the Analyze page shows while the task is open; by default the
    task as saved."""
    from workspace_methods import GOAL_ROLES, METHODS, holding_confirmations, required_confirmations

    selection = task.selection if selection is None else selection
    roles = GOAL_ROLES.get(task.goal, ())
    names = [n for value in selection.values() for n in _names(value)]
    filled = bool(roles) and all(_names(selection.get(r.key)) for r in roles if not r.optional)
    missing = session.has_data and any(n not in session.variables for n in names)
    advice = _advice(task, session, selection)
    chosen = advice is not None and advice.ready
    design = False
    if chosen:
        key = method or task.method or advice.method
        opts = {**advice.options, **(options if options is not None else
                                     (task.options if key == task.method else {}))}
        if key in METHODS:
            needed = required_confirmations(METHODS[key], opts)
            held = holding_confirmations(key, advice.roles, opts, task.confirms,
                                         (task.state or {}).get("confirm_scopes") or {}, session)
            design = all(c.key in held for c in needed)
    entries = session.task_results(task.id)
    latest = entries[-1] if entries else None
    result, total, reviewed, note, report = "none", 0, 0, False, "none"
    if latest is not None:
        result = "stale" if latest.stale_reasons else "current"
        facts = result_facts(latest)
        total = len(facts.assumptions)
        reviewed = len([a for a in facts.assumptions if a in facts.reviewed])
        note = bool((latest.note or "").strip())
        report = ("current" if latest.in_report else
                  "older" if any(e.in_report for e in entries[:-1]) else "none")
    skipped = "interpretation" in ((task.state or {}).get("skipped") or ())
    return TaskFacts(linked=bool(task.hypothesis_id),
                     hypothesis_in_plan=not task.hypothesis_id or task.hypothesis_id in plan_ids,
                     variables_filled=filled, variables_missing=bool(missing),
                     design_ready=design, method_chosen=chosen or result != "none", result=result,
                     assumptions_total=total, assumptions_reviewed=reviewed, note=note,
                     note_skipped=skipped, report=report)


@dataclass(frozen=True)
class HypothesisView:
    """Everything the interface shows about one hypothesis of the current plan."""

    facts: HypothesisFacts
    plan: dict                       # the hypothesis as saved in the plan
    tasks: tuple = ()                # the research tasks that test it
    analyses: tuple[AnalysisFacts, ...] = ()
    steps: tuple[Step, ...] = ()     # of its first task
    checks: tuple[Check, ...] = ()
    history: tuple[dict, ...] = ()
    records: tuple[dict, ...] = ()   # all its protocol records, oldest first
    latest_result: int | None = None


def hypothesis_views(session, project) -> tuple[HypothesisView, ...]:
    """The hypotheses of the project's current plan with their analyses,
    steps, checks, history and records (empty without a plan)."""
    current = project.plan() if project is not None else None
    if current is None:
        return ()
    plan = current["plan"]
    status = project.hypothesis_status()
    history = project.plan_history()
    records = project.protocol_records()
    plan_ids = frozenset(h["id"] for h in plan.get("hypotheses", []))
    questions = {q["id"]: q for q in plan.get("questions", [])}
    analyses_of: dict[str, list] = {}
    tasks_of: dict[str, list] = {}
    for task in session.tasks:
        if task.hypothesis_id in plan_ids:
            tasks_of.setdefault(task.hypothesis_id, []).append(task)
            analyses_of.setdefault(task.hypothesis_id, []).append(analysis_facts(task, session))
    facts = []
    for number, h in enumerate(plan.get("hypotheses", []), start=1):
        info = status.get(h["id"], {})
        facts.append(HypothesisFacts(
            id=h["id"], number=number, text=h.get("text", ""),
            direction=h.get("direction", "two-sided"), priority=h.get("priority", "primary"),
            alpha=float(h.get("alpha", ENGINE_ALPHA)), family=h.get("family", ""),
            method_key=h.get("method_key", ""), method_options=dict(h.get("method_options") or {}),
            roles=dict(h.get("roles") or {}), standing=info.get("standing", "new"),
            runs_before=int(info.get("runs_before", 0)),
            question_type=(questions.get(h.get("question_id", "")) or {}).get("type", "")))
    views = []
    for fact, h in zip(facts, plan.get("hypotheses", [])):
        label = fact.family.strip().casefold()
        peers = tuple((other.number, a) for other in facts
                      if other.id != fact.id and label and other.family.strip().casefold() == label
                      for a in analyses_of.get(other.id, ()))
        mine = tuple(r for r in records if r.get("hypothesis_id") == fact.id)
        hist = designation_history(history, mine, fact.id)
        tasks = tuple(tasks_of.get(fact.id, ()))
        analyses = tuple(analyses_of.get(fact.id, ()))
        steps = task_steps(task_facts(tasks[0], session, plan_ids=plan_ids)) if tasks else ()
        latest = None
        if tasks:
            entries = session.task_results(tasks[0].id)
            latest = entries[-1].id if entries else None
        views.append(HypothesisView(fact, dict(h), tasks, analyses, steps,
                                    hypothesis_checks(fact, analyses, mine, peers=peers,
                                                      history=hist), hist, mine, latest))
    return tuple(views)


def project_facts(session, project, *, views=(), draft: dict | None = None,
                  questionnaire_draft: bool = False, has_datasets: bool = False,
                  exported: bool = False) -> ProjectFacts:
    """The facts of :func:`next_action` for the project on screen. ``draft``
    is the plan as the researcher is editing it (unsaved changes count)."""
    from project_store import ProjectError, normalise_plan

    saved = project.plan() if project is not None else None
    saved_plan = (saved or {}).get("plan") or {}
    draft = draft if draft is not None else saved_plan
    all_questions = list(draft.get("questions") or [])
    all_hypotheses = list(draft.get("hypotheses") or [])

    def text(item) -> str:
        return (item.get("text") or "").strip()

    written = [q for q in all_questions if text(q) or q.get("type")]
    started = bool(written or all_hypotheses)
    incomplete = next((i for i, q in enumerate(all_questions, start=1)
                       if (text(q) or q.get("type")) and not (text(q) and q.get("type"))), None)
    with_h = {h.get("question_id") for h in all_hypotheses}
    lonely = next((i for i, q in enumerate(all_questions, start=1)
                   if q.get("type") in TESTABLE and text(q) and q.get("id") not in with_h), None)
    empty_h = next((i for i, h in enumerate(all_hypotheses, start=1) if not text(h)), None)
    dirty = False
    if started:
        try:
            clean = normalise_plan(draft)
            dirty = clean != normalise_plan(saved_plan) if saved else bool(
                clean.get("questions") or clean.get("hypotheses"))
        except ProjectError:
            dirty = True           # an invalid value: saving explains it
    progress = tuple(HypothesisProgress(
        v.facts.id, v.facts.number, v.facts.priority, v.tasks[0].id if v.tasks else None,
        v.steps, tuple(c.key for c in open_checks(v.checks)), v.latest_result) for v in views)
    return ProjectFacts(
        has_data=session.has_data or has_datasets, pending_levels=session.pending_levels(),
        has_results=bool(session.results),
        stale_results=sum(1 for e in session.results if e.stale_reasons),
        report_count=len(session.report_order), exported=exported,
        questionnaire_draft=questionnaire_draft, plan_started=started,
        question_incomplete=incomplete, question_without_hypothesis=lonely,
        hypothesis_incomplete=empty_h, plan_dirty=dirty, hypotheses=progress)
