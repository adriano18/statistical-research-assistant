#!/usr/bin/env python3
"""Generate invented Stage 36 fixtures. NEVER use or commit real participant data.

Output: a reproducible UCLA/SACS-shaped CSV, a 2-form 60-item DOCX,
and an image-only 2-page PDF with 52 numbered items plus distractor references.

These are artificial instrument names and fictional question texts. The fixture
is intentionally unsuitable for scientific interpretation or scale validation.

Usage: python tests/fixtures/stage36/generate_fixtures.py --out-dir .stage36-fixtures
Dependencies for developers/CI: python-docx, Pillow. No end-user install needed.
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
    from PIL import Image, ImageDraw, ImageFont

    def choose_font(size: int):
        for candidate in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "DejaVuSans.ttf",
            "Arial.ttf",
        ):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=".stage36-fixtures")
    args = parser.parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in (create_csv(out_dir), create_docx(out_dir), create_scan_pdf(out_dir)):
        print(f"{path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
