"""Local-first survey definitions and responses in the ignored data/ directory.

No network server, analytics, IP collection, email, or third-party account.
Definitions become immutable after creation. Responses are SQLite transactions.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid
from typing import Any

import pandas as pd


NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
ALLOWED_TYPES = {"likert5", "single_choice", "number", "short_text", "consent"}


@dataclass(frozen=True)
class SurveyDefinition:
    survey_id: str
    title: str
    description: str
    questions: tuple[dict[str, Any], ...]


def validate_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not 1 <= len(questions) <= 40:
        raise ValueError("Create between 1 and 40 questions.")
    normalized = []
    seen = set()
    for item in questions:
        key = str(item.get("key", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        kind = str(item.get("kind", "")).strip()
        required = bool(item.get("required", False))
        if not NAME_PATTERN.fullmatch(key) or key.lower() in {
            "response_id", "submitted_at", "survey_id",
        }:
            raise ValueError(f"Invalid question variable: {key}")
        if key in seen:
            raise ValueError(f"Duplicate question variable: {key}")
        if not 2 <= len(prompt) <= 300:
            raise ValueError(f"Question {key} needs a prompt of 2–300 characters.")
        if kind not in ALLOWED_TYPES:
            raise ValueError(f"Unsupported question type: {kind}")
        options = [str(v).strip() for v in item.get("options", [])]
        if kind == "single_choice":
            if not 2 <= len(options) <= 12:
                raise ValueError("Multiple choice needs 2–12 options.")
            if any(not v or len(v) > 120 for v in options):
                raise ValueError("Choice labels must be 1–120 characters.")
            if len(options) != len(set(options)):
                raise ValueError("Choice options must be unique.")
        elif options:
            raise ValueError("Only single-choice questions may specify options.")
        if kind == "consent" and not required:
            raise ValueError("Consent questions must be required.")
        normalized.append({
            "key": key, "prompt": prompt, "kind": kind,
            "required": required, "options": options,
        })
        seen.add(key)
    return normalized


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
    with sqlite3.connect(path) as db:
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
    with sqlite3.connect(path) as db:
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
            # An unrelated or damaged file cannot prevent opening the app.
            continue
    return results


def _clean_answer(question: dict[str, Any], answer: Any) -> Any:
    kind = question["kind"]
    if answer is None or (isinstance(answer, str) and not answer.strip()):
        if question["required"]:
            raise ValueError(f"Required question not answered: {question['key']}")
        return None
    if kind == "likert5":
        if isinstance(answer, bool) or str(answer) not in {"1", "2", "3", "4", "5"}:
            raise ValueError(f"Choose 1–5 for {question['key']}.")
        return int(answer)
    if kind == "single_choice":
        if not isinstance(answer, str) or answer not in question["options"]:
            raise ValueError(f"Choose a listed option for {question['key']}.")
        return answer
    if kind == "number":
        if isinstance(answer, bool):
            raise ValueError(f"Numeric answer required for {question['key']}.")
        try:
            number = float(str(answer).strip())
        except (ValueError, TypeError) as err:
            raise ValueError(f"Numeric answer required for {question['key']}.") from err
        if not math.isfinite(number) or abs(number) > 1e12:
            raise ValueError(f"Invalid numeric answer for {question['key']}.")
        return number
    if kind == "short_text":
        if not isinstance(answer, str) or len(answer.strip()) > 500:
            raise ValueError(f"Text too long or invalid for {question['key']}.")
        return answer.strip()
    if kind == "consent":
        if answer is not True:
            raise ValueError("Consent must be explicitly confirmed before submission.")
        return 1
    raise ValueError(f"Unknown question type: {kind}")


def submit_response(
    root: str | Path, survey_id: str, answers: dict[str, Any]
) -> str:
    definition = get_survey(root, survey_id)
    known = {q["key"] for q in definition.questions}
    if not isinstance(answers, dict) or set(answers) - known:
        raise ValueError("Response includes unknown fields.")
    cleaned = {
        q["key"]: _clean_answer(q, answers.get(q["key"]))
        for q in definition.questions
    }
    response_id = uuid.uuid4().hex
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db_path = _database(Path(root).expanduser().resolve(), survey_id)
    with sqlite3.connect(db_path, timeout=10) as db:
        db.execute(
            "INSERT INTO responses VALUES (?, ?, ?)",
            (response_id, stamp, json.dumps(cleaned, ensure_ascii=False)),
        )
    return response_id


def response_count(root: str | Path, survey_id: str) -> int:
    db_path = _database(Path(root).expanduser().resolve(), survey_id)
    with sqlite3.connect(db_path) as db:
        return int(db.execute("SELECT COUNT(*) FROM responses").fetchone()[0])


def responses_dataframe(
    root: str | Path, survey_id: str
) -> pd.DataFrame:
    definition = get_survey(root, survey_id)
    db_path = _database(Path(root).expanduser().resolve(), survey_id)
    with sqlite3.connect(db_path) as db:
        data = db.execute(
            "SELECT response_id, answers_json FROM responses "
            "ORDER BY submitted_at, response_id"
        ).fetchall()
    rows = []
    for response_id, encoded in data:
        answers = json.loads(encoded)
        rows.append({
            "response_id": response_id,
            **{q["key"]: answers.get(q["key"]) for q in definition.questions},
        })
    frame = pd.DataFrame(
        rows, columns=["response_id", *[q["key"] for q in definition.questions]]
    )
    for q in definition.questions:
        if q["kind"] in {"likert5", "number", "consent"}:
            frame[q["key"]] = pd.to_numeric(frame[q["key"]], errors="coerce")
    return frame


def save_survey_csv(
    root: str | Path, survey_id: str, path: str | Path
) -> Path:
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
