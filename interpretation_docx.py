"""Editable, locally produced APA 7-inspired statistical report in Word.

Only a previously computed analysis snapshot is used. Numerical result tables,
headings, interpretation, citations and figure captions are editable Word text;
the plotted chart is an embedded image, replaceable but not vector-editable.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import textwrap

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

from apa_figures import (
    default_section_figure_note,
    section_embeds_figure_header,
)
from interpretation_wizard import (
    AnalysisEvidence, interpretation_summary, source_references,
)
from output_workspace import PNG_SIGNATURE


def _style(document: Document):
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11.0)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.line_spacing = 2
    normal.paragraph_format.space_after = Pt(0)

    for style_name in ("Title", "Heading 1", "Heading 2"):
        style = document.styles[style_name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(12)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.line_spacing = 2
        style.paragraph_format.space_before = Pt(10)
        style.paragraph_format.space_after = Pt(2)
        style.paragraph_format.keep_with_next = True


def _table_borders(table):
    """Use APA-style horizontal rules, no grid/vertical cell borders."""
    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom"):
        element = OxmlElement("w:" + edge)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "8")
        borders.append(element)
    for edge in ("left", "right", "insideV", "insideH"):
        element = OxmlElement("w:" + edge)
        element.set(qn("w:val"), "nil")
        borders.append(element)
    tbl_pr.append(borders)

    for cell in table.rows[0].cells:
        properties = cell._tc.get_or_add_tcPr()
        previous = properties.find(qn("w:tcBorders"))
        if previous is not None:
            properties.remove(previous)
        cell_borders = OxmlElement("w:tcBorders")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "5")
        cell_borders.append(bottom)
        properties.append(cell_borders)


def _title(document, label: str, heading: str):
    number = document.add_paragraph()
    number.paragraph_format.keep_with_next = True
    number.add_run(label).bold = True
    title = document.add_paragraph()
    title.paragraph_format.keep_with_next = True
    title.add_run(heading).italic = True


def _note(document, text: str):
    """Accept both plain note text and an existing 'Note.' prefix."""
    body = text.strip()
    if body.lower().startswith("note."):
        body = body[5:].strip()
    paragraph = document.add_paragraph()
    paragraph.add_run("Note.").italic = True
    if body:
        paragraph.add_run(" " + body)


def _figure_body(image: bytes, section: str) -> BytesIO:
    if not isinstance(image, bytes) or not image.startswith(PNG_SIGNATURE):
        raise ValueError("Report chart must be a valid PNG.")
    if len(image) > 25_000_000:
        raise ValueError("Chart exceeds the 25 MB report limit.")
    with Image.open(BytesIO(image)) as opened:
        if opened.width * opened.height > 24_000_000:
            raise ValueError("Chart is too large.")
        graphic = opened.convert("RGB").copy()
    if section_embeds_figure_header(section):
        # Legacy charts already print hard-coded "Figure 1–14" at the top
        # and notes at the bottom. Crop only reserved caption bands so the
        # Word heading and note can be edited and renumbered independently.
        y_top = int(graphic.height * .115)
        y_bottom = int(graphic.height * .89)
        if y_bottom - y_top < 50:
            raise ValueError("Chart is too short to remove embedded captions.")
        graphic = graphic.crop((0, y_top, graphic.width, y_bottom))
    output = BytesIO()
    graphic.save(output, format="PNG")
    output.seek(0)
    return output


def build_apa_docx(
    evidence: AnalysisEvidence,
    *,
    reviewed: set[str] | tuple[str, ...] = (),
    researcher_notes: str = "",
    study_title: str = "",
    figure_title: str = "",
    figure_note: str = "",
    include_original_report: bool = True,
) -> Document:
    """Create a reviewable Word document, not a claimed journal-ready manuscript."""
    if not isinstance(evidence, AnalysisEvidence):
        raise ValueError("A calculated analysis snapshot is required.")
    if len(researcher_notes) > 10_000:
        raise ValueError("Researcher interpretation is too long (limit: 10,000 characters).")
    if len(study_title) > 250 or len(figure_title) > 250 or len(figure_note) > 1000:
        raise ValueError("Report titles or figure note are too long.")
    document = Document()
    _style(document)
    document.core_properties.title = study_title.strip() or evidence.title
    document.core_properties.subject = "Draft statistical analysis / APA 7-style"
    document.core_properties.author = ""
    document.core_properties.keywords = "research statistics; working draft"

    title_paragraph = document.add_paragraph(style="Title")
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_paragraph.add_run(study_title.strip() or "Statistical Analysis Report")
    document.add_paragraph(
        "Editable APA 7-style research draft · Verify statistical assumptions "
        "and journal-specific requirements before submission."
    )
    document.add_heading("Method and research design", level=1)
    document.add_paragraph(f"Selected analysis: {evidence.method}.")
    document.add_paragraph(evidence.rationale)

    document.add_heading("Assumption and data-quality review", level=1)
    reviewed_set = set(reviewed) & set(evidence.assumptions)
    for assumption in evidence.assumptions:
        mark = "Reviewed by researcher" if assumption in reviewed_set else "Not reviewed"
        document.add_paragraph(f"{mark}: {assumption}")
    document.add_paragraph(
        "A checked item records that it was reviewed; it does not establish "
        "that the assumption is satisfied. Retain the underlying diagnostics."
    )
    if evidence.warnings:
        document.add_heading("Warnings and limitations", level=2)
        for warning in evidence.warnings:
            document.add_paragraph(warning)
    document.add_paragraph(evidence.limitation)

    document.add_heading("Results", level=1)
    document.add_paragraph(
        interpretation_summary(evidence, reviewed_set)
    )
    _title(document, "Table 1", "Verified Statistics From the Current Analysis")
    table = document.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for cell, label in zip(
        table.rows[0].cells,
        ("Statistic", "Estimate", "95% CI", "p"),
    ):
        cell.text = label
        for para in cell.paragraphs:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.line_spacing = 1
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for entry in evidence.rows:
        cells = table.add_row().cells
        for cell, value in zip(
            cells, (entry.parameter, entry.estimate, entry.ci, entry.p)
        ):
            cell.text = value
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for para in cell.paragraphs:
                para.paragraph_format.line_spacing = 1
                if cell is not cells[0]:
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in para.runs:
                    run.font.size = Pt(10)
    _table_borders(table)
    _note(
        document,
        "N and individual estimates are taken from the completed calculation "
        "object; 'Not calculated' means the quantity was not provided. "
        "Confidence intervals refer only to their labeled estimate, and "
        "a researcher's assumption review is not a model-fit test.",
    )

    if evidence.figure_png is not None:
        document.add_heading("Figure", level=1)
        _title(document, "Figure 1", figure_title.strip() or evidence.title)
        body = _figure_body(evidence.figure_png, evidence.section)
        with Image.open(body) as figure:
            ratio = figure.height / figure.width
            width = min(6.25, 6.8 / max(ratio, .1))
        body.seek(0)
        chart = document.add_paragraph()
        chart.alignment = WD_ALIGN_PARAGRAPH.CENTER
        chart.add_run().add_picture(body, width=Inches(width))
        _note(
            document, figure_note.strip() or
            default_section_figure_note(evidence.section),
        )

    document.add_heading("Researcher interpretation", level=1)
    if researcher_notes.strip():
        for line in researcher_notes.strip().splitlines():
            document.add_paragraph(line)
    else:
        document.add_paragraph(
            "[Write the substantive conclusion in the context of the "
            "hypothesis, design, effect size, uncertainty, and limitations.]"
        )

    if include_original_report:
        document.add_heading("Appendix: Original calculation output", level=1)
        document.add_paragraph(
            "The following is the original application output, retained "
            "without editing or additional numerical interpretation."
        )
        for line in evidence.source_report.splitlines():
            if line.strip():
                document.add_paragraph(line)

    document.add_heading("References", level=1)
    for source in source_references(evidence.section):
        paragraph = document.add_paragraph(source)
        paragraph.paragraph_format.left_indent = Inches(.5)
        paragraph.paragraph_format.first_line_indent = Inches(-.5)
        paragraph.paragraph_format.line_spacing = 2

    return document


def save_apa_docx(
    path: str | Path, evidence: AnalysisEvidence, *,
    reviewed: set[str] | tuple[str, ...] = (),
    researcher_notes: str = "",
    study_title: str = "",
    figure_title: str = "",
    figure_note: str = "",
    include_original_report: bool = True,
) -> Path:
    """Write only to a user-chosen local .docx destination."""
    destination = Path(path).expanduser()
    if destination.suffix.lower() != ".docx":
        raise ValueError("Choose a .docx destination.")
    if not destination.parent.is_dir():
        raise FileNotFoundError("Destination folder does not exist.")
    document = build_apa_docx(
        evidence, reviewed=reviewed, researcher_notes=researcher_notes,
        study_title=study_title, figure_title=figure_title,
        figure_note=figure_note, include_original_report=include_original_report,
    )
    document.save(destination)
    return destination
