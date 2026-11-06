"""Project-scoped context permissions for a future AI assistant (Stage 34, C).

**No AI assistant is connected in this version.** Nothing in the
application sends project content to any service, and ``AI_AVAILABLE`` is
False, so ``check_request`` refuses every request. What this module fixes
now is the contract a future assistant has to follow:

* context comes only from the sources listed in ``SOURCES``; each one is
  off until the researcher allows it **for this project**
  (``Project.set_ai_permission``, stored in the project database);
* data rows can never go to a remote provider unless the researcher has
  stated, for this project, that its data rows identify nobody;
* before every request the researcher sees exactly what would be sent
  (``preview``) and confirms it; the transfer is logged in the project's
  activity log; switching projects means a new context;
* from the researcher profile only explanation preferences are used — never
  the study level, and nothing is inferred about anyone's ability.
"""

from __future__ import annotations

from dataclasses import dataclass

AI_AVAILABLE = False
PREVIEW_ROWS = 5
PREVIEW_REPORT_CHARS = 1200


@dataclass(frozen=True)
class ContextSource:
    key: str
    label: str        # workspace_text key
    detail: str       # workspace_text key


SOURCES = (
    ContextSource("overview", "ai.source.overview", "ai.source.overview_detail"),
    ContextSource("dictionary", "ai.source.dictionary", "ai.source.dictionary_detail"),
    ContextSource("results", "ai.source.results", "ai.source.results_detail"),
    ContextSource("questionnaires", "ai.source.questionnaires", "ai.source.questionnaires_detail"),
    ContextSource("raw_data", "ai.source.raw_data", "ai.source.raw_data_detail"),
    ContextSource("profile", "ai.source.profile", "ai.source.profile_detail"),
)
SOURCE_KEYS = tuple(source.key for source in SOURCES)
PROFILE_FIELDS = ("explanations", "experience", "language")   # never study level or name


class ContextRefused(Exception):
    """A permission change or request that the rules do not allow."""


def permissions(project) -> dict[str, bool]:
    """Every source with its decision for this project (off unless allowed)."""
    stored = project.ai_permissions()
    return {key: bool(stored.get(key, False)) for key in SOURCE_KEYS}


def allow(project, source: str, allowed: bool, *, remote: bool) -> None:
    """Record a decision; data rows for a remote provider need the anonymity statement."""
    if source not in SOURCE_KEYS:
        raise ContextRefused(f"Unknown context source: {source}")
    if allowed and source == "raw_data" and remote and not project.data_anonymous:
        raise ContextRefused("Data rows can go to a remote provider only after you state "
                             "that this project's data identify nobody.")
    project.set_ai_permission(source, allowed)


def check_request(project, sources, *, remote: bool) -> list[str]:
    """Why a request for these sources may not be sent (empty = allowed).

    In this version the first reason is always that no assistant exists."""
    reasons = []
    if not AI_AVAILABLE:
        reasons.append("AI assistance is not available in this version.")
    decided = permissions(project)
    for source in sources:
        if source not in SOURCE_KEYS:
            reasons.append(f"Unknown context source: {source}")
        elif not decided[source]:
            reasons.append(f"Not allowed for this project: {source}")
    if "raw_data" in sources and remote and not project.data_anonymous:
        reasons.append("Data rows cannot go to a remote provider: this project's data are "
                       "not stated to be anonymous.")
    return reasons


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
    raise ContextRefused(f"Unknown context source: {source}")
