"""Load a research dataset and inspect its variables without inferring tests."""

from pathlib import Path
import pandas as pd

from variable_rules import looks_like_identifier


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Return the first worksheet or a CSV table from a local file."""
    file_path = Path(path).expanduser()

    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.suffix.lower() == ".csv":
        # Let Pandas detect comma or semicolon separators.
        try:
            return pd.read_csv(file_path, sep=None, engine="python", encoding="utf-8-sig")
        except UnicodeDecodeError:
            # Useful for some Windows/Latvian exported datasets.
            return pd.read_csv(file_path, sep=None, engine="python", encoding="cp1257")

    if file_path.suffix.lower() in (".xlsx", ".xlsm"):
        return pd.read_excel(file_path, sheet_name=0)

    raise ValueError("Supported file formats: .csv, .xlsx, .xlsm")


def variable_overview(df: pd.DataFrame) -> pd.DataFrame:
    """Show variable names, data types and missing values.

    IMPORTANT: numeric dtype does not establish that a variable is continuous.
    The researcher must confirm the measurement scale.
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
