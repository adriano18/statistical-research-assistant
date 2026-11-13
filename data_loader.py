"""Conservative local CSV/Excel/SPSS importer with actionable quality diagnostics.

The loader never executes spreadsheet macros, formulas or user-provided code.
Uncertain numbers remain text, never silently converted to analysis scores.

Stage 37 (#67): SPSS ``.sav``/``.zsav`` files are read with pyreadstat. Their
variable labels, value labels, user-missing codes and measurement levels come
in as metadata (``ImportReport.metadata``); user-missing values are missing
in the table, as SPSS treats them, and their codes stay in the metadata. A
CSV this program exported brings its codebook's metadata the same way.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from variable_rules import looks_like_identifier


SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xlsm", ".sav", ".zsav"}
SAV_EXTENSIONS = {".sav", ".zsav"}
# The first note of a .sav file this program exported (data_export.sav_notes).
SAV_EXPORT_MARK = "Statistical Research Assistant export"
ENCODINGS = ("utf-8-sig", "utf-16", "cp1257", "cp1251", "cp1252")
SEPARATORS = {"auto": None, "comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}
DECIMALS = {"auto", "dot", "comma"}
USER_MISSING = {"missing", "codes"}       # SPSS user-missing values (Stage 37)
DEFAULT_MISSING = ("", "NA", "N/A", "NULL")
MAX_BYTES = 150 * 1024 * 1024
MAX_CELLS = 5_000_000


@dataclass(frozen=True)
class ImportOptions:
    """Header row is 1-based. Sheet name or zero-based position for Excel."""
    sheet: str | int = 0
    header_row: int = 1
    data_start_row: int | None = None
    separator: str = "auto"
    encoding: str = "auto"
    decimal: str = "auto"
    missing_tokens: tuple[str, ...] = DEFAULT_MISSING
    # SPSS files: "missing" makes a user-missing value missing, as SPSS treats
    # it; "codes" keeps the code (-9, DK) as the value. Either way the codes
    # stay declared with the variable.
    user_missing: str = "missing"


@dataclass(frozen=True)
class ImportReport:
    rows: int
    columns: int
    source: str
    sheet: str | None
    header_row: int
    data_start_row: int
    encoding: str | None
    separator: str | None
    converted_columns: tuple[str, ...]
    warnings: tuple[str, ...]
    # Stage 37 (#67): what the file documents about its variables
    # ({variable: {"label", "value_labels", "missing_codes", "measure", "source"}}).
    metadata: dict | None = None

    def as_text(self) -> str:
        source_details = [f"{self.rows} rows × {self.columns} variables",
                          f"header row {self.header_row}",
                          f"data starts row {self.data_start_row}"]
        if self.sheet:
            source_details.append(f"sheet '{self.sheet}'")
        if self.encoding:
            source_details.append(f"encoding {self.encoding}")
        if self.separator:
            source_details.append(f"separator {self.separator!r}")
        lines = ["Import: " + " · ".join(source_details)]
        if self.converted_columns:
            lines.append("Numeric conversion: " + ", ".join(self.converted_columns))
        if self.metadata:
            lines.append(f"Labels, value labels or missing codes read for "
                         f"{len(self.metadata)} variable(s)")
        if self.warnings:
            lines.extend("Review: " + item for item in self.warnings)
        else:
            lines.append("No import warnings. Verify measurement scales before analysis.")
        return "\n".join(lines)


def _validate_options(options: ImportOptions) -> None:
    if isinstance(options.header_row, bool) or not isinstance(options.header_row, int):
        raise ValueError("Header row must be a positive whole number.")
    if not 1 <= options.header_row <= 100:
        raise ValueError("Header row must be between 1 and 100.")
    if options.data_start_row is not None and (
        isinstance(options.data_start_row, bool) or
        not isinstance(options.data_start_row, int) or
        not options.header_row < options.data_start_row <= 150
    ):
        raise ValueError("Data start row must be after the header row (2–150).")
    if options.separator not in SEPARATORS:
        raise ValueError("Separator must be auto, comma, semicolon, tab or pipe.")
    if options.encoding != "auto" and options.encoding not in ENCODINGS:
        raise ValueError("Choose a supported encoding.")
    if options.decimal not in DECIMALS:
        raise ValueError("Decimal style must be auto, dot or comma.")
    if options.user_missing not in USER_MISSING:
        raise ValueError("SPSS user-missing values are either missing or kept as codes.")
    if not isinstance(options.missing_tokens, tuple) or len(options.missing_tokens) > 20:
        raise ValueError("Supply at most 20 text markers for missing values.")
    if any(not isinstance(token, str) or len(token) > 60
           for token in options.missing_tokens):
        raise ValueError("Missing-value markers must be short strings.")


def workbook_sheets(path: str | Path) -> list[str]:
    """Expose sheet names, including non-first survey-response sheets."""
    file_path = Path(path).expanduser()
    if file_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        return []
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    with pd.ExcelFile(file_path, engine="openpyxl") as book:
        return list(book.sheet_names)


def _file_guard(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Supported file formats: .csv, .tsv, .xlsx, .xlsm, .sav")
    if not path.stat().st_size:
        raise ValueError("The selected file is empty.")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("File exceeds the 150 MB local import safety limit.")


def _read_text(path: Path, encoding: str) -> tuple[str, str, list[str]]:
    data = path.read_bytes()
    warnings: list[str] = []
    choices = [encoding] if encoding != "auto" else list(ENCODINGS)
    if encoding == "auto":
        # Only attempt UTF-16 for files that actually carry a UTF-16 BOM.
        if not data.startswith((b"\xff\xfe", b"\xfe\xff")):
            choices.remove("utf-16")
    for candidate in choices:
        try:
            text = data.decode(candidate, errors="strict")
            if candidate == "utf-16" and text.startswith("\ufeff"):
                text = text[1:]
            if candidate not in {"utf-8-sig", "utf-16"}:
                warnings.append(
                    f"Legacy encoding {candidate} selected. Confirm that Latvian/"
                    "Russian letters display correctly; change encoding if needed."
                )
            if "\x00" in text:
                raise ValueError("Binary or unsupported text encoding detected.")
            return text, candidate, warnings
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "File text could not be decoded. Select another CSV encoding or "
        "export as UTF-8 CSV from Excel."
    )


def _detect_separator(text: str, path: Path, setting: str) -> str:
    if setting != "auto":
        return SEPARATORS[setting] or ","
    if path.suffix.lower() == ".tsv":
        return "\t"
    sample = "\n".join(text.splitlines()[:30])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {mark: sample.count(mark) for mark in (",", ";", "\t", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] else ","


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _undo_formula_protection(path: Path, rows: list[list],
                             book: dict | None = None) -> tuple[int, str] | None:
    """Undo the export's formula protection (csv_safety) in place, only when
    the codebook written next to the CSV vouches for exactly this file; in a
    CSV from anywhere else an apostrophe is the researcher's own text.
    Returns (cells changed, the vouching file's name), or None when the file
    is not one of this program's exports."""
    import csv_safety

    book = book if book is not None else csv_safety.exported_codebook(path)
    if book is None:
        return None
    changed = 0
    for row in rows:
        for index, cell in enumerate(row):
            if isinstance(cell, str):
                restored = csv_safety.restore(cell)
                if restored != cell:
                    row[index] = restored
                    changed += 1
    return changed, csv_safety.sidecar_name(path, book)


def _raw_table(path: Path, options: ImportOptions, book: dict | None = None):
    warnings: list[str] = []
    if path.suffix.lower() in {".csv", ".tsv"}:
        text, encoding, decoding_notes = _read_text(path, options.encoding)
        warnings.extend(decoding_notes)
        separator = _detect_separator(text, path, options.separator)
        exported = (book or {}).get("data_file") or {}
        if options.separator == "auto" and exported.get("delimiter") in (",", ";", "\t"):
            separator = exported["delimiter"]     # as the program's own export says
        from io import StringIO
        try:
            reader = csv.reader(StringIO(text), delimiter=separator, strict=True)
            rows = list(reader)
        except csv.Error as error:
            raise ValueError(
                f"CSV quotation marks or delimiters are malformed: {error}"
            ) from error
        if not rows:
            raise ValueError("The CSV contains no rows.")
        if options.header_row > len(rows):
            raise ValueError("Header row is after the end of the CSV.")
        expected = len(rows[options.header_row - 1])
        if not expected:
            raise ValueError("The selected header row has no columns.")
        shortened = 0
        extra_empty = 0
        normalized_rows = []
        for row_index, row in enumerate(rows, start=1):
            if row_index < (options.data_start_row or options.header_row + 1):
                normalized_rows.append(row[:expected] + [
                    None for _ in range(max(0, expected - len(row)))
                ])
                continue
            if not row:
                normalized_rows.append([None] * expected)
                continue
            if len(row) > expected:
                extras = row[expected:]
                if any(str(extra).strip() for extra in extras):
                    raise ValueError(
                        f"CSV row {row_index} has {len(row)} cells but the header "
                        f"has {expected}. Check separator or unquoted answer text."
                    )
                extra_empty += 1
                row = row[:expected]
            if len(row) < expected:
                shortened += 1
            normalized_rows.append(row + [None] * (expected - len(row)))
        restored = _undo_formula_protection(path, normalized_rows, book)
        if restored is not None:
            warnings.append(
                f"Formula protection removed from {restored[0]} text cell(s): this CSV "
                "was exported by Statistical Research Assistant and the file written "
                f"with it ({restored[1]}) matches it."
            )
        if shortened:
            warnings.append(
                f"{shortened} short CSV row(s) padded with missing trailing cells."
            )
        if extra_empty:
            warnings.append(
                f"{extra_empty} row(s) had empty trailing cells removed."
            )
        raw = pd.DataFrame(normalized_rows, dtype=object)
        return raw, None, encoding, separator, warnings

    sheets = workbook_sheets(path)
    if isinstance(options.sheet, str):
        if options.sheet not in sheets:
            raise ValueError(f"Worksheet '{options.sheet}' does not exist.")
        sheet: str | int = options.sheet
    elif (isinstance(options.sheet, bool) or
          not isinstance(options.sheet, int) or
          not 0 <= options.sheet < len(sheets)):
        raise ValueError("Choose an existing Excel worksheet.")
    else:
        sheet = options.sheet
    try:
        raw = pd.read_excel(
            path, sheet_name=sheet, header=None, dtype=object,
            engine="openpyxl",
        )
    except (ValueError, OSError, KeyError) as error:
        raise ValueError(f"Could not read Excel worksheet: {error}") from error
    chosen_sheet = sheets[sheet] if isinstance(sheet, int) else sheet
    # openpyxl returns cached values with data_only=True; formula cells without
    # cached results can appear blank. Never calculate or evaluate formulas.
    if path.stat().st_size <= 20 * 1024 * 1024:
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            worksheet = workbook[chosen_sheet]
            formulas = sum(
                cell.data_type == "f"
                for row in worksheet.iter_rows(
                    min_row=1, max_row=min(worksheet.max_row or 0, 300),
                    max_col=min(worksheet.max_column or 0, 60),
                )
                for cell in row
            )
            if formulas:
                warnings.append(
                    f"{formulas} spreadsheet formula cell(s) found in the "
                    "inspected region. Formulas are NOT executed; export "
                    "calculated values from Excel if their caches are blank."
                )
        finally:
            workbook.close()
    if len(sheets) > 1 and options.sheet == 0:
        warnings.append(
            "Workbook contains multiple sheets. First sheet used; choose "
            "another worksheet under Import settings if responses are elsewhere."
        )
    return raw, chosen_sheet, None, None, warnings


def _numeric_value(value: str, decimal: str) -> float | None:
    """Parse known formats only; reject ambiguous comma grouping in auto mode."""
    token = value.strip().replace("\u00a0", " ").replace("\u202f", " ")
    if not token or "%" in token:
        return None
    sign = r"[+-]?"
    plain = rf"{sign}\d+(?:\.\d+)?"
    plain_comma = rf"{sign}\d+(?:,\d+)?"
    space_groups = rf"{sign}\d{{1,3}}(?: \d{{3}})+(?:[.,]\d+)?"
    us_groups = rf"{sign}\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?"
    eu_groups = rf"{sign}\d{{1,3}}(?:\.\d{{3}})+(?:,\d+)?"
    if " " in token and re.fullmatch(space_groups, token):
        token = token.replace(" ", "")
    exponent_dot = rf"{sign}\d+(?:\.\d+)?[eE][+-]?\d+"
    exponent_comma = rf"{sign}\d+(?:,\d+)?[eE][+-]?\d+"
    if decimal in {"auto", "dot"} and re.fullmatch(exponent_dot, token):
        return float(token)
    if decimal == "comma" and re.fullmatch(exponent_comma, token):
        return float(token.replace(",", "."))
    if decimal == "auto":
        if re.fullmatch(us_groups, token) and "." in token and "," in token:
            return float(token.replace(",", ""))
        if re.fullmatch(eu_groups, token) and "." in token and "," in token:
            return float(token.replace(".", "").replace(",", "."))
        if re.fullmatch(plain, token):
            return float(token)
        if re.fullmatch(plain_comma, token) and "," in token:
            tail = token.rsplit(",", 1)[-1]
            # "1,234" could be one thousand two hundred thirty-four OR 1.234.
            if len(tail) == 3:
                return None
            return float(token.replace(",", "."))
        return None
    if decimal == "dot":
        if re.fullmatch(us_groups, token):
            return float(token.replace(",", ""))
        if re.fullmatch(plain, token):
            return float(token)
        return None
    if re.fullmatch(eu_groups, token):
        return float(token.replace(".", "").replace(",", "."))
    if re.fullmatch(plain_comma, token):
        return float(token.replace(",", "."))
    if re.fullmatch(rf"{sign}\d+", token):
        return float(token)
    return None


def _convert_numeric(frame: pd.DataFrame, style: str, warnings: list[str],
                     keep_text: frozenset = frozenset()) -> list[str]:
    converted: list[str] = []
    for name in frame.columns:
        column = frame[name]
        if pd.api.types.is_numeric_dtype(column) or looks_like_identifier(name) \
                or name in keep_text:
            continue
        observed = [v for v in column if not _blank(v)]
        if not observed:
            continue
        if any(
            isinstance(value, str) and re.fullmatch(r"[+-]?0\d+", value.strip())
            for value in observed
        ):
            warnings.append(
                f"Variable '{name}' has leading-zero codes (e.g. 001); "
                "preserved as text to avoid losing identifier information."
            )
            continue
        if not all(isinstance(v, (int, float, str)) and
                   not isinstance(v, bool) for v in observed):
            continue  # Dates, booleans and mixed date/number columns stay unchanged.
        if any(isinstance(value, str) and "%" in value for value in observed):
            warnings.append(
                f"Variable '{name}' contains percentages as text; "
                "it was not converted or divided by 100 automatically."
            )
            continue
        parsed = []
        for value in observed:
            parsed.append(_numeric_value(str(value), style))
        if all(number is not None for number in parsed):
            values = [
                _numeric_value(str(value), style) if not _blank(value) else float("nan")
                for value in column
            ]
            frame[name] = pd.to_numeric(pd.Series(values, index=frame.index),
                                        errors="raise")
            converted.append(str(name))
        elif any(number is not None for number in parsed):
            warnings.append(
                f"Variable '{name}' has mixed or ambiguous numeric text; "
                "kept as categories. Check decimal style and incorrect cells."
            )
        elif any(re.search(r"\d[,\.]\d", str(x)) for x in observed):
            warnings.append(
                f"Variable '{name}' has ambiguous locale-formatted numbers; "
                "kept as text. Choose dot/comma decimal style explicitly "
                "after checking the original file."
            )
    return converted


def load_dataset_with_report(
    path: str | Path, options: ImportOptions | None = None
) -> tuple[pd.DataFrame, ImportReport]:
    """Read with conservative normalization and transparent review messages."""
    options = options or ImportOptions()
    _validate_options(options)
    source = Path(path).expanduser()
    _file_guard(source)
    if source.suffix.lower() in SAV_EXTENSIONS:
        return _load_sav(source, options)
    book = None
    if source.suffix.lower() in {".csv", ".tsv"}:
        import csv_safety

        book = csv_safety.exported_codebook(source)
    raw, sheet, encoding, separator, warnings = _raw_table(source, options, book)
    if options.header_row > len(raw):
        raise ValueError(
            "Header row is after the end of the worksheet. "
            "Choose the row containing variable or question names."
        )
    headings = raw.iloc[options.header_row - 1].tolist()
    if any(_blank(name) for name in headings):
        raise ValueError(
            "One or more column headers are blank. Remove empty Excel columns "
            "or select the correct header row in Import settings."
        )
    names = [str(name).strip() for name in headings]
    if len(set(names)) != len(names):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(
            "Duplicate variable headings detected: " + ", ".join(duplicates[:8])
            + ". Rename duplicates in the source file before analysis."
        )
    if any(name != str(original) for name, original in zip(names, headings)):
        warnings.append("Leading/trailing spaces in column headings were trimmed.")
    if any(len(name) > 120 for name in names):
        warnings.append("Long survey-question headings detected; consider short variable IDs.")
    if any(name.isdigit() for name in names):
        warnings.append(
            "Numeric column headings detected. Confirm the selected header row."
        )
    if len(names) > 1000 or len(raw) * len(names) > MAX_CELLS:
        raise ValueError(
            "Dataset exceeds 5 million cells or 1,000 columns. "
            "Split the source file into smaller research datasets."
        )

    first_data = options.data_start_row or options.header_row + 1
    frame = raw.iloc[first_data - 1:].copy().reset_index(drop=True)
    frame.columns = names
    blank_rows = frame.apply(lambda row: all(_blank(x) for x in row), axis=1)
    removed = int(blank_rows.sum())
    if removed:
        warnings.append(f"{removed} completely blank row(s) excluded.")
    frame = frame.loc[~blank_rows].reset_index(drop=True)
    if frame.empty:
        raise ValueError(
            "No respondent rows found. Confirm the worksheet and header row."
        )

    missing = {x.strip().casefold() for x in options.missing_tokens}
    replaced = 0
    normalized_linebreaks = 0
    for col in frame.columns:
        values = []
        for original in frame[col]:
            if _blank(original) or (
                isinstance(original, str) and original.strip().casefold() in missing
            ):
                if not _blank(original):
                    replaced += 1
                values.append(None)
            else:
                if isinstance(original, str) and "\r" in original:
                    original = original.replace("\r\n", "\n").replace("\r", "\n")
                    normalized_linebreaks += 1
                values.append(original)
        frame[col] = pd.Series(values, dtype=object)
    if normalized_linebreaks:
        warnings.append(
            f"Normalized line endings in {normalized_linebreaks} text cell(s) "
            "to match CSV/Excel behavior across Windows and other systems."
        )
    if replaced:
        warnings.append(
            f"{replaced} text marker(s) converted to missing using the "
            "selected missing-value markers. Review before scoring."
        )
    decimal, keep_text, metadata = options.decimal, frozenset(), None
    if book is not None:
        exported = book.get("data_file") or {}
        if decimal == "auto" and exported.get("decimal") in ("dot", "comma"):
            decimal = exported["decimal"]           # as the program's own export says
        keep_text = frozenset(str(v.get("name")) for v in book.get("variables") or ()
                              if isinstance(v, dict)
                              and v.get("kind") in ("text", "mixed", "category"))
        metadata = codebook_metadata(book) or None
    converted = _convert_numeric(frame, decimal, warnings, keep_text)
    if frame.shape[1] == 1:
        warnings.append(
            "Only one variable detected. Confirm the CSV separator and header row."
        )
    if any(str(column).lower().startswith("unnamed:") for column in frame.columns):
        warnings.append("An 'Unnamed' column was found; check Excel export formatting.")
    if not any(pd.api.types.is_numeric_dtype(frame[col]) for col in frame.columns):
        warnings.append(
            "No numeric variables detected. Encoded text choices need explicit "
            "recoding before calculating means, reliability or regression."
        )
    if options.header_row != 1:
        warnings.append(
            f"Header row {options.header_row} selected; previous rows were excluded."
        )
    if first_data > options.header_row + 1:
        warnings.append(
            f"{first_data - options.header_row - 1} metadata/description row(s) "
            "between the header and answers were excluded at your request."
        )
    report = ImportReport(
        rows=len(frame), columns=len(frame.columns),
        source=source.name, sheet=sheet, header_row=options.header_row,
        data_start_row=first_data, encoding=encoding, separator=separator,
        converted_columns=tuple(converted), warnings=tuple(warnings),
        metadata=metadata,
    )
    return frame, report


# ------------------------------------------------- metadata (Stage 37, #67)
def _code_text(value) -> str:
    """A code as text: ``1`` rather than ``1.0``."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 2 ** 53:
        return str(int(value))
    return str(value)


def codebook_metadata(book: dict) -> dict:
    """Variable metadata from a codebook this program wrote: the data
    codebook (``variables``) or a questionnaire's (``questions``)."""
    found: dict[str, dict] = {}
    levels = {"nominal": "nominal", "ordinal": "ordinal", "scale": "scale",
              "quantitative": "scale"}
    for item in book.get("variables") or ():
        if not isinstance(item, dict) or not item.get("name"):
            continue
        entry = {"label": str(item.get("label") or ""),
                 "value_labels": {str(k): str(v) for k, v in
                                  (item.get("value_labels") or {}).items()},
                 "missing_codes": list(item.get("missing_codes") or []),
                 "measure": levels.get(str(item.get("level") or "")), "source": "codebook"}
        if entry["label"] or entry["value_labels"] or entry["missing_codes"] or entry["measure"]:
            found[str(item["name"])] = entry
    for question in book.get("questions") or ():
        if not isinstance(question, dict) or not question.get("key"):
            continue
        found[str(question["key"])] = {
            "label": str(question.get("prompt") or ""),
            "value_labels": {str(k): str(v) for k, v in
                             (question.get("value_labels") or {}).items()},
            "missing_codes": [], "source": "codebook",
            "measure": levels.get(str(question.get("measurement_level") or ""))}
        options = question.get("missing_options") or {}
        if options and question.get("missing_reason_column"):
            found[str(question["missing_reason_column"])] = {
                "label": f"Missing reason: {question['key']}",
                "value_labels": {str(k): str(v) for k, v in options.items()},
                "missing_codes": list(options), "source": "codebook", "measure": "nominal"}
    return found


def sav_renames(notes) -> dict[str, str]:
    """{SPSS name: original name} from the notes of a .sav file this program
    exported ("Renamed: NAME = original", or the original on "+ " lines)."""
    notes = [str(n) for n in (notes or [])]
    if not notes or not notes[0].startswith(SAV_EXPORT_MARK):
        return {}
    renames: dict[str, str] = {}
    current, parts = None, []

    def finish():
        if current is not None and parts:
            renames[current] = "".join(parts)

    for line in notes[1:]:
        if line.startswith("Renamed: "):
            finish()
            current, parts = None, []
            name, separator, rest = line[len("Renamed: "):].partition(" =")
            if not separator:
                continue
            if rest.startswith(" ") and rest.strip():
                renames[name] = rest[1:]
            elif not rest:
                current = name
        elif line.startswith("+ ") and current is not None:
            parts.append(line[2:])
        else:
            finish()
            current, parts = None, []
    finish()
    return renames


def _load_sav(path: Path, options: ImportOptions | None = None
              ) -> tuple[pd.DataFrame, ImportReport]:
    """An SPSS file: values as stored, user-missing values as missing (or
    kept as codes, ``options.user_missing``), and labels, value labels,
    missing codes and levels as metadata."""
    keep_codes = (options or ImportOptions()).user_missing == "codes"
    import pyreadstat

    try:
        frame, meta = pyreadstat.read_sav(str(path), user_missing=True)
    except Exception as error:   # pyreadstat raises its own error types
        raise ValueError(f"The SPSS file could not be read: {error}") from error
    warnings: list[str] = []
    if frame.shape[1] > 1000 or frame.shape[0] * frame.shape[1] > MAX_CELLS:
        raise ValueError(
            "Dataset exceeds 5 million cells or 1,000 columns. "
            "Split the source file into smaller research datasets."
        )
    renames = sav_renames(meta.notes)
    names = [renames.get(str(c), str(c)) for c in frame.columns]
    if len({n.casefold() for n in names}) != len(names):
        names = [str(c) for c in frame.columns]
        warnings.append("The original variable names in the file's notes clash; the SPSS "
                        "names were kept.")
    elif any(name != str(column) for name, column in zip(names, frame.columns)):
        warnings.append(f"{sum(n != str(c) for n, c in zip(names, frame.columns))} original "
                        "variable name(s) restored from the notes of this exported file.")
    metadata: dict[str, dict] = {}
    user_missing = 0
    columns = {}
    for column, name in zip(frame.columns, names):
        values = frame[column]
        text = not pd.api.types.is_numeric_dtype(values.dtype) and \
            not pd.api.types.is_datetime64_any_dtype(values.dtype)
        codes: list = []
        mask = pd.Series(False, index=values.index)
        for found in (meta.missing_ranges or {}).get(column, []):
            low, high = found.get("lo"), found.get("hi")
            if text:
                if low == high and str(low).strip():
                    codes.append(str(low))
                    mask |= values.map(lambda v, c=str(low): isinstance(v, str)
                                       and v.rstrip() == c.rstrip()).astype(bool)
                elif low == high:
                    pass                        # a blank text is missing here anyway
                continue
            if low == high:
                codes.append(_code_text(low))
                mask |= values == low
            else:
                codes.append(["range", low, high])
                mask |= (values >= low) & (values <= high)
        user_missing += int(mask.sum())
        if mask.any() and not keep_codes:
            values = values.mask(mask)
        if text:
            values = values.map(lambda v: None if v is None or (isinstance(v, str)
                                                                 and not v.strip()) else v)
            values = values.astype(object)
        columns[name] = values
        labels = (meta.variable_value_labels or {}).get(column) or {}
        entry = {"label": str((meta.column_names_to_labels or {}).get(column) or ""),
                 "value_labels": {_code_text(k): str(v) for k, v in labels.items()},
                 "missing_codes": codes, "source": "sav",
                 "measure": (meta.variable_measure or {}).get(column)}
        if entry["label"] or entry["value_labels"] or entry["missing_codes"] or \
                entry["measure"] in ("nominal", "ordinal", "scale"):
            metadata[name] = entry
    table = pd.DataFrame(columns, index=frame.index).reset_index(drop=True)
    if user_missing and keep_codes:
        warnings.append(f"{user_missing} value(s) keep their user-missing codes as values, as "
                        "chosen: mark them missing (Data → Prepare) before analysing these "
                        "variables.")
    elif user_missing:
        warnings.append(f"{user_missing} value(s) with user-missing codes are missing here, as "
                        "SPSS treats them; the codes are kept with the variables.")
    if table.empty:
        raise ValueError("No respondent rows found in the SPSS file.")
    report = ImportReport(
        rows=len(table), columns=len(table.columns), source=path.name, sheet=None,
        header_row=1, data_start_row=2, encoding=getattr(meta, "file_encoding", None),
        separator=None, converted_columns=(), warnings=tuple(warnings),
        metadata=metadata or None)
    return table, report


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Backwards-compatible default importer used by scripts and tests."""
    return load_dataset_with_report(path)[0]


def variable_overview(df: pd.DataFrame) -> pd.DataFrame:
    """Show variable names, inferred types and missing counts.

    A numeric dtype does not establish interval-level measurement; the
    researcher is still responsible for confirming each variable's scale.
    """
    rows = []
    for name in df.columns:
        column = df[name]
        numeric = pd.api.types.is_numeric_dtype(column)
        if looks_like_identifier(name):
            hint = "identifier (do not analyze as a score)"
        else:
            hint = "numeric (verify scale)" if numeric else "text/category (verify scale)"
        rows.append({
            "variable": str(name),
            "dtype": str(column.dtype),
            "non_missing": int(column.notna().sum()),
            "missing": int(column.isna().sum()),
            "unique_values": int(column.nunique(dropna=True)),
            "type_hint": hint,
        })
    return pd.DataFrame(rows, columns=[
        "variable", "dtype", "non_missing", "missing", "unique_values", "type_hint"
    ])
