"""First runnable workflow: open CSV/XLSX and inspect variable structure."""

import argparse
from data_loader import load_dataset, variable_overview


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a research dataset")
    parser.add_argument("file", help="Path to a .csv or .xlsx file")
    args = parser.parse_args()

    df = load_dataset(args.file)
    print(f"Rows: {len(df)} | Variables: {len(df.columns)}")
    if df.empty:
        print("Warning: dataset contains no observations.")

    print("\nVARIABLE OVERVIEW")
    print(variable_overview(df).to_string(index=False))
    print("\nNote: verify ordinal/nominal/continuous measurement scales manually.")


if __name__ == "__main__":
    main()
