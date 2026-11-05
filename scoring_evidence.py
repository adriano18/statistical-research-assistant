"""Documented scoring statements as review-only evidence (never applied).

Instrument documents often end with a scoring recipe, for example::

    Synthetic approach style (Items 2, 7, 10, 12, mean of the 4 marked codes, range 1–4):
    Total score = sum of items 1–10.

Editions, translations and adaptations of an instrument differ, so this
module records only what THIS document states — the group name, the listed
item numbers, the aggregation word (average/mean or sum/total), the printed
value range, the page and the source line — and checks the statement against
the item numbers actually found. It never infers subscales, item pairings,
totals, reverse keys or norms, and it never changes a question or a score.
A researcher must approve the evidence explicitly; even then it is metadata
for review (Stage 33), not an applied scoring rule.

:class:`ReviewEvidence` is the small, stable interface attached to every
``InstrumentCandidate`` (``candidate.evidence``): documented scoring groups
and statements, item numbers missing from an otherwise consecutive sequence
and per-item review flags.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

MAX_GROUPS = 40
MAX_STATEMENTS = 8

_ITEM_WORDS = r"(?:items?|questions?|statements?|пункты?|вопросы?|утверждения?|jautājum[sia]|apgalvojum[sia])"
_LIST = r"\d{1,3}(?:\s*[-–]\s*\d{1,3})?(?:\s*(?:,|;|\band\b|\bи\b|\bun\b|&)\s*\d{1,3}(?:\s*[-–]\s*\d{1,3})?)*"
_GROUP_PAREN = re.compile(
    rf"^(?P<name>[^\d():=]{{2,80}}?)\s*\(\s*{_ITEM_WORDS}\s*(?:no\.?\s*|nr\.?\s*|№\s*)?"
    rf"(?P<items>{_LIST})\s*,?\s*(?P<rest>[^)]*)\)\s*[:.;]?\s*(?P<after>.*)$",
    re.I,
)
_GROUP_COLON = re.compile(
    rf"^(?P<name>[^\d():=]{{2,80}}?)\s*[:=]\s*(?P<pre>[^\d]{{0,40}}?)\b{_ITEM_WORDS}\s*"
    rf"(?:no\.?\s*|nr\.?\s*|№\s*)?(?P<items>{_LIST})\s*[,.;]?\s*(?P<rest>.*)$",
    re.I,
)
_MEAN = re.compile(r"\b(?:average|mean|averaged|vidēj\w*|средн\w*)\b", re.I)
_SUM = re.compile(r"\b(?:sum|summed|total|add(?:ed)?\s+up|summ\w*|kopsumm\w*|сумм\w*)\b", re.I)
_COUNT = re.compile(
    r"\b(?:average|mean|sum|total|vidējais|vidējā|summa|среднее|сумма)\s+(?:of|no|из)\s+"
    r"(?:the\s+|these\s+|all\s+)?(\d{1,3})\b", re.I,
)
_RANGE = re.compile(r"(?<![\d.])(-?\d{1,3})\s*[–-]\s*(\d{1,3})(?![\d.])")
_SCORING_WORDS = re.compile(
    r"\b(?:scor\w*|subscale\w*|total|average|mean|sum|summed|norms?|cut-?offs?|"
    r"vērtē\w*|apakšskal\w*|kopsumm\w*|балл\w*|шкал\w*|подшкал\w*|сумм\w*)\b",
    re.I,
)


@dataclass(frozen=True)
class ScoringGroup:
    """One documented scoring rule — review-only, never applied automatically."""
    id: str
    name: str                     # as printed
    items: tuple[int, ...]        # item numbers listed in the source
    aggregation: str              # "mean" | "sum" | "unspecified"
    stated_count: int | None      # "mean of the 8 marked codes" → 8
    value_range: str              # printed range text such as "1–4" ("" if none)
    page: int
    source_line: str
    evidence: str                 # "pdf_text_layer" | "ocr" | "docx" | "doc" | "text"
    issues: tuple[str, ...] = ()
    approved: bool = False

    @property
    def ocr_only(self) -> bool:
        return self.evidence == "ocr"


@dataclass(frozen=True)
class ScoringStatement:
    """A scoring-related sentence that is not a parsable item group."""
    page: int
    text: str
    evidence: str


@dataclass(frozen=True)
class ReviewEvidence:
    """Stage 33 review interface of one instrument candidate.

    * ``scoring_groups`` / ``scoring_statements`` — documented scoring, kept
      separate from the verified response scale; nothing is applied.
    * ``missing_items`` — numbers absent from an otherwise consecutive item
      sequence (they block the draft until acknowledged or added).
    * ``item_flags`` — ``(item number, flags)`` that need a look on the source.
    """
    scoring_groups: tuple[ScoringGroup, ...] = ()
    scoring_statements: tuple[ScoringStatement, ...] = ()
    missing_items: tuple[int, ...] = ()
    item_flags: tuple[tuple[int, tuple[str, ...]], ...] = ()
    issues: tuple[str, ...] = ()
    missing_acknowledged: bool = False

    @property
    def has_scoring(self) -> bool:
        return bool(self.scoring_groups or self.scoring_statements)

    @property
    def ocr_only(self) -> bool:
        sources = [g.evidence for g in self.scoring_groups] + [s.evidence for s in self.scoring_statements]
        return bool(sources) and all(source == "ocr" for source in sources)

    @property
    def scoring_approved(self) -> bool:
        return bool(self.scoring_groups) and all(g.approved for g in self.scoring_groups)

    def flags_for(self, number: int) -> tuple[str, ...]:
        return dict(self.item_flags).get(number, ())

    def unassigned_items(self, numbers) -> tuple[int, ...]:
        """Items listed in no documented group (informative, not an error)."""
        if not self.scoring_groups:
            return ()
        listed = {n for g in self.scoring_groups for n in g.items}
        return tuple(n for n in numbers if n not in listed)


def item_numbers(text: str) -> tuple[int, ...]:
    """``2, 7, 10–12 and 14`` → (2, 7, 10, 11, 12, 14); bounded ranges only."""
    numbers: list[int] = []
    for part in re.split(r"\s*(?:,|;|\band\b|\bи\b|\bun\b|&)\s*", text.strip()):
        match = re.fullmatch(r"(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?", part.strip())
        if not match:
            continue
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        if last < first or last - first > 60:
            numbers.append(first)
            continue
        numbers.extend(range(first, last + 1))
    return tuple(numbers)


def _aggregation(text: str) -> str:
    if _MEAN.search(text):
        return "mean"
    if _SUM.search(text):
        return "sum"
    return "unspecified"


def _group(line: str, page: int, evidence: str, index: int) -> ScoringGroup | None:
    for pattern in (_GROUP_PAREN, _GROUP_COLON):
        match = pattern.match(line)
        if not match:
            continue
        name = " ".join(match.group("name").split()).strip(" -–:,;")
        items = item_numbers(match.group("items"))
        if len(items) < 1 or not re.search(r"[^\W\d_]{3}", name):
            continue
        rest = " ".join(part for part in (
            match.groupdict().get("pre") or "", match.group("rest") or "",
            match.groupdict().get("after") or "",
        ) if part)
        count = _COUNT.search(rest)
        ranges = _RANGE.search(rest)
        return ScoringGroup(
            f"g{index}", name[:80], items, _aggregation(rest + " " + name),
            int(count.group(1)) if count else None,
            ranges.group(0).replace(" ", "") if ranges else "",
            page, line[:240], evidence,
        )
    return None


def _unwrapped(lines):
    """Join a statement wrapped inside an open parenthesis (≤ 3 lines)."""
    lines = [(page, " ".join(str(raw).split())) for page, raw in lines]
    out, i = [], 0
    while i < len(lines):
        page, text = lines[i]
        j = i + 1
        while (text.count("(") > text.count(")") and j < len(lines) and j - i <= 3
               and lines[j][0] == page and len(text) < 600):
            text = f"{text} {lines[j][1]}"
            j += 1
        if text.count("(") > text.count(")"):
            text, j = lines[i][1], i + 1  # never glue unrelated lines
        out.append((page, text))
        i = j
    return out


def parse_scoring_evidence(
    lines: list[tuple[int, str]], numbers, *, evidence_for=lambda page: "text",
) -> tuple[tuple[ScoringGroup, ...], tuple[ScoringStatement, ...], tuple[str, ...]]:
    """Scoring groups and statements printed in ``lines`` of one instrument.

    ``numbers`` are the item numbers found; ``evidence_for(page)`` names the
    text source of a page. Returns ``(groups, statements, issues)``.
    """
    found = set(numbers)
    groups: list[ScoringGroup] = []
    statements: list[ScoringStatement] = []
    for page, raw in _unwrapped(lines):
        line = " ".join(str(raw).split())
        if len(line) < 6 or len(line) > 600:
            continue
        group = _group(line, page, evidence_for(page), len(groups) + 1)
        if group is not None and len(groups) < MAX_GROUPS:
            groups.append(group)
            continue
        if _SCORING_WORDS.search(line) and len(statements) < MAX_STATEMENTS:
            statements.append(ScoringStatement(page, line[:240], evidence_for(page)))
    seen: dict[int, list[str]] = {}
    checked = []
    for group in groups:
        issues = []
        unknown = [n for n in group.items if n not in found]
        if unknown:
            issues.append("Lists item(s) " + ", ".join(map(str, unknown))
                          + " that were not found in this instrument.")
        if len(set(group.items)) != len(group.items):
            issues.append("Lists an item more than once.")
        if group.stated_count is not None and group.stated_count != len(set(group.items)):
            issues.append(f"States {group.stated_count} values but lists "
                          f"{len(set(group.items))} item(s).")
        if group.ocr_only:
            issues.append("Read by OCR only — compare the item list with the source page.")
        for number in group.items:
            seen.setdefault(number, []).append(group.name)
        checked.append(replace(group, issues=tuple(issues)))
    overall = []
    shared = sorted(n for n, names in seen.items() if len(names) > 1)
    if shared:
        overall.append("Item(s) " + ", ".join(map(str, shared[:15]))
                       + " appear in more than one documented scoring group.")
    if checked:
        overall.append(
            "Documented scoring is review-only evidence from this document; it is "
            "NOT applied. Editions and translations differ — verify it in the manual."
        )
    return tuple(checked), tuple(statements), tuple(overall)


def referenced_missing(groups, numbers) -> tuple[int, ...]:
    """Item numbers named by a scoring group but absent from the instrument."""
    found = set(numbers)
    return tuple(sorted({n for g in groups for n in g.items if n not in found and n >= 1}))


def sequence_gaps(numbers) -> tuple[int, ...]:
    """Numbers missing from an otherwise consecutive sequence (≥ 3 items)."""
    values = sorted(set(n for n in numbers if isinstance(n, int)))
    if len(values) < 3:
        return ()
    missing = [n for n in range(values[0], values[-1] + 1) if n not in set(values)]
    if not missing or len(missing) > max(3, len(values) // 4):
        return ()
    return tuple(missing)


__all__ = [
    "ReviewEvidence", "ScoringGroup", "ScoringStatement", "item_numbers",
    "parse_scoring_evidence", "referenced_missing", "sequence_gaps",
]
