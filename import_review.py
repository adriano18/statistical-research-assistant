"""Review sessions of the scientific import wizard (Stage 36.5 UI).

**Autosave and resume.** The researcher's review of one document — the
form chosen, the wizard step, the items compared with the source, wording
corrections, response-scale reviews, the confirmations, the last selected
item and where the document was opened from — is kept in the
application's data folder beside the surveys,
``<data>/import_sessions/<sha256>.json``. The file is keyed by the SHA-256
of the document's bytes and written atomically (a temporary file, then a
rename) after every change. Nothing leaves the computer and nothing is
written into the program or the repository.

A saved review is the researcher's own actions, replayed on a fresh
reading of the same bytes:

* it never holds a confirmation the researcher did not give (only the
  values of their own clicks, and scale reviews exactly as they applied
  them);
* it is never applied to a changed document — another SHA-256 is another
  file name;
* a form whose fresh reading differs from the one reviewed (another
  fingerprint: other items, wording or scales, e.g. after an OCR engine
  update) is not restored.

**Scans.** :func:`scanned_pages` tells a PDF without any text layer (a
scan) from one whose text can suggest the OCR language, so that the
wizard can ask for the language before local OCR runs.

The import engine (``scientific_survey_import``, ``table_forms``,
``ocr_table_rows``) is used read-only here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

SESSION_VERSION = 1
FOLDER = "import_sessions"
STEPS = ("source", "scale", "items", "confirm")
CONFIRMATIONS = ("version", "rights", "items")
ACTIONS = ("wording", "scale", "not_shared")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_LANGUAGE = re.compile(r"^[a-z]{3}(\+[a-z]{3}){0,3}$")


def _int(value) -> bool:
    """A JSON integer (``true`` is not an item number)."""
    return isinstance(value, int) and not isinstance(value, bool)


def source_sha256(binary: bytes) -> str:
    """The identity of a document: the SHA-256 of its bytes."""
    return hashlib.sha256(binary).hexdigest()


def sessions_folder(survey_root: Path) -> Path:
    """``<data>/import_sessions``: beside ``surveys`` and ``projects``."""
    return Path(survey_root).parent / FOLDER


def form_fingerprint(instrument) -> str:
    """What the researcher reviewed: the form's items (number, page,
    wording, answer type, scale link) and its scales, as first read."""
    data = {
        "title": instrument.title,
        "items": [[row.number, row.page, row.question.get("prompt", ""),
                   row.question.get("kind", ""), row.scheme_id]
                  for row in instrument.questions],
        "scales": [[scheme.id, list(scheme.labels), [c or "" for c in scheme.codes],
                    scheme.evidence] for scheme in instrument.schemes],
    }
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_action(action) -> dict | None:
    """One recorded action with checked types, or None (never trusted blindly)."""
    if not isinstance(action, dict) or action.get("do") not in ACTIONS:
        return None
    kind = action["do"]
    if kind == "wording":
        if not _int(action.get("index")) or not isinstance(action.get("prompt"), str):
            return None
        return {"do": kind, "index": action["index"], "prompt": action["prompt"]}
    if not isinstance(action.get("scheme"), str):
        return None
    if kind == "not_shared":
        return {"do": kind, "scheme": action["scheme"]}
    labels, codes = action.get("labels"), action.get("codes")
    reverse = action.get("reverse_items", [])
    if not (isinstance(labels, list) and all(isinstance(x, str) for x in labels)
            and isinstance(codes, list) and all(isinstance(x, str) for x in codes)
            and isinstance(reverse, list) and all(_int(x) for x in reverse)):
        return None
    flags = {name: action.get(name) is True for name in ("structure", "numeric", "reverse")}
    return {"do": kind, "scheme": action["scheme"], "labels": labels, "codes": codes,
            "reverse_items": reverse, **flags}


@dataclass
class FormReview:
    """The researcher's review of one form of the document."""

    fingerprint: str
    title: str = ""
    count: int = 0
    reviewed: tuple[int, ...] = ()            # item indices compared with the source
    checks: dict = field(default_factory=dict)  # version / rights / items
    actions: tuple[dict, ...] = ()            # wording and scale reviews, in order

    def to_json(self) -> dict:
        return {"fingerprint": self.fingerprint, "title": self.title, "count": self.count,
                "reviewed": sorted(self.reviewed), "checks": dict(self.checks),
                "actions": list(self.actions)}

    @classmethod
    def from_json(cls, data) -> "FormReview":
        if not isinstance(data, dict) or not isinstance(data.get("fingerprint"), str):
            raise ValueError("form review without a fingerprint")
        count = data.get("count") if _int(data.get("count")) else 0
        reviewed = tuple(sorted({i for i in data.get("reviewed") or ()
                                 if _int(i) and 0 <= i < count}))
        checks = {key: True for key in CONFIRMATIONS
                  if isinstance(data.get("checks"), dict) and data["checks"].get(key) is True}
        actions = tuple(a for a in map(_clean_action, data.get("actions") or ()) if a)
        return cls(data["fingerprint"], str(data.get("title") or ""), count, reviewed,
                   checks, actions)


@dataclass
class ReviewRecord:
    """One document's review session, as kept on disk."""

    sha256: str
    filename: str
    path: str | None = None                  # where the document was opened from
    ocr_language: str | None = None          # the OCR language of the reading
    ocr_pages: tuple[int, ...] = ()          # pages read with "OCR this page"
    chosen: int | None = None                # the form under review
    step: str = "source"
    selected: int | None = None              # the last selected item
    forms: dict[int, FormReview] = field(default_factory=dict)
    saved_at: str = ""

    @property
    def checked(self) -> int:
        """Items of the chosen form compared with the source."""
        form = self.forms.get(self.chosen) if self.chosen is not None else None
        return len(form.reviewed) if form else 0

    @property
    def total(self) -> int:
        form = self.forms.get(self.chosen) if self.chosen is not None else None
        return form.count if form else 0

    def to_json(self) -> dict:
        return {
            "version": SESSION_VERSION, "sha256": self.sha256, "file": self.filename,
            "path": self.path, "ocr_language": self.ocr_language,
            "ocr_pages": list(self.ocr_pages), "chosen": self.chosen, "step": self.step,
            "selected": self.selected, "saved_at": self.saved_at,
            "forms": {str(index): form.to_json() for index, form in sorted(self.forms.items())},
        }

    @classmethod
    def from_json(cls, data) -> "ReviewRecord":
        if not isinstance(data, dict) or data.get("version") != SESSION_VERSION:
            raise ValueError("not a review session of this version")
        sha = data.get("sha256")
        if not isinstance(sha, str) or not _SHA.match(sha):
            raise ValueError("review session without a document identity")
        forms = {}
        for key, value in (data.get("forms") or {}).items():
            if str(key).isdigit():
                forms[int(key)] = FormReview.from_json(value)
        chosen = data.get("chosen") if _int(data.get("chosen")) else None
        selected = data.get("selected") if _int(data.get("selected")) else None
        step = data.get("step") if data.get("step") in STEPS else "source"
        path = data.get("path") if isinstance(data.get("path"), str) and data["path"] else None
        language = data.get("ocr_language")
        pages = tuple(p for p in data.get("ocr_pages") or () if _int(p) and p > 0)
        return cls(sha, str(data.get("file") or ""), path,
                   language if isinstance(language, str) and _LANGUAGE.match(language) else None,
                   pages,
                   chosen if chosen in forms else None, step, selected, forms,
                   str(data.get("saved_at") or ""))


_HASHES: dict[tuple, str] = {}


def file_sha256(path: Path) -> str | None:
    """SHA-256 of the file at ``path`` (cached by size and modification
    time), or None when it cannot be read."""
    try:
        status = path.stat()
        key = (str(path), status.st_size, status.st_mtime_ns)
        if key not in _HASHES:
            if not 0 < status.st_size <= 20_000_000:
                return None
            _HASHES[key] = source_sha256(path.read_bytes())
        return _HASHES[key]
    except OSError:
        return None


class ReviewStore:
    """Review sessions in one folder, one JSON file per document."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def path(self, sha: str) -> Path:
        if not _SHA.match(sha or ""):
            raise ValueError("A review session is named by the document's SHA-256.")
        return self.folder / f"{sha}.json"

    def load(self, sha: str) -> ReviewRecord | None:
        """The saved review of the document ``sha``, or None (missing,
        unreadable or not a review of exactly this document)."""
        try:
            data = json.loads(self.path(sha).read_text(encoding="utf-8"))
            record = ReviewRecord.from_json(data)
        except (OSError, ValueError):
            return None
        return record if record.sha256 == sha else None

    def save(self, record: ReviewRecord) -> bool:
        """Write ``record`` atomically; False (and nothing half-written)
        when the folder cannot be written. Never raises for I/O."""
        record.saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        target = self.path(record.sha256)
        temporary = target.with_name(f".{target.stem}.{os.getpid()}.tmp")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(record.to_json(), ensure_ascii=False, indent=1),
                                 encoding="utf-8")
            os.replace(temporary, target)
            return True
        except OSError:
            try:
                temporary.unlink()
            except OSError:
                pass
            return False

    def remove(self, sha: str) -> None:
        try:
            self.path(sha).unlink()
        except (OSError, ValueError):
            pass

    def records(self) -> list[ReviewRecord]:
        """Every readable review, the most recently saved first."""
        found = []
        try:
            names = sorted(self.folder.glob("*.json"))
        except OSError:
            return []
        for name in names:
            record = self.load(name.stem)
            if record is not None:
                found.append(record)
        return sorted(found, key=lambda r: r.saved_at, reverse=True)

    def resumable(self) -> list[ReviewRecord]:
        """Reviews whose document is still at its path, unchanged."""
        return [record for record in self.records()
                if record.path and file_sha256(Path(record.path)) == record.sha256]


def scanned_pages(binary: bytes) -> tuple[int, ...]:
    """Pages of a PDF without any text layer that draw a large image: a
    scan, whose language no text can suggest for OCR. Empty when a page has
    text, when no page is an image, or when the PDF cannot be inspected
    (the regular reading then decides, with OCR where it applies)."""
    from io import BytesIO

    from pypdf import PdfReader

    from import_session import AUTO_OCR_MIN_IMAGE_SHARE
    from visual_survey_review import pdf_image_coverage

    try:
        reader = PdfReader(BytesIO(binary))
        if reader.is_encrypted:
            return ()
        for page in reader.pages:
            if (page.extract_text() or "").strip():
                return ()
        shares = pdf_image_coverage(binary)
    except Exception:
        return ()
    return tuple(page for page, share in sorted(shares.items())
                 if share >= AUTO_OCR_MIN_IMAGE_SHARE)


# ------------------------------------------------------------- OCR language
OCR_CHOICES = ("eng", "lav", "rus", "lav+eng", "rus+eng", "lav+rus+eng")
DEFAULT_OCR = {"en": "eng", "lv": "lav", "ru": "rus"}


def ocr_language_used(review) -> str | None:
    """The OCR language a reading used, as its OCR note states it."""
    for warning in getattr(review, "warnings", ()) or ():
        match = re.search(r"Language: ([a-z+]+)\.", str(warning))
        if match:
            return match[1]
    return None
