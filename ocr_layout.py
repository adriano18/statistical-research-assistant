"""Spatial OCR evidence: typed words/lines/blocks, confidence and regions.

Everything in this module is pure data processing: no OCR engine, network
or UI. Coordinates are *normalized* page fractions ``(x0, y0, x1, y1)`` in
``[0, 1]`` measured from the top-left corner of the rendered page image, so
they stay aligned with the page at any zoom level or render resolution.

Two kinds of confidence are deliberately kept apart:

* **OCR confidence** is Tesseract's raw per-word recognition score
  (0–100). It says how sure the engine was about *characters*; ``None``
  means no OCR score exists (text-layer PDFs, Word files, manual text).
* **Structural review status** is a labelled heuristic about how a
  question was *reconstructed* (numbering, wrapping, options, links). It is
  never expressed as a percentage and is not calibrated.

Neither is evidence of psychometric reliability or validity.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import math
import re
from typing import Iterable

BBox = tuple[float, float, float, float]

#: Documented thresholds for the *mean raw Tesseract word confidence*.
OCR_HIGH_THRESHOLD = 85.0
OCR_REVIEW_THRESHOLD = 60.0
#: Fewer valid OCR words than this gives an explicit UNKNOWN status.
MIN_CONFIDENCE_WORDS = 2
MAX_TSV_ROWS = 200_000
MAX_WORD_CHARS = 200

OCR_CATEGORIES = ("high", "review", "low", "unknown")
OCR_CATEGORY_LABELS = {
    "high": "OCR high (mean ≥ 85)",
    "review": "OCR review (mean 60–84 or a word < 60)",
    "low": "OCR low (mean < 60)",
    "unknown": "OCR unknown (no OCR word scores)",
}
STRUCTURE_LABELS = {
    "consistent": "Structure consistent (heuristic)",
    "needs_review": "Structure needs review (heuristic)",
    "unresolved": "Structure unresolved (heuristic)",
}
PSYCHOMETRIC_NOTICE = (
    "OCR confidence measures character recognition only. It is NOT a "
    "measure of reliability, validity or correct scoring of the scale."
)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def normalize_box(box: Iterable[float]) -> BBox:
    """Validate and clamp a normalized ``(x0, y0, x1, y1)`` box."""
    values = tuple(float(v) for v in box)
    if len(values) != 4 or not all(math.isfinite(v) for v in values):
        raise ValueError("A region needs four finite coordinates.")
    x0, y0, x1, y1 = (_clamp(v) for v in values)
    if x1 - x0 < 0.002 or y1 - y0 < 0.002:
        raise ValueError("A region must have a positive width and height.")
    return (x0, y0, x1, y1)


def union_box(boxes: Iterable[BBox]) -> BBox:
    items = list(boxes)
    if not items:
        raise ValueError("Cannot combine an empty set of regions.")
    return (
        min(b[0] for b in items), min(b[1] for b in items),
        max(b[2] for b in items), max(b[3] for b in items),
    )


def box_center(box: BBox) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def box_contains(box: BBox, x: float, y: float) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def to_pixels(box: BBox, width: float, height: float) -> tuple[float, float, float, float]:
    """Convert a normalized box to ``(left, top, width, height)`` pixels."""
    return (
        box[0] * width, box[1] * height,
        (box[2] - box[0]) * width, (box[3] - box[1]) * height,
    )


@dataclass(frozen=True)
class OCRWord:
    id: str
    text: str
    box: BBox
    confidence: float | None  # raw engine score 0–100; None = not OCR
    line_id: str


@dataclass(frozen=True)
class OCRLine:
    id: str
    block_id: str
    words: tuple[OCRWord, ...]
    box: BBox

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)


@dataclass(frozen=True)
class OCRBlock:
    id: str
    lines: tuple[OCRLine, ...]
    box: BBox


@dataclass(frozen=True)
class OCRPage:
    """One page of positioned text in normalized rendered-page coordinates."""
    page_number: int
    pixel_width: int
    pixel_height: int
    blocks: tuple[OCRBlock, ...]
    source: str  # "tesseract_tsv" | "pdf_text_layer" | "plain_text"
    language: str = ""
    rotation: int = 0  # clockwise degrees applied to the rendered page
    engine: str = ""

    @property
    def lines(self) -> tuple[OCRLine, ...]:
        return tuple(line for block in self.blocks for line in block.lines)

    @property
    def words(self) -> tuple[OCRWord, ...]:
        return tuple(word for line in self.lines for word in line.words)

    @property
    def has_geometry(self) -> bool:
        return self.source != "plain_text"

    def line(self, line_id: str) -> OCRLine | None:
        for line in self.lines:
            if line.id == line_id:
                return line
        return None

    def line_at(self, x: float, y: float) -> OCRLine | None:
        """Hit-test a normalized point. Never creates question content."""
        for line in self.lines:
            if box_contains(line.box, x, y):
                return line
        return None

    def words_in(self, box: BBox) -> tuple[OCRWord, ...]:
        return tuple(
            word for word in self.words
            if box_contains(box, *box_center(word.box))
        )


def parse_tesseract_tsv(
    tsv: str, page_number: int, *, language: str = "", rotation: int = 0,
    engine: str = "",
) -> OCRPage:
    """Parse Tesseract TSV (levels 1–5) into an immutable :class:`OCRPage`.

    Rows with ``conf == -1`` are structural rows; a negative word
    confidence is stored as ``None`` (unavailable), never as zero.
    """
    if not isinstance(page_number, int) or page_number < 1:
        raise ValueError("OCR page number must be a positive integer.")
    rows = tsv.splitlines()
    if not rows or not rows[0].startswith("level\t"):
        raise ValueError("Tesseract did not return TSV layout data.")
    if len(rows) > MAX_TSV_ROWS:
        raise ValueError("OCR layout output exceeds the safety limit.")
    header = rows[0].split("\t")
    try:
        col = {name: header.index(name) for name in (
            "level", "block_num", "par_num", "line_num", "word_num",
            "left", "top", "width", "height", "conf", "text",
        )}
    except ValueError as error:
        raise ValueError("Unexpected Tesseract TSV columns.") from error
    page_w = page_h = 0
    words: dict[tuple[int, int, int], list[tuple[int, str, tuple[int, int, int, int], float | None]]] = {}
    for raw in rows[1:]:
        cells = raw.split("\t")
        if len(cells) < len(header) - 1:
            continue
        if len(cells) < len(header):
            cells.append("")
        try:
            level = int(cells[col["level"]])
            left, top = int(cells[col["left"]]), int(cells[col["top"]])
            width, height = int(cells[col["width"]]), int(cells[col["height"]])
            conf = float(cells[col["conf"]])
            block = int(cells[col["block_num"]])
            par = int(cells[col["par_num"]])
            line = int(cells[col["line_num"]])
            number = int(cells[col["word_num"]])
        except ValueError:
            continue
        if level == 1:
            page_w, page_h = max(page_w, left + width), max(page_h, top + height)
            continue
        if level != 5:
            continue
        text = " ".join(cells[col["text"]].split())[:MAX_WORD_CHARS]
        if not text or width <= 0 or height <= 0:
            continue
        score = None if conf < 0 or not math.isfinite(conf) else min(conf, 100.0)
        words.setdefault((block, par, line), []).append(
            (number, text, (left, top, width, height), score)
        )
    if page_w <= 0 or page_h <= 0:
        raise ValueError("OCR layout is missing page dimensions.")

    def norm(left, top, width, height) -> BBox:
        return (
            _clamp(left / page_w), _clamp(top / page_h),
            _clamp((left + width) / page_w), _clamp((top + height) / page_h),
        )

    blocks: dict[int, list[OCRLine]] = {}
    for (block, par, line_no), items in sorted(words.items()):
        line_id = f"p{page_number}-b{block}-r{par}-l{line_no}"
        built = tuple(
            OCRWord(f"{line_id}-w{num}", text, norm(*geometry), score, line_id)
            for num, text, geometry, score in sorted(items)
        )
        blocks.setdefault(block, []).append(OCRLine(
            line_id, f"p{page_number}-b{block}", built,
            union_box(w.box for w in built),
        ))
    return OCRPage(
        page_number, page_w, page_h,
        tuple(
            OCRBlock(f"p{page_number}-b{block}", tuple(lines),
                     union_box(l.box for l in lines))
            for block, lines in sorted(blocks.items())
        ),
        "tesseract_tsv", language, rotation % 360, engine,
    )


def page_from_plain_text(page_number: int, text: str, *, source="plain_text") -> OCRPage:
    """Wrap text without coordinates; spatial overlay is unavailable."""
    lines = []
    for n, raw in enumerate(text.splitlines(), 1):
        clean = " ".join(raw.split())
        if not clean:
            continue
        line_id = f"p{page_number}-t-l{n}"
        word = OCRWord(f"{line_id}-w1", clean[:2000], (0, 0, 1, 1), None, line_id)
        lines.append(OCRLine(line_id, f"p{page_number}-t", (word,), (0, 0, 1, 1)))
    block = OCRBlock(f"p{page_number}-t", tuple(lines), (0, 0, 1, 1))
    return OCRPage(page_number, 1, 1, (block,) if lines else (), source)


def page_from_positioned_words(
    page_number: int, words: list[tuple[str, BBox]], *, pixel_width: int,
    pixel_height: int, source: str = "pdf_text_layer", rotation: int = 0,
) -> OCRPage:
    """Group positioned words (no OCR score) into reading-order lines."""
    ordered = sorted(
        ((t, normalize_box(b)) for t, b in words if t.strip()),
        key=lambda item: (round(box_center(item[1])[1], 3), item[1][0]),
    )
    lines: list[list[tuple[str, BBox]]] = []
    for text, box in ordered:
        height = box[3] - box[1]
        if lines:
            ref = union_box(b for _, b in lines[-1])
            overlap = min(ref[3], box[3]) - max(ref[1], box[1])
            if overlap > 0.5 * min(height, ref[3] - ref[1]):
                lines[-1].append((text, box))
                continue
        lines.append([(text, box)])
    built = []
    for n, items in enumerate(lines, 1):
        items.sort(key=lambda item: item[1][0])
        line_id = f"p{page_number}-x-l{n}"
        line_words = tuple(
            OCRWord(f"{line_id}-w{i}", t[:MAX_WORD_CHARS], b, None, line_id)
            for i, (t, b) in enumerate(items, 1)
        )
        built.append(OCRLine(line_id, f"p{page_number}-x", line_words,
                             union_box(w.box for w in line_words)))
    blocks = (
        (OCRBlock(f"p{page_number}-x", tuple(built),
                  union_box(l.box for l in built)),)
        if built else ()
    )
    return OCRPage(page_number, pixel_width, pixel_height, blocks, source,
                   rotation=rotation % 360)


@dataclass(frozen=True)
class OCRConfidence:
    """Aggregate of raw OCR word scores (never a structural judgement)."""
    category: str
    mean: float | None
    minimum: float | None
    word_count: int
    scored_words: int
    low_words: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return OCR_CATEGORY_LABELS[self.category]

    def describe(self) -> str:
        if self.mean is None:
            return f"{self.label}; {self.word_count} word(s) without OCR scores"
        low = (
            f"; low words: {', '.join(self.low_words[:6])}"
            if self.low_words else ""
        )
        return (
            f"{self.label}; mean {self.mean:.1f}, min {self.minimum:.1f}, "
            f"{self.scored_words} scored word(s){low}"
        )


def aggregate_confidence(words: Iterable[OCRWord]) -> OCRConfidence:
    items = list(words)
    scores = [w.confidence for w in items if w.confidence is not None]
    if len(scores) < MIN_CONFIDENCE_WORDS:
        return OCRConfidence("unknown", None, None, len(items), len(scores))
    mean = sum(scores) / len(scores)
    low = tuple(
        w.text for w in items
        if w.confidence is not None and w.confidence < OCR_REVIEW_THRESHOLD
    )
    if mean < OCR_REVIEW_THRESHOLD:
        category = "low"
    elif mean < OCR_HIGH_THRESHOLD or low:
        category = "review"
    else:
        category = "high"
    return OCRConfidence(category, mean, min(scores), len(items), len(scores), low)


@dataclass(frozen=True)
class StructuralAssessment:
    """Heuristic reconstruction status — deliberately NOT a percentage."""
    category: str  # consistent | needs_review | unresolved
    reasons: tuple[str, ...]

    @property
    def label(self) -> str:
        return STRUCTURE_LABELS[self.category]


def assess_structure(candidate, *, expected_number: int | None,
                     linked_regions: int | None) -> StructuralAssessment:
    """Flag reconstruction risks of one ``Candidate`` from scientific import."""
    reasons = []
    unresolved = False
    question = candidate.question
    if expected_number is not None and candidate.number != expected_number:
        reasons.append(f"Numbering jumps to {candidate.number}; expected {expected_number}.")
    if getattr(candidate, "confidence", "review") == "low":
        reasons.append("Extractor marked the wording as low-certainty.")
    if any("Edited manually" in note for note in candidate.notes):
        reasons.append("Edited manually — verify against the source.")
    if any("wrapped" in note.lower() for note in candidate.notes):
        reasons.append("Wrapped text may be incomplete.")
    if question.get("kind") == "short_text":
        reasons.append("No response options were detected.")
    if len(question.get("options", [])) == 1:
        reasons.append("Only one response option was detected.")
    if linked_regions == 0:
        reasons.append("No source region is linked on the page.")
        unresolved = True
    if re.search(r"[|_~{}<>]{1,}|\s{3,}", question.get("prompt", "")):
        reasons.append("Prompt contains characters typical of OCR noise.")
    if unresolved:
        return StructuralAssessment("unresolved", tuple(reasons))
    if reasons:
        return StructuralAssessment("needs_review", tuple(reasons))
    return StructuralAssessment("consistent", ())


@dataclass(frozen=True)
class Region:
    id: str
    page: int
    box: BBox
    line_ids: tuple[str, ...] = ()
    origin: str = "detected"  # detected | manual | merged | split


@dataclass(frozen=True)
class SpatialEvidence:
    """Page geometry plus question ↔ region links (immutable)."""
    pages: tuple[OCRPage, ...]
    links: tuple[tuple[str, tuple[Region, ...]], ...]
    original_links: tuple[tuple[str, tuple[Region, ...]], ...]
    next_region: int = 1

    def page(self, number: int) -> OCRPage | None:
        for page in self.pages:
            if page.page_number == number:
                return page
        return None

    def regions(self, ref: str) -> tuple[Region, ...]:
        return dict(self.links).get(ref, ())

    def region_owner(self, region_id: str) -> str | None:
        for ref, regions in self.links:
            if any(r.id == region_id for r in regions):
                return ref
        return None

    def regions_on_page(self, number: int) -> tuple[tuple[str, Region], ...]:
        return tuple(
            (ref, region) for ref, regions in self.links for region in regions
            if region.page == number
        )

    def hit_test(self, number: int, x: float, y: float) -> tuple[str | None, Region | None]:
        """Return the question owning the smallest region at a point.

        Text outside every linked region returns ``(None, None)``; callers
        must not fabricate a question from unlinked text.
        """
        hits = [
            (ref, region) for ref, region in self.regions_on_page(number)
            if box_contains(region.box, x, y)
        ]
        if not hits:
            return None, None
        ref, region = min(
            hits, key=lambda h: (h[1].box[2]-h[1].box[0]) * (h[1].box[3]-h[1].box[1])
        )
        return ref, region

    def words_for(self, ref: str) -> tuple[OCRWord, ...]:
        found: dict[str, OCRWord] = {}
        for region in self.regions(ref):
            page = self.page(region.page)
            if page is None or not page.has_geometry:
                continue
            for word in page.words_in(region.box):
                found[word.id] = word
        return tuple(found.values())

    def confidence(self, ref: str) -> OCRConfidence:
        return aggregate_confidence(self.words_for(ref))

    def unlinked_lines(self, number: int) -> tuple[OCRLine, ...]:
        page = self.page(number)
        if page is None or not page.has_geometry:
            return ()
        used = {lid for _, r in self.regions_on_page(number) for lid in r.line_ids}
        return tuple(
            line for line in page.lines
            if line.id not in used and not any(
                box_contains(region.box, *box_center(line.box))
                for _, region in self.regions_on_page(number)
            )
        )


def question_ref(instrument: int, index: int) -> str:
    return f"{int(instrument)}:{int(index)}"


def _norm_text(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def _similar(a: str, b: str) -> float:
    a, b = _norm_text(a), _norm_text(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


LINK_THRESHOLD = 0.8


def link_candidates(review, pages: Iterable[OCRPage]) -> SpatialEvidence:
    """Conservatively link scientific-import candidates to page lines.

    A candidate is linked only when one line on its recorded page matches
    its source excerpt with similarity ≥ 0.8. Following lines are attached
    only when they occur verbatim inside the candidate's (wrapped) prompt.
    Each line is used once; unmatched candidates remain unlinked.
    """
    page_list = tuple(sorted(pages, key=lambda p: p.page_number))
    by_number = {p.page_number: p for p in page_list}
    used: set[str] = set()
    links = []
    counter = 1
    for i, instrument in enumerate(review.instruments):
        cursor: dict[int, int] = {}
        for j, candidate in enumerate(instrument.questions):
            page = by_number.get(candidate.page)
            ref = question_ref(i, j)
            if page is None or not page.has_geometry:
                links.append((ref, ()))
                continue
            lines = page.lines
            start = cursor.get(page.page_number, 0)
            best = None
            for order in (range(start, len(lines)), range(0, start)):
                for k in order:
                    line = lines[k]
                    if line.id in used:
                        continue
                    score = _similar(line.text, candidate.excerpt)
                    if score >= LINK_THRESHOLD and (best is None or score > best[0]):
                        best = (score, k)
                        if score == 1.0:
                            break
                if best is not None:
                    break
            if best is None:
                links.append((ref, ()))
                continue
            k = best[1]
            chosen = [lines[k]]
            prompt = _norm_text(candidate.question.get("prompt", ""))
            for follow in lines[k+1:k+6]:
                text = _norm_text(follow.text)
                if (
                    follow.id in used or len(text) < 6
                    or follow.block_id != lines[k].block_id and follow.box[1] - chosen[-1].box[3] > 0.03
                    or text not in prompt
                ):
                    break
                chosen.append(follow)
            used.update(line.id for line in chosen)
            cursor[page.page_number] = k + len(chosen)
            region = Region(
                f"r{counter}", page.page_number,
                union_box(line.box for line in chosen),
                tuple(line.id for line in chosen), "detected",
            )
            counter += 1
            links.append((ref, (region,)))
    frozen = tuple(links)
    return SpatialEvidence(page_list, frozen, frozen, counter)


def _replace_regions(evidence: SpatialEvidence, ref: str,
                     regions: tuple[Region, ...], *, consumed: int = 0) -> SpatialEvidence:
    if ref not in dict(evidence.links):
        raise KeyError("Unknown question reference.")
    links = tuple(
        (key, regions if key == ref else value) for key, value in evidence.links
    )
    return replace(evidence, links=links, next_region=evidence.next_region + consumed)


def set_region_box(evidence: SpatialEvidence, ref: str, region_id: str,
                   box: Iterable[float]) -> SpatialEvidence:
    """Manually adjust a region; the source document is never modified."""
    clean = normalize_box(box)
    regions = evidence.regions(ref)
    if not any(r.id == region_id for r in regions):
        raise KeyError("Select a region of this question.")
    return _replace_regions(evidence, ref, tuple(
        replace(r, box=clean, origin="manual") if r.id == region_id else r
        for r in regions
    ))


def link_line(evidence: SpatialEvidence, ref: str, page_number: int,
              line_id: str) -> SpatialEvidence:
    """Attach an existing OCR/text line to a question (manual link)."""
    page = evidence.page(page_number)
    line = page.line(line_id) if page else None
    if line is None or not page.has_geometry:
        raise KeyError("That text line does not exist on this page.")
    owner = next(
        (key for key, regions in evidence.links
         for r in regions if line_id in r.line_ids), None,
    )
    if owner is not None:
        raise ValueError("This line is already linked; unlink it first.")
    region = Region(f"r{evidence.next_region}", page_number, line.box,
                    (line_id,), "manual")
    return _replace_regions(evidence, ref, (*evidence.regions(ref), region), consumed=1)


def add_manual_region(evidence: SpatialEvidence, ref: str, page_number: int,
                      box: Iterable[float]) -> SpatialEvidence:
    if evidence.page(page_number) is None:
        raise KeyError("No rendered geometry exists for that page.")
    region = Region(f"r{evidence.next_region}", page_number,
                    normalize_box(box), (), "manual")
    return _replace_regions(evidence, ref, (*evidence.regions(ref), region), consumed=1)


def unlink_region(evidence: SpatialEvidence, ref: str, region_id: str) -> SpatialEvidence:
    regions = evidence.regions(ref)
    if not any(r.id == region_id for r in regions):
        raise KeyError("Select a region of this question.")
    return _replace_regions(evidence, ref, tuple(r for r in regions if r.id != region_id))


def merge_regions(evidence: SpatialEvidence, ref: str,
                  region_ids: Iterable[str]) -> SpatialEvidence:
    """Merge two or more regions of one question on the same page."""
    wanted = list(dict.fromkeys(region_ids))
    regions = evidence.regions(ref)
    chosen = [r for r in regions if r.id in wanted]
    if len(chosen) < 2 or len(chosen) != len(wanted):
        raise ValueError("Select at least two regions of this question to merge.")
    if len({r.page for r in chosen}) != 1:
        raise ValueError("Regions on different pages cannot be merged.")
    merged = Region(
        f"r{evidence.next_region}", chosen[0].page,
        union_box(r.box for r in chosen),
        tuple(dict.fromkeys(l for r in chosen for l in r.line_ids)), "merged",
    )
    kept = []
    inserted = False
    for region in regions:
        if region.id in wanted:
            if not inserted:
                kept.append(merged)
                inserted = True
        else:
            kept.append(region)
    return _replace_regions(evidence, ref, tuple(kept), consumed=1)


def split_region(evidence: SpatialEvidence, ref: str, region_id: str) -> SpatialEvidence:
    """Split a region in two at its widest gap (between lines or words)."""
    regions = evidence.regions(ref)
    target = next((r for r in regions if r.id == region_id), None)
    if target is None:
        raise KeyError("Select a region of this question.")
    page = evidence.page(target.page)
    lines = [
        line for line in (page.lines if page else ())
        if line.id in target.line_ids or box_contains(target.box, *box_center(line.box))
    ]
    lines.sort(key=lambda l: l.box[1])
    first = second = None
    if len(lines) >= 2:
        gaps = [(lines[k+1].box[1] - lines[k].box[3], k) for k in range(len(lines)-1)]
        k = max(gaps)[1]
        top, bottom = lines[:k+1], lines[k+1:]
        first = (union_box(l.box for l in top), tuple(l.id for l in top))
        second = (union_box(l.box for l in bottom), tuple(l.id for l in bottom))
    else:
        words = sorted(page.words_in(target.box) if page else (), key=lambda w: w.box[0])
        x0, y0, x1, y1 = target.box
        if len(words) >= 2:
            gaps = [(words[k+1].box[0] - words[k].box[2], k) for k in range(len(words)-1)]
            k = max(gaps)[1]
            cut = (words[k].box[2] + words[k+1].box[0]) / 2
        else:
            cut = (x0 + x1) / 2
        if not x0 + 0.002 < cut < x1 - 0.002:
            raise ValueError("This region is too small to split.")
        ids = target.line_ids
        first = ((x0, y0, cut, y1), ids)
        second = ((cut, y0, x1, y1), ids)
    n = evidence.next_region
    pieces = (
        Region(f"r{n}", target.page, first[0], first[1], "split"),
        Region(f"r{n+1}", target.page, second[0], second[1], "split"),
    )
    out = []
    for region in regions:
        out.extend(pieces if region.id == region_id else (region,))
    return _replace_regions(evidence, ref, tuple(out), consumed=2)


def revert_links(evidence: SpatialEvidence, ref: str | None = None) -> SpatialEvidence:
    """Restore detected regions for one question, or for every question."""
    original = dict(evidence.original_links)
    if ref is None:
        return replace(evidence, links=evidence.original_links)
    if ref not in original:
        raise KeyError("Unknown question reference.")
    return _replace_regions(evidence, ref, original[ref])


def review_queue(review, evidence: SpatialEvidence | None, *,
                 include: Iterable[str] = ("low", "unknown", "review", "unlinked")) -> tuple[tuple[str, str], ...]:
    """List ``(ref, reason)`` for questions needing attention, in order."""
    wanted = set(include)
    queue = []
    for i, instrument in enumerate(review.instruments):
        for j, _candidate in enumerate(instrument.questions):
            ref = question_ref(i, j)
            if evidence is None:
                if "unknown" in wanted:
                    queue.append((ref, "unknown"))
                continue
            regions = evidence.regions(ref)
            conf = evidence.confidence(ref)
            if not regions and "unlinked" in wanted:
                queue.append((ref, "unlinked"))
            elif conf.category in wanted:
                queue.append((ref, conf.category))
    return tuple(queue)
