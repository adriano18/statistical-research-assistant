#!/usr/bin/env python3
"""Generate invented Stage 36 fixtures. NEVER use or commit real participant data.

Output: a reproducible UCLA/SACS-shaped CSV, a 2-form 60-item DOCX,
and an image-only 2-page PDF with 52 numbered items plus distractor references.

These are artificial instrument names and fictional question texts. The fixture
is intentionally unsuitable for scientific interpretation or scale validation.

Usage: python tests/fixtures/stage36/generate_fixtures.py --out-dir .stage36-fixtures
Dependencies for developers/CI: python-docx, Pillow, matplotlib (for its bundled
fonts). No end-user install needed.

The scans are drawn with fonts that matplotlib ships (DejaVu, STIX), never
with the fonts of the computer: the same fixture on Linux and Windows. Before
36.7 the Windows runner drew the Latvian table in Times New Roman, so the
packaged-EXE journey read a different document than the Linux tests did.
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

COLUMNS = [
    "Code", "Age", "Sex", "UCLA", "AssertiveAction",
    "SocialJoining", "SeekingSocialSupport", "CautiousAction",
    "InstinctiveAction", "Avoidancen", "IndirectAction",
    "AntisocialAction", "UCLA_Level",
]
SCALES = COLUMNS[4:12]
SEED = 360612


def bundled_font(name: str, size: int):
    """A TrueType font shipped with matplotlib: identical on every platform."""
    import matplotlib
    from PIL import ImageFont

    return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name), size)


def create_csv(out_dir: Path) -> Path:
    rnd = random.Random(SEED)
    # Exact fabricated group sizes exercise highly imbalanced-group warnings.
    levels = [1] * 3 + [2] * 47 + [3] * 5
    rnd.shuffle(levels)
    ages = [rnd.randint(18, 30) for _ in range(50)] + [
        rnd.randint(31, 39) for _ in range(5)
    ]
    rnd.shuffle(ages)
    path = out_dir / "synthetic_ucla_sacs_55.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        for i, (level, age) in enumerate(zip(levels, ages), 1):
            score = {
                1: rnd.randint(36, 39),
                2: rnd.randint(40, 59),
                3: rnd.randint(60, 69),
            }[level]
            row = {
                "Code": f"fictional_{i:03d}",
                "Age": age,
                "Sex": rnd.choice([0, 1]),
                "UCLA": score,
                "UCLA_Level": level,
            }
            for j, name in enumerate(SCALES):
                # Synthetic bounded scores with nonidentical distributions.
                row[name] = min(45, max(8, int(round(
                    22 + 0.15 * (score - 50) * ((j % 3) - 1)
                    + rnd.gauss(0, 5.5)
                ))))
            writer.writerow(row)
    return path


def create_docx(out_dir: Path) -> Path:
    from docx import Document

    doc = Document()
    doc.add_heading("FICTIONAL COPING CHECKLIST — TEST FIXTURE ONLY", 0)
    doc.add_paragraph("This file contains invented text and no validated instrument.")

    for form_idx, form in enumerate(("GENERAL", "SITUATIONAL")):
        doc.add_heading(f"SYNTHETIC FORM: {form}", level=1)
        doc.add_paragraph(
            f"Select one category: 1 Never / 2 Rarely / 3 Sometimes / 4 Often. "
            f"Only use the {form.lower()} form you explicitly select."
        )
        table = doc.add_table(rows=1 if form_idx == 0 else 0, cols=5)
        if form_idx == 0:
            for cell, value in zip(table.rows[0].cells, ["Invented prompt", "1", "2", "3", "4"]):
                cell.text = value
        for i in range(1, 61):
            cells = table.add_row().cells
            cells[0].text = (
                f"{i}. In an invented {form.lower()} scenario {i}, "
                f"I evaluated a fictional option before responding."
            )
            for j in range(1, 5):
                cells[j].text = str(j)

    doc.add_heading("METADATA — NOT QUESTIONS", level=1)
    doc.add_paragraph("Fifteen fictional subscales, each with four invented items:")
    for idx in range(15):
        ids = [idx * 4 + n for n in range(1, 5)]
        doc.add_paragraph(f"Dimension {idx+1}: items {', '.join(map(str, ids))}.")
    doc.add_heading("REFERENCES — NOT QUESTIONS", level=1)
    doc.add_paragraph("1. Imaginary Author (2099). Fictional testing manual.")
    doc.add_paragraph("2. Invented Editor (2098). Synthetic methods article.")
    target = out_dir / "synthetic_cope_two_forms_60.docx"
    doc.save(target)
    return target


def create_scan_pdf(out_dir: Path) -> Path:
    from PIL import Image, ImageDraw

    def choose_font(size: int):
        return bundled_font("DejaVuSans.ttf", size)

    pages = []
    for page in (0, 1):
        im = Image.new("RGB", (1240, 1754), "white")
        draw = ImageDraw.Draw(im)
        title_font, body_font = choose_font(27), choose_font(20)
        draw.text((65, 55), "SYNTHETIC SACS-LIKE QUESTIONNAIRE", font=title_font, fill="black")
        draw.text((65, 103), f"Page {page+1} of 2 | Not a validated instrument", font=body_font, fill="black")
        draw.text((65, 160), "Fictional statements only", font=body_font, fill="black")
        draw.text((920, 160), "1   2   3   4   5", font=body_font, fill="black")
        for local in range(26):
            idx = page * 26 + local + 1
            y = 205 + local * 47
            draw.line((65, y - 8, 1170, y - 8), fill="#CCCCCC", width=1)
            draw.text((65, y), f"{idx}. Invented coping action {idx} in a made-up situation.", font=body_font, fill="black")
            draw.text((920, y), "1   2   3   4   5", font=body_font, fill="black")
        if page == 1:
            draw.text((65, 1500), "REFERENCES — not questionnaire items", font=body_font, fill="black")
            draw.text((65, 1540), "1. Fictional Author (2099) — test note only.", font=body_font, fill="black")
            draw.text((65, 1575), "2. Fictional Editor (2098) — test note only.", font=body_font, fill="black")
        pages.append(im)
    target = out_dir / "synthetic_sacs_scanned_52.pdf"
    pages[0].save(target, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return target


# --------------------------------------------------------------------------
# Structural variants added in Stage 36.0. They reproduce the layouts that
# defeated the importer on the owner's private documents, with wholly
# invented text: no wording, labels or scoring of any real instrument.

UNNUMBERED_FORMS = (
    # (form name, its own response options, header row or None)
    ("GENERAL", ("Hardly ever", "Now and then", "Fairly often", "Very often"),
     ("Invented statement", "Hardly ever", "Now and then", "Fairly often", "Very often")),
    ("SITUATIONAL", ("Not at all", "Slightly", "Moderately", "Strongly"), None),
)


def create_docx_unnumbered(out_dir: Path) -> Path:
    """Two 60-item table forms whose cells carry NO item numbers.

    Like the owner's two-form coping document: a method description, a
    first table of 61 rows (header + 60 items) and a second table of 60
    rows, 5 columns each; each form has its own response options; a
    scoring key (15 dimensions x 4 items) and numbered references follow.
    """
    from docx import Document

    doc = Document()
    doc.add_heading("FICTIONAL STRAIN-HANDLING INVENTORY — TEST FIXTURE ONLY", 0)
    doc.add_paragraph("Method notes: this invented inventory has two forms. The general form asks "
                      "about usual reactions; the situational form asks about one invented event. "
                      "Nothing here is a validated instrument.")
    for form, options, header in UNNUMBERED_FORMS:
        doc.add_heading(f"INVENTORY FORM: {form}", level=1)
        doc.add_paragraph("Answer every statement with one of: " + "; ".join(
            f"{code} = {label}" for code, label in enumerate(options, start=1)) + ".")
        table = doc.add_table(rows=1 if header else 0, cols=5)
        if header:
            for cell, value in zip(table.rows[0].cells, header):
                cell.text = value
        for i in range(1, 61):
            cells = table.add_row().cells
            wording = (f"In this invented {form.lower()} case {i} I would compare imaginary "
                       f"choices calmly")
            if i % 7 == 0:
                wording += " and ask a fictional colleague before deciding anything"
            cells[0].text = wording + "."
            for j in range(1, 5):
                cells[j].text = str(j)
    doc.add_heading("SCORING KEY — METADATA, NOT QUESTIONS", level=1)
    doc.add_paragraph("Fifteen invented dimensions; each dimension sums four statements.")
    for idx in range(15):
        ids = [idx + 1 + 15 * n for n in range(4)]
        doc.add_paragraph(f"Dimension {idx + 1} (invented): statements {', '.join(map(str, ids))}.")
    doc.add_heading("REFERENCES — NOT QUESTIONS", level=1)
    doc.add_paragraph("1. Imaginary Author, A. (2099). An invented handbook. Nowhere Press.")
    doc.add_paragraph("2. Invented Editor, B. (2098). Synthetic forms in testing. Fictional Journal, 1, 1-2.")
    target = out_dir / "synthetic_cope_two_forms_60_unnumbered.docx"
    doc.save(target)
    return target


LV_LEGEND = ("1- gandrīz nekad", "2- reti", "3- dažkārt", "4- bieži", "5- gandrīz vienmēr")
LV_VERBS = ("rūpīgi apsveru", "ātri pieņemu", "lūdzu padomu par", "atlieku", "pārrunāju",
            "meklēju citu skatu uz", "pierakstu", "nesteidzīgi vērtēju")
LV_OBJECTS = ("izdomāto uzdevumu", "šķietamo problēmu", "neparastu lēmumu", "kopīgu plānu",
              "gaidāmo pārbaudījumu", "sīku neveiksmi")


def _lv_statement(index: int) -> str:
    verb = LV_VERBS[index % len(LV_VERBS)]
    obj = LV_OBJECTS[(index * 5) % len(LV_OBJECTS)]
    text = f"Izdomātā situācijā Nr. {index} es {verb} {obj}"
    if index % 4 == 1:
        # Long statements wrap to a second line, as in the scanned original.
        text += ", kamēr pārējie dalībnieki vēl gaida ilgāku laiku un nemaina savas domas"
    return text + "."


LV_TABLE_TYPEFACES = {
    # typeface: (font file shipped with matplotlib, fixture name)
    "dejavu": ("DejaVuSerif.ttf", "synthetic_lv_table_scan_52.pdf"),
    # A Times-like serif. Set in Times New Roman, this table lost rows in
    # OCR: the ruling lines made Tesseract skip text lines, and single-digit
    # item numbers were misread (found by the packaged Windows run, 36.7).
    "stix": ("STIXGeneral.ttf", "synthetic_lv_table_scan_52_stix.pdf"),
}


def create_lv_table_scan_pdf(out_dir: Path, typeface: str = "dejavu") -> Path:
    """Two image-only pages of a 52-item table, the way a scan looks.

    Item numbers stand in their own column, statements wrap onto a second
    line, the 1-5 response digits stand in a right column, the legend is
    repeated at the top of page 2 and stands right under an instruction
    line that opens with a bare "5", the page is slightly rotated, and a
    tick-like mark precedes some numbers (scan artifacts that OCR reads
    as quotes). Latvian letters with diacritics test the OCR language.
    ``typeface`` picks the font (``LV_TABLE_TYPEFACES``); the layout, the
    text and the noise are the same.
    """
    import random as _random

    from PIL import Image, ImageDraw

    font_file, file_name = LV_TABLE_TYPEFACES[typeface]

    def font(size: int):
        return bundled_font(font_file, size)

    rnd = _random.Random(SEED + 52)
    title, body = font(28), font(21)
    width, height = 1240, 1754
    # Stage 36.5: the statement column ends at x = 935 (digits at 965), so
    # only the 13 long statements wrap and all 26 rows of a page stay above
    # the footer. With digits at 905, page 1 drew item 26 below the bottom
    # edge (y = 1761 of 1754) and the footer over item 24: no reader could
    # find 52 items in that scan.
    left_number, left_text, digits_x, right = 120, 175, 965, 1150
    footer_top = height - 90

    def wrap(draw, text):
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = (line + " " + word).strip()
            if draw.textlength(trial, font=body) > digits_x - left_text - 30:
                lines.append(line)
                line = word
            else:
                line = trial
        return lines + [line]

    pages = []
    for page in (0, 1):
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        y = 70
        if page == 0:
            draw.text((330, y), "IZDOMĀTA APTAUJA (testa paraugs)", font=title, fill="black")
            y += 50
            draw.text((left_number, y), "Lūdzu, iedomājieties izdomātas ikdienas situācijas un "
                      "atbildiet, kā jūs parasti", font=body, fill="black")
            y += 32
            draw.text((left_number, y), "rīkotos. Izvēlieties vienu no", font=body, fill="black")
            y += 32
            # Stage 36.5: the option count opens the next instruction line, so a
            # bare "5" stands between the number and statement columns right
            # above the legend (a real scan did this); it is not item 5.
            draw.text((150, y), "5 atbilžu variantiem:", font=body, fill="black")
            y += 40
        for label in LV_LEGEND:
            draw.text((430, y), label, font=body, fill="black")
            y += 30
        y += 12
        for local in range(26):
            index = page * 26 + local + 1
            lines = wrap(draw, _lv_statement(index))
            draw.line((left_number - 15, y - 6, right, y - 6), fill="#555555", width=1)
            if index in (17, 18, 19, 20, 21, 24):
                # Scan artifact: two short strokes just left of the number.
                draw.line((left_number - 12, y + 2, left_number - 12, y + 9), fill="black", width=2)
                draw.line((left_number - 7, y + 2, left_number - 7, y + 9), fill="black", width=2)
            draw.text((left_number, y), f"{index}.", font=body, fill="black")
            for k, line in enumerate(lines):
                draw.text((left_text, y + k * 27), line, font=body, fill="black")
            shift = 7 if page == 1 and local % 3 == 1 else 0   # digits slightly off the row
            draw.text((digits_x, y + shift), "1    2    3    4    5", font=body, fill="black")
            y += 27 * len(lines) + 12
            if y > footer_top:
                raise ValueError(f"item {index} does not fit on page {page + 1}")
        if page == 1:
            y += 30
            if y + 66 + 27 > footer_top:
                raise ValueError("the references do not fit above the footer")
            draw.text((left_number, y), "Atsauces (nav aptaujas jautājumi):", font=body, fill="black")
            draw.text((left_number, y + 34), "1. Izdomāts Autors (2099). Testa piezīme.", font=body,
                      fill="black")
            draw.text((left_number, y + 66), "2. Izdomāts Redaktors (2098). Testa piezīme.",
                      font=body, fill="black")
        draw.text((470, footer_top), "Izdomāta laboratorija", font=body, fill="black")
        for _ in range(900):                                  # light, fixed speckle noise
            px, py = rnd.randrange(width), rnd.randrange(height)
            draw.point((px, py), fill="#9a9a9a")
        pages.append(image.rotate(0.35 if page == 0 else -0.3, resample=Image.BICUBIC,
                                  fillcolor="white", expand=False))
    target = out_dir / file_name
    pages[0].save(target, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=".stage36-fixtures")
    args = parser.parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in (create_csv(out_dir), create_docx(out_dir), create_scan_pdf(out_dir),
                 create_docx_unnumbered(out_dir), create_lv_table_scan_pdf(out_dir),
                 create_lv_table_scan_pdf(out_dir, "stix")):
        print(f"{path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
