"""Local-first survey schemas, conditional answers, and SQLite responses.

Survey definitions are immutable after creation. Editing happens in the draft
editor, before saving; existing surveys/responses remain backwards compatible.
No networking or automatic upload is performed by this module.
"""

from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid
from typing import Any

import pandas as pd


NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
ALLOWED_TYPES = {
    "likert5", "likert7", "single_choice", "multiple_choice", "yes_no",
    "number", "short_text", "long_text", "date", "consent",
}
CONDITION_OPS = {"equals", "not_equals", "greater", "less"}


@dataclass(frozen=True)
class SurveyDefinition:
    survey_id: str
    title: str
    description: str
    questions: tuple[dict[str, Any], ...]


def _check_condition(condition, earlier: dict[str, dict]) -> dict | None:
    if condition is None or condition == {}:
        return None
    if not isinstance(condition, dict):
        raise ValueError("Visibility condition must be a structured rule.")
    if set(condition) != {"question", "operator", "value"}:
        raise ValueError("Use question, operator, value for a conditional rule.")
    parent = str(condition["question"])
    if parent not in earlier:
        raise ValueError(
            "Conditional question must depend on an EARLIER question "
            "(not itself or a later question)."
        )
    kind = earlier[parent]["kind"]
    op = str(condition["operator"])
    if op not in CONDITION_OPS:
        raise ValueError("Unsupported visibility condition operator.")
    if kind not in {"single_choice", "yes_no", "likert5", "likert7", "number"}:
        raise ValueError("Conditions require a choice or numeric earlier question.")
    if kind in {"single_choice", "yes_no"}:
        if op not in {"equals", "not_equals"}:
            raise ValueError("Choice conditions support equals / not_equals only.")
        allowed = earlier[parent]["options"] if kind == "single_choice" else ["Yes", "No"]
        value = str(condition["value"])
        if value not in allowed:
            raise ValueError("Conditional value must be a listed answer option.")
    else:
        try:
            value = float(condition["value"])
        except (TypeError, ValueError) as err:
            raise ValueError("Numeric conditional value is invalid.") from err
        if not math.isfinite(value):
            raise ValueError("Numeric conditional value must be finite.")
        if kind.startswith("likert") and not (1 <= value <= int(kind[-1])):
            raise ValueError("Likert conditional value is outside response scale.")
    return {"question": parent, "operator": op, "value": value}


def validate_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not 1 <= len(questions) <= 40:
        raise ValueError("Create between 1 and 40 questions.")
    normalized: list[dict[str, Any]] = []
    earlier = {}
    page_titles: dict[int, str] = {}
    previous_page = 1
    for item in questions:
        if not normalized and item.get("page", 1) != 1:
            raise ValueError("The questionnaire must start on page 1.")
        key = str(item.get("key", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        kind = str(item.get("kind", "")).strip()
        required = bool(item.get("required", False))
        if not NAME_PATTERN.fullmatch(key) or key.lower() in {
            "response_id", "submitted_at", "survey_id",
        }:
            raise ValueError(f"Invalid question variable: {key}")
        if key in earlier:
            raise ValueError(f"Duplicate question variable: {key}")
        if not 2 <= len(prompt) <= 300:
            raise ValueError(f"Question {key} needs a prompt of 2–300 characters.")
        if kind not in ALLOWED_TYPES:
            raise ValueError(f"Unsupported question type: {kind}")
        options = [str(x).strip() for x in item.get("options", [])]
        if kind in {"single_choice", "multiple_choice"}:
            if not 2 <= len(options) <= 12:
                raise ValueError("Choice questions need 2–12 options.")
            if any(not v or len(v) > 120 for v in options):
                raise ValueError("Choice labels must be 1–120 characters.")
            if len(options) != len(set(options)):
                raise ValueError("Choice options must be unique.")
        elif options:
            raise ValueError("Only choice questions may specify options.")
        if kind == "consent" and not required:
            raise ValueError("Consent questions must be required.")
        section = str(item.get("section", "")).strip()
        if len(section) > 80:
            raise ValueError("Section name must be no longer than 80 characters.")
        page = item.get("page", 1)
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 20:
            raise ValueError("Page must be an integer from 1 to 20.")
        if page < previous_page or page > previous_page + 1:
            raise ValueError("Question pages must be consecutive and in order.")
        previous_page = page
        page_title = str(item.get("page_title", "")).strip()
        if len(page_title) > 80:
            raise ValueError("Page title must be 80 characters or shorter.")
        if page_title:
            if page_titles.get(page, page_title) != page_title:
                raise ValueError("Questions on the same page must share a page title.")
            page_titles[page] = page_title
        scale_id = str(item.get("scale_id", "")).strip()
        if scale_id and not NAME_PATTERN.fullmatch(scale_id):
            raise ValueError("Scale ID must be a valid variable-style name.")
        reversed_key = item.get("reverse_scored", False)
        if not isinstance(reversed_key, bool):
            raise ValueError("Reverse-scored flag must be True or False.")
        if reversed_key and kind not in {"likert5", "likert7"}:
            raise ValueError("Only Likert items can be marked reverse-scored.")
        if reversed_key and not scale_id:
            raise ValueError("Assign a scale ID to reverse-scored items.")
        raw_labels = item.get("value_labels") or {}
        if not isinstance(raw_labels, dict):
            raise ValueError("Value labels must map numeric codes to text.")
        value_labels: dict[str, str] = {}
        if raw_labels:
            if kind not in {"likert5", "likert7"}:
                raise ValueError("Value labels are supported for Likert items only.")
            expected = {str(n) for n in range(1, int(kind[-1]) + 1)}
            if set(raw_labels) != expected:
                raise ValueError("Provide a label for every numeric Likert code.")
            for n in range(1, int(kind[-1]) + 1):
                label = raw_labels[str(n)]
                if not isinstance(label, str) or not 1 <= len(label.strip()) <= 100:
                    raise ValueError("Value labels must be 1–100 characters.")
                value_labels[str(n)] = label.strip()
            if len(set(value_labels.values())) != len(value_labels):
                raise ValueError("Likert value labels must be distinct.")
        anchors = [
            str(item.get("min_label", "")).strip(),
            str(item.get("max_label", "")).strip(),
        ]
        if any(len(v) > 80 for v in anchors):
            raise ValueError("Scale anchor labels must be at most 80 characters.")
        condition = _check_condition(item.get("condition"), earlier)
        if kind == "consent" and condition is not None:
            raise ValueError("Consent questions cannot be conditional.")
        normalized_item = {
            "key": key, "prompt": prompt, "kind": kind,
            "required": required, "options": options,
            "section": section, "page": page, "page_title": page_title,
            "scale_id": scale_id, "reverse_scored": reversed_key,
            "min_label": anchors[0], "max_label": anchors[1],
            "value_labels": value_labels, "condition": condition,
        }
        normalized.append(normalized_item)
        earlier[key] = normalized_item
    # A page heading is shared by every question, even if entered only once.
    for q in normalized:
        q["page_title"] = page_titles.get(q["page"], "")
    return normalized


def likert_choices(question: dict[str, Any]) -> list[tuple[int, str]]:
    """Respondent labels with stable numeric storage codes, including old surveys."""
    kind = question["kind"]
    if kind not in {"likert5", "likert7"}:
        raise ValueError("Only Likert questions have numeric value labels.")
    maximum = int(kind[-1])
    labels = question.get("value_labels") or {}
    result = []
    for number in range(1, maximum + 1):
        label = labels.get(str(number), "")
        if not label and number == 1:
            label = question.get("min_label", "")
        if not label and number == maximum:
            label = question.get("max_label", "")
        result.append((number, f"{number} — {label}" if label else str(number)))
    return result


def reorder_questions(questions: list[dict[str, Any]], old: int, new: int) -> list[dict[str, Any]]:
    """Move a draft question safely, rejecting broken skip-logic or page order."""
    if not (0 <= old < len(questions) and 0 <= new < len(questions)):
        raise ValueError("Reorder position is outside the questionnaire.")
    candidate = [dict(q) for q in questions]
    candidate.insert(new, candidate.pop(old))
    return validate_questions(candidate)


def question_is_visible(question: dict, answers: dict[str, Any]) -> bool:
    """Safe non-executable visibility evaluation on already cleaned prior answers."""
    rule = question.get("condition")
    if not rule:
        return True
    parent = answers.get(rule["question"])
    if parent is None:
        return False  # Includes prior hidden questions: cascading visibility.
    op, compare = rule["operator"], rule["value"]
    if op == "equals":
        return parent == compare
    if op == "not_equals":
        return parent != compare
    if isinstance(parent, bool) or not isinstance(parent, (int, float)):
        return False
    return parent > compare if op == "greater" else parent < compare


def _database(root: Path, survey_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", survey_id):
        raise ValueError("Invalid survey identifier.")
    return root / f"survey_{survey_id}.sqlite3"


def create_survey(
    root: str | Path, title: str, description: str,
    questions: list[dict[str, Any]],
) -> SurveyDefinition:
    title = str(title).strip()
    description = str(description).strip()
    if not 3 <= len(title) <= 120 or len(description) > 2000:
        raise ValueError("Use a title of 3–120 and a description of up to 2,000 characters.")
    items = validate_questions(questions)
    directory = Path(root).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    survey_id = uuid.uuid4().hex
    definition = SurveyDefinition(survey_id, title, description, tuple(items))
    path = _database(directory, survey_id)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "CREATE TABLE survey (id TEXT PRIMARY KEY, title TEXT NOT NULL, "
            "description TEXT NOT NULL, questions_json TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE responses (response_id TEXT PRIMARY KEY, "
            "submitted_at TEXT NOT NULL, answers_json TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO survey VALUES (?, ?, ?, ?)",
            (survey_id, title, description, json.dumps(items, ensure_ascii=False)),
        )
    return definition


def get_survey(root: str | Path, survey_id: str) -> SurveyDefinition:
    path = _database(Path(root).expanduser().resolve(), survey_id)
    if not path.is_file():
        raise FileNotFoundError("Survey not found on this device.")
    with closing(sqlite3.connect(path)) as db:
        row = db.execute(
            "SELECT id, title, description, questions_json FROM survey"
        ).fetchone()
    if not row or row[0] != survey_id:
        raise ValueError("Survey definition is missing or inconsistent.")
    return SurveyDefinition(
        row[0], row[1], row[2],
        tuple(validate_questions(json.loads(row[3]))),
    )


def list_surveys(root: str | Path) -> list[SurveyDefinition]:
    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        return []
    results = []
    for path in sorted(directory.glob("survey_*.sqlite3")):
        survey_id = path.stem.removeprefix("survey_")
        try:
            results.append(get_survey(directory, survey_id))
        except (ValueError, sqlite3.DatabaseError, FileNotFoundError):
            continue
    return results


def _clean_answer(question: dict[str, Any], answer: Any) -> Any:
    kind = question["kind"]
    if answer is None or (isinstance(answer, str) and not answer.strip()) or (
        kind == "multiple_choice" and answer == []
    ):
        if question["required"]:
            raise ValueError(f"Required question not answered: {question['key']}")
        return None
    if kind.startswith("likert"):
        maximum = int(kind[-1])
        if isinstance(answer, bool) or str(answer) not in {
            str(n) for n in range(1, maximum + 1)
        }:
            raise ValueError(f"Choose 1–{maximum} for {question['key']}.")
        return int(answer)
    if kind == "single_choice":
        if not isinstance(answer, str) or answer not in question["options"]:
            raise ValueError(f"Choose a listed option for {question['key']}.")
        return answer
    if kind == "multiple_choice":
        if not isinstance(answer, list) or len(answer) != len(set(map(str, answer))):
            raise ValueError(f"Choose distinct listed options for {question['key']}.")
        if any(not isinstance(v, str) or v not in question["options"] for v in answer):
            raise ValueError(f"Choose listed options for {question['key']}.")
        return answer
    if kind == "yes_no":
        if answer not in ("Yes", "No"):
            raise ValueError(f"Choose Yes or No for {question['key']}.")
        return answer
    if kind == "number":
        if isinstance(answer, bool):
            raise ValueError(f"Numeric answer required for {question['key']}.")
        try:
            number = float(str(answer).strip())
        except (TypeError, ValueError) as err:
            raise ValueError(f"Numeric answer required for {question['key']}.") from err
        if not math.isfinite(number) or abs(number) > 1e12:
            raise ValueError(f"Invalid numeric answer for {question['key']}.")
        return number
    if kind in {"short_text", "long_text"}:
        limit = 500 if kind == "short_text" else 2000
        if not isinstance(answer, str) or len(answer.strip()) > limit:
            raise ValueError(f"Text too long or invalid for {question['key']}.")
        return answer.strip()
    if kind == "date":
        if not isinstance(answer, str):
            raise ValueError(f"Valid ISO date required for {question['key']}.")
        try:
            return date.fromisoformat(answer.strip()).isoformat()
        except ValueError as err:
            raise ValueError(f"Valid ISO date required for {question['key']}.") from err
    if kind == "consent":
        if answer is not True:
            raise ValueError("Consent must be explicitly confirmed before submission.")
        return 1
    raise ValueError(f"Unknown question type: {kind}")


def validate_page_answers(
    questions: list[dict[str, Any]], answers: dict[str, Any], current_page: int
) -> None:
    """Validate current and preceding pages before navigating forward."""
    cleaned: dict[str, Any] = {}
    for q in questions:
        if q.get("page", 1) > current_page:
            break
        if question_is_visible(q, cleaned):
            cleaned[q["key"]] = _clean_answer(q, answers.get(q["key"]))
        else:
            cleaned[q["key"]] = None


def submit_response(
    root: str | Path, survey_id: str, answers: dict[str, Any]
) -> str:
    definition = get_survey(root, survey_id)
    known = {q["key"] for q in definition.questions}
    if not isinstance(answers, dict) or set(answers) - known:
        raise ValueError("Response includes unknown fields.")
    cleaned: dict[str, Any] = {}
    for question in definition.questions:
        key = question["key"]
        if question_is_visible(question, cleaned):
            cleaned[key] = _clean_answer(question, answers.get(key))
        else:
            # Never treat a skipped question as zero, and do not trust stale UI
            # values sent for a field that is currently hidden.
            cleaned[key] = None
    response_id = uuid.uuid4().hex
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db_path = _database(Path(root).expanduser().resolve(), survey_id)
    with closing(sqlite3.connect(db_path, timeout=10)) as db, db:
        db.execute(
            "INSERT INTO responses VALUES (?, ?, ?)",
            (response_id, stamp, json.dumps(cleaned, ensure_ascii=False)),
        )
    return response_id


def response_count(root: str | Path, survey_id: str) -> int:
    db_path = _database(Path(root).expanduser().resolve(), survey_id)
    with closing(sqlite3.connect(db_path)) as db:
        return int(db.execute("SELECT COUNT(*) FROM responses").fetchone()[0])


def responses_dataframe(root: str | Path, survey_id: str) -> pd.DataFrame:
    definition = get_survey(root, survey_id)
    db_path = _database(Path(root).expanduser().resolve(), survey_id)
    with closing(sqlite3.connect(db_path)) as db:
        data = db.execute(
            "SELECT response_id, answers_json FROM responses ORDER BY rowid ASC"
        ).fetchall()
    rows = []
    for response_id, encoded in data:
        answers = json.loads(encoded)
        row = {
            "response_id": response_id,
            **{q["key"]: answers.get(q["key"]) for q in definition.questions},
        }
        for question in definition.questions:
            if question["kind"] == "multiple_choice":
                value = row[question["key"]]
                row[question["key"]] = (
                    json.dumps(value, ensure_ascii=False)
                    if value is not None else None
                )
        rows.append(row)
    frame = pd.DataFrame(
        rows, columns=["response_id", *[q["key"] for q in definition.questions]]
    )
    for q in definition.questions:
        if q["kind"] in {"likert5", "likert7", "number", "consent"}:
            frame[q["key"]] = pd.to_numeric(frame[q["key"]], errors="coerce")
    return frame


def survey_codebook(root: str | Path, survey_id: str) -> dict[str, Any]:
    definition = get_survey(root, survey_id)
    return {
        "survey_id": definition.survey_id,
        "title": definition.title,
        "description": definition.description,
        "response_id": "Random identifier, not an anonymization guarantee",
        "questions": [
            {**q, "measurement_level": (
                "ordinal" if q["kind"] in {"likert5", "likert7"}
                else "quantitative" if q["kind"] == "number"
                else "nominal"
            )}
            for q in definition.questions
        ],
        "scoring_note": (
            "Reverse-scored flags are METADATA ONLY. Raw responses have not "
            "been reversed, and scale totals have not been calculated."
        ),
    }


def save_survey_codebook(
    root: str | Path, survey_id: str, path: str | Path
) -> Path:
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != ".json" or not destination.parent.is_dir():
        raise ValueError("Choose an existing folder and a .json file.")
    destination.write_text(
        json.dumps(survey_codebook(root, survey_id), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def save_survey_csv(root: str | Path, survey_id: str, path: str | Path) -> Path:
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != ".csv":
        raise ValueError("Export must be a .csv file.")
    if not destination.parent.is_dir():
        raise FileNotFoundError("The chosen folder does not exist.")
    frame = responses_dataframe(root, survey_id)
    if frame.empty:
        raise ValueError("There are no responses to export.")
    frame.to_csv(destination, index=False, encoding="utf-8-sig")
    return destination
