"""Conservative local CSV/Excel importer with actionable quality diagnostics.

The loader never executes spreadsheet macros, formulas or user-provided code.
Uncertain numbers remain text, never silently converted to analysis scores.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from variable_rules import looks_like_identifier


SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xlsm"}
ENCODINGS = ("utf-8-sig", "utf-16", "cp1257", "cp1251", "cp1252")
SEPARATORS = {"auto": None, "comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}
DECIMALS = {"auto", "dot", "comma"}
DEFAULT_MISSING = ("", "NA", "N/A", "NULL")
MAX_BYTES = 150 * 1024 * 1024
MAX_CELLS = 5_000_000


@dataclass(frozen=True)
class ImportOptions:
    """Header row is 1-based. Sheet name or zero-based position for Excel."""
    sheet: str | int = 0
    header_row: int = 1
    separator: str = "auto"
    encoding: str = "auto"
    decimal: str = "auto"
    missing_tokens: tuple[str, ...] = DEFAULT_MISSING


@dataclass(frozen=True)
class ImportReport:
    rows: int
    columns: int
    source: str
    sheet: str | None
    header_row: int
    encoding: str | None
    separator: str | None
    converted_columns: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_text(self) -> str:
        source_details = [f"{self.rows} rows × {self.columns} variables",
                          f"header row {self.header_row}"]
        if self.sheet:
            source_details.append(f"sheet '{self.sheet}'")
        if self.encoding:
            source_details.append(f"encoding {self.encoding}")
        if self.separator:
            source_details.append(f"separator {self.separator!r}")
        lines = ["Import: " + " · ".join(source_details)]
        if self.converted_columns:
            lines.append("Numeric conversion: " + ", ".join(self.converted_columns))
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
    if options.separator not in SEPARATORS:
        raise ValueError("Separator must be auto, comma, semicolon, tab or pipe.")
    if options.encoding != "auto" and options.encoding not in ENCODINGS:
        raise ValueError("Choose a supported encoding.")
    if options.decimal not in DECIMALS:
        raise ValueError("Decimal style must be auto, dot or comma.")
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
        raise ValueError("Supported file formats: .csv, .tsv, .xlsx, .xlsm")
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


def _raw_table(path: Path, options: ImportOptions):
    warnings: list[str] = []
    if path.suffix.lower() in {".csv", ".tsv"}:
        text, encoding, decoding_notes = _read_text(path, options.encoding)
        warnings.extend(decoding_notes)
        separator = _detect_separator(text, path, options.separator)
        from io import StringIO
        try:
            raw = pd.read_csv(
                StringIO(text), sep=separator, engine="python", header=None,
                dtype=object, keep_default_na=False, skip_blank_lines=False,
                on_bad_lines="error",
            )
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as error:
            raise ValueError(
                f"CSV rows have inconsistent delimiters or quotation marks: {error}"
            ) from error
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


def _convert_numeric(frame: pd.DataFrame, style: str, warnings: list[str]) -> list[str]:
    converted: list[str] = []
    for name in frame.columns:
        column = frame[name]
        if pd.api.types.is_numeric_dtype(column) or looks_like_identifier(name):
            continue
        observed = [v for v in column if not _blank(v)]
        if not observed:
            continue
        if not all(isinstance(v, (int, float, str)) and
                   not isinstance(v, bool) for v in observed):
            continue  # Dates, booleans and mixed date/number columns stay unchanged.
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
                f"Variable '{name}' may contain locale-formatted values; "
                "kept as text. Choose an explicit decimal style if appropriate."
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
    raw, sheet, encoding, separator, warnings = _raw_table(source, options)
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

    frame = raw.iloc[options.header_row:].copy().reset_index(drop=True)
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
                values.append(original)
        frame[col] = pd.Series(values, dtype=object)
    if replaced:
        warnings.append(
            f"{replaced} text marker(s) converted to missing using the "
            "selected missing-value markers. Review before scoring."
        )
    converted = _convert_numeric(frame, options.decimal, warnings)
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
    report = ImportReport(
        rows=len(frame), columns=len(frame.columns),
        source=source.name, sheet=sheet, header_row=options.header_row,
        encoding=encoding, separator=separator,
        converted_columns=tuple(converted), warnings=tuple(warnings),
    )
    return frame, report


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
