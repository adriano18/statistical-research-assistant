"""Non-destructive transformations for questionnaire and research data.

Every operation returns a deep-copied dataframe. Source columns are never
replaced, and a proposed output name must not overwrite an existing column.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd


COLUMN_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


@dataclass
class TransformationResult:
    frame: pd.DataFrame
    step: dict[str, Any]
    message: str


def _check_target(df: pd.DataFrame, source: list[str], target: str) -> None:
    if not isinstance(target, str) or not COLUMN_NAME.fullmatch(target):
        raise ValueError(
            "New variable name must start with a letter and contain only "
            "letters, digits or underscores (up to 64 characters)."
        )
    if target in df.columns:
        raise ValueError("The new variable already exists; no columns may be overwritten.")
    if df.columns.duplicated().any():
        raise ValueError("Source data has duplicated column names.")
    for item in source:
        if item not in df.columns:
            raise ValueError(f"Unknown source variable: {item}")


def _key(value: Any) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError("Non-finite source values are not supported.")
        return f"{value:g}"
    return str(value).strip()


def mark_missing(
    df: pd.DataFrame, source: str, target: str, codes: list[str]
) -> TransformationResult:
    _check_target(df, [source], target)
    if not codes or len(codes) > 30:
        raise ValueError("Provide 1–30 explicit missing-value codes.")
    cleaned = [str(x).strip() for x in codes]
    if any(not code for code in cleaned):
        raise ValueError("Missing-value codes must not be empty.")
    tokens = set(cleaned)
    matches = df[source].map(_key).isin(tokens)
    copy = df.copy(deep=True)
    copy[target] = df[source].where(~matches, np.nan)
    count = int(matches.sum())
    return TransformationResult(
        copy,
        {"type": "missing", "source": source, "target": target, "codes": cleaned},
        f"Created {target}. Converted {count} explicitly coded values to missing; "
        "source column retained.",
    )


def recode_column(
    df: pd.DataFrame,
    source: str,
    target: str,
    mapping: dict[str, str],
    unmapped: str = "keep",
) -> TransformationResult:
    _check_target(df, [source], target)
    if not mapping or len(mapping) > 40:
        raise ValueError("Provide 1–40 old-to-new pairs.")
    if unmapped not in {"keep", "missing"}:
        raise ValueError("Unmapped values must be kept or marked missing.")
    rules = {str(k).strip(): str(v).strip() for k, v in mapping.items()}
    if any(not key or not value for key, value in rules.items()):
        raise ValueError("Recode keys and values must not be empty.")

    source_keys = df[source].map(_key)
    updated = []
    changed = missing_unmapped = 0
    for original, key in zip(df[source], source_keys):
        if key is None:
            updated.append(np.nan)
        elif key in rules:
            updated.append(rules[key])
            changed += 1
        elif unmapped == "missing":
            updated.append(np.nan)
            missing_unmapped += 1
        else:
            updated.append(original)
    copy = df.copy(deep=True)
    prepared = pd.Series(updated, index=df.index)
    coerced = pd.to_numeric(prepared, errors="coerce")
    copy[target] = coerced if prepared.notna().sum() == coerced.notna().sum() else prepared
    return TransformationResult(
        copy,
        {
            "type": "recode", "source": source, "target": target,
            "mapping": rules, "unmapped": unmapped,
        },
        f"Created {target}. Recoded {changed} values; "
        f"{missing_unmapped} unmapped responses marked missing.",
    )


def reverse_item(
    df: pd.DataFrame,
    source: str,
    target: str,
    minimum: float,
    maximum: float,
) -> TransformationResult:
    _check_target(df, [source], target)
    low, high = float(minimum), float(maximum)
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise ValueError("Reverse scoring requires valid minimum < maximum.")
    original = df[source]
    values = pd.to_numeric(original, errors="coerce")
    if (original.notna() & values.isna()).any() or np.isinf(values.to_numpy(dtype=float)).any():
        raise ValueError("Reverse-scored items must contain numeric values or missing.")
    if ((values.dropna() < low) | (values.dropna() > high)).any():
        raise ValueError(
            "Values outside the specified response scale were found. "
            "Clean missing-value codes first and check the correct scale."
        )
    copy = df.copy(deep=True)
    copy[target] = low + high - values
    return TransformationResult(
        copy,
        {
            "type": "reverse", "source": source, "target": target,
            "minimum": low, "maximum": high,
        },
        f"Created {target} = {low:g} + {high:g} − {source}. "
        f"{values.notna().sum()} non-missing values reversed.",
    )


def score_scale(
    df: pd.DataFrame,
    sources: list[str],
    target: str,
    method: str,
    min_answered: int,
) -> TransformationResult:
    if len(sources) < 2 or len(sources) > 30 or len(set(sources)) != len(sources):
        raise ValueError("Choose 2–30 distinct items from the SAME construct.")
    _check_target(df, sources, target)
    if method not in {"mean", "sum"}:
        raise ValueError("Use mean or sum as the scoring method.")
    if not 1 <= min_answered <= len(sources):
        raise ValueError("Minimum answered count must be between 1 and the item count.")
    if method == "sum" and min_answered != len(sources):
        raise ValueError(
            "Sum scoring requires ALL items to be answered. "
            "Use mean for transparent partial-response scoring."
        )
    raw = df[sources]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    if (raw.notna() & numeric.isna()).any().any() or np.isinf(
        numeric.to_numpy(dtype=float)
    ).any():
        raise ValueError(
            "Every selected item must be numeric. Recode categories and "
            "missing-value codes before scoring."
        )
    answered = numeric.notna().sum(axis=1)
    score = numeric.mean(axis=1) if method == "mean" else numeric.sum(axis=1, min_count=len(sources))
    copy = df.copy(deep=True)
    copy[target] = score.where(answered >= min_answered, np.nan)
    n_scored = int(copy[target].notna().sum())
    return TransformationResult(
        copy,
        {
            "type": "scale", "sources": list(sources), "target": target,
            "method": method, "min_answered": min_answered,
        },
        f"Created {target} from {len(sources)} items ({method}); "
        f"{n_scored}/{len(df)} rows meet the response rule. "
        "Confirm the same construct, response direction and reverse-coded items.",
    )


def save_prepared_dataset(
    df: pd.DataFrame,
    steps: list[dict[str, Any]],
    destination: str | Path,
    source_file: str | Path | None = None,
) -> tuple[Path, Path]:
    path = Path(destination).expanduser().resolve()
    if path.suffix.lower() != ".csv":
        raise ValueError("Choose a .csv destination.")
    if not path.parent.is_dir():
        raise FileNotFoundError("Destination directory does not exist.")
    if source_file is not None and path == Path(source_file).expanduser().resolve():
        raise ValueError("Cannot overwrite the original source file.")
    recipe = path.with_name(path.stem + "_steps.json")
    if recipe == path:
        raise ValueError("Invalid recipe path.")
    # Avoid half an export when an old recipe is read-only or inaccessible.
    payload = {
        "format": "statistical-research-assistant-prep-v1",
        "steps": steps,
        "final_columns": [str(x) for x in df.columns],
        "rows": int(len(df)),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    # The user explicitly selected the CSV path through a desktop save dialog.
    # Original dataframe and original file are never modified.
    df.to_csv(path, index=False, encoding="utf-8-sig")
    recipe.write_text(text, encoding="utf-8")
    return path, recipe
