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
