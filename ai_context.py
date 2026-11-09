"""Project-scoped context permissions for the AI assistant (Stage 34, C;
enabled in Stage 36, §12).

The assistant can be used only when it is **set up**: a provider and a
model are chosen in Settings and the researcher's own key for that provider
is in the operating system's credential store (``readiness``). Without
that, ``check_request`` refuses every request and the application works
exactly as before, offline. The contract every request follows:

* context comes only from the sources listed in ``SOURCES``; each one is
  off until the researcher allows it **for this project**
  (``Project.set_ai_permission``, stored in the project database);
* data rows can never go to a remote provider unless the researcher has
  stated, for this project, that its data rows identify nobody;
* before every request the researcher sees exactly what would be sent
  (``preview``) and confirms it; the transfer is logged in the project's
  activity log; switching projects means a new context;
* without an open project no project source can be sent (only a result's
  own text, see ``ai_assist``);
* from the researcher profile only explanation preferences are used — never
  the study level, and nothing is inferred about anyone's ability.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PREVIEW_ROWS = 5
PREVIEW_REPORT_CHARS = 1200


@dataclass(frozen=True)
class ContextSource:
    key: str
    label: str        # workspace_text key
    detail: str       # workspace_text key


SOURCES = (
    ContextSource("overview", "ai.source.overview", "ai.source.overview_detail"),
    ContextSource("plan", "ai.source.plan", "ai.source.plan_detail"),
    ContextSource("dictionary", "ai.source.dictionary", "ai.source.dictionary_detail"),
    ContextSource("results", "ai.source.results", "ai.source.results_detail"),
    ContextSource("questionnaires", "ai.source.questionnaires", "ai.source.questionnaires_detail"),
    ContextSource("raw_data", "ai.source.raw_data", "ai.source.raw_data_detail"),
    ContextSource("profile", "ai.source.profile", "ai.source.profile_detail"),
)
SOURCE_KEYS = tuple(source.key for source in SOURCES)
PROFILE_FIELDS = ("explanations", "experience", "language")   # never study level or name


class ContextRefused(Exception):
    """A permission change or request that the rules do not allow.

    ``codes`` are stable keys for the interface (see ``refusals``)."""

    def __init__(self, message: str, codes: tuple[str, ...] = ()):
        super().__init__(message)
        self.codes = tuple(codes)


# ------------------------------------------------------------- readiness
@dataclass(frozen=True)
class Readiness:
    """Whether the assistant can be used: ``problem`` is empty when it can,
    otherwise ``no_store`` (no protected credential store on this computer),
    ``no_key`` (no key saved for the chosen provider) or ``no_model``."""

    provider: str = "openai"
    model: str = ""
    daily_tokens: int = 0
    problem: str = "no_key"

    @property
    def ready(self) -> bool:
        return not self.problem

    @property
    def provider_name(self) -> str:
        import ai_providers

        info = ai_providers.PROVIDERS.get(self.provider)
        return info.name if info else self.provider

    @property
    def host(self) -> str:
        import ai_providers

        info = ai_providers.PROVIDERS.get(self.provider)
        return info.host if info else ""


def readiness(data_root: Path) -> Readiness:
    """The assistant's set-up, read locally: the settings file and whether the
    credential store holds a key. Nothing is sent and the key is not read."""
    import ai_providers
    import secret_store

    settings = ai_providers.load_settings(data_root)
    provider, model = settings["provider"], settings["model"]
    try:
        store = secret_store.available()
        stored = store and secret_store.has_key(provider)
    except Exception:          # a credential store that cannot be read is no store
        store, stored = False, False
    problem = ("no_store" if not store else "no_key" if not stored
               else "no_model" if not model else "")
    return Readiness(provider, model, settings["daily_tokens"], problem)


def _is_ready(available) -> bool:
    if isinstance(available, Readiness):
        return available.ready
    return bool(available)


# ---------------------------------------------------------- permissions
def permissions(project) -> dict[str, bool]:
    """Every source with its decision for this project (off unless allowed)."""
    stored = project.ai_permissions()
    return {key: bool(stored.get(key, False)) for key in SOURCE_KEYS}


def allow(project, source: str, allowed: bool, *, remote: bool) -> None:
    """Record a decision; data rows for a remote provider need the anonymity statement."""
    if source not in SOURCE_KEYS:
        raise ContextRefused(f"Unknown context source: {source}", ("unknown_source",))
    if allowed and source == "raw_data" and remote and not project.data_anonymous:
        raise ContextRefused("Data rows can go to a remote provider only after you state "
                             "that this project's data identify nobody.", ("rows_not_anonymous",))
    project.set_ai_permission(source, allowed)


def state_anonymous(project, anonymous: bool) -> None:
    """Record (or withdraw) the statement that the project's data rows
    identify nobody. Withdrawing it also withdraws permission for data rows."""
    project.set_data_anonymous(anonymous)
    if not anonymous and permissions(project)["raw_data"]:
        project.set_ai_permission("raw_data", False)


@dataclass(frozen=True)
class Refusal:
    code: str        # not_ready | no_project | unknown_source | not_allowed | rows_not_anonymous
    source: str      # the context source concerned, or ""
    message: str     # English, for logs and errors


def refusals(project, sources, *, remote: bool, available=None) -> list[Refusal]:
    """Every reason why a request for these sources may not be sent.

    ``available`` is a ``Readiness`` (or a bool): whether a provider, a model
    and the researcher's key are set up. Without it nothing is sent.
    ``project`` may be None: then no project source can be included."""
    found = []
    if not _is_ready(available):
        found.append(Refusal("not_ready", "", "No AI provider is set up: connect a provider "
                             "with your own key and choose a model in Settings."))
    sources = list(sources)
    if project is None:
        if sources:
            found.append(Refusal("no_project", "", "Project sources can be sent only while "
                                 "a project is open."))
        return found
    decided = permissions(project)
    for source in sources:
        if source not in SOURCE_KEYS:
            found.append(Refusal("unknown_source", str(source),
                                 f"Unknown context source: {source}"))
        elif not decided[source]:
            found.append(Refusal("not_allowed", source, f"Not allowed for this project: {source}"))
    if "raw_data" in sources and remote and not project.data_anonymous:
        found.append(Refusal("rows_not_anonymous", "raw_data",
                             "Data rows cannot go to a remote provider: this project's data "
                             "are not stated to be anonymous."))
    return found


def check_request(project, sources, *, remote: bool, available=None) -> list[str]:
    """Why a request for these sources may not be sent (empty = allowed)."""
    return [refusal.message for refusal in refusals(project, sources, remote=remote,
                                                    available=available)]


def data_rows(sources, session) -> int:
    """How many data rows a request with these sources would contain."""
    if "raw_data" not in sources or session is None or not session.has_data:
        return 0
    return min(PREVIEW_ROWS, len(session.df))


# -------------------------------------------------------------- preview
_PLAN_FIELDS = (("objectives", "Objectives"), ("design", "Design"),
                ("population", "Population"), ("preregistration", "Pre-registration"))
_HYPOTHESIS_FIELDS = (("h0", "H0"), ("outcome", "Outcome"), ("predictors", "Predictors"),
                      ("covariates", "Covariates"), ("method", "Planned method"),
                      ("exclusions", "Exclusions"))
_STANDING = {"confirmatory": "in the plan before any result was calculated",
             "added_after_results": "added to the plan after results had been calculated",
             "exploratory": "marked exploratory"}


def _plan(project) -> str:
    current = project.plan()
    if current is None:
        return ""
    plan, status = current["plan"], project.hypothesis_status()
    lines = [f"{label}: {plan[name]}" for name, label in _PLAN_FIELDS if plan.get(name)]
    for number, hypothesis in enumerate(plan.get("hypotheses") or [], start=1):
        standing = _STANDING.get(status.get(hypothesis["id"], {}).get("standing", ""), "")
        lines.append(f"Hypothesis {number} ({hypothesis['priority']}, {hypothesis['direction']}, "
                     f"alpha {hypothesis['alpha']:g}" + (f"; {standing}" if standing else "")
                     + f"): {hypothesis['text']}")
        lines += [f"  {label}: {hypothesis[name]}" for name, label in _HYPOTHESIS_FIELDS
                  if hypothesis.get(name)]
    return "\n".join(lines)


def preview(source: str, *, project=None, session=None, profile=None,
            survey_root=None) -> str:
    """Exactly what this source would contribute for the open project, as text.

    Built locally from the project and the session; nothing leaves the computer."""
    if source == "overview":
        if project is None:
            return ""
        info = project.info()
        lines = [f"Title: {info.title}"]
        if info.description:
            lines.append(f"Description: {info.description}")
        if info.research_area:
            lines.append(f"Research area: {info.research_area}")
        lines += [f"Research question: {q['text']}" for q in project.questions()]
        return "\n".join(lines)
    if source == "plan":
        return "" if project is None else _plan(project)
    if source == "dictionary":
        if session is None or not session.has_data:
            return ""
        return "\n".join(f"{name}: {info.confirmed}" for name, info in session.variables.items())
    if source == "results":
        if session is None:
            return ""
        parts = []
        for entry in session.results:
            report = entry.run.report.strip()
            if len(report) > PREVIEW_REPORT_CHARS:
                report = report[:PREVIEW_REPORT_CHARS] + " …"
            parts.append(f"{entry.title} ({entry.dataset})\n{report}")
        return "\n\n".join(parts)
    if source == "questionnaires":
        if project is None:
            return ""
        lines = []
        for linked in project.questionnaires():
            count = ""
            if survey_root is not None:
                try:
                    from survey_storage import get_survey

                    count = f" — {len(get_survey(survey_root, linked['survey_id']).questions)} questions"
                except Exception:
                    count = ""
            lines.append(f"{linked['title']}{count}")
        return "\n".join(lines)
    if source == "raw_data":
        if session is None or not session.has_data:
            return ""
        frame = session.df
        head = frame.head(PREVIEW_ROWS).to_csv(index=False, lineterminator="\n").strip()
        more = len(frame) - min(len(frame), PREVIEW_ROWS)
        return head + (f"\n… {more} more rows" if more > 0 else "")
    if source == "profile":
        if profile is None:
            return ""
        return "\n".join(f"{name}: {getattr(profile, name)}" for name in PROFILE_FIELDS
                         if getattr(profile, name))
    raise ContextRefused(f"Unknown context source: {source}", ("unknown_source",))
