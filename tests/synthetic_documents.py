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


# ----------------------------- answer choices repeated after EVERY item (#20)
# Layout of coping-inventory forms: item number | wrapped prompt | four cells,
# each printing a code with a small (often wrapped) uppercase label. All
# wording below is invented; it is not taken from any published inventory.
COPING_LABELS = ("NOT AT ALL", "A SMALL AMOUNT", "A FAIR AMOUNT", "VERY MUCH")
COPING_LABELS_LV = ("NEMAZ", "NEDAUDZ", "DIEZGAN DAUDZ", "ĻOTI DAUDZ")
COPING_LABELS_RU = ("СОВСЕМ НЕТ", "НЕМНОГО", "ДОВОЛЬНО МНОГО", "ОЧЕНЬ МНОГО")
COPING_TITLE = "SYNTHETIC COPING STYLES CHECKLIST"
_COPE_ACTIONS = ("sorting", "postponing", "sketching", "rearranging", "discussing",
                 "imagining", "listing")
_COPE_OBJECTS = ("invented garden chores", "fictional weekend errands",
                 "made-up travel plans", "pretend museum visits")
_COPE_ACTIONS_LV = ("kārtoju", "atliku", "zīmēju", "pārkārtoju", "apspriedu", "iztēlojos",
                    "uzskaitīju")
_COPE_OBJECTS_LV = ("izdomātus dārza darbus", "fiktīvas nedēļas nogales lietas",
                    "izdomātus ceļojumu plānus", "šķietamus muzeja apmeklējumus")
_COPE_ACTIONS_RU = ("сортировал", "откладывал", "набрасывал", "переставлял", "обсуждал",
                    "представлял", "перечислял")
_COPE_OBJECTS_RU = ("вымышленные садовые дела", "выдуманные поручения выходного дня",
                    "придуманные планы поездок", "мнимые походы в музей")
#: Invented scoring recipe printed at the end (review-only evidence in tests).
COPING_STYLES = (
    ("Synthetic planning style", (2, 5, 9, 12, 16, 19, 23, 26)),
    ("Synthetic sharing style", (1, 4, 7, 10, 13, 17, 20, 24, 27)),
    ("Synthetic distancing style", (3, 6, 8, 11, 14, 15, 18, 21, 22, 25, 28)),
)


def coping_statements(count: int = 28, *, language: str = "en") -> list[str]:
    """Deterministic invented coping-style statements (some long enough to wrap)."""
    items = []
    for n in range(count):
        if language == "lv":
            action = _COPE_ACTIONS_LV[n % len(_COPE_ACTIONS_LV)]
            obj = _COPE_OBJECTS_LV[(n // len(_COPE_ACTIONS_LV)) % len(_COPE_OBJECTS_LV)]
            text = f"Izdomātajā nedēļā es {action} {obj} ({n + 1}. situācija)"
            text += ", lai fiktīvais grafiks šķistu vieglāks." if n % 3 == 0 else "."
        elif language == "ru":
            action = _COPE_ACTIONS_RU[n % len(_COPE_ACTIONS_RU)]
            obj = _COPE_OBJECTS_RU[(n // len(_COPE_ACTIONS_RU)) % len(_COPE_OBJECTS_RU)]
            text = f"В выдуманную неделю я {action} {obj} (ситуация {n + 1})"
            text += ", чтобы вымышленный график казался проще." if n % 3 == 0 else "."
        else:
            action = _COPE_ACTIONS[n % len(_COPE_ACTIONS)]
            obj = _COPE_OBJECTS[(n // len(_COPE_ACTIONS)) % len(_COPE_OBJECTS)]
            text = f"During the invented week I kept {action} {obj} (situation {n + 1})"
            text += (", so that the fictional schedule felt easier to follow." if n % 3 == 0
                     else ".")
        items.append(text)
    return items


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width) or [text]


def _label_lines(label: str) -> list[str]:
    """Wrap a short label like a narrow answer cell does (two lines)."""
    words = label.split()
    if len(words) < 2:
        return [label]
    cut = (len(words) + 1) // 2
    return [" ".join(words[:cut]), " ".join(words[cut:])]


def coping_scoring_lines(language: str = "en") -> list[str]:
    word = {"en": "Items", "lv": "jautājumi", "ru": "пункты"}[language]
    tail = {"en": "mean of the {n} marked codes, range 1–4",
            "lv": "vidējais no {n} atzīmētajiem kodiem, diapazons 1–4",
            "ru": "среднее из {n} отмеченных кодов, диапазон 1–4"}[language]
    lines = []
    for name, numbers in COPING_STYLES:
        listed = ", ".join(map(str, numbers))
        lines.append(f"{name} ({word} {listed}, {tail.format(n=len(numbers))}):")
    lines.append("Invented styles: compute the mean of the listed items; a sum over all items "
                 "is not defined.")
    return lines


def _mark(number: int, numbering: str) -> str:
    """Item number as printed; DejaVu Sans has circled digits ① … ⑩ only."""
    return chr(0x2460 + number - 1) if numbering == "circled" and number <= 10 else str(number)


def coping_text_lines(*, labels=COPING_LABELS, language: str = "en", count: int = 28,
                      per_page: int = 16, numbering: str = "standalone", missing=(),
                      scoring: bool = True, same_line_codes: bool = False,
                      overrides=None) -> list[tuple[int, str]]:
    """The text-layer reading order of :func:`coping_text_pdf` as ``(page, line)``.

    ``same_line_codes`` prints "1 NOT AT ALL" on one line; ``overrides`` maps
    an item number to the labels printed after THAT item only.
    """
    statements = coping_statements(count, language=language)
    numbers = [n for n in range(1, count + 1) if n not in set(missing)]
    rows = [(1, COPING_TITLE), (1, "PARTICIPANT NAME DATE RATER"), (1, "Complete online"),
            (1, "Read each statement and circle the number that shows how often you used it.")]
    for index, number in enumerate(numbers):
        page = 1 + index // per_page
        prompt = _wrap(statements[number - 1], 52)
        if numbering == "inline":
            prompt[0] = f"{number} {prompt[0]}"
        else:
            rows.append((page, _mark(number, numbering)))
        rows += [(page, text) for text in prompt]
        printed = (overrides or {}).get(number, labels)
        for code, label in zip(("1", "2", "3", "4"), printed):
            if same_line_codes:
                rows.append((page, f"{code} {label}"))
            else:
                rows.append((page, code))
                rows += [(page, part) for part in _label_lines(label)]
    if scoring:
        last = rows[-1][0]
        rows += [(last, text) for text in coping_scoring_lines(language)]
    return rows


def coping_text_pdf(*, labels=COPING_LABELS, language: str = "en", count: int = 28,
                    per_page: int = 16, numbering: str = "standalone",
                    letter_spaced: bool = False, missing=(), scoring: bool = True,
                    gap_em: float = 0.17) -> bytes:
    """Text-layer PDF: number, wrapped prompt and four labelled answer cells per item.

    Drawing order is item number, prompt lines, then code and label lines of
    every cell, so a text layer reads "1 / prompt / 1 / NOT AT / ALL / 2 …".
    ``numbering``: "standalone" (number left of the prompt), "inline" (on the
    prompt's first line), "circled" (① … ⑩ glyphs, then plain numbers) or
    "ring" (a number drawn inside a circle shape). ``letter_spaced`` draws the longest word of each
    first prompt line as two text objects ``gap_em`` apart, so text
    extractors insert spurious spaces inside it.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Ellipse
    import matplotlib.pyplot as plt

    statements = coping_statements(count, language=language)
    numbers = [n for n in range(1, count + 1) if n not in set(missing)]
    columns = (0.555, 0.665, 0.775, 0.885)
    stream = BytesIO()
    with PdfPages(stream) as pdf:
        for start in range(0, len(numbers), per_page):
            figure = plt.figure(figsize=(8.27, 11.69))
            renderer = figure.canvas.get_renderer()

            def advance(text, size):
                artist = figure.text(0, -1, text, fontsize=size)
                extent = artist.get_window_extent(renderer).width / figure.bbox.width
                artist.remove()
                return extent

            def draw(x, y, text, size, *, split=False):
                words = text.split(" ")
                longest = max(range(len(words)), key=lambda k: len(words[k]))
                if not split or len(words[longest]) < 6:
                    figure.text(x, y, text, fontsize=size)
                    return
                cut = len(words[longest]) // 2
                first = " ".join(words[:longest] + [words[longest][:cut]])
                second = " ".join([words[longest][cut:]] + words[longest + 1:])
                figure.text(x, y, first, fontsize=size)
                gap = gap_em * size / 72 / 8.27
                figure.text(x + advance(first, size) + gap, y, second, fontsize=size)

            y = 0.95
            if start == 0:
                figure.text(0.07, y, COPING_TITLE, fontsize=13)
                y -= 0.03
                figure.text(0.07, y, "PARTICIPANT NAME", fontsize=6)
                figure.text(0.40, y, "DATE", fontsize=6)
                figure.text(0.70, y, "RATER", fontsize=6)
                figure.text(0.80, y + 0.03, "Complete online", fontsize=7)
                y -= 0.035
                figure.text(0.07, y, "Read each statement and circle the number that shows "
                            "how often you used it.", fontsize=8)
                y -= 0.035
            else:
                figure.text(0.07, y, f"{COPING_TITLE} (continued)", fontsize=9)
                y -= 0.03
            for number in numbers[start:start + per_page]:
                prompt = _wrap(statements[number - 1], 52)
                mark = _mark(number, numbering)
                if numbering == "inline":
                    prompt[0] = f"{number} {prompt[0]}"
                else:
                    figure.text(0.065, y - 0.006, mark, fontsize=7, color="#555555", ha="center")
                    if numbering == "ring":
                        figure.add_artist(Ellipse((0.065, y - 0.0045), 0.022, 0.016,
                                                  fill=False, linewidth=0.6,
                                                  transform=figure.transFigure))
                for k, text in enumerate(prompt):
                    draw(0.09, y - 0.012 * k, text, 8.5, split=letter_spaced and k == 0)
                for x, code, label in zip(columns, ("1", "2", "3", "4"), labels):
                    figure.text(x, y + 0.004, code, fontsize=11, ha="center")
                    for j, part in enumerate(_label_lines(label)):
                        figure.text(x, y - 0.006 - 0.007 * j, part, fontsize=5, ha="center")
                y -= max(0.012 * len(prompt), 0.02) + 0.022
            if start + per_page >= len(numbers) and scoring:
                y -= 0.01
                for text in coping_scoring_lines(language):
                    for part in _wrap(text, 110):
                        figure.text(0.07, y, part, fontsize=7)
                        y -= 0.016
            pdf.savefig(figure)
            plt.close(figure)
    return stream.getvalue()


def coping_scan_pages(*, labels=COPING_LABELS, count: int = 28, per_page: int = 14,
                      seed: int = 11) -> list[Image.Image]:
    """Scanned look-alike (about 200 dpi): the same item rows and labelled cells."""
    statements = coping_statements(count)
    number_font, prompt_font, code_font, label_font = font(28), font(27), font(38), font(22)
    columns = (1080, 1260, 1440, 1620)
    pages = []
    for start in range(0, count, per_page):
        image = Image.new("L", (1800, 2500), 255)
        draw = ImageDraw.Draw(image)
        y = 100
        if start == 0:
            draw.text((110, y), COPING_TITLE, font=font(40), fill=0)
            y += 70
            draw.text((110, y), "Circle one number for each statement.", font=prompt_font, fill=0)
            y += 80
        for number in range(start + 1, min(start + per_page, count) + 1):
            prompt = _wrap(statements[number - 1], 46)
            draw.text((60, y + 16), str(number), font=number_font, fill=0)
            for k, text in enumerate(prompt):
                draw.text((130, y + 36 * k), text, font=prompt_font, fill=0)
            for x, code, label in zip(columns, ("1", "2", "3", "4"), labels):
                draw.text((x - 12, y - 8), code, font=code_font, fill=0)
                for j, part in enumerate(_label_lines(label)):
                    width = draw.textlength(part, font=label_font)
                    draw.text((x - width / 2, y + 40 + 25 * j), part, font=label_font, fill=0)
            y += max(36 * len(prompt), 96) + 50
            draw.line([(50, y - 24), (1750, y - 24)], fill=200, width=2)
        rng = random.Random(seed + start)
        pixels = image.load()
        for _ in range(3000):
            pixels[rng.randrange(1800), rng.randrange(2500)] = rng.choice((0, 210))
        pages.append(image.filter(ImageFilter.GaussianBlur(0.4)).convert("RGB"))
    return pages


def coping_scan_pdf(**kwargs) -> bytes:
    """Image-only PDF of :func:`coping_scan_pages` (150 dpi: rendered ~1:1 for OCR)."""
    return image_pdf(*coping_scan_pages(**kwargs), resolution=150.0)


def coping_docx(*, labels=COPING_LABELS, count: int = 28, header_columns: bool = False,
                missing=()) -> bytes:
    """Native Word table: No. | Statement | four answer cells per item.

    By default every cell repeats its code and label (two paragraphs); with
    ``header_columns`` the labels are column headers and cells hold codes.
    """
    from docx import Document

    document = Document()
    document.add_paragraph(COPING_TITLE)
    document.add_paragraph("Circle the number that shows how often you used each approach.")
    numbers = [n for n in range(1, count + 1) if n not in set(missing)]
    statements = coping_statements(count)
    table = document.add_table(rows=len(numbers) + int(header_columns), cols=6)
    r = 0
    if header_columns:
        table.cell(0, 0).text = "No."
        table.cell(0, 1).text = "Statement"
        for c, label in enumerate(labels, 2):
            table.cell(0, c).text = label
        r = 1
    for number in numbers:
        table.cell(r, 0).text = str(number)
        table.cell(r, 1).text = statements[number - 1]
        for c, (code, label) in enumerate(zip(("1", "2", "3", "4"), labels), 2):
            cell = table.cell(r, c)
            cell.text = code
            if not header_columns:
                cell.add_paragraph(label)
        r += 1
    for text in coping_scoring_lines():
        document.add_paragraph(text)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()
