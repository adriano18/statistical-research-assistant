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
* Stage 37.0b: each hypothesis of the plan gets one block in the Hypotheses
  section (:func:`hypothesis_rows`: direction, α and plan version; the
  analyses and results that test it with the engine's n and estimates as
  saved; the researcher's recorded decisions with their reasons; the open
  checks), and the editable table *Hypotheses and evidence*
  (:func:`evidence_table`). Every line names its hypothesis, so no paragraph
  is written twice; nothing says whether a hypothesis is supported.
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
        "h0": "Null hypothesis of H{number}: {text}",
        "post_hoc": "H{number} was added after results were calculated: exploratory (post hoc), "
                    "not a confirmatory test.",
        "planned": "H{number} was planned before the results.",
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
        "version_line": "Data of “{title}”: {name} ({rows} rows), version {sha}, calculated "
                        "{when}.",
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
        # Stage 37.0b: the hypothesis rows and the hypotheses-and-evidence table.
        "hyp_direction": "H{number}: direction {direction}; α = {alpha}; plan version {version}.",
        "not_tested": "No analysis in this project tests H{number} yet.",
        "tested_by": "H{number} tested by “{task}”: {calculation}; {state}.",
        "tested_by_none": "H{number} tested by “{task}”: no result yet.",
        "result_line": "Result for H{number}: “{title}” ({state}; {link}): n = {n}; "
                       "{estimates}; {review}.",
        "estimate": "{parameter} = {estimate}",
        "estimate_ci": "{parameter} = {estimate}, 95% CI {ci}",
        "no_estimate": "no estimate in the saved result",
        "state.current": "result current",
        "state.stale": "result needs review ({reasons})",
        "state.in_report": "in this report",
        "state.not_in_report": "not in this report",
        "review_line": "{reviewed} of {total} assumption checks reviewed, {note}",
        "note.written": "researcher's note written",
        "note.skipped": "interpretation skipped by the researcher",
        "note.none": "no researcher's note",
        "calc.tests": "{count} tests",
        "calc.correction": "correction: {adjust}",
        "records_title": "Decisions recorded for H{number}:",
        "records_none": "No decision is recorded for H{number}.",
        "record.deviation": "Deviation from the plan ({what}), recorded {when}, {timing}. "
                            "{change}Reason: {reason}",
        "record.acknowledgement": "Acknowledged ({check}), recorded {when}, {timing}. "
                                  "Reason: {reason}",
        "record.justification": "Justification ({check}), recorded {when}, {timing}. "
                                "Reason: {reason}",
        "record.designation": "Designation of H{number} changed after results: {from} → {to} "
                              "(plan version "
                              "{version}; {runs} result(s) in the project), recorded {when}. "
                              "Reason: {reason}",
        "record.designation_unexplained": "Designation of H{number} changed after results: "
                                          "{from} → {to} "
                                          "(plan version {version}; {runs} result(s) in the "
                                          "project); no reason was recorded.",
        "record.withdrawn": "Withdrawn on {when}. Reason for the withdrawal: {reason}",
        "record.plan_change": "H{number} changed in the plan after results ({what}): {from} → "
                              "{to} (plan version {version}; {runs} result(s) in the project), "
                              "recorded {when}. Reason: {reason}",
        "record.planned_actual": "Planned: {planned}; used: {actual}. ",
        "timing.before": "before H{number} had any result",
        "timing.after": "after {count} result(s) of H{number}",
        "what.method": "method", "what.variables": "variables", "what.direction": "direction",
        "what.alpha": "significance level", "what.designation": "designation",
        "what.sample": "sample", "what.exclusions": "exclusions", "what.data": "data",
        "what.other": "other", "what.wording": "wording",
        "about.H-DIR-TWOSIDED": "a directional hypothesis, two-sided p-values",
        "about.H-DIR-OMNIBUS": "a directional hypothesis, a test without direction",
        "about.H-FAMILY-UNCORRECTED": "several tests without an adjustment",
        "about.H-FAMILY-SPLIT": "one family over several analyses",
        "about.H-ALPHA": "the plan's α and the analysis's α differ",
        "about.H-METHOD-DIFFERS": "another method than planned",
        "about.H-VARIABLES-DIFFER": "other variables than planned",
        "about.H-SPEC-CHANGED": "the analysis changed after its first result",
        "about.H-ADDED-AFTER": "added after results",
        "about.H-DESIGNATION-CHANGED": "designation changed after results",
        "about.other": "a recorded decision",
        "limits_title": "Limitations of the evidence for H{number}: {items}",
        "others": "{count} other result(s) of the analyses of H{number} are not in this "
                  "report.",
        "evidence": "Hypotheses and evidence",
        "evidence_columns": ("Hypothesis", "Source result", "Data version", "Calculation",
                             "Review", "Limitations"),
        "evidence_none": "No result in this report",
        "cell.hypothesis": "H{number} ({priority})",
        "cell.result": "{title} ({state})",
        "cell.current": "current", "cell.stale": "needs review",
        "cell.calculated_for": "calculated as a test of H{number}, plan version {version}",
        "cell.linked_late": "linked to H{number} after it was calculated",
        "cell.review": "{reviewed} of {total} assumption checks reviewed; {note}",
        "cell.stale_reasons": "Needs review: {reasons}",
        "cell.missing": "{complete} of {rows} rows complete",
        "evidence_note": "Each row is a result of this report that tests the hypothesis. The "
                         "table repeats saved engine output and the researcher's own records; "
                         "it does not judge the hypothesis.",
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
        "h0": "H{number} nulles hipotēze: {text}",
        "post_hoc": "H{number} pievienota pēc rezultātu aprēķina: pētnieciska (post hoc), nevis "
                    "apstiprinoša pārbaude.",
        "planned": "H{number} plānota pirms rezultātiem.",
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
        "version_line": "“{title}” dati: {name} ({rows} rindas), versija {sha}, aprēķināts "
                        "{when}.",
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
        # Stage 37.0b. LV drafts — needs native review.
        "hyp_direction": "H{number}: virziens {direction}; α = {alpha}; plāna versija {version}.",
        "not_tested": "Neviena šī projekta analīze vēl nepārbauda H{number}.",
        "tested_by": "H{number} pārbauda “{task}”: {calculation}; {state}.",
        "tested_by_none": "H{number} pārbauda “{task}”: rezultāta vēl nav.",
        "result_line": "H{number} rezultāts: “{title}” ({state}; {link}): n = {n}; "
                       "{estimates}; {review}.",
        "estimate": "{parameter} = {estimate}",
        "estimate_ci": "{parameter} = {estimate}, 95% TI {ci}",
        "no_estimate": "saglabātajā rezultātā nav novērtējuma",
        "state.current": "rezultāts ir aktuāls",
        "state.stale": "rezultāts jāpārskata ({reasons})",
        "state.in_report": "ir šajā atskaitē",
        "state.not_in_report": "nav šajā atskaitē",
        "review_line": "pārskatītas {reviewed} no {total} pieņēmumu pārbaudēm, {note}",
        "note.written": "pētnieka piezīme uzrakstīta",
        "note.skipped": "pētnieks interpretāciju izlaida",
        "note.none": "pētnieka piezīmes nav",
        "calc.tests": "testu skaits: {count}",
        "calc.correction": "korekcija: {adjust}",
        "records_title": "Hipotēzei H{number} ierakstītie lēmumi:",
        "records_none": "Hipotēzei H{number} nav ierakstīta neviena lēmuma.",
        "record.deviation": "Novirze no plāna ({what}), ierakstīta {when}, {timing}. "
                            "{change}Iemesls: {reason}",
        "record.acknowledgement": "Atzīts ({check}), ierakstīts {when}, {timing}. "
                                  "Iemesls: {reason}",
        "record.justification": "Pamatojums ({check}), ierakstīts {when}, {timing}. "
                                "Iemesls: {reason}",
        "record.designation": "H{number} prioritāte mainīta pēc rezultātiem: {from} → {to} "
                              "(plāna versija "
                              "{version}; rezultāti projektā: {runs}), ierakstīts {when}. "
                              "Iemesls: {reason}",
        "record.designation_unexplained": "H{number} prioritāte mainīta pēc rezultātiem: "
                                          "{from} → {to} "
                                          "(plāna versija {version}; rezultāti projektā: "
                                          "{runs}); iemesls nav ierakstīts.",
        "record.withdrawn": "Atsaukts {when}. Atsaukšanas iemesls: {reason}",
        "record.plan_change": "H{number} plānā mainīta pēc rezultātiem ({what}): {from} → "
                              "{to} (plāna versija {version}; rezultāti projektā: {runs}), "
                              "ierakstīts {when}. Iemesls: {reason}",
        "record.planned_actual": "Plānots: {planned}; izmantots: {actual}. ",
        "timing.before": "pirms H{number} bija kāds rezultāts",
        "timing.after": "pēc H{number} rezultātiem ({count})",
        "what.method": "metode", "what.variables": "mainīgie", "what.direction": "virziens",
        "what.alpha": "nozīmības līmenis", "what.designation": "prioritāte",
        "what.sample": "izlase", "what.exclusions": "izslēgšana", "what.data": "dati",
        "what.other": "cits", "what.wording": "formulējums",
        "about.H-DIR-TWOSIDED": "virziena hipotēze, divpusējas p vērtības",
        "about.H-DIR-OMNIBUS": "virziena hipotēze, tests bez virziena",
        "about.H-FAMILY-UNCORRECTED": "vairāki testi bez korekcijas",
        "about.H-FAMILY-SPLIT": "viena saime vairākās analīzēs",
        "about.H-ALPHA": "plāna α un analīzes α atšķiras",
        "about.H-METHOD-DIFFERS": "cita metode nekā plānots",
        "about.H-VARIABLES-DIFFER": "citi mainīgie nekā plānots",
        "about.H-SPEC-CHANGED": "analīze mainīta pēc pirmā rezultāta",
        "about.H-ADDED-AFTER": "pievienota pēc rezultātiem",
        "about.H-DESIGNATION-CHANGED": "prioritāte mainīta pēc rezultātiem",
        "about.other": "ierakstīts lēmums",
        "limits_title": "Hipotēzes H{number} pierādījumu ierobežojumi: {items}",
        "others": "Citi H{number} analīžu rezultāti, kas nav šajā atskaitē: {count}.",
        "evidence": "Hipotēzes un pierādījumi",
        "evidence_columns": ("Hipotēze", "Avota rezultāts", "Datu versija", "Aprēķins",
                             "Pārskatīšana", "Ierobežojumi"),
        "evidence_none": "Šajā atskaitē nav rezultāta",
        "cell.hypothesis": "H{number} ({priority})",
        "cell.result": "{title} ({state})",
        "cell.current": "aktuāls", "cell.stale": "jāpārskata",
        "cell.calculated_for": "aprēķināts kā H{number} pārbaude, plāna versija {version}",
        "cell.linked_late": "sasaistīts ar H{number} pēc aprēķina",
        "cell.review": "pārskatītas {reviewed} no {total} pieņēmumu pārbaudēm; {note}",
        "cell.stale_reasons": "Jāpārskata: {reasons}",
        "cell.missing": "pilnas {complete} no {rows} rindām",
        "evidence_note": "Katra rinda ir šīs atskaites rezultāts, kas pārbauda hipotēzi. Tabulā "
                         "atkārtots analīzes dzinēja saglabātais rezultāts un pētnieka ieraksti; "
                         "tā hipotēzi nevērtē.",
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
        "h0": "Нулевая гипотеза для H{number}: {text}",
        "post_hoc": "H{number} добавлена после расчёта результатов: разведочная (post hoc), а не "
                    "подтверждающая проверка.",
        "planned": "H{number} запланирована до получения результатов.",
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
        "version_line": "Данные «{title}»: {name} ({rows} строк), версия {sha}, рассчитано "
                        "{when}.",
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
        # Stage 37.0b. RU drafts — needs native review.
        "hyp_direction": "H{number}: направленность {direction}; α = {alpha}; версия плана "
                         "{version}.",
        "not_tested": "Пока ни один анализ этого проекта не проверяет H{number}.",
        "tested_by": "H{number} проверяется анализом «{task}»: {calculation}; {state}.",
        "tested_by_none": "H{number} проверяется анализом «{task}»: результата ещё нет.",
        "result_line": "Результат для H{number}: «{title}» ({state}; {link}): n = {n}; "
                       "{estimates}; {review}.",
        "estimate": "{parameter} = {estimate}",
        "estimate_ci": "{parameter} = {estimate}, 95% ДИ {ci}",
        "no_estimate": "в сохранённом результате нет оценки",
        "state.current": "результат актуален",
        "state.stale": "результат требует проверки ({reasons})",
        "state.in_report": "есть в этом отчёте",
        "state.not_in_report": "нет в этом отчёте",
        "review_line": "проверено допущений {reviewed} из {total}, {note}",
        "note.written": "примечание исследователя написано",
        "note.skipped": "исследователь пропустил интерпретацию",
        "note.none": "примечания исследователя нет",
        "calc.tests": "проверок: {count}",
        "calc.correction": "поправка: {adjust}",
        "records_title": "Решения, записанные для H{number}:",
        "records_none": "Для H{number} не записано ни одного решения.",
        "record.deviation": "Отклонение от плана ({what}), записано {when}, {timing}. "
                            "{change}Причина: {reason}",
        "record.acknowledgement": "Признано ({check}), записано {when}, {timing}. "
                                  "Причина: {reason}",
        "record.justification": "Обоснование ({check}), записано {when}, {timing}. "
                                "Причина: {reason}",
        "record.designation": "Приоритет H{number} изменён после результатов: {from} → {to} "
                              "(версия плана "
                              "{version}; результатов в проекте: {runs}), записано {when}. "
                              "Причина: {reason}",
        "record.designation_unexplained": "Приоритет H{number} изменён после результатов: "
                                          "{from} → {to} "
                                          "(версия плана {version}; результатов в проекте: "
                                          "{runs}); причина не записана.",
        "record.withdrawn": "Отозвано {when}. Причина отзыва: {reason}",
        "record.plan_change": "H{number} изменена в плане после результатов ({what}): {from} "
                              "→ {to} (версия плана {version}; результатов в проекте: "
                              "{runs}), записано {when}. Причина: {reason}",
        "record.planned_actual": "По плану: {planned}; использовано: {actual}. ",
        "timing.before": "до первого результата H{number}",
        "timing.after": "после результатов H{number} ({count})",
        "what.method": "метод", "what.variables": "переменные", "what.direction": "направленность",
        "what.alpha": "уровень значимости", "what.designation": "приоритет",
        "what.sample": "выборка", "what.exclusions": "исключения", "what.data": "данные",
        "what.other": "другое", "what.wording": "формулировка",
        "about.H-DIR-TWOSIDED": "направленная гипотеза, двусторонние p-значения",
        "about.H-DIR-OMNIBUS": "направленная гипотеза, критерий без направления",
        "about.H-FAMILY-UNCORRECTED": "несколько проверок без поправки",
        "about.H-FAMILY-SPLIT": "одно семейство в нескольких анализах",
        "about.H-ALPHA": "α плана и α анализа различаются",
        "about.H-METHOD-DIFFERS": "другой метод, чем в плане",
        "about.H-VARIABLES-DIFFER": "другие переменные, чем в плане",
        "about.H-SPEC-CHANGED": "анализ изменён после первого результата",
        "about.H-ADDED-AFTER": "добавлена после результатов",
        "about.H-DESIGNATION-CHANGED": "приоритет изменён после результатов",
        "about.other": "записанное решение",
        "limits_title": "Ограничения данных по H{number}: {items}",
        "others": "Других результатов анализов H{number}, которых нет в этом отчёте: "
                  "{count}.",
        "evidence": "Гипотезы и данные",
        "evidence_columns": ("Гипотеза", "Исходный результат", "Версия данных", "Расчёт",
                             "Проверка", "Ограничения"),
        "evidence_none": "В этом отчёте нет результата",
        "cell.hypothesis": "H{number} ({priority})",
        "cell.result": "{title} ({state})",
        "cell.current": "актуален", "cell.stale": "требует проверки",
        "cell.calculated_for": "рассчитан как проверка H{number}, версия плана {version}",
        "cell.linked_late": "связан с H{number} после расчёта",
        "cell.review": "проверено допущений {reviewed} из {total}; {note}",
        "cell.stale_reasons": "Требует проверки: {reasons}",
        "cell.missing": "полных строк {complete} из {rows}",
        "evidence_note": "Каждая строка — результат этого отчёта, проверяющий гипотезу. Таблица "
                         "повторяет сохранённый вывод движка анализа и записи исследователя; "
                         "она не оценивает гипотезу.",
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


@dataclass(frozen=True)
class AnalysisLine:
    """Stage 37.0b: one research task that tests a hypothesis, as the report
    names it. Every number is the engine's (the size of a batch family and
    its adjustment come from the saved result)."""

    task: str
    method: str = ""                  # method key ("" before a method is chosen)
    options: dict = field(default_factory=dict)
    method_label: str = ""            # English engine label of the test that ran
    tests: int | None = None          # the engine's family size (batch analyses)
    correction: str = ""              # the engine's adjustment key (batch analyses)
    state: str = "none"               # none | current | stale (its latest result)
    reasons: tuple[str, ...] = ()     # why a stale result needs review
    in_report: bool = False           # its latest result is in this report
    title: str = ""                   # the title of its latest result
    reviewed: int = 0                 # assumption checks of that result marked reviewed
    assumptions: int = 0              # assumption checks of that result
    note: str = "none"                # written | skipped | none


@dataclass(frozen=True)
class EvidenceResult:
    """Stage 37.0b: one result of the report that tests a hypothesis (one row
    of the table *Hypotheses and evidence*)."""

    title: str
    dataset: str = ""
    dataset_sha: str = ""
    method: str = ""
    options: dict = field(default_factory=dict)
    method_label: str = ""
    tests: int | None = None
    correction: str = ""
    state: str = "current"            # current | stale
    reasons: tuple[str, ...] = ()
    reviewed: int = 0
    assumptions: int = 0
    note: str = "none"                # written | skipped | none
    calculated_for: int | None = None  # plan version of its snapshot (a test of H)
    linked_late: bool = False         # its task was linked to H after it was calculated
    warnings: tuple[str, ...] = ()    # the engine's own warnings
    complete: int | None = None
    rows: int = 0
    checks: tuple = ()                # research_workflow.Check of its task: open or info
    n: str = ""                       # the engine's n (complete cases, or per pair)
    estimates: tuple = ()             # the engine's verified rows: (parameter, estimate, ci, p)


@dataclass(frozen=True)
class HypothesisEvidence:
    """Stage 37.0b: what the report says about one hypothesis beyond its
    text: direction and α, the analyses that test it, the results of this
    report that do, the researcher's recorded decisions and the checks that
    are open or disclosed. Built by :func:`hypothesis_evidence` from saved
    output and records only."""

    number: int
    direction: str = "two-sided"
    alpha: float = 0.05
    analyses: tuple[AnalysisLine, ...] = ()
    results: tuple[EvidenceResult, ...] = ()
    others: int = 0                   # results of its analyses not in this report
    records: tuple[dict, ...] = ()    # its protocol records, oldest first
    history: tuple[dict, ...] = ()    # research_workflow.designation_history
    checks: tuple = ()                # research_workflow.Check: open warnings, disclosures
    plan_version: int | None = None   # the plan version the report states


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
    # Stage 37.0b: {hypothesis id: HypothesisEvidence}. Without it the
    # Hypotheses section is written exactly as before.
    evidence: dict = field(default_factory=dict)


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
    done_tasks: set[tuple[str, str]] = set()
    for result in results:
        if result.task_id:
            # Stage 37.0b (review D5): one heading per task and specification;
            # a result calculated with other variables is named by its own.
            key = (result.task_id, result.task_title)
            if key in done_tasks:
                heading = None
            else:
                done_tasks.add(key)
                heading = text(language, "task", title=result.task_title or result.title)
        else:
            heading = None
        if heading:
            items.append(Item("heading", heading))
        items.append(Item("subheading", result.title))
        when = result.created.strftime("%Y-%m-%d %H:%M") if result.created else "—"
        items.append(Item("note", text(language, "version_line", name=result.dataset or "—",
                                       rows=result.dataset_rows, title=result.title,
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


# ------------------------------------------ hypotheses and evidence (Stage 37.0b)
# Engine labels of the tests a batch of group comparisons runs (GroupFamily.method).
GROUP_TESTS = {"kruskal": "Kruskal–Wallis H", "mannwhitney": "Mann–Whitney U",
               "welch": "Welch’s independent t"}
# Options shown in the method's title or as the correction, not again as an option.
_TITLE_OPTIONS = ("method", "adjust", "two_group_method")
# Checks the hypothesis rows leave to other lines: the analyses (no task), the
# post hoc warning (added after results) and the designation history.
_COVERED_CHECKS = ("H-NO-TASK", "H-DESIGNATION-CHANGED")
RECORD_KINDS = ("deviation", "acknowledgement", "justification", "designation")


def _ui(language: str, key: str, **values) -> str:
    from workspace_text import t

    return t(language, key, **values)


def _alpha(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _one_line(value) -> str:
    """The researcher's words on one line (a list item is one line)."""
    return " ".join(str(value or "").split())


def _when(stamp) -> str:
    """A record's time (UTC, ISO) as the local date and time."""
    try:
        moment = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return str(stamp or "")[:16].replace("T", " ")
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return f"{moment:%Y-%m-%d %H:%M}"


def method_label(method: str, options: dict | None = None, result=None) -> str:
    """The English engine label of the test a result ran (``Spearman’s ρ``,
    ``Kruskal–Wallis H``), from the method key, its options and, for a batch
    of group comparisons, the test the engine chose."""
    from research_workflow import method_title

    if not method:
        return ""
    if method == "batch_groups":
        test = GROUP_TESTS.get(str(getattr(result, "method", "") or ""))
        if test:
            return test
    return method_title(method, options or {})


def calculation(language: str, method: str, options: dict | None, *, label_en: str = "",
                tests: int | None = None, correction: str = "") -> str:
    """The method and its options as the report writes them: the test, the
    number of tests and the correction of a batch (the engine's own values),
    then the other options, in the report's language."""
    from workspace_methods import METHODS
    from workspace_text import label

    if not method:
        return "—"
    options = dict(options or {})
    parts = [label(language, label_en or method_label(method, options))]
    if tests:
        parts.append(text(language, "calc.tests", count=tests))
    spec = METHODS.get(method)
    for option in (spec.options if spec is not None else ()):
        choices = dict(option.choices)
        if option.key == "adjust":
            adjust = correction or str(options.get("adjust") or "")
            if adjust:
                parts.append(text(language, "calc.correction",
                                  adjust=label(language, choices.get(adjust, adjust))))
        elif option.key not in _TITLE_OPTIONS and option.key in options:
            value = str(options[option.key])
            parts.append(f"{label(language, option.label)} = "
                         f"{label(language, choices.get(value, value))}")
    return "; ".join(parts)


def _plan_fact(language: str, value) -> str:
    """A planned or used analysis as recorded with a deviation: a method
    (``{"method", "options"}``), variables by role, or a specification."""
    from workspace_text import label

    if isinstance(value, dict) and value.get("method"):
        title = label(language, method_label(str(value["method"]), value.get("options") or {}))
        names = value.get("variables")
        return title + (f" ({', '.join(map(str, names))})" if names else "")
    if isinstance(value, dict):
        names = []
        for item in value.values():
            for name in (item if isinstance(item, (list, tuple)) else [item]):
                if str(name) not in names:
                    names.append(str(name))
        return ", ".join(names) or "—"
    return _one_line(value) or "—"


def _timing(language: str, record: dict, number: int) -> str:
    count = int(record.get("results_of_hypothesis") or 0)
    return (text(language, "timing.before", number=number) if not count else
            text(language, "timing.after", count=count, number=number))


def _priority(language: str, value) -> str:
    key = f"priority.{value or 'primary'}"
    return text(language, key) if key in TEXT["en"] else str(value)


def record_lines(evidence: HypothesisEvidence, language: str) -> list[str]:
    """Every decision recorded for the hypothesis, oldest first, with its
    reason; a withdrawn one stays, followed by its withdrawal. A designation
    changed after results without a record is listed too. Each line names
    the hypothesis, so no two lines of the report are the same."""
    number = evidence.number
    records = list(evidence.records)
    withdrawn = {r.get("supersedes"): r for r in records if r.get("kind") == "withdrawal"}
    lines = []
    for record in records:
        kind = record.get("kind")
        if kind not in RECORD_KINDS:
            continue
        detail = record.get("detail") or {}
        when, reason = _when(record.get("at")), _one_line(record.get("reason"))
        if kind == "designation":
            line = text(language, "record.designation", number=number,
                        version=record.get("plan_version") or "—",
                        runs=int(record.get("results_in_project") or 0), when=when,
                        reason=reason, **{"from": _priority(language, detail.get("from")),
                                          "to": _priority(language, detail.get("to"))})
        elif kind == "deviation" and "from" in detail and "to" in detail:
            # Stage 37.0b (S8): the plan itself changed after results.
            what = detail.get("what") if f"what.{detail.get('what')}" in TEXT["en"] else "other"
            line = text(language, "record.plan_change", number=number,
                        what=text(language, f"what.{what}"),
                        version=record.get("plan_version") or "—",
                        runs=int(record.get("results_in_project") or 0), when=when, reason=reason,
                        **{"from": _change_value(language, what, detail.get("from")),
                           "to": _change_value(language, what, detail.get("to"))})
        elif kind == "deviation":
            what = detail.get("what") if f"what.{detail.get('what')}" in TEXT["en"] else "other"
            change = ""
            if detail.get("planned") is not None and detail.get("actual") is not None:
                change = text(language, "record.planned_actual",
                              planned=_plan_fact(language, detail["planned"]),
                              actual=_plan_fact(language, detail["actual"]))
            line = text(language, "record.deviation", what=text(language, f"what.{what}"),
                        when=when, timing=_timing(language, record, number), change=change,
                        reason=reason)
        else:
            about = f"about.{record.get('check_key')}"
            line = text(language, f"record.{kind}",
                        check=text(language, about if about in TEXT["en"] else "about.other"),
                        when=when, timing=_timing(language, record, number), reason=reason)
        withdrawal = withdrawn.get(record.get("id"))
        if withdrawal is not None:
            line += " " + text(language, "record.withdrawn", when=_when(withdrawal.get("at")),
                               reason=_one_line(withdrawal.get("reason")))
        lines.append(line)
    for entry in evidence.history:
        if entry.get("changed") and entry.get("runs_before") and entry.get("record") is None:
            lines.append(text(language, "record.designation_unexplained", number=number,
                              version=entry["version"], runs=entry["runs_before"], **{
                                  "from": _priority(language, entry["previous"]),
                                  "to": _priority(language, entry["priority"])}))
    return lines


def _change_value(language: str, what: str, value) -> str:
    """A direction, α or wording as a plan change names it."""
    if what == "direction" and value in ("two-sided", "greater", "less"):
        return _ui(language, f"plan.direction.{value}")
    if what == "alpha":
        return _alpha(value)
    return "“" + _one_line(value) + "”" if value else "—"


def _review(language: str, item) -> str:
    return text(language, "review_line", reviewed=item.reviewed, total=item.assumptions,
                note=text(language, f"note.{item.note}"))


def _estimates(language: str, result: EvidenceResult) -> str:
    """The engine's verified rows as they were saved (no number is formatted
    or computed here): parameter = estimate, 95% CI, p."""
    parts = []
    for parameter, estimate, ci, p in result.estimates:
        key = "estimate_ci" if ci and ci != "Not calculated" else "estimate"
        part = text(language, key, parameter=parameter, estimate=estimate, ci=ci)
        if p and p != "Not calculated":
            part += f", p {p}"
        parts.append(part)
    return "; ".join(parts) or text(language, "no_estimate")


def _link(language: str, result: EvidenceResult, number: int) -> str:
    if result.linked_late:
        return text(language, "cell.linked_late", number=number)
    return text(language, "cell.calculated_for", number=number,
                version=result.calculated_for or "—")


def hypothesis_rows(evidence: HypothesisEvidence, hypothesis: dict, language: str) -> list[Item]:
    """The block a hypothesis gains in the Hypotheses section (Stage 37.0b):
    its direction, α and plan version; the analyses that test it (method,
    number of tests, correction, whether the latest result is current and in
    the report); each result of the report that tests it, with the engine's
    n and estimates as saved and its review; the decisions recorded with
    their reasons; the checks that are open or disclosed. Every line names
    the hypothesis. Nothing is computed and nothing says whether the
    hypothesis holds."""
    from research_workflow import check_message

    number = evidence.number
    items = [Item("note", text(language, "hyp_direction", number=number,
                               direction=_ui(language, f"plan.direction.{evidence.direction}"),
                               alpha=_alpha(evidence.alpha),
                               version=evidence.plan_version or "—"))]
    lines = []
    for analysis in evidence.analyses:
        if analysis.state == "none":
            lines.append(text(language, "tested_by_none", number=number, task=analysis.task))
            continue
        state = (text(language, "state.current") if analysis.state == "current" else
                 text(language, "state.stale", reasons="; ".join(analysis.reasons) or "—"))
        state += ", " + text(language, "state.in_report" if analysis.in_report
                             else "state.not_in_report")
        lines.append(text(language, "tested_by", number=number, task=analysis.task, state=state,
                          calculation=calculation(
                              language, analysis.method, analysis.options,
                              label_en=analysis.method_label, tests=analysis.tests,
                              correction=analysis.correction)))
    for result in evidence.results:
        lines.append(text(language, "result_line", number=number, title=result.title,
                          state=text(language, f"cell.{result.state}"),
                          link=_link(language, result, number), n=result.n or "—",
                          estimates=_estimates(language, result),
                          review=_review(language, result)))
    if lines:
        items.append(Item("list", "\n".join(lines)))
    else:
        items.append(Item("note", text(language, "not_tested", number=number)))
    if evidence.others:
        items.append(Item("note", text(language, "others", count=evidence.others,
                                       number=number)))
    records = record_lines(evidence, language)
    if records:
        items.append(Item("note", text(language, "records_title", number=number)))
        items.append(Item("list", "\n".join(records)))
    else:
        items.append(Item("note", text(language, "records_none", number=number)))
    limits = [line if line.endswith((".", "!", "?")) else line + "."
              for line in dict.fromkeys(_one_line(check_message(check, language))
                                        for check in evidence.checks)]
    if limits:
        items.append(Item("warning" if any(c.state == "open" for c in evidence.checks)
                          else "note", text(language, "limits_title", number=number,
                                            items=" ".join(limits))))
    return items


def _limitations(language: str, result: EvidenceResult) -> str:
    from research_workflow import check_message

    parts = []
    if result.state == "stale":
        parts.append(text(language, "cell.stale_reasons", reasons="; ".join(result.reasons)
                          or "—"))
    parts += [w.strip() for w in result.warnings
              if _SMALL_GROUP.search(w or "") or _UNEQUAL.search(w or "")]
    if result.complete is not None and result.rows and result.complete < result.rows:
        parts.append(text(language, "cell.missing", complete=result.complete, rows=result.rows))
    parts += [_one_line(check_message(check, language)) for check in result.checks]
    sentences = [part if part.endswith((".", "!", "?")) else part + "."
                 for part in dict.fromkeys(p.strip() for p in parts) if part]
    return " ".join(sentences) or "—"


def evidence_table(inputs: ReportInputs, language: str) -> list[Item]:
    """The editable table *Hypotheses and evidence*: one row per hypothesis
    and result of this report that tests it (a hypothesis with none has one
    row that says so). Written only when an analysis of the project tests a
    hypothesis, so a report without linked hypotheses keeps its tables and
    their numbers."""
    found = [(number, hypothesis, inputs.evidence.get(str(hypothesis.get("id") or "")))
             for number, hypothesis in enumerate(inputs.hypotheses, start=1)]
    found = [(number, h, e) for number, h, e in found if e is not None]
    if not any(e.analyses or e.results for _, _, e in found):
        return []
    rows = []
    for number, hypothesis, evidence in found:
        priority = hypothesis.get("priority") or "primary"
        name = text(language, "cell.hypothesis", number=number,
                    priority=text(language, f"priority.{priority}")
                    if f"priority.{priority}" in TEXT["en"] else priority)
        if not evidence.results:
            rows.append((name, text(language, "evidence_none"), "—", "—", "—", "—"))
            continue
        for result in evidence.results:
            source = text(language, "cell.result", title=result.title,
                          state=text(language, f"cell.{result.state}")) + "; " + _link(
                              language, result, number)
            version = " · ".join(x for x in (result.dataset, (result.dataset_sha or "")[:12]) if x)
            rows.append((name, source, version or "—",
                         calculation(language, result.method, result.options,
                                     label_en=result.method_label, tests=result.tests,
                                     correction=result.correction),
                         text(language, "cell.review", reviewed=result.reviewed,
                              total=result.assumptions,
                              note=text(language, f"note.{result.note}")),
                         _limitations(language, result)))
    return [Item("table", title=text(language, "evidence"),
                 columns=text(language, "evidence_columns"), rows=tuple(rows)),
            Item("note", text(language, "evidence_note"))]


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
            hypotheses.append(Item("note", text(language, "h0", number=number,
                                                 text=hypothesis["h0"])))
        if hypothesis.get("standing") == "added_after_results":
            post_hoc += 1
            hypotheses.append(Item("warning", text(language, "post_hoc", number=number)))
        elif hypothesis.get("standing") == "confirmatory":
            hypotheses.append(Item("note", text(language, "planned", number=number)))
        evidence = inputs.evidence.get(str(hypothesis.get("id") or ""))
        if evidence is not None:
            hypotheses += hypothesis_rows(evidence, hypothesis, language)
    table = evidence_table(inputs, language)
    if table:
        hypotheses += table
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


# --------------------------------------------- hypothesis evidence (adapter)
def _disclosed(check) -> bool:
    """A check the hypothesis rows list as a limitation: open or a disclosed
    fact; decisions already recorded are listed as records instead."""
    if check.state not in ("open", "info") or check.key in _COVERED_CHECKS:
        return False
    # Added after results (and not exploratory): the post hoc line says it.
    return not (check.key == "H-ADDED-AFTER" and check.severity == "warning")


def _assumptions(entry) -> tuple[int, int]:
    try:
        assumptions = tuple(entry.run.evidence().assumptions)
    except Exception:          # an unreadable result: nothing to review
        assumptions = ()
    return len([a for a in assumptions if a in entry.reviewed]), len(assumptions)


def _note_state(entry, task) -> str:
    if (entry.note or "").strip():
        return "written"
    skipped = ((getattr(task, "state", None) or {}).get("skipped") or ()) if task else ()
    return "skipped" if "interpretation" in skipped else "none"


def _family(entry) -> tuple[int | None, str]:
    """(tests, adjustment) of a batch result, as the engine saved them."""
    result = getattr(entry.run, "result", None)
    size = getattr(result, "family_size", None)
    tests = int(size) if isinstance(size, int) and not isinstance(size, bool) else None
    return tests, str(getattr(result, "adjustment", "") or "")


def _complete(entry) -> int | None:
    complete = (entry.provenance or {}).get("complete")
    if complete is None:
        try:
            complete = entry.run.evidence().n_complete
        except Exception:
            complete = None
    return None if complete is None else int(complete)


def _n(entry) -> str:
    """The engine's n of a result: its complete cases, or the n of each pair
    or outcome of a batch (one value when they are all the same)."""
    try:
        evidence = entry.run.evidence()
    except Exception:
        evidence = None
    if evidence is not None and evidence.n_complete is not None:
        return str(evidence.n_complete)
    rows = getattr(getattr(entry.run, "result", None), "rows", None) or ()
    values = [str(getattr(row, "n")) for row in rows
              if isinstance(getattr(row, "n", None), int)]
    if values:
        distinct = list(dict.fromkeys(values))
        return distinct[0] if len(distinct) == 1 else ", ".join(values)
    complete = _complete(entry)
    return "—" if complete is None else str(complete)


def _rows(entry) -> tuple:
    """(parameter, estimate, ci, p) of the engine's verified rows, as saved;
    the n rows are given apart."""
    try:
        rows = entry.run.evidence().rows
    except Exception:
        return ()
    skip = ("Complete observations (N)", "Original records", "N", "Missing")
    return tuple((row.parameter, row.estimate, row.ci, row.p) for row in rows
                 if row.parameter not in skip)


def hypothesis_evidence(session, project, entries=None) -> dict[str, HypothesisEvidence]:
    """{hypothesis id: HypothesisEvidence} for the project's current plan and
    the results ``entries`` of the report (default: the session's report).
    Only saved output, the plan and the protocol records are read; no
    engine runs and nothing is written."""
    import research_workflow as rw

    if project is None:
        return {}
    entries = list(session.report_entries() if entries is None else entries)
    in_report = {entry.id for entry in entries}
    current = project.plan()
    version = int(current["version"]) if current else None
    evidence = {}
    for view in rw.hypothesis_views(session, project):
        facts = view.facts
        tasks = {task.id: task for task in view.tasks}
        analyses, others = [], 0
        for task, analysis in zip(view.tasks, view.analyses):
            results = session.task_results(task.id)
            others += sum(1 for entry in results if entry.id not in in_report)
            latest = results[-1] if results else None
            if latest is None:
                analyses.append(AnalysisLine(task.title, analysis.method, dict(analysis.options),
                                             method_label(analysis.method, analysis.options)))
                continue
            tests, adjustment = _family(latest)
            reviewed, total = _assumptions(latest)
            analyses.append(AnalysisLine(
                task.title, latest.method or "", dict(latest.options or {}),
                method_label(latest.method or "", latest.options,
                             getattr(latest.run, "result", None)),
                tests, adjustment, "stale" if latest.stale_reasons else "current",
                tuple(latest.stale_reasons or ()), latest.in_report, latest.title, reviewed,
                total, _note_state(latest, task)))
        latest_ids = {(session.task_results(task_id) or [None])[-1].id
                      for task_id in tasks if session.task_results(task_id)}
        results = []
        for entry in entries:
            snapshot = (entry.provenance or {}).get("hypothesis") or {}
            mine = snapshot.get("id") == facts.id
            if not mine and entry.task_id not in tasks:
                continue
            tests, adjustment = _family(entry)
            reviewed, total = _assumptions(entry)
            checks = tuple(check for check in view.checks
                           if entry.id in latest_ids and check.task_id == entry.task_id
                           and _disclosed(check))
            results.append(EvidenceResult(
                entry.title, entry.dataset or "",
                str((entry.provenance or {}).get("dataset_sha256") or ""), entry.method or "",
                dict(entry.options or {}),
                method_label(entry.method or "", entry.options,
                             getattr(entry.run, "result", None)),
                tests, adjustment, "stale" if entry.stale_reasons else "current",
                tuple(entry.stale_reasons or ()), reviewed, total,
                _note_state(entry, tasks.get(entry.task_id) or session.task(entry.task_id)),
                int(snapshot["plan_version"]) if mine and snapshot.get("plan_version") else None,
                not mine, tuple(getattr(entry.run, "warnings", ()) or ()), _complete(entry),
                int(entry.rows or 0), checks, _n(entry), _rows(entry)))
        evidence[facts.id] = HypothesisEvidence(
            facts.number, facts.direction, facts.alpha, tuple(analyses), tuple(results), others,
            tuple(view.records), tuple(view.history),
            tuple(check for check in view.checks if _disclosed(check)), version)
    return evidence
