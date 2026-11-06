"""Conservative detection of binary response formats (True/False, Yes/No).

Recognized evidence, strongest first:

* **row** — the pair is printed on the item's own line or table row
  (``12. I enjoy parties.   T  F`` or ``T F 12. …``);
* **header** — a line or table header that consists ONLY of the pair,
  optionally with generic column words (``Statement   True   False``);
* **instruction** — a sentence such as "Answer each statement True or
  False". This is weak evidence and is never applied automatically.

Labels are kept as printed (case-normalised for full words; single letters
stay letters unless the document defines them, e.g. ``T = True``). True/False
and Yes/No are different formats and are never interchanged. No numeric
codes, keyed answers or reverse scoring are ever proposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

TRUE_FALSE = "true_false"
YES_NO = "yes_no"
FORMAT_LABELS = {TRUE_FALSE: "True / False", YES_NO: "Yes / No"}

# (kind, first, second) — casefolded spellings → display form.
_PAIRS = (
    (TRUE_FALSE, ("t",), ("f",), "T", "F"),
    (TRUE_FALSE, ("true",), ("false",), "True", "False"),
    (TRUE_FALSE, ("верно",), ("неверно",), "Верно", "Неверно"),
    (TRUE_FALSE, ("правда",), ("неправда",), "Правда", "Неправда"),
    (TRUE_FALSE, ("patiesi",), ("nepatiesi",), "Patiesi", "Nepatiesi"),
    (TRUE_FALSE, ("patiess",), ("nepatiess",), "Patiess", "Nepatiess"),
    (TRUE_FALSE, ("pareizi",), ("nepareizi",), "Pareizi", "Nepareizi"),
    (YES_NO, ("y",), ("n",), "Y", "N"),
    (YES_NO, ("yes",), ("no",), "Yes", "No"),
    (YES_NO, ("да",), ("нет",), "Да", "Нет"),
    (YES_NO, ("д",), ("н",), "Д", "Н"),
    (YES_NO, ("jā", "ja"), ("nē", "ne"), "Jā", "Nē"),
)
# OCR/look-alike repairs applied to single-letter tokens only.
_CONFUSABLE = {"т": "t", "Т": "t"}
_SEPARATORS = r"(?:\s*(?:/|\||\\|,|;|-|–|—|:|\bor\b|\bили\b|\bvai\b)\s*|\s+)"
_MARKERS = "□☐◯○●•▢◻◽⬜❍()[]{}"
_HEADER_WORDS = {
    "statement", "statements", "item", "items", "question", "questions", "no",
    "no.", "nr", "nr.", "#", "№", "answer", "response", "circle", "mark",
    "утверждение", "утверждения", "вопрос", "вопросы", "ответ", "пункт",
    "apgalvojums", "apgalvojumi", "jautājums", "jautājumi", "atbilde",
}
_INSTRUCTION_VERBS = re.compile(
    r"\b(answer|mark|circle|indicate|decide|respond|tick|check|choose|select|"
    r"ответьте|отметьте|обведите|укажите|выберите|отвечайте|"
    r"atbildiet|atzīmējiet|apvelciet|norādiet|izvēlieties)\w*",
    re.I,
)
_LEGEND = re.compile(
    r"\b([TFYNДН])\s*(?:=|-|–|—|:|\bif\b|\bfor\b)\s*(true|false|yes|no|да|нет)\b"
    r"|\b(true|false|yes|no)\s*\(\s*([TFYN])\s*\)",
    re.I,
)


@dataclass(frozen=True)
class BinaryScale:
    kind: str                  # TRUE_FALSE | YES_NO
    labels: tuple[str, str]    # as printed (normalised case), e.g. ("T", "F")
    printed: str               # source text, e.g. "T / F"

    @property
    def description(self) -> str:
        return f"{FORMAT_LABELS[self.kind]} ({' / '.join(self.labels)})"


def _token(text: str) -> str:
    raw = text.strip().strip(".:")
    if len(raw) == 1:
        raw = _CONFUSABLE.get(raw, raw)
    return raw.casefold()


def _pair_regex() -> re.Pattern:
    words = sorted(
        {w for _, first, second, _, _ in _PAIRS for w in (*first, *second)}
        | set(_CONFUSABLE),
        key=len, reverse=True,
    )
    alternatives = "|".join(re.escape(w) for w in words)
    marker = f"[{re.escape(_MARKERS)}]*"
    return re.compile(
        rf"(?<![\w]){marker}\s*({alternatives})\.?\s*{marker}"
        rf"{_SEPARATORS}{marker}\s*({alternatives})\.?\s*{marker}(?![\w])",
        re.I,
    )


_PAIR = _pair_regex()


def _lookup(first: str, second: str) -> BinaryScale | None:
    a, b = _token(first), _token(second)
    for kind, firsts, seconds, label_a, label_b in _PAIRS:
        if a in firsts and b in seconds:
            # Single letters keep the printed (upper-case) letter.
            return BinaryScale(kind, (label_a, label_b), f"{first} / {second}")
    return None


def match_header(text: str) -> BinaryScale | None:
    """A line/table header consisting only of a binary pair (+ column words)."""
    clean = " ".join(str(text).split())
    if not clean or len(clean) > 80:
        return None
    for match in _PAIR.finditer(clean):
        rest = (clean[:match.start()] + " " + clean[match.end():]).strip()
        words = [w.casefold().strip("|:") for w in rest.split() if w.strip("|:")]
        if all(w in _HEADER_WORDS for w in words):
            scale = _lookup(match.group(1), match.group(2))
            if scale is not None:
                return BinaryScale(scale.kind, scale.labels, clean)
    return None


def split_row(text: str) -> tuple[str, BinaryScale | None]:
    """Strip a binary pair printed before or after an item's text."""
    clean = str(text).replace("\t", " ")  # keep spacing: "1  Item" numbering
    for match in _PAIR.finditer(clean):
        before, after = clean[:match.start()].strip(), clean[match.end():].strip()
        at_start = not before or before in {"|", "-"}
        at_end = not after.strip("|.")
        if not (at_start or at_end):
            continue
        scale = _lookup(match.group(1), match.group(2))
        if scale is None:
            continue
        rest = after if at_start else before
        if not _looks_like_columns(match):
            continue  # "… yes or no?" is question text, not answer columns
        if len(rest.split()) < 2:
            continue
        rest = (clean[match.end():] if at_start else clean[:match.start()]).strip(" |")
        return rest, BinaryScale(scale.kind, scale.labels, " ".join(match.group(0).split()))
    return str(text), None


def _looks_like_columns(match: re.Match) -> bool:
    first, second = match.group(1), match.group(2)
    between = match.string[match.end(1):match.start(2)].casefold()
    if re.search(r"\b(or|или|vai)\b", between):
        return False
    if len(first) == 1 and len(second) == 1:
        return True
    return first[:1].isupper() and second[:1].isupper()


# OCR often glues a speck to the T column ("tT F", "|T F", ".T F").
_NOISY_TRAILING_TF = re.compile(r"\s+[^\s\w]?[a-z|.,'`]{0,2}[TТ]\s*[|/]?\s*F[.,|]?\s*$")


def strip_noisy_row_pair(text: str) -> tuple[str, BinaryScale | None]:
    """Fallback for OCR rows whose trailing T / F letters are slightly garbled."""
    match = _NOISY_TRAILING_TF.search(str(text))
    if match is None:
        return str(text), None
    rest = str(text)[:match.start()].rstrip()
    if len(rest.split()) < 3:
        return str(text), None
    return rest, BinaryScale(TRUE_FALSE, ("T", "F"), " ".join(match.group(0).split()))


def match_instruction(text: str) -> BinaryScale | None:
    """Weak evidence: an instruction naming the two answers (never auto-applied)."""
    clean = " ".join(str(text).split())
    if len(clean) > 400 or not _INSTRUCTION_VERBS.search(clean):
        return None
    lowered = clean.casefold()
    for kind, first, second, label_a, label_b in _PAIRS:
        if len(first[0]) == 1:
            continue
        a = "|".join(re.escape(w) for w in first)
        b = "|".join(re.escape(w) for w in second)
        if re.search(rf"\b({a})\b.{{0,30}}\b({b})\b", lowered):
            return BinaryScale(kind, (label_a, label_b), clean[:160])
    return None


def legend_labels(text: str) -> dict[str, str]:
    """Letter → word definitions printed in the source, e.g. T = True."""
    found = {}
    for match in _LEGEND.finditer(str(text)):
        if match.group(1):
            found[match.group(1).upper()] = match.group(2).capitalize()
        else:
            found[match.group(4).upper()] = match.group(3).capitalize()
    return found


def expand_with_legend(scale: BinaryScale, legend: dict[str, str]) -> BinaryScale:
    """Use the document's own words for single-letter labels, when defined."""
    if not all(len(label) == 1 for label in scale.labels):
        return scale
    words = tuple(legend.get(label.upper()) for label in scale.labels)
    if all(words) and len(set(words)) == 2:
        return BinaryScale(scale.kind, words, scale.printed)
    return scale
