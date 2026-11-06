"""Synthetic questionnaire fixtures for OCR, geometry and matrix tests.

All item wording is invented for testing and does not reproduce any
published or copyrighted scale.
"""

from __future__ import annotations

from io import BytesIO
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

def _matplotlib_font() -> str:
    """DejaVu Sans shipped with matplotlib: identical glyphs on every OS."""
    import os
    import matplotlib

    return os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")


FONT_NAMES = (
    _matplotlib_font(), "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

LIKERT_ITEMS = (
    "I felt calm during the synthetic week.",
    "Synthetic tasks felt manageable for me.",
    "I could rely on fictional colleagues.",
    "My invented schedule felt predictable.",
)
FREQUENCY_LABELS = ("Never", "Rarely", "Sometimes", "Often", "Always")


def font(size: int):
    for name in FONT_NAMES:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def questionnaire_image(
    items=LIKERT_ITEMS, labels=FREQUENCY_LABELS, codes=("0", "1", "2", "3", "4"),
    *, size=(1700, 2200), title="Synthetic Weekly Experience Form",
    skew: float = 0.0, noise: bool = True, wrap_second: bool = False,
    seed: int = 7,
) -> Image.Image:
    """Render a matrix questionnaire like a 200-dpi grayscale scan."""
    width, height = size
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    big, normal = font(44), font(34)
    draw.text((120, 120), title, font=big, fill=0)
    draw.text((120, 210), "Circle one number for each statement.", font=normal, fill=0)
    columns = [820 + i * 175 for i in range(len(labels))]
    for x, label in zip(columns, labels):
        draw.text((x, 330), label, font=normal, fill=0)
    y = 420
    for number, item in enumerate(items, 1):
        if wrap_second and number == 2:
            words = item.split()
            head, tail = " ".join(words[:3]), " ".join(words[3:])
            draw.text((120, y), f"{number}. {head}", font=normal, fill=0)
            draw.text((168, y + 46), tail, font=normal, fill=0)
        else:
            text = f"{number}. {item}"
            # Keep the prompt inside the prompt column.
            while draw.textlength(text, font=normal) > 680:
                text = text[:-1]
            draw.text((120, y), text, font=normal, fill=0)
        for x, code in zip(columns, codes):
            draw.text((x + 40, y), code, font=normal, fill=0)
        y += 130 if wrap_second and number == 2 else 100
    if skew:
        image = image.rotate(skew, resample=Image.BICUBIC, fillcolor=255)
    if noise:
        rng = random.Random(seed)
        pixels = image.load()
        for _ in range(width * height // 300):
            pixels[rng.randrange(width), rng.randrange(height)] = rng.choice((0, 180, 230))
        image = image.filter(ImageFilter.GaussianBlur(0.6))
    return image.convert("RGB")


def text_lines_image(lines, *, size=(1700, 1200)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    normal = font(38)
    for n, line in enumerate(lines):
        draw.text((120, 140 + 80 * n), line, font=normal, fill="black")
    return image


def image_pdf(*images: Image.Image, resolution: float = 200.0) -> bytes:
    """Image-only PDF (no text layer), like a scanner produces."""
    stream = BytesIO()
    first, *rest = images
    first.save(stream, "PDF", resolution=resolution, save_all=True, append_images=rest)
    return stream.getvalue()


def text_pdf(pages) -> bytes:
    """Digital PDF with a real text layer. ``pages`` = list of [(x, y, text)]."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt

    stream = BytesIO()
    with PdfPages(stream) as pdf:
        for entries in pages:
            figure = plt.figure(figsize=(8.27, 11.69))
            for entry in entries:
                x, y, text, *size = entry
                figure.text(x, y, text, fontsize=size[0] if size else 10)
            pdf.savefig(figure)
            plt.close(figure)
    return stream.getvalue()


def matrix_text_pdf(items=LIKERT_ITEMS, labels=FREQUENCY_LABELS,
                    codes=("0", "1", "2", "3", "4"), *, split_after=None,
                    spacing: float = 0.09, label_size: float = 8,
                    start: float = 0.55) -> bytes:
    """Text-layer matrix; optionally continue rows on a second page."""
    columns = [start + spacing * i for i in range(len(labels))]

    def header():
        return [(x, 0.80, label, label_size) for x, label in zip(columns, labels)]

    pages, current = [], [(0.08, 0.90, "Synthetic Weekly Experience Form")] + header()
    y = 0.75
    for number, item in enumerate(items, 1):
        if split_after and number == split_after + 1:
            pages.append(current)
            current, y = [(0.08, 0.90, "Synthetic form (continued)")], 0.80
        current.append((0.08, y, f"{number}. {item}"[:60], 9))
        current += [(x + 0.02, y, code) for x, code in zip(columns, codes)]
        y -= 0.05
    pages.append(current)
    return text_pdf(pages)


def docx_matrix(*, merged_header=True, missing_cell=False, multiline=False,
                numeric_row=True) -> bytes:
    """Native Word table matrix with optional merged group header."""
    from docx import Document

    document = Document()
    document.add_paragraph("Synthetic Team Climate Form")
    rows = len(LIKERT_ITEMS) + 1 + int(merged_header) + int(numeric_row)
    table = document.add_table(rows=rows, cols=1 + len(FREQUENCY_LABELS))
    r = 0
    if merged_header:
        table.cell(0, 0).text = "Statement"
        group = table.cell(0, 1).merge(table.cell(0, len(FREQUENCY_LABELS)))
        group.text = "How often during the past week?"
        r = 1
    table.cell(r, 0).text = "" if merged_header else "Statement"
    for c, label in enumerate(FREQUENCY_LABELS, 1):
        table.cell(r, c).text = label
    r += 1
    if numeric_row:
        for c in range(len(FREQUENCY_LABELS)):
            table.cell(r, c + 1).text = str(c)
        r += 1
    for n, item in enumerate(LIKERT_ITEMS, 1):
        prompt = f"{n}. {item}"
        if multiline and n == 2:
            words = prompt.split()
            prompt = " ".join(words[:3]) + "\n" + " ".join(words[3:])
        table.cell(r, 0).text = prompt
        for c in range(len(FREQUENCY_LABELS)):
            if missing_cell and n == 3 and c == 2:
                continue
            table.cell(r, c + 1).text = "○"
        r += 1
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


# ------------------------------------------------------------ True / False
_TF_SUBJECTS = ("I", "My colleagues", "Our fictional team", "My neighbours", "People around me")
_TF_VERBS = ("enjoy", "avoid", "remember", "plan", "discuss", "postpone")
_TF_OBJECTS = (
    "synthetic weekend trips", "imaginary board games", "invented garden chores",
    "fictional evening walks", "made-up cooking contests", "pretend museum visits",
)


def true_false_statements(count: int = 60) -> list[str]:
    """Deterministic invented statements (no published inventory content)."""
    items = []
    for n in range(count):
        subject = _TF_SUBJECTS[n % len(_TF_SUBJECTS)]
        verb = _TF_VERBS[(n // len(_TF_SUBJECTS)) % len(_TF_VERBS)]
        obj = _TF_OBJECTS[(n // 3) % len(_TF_OBJECTS)]
        verb = verb if subject == "I" or subject.endswith("s") or subject == "People around me" else verb + "s"
        items.append(f"{subject} {verb} {obj} number {n + 1}.")
    return items


def true_false_scan_pages(count: int = 60, per_page: int = 20, *, labels=("T", "F"),
                          row_labels: bool = True, header: bool = True,
                          title="Synthetic Everyday Habits Inventory") -> list[Image.Image]:
    """Scanned-looking pages: item text left, T / F answer columns right."""
    statements = true_false_statements(count)
    pages = []
    normal, big = font(32), font(42)
    for start in range(0, count, per_page):
        image = Image.new("L", (1700, 2200), 255)
        draw = ImageDraw.Draw(image)
        y = 120
        if start == 0:
            draw.text((110, y), title, font=big, fill=0)
            y += 80
            draw.text((110, y), "Read each statement and circle T or F.", font=normal, fill=0)
            y += 70
        if header:
            for x, label in zip((1390, 1510), labels):
                draw.text((x, y), label, font=normal, fill=0)
            y += 60
        for n in range(start, min(start + per_page, count)):
            draw.text((110, y), f"{n + 1}. {statements[n]}", font=normal, fill=0)
            if row_labels:
                for x, label in zip((1390, 1510), labels):
                    draw.text((x, y), label, font=normal, fill=0)
            y += 86
        rng = random.Random(start + 3)
        pixels = image.load()
        for _ in range(5000):
            pixels[rng.randrange(1700), rng.randrange(2200)] = rng.choice((0, 210))
        pages.append(image.filter(ImageFilter.GaussianBlur(0.5)).convert("RGB"))
    return pages


def true_false_text_pdf(count: int = 60, per_page: int = 30, *, labels=("T", "F"),
                        row_labels: bool = True, header: bool = True) -> bytes:
    statements = true_false_statements(count)
    pages = []
    for start in range(0, count, per_page):
        entries = [(0.08, 0.95, "Synthetic Everyday Habits Inventory")] if start == 0 else []
        y = 0.91
        if header:
            entries += [(0.80, y, labels[0]), (0.88, y, labels[1])]
            y -= 0.028
        for n in range(start, min(start + per_page, count)):
            entries.append((0.08, y, f"{n + 1}. {statements[n]}", 8))
            if row_labels:
                entries += [(0.80, y, labels[0], 8), (0.88, y, labels[1], 8)]
            y -= 0.028
        pages.append(entries)
    return text_pdf(pages)


def true_false_docx(count: int = 60, *, labels=("True", "False"), number_column=True,
                    row_labels=False, paragraphs=False, header_line="T F") -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph("Synthetic Everyday Habits Inventory")
    statements = true_false_statements(count)
    if paragraphs:
        document.add_paragraph(header_line)
        for n, text in enumerate(statements, 1):
            document.add_paragraph(f"{n}. {text}")
    else:
        columns = (["No."] if number_column else []) + ["Statement", *labels]
        table = document.add_table(rows=count + 1, cols=len(columns))
        for c, value in enumerate(columns):
            table.cell(0, c).text = value
        for n, text in enumerate(statements, 1):
            c = 0
            if number_column:
                table.cell(n, 0).text = str(n)
                c = 1
            table.cell(n, c).text = text if number_column else f"{n}. {text}"
            if row_labels:
                table.cell(n, c + 1).text = labels[0]
                table.cell(n, c + 2).text = labels[1]
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


# ------------------------------------------- shared 4-category frequency scales
_CONNECT_FEELINGS = ("connected", "left out", "close", "isolated", "understood")
_CONNECT_TOPICS = ("neighbours", "club members", "coworkers", "classmates")


def connectedness_statements(count: int = 20, *, revised: bool = False) -> list[str]:
    """Invented 'connectedness' statements; not items of any published scale."""
    lead = "I feel" if not revised else "How often do I feel"
    items = []
    for n in range(count):
        feeling = _CONNECT_FEELINGS[n % len(_CONNECT_FEELINGS)]
        topic = _CONNECT_TOPICS[(n // len(_CONNECT_FEELINGS)) % len(_CONNECT_TOPICS)]
        end = "?" if revised else "."
        items.append(f"{lead} {feeling} among fictional {topic} {n + 1}{end}")
    return items


ORIGINAL_ABBREVIATIONS = ("O", "S", "R", "N")
ORIGINAL_LABELS = ("Often", "Sometimes", "Rarely", "Never")
REVISED_LABELS = ("Never", "Rarely", "Sometimes", "Often")
REVISED_REVERSE = (1, 5, 6, 9, 10, 15, 16, 19, 20)


def _scale_page(title, instruction, legend, header, statements, row_tokens, *,
                start=1, footer=(), columns=(0.62, 0.70, 0.78, 0.86), size=8):
    entries = [(0.08, 0.95, title, 11)]
    y = 0.92
    for text in (instruction, legend):
        if text:
            entries.append((0.08, y, text, 8))
            y -= 0.025
    if header:
        entries += [(x, y, label, 7) for x, label in zip(columns, header)]
        y -= 0.03
    for offset, text in enumerate(statements):
        entries.append((0.08, y, f"{start + offset}. {text}", size))
        if row_tokens:
            entries += [(x + 0.01, y, token, size) for x, token in zip(columns, row_tokens)]
        y -= 0.032
    for text in footer:
        y -= 0.01
        entries.append((0.08, y, text, 8))
        y -= 0.025
    return entries


def connectedness_text_pdf(*, coded: bool = True, reverse_note: bool = True,
                           legend: bool = True, split_revised: bool = False) -> bytes:
    """Two instruments in ONE PDF: an O/S/R/N original form and a revised
    Never/Rarely/Sometimes/Often form (optionally 1-4 coded), 20 items each."""
    original = _scale_page(
        "SYNTHETIC CONNECTEDNESS INVENTORY", "Indicate how often each statement describes you.",
        "O = Often   S = Sometimes   R = Rarely   N = Never" if legend else "",
        ORIGINAL_ABBREVIATIONS, connectedness_statements(), ORIGINAL_ABBREVIATIONS,
    )
    revised_items = connectedness_statements(revised=True)
    footer = (
        ("Items 1, 5, 6, 9, 10, 15, 16, 19 and 20 are reverse scored.",)
        if reverse_note else ()
    )
    tokens = ("1", "2", "3", "4") if coded else ()
    title = "REVISED SYNTHETIC CONNECTEDNESS INVENTORY"
    instruction = "Indicate how often you feel the way described in each statement."
    if split_revised:
        pages = [
            original,
            _scale_page(title, instruction, "", REVISED_LABELS, revised_items[:10], tokens),
            _scale_page("Revised form (continued)", "", "", REVISED_LABELS,
                        revised_items[10:], tokens, start=11, footer=footer),
        ]
    else:
        pages = [original, _scale_page(title, instruction, "", REVISED_LABELS,
                                       revised_items, tokens, footer=footer)]
    return text_pdf(pages)


def connectedness_scan_pages(*, coded: bool = True) -> list[Image.Image]:
    """Scanned look-alike of the two-instrument PDF (one page each)."""
    pages = []
    specs = (
        ("SYNTHETIC CONNECTEDNESS INVENTORY", "O = Often   S = Sometimes   R = Rarely   N = Never",
         ORIGINAL_ABBREVIATIONS, connectedness_statements(), ORIGINAL_ABBREVIATIONS, ()),
        ("REVISED SYNTHETIC CONNECTEDNESS INVENTORY", "",
         REVISED_LABELS, connectedness_statements(revised=True),
         ("1", "2", "3", "4") if coded else (),
         ("Items 1, 5, 6, 9, 10, 15, 16, 19 and 20 are reverse scored.",)),
    )
    normal, big, small = font(28), font(38), font(24)
    for title, legend, header, statements, tokens, footer in specs:
        image = Image.new("L", (1700, 2300), 255)
        draw = ImageDraw.Draw(image)
        draw.text((100, 100), title, font=big, fill=0)
        y = 170
        if legend:
            draw.text((100, y), legend, font=normal, fill=0)
            y += 60
        columns = (1080, 1230, 1380, 1530)
        for x, label in zip(columns, header):
            draw.text((x, y), label, font=small, fill=0)
        y += 60
        for n, text in enumerate(statements, 1):
            draw.text((100, y), f"{n}. {text}", font=normal, fill=0)
            for x, token in zip(columns, tokens):
                draw.text((x + 20, y), token, font=normal, fill=0)
            y += 88
        for text in footer:
            draw.text((100, y + 20), text, font=normal, fill=0)
        rng = random.Random(len(title))
        pixels = image.load()
        for _ in range(4000):
            pixels[rng.randrange(1700), rng.randrange(2300)] = rng.choice((0, 210))
        pages.append(image.filter(ImageFilter.GaussianBlur(0.5)).convert("RGB"))
    return pages


def connectedness_docx(*, abbreviations: bool = True, coded_row: bool = False) -> bytes:
    """Native Word table: Statement | 4 frequency columns (+ optional code row)."""
    from docx import Document

    document = Document()
    document.add_paragraph("SYNTHETIC CONNECTEDNESS INVENTORY")
    if abbreviations:
        document.add_paragraph("O = Often   S = Sometimes   R = Rarely   N = Never")
    header = ORIGINAL_ABBREVIATIONS if abbreviations else REVISED_LABELS
    statements = connectedness_statements()
    table = document.add_table(rows=len(statements) + 1 + int(coded_row), cols=5)
    table.cell(0, 0).text = "Statement"
    for c, label in enumerate(header, 1):
        table.cell(0, c).text = label
    r = 1
    if coded_row:
        for c in range(4):
            table.cell(1, c + 1).text = str(c + 1)
        r = 2
    for n, text in enumerate(statements, 1):
        table.cell(r, 0).text = f"{n}. {text}"
        for c in range(4):
            table.cell(r, c + 1).text = "○"
        r += 1
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


# ------------------------------------- import integrity: references, image pages
# The same geometry on every machine: a matplotlibrc may choose another font,
# and hinted Agg extents differ between platforms.
PINNED_STYLE = {"font.family": ["DejaVu Sans"], "text.hinting": "no_hinting", "pdf.fonttype": 3}
STRAIN_LABELS = ("Almost never", "Sometimes", "Often", "Usually")
_STRAIN_SUBJECTS = ("Fictional neighbours", "Synthetic coworkers", "Pretend classmates",
                    "Made-up relatives", "Sample club members")
_STRAIN_FEELINGS = ("rested", "hurried", "calm", "under pressure", "cheerful", "tense")
_STRAIN_WEEKS = ("one", "two", "three", "four", "five", "six", "seven")
# Invented bibliography entries in common citation shapes (author list,
# year in parentheses, et al., volume (issue) pages, DOI).
FICTIONAL_CITATIONS = (
    ("1. Fictional, A., & Placeholder, B. (2001). Invented strain in synthetic samples.",
     "Journal of Fictional Studies, 4 (2), 101–119."),
    ("2. Sample, C., et al. (2015). A made-up questionnaire for tests. "
     "Synthetic Review, 12 (3), 33–47.",),
    ("3. Example, D. (1999). Fabricated items and pretend scales. doi:10.0000/fictional.1999",),
)
SSQ_DESCRIPTION = (
    "This fictional questionnaire consists of 30 items about invented daily strain.",
    "Respondents rate each statement on a 4-point scale from 1 (almost never) to 4 (usually).",
    "The form is a synthetic test fixture, not a published instrument.",
)
SSQ_SCORING_NOTE = ("Scoring note: add the item codes; consult the fictional manual "
                    "before interpreting totals.")


def strain_statements(count: int = 30) -> list[str]:
    """Invented, distinct statements (none starts with a capital I, which
    DejaVu Sans draws as a bar that OCR reads as "|")."""
    items = []
    for n in range(count):
        subject = _STRAIN_SUBJECTS[(n // len(_STRAIN_FEELINGS)) % len(_STRAIN_SUBJECTS)]
        text = f"{subject} leave me feeling {_STRAIN_FEELINGS[n % len(_STRAIN_FEELINGS)]}"
        if count > 30:
            text += f" in synthetic week {_STRAIN_WEEKS[n // 30]}"
        items.append(text + ".")
    return items


def _pdf_pages(*draw_page) -> bytes:
    """One A4 page per callable ``draw(figure)``; pinned fonts and metrics."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt

    stream = BytesIO()
    with matplotlib.rc_context(PINNED_STYLE), PdfPages(stream) as pdf:
        for draw in draw_page:
            figure = plt.figure(figsize=(8.27, 11.69))
            draw(figure)
            pdf.savefig(figure)
            plt.close(figure)
    return stream.getvalue()


def _place_image(figure, image: Image.Image, box) -> None:
    """Embed ``image`` as a raster XObject inside ``box`` (figure fractions)."""
    import numpy as np

    axes = figure.add_axes(box)
    axes.imshow(np.asarray(image.convert("RGB")), interpolation="none")
    axes.axis("off")


def strain_table_image(statements=None, labels=STRAIN_LABELS, *, dpi: int = 150) -> Image.Image:
    """The item matrix as a raster table (matplotlib text, rendered to PNG):
    numbered statements and one row of 1–4 codes under shared labels."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    statements = list(statements or strain_statements(30))
    columns = (0.60, 0.72, 0.83, 0.92)
    stream = BytesIO()
    with matplotlib.rc_context(PINNED_STYLE):
        figure = plt.figure(figsize=(7.4, 0.6 + 0.24 * len(statements)), dpi=dpi)
        step = 0.24 / (0.6 + 0.24 * len(statements))
        y = 1 - 0.3 / (0.6 + 0.24 * len(statements))
        for x, label in zip(columns, labels):
            figure.text(x, y, label, fontsize=9, ha="center")
        for number, text in enumerate(statements, 1):
            y -= step
            figure.text(0.02, y, f"{number}.", fontsize=9)
            figure.text(0.07, y, text, fontsize=9)
            for x, code in zip(columns, "1234"):
                figure.text(x, y, code, fontsize=9, ha="center")
        figure.savefig(stream, format="png", dpi=dpi, facecolor="white")
        plt.close(figure)
    return Image.open(BytesIO(stream.getvalue())).convert("RGB")


def _citation_entries(start_y: float, *, heading: str | None, size: float = 8,
                      step: float = 0.022) -> list[tuple[float, float, str, float]]:
    entries, y = [], start_y
    if heading:
        entries.append((0.08, y, heading, size + 2))
        y -= step + 0.006
    for citation in FICTIONAL_CITATIONS:
        for k, line in enumerate(citation):
            entries.append((0.08 if k == 0 else 0.11, y, line, size))
            y -= step
    return entries


def psq_like_pdf(*, references_heading: str | None = "References", dpi: int = 150) -> bytes:
    """A 2-page scale description in the shape of Issue #31 (all invented).

    Page 1: text only — a fictional title and a description that states 30
    items and a 4-point 1–4 scale. Page 2: the 30-item matrix as an
    embedded RASTER image (so pypdf reports ``page.images``) and, in the
    text layer, only a header, a scoring note and a numbered bibliography.
    """
    table = strain_table_image(dpi=dpi)

    def description(figure):
        figure.text(0.08, 0.93, "Synthetic Strain Questionnaire (SSQ)", fontsize=13)
        for k, line in enumerate(SSQ_DESCRIPTION):
            figure.text(0.08, 0.88 - 0.025 * k, line, fontsize=9)

    def form(figure):
        figure.text(0.08, 0.955, "SSQ response form (synthetic)", fontsize=9)
        _place_image(figure, table, (0.05, 0.30, 0.90, 0.63))
        figure.text(0.08, 0.26, SSQ_SCORING_NOTE, fontsize=8)
        for x, y, text, size in _citation_entries(0.23, heading=references_heading):
            figure.text(x, y, text, fontsize=size)

    return _pdf_pages(description, form)


def references_only_pdf(heading: str | None = "References", *, logo: bool = False) -> bytes:
    """A reading list without any questionnaire; optional small logo image."""
    def page(figure):
        figure.text(0.08, 0.93, "Synthetic reading list", fontsize=13)
        for x, y, text, size in _citation_entries(0.88, heading=heading, size=9, step=0.024):
            figure.text(x, y, text, fontsize=size)
        if logo:  # ~1 % of the page: a header logo, not a scanned form
            mark = Image.new("RGB", (160, 80), "white")
            ImageDraw.Draw(mark).ellipse((10, 10, 150, 70), outline="black", width=6)
            _place_image(figure, mark, (0.80, 0.93, 0.12, 0.05))

    return _pdf_pages(page)


def numbered_items_pdf(count: int, *, references: bool = False, per_page: int = 30) -> bytes:
    """Text-layer form: ``count`` numbered items, ONE shared 4-point code
    legend on page 1, printed 1–4 codes on every row; optional references."""
    statements = strain_statements(count)
    columns = (0.70, 0.77, 0.84, 0.91)
    pages = []
    for start in range(0, count, per_page):
        entries, y = [], 0.95
        if start == 0:
            entries.append((0.08, y, "Synthetic Daily Strain Form", 12))
            y -= 0.03
            entries.append((0.08, y, f"This synthetic form consists of {count} items.", 8))
            y -= 0.022
            entries.append((0.08, y, "   ".join(f"{code} = {label}" for code, label
                                                in zip("1234", STRAIN_LABELS)), 8))
            y -= 0.03
        for n in range(start, min(start + per_page, count)):
            entries.append((0.08, y, f"{n + 1}. {statements[n]}", 8))
            entries += [(x, y, code, 8) for x, code in zip(columns, "1234")]
            y -= 0.028
        pages.append(entries)
    if references:
        pages.append(_citation_entries(0.93, heading="References"))
    draws = [lambda figure, entries=entries: [figure.text(x, y, t, fontsize=s)
                                              for x, y, t, s in entries]
             for entries in pages]
    return _pdf_pages(*draws)
