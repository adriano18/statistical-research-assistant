"""Answer choices printed again after EVERY item (coping-inventory layouts).

Some forms repeat the whole numbered answer set under or beside each item,
so that respondents circle a code::

    1                      ← item number (a line of its own, or "1 During …")
    During the invented …  ← prompt, wrapped over one to three lines
    1                      ← answer code
    NOT AT                 ← its label, possibly wrapped
    ALL
    2
    A SMALL AMOUNT
    3 A FAIR AMOUNT        ← code and label may also share a line
    4
    VERY MUCH
    2                      ← the next item number
    …

Read line by line, the answer codes look exactly like item numbers. This
module finds the repeated block by *consensus* — the same ascending codes
with the same labels after at least three items — removes every copy from
the item text and joins each item number with its prompt (sequence logic,
independent of geometry, so it works for text layers, OCR text and Word
tables alike).

Labels are kept exactly as printed; only whitespace and apostrophe variants
are normalised. Numeric codes are reported only because they are printed.
A block that differs on some items is reported, never silently replaced.
Nothing is scored here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
import unicodedata

MAX_CATEGORIES = 11
MAX_LABEL_LINES = 4
MAX_PROMPT_LINES = 6
MIN_REPEATS = 3

_APOSTROPHES = str.maketrans({"ʼ": "'", "’": "'", "‘": "'", "`": "'", "´": "'", "′": "'"})
_CODE = re.compile(r"^[(\[]?\s*(\d{1,2})\s*[)\].:]?$")
_CODE_LABEL = re.compile(r"^[(\[]?\s*(\d{1,2})\s*(?:[)\].:=]|[-–—](?=\s))?\s+(\S.*)$")
_INLINE_ITEM = re.compile(r"^[(\[]?\s*(\d{1,3})\s*(?:[)\].:,]\s*|\s+)(\S.*)$")
_CIRCLED_LEAD = re.compile(r"^([①-⑳⓪⓵-⓾❶-➓])\s*(.*)$")


def printed_label(text: str) -> str:
    """Label as printed: whitespace collapsed, apostrophe variants unified."""
    return " ".join(str(text).translate(_APOSTROPHES).split())


def _key(text: str) -> str:
    return unicodedata.normalize("NFKC", printed_label(text)).casefold()


def _circled_value(char: str) -> int | None:
    try:
        value = unicodedata.numeric(char)
    except (TypeError, ValueError):
        return None
    return int(value) if value == int(value) and 0 <= value <= 20 else None


def code_of(line: str) -> int | None:
    """The answer code / number printed alone on a line (``1``, ``(2)``, ``③``)."""
    text = line.strip()
    if len(text) == 1:
        return int(text) if text.isdecimal() else _circled_value(text)
    match = _CODE.match(text)
    return int(match.group(1)) if match else None


def code_label_of(line: str) -> tuple[int, str] | None:
    """``1 NOT AT ALL`` / ``2 = A SMALL AMOUNT`` / ``③ OFTEN`` → (code, label)."""
    text = line.strip()
    circled = _CIRCLED_LEAD.match(text)
    if circled and circled.group(2) and _circled_value(circled.group(1)) is not None:
        label = circled.group(2).strip()
        if re.search(r"[^\W\d_]", label):
            return _circled_value(circled.group(1)), label
        return None
    match = _CODE_LABEL.match(text)
    if not match or not re.search(r"[^\W\d_]", match.group(2)):
        return None
    return int(match.group(1)), match.group(2).strip()


def item_start(line: str) -> tuple[int, str, str] | None:
    """Item number at the start of a line: (number, rest, kind)."""
    text = line.strip()
    value = code_of(text)
    if value is not None:
        return value, "", "circled" if not text[:1].isdecimal() and text[:1] not in "([" else "standalone"
    circled = _CIRCLED_LEAD.match(text)
    if circled and _circled_value(circled.group(1)) is not None:
        return _circled_value(circled.group(1)), circled.group(2).strip(), "circled"
    match = _INLINE_ITEM.match(text)
    if match and re.search(r"[^\W\d_]{2}", match.group(2)):
        return int(match.group(1)), match.group(2).strip(), "inline"
    return None


def _noise(line: str) -> bool:
    """A line without letters or digits ("_", "|", "—"): OCR specks, rules."""
    return not re.search(r"[^\W_]", line)


def _label_like(line: str) -> bool:
    text = line.strip()
    return (
        bool(text) and len(text) <= 60 and len(text.split()) <= 8
        and bool(re.search(r"[^\W\d_]", text)) and not text.endswith("?")
        and code_of(text) is None
    )


def preferred_spelling(spellings) -> str:
    """Most frequent spelling; OCR drops spaces far more often than it adds
    them, so a variant with more words wins when it repeats ("A FAIR" over
    "AFAIR" when both occur at least twice or a quarter as often)."""
    spellings = list(spellings)
    best = max(set(spellings), key=spellings.count)
    compact = re.sub(r"\s+", "", best).casefold()
    floor = max(2, 0.25 * spellings.count(best))
    spaced = [s for s in set(spellings)
              if re.sub(r"\s+", "", s).casefold() == compact
              and len(s.split()) > len(best.split()) and spellings.count(s) >= floor]
    return max(spaced, key=lambda s: (len(s.split()), spellings.count(s))) if spaced else best


def _join_label(parts) -> str:
    out = ""
    for part in parts:
        part = printed_label(part)
        if not part:
            continue
        if out.endswith("-") and part[:1].isalpha():
            out += part
        else:
            out = (out + " " + part).strip()
    return out


@dataclass(frozen=True)
class ChoiceBlock:
    """One printed copy of the answer set."""
    codes: tuple[str, ...]
    labels: tuple[str, ...]
    page: int
    start: int = 0           # line index of the block in the input
    end: int = 0
    line_counts: tuple[int, ...] = ()  # printed label lines per choice

    @property
    def key(self) -> tuple[tuple[str, str], ...]:
        return tuple((c, _key(l)) for c, l in zip(self.codes, self.labels))

    @property
    def size(self) -> int:
        return len(self.codes)

    def describe(self) -> str:
        return " / ".join(f"{c} {l}".strip() for c, l in zip(self.codes, self.labels))


@dataclass(frozen=True)
class BlockItem:
    """An item whose answer choices were printed right after it."""
    number: int
    prompt: str
    page: int
    excerpt: str
    block: ChoiceBlock
    number_source: str            # standalone | inline | circled | inferred
    prompt_lines: int
    deviations: tuple[str, ...] = ()   # how this item's block differs from the common one
    notes: tuple[str, ...] = ()


class BlockItemLine(str):
    """A rewritten item line (``"N. prompt"``) carrying its :class:`BlockItem`."""
    item: BlockItem

    def __new__(cls, item: BlockItem):
        line = super().__new__(cls, f"{item.number}. {item.prompt}")
        line.item = item
        return line


@dataclass(frozen=True)
class ChoiceLayout:
    """Summary of a detected repeated-choice layout (review evidence)."""
    template: ChoiceBlock
    items: tuple[BlockItem, ...]
    fuzzy: bool = False
    issues: tuple[str, ...] = field(default=())

    @property
    def numbers(self) -> tuple[int, ...]:
        return tuple(item.number for item in self.items)


def _similar(a: str, b: str) -> float:
    a, b = _key(a), _key(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


class _Reader:
    def __init__(self, lines: list[tuple[int, str]]):
        self.pages = [page for page, _ in lines]
        self.text = [" ".join(str(raw).split()) for _, raw in lines]
        self.codes = [code_of(t) for t in self.text]
        self.pairs = [code_label_of(t) if c is None else None for t, c in zip(self.text, self.codes)]
        self.n = len(self.text)

    def is_code(self, i: int) -> bool:
        return self.codes[i] is not None or self.pairs[i] is not None

    def code_at(self, i: int) -> int | None:
        if self.codes[i] is not None:
            return self.codes[i]
        return self.pairs[i][0] if self.pairs[i] else None

    def greedy_block(self, i: int) -> list[tuple[int, str, int]]:
        """Ascending codes with label lines from index ``i`` (no template)."""
        first = self.code_at(i)
        if first not in (0, 1):
            return []
        cats, j, expected = [], i, first
        sizes = []
        while j < self.n and len(cats) < MAX_CATEGORIES and self.code_at(j) == expected:
            label = [self.pairs[j][1]] if self.pairs[j] else []
            j += 1
            while (j < self.n and not self.is_code(j) and len(label) < MAX_LABEL_LINES
                   and (_label_like(self.text[j]) or _noise(self.text[j]))):
                if not _noise(self.text[j]):
                    label.append(self.text[j])
                j += 1
            cats.append((expected, label, j))
            sizes.append(len(label))
            expected += 1
        if len(cats) < 2:
            return []
        # The last label cannot be longer than the longest earlier one: the
        # next item's prompt may follow without a number line.
        code, label, end = cats[-1]
        limit = max(sizes[:-1])
        if len(label) > limit:
            cats[-1] = (code, label[:limit], end - (len(label) - limit))
        return [(code, _join_label(label), end, len(label)) for code, label, end in cats]


def _template(reader: _Reader, fuzzy: bool) -> ChoiceBlock | None:
    candidates = []
    for i in range(reader.n):
        cats = reader.greedy_block(i)
        if cats:
            candidates.append((i, cats))
    if len(candidates) < MIN_REPEATS:
        return None
    for size in range(MAX_CATEGORIES, 1, -1):
        long_enough = [(i, cats[:size]) for i, cats in candidates if len(cats) >= size]
        if len(long_enough) < MIN_REPEATS:
            continue
        # Per-category consensus: the most frequent spelling (OCR: the most
        # frequent group of near-identical spellings) of every label.
        consensus = []
        for k in range(size):
            texts = [printed_label(cats[k][1]) for _, cats in long_enough]
            keys = [_key(t) for t in texts]
            if fuzzy:
                support = {key: sum(1 for other in keys if other == key or _similar(other, key) >= 0.8)
                           for key in set(keys)}
                common = max(support, key=lambda key: (support[key], keys.count(key)))
            else:
                common = max(set(keys), key=keys.count)
            if fuzzy:
                compact = re.sub(r"\s+", "", common)
                spellings = [t for t, key in zip(texts, keys) if re.sub(r"\s+", "", key) == compact]
                consensus.append(preferred_spelling(spellings))
            else:
                spellings = [t for t, key in zip(texts, keys) if key == common]
                consensus.append(max(set(spellings), key=spellings.count))

        def agrees(cats) -> bool:
            matches = sum(
                1 for k in range(size)
                if _key(cats[k][1]) == _key(consensus[k])
                or fuzzy and _similar(cats[k][1], consensus[k]) >= 0.8
            )
            # OCR may garble one label of a copy; the others must agree.
            return matches == size or (fuzzy and size >= 3 and matches >= size - 1)

        best = [(i, cats) for i, cats in long_enough if agrees(cats)]
        if len(best) >= MIN_REPEATS and len(best) >= 0.6 * len(long_enough):
            codes = tuple(str(cat[0]) for cat in best[0][1])
            counts = tuple(
                max(set(c), key=c.count)
                for c in ([cats[k][3] for _, cats in best] for k in range(size))
            )
            return ChoiceBlock(codes, tuple(consensus), reader.pages[best[0][0]],
                               line_counts=counts)
    return None


def _read_block(reader: _Reader, i: int, template: ChoiceBlock, fuzzy: bool):
    """Read one copy of the template at ``i``; returns (block, deviations) or None."""
    codes = [int(c) for c in template.codes]
    if reader.code_at(i) != codes[0]:
        return None
    labels, j = [], i
    for k, code in enumerate(codes):
        if j >= reader.n or reader.code_at(j) != code:
            if k >= 2:  # a shortened copy of the block
                break
            return None
        parts = [reader.pairs[j][1]] if reader.pairs[j] else []
        j += 1
        last = k == len(codes) - 1
        target = template.labels[k]
        if not last:
            while (j < reader.n and not reader.is_code(j) and len(parts) < MAX_LABEL_LINES
                   and (_label_like(reader.text[j]) or _noise(reader.text[j]))):
                if not _noise(reader.text[j]):
                    parts.append(reader.text[j])
                j += 1
        elif target and _key(_join_label(parts)) != _key(target):
            # The last label ends where the printed template label ends.
            best, best_score = 0, _similar(_join_label(parts), target) if parts else 0.0
            for extra in range(1, MAX_LABEL_LINES + 1):
                if j + extra > reader.n or reader.is_code(j + extra - 1) or not _label_like(
                        reader.text[j + extra - 1]):
                    break
                score = _similar(_join_label(parts + reader.text[j:j + extra]), target)
                if score > best_score + 1e-9:
                    best, best_score = extra, score
                if _key(_join_label(parts + reader.text[j:j + extra])) == _key(target):
                    break
            if best_score < (0.6 if fuzzy else 0.5):
                # A different label: as many label lines as the common block prints.
                best = 0
                limit = template.line_counts[-1] if template.line_counts else 1
                while (best < limit and j + best < reader.n and not reader.is_code(j + best)
                       and _label_like(reader.text[j + best])):
                    best += 1
            parts += reader.text[j:j + best]
            j += best
        labels.append(_join_label(parts))
    block = ChoiceBlock(tuple(template.codes[:len(labels)]), tuple(labels), reader.pages[i], i, j)
    deviations = []
    if len(labels) < template.size:
        deviations.append(
            f"only {len(labels)} of {template.size} answer choices were found "
            f"(missing {', '.join(template.codes[len(labels):])})"
        )
    for code, label, target in zip(block.codes, block.labels, template.labels):
        if _key(label) == _key(target):
            continue
        if fuzzy and _similar(label, target) >= 0.8:
            deviations.append(f"choice {code} reads “{label}” (OCR variant of “{target}”)")
        else:
            deviations.append(f"choice {code} reads “{label or '(no label)'}” instead of “{target}”")
    return block, tuple(deviations)


def segment_repeated_choices(
    lines: list[tuple[int, str]], *, fuzzy_pages=(),
) -> tuple[list[tuple[int, str]], ChoiceLayout | None]:
    """Rewrite item + repeated-choice runs into one line per item.

    Returns the new ``(page, line)`` list — every detected item becomes a
    :class:`BlockItemLine` — and the :class:`ChoiceLayout`, or the input
    unchanged and ``None`` when no block repeats after at least three items.
    ``fuzzy_pages`` (OCR pages) tolerate small label differences, which are
    still reported.
    """
    reader = _Reader(lines)
    if reader.n < 3 * MIN_REPEATS:
        return lines, None
    fuzzy_set = set(fuzzy_pages)
    fuzzy = bool(fuzzy_set) and any(page in fuzzy_set for page in reader.pages)
    template = _template(reader, fuzzy)
    if template is None:
        return lines, None
    blocks = []
    i = 0
    while i < reader.n:
        found = _read_block(reader, i, template, fuzzy and reader.pages[i] in fuzzy_set)
        if found is None:
            i += 1
            continue
        blocks.append(found)
        i = max(found[0].end, i + 1)
    if len(blocks) < MIN_REPEATS:
        return lines, None

    items, spans = [], []
    previous_end, previous_number = 0, 0
    numbered = 0
    for block, deviations in blocks:
        segment = range(previous_end, block.start)
        start = None
        for back in range(block.start - 1, max(previous_end, block.start - MAX_PROMPT_LINES) - 1, -1):
            found = item_start(reader.text[back])
            if found is None:
                continue
            number, rest, kind = found
            if previous_number and not previous_number < number <= previous_number + 10:
                continue  # a page number or code, not the next item number
            start = (back, number, rest, kind)
            break
        if start is None:
            prompt_lines = [k for k in segment if reader.text[k]][-3:]
            if not items or not prompt_lines:
                previous_end = block.end
                continue  # cannot anchor an unnumbered first item safely
            back, number, rest, kind = prompt_lines[0], previous_number + 1, "", "inferred"
            body = [reader.text[k] for k in prompt_lines]
        else:
            back, number, rest, kind = start
            body = ([rest] if rest else []) + [reader.text[k] for k in range(back + 1, block.start)]
            numbered += 1
        body = [line for line in body if line]
        prompt = " ".join(body).strip()
        if not prompt or len(prompt) > 300:
            previous_end = block.end
            continue
        excerpt = reader.text[back] if rest or kind == "inferred" else (
            f"{reader.text[back]} {body[0]}" if body else reader.text[back])
        notes = []
        if kind == "inferred":
            notes.append(f"No item number was recognized before this item; {number} was "
                         "inferred from the order — check the source.")
        if len(body) > 1:
            notes.append(f"Prompt joined from {len(body)} wrapped source lines.")
        items.append(BlockItem(number, prompt, reader.pages[back], excerpt, block,
                               kind, len(body), deviations, tuple(notes)))
        spans.append((back, block.end))
        previous_end, previous_number = block.end, number
    # Most items must carry a printed number; OCR often misreads small item
    # numbers, so OCR text needs fewer (the rest are inferred and flagged).
    if len(items) < MIN_REPEATS or numbered < (0.3 if fuzzy else 0.6) * len(items):
        return lines, None

    out: list[tuple[int, str]] = []
    cursor = 0
    for item, (begin, end) in zip(items, spans):
        out.extend(lines[cursor:begin])
        out.append((item.page, BlockItemLine(item)))
        cursor = end
    out.extend(lines[cursor:])
    issues = []
    differing = [item.number for item in items if item.deviations]
    if differing:
        issues.append(
            "Printed answer choices differ on item(s) "
            + ", ".join(map(str, differing[:15]))
            + "; check them on the source page."
        )
    return out, ChoiceLayout(template, tuple(items), fuzzy, tuple(issues))


__all__ = [
    "BlockItem", "BlockItemLine", "ChoiceBlock", "ChoiceLayout", "code_label_of",
    "code_of", "item_start", "printed_label", "segment_repeated_choices",
]
