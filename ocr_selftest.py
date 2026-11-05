"""End-to-end OCR self-test for packaged builds (CI and support diagnostics).

Run from a packaged Windows app by setting ``SRA_OCR_SELFTEST=<result.json>``
before launching the executable, or from source::

    python ocr_selftest.py result.json [optional-scanned.pdf]

It renders a synthetic *scanned* (image-only) questionnaire, OCRs it with the
resolved engine (bundled runtime first in packaged builds), reconstructs the
matrix and writes a JSON verdict. No network access, no user documents.
"""

from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

SAMPLE_ITEMS = (
    "I felt calm during the synthetic week.",
    "Synthetic tasks felt manageable for me.",
    "I could rely on fictional colleagues.",
)
SAMPLE_LABELS = ("Never", "Rarely", "Sometimes", "Often", "Always")


def _font(size: int):
    from PIL import ImageFont

    candidates = []
    try:  # DejaVu Sans ships with matplotlib, a bundled dependency.
        import matplotlib
        candidates.append(os.path.join(
            matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf",
        ))
    except Exception:
        pass
    for name in (
        *candidates, r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
        "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def synthetic_scanned_pdf() -> bytes:
    """A grayscale, slightly noisy, image-only questionnaire page."""
    import random
    from PIL import Image, ImageDraw, ImageFilter

    image = Image.new("L", (1700, 1400), 255)
    draw = ImageDraw.Draw(image)
    normal = _font(34)
    draw.text((120, 120), "Synthetic Weekly Experience Form", font=_font(44), fill=0)
    columns = [820 + i * 175 for i in range(len(SAMPLE_LABELS))]
    for x, label in zip(columns, SAMPLE_LABELS):
        draw.text((x, 260), label, font=normal, fill=0)
    for n, item in enumerate(SAMPLE_ITEMS, 1):
        y = 350 + 100 * (n - 1)
        draw.text((120, y), f"{n}. {item}", font=normal, fill=0)
        for x, code in zip(columns, "01234"):
            draw.text((x + 40, y), code, font=normal, fill=0)
    rng = random.Random(11)
    pixels = image.load()
    for _ in range(4000):
        pixels[rng.randrange(1700), rng.randrange(1400)] = rng.choice((0, 200))
    image = image.rotate(0.7, resample=Image.BICUBIC, fillcolor=255)
    image = image.filter(ImageFilter.GaussianBlur(0.5)).convert("RGB")
    stream = BytesIO()
    image.save(stream, "PDF", resolution=200.0)
    return stream.getvalue()


def run_selftest(output: Path, sample: Path | None = None) -> int:
    started = time.monotonic()
    result: dict = {
        "ok": False, "python": sys.version.split()[0],
        "platform": platform.platform(), "app_dir": str(Path(__file__).resolve().parent),
        "executable": sys.executable, "errors": [],
    }
    try:
        from ocr_runtime import ocr_readiness, resolve_tesseract
        from ocr_layout import aggregate_confidence
        from visual_survey_review import ocr_scientific_pdf

        runtime = resolve_tesseract()
        result["origin"] = runtime.origin
        result["engine"] = str(runtime.executable)
        ready = ocr_readiness(full_hash=True, use_cache=False)
        result.update({
            "readiness": ready.summary(), "version": ready.version,
            "languages": list(ready.languages),
            "missing_languages": list(ready.missing_languages),
            "bundle_verified": ready.bundle_verified,
        })
        if not ready.available:
            result["errors"].append("engine not ready")
        if ready.missing_languages:
            result["errors"].append("missing languages: " + ", ".join(ready.missing_languages))
        if ready.bundle_verified is False:
            result["errors"].append("bundle integrity check failed")
        source = sample.read_bytes() if sample else synthetic_scanned_pdf()
        review = ocr_scientific_pdf(source, "selftest_scan.pdf", [1], "eng")
        questions = review.instruments[0].questions
        words = [w for p in review.spatial.pages for w in p.words]
        confidence = aggregate_confidence(words)
        result.update({
            "questions": [q.question["prompt"] for q in questions],
            "words": len(words), "mean_confidence": confidence.mean,
            "confidence_category": confidence.category,
            "matrices": [
                {"columns": [c.label for c in m.columns], "codes": list(m.codes),
                 "rows": len(m.rows)} for m in review.matrices
            ],
        })
        text = " ".join(result["questions"]).lower()
        if len(questions) < 3 or "synthetic" not in text:
            result["errors"].append("OCR did not recover the sample questions")
        if not review.matrices or len(review.matrices[0].columns) != 5:
            result["errors"].append("matrix reconstruction failed")
        multilingual = ocr_scientific_pdf(source, "selftest_scan.pdf", [1], "eng+lav+rus")
        result["multilingual_questions"] = len(multilingual.instruments[0].questions)
        result["ok"] = not result["errors"]
    except Exception as error:  # report everything; this is a diagnostic
        result["errors"].append(f"{type(error).__name__}: {error}")
        result["traceback"] = traceback.format_exc()[-4000:]
    result["seconds"] = round(time.monotonic() - started, 2)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0 if result["ok"] else 1


def maybe_run_from_environment() -> None:
    """Hook for the packaged app: run and exit when SRA_OCR_SELFTEST is set."""
    target = os.environ.get("SRA_OCR_SELFTEST", "").strip()
    if not target:
        return
    sample = os.environ.get("SRA_OCR_SELFTEST_PDF", "").strip()
    code = run_selftest(Path(target), Path(sample) if sample else None)
    os._exit(code)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(run_selftest(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None))
