"""Four-stage Flet interpretation assistant for the last completed analysis.

This is not an AI model: it presents verified output and asks the researcher
to review assumptions and write an editable substantive interpretation.
"""

from __future__ import annotations

import flet as ft

from interpretation_wizard import (
    AnalysisEvidence, interpretation_summary,
)
from statistical_guide import method_guide_items


LABELS = {
    "en": {
        "heading": "Interpretation wizard · Editable APA 7 Word report",
        "empty": "Run an analysis on this screen to start the interpretation wizard.",
        "progress": "Step {step} of 4",
        "steps": ("1. Method", "2. Assumptions", "3. Estimates", "4. Word report"),
        "method": "Selected method (from completed calculation)",
        "review": "Review each assumption manually. Checking a box records review, not that the assumption is satisfied.",
        "estimate": "Verified numerical output · no figures are estimated by this wizard",
        "not_structured": "Some results are only available in the original calculation report below.",
        "warnings": "Limitations and missing statistics",
        "prev": "Previous", "next": "Next",
        "doc_title": "Study/report title (editable)",
        "interpretation": "Your substantive interpretation (optional; editable)",
        "figure_title": "Figure title in Word (optional)",
        "figure_note": "Figure note in Word (optional)",
        "export": "Export editable APA 7 Word (.docx)",
        "source": "Original numerical report is included unchanged in the Word appendix.",
        "figure": "The plot is an embedded PNG (replaceable image); captions and tables are editable Word elements.",
    },
    "lv": {
        "heading": "Interpretācijas vednis · Rediģējams APA 7 Word pārskats",
        "empty": "Vispirms veiciet analīzi šajā sadaļā.",
        "progress": "{step}. solis no 4",
        "steps": ("1. Metode", "2. Pieņēmumi", "3. Novērtējumi", "4. Word pārskats"),
        "method": "Izvēlētā metode (no aprēķina)",
        "review": "Pārbaudiet pieņēmumus. Atzīme nozīmē pārbaudi, nevis pieņēmuma izpildi.",
        "estimate": "Pārbaudāmie aprēķinu rezultāti · vednis nerada jaunus skaitļus",
        "not_structured": "Daži rezultāti pieejami tikai sākotnējā aprēķina pārskatā.",
        "warnings": "Ierobežojumi un neaprēķinātie rādītāji",
        "prev": "Atpakaļ", "next": "Tālāk",
        "doc_title": "Pētījuma / pārskata nosaukums (rediģējams)",
        "interpretation": "Jūsu interpretācija (neobligāta; rediģējama)",
        "figure_title": "Attēla nosaukums Word dokumentā (neobligāti)",
        "figure_note": "Attēla piezīme Word dokumentā (neobligāti)",
        "export": "Eksportēt rediģējamu APA 7 Word (.docx)",
        "source": "Sākotnējais aprēķina pārskats saglabāts Word pielikumā.",
        "figure": "Grafiks ievietots kā PNG; virsraksti un tabulas ir rediģējami.",
    },
    "ru": {
        "heading": "Мастер интерпретации · Редактируемый отчёт APA 7 Word",
        "empty": "Сначала выполните анализ в этом разделе.",
        "progress": "Шаг {step} из 4",
        "steps": ("1. Метод", "2. Предпосылки", "3. Оценки", "4. Отчёт Word"),
        "method": "Метод из выполненного расчёта",
        "review": "Проверьте предпосылки самостоятельно. Отметка означает проверку, а не доказательство их выполнения.",
        "estimate": "Проверенные числовые результаты · мастер не придумывает статистику",
        "not_structured": "Часть результатов доступна только в исходном отчёте расчёта.",
        "warnings": "Ограничения и отсутствующие оценки",
        "prev": "Назад", "next": "Далее",
        "doc_title": "Название исследования / отчёта (редактируемое)",
        "interpretation": "Ваша интерпретация (необязательно; редактируемая)",
        "figure_title": "Название рисунка в Word (необязательно)",
        "figure_note": "Примечание к рисунку в Word (необязательно)",
        "export": "Экспорт в редактируемый APA 7 Word (.docx)",
        "source": "Исходный числовой отчёт включён без изменений в приложение Word.",
        "figure": "График встроен как PNG; подписи и таблицы редактируются.",
    },
}


class InterpretationWizardView:
    def __init__(self, page, *, language_getter, on_export):
        self.page = page
        self.language_getter = language_getter
        self.on_export = on_export
        self.evidence: AnalysisEvidence | None = None
        self.step = 0
        self.reviewed: set[str] = set()
        self.study_title = ""
        self.researcher_notes = ""
        self.figure_title = ""
        self.figure_note = ""
        self.step_title = ft.Text(weight="bold", size=14)
        self.step_content = ft.Column(spacing=9)
        self.previous_button = ft.Button("Previous", on_click=self.previous)
        self.next_button = ft.Button("Next", on_click=self.next)
        self.root = ft.ExpansionTile(
            title=ft.Text("Interpretation wizard · Editable APA 7 Word report"),
            expanded=False,
            controls=[
                self.step_title,
                self.step_content,
                ft.Row(
                    controls=[self.previous_button, self.next_button],
                    wrap=True, spacing=8,
                ),
            ],
        )
        self.render()

    def _labels(self):
        code = self.language_getter() or "en"
        return LABELS.get(code, LABELS["en"])

    def set_evidence(self, evidence: AnalysisEvidence | None):
        if self.evidence is not evidence:
            self.evidence = evidence
            self.step = 0
            self.reviewed = set()
            self.researcher_notes = ""
            self.study_title = ""
            self.figure_title = ""
            self.figure_note = ""
        self.render()

    def previous(self, e=None):
        self._capture()
        self.step = max(0, self.step - 1)
        self.render()
        self.page.update()

    def next(self, e=None):
        self._capture()
        self.step = min(3, self.step + 1)
        self.render()
        self.page.update()

    def _capture(self):
        if self.step != 3 or self.evidence is None:
            return
        for name in ("study_title", "researcher_notes", "figure_title", "figure_note"):
            control = getattr(self, "_" + name, None)
            if control is not None:
                setattr(self, name, control.value or "")

    async def _export(self, e):
        if self.evidence is None:
            return
        self._capture()
        await self.on_export(
            self.evidence, set(self.reviewed), self.study_title,
            self.researcher_notes, self.figure_title, self.figure_note,
        )

    def _mark_reviewed(self, assumption: str, checked: bool):
        if checked:
            self.reviewed.add(assumption)
        else:
            self.reviewed.discard(assumption)

    def render(self):
        labels = self._labels()
        self.root.title.value = labels["heading"]
        self.step_title.value = (
            labels["progress"].format(step=self.step + 1)
            + (" · " + labels["steps"][self.step] if self.evidence else "")
        )
        self.previous_button.content = labels["prev"]
        self.next_button.content = labels["next"]
        self.previous_button.disabled = self.evidence is None or self.step == 0
        self.next_button.disabled = self.evidence is None or self.step == 3
        controls = []
        item = self.evidence
        if item is None:
            controls.append(ft.Text(labels["empty"], size=12, color="#61728A"))
        elif self.step == 0:
            controls.extend([
                ft.Text(labels["method"], weight="bold"),
                ft.Text(item.method, size=18, weight="bold", color="#2755A1"),
                ft.Text(item.rationale, selectable=True),
                ft.Text(item.limitation, color="#9A4D25", selectable=True),
            ])
            guide = method_guide_items(item.section, self.language_getter())
            controls.extend(
                ft.Text(f"{entry['symbol']}: {entry['explanation']}",
                        selectable=True, size=12)
                for entry in guide[:3]
            )
        elif self.step == 1:
            controls.append(ft.Text(labels["review"], color="#526581", size=12))
            for assumption in item.assumptions:
                checkbox = ft.Checkbox(
                    label=assumption, value=assumption in self.reviewed,
                    on_change=lambda e, key=assumption: self._mark_reviewed(
                        key, bool(e.control.value),
                    ),
                )
                controls.append(checkbox)
            controls.append(ft.Text(
                f"{len(self.reviewed)} / {len(item.assumptions)}",
                color="#2755A1",
            ))
        elif self.step == 2:
            controls.append(ft.Text(labels["estimate"], weight="bold", size=12))
            if not item.has_structured_values:
                controls.append(ft.Text(labels["not_structured"], color="#9A4D25"))
            table = ft.DataTable(
                columns=[
                    ft.DataColumn(label=ft.Text(title)) for title in
                    ("Statistic", "Estimate", "95% CI", "p")
                ],
                rows=[
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(text, selectable=True))
                        for text in (row.parameter, row.estimate, row.ci, row.p)
                    ])
                    for row in item.rows
                ],
            )
            controls.append(ft.Row(controls=[table], scroll=ft.ScrollMode.AUTO))
            controls.append(ft.Text(labels["warnings"], weight="bold"))
            controls.extend(
                ft.Text(warning, size=12, color="#975321", selectable=True)
                for warning in item.warnings
            )
        else:
            self._study_title = ft.TextField(
                label=labels["doc_title"], width=560,
                value=self.study_title,
            )
            self._researcher_notes = ft.TextField(
                label=labels["interpretation"], width=800, multiline=True,
                min_lines=3, max_lines=8, value=self.researcher_notes,
            )
            self._figure_title = ft.TextField(
                label=labels["figure_title"], width=560,
                value=self.figure_title,
            )
            self._figure_note = ft.TextField(
                label=labels["figure_note"], width=800,
                multiline=True, min_lines=2, max_lines=4,
                value=self.figure_note,
            )
            controls.extend([
                ft.Text(
                    interpretation_summary(
                        item, self.reviewed, self.researcher_notes
                    ),
                    size=12, selectable=True,
                ),
                self._study_title, self._researcher_notes,
                self._figure_title, self._figure_note,
                ft.Text(labels["source"], size=12, color="#526581"),
                ft.Text(labels["figure"], size=12, color="#526581"),
                ft.Button(labels["export"], on_click=self._export),
            ])
        self.step_content.controls = controls

    def update_language(self):
        self._capture()
        self.render()
