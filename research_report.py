"""The research report as one scientific document (Stage 36.6, spec §11).

Stage 35 (#42) wrote one block per result. This module plans the report
the way a study is written up, in fifteen sections:

 1. title                 6. reliability          11. effects
 2. research question     7. data preparation     12. figures
 3. hypotheses            8. descriptives         13. interpretation
 4. data and sample       9. assumption checks    14. limitations
 5. instruments          10. hypothesis tests     15. appendix (reproducibility)

The plan (:func:`plan_report`) is pure data: sections holding paragraphs,
tables, figures and notes, so it can be tested and previewed without Word.
``report_docx.build_research_docx`` writes it as an editable document.

Rules (spec §11):
* Only saved engine output and the researcher's own entries are used; no
  number is computed, rounded or invented here (a threshold such as .70 for
  a reliability coefficient is compared, never changed).
* Results of one research task are written under one heading; a paragraph
  that would repeat word for word is written once; a result calculated
  twice with an identical report is written once and says so.
* Results from different versions of the data are never presented as one
  finding: each block names its version and the report says how many
  versions it draws on.
* Hypotheses added after results were seen are labelled exploratory
  (post hoc); low reliability, small or unequal groups, missing values,
  stale results and multiple data versions are named as limitations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Iterable

SECTIONS = (
    "title", "question", "hypotheses", "data", "instruments", "reliability", "preparation",
    "descriptives", "assumptions", "tests", "effects", "figures", "interpretation",
    "limitations", "appendix",
)
# Method keys of the workspace and the engine's own section keys (a result
# produced through the classic interface carries only the latter).
DESCRIPTIVE_METHODS = ("descriptive", "explore")
MEASUREMENT_METHODS = ("alpha", "omega", "factor", "item_diagnostics", "reliability")
RELIABILITY_BENCHMARK = 0.70
_COEFFICIENT = re.compile(r"(cronbach|mcdonald|\bα\b|\bω\b|alpha|omega)", re.I)
_SMALL_GROUP = re.compile(r"small group|fewer than (five|5)|permutation p", re.I)
_UNEQUAL = re.compile(r"unequal group", re.I)

TEXT = {
    "en": {
        "title": "Title", "question": "Research question", "hypotheses": "Hypotheses",
        "data": "Data and sample", "instruments": "Instruments and scales",
        "reliability": "Reliability and measurement quality", "preparation": "Data preparation",
        "descriptives": "Descriptive statistics", "assumptions": "Assumption checks",
        "tests": "Hypothesis tests", "effects": "Effects and confidence intervals",
        "figures": "Figures", "interpretation": "Interpretation", "limitations": "Limitations",
        "appendix": "Appendix: parameters for reproducibility",
        "no_question": "The research question is not stated in the project.",
        "hypothesis": "H{number} ({priority}): {text}",
        "h0": "Null hypothesis: {text}",
        "post_hoc": "Added after results were calculated: exploratory (post hoc), not a "
                    "confirmatory test.",
        "planned": "Planned before the results.",
        "priority.primary": "primary", "priority.secondary": "secondary",
        "priority.exploratory": "exploratory",
        "data_columns": ("Result", "Dataset", "Version", "Complete cases", "Rows"),
        "versions": "These results come from {count} versions of the data; each result names "
                    "its version and they are not combined into one finding.",
        "one_version": "All results come from one version of the data ({sha}).",
        "questionnaires": "Questionnaires linked to the project: {items}.",
        "low_reliability": "Measurement quality: {parameter} = {value} for “{title}” is below "
                           "the common .70 benchmark; relationships with this scale are "
                           "attenuated and should be interpreted with caution.",
        "transformation": "{dataset}: {kind} → {outputs}",
        "assumption_reviewed": "reviewed by the researcher",
        "assumption_open": "not yet reviewed",
        "no_assumptions": "No assumption to review was recorded for this result.",
        "effects_columns": ("Result", "Estimate", "Value", "95% CI", "p"),
        "effects_note": "Estimates as calculated by the analysis engine; intervals are the "
                        "engine's 95% confidence intervals.",
        "researcher_note": "Researcher's note (not verified by the analysis engine):",
        "duplicate": "Calculated {count} times with an identical result; written once.",
        "version_line": "Data: {name} ({rows} rows), version {sha}, calculated {when}.",
        "stale": "Needs review: calculated before these changes: {reasons}.",
        "limit.post_hoc": "{count} hypothesis(es) were added after results were calculated; "
                          "their tests are exploratory.",
        "limit.small_groups": "Small groups: {titles}. Results involving them are exploratory.",
        "limit.unequal": "Very unequal group sizes: {titles}.",
        "limit.missing": "Missing values: {title} uses {complete} of {rows} rows.",
        "limit.versions": "The results draw on {count} versions of the data.",
        "limit.stale": "{count} result(s) were calculated before later changes and are marked "
                       "as needing review.",
        "limit.reliability": "Reliability below .70: {titles}.",
        "appendix_columns": ("#", "Result", "Method and options", "Dataset version", "Run"),
        "libraries": "Software: {items}.",
        "figure_title": "Figure of the result “{title}”",
        "task": "Research task: {title}",
    },
    "lv": {
        "title": "Nosaukums", "question": "Pētījuma jautājums", "hypotheses": "Hipotēzes",
        "data": "Dati un izlase", "instruments": "Instrumenti un skalas",
        "reliability": "Ticamība un mērījumu kvalitāte", "preparation": "Datu sagatavošana",
        "descriptives": "Aprakstošā statistika", "assumptions": "Pieņēmumu pārbaude",
        "tests": "Hipotēžu pārbaude", "effects": "Efekti un ticamības intervāli",
        "figures": "Attēli", "interpretation": "Interpretācija", "limitations": "Ierobežojumi",
        "appendix": "Pielikums: parametri atkārtojamībai",
        "no_question": "Pētījuma jautājums projektā nav norādīts.",
        "hypothesis": "H{number} ({priority}): {text}",
        "h0": "Nulles hipotēze: {text}",
        "post_hoc": "Pievienota pēc rezultātu aprēķina: pētnieciska (post hoc), nevis "
                    "apstiprinoša pārbaude.",
        "planned": "Plānota pirms rezultātiem.",
        "priority.primary": "galvenā", "priority.secondary": "papildu",
        "priority.exploratory": "pētnieciska",
        "data_columns": ("Rezultāts", "Datu kopa", "Versija", "Pilnie gadījumi", "Rindas"),
        "versions": "Šie rezultāti iegūti no {count} datu versijām; katrs rezultāts norāda savu "
                    "versiju, un tie netiek apvienoti vienā secinājumā.",
        "one_version": "Visi rezultāti iegūti no vienas datu versijas ({sha}).",
        "questionnaires": "Projektam piesaistītās anketas: {items}.",
        "low_reliability": "Mērījumu kvalitāte: {parameter} = {value} rezultātam “{title}” ir "
                           "zem ierastā .70 sliekšņa; sakarības ar šo skalu ir vājinātas, tās "
                           "jāinterpretē piesardzīgi.",
        "transformation": "{dataset}: {kind} → {outputs}",
        "assumption_reviewed": "pētnieks pārbaudījis",
        "assumption_open": "vēl nav pārbaudīts",
        "no_assumptions": "Šim rezultātam nav reģistrētu pārbaudāmu pieņēmumu.",
        "effects_columns": ("Rezultāts", "Novērtējums", "Vērtība", "95% TI", "p"),
        "effects_note": "Novērtējumi, kā tos aprēķināja analīzes dzinējs; intervāli ir dzinēja "
                        "95% ticamības intervāli.",
        "researcher_note": "Pētnieka piezīme (analīzes dzinējs to nav pārbaudījis):",
        "duplicate": "Aprēķināts {count} reizes ar identisku rezultātu; uzrakstīts vienreiz.",
        "version_line": "Dati: {name} ({rows} rindas), versija {sha}, aprēķināts {when}.",
        "stale": "Jāpārskata: aprēķināts pirms šīm izmaiņām: {reasons}.",
        "limit.post_hoc": "{count} hipotēze(s) pievienotas pēc rezultātu aprēķina; to pārbaudes "
                          "ir pētnieciskas.",
        "limit.small_groups": "Mazas grupas: {titles}. Rezultāti par tām ir pētnieciski.",
        "limit.unequal": "Ļoti nevienādi grupu lielumi: {titles}.",
        "limit.missing": "Trūkstošās vērtības: {title} izmanto {complete} no {rows} rindām.",
        "limit.versions": "Rezultāti balstās uz {count} datu versijām.",
        "limit.stale": "{count} rezultāts(-i) aprēķināti pirms vēlākām izmaiņām un atzīmēti kā "
                       "pārskatāmi.",
        "limit.reliability": "Ticamība zem .70: {titles}.",
        "appendix_columns": ("#", "Rezultāts", "Metode un iestatījumi", "Datu versija", "Aprēķins"),
        "libraries": "Programmatūra: {items}.",
        "figure_title": "Rezultāta “{title}” attēls",
        "task": "Pētījuma uzdevums: {title}",
    },
    "ru": {
        "title": "Название", "question": "Исследовательский вопрос", "hypotheses": "Гипотезы",
        "data": "Данные и выборка", "instruments": "Инструменты и шкалы",
        "reliability": "Надёжность и качество измерения", "preparation": "Подготовка данных",
        "descriptives": "Описательные статистики", "assumptions": "Проверка допущений",
        "tests": "Проверка гипотез", "effects": "Эффекты и доверительные интервалы",
        "figures": "Рисунки", "interpretation": "Интерпретация", "limitations": "Ограничения",
        "appendix": "Приложение: параметры воспроизводимости",
        "no_question": "Исследовательский вопрос в проекте не указан.",
        "hypothesis": "H{number} ({priority}): {text}",
        "h0": "Нулевая гипотеза: {text}",
        "post_hoc": "Добавлена после расчёта результатов: разведочная (post hoc), а не "
                    "подтверждающая проверка.",
        "planned": "Запланирована до получения результатов.",
        "priority.primary": "основная", "priority.secondary": "дополнительная",
        "priority.exploratory": "разведочная",
        "data_columns": ("Результат", "Набор данных", "Версия", "Полные наблюдения", "Строк"),
        "versions": "Эти результаты получены на {count} версиях данных; у каждого результата "
                    "указана его версия, и они не объединяются в один вывод.",
        "one_version": "Все результаты получены на одной версии данных ({sha}).",
        "questionnaires": "Анкеты, связанные с проектом: {items}.",
        "low_reliability": "Качество измерения: {parameter} = {value} для «{title}» ниже "
                           "общепринятого порога .70; связи с этой шкалой ослаблены и требуют "
                           "осторожной интерпретации.",
        "transformation": "{dataset}: {kind} → {outputs}",
        "assumption_reviewed": "проверено исследователем",
        "assumption_open": "ещё не проверено",
        "no_assumptions": "Для этого результата не записано допущений для проверки.",
        "effects_columns": ("Результат", "Оценка", "Значение", "95% ДИ", "p"),
        "effects_note": "Оценки рассчитаны движком анализа; интервалы — его 95% доверительные "
                        "интервалы.",
        "researcher_note": "Примечание исследователя (не проверено движком анализа):",
        "duplicate": "Рассчитано {count} раз(а) с идентичным результатом; приведено один раз.",
        "version_line": "Данные: {name} ({rows} строк), версия {sha}, рассчитано {when}.",
        "stale": "Требует проверки: рассчитано до этих изменений: {reasons}.",
        "limit.post_hoc": "Гипотез, добавленных после расчёта результатов: {count}; их проверки "
                          "носят разведочный характер.",
        "limit.small_groups": "Малые группы: {titles}. Выводы о них носят разведочный характер.",
        "limit.unequal": "Сильно неравные размеры групп: {titles}.",
        "limit.missing": "Пропуски: «{title}» использует {complete} из {rows} строк.",
        "limit.versions": "Результаты опираются на {count} версии данных.",
        "limit.stale": "Результатов, рассчитанных до последующих изменений и отмеченных как "
                       "требующие проверки: {count}.",
        "limit.reliability": "Надёжность ниже .70: {titles}.",
        "appendix_columns": ("№", "Результат", "Метод и параметры", "Версия данных", "Расчёт"),
        "libraries": "Программное обеспечение: {items}.",
        "figure_title": "Рисунок результата «{title}»",
        "task": "Исследовательская задача: {title}",
    },
}


def text(language: str, key: str, **values) -> str:
    table = TEXT.get(language, TEXT["en"])
    value = table.get(key, TEXT["en"][key])
    return value.format(**values) if values and isinstance(value, str) else value


# ------------------------------------------------------------------ inputs
@dataclass
class ResultInfo:
    """What one report entry contributes (taken from the workspace entry)."""

    id: int
    title: str
    method: str
    report: str
    tables: tuple = ()
    figure: bytes | None = None
    figure_title: str = ""
    figure_note: str = ""
    figure_from_studio: bool = False
    interpretation: str = ""
    warnings: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    reviewed: frozenset = frozenset()
    rows: tuple = ()                    # EvidenceRow(parameter, estimate, ci, p)
    dataset: str = ""
    dataset_rows: int = 0
    dataset_sha: str = ""
    complete: int | None = None
    created: datetime | None = None
    task_id: str | None = None
    task_title: str = ""
    stale: tuple[str, ...] = ()
    note: str = ""
    options: dict = field(default_factory=dict)
    run_id: str = ""


@dataclass
class ReportInputs:
    title: str = ""
    project: str = ""
    language: str = "en"
    question: str = ""
    hypotheses: list[dict] = field(default_factory=list)   # text, h0, priority, standing
    questionnaires: list[str] = field(default_factory=list)
    transformations: list[dict] = field(default_factory=list)   # dataset, kind, outputs
    libraries: dict = field(default_factory=dict)
    results: list[ResultInfo] = field(default_factory=list)
    sections: frozenset = frozenset(SECTIONS)


# -------------------------------------------------------------------- plan
@dataclass(frozen=True)
class Item:
    kind: str                     # heading, paragraph, list, table, figure, note
    text: str = ""
    columns: tuple = ()
    rows: tuple = ()
    image: bytes | None = None
    title: str = ""
    note: str = ""
    studio: bool = False
    section: str = ""             # engine section of a figure (caption bands)


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    items: tuple[Item, ...]


@dataclass(frozen=True)
class ReportPlan:
    title: str
    project: str
    language: str
    sections: tuple[Section, ...]
    versions: tuple[str, ...]
    results: int

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)


def _float(value: str) -> float | None:
    try:
        return float(str(value).replace("−", "-").replace(",", ".").strip())
    except ValueError:
        return None


def low_reliability(result: ResultInfo) -> tuple[str, str] | None:
    """(parameter, value) of a reliability coefficient below .70, if any."""
    if result.method not in MEASUREMENT_METHODS:
        return None
    for row in result.rows:
        if _COEFFICIENT.search(row.parameter or ""):
            value = _float(row.estimate)
            if value is not None and value < RELIABILITY_BENCHMARK:
                return row.parameter, row.estimate
    return None


def _merge(results: list[ResultInfo]) -> tuple[list[ResultInfo], dict[int, int]]:
    """Results in report order, a repeated identical result (same method,
    report and data version) kept once with its count."""
    kept: list[ResultInfo] = []
    counts: dict[int, int] = {}
    seen: dict[tuple, ResultInfo] = {}
    for result in results:
        key = (result.method, result.report.strip(), result.dataset_sha)
        if key in seen:
            counts[seen[key].id] = counts.get(seen[key].id, 1) + 1
            continue
        seen[key] = result
        kept.append(result)
    return kept, counts


class _Writer:
    """Collects items, writing a paragraph or note only once per report."""

    def __init__(self):
        self.seen: set[str] = set()

    def paragraphs(self, body: str) -> list[Item]:
        items = []
        for chunk in re.split(r"\n\s*\n", (body or "").strip()):
            chunk = chunk.strip()
            if chunk and chunk not in self.seen:
                self.seen.add(chunk)
                items.append(Item("paragraph", chunk))
        return items


def _result_blocks(results: list[ResultInfo], counts: dict[int, int], writer: _Writer,
                   language: str, *, figures: bool) -> list[Item]:
    """Result blocks grouped by research task, one heading per task."""
    items: list[Item] = []
    done_tasks: set[str] = set()
    for result in results:
        if result.task_id:
            if result.task_id in done_tasks:
                heading = None
            else:
                done_tasks.add(result.task_id)
                heading = text(language, "task", title=result.task_title or result.title)
        else:
            heading = None
        if heading:
            items.append(Item("heading", heading))
        items.append(Item("subheading", result.title))
        when = result.created.strftime("%Y-%m-%d %H:%M") if result.created else "—"
        items.append(Item("note", text(language, "version_line", name=result.dataset or "—",
                                       rows=result.dataset_rows,
                                       sha=(result.dataset_sha or "—")[:12], when=when)))
        if result.stale:
            items.append(Item("warning", text(language, "stale",
                                              reasons="; ".join(result.stale))))
        if counts.get(result.id, 1) > 1:
            items.append(Item("note", text(language, "duplicate", count=counts[result.id])))
        items += writer.paragraphs(result.report)
        for table in result.tables:
            items.append(Item("table", title=str(table.title or result.title),
                              columns=tuple(str(c) for c in table.columns),
                              rows=tuple(tuple(str(v) for v in row) for row in table.rows)))
        if figures and result.figure:
            items.append(_figure(result, language))
    return items


def _figure(result: ResultInfo, language: str) -> Item:
    return Item("figure", image=result.figure,
                title=result.figure_title or text(language, "figure_title", title=result.title),
                note=result.figure_note, studio=result.figure_from_studio,
                section=result.method)


def plan_report(inputs: ReportInputs) -> ReportPlan:
    """The fifteen-section plan of the report (sections without content are
    left out; the researcher chose ``inputs.sections``)."""
    language = inputs.language if inputs.language in TEXT else "en"
    results, counts = _merge(list(inputs.results))
    writer = _Writer()
    wanted = set(inputs.sections)
    sections: list[Section] = []

    def add(key: str, items: Iterable[Item]) -> None:
        items = tuple(items)
        if key in wanted and items:
            sections.append(Section(key, text(language, key), items))

    descriptive = [r for r in results if r.method in DESCRIPTIVE_METHODS]
    measurement = [r for r in results if r.method in MEASUREMENT_METHODS]
    tests = [r for r in results if r not in descriptive and r not in measurement]
    versions = tuple(dict.fromkeys(r.dataset_sha for r in results if r.dataset_sha))

    # 2. Research question
    add("question", [Item("paragraph", inputs.question.strip() or text(language, "no_question"))])

    # 3. Hypotheses
    hypotheses = []
    post_hoc = 0
    for number, hypothesis in enumerate(inputs.hypotheses, start=1):
        priority = hypothesis.get("priority") or "primary"
        line = text(language, "hypothesis", number=number,
                    priority=text(language, f"priority.{priority}")
                    if f"priority.{priority}" in TEXT["en"] else priority,
                    text=str(hypothesis.get("text", "")).strip())
        hypotheses.append(Item("paragraph", line))
        if hypothesis.get("h0"):
            hypotheses.append(Item("note", text(language, "h0", text=hypothesis["h0"])))
        if hypothesis.get("standing") == "added_after_results":
            post_hoc += 1
            hypotheses.append(Item("warning", text(language, "post_hoc")))
        elif hypothesis.get("standing") == "confirmatory":
            hypotheses.append(Item("note", text(language, "planned")))
    add("hypotheses", hypotheses)

    # 4. Data and sample
    data_items: list[Item] = []
    if results:
        data_items.append(Item("table", title=text(language, "data"),
                               columns=text(language, "data_columns"),
                               rows=tuple((r.title, r.dataset or "—", (r.dataset_sha or "—")[:12],
                                           "—" if r.complete is None else str(r.complete),
                                           str(r.dataset_rows)) for r in results)))
        if len(versions) > 1:
            data_items.append(Item("warning", text(language, "versions", count=len(versions))))
        elif versions:
            data_items.append(Item("note", text(language, "one_version", sha=versions[0][:12])))
    add("data", data_items)

    # 5. Instruments and scales
    add("instruments", [Item("paragraph", text(language, "questionnaires",
                                               items="; ".join(inputs.questionnaires)))]
        if inputs.questionnaires else [])

    # 6. Reliability and measurement quality
    reliability_items = _result_blocks(measurement, counts, writer, language, figures=False)
    low = [(r, found) for r in measurement if (found := low_reliability(r))]
    for result, (parameter, value) in low:
        reliability_items.append(Item("warning", text(language, "low_reliability",
                                                      parameter=parameter, value=value,
                                                      title=result.title)))
    add("reliability", reliability_items)

    # 7. Data preparation
    add("preparation", [Item("list", "\n".join(
        text(language, "transformation", dataset=t.get("dataset", "—"), kind=t.get("kind", "—"),
             outputs=", ".join(map(str, t.get("outputs") or ())) or "—")
        for t in inputs.transformations))] if inputs.transformations else [])

    # 8. Descriptive statistics
    add("descriptives", _result_blocks(descriptive, counts, writer, language, figures=False))

    # 9. Assumption checks (reviews are recorded against the English text)
    from interpretation_i18n import translate_assumption

    assumption_items: list[Item] = []
    for result in tests:
        assumption_items.append(Item("subheading", result.title))
        if result.assumptions:
            assumption_items.append(Item("list", "\n".join(
                f"{translate_assumption(a, language)} — "
                + text(language, "assumption_reviewed" if a in result.reviewed
                       else "assumption_open") for a in result.assumptions)))
        else:
            assumption_items.append(Item("note", text(language, "no_assumptions")))
    add("assumptions", assumption_items)

    # 10. Hypothesis tests
    add("tests", _result_blocks(tests, counts, writer, language, figures=False))

    # 11. Effects and confidence intervals
    effect_rows = tuple((r.title, row.parameter, row.estimate, row.ci,
                         "—" if row.p == "Not calculated" else row.p)
                        for r in results if r.method not in DESCRIPTIVE_METHODS
                        for row in r.rows if row.ci and row.ci != "Not calculated")
    add("effects", [Item("table", title=text(language, "effects"),
                         columns=text(language, "effects_columns"), rows=effect_rows),
                    Item("note", text(language, "effects_note"))] if effect_rows else [])

    # 12. Figures
    add("figures", [_figure(r, language) for r in results if r.figure])

    # 13. Interpretation
    interpretation: list[Item] = []
    for result in results:
        body = writer.paragraphs(result.interpretation)
        note = result.note.strip()
        if body or note:
            interpretation.append(Item("subheading", result.title))
            interpretation += body
            if note:
                interpretation.append(Item("note", text(language, "researcher_note") + " " + note))
    add("interpretation", interpretation)

    # 14. Limitations
    limits: list[str] = []
    if post_hoc:
        limits.append(text(language, "limit.post_hoc", count=post_hoc))
    if low:
        limits.append(text(language, "limit.reliability",
                           titles="; ".join(f"{r.title} ({p} = {v})" for r, (p, v) in low)))
    small = [r.title for r in results if any(_SMALL_GROUP.search(w) for w in r.warnings)]
    if small:
        limits.append(text(language, "limit.small_groups", titles="; ".join(small)))
    unequal = [r.title for r in results if any(_UNEQUAL.search(w) for w in r.warnings)]
    if unequal:
        limits.append(text(language, "limit.unequal", titles="; ".join(unequal)))
    for result in results:
        if result.complete is not None and result.dataset_rows and \
                result.complete < result.dataset_rows:
            limits.append(text(language, "limit.missing", title=result.title,
                               complete=result.complete, rows=result.dataset_rows))
    if len(versions) > 1:
        limits.append(text(language, "limit.versions", count=len(versions)))
    stale = [r for r in results if r.stale]
    if stale:
        limits.append(text(language, "limit.stale", count=len(stale)))
    engine = []
    for result in results:
        for warning in result.warnings:
            warning = warning.strip()
            if warning and warning not in writer.seen and warning not in engine:
                engine.append(warning)
    add("limitations", [Item("list", "\n".join(limits + engine))] if limits or engine else [])

    # 15. Appendix: reproducibility
    appendix_rows = tuple(
        (str(number), r.title,
         r.method + ("" if not r.options else " · " + ", ".join(
             f"{k}={v}" for k, v in sorted(r.options.items()))),
         (r.dataset_sha or "—")[:12], (r.run_id or "—")[:12])
        for number, r in enumerate(results, start=1))
    appendix = [Item("table", title=text(language, "appendix"),
                     columns=text(language, "appendix_columns"), rows=appendix_rows)]
    if inputs.libraries:
        appendix.append(Item("note", text(language, "libraries", items=", ".join(
            f"{k} {v}" for k, v in sorted(inputs.libraries.items())))))
    add("appendix", appendix if results else [])

    return ReportPlan(title=inputs.title, project=inputs.project, language=language,
                      sections=tuple(sections), versions=versions, results=len(results))


def result_info(entry, *, reviewed=frozenset(), note: str = "", task_title: str = "") -> ResultInfo:
    """A workspace ``ResultEntry`` as report input (only saved output)."""
    from report_docx import _studio_figure

    run = entry.run
    evidence = run.evidence()
    provenance = entry.provenance or {}
    studio = _studio_figure(entry)
    figure, figure_title, figure_note = studio if studio else (run.png, "", "")
    complete = evidence.n_complete
    if complete is None and provenance.get("complete") is not None:
        complete = int(provenance["complete"])
    return ResultInfo(
        id=entry.id, title=run.title, method=entry.method or run.section, report=run.report or "",
        tables=tuple(run.tables or ()), figure=figure, figure_title=figure_title,
        figure_note=figure_note, figure_from_studio=studio is not None,
        interpretation=run.interpretation or "", warnings=tuple(run.warnings or ()),
        assumptions=tuple(evidence.assumptions), reviewed=frozenset(reviewed),
        rows=tuple(evidence.rows), dataset=entry.dataset, dataset_rows=entry.rows,
        dataset_sha=str(provenance.get("dataset_sha256") or ""), complete=complete,
        created=entry.created, task_id=entry.task_id, task_title=task_title,
        stale=tuple(entry.stale_reasons or ()), note=note, options=dict(entry.options or {}),
        run_id=entry.record_id or "")
