"""Shared ordered response scales (frequency, agreement, intensity).

Pure text helpers used by the scientific importer:

* :func:`parse_legend` — abbreviation definitions printed in the source,
  e.g. ``O = Often   S = Sometimes`` or ``Often (O)``;
* :func:`parse_code_legend` — numeric anchors printed as ``1 = Never``;
* :func:`match_scale_header` — a header row naming 3–11 categories, either
  spelled out (``Never Rarely Sometimes Often``) or abbreviated (``O S R N``);
* :func:`split_row_tokens` — the answer tokens printed at the end of an item
  row (``… 1 2 3 4`` or ``… O S R N``).

Labels are kept exactly as printed (only whitespace is normalised). An
abbreviation becomes a word only when THIS document defines it; categories
of one instrument version are never borrowed from another. Nothing here
assigns scores: numeric codes are reported only when printed.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

# Spelled-out category phrases (casefolded). Longest phrases are tried first.
CATEGORY_PHRASES = tuple(sorted({
    # frequency
    "never", "almost never", "rarely", "seldom", "sometimes", "occasionally",
    "fairly often", "often", "very often", "always", "almost always", "usually",
    # agreement
    "strongly disagree", "disagree", "somewhat disagree", "slightly disagree",
    "neither agree nor disagree", "neutral", "undecided", "slightly agree",
    "somewhat agree", "agree", "strongly agree",
    # intensity
    "not at all", "a little", "slightly", "moderately", "quite a bit", "extremely",
    "very much",
    # Russian
    "никогда", "почти никогда", "редко", "иногда", "часто", "очень часто",
    "всегда", "почти всегда", "совершенно не согласен", "не согласен",
    "скорее не согласен", "затрудняюсь ответить", "скорее согласен",
    "согласен", "совершенно согласен", "полностью согласен",
    # Latvian
    "nekad", "gandrīz nekad", "reti", "dažreiz", "dažkārt", "bieži",
    "ļoti bieži", "vienmēr", "gandrīz vienmēr", "pilnībā nepiekrītu",
    "nepiekrītu", "drīzāk nepiekrītu", "grūti pateikt", "drīzāk piekrītu",
    "piekrītu", "pilnībā piekrītu",
}, key=len, reverse=True))
GENERIC_HEADER_WORDS = {
    "statement", "statements", "item", "items", "question", "questions", "no",
    "no.", "nr", "nr.", "#", "№", "утверждение", "вопрос", "apgalvojums",
    "jautājums", "how", "often",
}
_ABBREVIATION = re.compile(r"^[A-ZА-ЯĀČĒĢĪĶĻŅŠŪŽ]{1,3}$")
_TOKEN = r"(?:\d{1,2}|[A-ZА-ЯĀČĒĢĪĶĻŅŠŪŽ]{1,3}|[○◯□☐●])"
_ROW_TOKENS = re.compile(rf"^(?P<rest>.*?\S)\s+(?P<tokens>(?:{_TOKEN}\s+){{2,10}}{_TOKEN})\s*$")
_LEGEND = re.compile(
    r"(?<![\w])(?P<abbr>[A-ZА-ЯĀČĒĢĪĶĻŅŠŪŽ]{1,3})\s*(?:=|–|—|-|:)\s*"
    r"(?P<label>[^\W\d_][^=:–—\n]*?)"
    r"(?=\s+[A-ZА-ЯĀČĒĢĪĶĻŅŠŪŽ]{1,3}\s*(?:=|–|—|-|:)|\s*[,;]|\s*\.?\s*$)"
)
_LEGEND_PAREN = re.compile(
    r"(?P<label>[^\W\d_][^\W\d_ ]*(?: [^\W\d_]+)?)\s*\(\s*(?P<abbr>[A-ZА-Я]{1,3})\s*\)"
)
_CODE_LEGEND = re.compile(
    r"(?<![\w])(?P<code>-?\d{1,2})\s*(?:=|–|—|:)\s*(?P<label>[^\W\d_][^=:–—\n]*?)"
    r"(?=\s+-?\d{1,2}\s*(?:=|–|—|:)|\s*[,;]|\s*\.?\s*$)"
)


@dataclass(frozen=True)
class ScaleHeader:
    printed: tuple[str, ...]        # tokens as printed: ("O", "S", "R", "N")
    labels: tuple[str, ...]         # documented labels (legend applied)
    abbreviated: bool               # printed tokens were abbreviations
    defined: bool                   # every abbreviation is defined in the source
    text: str                       # the header line
    uncertain: tuple[str, ...] = ()  # printed labels that may be incomplete


def _clean(text: str) -> str:
    return " ".join(str(text).split())


def parse_legend(text: str) -> dict[str, str]:
    """Abbreviation → label as printed in this line (``O = Often``)."""
    clean = _clean(text)
    found: dict[str, str] = {}
    for match in _LEGEND.finditer(clean):
        label = match.group("label").strip(" .,;")
        if 1 <= len(label) <= 40 and len(label.split()) <= 5:
            found[match.group("abbr")] = label
    for match in _LEGEND_PAREN.finditer(clean):
        found.setdefault(match.group("abbr"), match.group("label").strip())
    # A single "X = word" pair is too weak to be a response legend.
    return found if len(found) >= 2 else {}


def parse_code_legend(text: str) -> dict[str, str]:
    """Numeric anchor → label (``1 = Never  2 = Rarely``); ≥ 2 pairs."""
    clean = _clean(text)
    found = {
        m.group("code"): m.group("label").strip(" .,;")
        for m in _CODE_LEGEND.finditer(clean)
        if 1 <= len(m.group("label").strip()) <= 40
    }
    return found if len(found) >= 2 else {}


def _phrases(text: str) -> list[tuple[str, str]] | None:
    """Split a header into (kind, printed) tokens or None if not a header."""
    words = _clean(text).split()
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(words):
        matched = None
        for phrase in CATEGORY_PHRASES:
            size = phrase.count(" ") + 1
            candidate = " ".join(words[i:i + size])
            if candidate.casefold().strip(".,;:") == phrase:
                matched = (size, candidate.strip(".,;:"))
                break
        if matched:
            tokens.append(("word", matched[1]))
            i += matched[0]
            continue
        word = words[i].strip(".,;:|")
        if _ABBREVIATION.fullmatch(word):
            tokens.append(("abbr", word))
        elif re.fullmatch(r"[A-ZА-ЯĀ-Ž][^\W\d_]{2,15}", word):
            tokens.append(("unknown", word))  # e.g. first line of "Almost / never"
        elif word.casefold() in GENERIC_HEADER_WORDS and not tokens:
            pass  # leading column title such as "Statement"
        elif word in {"|", "/", "-", "–"}:
            pass
        else:
            return None
        i += 1
    return tokens


def match_scale_header(text: str, legend: dict[str, str] | None = None) -> ScaleHeader | None:
    """A header row with 3–11 response categories, or None."""
    clean = _clean(text)
    if not clean or len(clean) > 160:
        return None
    tokens = _phrases(clean)
    if not tokens or not 3 <= len(tokens) <= 11:
        return None
    printed = tuple(t for _, t in tokens)
    if len({p.casefold() for p in printed}) != len(printed):
        return None
    unknown = tuple(t for kind, t in tokens if kind == "unknown")
    words = sum(1 for kind, _ in tokens if kind == "word")
    # One unrecognised capitalised word is tolerated among ≥ 3 known labels
    # (two-line headers such as "Almost / never" lose their second line).
    if unknown and (len(unknown) > 1 or words < 3):
        return None
    abbreviated = any(kind == "abbr" for kind, _ in tokens)
    if abbreviated and (words or unknown):
        return None  # mixed rows are prose or tables we do not trust
    legend = legend or {}
    if abbreviated:
        defined = all(p in legend for p in printed)
        labels = tuple(legend[p] for p in printed) if defined else printed
    else:
        defined, labels = True, printed
    return ScaleHeader(printed, labels, abbreviated, defined, clean, unknown)


def split_row_tokens(text: str) -> tuple[str, tuple[str, ...]]:
    """Strip answer tokens printed at the end of an item row."""
    match = _ROW_TOKENS.match(str(text).rstrip())
    if not match:
        return str(text), ()
    rest = match.group("rest")
    if len(rest.split()) < 3:
        return str(text), ()
    return rest, tuple(match.group("tokens").split())


def _token_matches(token: str, key: str) -> bool:
    clean = token.strip(".,;:|()[]{}")
    return clean == key or (clean[:1].upper() == key[:1] and clean.casefold().startswith(key.casefold()[:1])
                            and len(clean) <= len(key) + 1 and clean[:1].isupper())


def match_legend_header(text: str, legend: dict[str, str]) -> ScaleHeader | None:
    """OCR-tolerant abbreviation header ordered like THIS document's legend.

    ``ie) Ss R N`` with legend O/S/R/N becomes O/S/R/N when the token count
    matches and at least half of the tokens agree with the legend keys at
    their positions. Garbled tokens are reported as uncertain.
    """
    keys = list(legend)
    tokens = _clean(text).split()
    if len(keys) < 3 or len(tokens) != len(keys) or len(_clean(text)) > 60:
        return None
    exact = sum(1 for token, key in zip(tokens, keys) if token.strip(".,;:|") == key)
    close = sum(1 for token, key in zip(tokens, keys) if _token_matches(token, key))
    if exact < 1 or close < (len(keys) + 1) // 2 or any(len(t) > 4 for t in tokens):
        return None
    uncertain = tuple(t for t, k in zip(tokens, keys) if t.strip(".,;:|") != k)
    return ScaleHeader(tuple(keys), tuple(legend[k] for k in keys), True, True,
                       _clean(text), uncertain)


def strip_trailing_scale_tokens(text: str, printed: tuple[str, ...]) -> tuple[str, bool]:
    """Remove a (possibly OCR-garbled) copy of the header at a row's end."""
    words = str(text).rstrip().split()
    size = len(printed)
    if len(words) <= size + 2:
        return str(text), False
    tail = words[-size:]
    close = sum(1 for token, key in zip(tail, printed) if _token_matches(token, key))
    if close >= (size + 1) // 2 and all(len(t) <= 4 for t in tail):
        return " ".join(words[:-size]), True
    return str(text), False


def normalize_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Repair OCR look-alikes in code rows: ``I 2 3 4`` → ``1 2 3 4``."""
    digits = sum(1 for t in tokens if re.fullmatch(r"-?\d{1,2}", t))
    if digits < max(2, len(tokens) - 1):
        return tokens
    fixes = {"I": "1", "l": "1", "|": "1", "O": "0", "o": "0"}
    return tuple(fixes.get(t, t) for t in tokens)


def codes_line(text: str, size: int) -> tuple[str, ...] | None:
    """A line holding only ``size`` integer codes, e.g. ``1 2 3 4``."""
    tokens = _clean(text).split()
    if len(tokens) == size and all(re.fullmatch(r"-?\d{1,2}", t) for t in tokens):
        return tuple(tokens)
    return None
