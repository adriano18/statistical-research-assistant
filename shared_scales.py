"""Link reconstructed matrices to questions and review shared response scales.

One coherent model replaces the former two parallel outputs: every item that
belongs to a row × column response table carries ``Candidate.scheme_id`` (the
instrument's :class:`ResponseScheme`) and ``Candidate.matrix_row`` (the
reconstructed matrix row). Matrices are linked only to the instrument version
whose page, item numbers and wording they match, so an original and a revised
version never share labels, codes or reverse keys.

Review is explicit and separate: structure (labels shared by all linked
items), numeric coding (codes exactly as printed) and reverse scoring (items
listed in the source). Any change of labels, codes, reverse items or scale
membership clears the confirmations.
"""

from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
import re

from scientific_survey_import import (
    Candidate, InstrumentCandidate, ResponseScheme, ScientificDocumentReview,
    linked_questions, proposed_scheme_question,
)
from repeated_choices import printed_label
from survey_storage import validate_questions

MATCH_THRESHOLD = 0.6


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", str(text).casefold()).strip()


def _compact(label: str) -> str:
    """Label comparison form: case, whitespace and apostrophe variants ignored."""
    return re.sub(r"\s+", "", printed_label(label)).casefold()


def _similar(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _manually_edited(row: Candidate) -> bool:
    return any("Edited manually" in note or "not a shared scale" in note for note in row.notes)


def _match_rows(instrument: InstrumentCandidate, matrix) -> list[tuple[int, object]]:
    """(question index, matrix row) pairs: same item number, page and wording."""
    used: set[int] = set()
    pairs = []
    for row in matrix.rows:
        best = None
        for index, candidate in enumerate(instrument.questions):
            if index in used:
                continue
            if row.number is not None and candidate.number != row.number:
                continue
            if matrix.source_kind != "docx_table" and row.page != candidate.page:
                continue
            score = _similar(row.prompt, candidate.question.get("prompt", ""))
            if score >= MATCH_THRESHOLD and (best is None or score > best[0]):
                best = (score, index)
        if best is not None:
            used.add(best[1])
            pairs.append((best[1], row))
    return pairs


def _matrix_labels(matrix, legend: dict[str, str]) -> tuple[tuple[str, ...], tuple[str, ...], list[str]]:
    printed = tuple(column.label.strip() for column in matrix.columns)
    issues = []
    abbreviations = [p for p in printed if re.fullmatch(r"[A-ZА-Я]{1,3}", p)]
    if abbreviations and len(abbreviations) == len(printed):
        if all(p in legend for p in printed):
            return tuple(legend[p] for p in printed), printed, issues
        issues.append("Column abbreviations " + " / ".join(printed)
                      + " are not defined in this document; enter the labels.")
    if any(not p for p in printed):
        issues.append("Some matrix columns have no printed label; enter them.")
    if any(column.ambiguous for column in matrix.columns):
        issues.append("Some column headers overlap neighbouring columns; check the labels.")
    return printed, printed, issues


def _cell_issues(matrix, pairs, instrument) -> list[str]:
    """Readable notes about unresolved cells of the linked rows only."""
    linked_rows = {row.id: instrument.questions[index].number for index, row in pairs}
    blank_columns = {
        c for c in range(len(matrix.columns))
        if all(not row.cells[c].text.strip() for row in matrix.rows)
    }
    notes = []
    for r, c in matrix.unresolved_cells:
        row = matrix.rows[r]
        if row.id not in linked_rows:
            continue
        label = matrix.columns[c].label or f"column {c + 1}"
        state = row.cells[c].state
        what = "could not be read (possibly dropped text)" if state == "missing" else (
            f"shows “{row.cells[c].text}”")
        notes.append(f"Item {linked_rows[row.id]}, {label}: {what}")
    if blank_columns and len(blank_columns) == len(matrix.columns):
        notes.append("All answer boxes are blank (expected for an unfilled form).")
    return notes


def link_matrices(review: ScientificDocumentReview) -> ScientificDocumentReview:
    """Attach every reconstructed matrix to its instrument's questions."""
    if not review.matrices or not review.instruments:
        return review
    instruments = list(review.instruments)
    for matrix in review.matrices:
        scored = []
        for i, instrument in enumerate(instruments):
            pairs = _match_rows(instrument, matrix)
            if len(pairs) >= max(2, (len(matrix.rows) + 1) // 2):
                scored.append((len(pairs), i, pairs))
        if not scored:
            continue
        _, i, pairs = max(scored, key=lambda item: item[0])
        instruments[i] = _merge_matrix(instruments[i], matrix, pairs)
    return replace(review, instruments=tuple(instruments))


def _merge_matrix(instrument: InstrumentCandidate, matrix, pairs) -> InstrumentCandidate:
    legend = dict(instrument.scale_legend)
    labels, printed, label_issues = _matrix_labels(matrix, legend)
    codes = tuple(column.code for column in matrix.columns)
    cell_notes = _cell_issues(matrix, pairs, instrument)
    questions = list(instrument.questions)
    schemes = {s.id: s for s in instrument.schemes}
    existing = {questions[index].scheme_id for index, _ in pairs if questions[index].scheme_id}
    target: ResponseScheme | None = None
    if len(existing) == 1:
        target = schemes[next(iter(existing))]
    if target is not None:
        merged_issues = list(target.issues)
        new_labels = target.labels
        if target.label_problems() and not label_issues and len(labels) == target.size:
            new_labels = labels  # the matrix header supplies missing labels
            merged_issues = [issue for issue in merged_issues
                             if "no printed label" not in issue and "not printed" not in issue]
        elif len(labels) == target.size and [_compact(l) for l in labels] != [
            _compact(l) for l in target.labels
        ] and not label_issues:
            merged_issues.append(
                "Matrix columns (" + " / ".join(labels) + ") differ from the header text; "
                "check which labels the source uses."
            )
        new_codes = target.codes
        if not target.has_codes and len(codes) == target.size and all(codes):
            new_codes = codes
        target = replace(
            target, labels=new_labels, codes=new_codes, matrix_id=matrix.id,
            evidence=target.evidence if "matrix" in target.evidence else target.evidence + "+matrix",
            issues=tuple(dict.fromkeys([*merged_issues, *cell_notes])),
        )
    else:
        numbers = tuple(questions[index].number for index, _ in pairs)
        target = ResponseScheme(
            f"s{len(schemes) + 1}", labels, printed,
            codes if len(codes) == len(labels) else (None,) * len(labels),
            "matrix", matrix.pages[0], f"matrix {matrix.id}", numbers,
            tuple(n for n in instrument.scoring.reverse_numbers if n in numbers),
            next((w for w in instrument.scoring.warnings if "revers" in w.lower()), ""),
            matrix.id, tuple(dict.fromkeys([*label_issues, *cell_notes])),
        )
    schemes[target.id] = target
    for index, row in pairs:
        question = questions[index]
        if question.scheme_id not in (None, target.id) or _manually_edited(question):
            continue
        if question.scheme_id is None and question.question.get("kind") != "short_text":
            continue  # already has its own choices (e.g. True/False)
        questions[index] = replace(
            question, scheme_id=target.id, matrix_row=f"{matrix.id}:{row.id}",
            question=proposed_scheme_question(question.question, target),
            notes=question.notes if question.scheme_id == target.id else (
                *question.notes, f"Linked to matrix {matrix.id} row {row.id}; "
                f"shared scale {target.id} proposed, not verified."),
        )
    # Refresh every linked proposal so labels supplied by the matrix appear.
    for index, question in enumerate(questions):
        if question.scheme_id == target.id:
            questions[index] = replace(
                question, question=proposed_scheme_question(question.question, target),
            )
    numbers = tuple(q.number for q in questions if q.scheme_id == target.id)
    if not numbers:
        return instrument  # every matched item already has its own choices
    schemes[target.id] = replace(target, items=numbers, reverse_items=tuple(
        n for n in (target.reverse_items or instrument.scoring.reverse_numbers) if n in numbers
    ))
    return replace(instrument, questions=tuple(questions), schemes=tuple(schemes.values()))


def _parse_codes(codes) -> tuple[str | None, ...]:
    out = []
    for code in codes:
        text = "" if code is None else str(code).strip()
        if text and not re.fullmatch(r"-?\d{1,3}", text):
            raise ValueError(f"Numeric code “{text}” must be an integer such as 1 or 0.")
        out.append(text or None)
    return tuple(out)


def review_scheme(
    candidate: InstrumentCandidate, scheme_id: str, *,
    labels, codes, reverse_items,
    structure: bool = False, numeric: bool = False, reverse: bool = False,
) -> InstrumentCandidate:
    """Apply a researcher's review of one shared scale to ALL its questions."""
    schemes = {s.id: s for s in candidate.schemes}
    if scheme_id not in schemes:
        raise KeyError("Select a detected response scale.")
    scheme = schemes[scheme_id]
    new_labels = tuple(" ".join(str(label).split()) for label in labels)
    if len(new_labels) != scheme.size:
        raise ValueError("Keep one label per category.")
    new_codes = _parse_codes(codes)
    if len(new_codes) != scheme.size:
        raise ValueError("Keep one code field per category.")
    linked = linked_questions(candidate, scheme_id)
    numbers = {candidate.questions[i].number for i in linked}
    new_reverse = tuple(sorted({int(n) for n in reverse_items}))
    if any(n not in numbers for n in new_reverse):
        raise ValueError("Reverse-keyed items must be questions on this scale.")
    updated = replace(
        scheme, labels=new_labels, codes=new_codes, reverse_items=new_reverse,
        structure_confirmed=False, codes_confirmed=False, reverse_confirmed=False,
    )
    if reverse and not numeric:
        raise ValueError("Confirm numeric coding before reverse scoring.")
    if numeric and not structure:
        raise ValueError("Confirm the scale structure before numeric coding.")
    if structure:
        problems = updated.label_problems()
        if problems:
            raise ValueError(" ".join(problems))
        updated = replace(updated, structure_confirmed=True)
    if numeric:
        if not updated.has_codes:
            raise ValueError("Enter a numeric code for every category (as printed in the source).")
        if len(set(updated.codes)) != len(updated.codes):
            raise ValueError("Numeric codes must be unique.")
        updated = replace(updated, codes_confirmed=True)
    if reverse:
        if not new_reverse:
            raise ValueError("List the reverse-keyed items documented in the source.")
        updated = replace(updated, reverse_confirmed=True)
    questions = list(candidate.questions)
    for index in linked:
        row = questions[index]
        questions[index] = replace(
            row, question=proposed_scheme_question(row.question, updated),
            confidence="review",
        )
    schemes[scheme_id] = updated
    result = replace(candidate, questions=tuple(questions), schemes=tuple(schemes.values()))
    if structure:
        from scientific_survey_import import draft_questions
        draft_questions(result)  # validates the full draft with these settings
    return result


def unlink_scheme(candidate: InstrumentCandidate, scheme_id: str) -> InstrumentCandidate:
    """Researcher decision: these items do not share a response scale."""
    linked = linked_questions(candidate, scheme_id)
    if not linked:
        raise KeyError("This scale has no linked questions.")
    questions = list(candidate.questions)
    for index in linked:
        row = questions[index]
        q = dict(row.question)
        for name in ("options", "value_labels", "scale_id"):
            q.pop(name, None)
        q.update({"kind": "short_text", "reverse_scored": False})
        questions[index] = replace(
            row, question=q, scheme_id=None, matrix_row=None,
            notes=(*row.notes, "Researcher marked this item as not a shared scale."),
        )
    return replace(
        candidate, questions=tuple(questions),
        schemes=tuple(s for s in candidate.schemes if s.id != scheme_id),
    )


def detach_question(candidate: InstrumentCandidate, index: int) -> InstrumentCandidate:
    """A manual per-question edit leaves the shared scale; confirmations reset."""
    row = candidate.questions[index]
    if row.scheme_id is None:
        return candidate
    questions = list(candidate.questions)
    questions[index] = replace(row, scheme_id=None)
    schemes = tuple(
        replace(s, structure_confirmed=False, codes_confirmed=False, reverse_confirmed=False,
                items=tuple(n for n in s.items if n != row.number))
        if s.id == row.scheme_id else s
        for s in candidate.schemes
    )
    return replace(candidate, questions=tuple(questions), schemes=schemes)


def scheme_summary(candidate: InstrumentCandidate, scheme: ResponseScheme) -> str:
    linked = linked_questions(candidate, scheme.id)
    numbers = [candidate.questions[i].number for i in linked]
    span = f"{min(numbers)}–{max(numbers)}" if numbers else "none"
    state = ("structure confirmed" if scheme.structure_confirmed else "NOT verified")
    if scheme.codes_confirmed:
        state += ", codes confirmed"
    if scheme.reverse_confirmed:
        state += ", reverse scoring confirmed"
    return (
        f"{len(linked)} linked questions (items {span}) · {scheme.size} categories · "
        f"evidence: {scheme.evidence} on page {scheme.page}"
        + (f" · matrix {scheme.matrix_id}" if scheme.matrix_id else "")
        + f" · {state}"
    )


__all__ = [
    "link_matrices", "review_scheme", "unlink_scheme", "detach_question",
    "scheme_summary", "validate_questions",
]
