"""Offline diagnostic for privately held research questionnaire documents.

Usage:
  python tools/audit_local_survey_docs.py "C:\...\UCLA.pdf" "C:\...\Stress.doc"

Never uploads or copies documents into the repository. Prints only candidate
instrument titles, counts, page references and brief warnings (not item text).
"""

from pathlib import Path
import argparse
import sys

# The script is run from the repository root but accepts paths anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scientific_survey_import import read_scientific_document


def main():
    parser = argparse.ArgumentParser(
        description="Audit private PDF/DOC/DOCX questionnaire imports locally."
    )
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    failed = 0
    for path in args.files:
        print(f"\nSOURCE: {path.name}")
        try:
            review = read_scientific_document(path)
        except Exception as error:
            failed += 1
            print(f"  NOT IMPORTED: {error}")
            continue
        print(f"  Pages: {review.page_count}")
        for item in review.instruments:
            print(
                f"  CANDIDATE: {item.title} | questions: "
                f"{len(item.questions)} | first source page: {item.first_page}"
            )
            print(
                f"    Codes: {list(item.scoring.code_labels)}; "
                f"reverse proposed: {list(item.scoring.reverse_numbers)}"
            )
            for warning in item.warnings[:6]:
                print(f"    REVIEW: {warning}")
        for warning in review.warnings:
            print(f"  DOCUMENT REVIEW: {warning}")
    print(
        f"\nCompleted locally; no questions published. "
        f"Unimportable files: {failed}/{len(args.files)}."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
