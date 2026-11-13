"""Table rules removed from a page image before local OCR.

A scanned questionnaire table draws a thin rule between its rows. With the
page read as one block of text (``--psm 6``), Tesseract can take a rule and
the row that touches it for one tall line and then drop that line's text
entirely: a Latvian table set in a Times-like font lost rows 29 and 42-45
this way on the packaged Windows program (Stage 36.7). Whitening the rules
first gives Tesseract only the text.

A rule is found where it is: a long, thin, nearly straight run of ink. The
search joins the one-pixel steps of a slightly rotated rule, fits the rule's
centre line and whitens only the pixels within half its thickness of that
line, so letters that touch a rule keep everything but the touching pixels.
Filled bars (thicker than a rule) and text (no run of ink is as long as a
fifth of the page) are left alone. Vertical rules are handled the same way.

The cleaned image is used only for OCR; the page shown to the researcher is
the original. A page without rules is returned unchanged, byte for byte.
"""

from __future__ import annotations

from io import BytesIO

INK = 200                 # grey level below which a pixel can belong to a rule
MIN_SHARE = 0.2           # a rule spans at least this share of the page
REACH = 3                 # rows joined when following a slightly rotated rule
MAX_THICKNESS_INCH = 0.04  # a rule is at most about 1 mm thick


def _run_lengths(mask):
    """For each True pixel, the length of its run of True pixels along the row."""
    import numpy as np

    height, width = mask.shape
    padded = np.zeros((height, width + 2), bool)
    padded[:, 1:-1] = mask
    flat = padded.ravel()
    steps = np.diff(flat.astype(np.int8))
    starts = np.flatnonzero(steps == 1) + 1
    ends = np.flatnonzero(steps == -1) + 1
    lengths = ends - starts
    out = np.zeros(flat.size, np.int32)
    if lengths.size:
        offsets = np.arange(int(lengths.sum())) - np.repeat(np.cumsum(lengths) - lengths, lengths)
        out[np.repeat(starts, lengths) + offsets] = np.repeat(lengths, lengths)
    return out.reshape(height, width + 2)[:, 1:-1]


def _horizontal_rules(ink, *, min_length: int, max_thickness: float):
    """The pixels of long, thin, nearly horizontal rules in ``ink`` (a bool image)."""
    import numpy as np
    from scipy import ndimage

    height = ink.shape[0]
    band = ink.copy()
    for k in range(1, REACH + 1):              # join the steps of a rotated rule
        band[k:] |= ink[:-k]
        band[:-k] |= ink[k:]
    long = _run_lengths(band) >= min_length
    rules = np.zeros_like(ink)
    if not long.any():
        return rules
    labels, _count = ndimage.label(long, structure=np.ones((3, 3), bool))
    for index, region in enumerate(ndimage.find_objects(labels), start=1):
        ys, xs = region
        inside = (labels[region] == index) & ink[region]
        counts = inside.sum(axis=0)
        columns = np.flatnonzero(counts)
        if columns.size < min_length:
            continue
        # The rule's centre in each column: the mean inked row there; columns
        # where a letter touches the rule are outliers of the straight line.
        rows = np.arange(ys.start, ys.stop)[:, None]
        centres = (rows * inside).sum(axis=0)[columns] / counts[columns]
        x = columns + xs.start
        slope, offset = np.polyfit(x, centres, 1)
        residual = np.abs(centres - (offset + slope * x))
        keep = residual <= max(1.5, 2 * float(np.percentile(residual, 75)))
        if keep.sum() >= min_length // 2:
            slope, offset = np.polyfit(x[keep], centres[keep], 1)
        thickness = _thickness(ink, offset, slope, x)
        if thickness > max_thickness:
            continue                            # a filled bar, not a rule
        half = thickness / 2 + 1
        # Follow the rule past the run that found it, to its real ends: a
        # stub left at the end of a rule reads as a letter or a dash.
        first = _follow(ink, offset, slope, half, int(x.min()), -1)
        last = _follow(ink, offset, slope, half, int(x.max()), +1)
        line = offset + slope * np.arange(first, last + 1)[None, :]
        top = max(0, int(np.floor(line.min() - half)))
        bottom = min(height, int(np.ceil(line.max() + half)) + 1)
        rows = np.arange(top, bottom)[:, None]
        rules[top:bottom, first:last + 1] |= np.abs(rows - line) <= half
    return rules


def _thickness(ink, offset: float, slope: float, x) -> float:
    """Median count of inked rows within ``REACH`` of the line, over columns ``x``."""
    import numpy as np

    height = ink.shape[0]
    centre = offset + slope * x
    top = max(0, int(np.floor(centre.min())) - REACH)
    bottom = min(height, int(np.ceil(centre.max())) + REACH + 1)
    rows = np.arange(top, bottom)[:, None]
    near = (np.abs(rows - centre[None, :]) <= REACH) & ink[top:bottom, x]
    return float(np.median(near.sum(axis=0)))


def _follow(ink, offset: float, slope: float, half: float, x: int, step: int, gap: int = 3) -> int:
    """The last column, going ``step`` from ``x``, where the rule's line still
    has ink within ``half`` rows (gaps of up to ``gap`` columns are crossed)."""
    import numpy as np

    height, width = ink.shape
    end, missing = x, 0
    while 0 <= x + step < width and missing <= gap:
        x += step
        centre = offset + slope * x
        low, high = max(0, int(np.floor(centre - half))), min(height, int(np.ceil(centre + half)) + 1)
        if low < high and ink[low:high, x].any():
            end, missing = x, 0
        else:
            missing += 1
    return end


def ruling_line_mask(gray, *, dpi: float | None = None):
    """Bool mask of the rule pixels in a grey image (a 2-D uint8 array)."""
    import numpy as np

    ink = gray < INK
    height, width = ink.shape
    max_thickness = max(3.0, (dpi or 144.0) * MAX_THICKNESS_INCH)
    rules = _horizontal_rules(ink, min_length=max(80, int(width * MIN_SHARE)),
                              max_thickness=max_thickness)
    rules |= _horizontal_rules(np.ascontiguousarray(ink.T),
                               min_length=max(80, int(height * MIN_SHARE)),
                               max_thickness=max_thickness).T
    return rules & (gray < 250)


def without_ruling_lines(png: bytes, *, dpi: float | None = None) -> bytes:
    """The page with its table rules whitened, for OCR; ``png`` itself when
    it has none (or when the image cannot be analysed)."""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(BytesIO(png)) as image:
            gray = np.asarray(image.convert("L"))
        rules = ruling_line_mask(gray, dpi=dpi)
        if not rules.any():
            return png
        cleaned = gray.copy()
        cleaned[rules] = 255
        buffer = BytesIO()
        # Lossless at any level; level 3 is the fast one (Stage 36.8).
        Image.fromarray(cleaned).save(buffer, "PNG", compress_level=3)
        return buffer.getvalue()
    except Exception:   # never lose a page to the clean-up: OCR reads the original
        return png
