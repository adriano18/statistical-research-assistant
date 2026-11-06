r"""Offline structure audit of privately held questionnaire documents.

Usage:
  python tools/audit_local_survey_docs.py "C:\...\form.pdf" "C:\...\Stress.doc"
  python tools/audit_local_survey_docs.py --ocr eng "C:\...\scan.pdf"
  python tools/audit_local_survey_docs.py --items "C:\...\form.pdf"

Never uploads or copies documents into the repository. The default report
prints NO source wording: titles, labels and statements appear only as a
short SHA-256 prefix and a length, so the output can be shared to discuss
discrepancies (item numbers found/missing, answer-block structure, codes,
spacing repairs, pages, scale and scoring evidence, text layer vs OCR).
``--show-titles`` adds titles and warnings, which may contain source text.
"""

from pathlib import Path
import argparse
import hashlib
import sys

# The script is run from the repository root but accepts paths anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scientific_survey_import import (  # noqa: E402
    missing_items_banner, read_scientific_document, scheme_banner,
)


def fingerprint(text: str) -> str:
    """Wording-free stand-in for source text: hash prefix + length."""
    clean = " ".join(str(text).split())
    return f"#{hashlib.sha256(clean.encode('utf-8')).hexdigest()[:8]}/{len(clean)}"


def _span(numbers) -> str:
    numbers = sorted(numbers)
    if not numbers:
        return "none"
    out, start, prev = [], numbers[0], numbers[0]
    for n in numbers[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        out.append(f"{start}–{prev}" if prev != start else str(start))
        if n is not None:
            start = prev = n
    return ", ".join(out)


def _labels(labels) -> str:
    if not any(labels):
        return "labels not printed/readable"
    return (f"label lengths {[len(label) for label in labels]}, labels "
            f"{fingerprint(' | '.join(labels))}")


def _counts(values) -> str:
    found: dict = {}
    for value in values:
        found[value] = found.get(value, 0) + 1
    return ", ".join(f"{key} {count}" for key, count in sorted(found.items())) or "none"


def structure_report(review, *, source: str, items: bool = False) -> list[str]:
    """Text-free lines describing one parsed document."""
    out = [f"  [{source}] pages: {review.page_count}"
           + (f" | image-backed pages: {list(review.image_only_pages)}" if review.image_only_pages else "")]
    repairs = getattr(review, "spacing_repairs", ())
    if repairs:
        methods = _counts(r.method for r in repairs)
        out.append(
            f"    Spacing repairs: {len(repairs)} line(s) on page(s) "
            f"{sorted({r.page for r in repairs})}; {sum(r.joins for r in repairs)} join(s) inside "
            f"words; {sum(r.splits for r in repairs)} restored gap(s); evidence: {methods}"
        )
    else:
        out.append("    Spacing repairs: none")
    layout = getattr(review, "choice_layout", None)
    if layout is not None:
        template = layout.template
        sizes = _counts(len(item.block.labels) for item in layout.items)
        differing = [item.number for item in layout.items if item.deviations]
        out.append(
            f"    Repeated answer blocks: {len(layout.items)} item(s); common block "
            f"{template.size} choices, codes {','.join(template.codes)}, "
            f"{_labels(template.labels)}; choices per block: {sizes}; "
            f"differing blocks: {_span(differing)}"
            + (" (OCR-tolerant comparison)" if layout.fuzzy else "")
        )
        out.append("    Item numbers printed as: "
                   + _counts(item.number_source for item in layout.items))
    else:
        out.append("    Repeated answer blocks: not detected")
    if not review.instruments:
        out.append("    No candidate instrument (no numbered items were recognized).")
    for index, inst in enumerate(review.instruments, 1):
        numbers = [row.number for row in inst.questions]
        evidence = inst.evidence
        out.append(
            f"    CANDIDATE {index}: title {fingerprint(inst.title)} | questions {len(numbers)} | "
            f"pages {sorted({row.page for row in inst.questions})} | first page {inst.first_page}"
        )
        out.append(f"      Item numbers found: {_span(numbers)}; missing: "
                   f"{_span(evidence.missing_items)}"
                   + ("; order is not ascending" if numbers != sorted(numbers) else ""))
        out.append(f"      Question types: {_counts(row.question['kind'] for row in inst.questions)}")
        codes = [code for code, _label in inst.scoring.code_labels]
        out.append(f"      Text codebook: {','.join(codes) or 'none'}; reverse proposed: "
                   f"{_span(inst.scoring.reverse_numbers)}; binary formats: "
                   f"{_counts(f.kind for f in inst.response_formats)}")
        for scheme in inst.schemes:
            linked = [row.number for row in inst.questions if row.scheme_id == scheme.id]
            out.append(
                f"      Scale {scheme.id}: {scheme.size} categories | codes "
                f"{','.join(c or '-' for c in scheme.codes)} | evidence {scheme.evidence} | "
                f"linked items {_span(linked)} | {_labels(scheme.labels)} | "
                f"issues {len(scheme.issues)} | "
                + ("structure confirmed" if scheme.structure_confirmed else "NOT verified")
            )
        if not inst.schemes:
            out.append("      Scale: none detected")
        groups = evidence.scoring_groups
        if groups:
            for group in groups:
                out.append(
                    f"      Documented scoring {group.id}: name {fingerprint(group.name)} | "
                    f"items {_span(group.items)} ({len(group.items)}) | {group.aggregation}"
                    + (f" of {group.stated_count}" if group.stated_count is not None else "")
                    + (f" | range {group.value_range}" if group.value_range else "")
                    + f" | page {group.page} | {group.evidence} | issues {len(group.issues)}"
                )
            unassigned = evidence.unassigned_items(numbers)
            out.append(f"      Items in no documented group: {_span(unassigned)}")
        else:
            out.append("      Documented scoring groups: none")
        out.append(f"      Scoring statements: {len(evidence.scoring_statements)}"
                   + (" (OCR only)" if evidence.ocr_only else "")
                   + " — review-only, never applied")
        flags: dict = {}
        for _number, values in evidence.item_flags:
            for value in values:
                key = "prompt joined from several lines" if value.startswith("prompt joined") else value
                flags[key] = flags.get(key, 0) + 1
        out.append("      Item flags: " + (", ".join(f"{k} {v}" for k, v in sorted(flags.items()))
                                           or "none"))
        blocked = [name for name, banner in (("unverified scale", scheme_banner(inst)),
                                             ("missing items", missing_items_banner(inst)))
                   if banner]
        out.append("      Draft blocked by: " + (", ".join(blocked) or "nothing"))
        if items:
            for row in inst.questions:
                out.append(
                    f"        item {row.number:>3} | page {row.page} | {row.question['kind']} | "
                    f"prompt {fingerprint(row.question['prompt'])} | flags "
                    f"{list(evidence.flags_for(row.number)) or '-'}"
                )
    spatial = review.spatial
    if spatial is not None:
        linked = sum(1 for _, regions in spatial.links if regions)
        sources = sorted({page.source for page in spatial.pages})
        out.append(f"    Page geometry: {', '.join(sources)}; linked source regions {linked}/"
                   f"{len(spatial.links)}")
    for matrix in review.matrices:
        out.append(
            f"    Matrix {matrix.id}: {len(matrix.columns)} columns, codes "
            f"{','.join(c.code or '-' for c in matrix.columns)}, {len(matrix.rows)} rows, pages "
            f"{list(matrix.pages)}, unresolved cells {len(matrix.unresolved_cells)}"
        )
    return out


def _read_with_geometry(path: Path):
    review = read_scientific_document(path)
    try:
        from visual_survey_review import attach_docx_matrices, attach_text_layer_geometry
        data = path.read_bytes()
        if path.suffix.lower() == ".pdf":
            review = attach_text_layer_geometry(review, data)
        elif path.suffix.lower() == ".docx":
            review = attach_docx_matrices(review, data)
    except Exception as error:  # geometry is optional evidence
        print(f"  (page geometry unavailable: {type(error).__name__})")
    return review


def _ocr_review(path: Path, language: str):
    from visual_survey_review import MAX_BATCH_PAGES, ocr_scientific_pdf, pdf_page_count
    data = path.read_bytes()
    pages = list(range(1, min(pdf_page_count(data), MAX_BATCH_PAGES) + 1))
    return ocr_scientific_pdf(data, path.name, pages, language)


def main():
    parser = argparse.ArgumentParser(
        description="Audit private PDF/DOC/DOCX questionnaire imports locally (no wording printed)."
    )
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--ocr", metavar="LANG",
                        help="also run local Tesseract OCR on the first 20 PDF pages "
                             "(e.g. eng, lav+eng, rus+eng) and report it separately")
    parser.add_argument("--items", action="store_true",
                        help="one line per item (number, page, type, fingerprint, flags)")
    parser.add_argument("--show-titles", action="store_true",
                        help="also print titles and warnings (MAY CONTAIN SOURCE TEXT)")
    args = parser.parse_args()
    failed = 0
    for path in args.files:
        print(f"\nSOURCE: {path.name} ({path.suffix.lower().lstrip('.') or 'unknown'}, "
              f"{path.stat().st_size if path.exists() else 0} bytes)")
        runs = [("text layer" if path.suffix.lower() == ".pdf" else "document text", None)]
        if args.ocr and path.suffix.lower() == ".pdf":
            runs.append((f"local OCR {args.ocr}", args.ocr))
        for label, language in runs:
            try:
                review = _read_with_geometry(path) if language is None else _ocr_review(path, language)
            except Exception as error:
                if language is None:
                    failed += 1
                print(f"  [{label}] NOT IMPORTED: {type(error).__name__}: "
                      + ("no numbered questions in this text" if "No numbered" in str(error)
                         else str(error)[:160]))
                continue
            for line in structure_report(review, source=label, items=args.items):
                print(line)
            if args.show_titles:
                for item in review.instruments:
                    print(f"    TITLE (source text): {item.title}")
                    for warning in item.warnings[:8]:
                        print(f"    REVIEW (may quote source): {warning}")
                for warning in review.warnings:
                    print(f"    DOCUMENT REVIEW: {warning}")
    print(
        f"\nCompleted locally; no questions published and no wording printed"
        + (" (except --show-titles)" if args.show_titles else "")
        + f". Unimportable files: {failed}/{len(args.files)}."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
