"""Results workbook, provenance and the reproducibility bundle (Stage 37, #67).

No Flet here. The workspace collects what is on screen (the session, the
open project) and these functions turn it into files:

* :func:`codebook_for` — the codebook of the dataset in use: confirmed
  levels, the questionnaires' wording, value labels and missing options,
  and the derived-variable history the project keeps (every version of the
  dataset back to the imported one).
* :func:`results_sheets` — an editable workbook: the Results overview, one
  sheet per analysis (the verified estimates and tables as shown, and the
  engine's unrounded values as numbers) and the Provenance rows.
* :func:`write_bundle` — a ``.zip`` with ``manifest.json`` (dataset
  SHA-256, program and library versions, methods, options, roles,
  confirmations and seeds, the SHA-256 of every file), the codebook, the
  data (.csv, .xlsx, .sav), the results workbook, the Word report and the
  figures, and R syntax for the analyses whose syntax was verified against
  the engine (:data:`R_SYNTAX`). No other procedure gets syntax.

Nothing here computes a statistic: every number comes from the engine's
result objects or the texts it produced.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import fields, is_dataclass
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re
import tempfile
import zipfile

import numpy as np
import pandas as pd

import csv_safety
import data_export as de

BUNDLE_FORMAT = "statistical-research-assistant-bundle"
BUNDLE_VERSION = 1
MAX_ENGINE_ROWS = 400

# Seeds fixed inside engine functions that do not keep them in their result
# objects (tests/test_stage37_export.py checks that the engine still uses them).
ENGINE_SEEDS = {
    ("correlation", "spearman"): {
        "seed": 2026, "resamples": 1999,
        "what": "permutation p of Spearman's rho for n <= 500 (correlation.analyze_correlation)"},
    ("factor", None): {
        "seed": 20261103, "simulations": 150,
        "what": "parallel analysis (factor_exploration.analyze_factor_exploration)"},
}
SEED_FIELDS = ("seed", "resamples", "n_resamples", "permutations", "simulations", "seed_rule")


# ============================================================== the codebook
def _questionnaire(definition) -> dict | None:
    if definition is None:
        return None
    return {"title": str(getattr(definition, "title", "")),
            "survey_id": str(getattr(definition, "survey_id", "")),
            "questions": [dict(q) for q in getattr(definition, "questions", ())]}


def _lineage(project, dataset_id: str | None) -> list:
    """The dataset and the versions it was derived from, oldest first."""
    chain, seen = [], set()
    current = dataset_id
    while current and current not in seen:
        seen.add(current)
        try:
            record = project.dataset(current)
        except Exception:
            break
        chain.append(record)
        current = record.parent_id
    return list(reversed(chain))


def codebook_for(session, *, project=None, dataset_id: str | None = None,
                 app_version: str = "", now: dt.datetime | None = None) -> de.Codebook:
    """The codebook of the dataset on screen (``session.df``)."""
    if not session.has_data:
        raise de.ExportError("Open a dataset first.")
    levels = {name: (info.confirmed, info.confirmed_in, info.suggested)
              for name, info in session.variables.items()}
    loader = getattr(session, "questionnaire_loader", None)
    books, seen = [], set()
    survey_ids = [session.dataset_survey_id] if session.dataset_survey_id else []
    if project is not None:
        try:
            survey_ids += [row["survey_id"] for row in project.questionnaires()]
        except Exception:
            pass
    for survey_id in survey_ids:
        if survey_id in seen or loader is None:
            continue
        seen.add(survey_id)
        try:
            book = _questionnaire(loader(survey_id))
        except Exception:
            book = None
        if book is not None:
            books.append(book)
    history: list[dict] = []
    if project is not None and dataset_id:
        for record in _lineage(project, dataset_id):
            try:
                steps = project.transformations(record.id)
            except Exception:
                steps = []
            for step in steps:
                history.append({"kind": step["kind"], "params": step["params"],
                                "output_columns": step["output_columns"],
                                "created_at": step.get("created_at", ""),
                                "dataset": record.name})
    for step in getattr(session, "pending_transformations", []) or []:
        history.append({"kind": step.get("kind", ""), "params": step.get("params", {}),
                        "output_columns": step.get("output_columns", []),
                        "created_at": "", "dataset": session.source_name})
    stamp = (now or dt.datetime.now()).isoformat(sep=" ", timespec="seconds")
    metadata = session.metadata() if hasattr(session, "metadata") else {}
    return de.build_codebook(session.df, session.source_name or "Dataset", levels=levels,
                             metadata=metadata, questionnaires=books, history=history,
                             sha256=session.dataset_sha256(), created=stamp,
                             app_version=app_version)


# ============================================================ engine values
def _scalar(value) -> float | int | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    return None


def engine_values(result, prefix: str = "", depth: int = 0) -> list[tuple[str, object]]:
    """(name, value) of every number the engine's result object holds, at
    full precision. Arrays and tables of participants' values are left out."""
    if result is None or depth > 4:
        return []
    found: list[tuple[str, object]] = []
    if hasattr(result, "structured") and callable(result.structured) and depth == 0:
        try:
            result = result.structured()
        except Exception:
            pass
    from stat_results import StructuredResult

    if isinstance(result, StructuredResult):
        for quantity in (*result.quantities, *result.diagnostics):
            base = f"{prefix}{quantity.key}"
            if quantity.ok:
                found.append((base, float(quantity.value)))
            else:
                found.append((base, quantity.status))
            for key in ("ci_low", "ci_high", "p"):
                value = getattr(quantity, key)
                if value is not None and math.isfinite(float(value)):
                    found.append((f"{base}.{key}", float(value)))
        for key, value in (result.sample or {}).items():
            number = _scalar(value)
            if number is not None:
                found.append((f"{prefix}sample.{key}", number))
        return found[:MAX_ENGINE_ROWS]
    if is_dataclass(result) and not isinstance(result, type):
        items = [(f.name, getattr(result, f.name)) for f in fields(result)]
    elif isinstance(result, dict):
        items = [(str(k), v) for k, v in result.items()]
    else:
        return []
    for name, value in items:
        number = _scalar(value)
        key = f"{prefix}{name}"
        if number is not None:
            found.append((key, number))
        elif is_dataclass(value) and not isinstance(value, type):
            found += engine_values(value, key + ".", depth + 1)
        elif isinstance(value, dict) and value and all(_scalar(v) is not None
                                                        for v in value.values()):
            found += [(f"{key}[{k}]", _scalar(v)) for k, v in value.items()]
        elif isinstance(value, (list, tuple)) and value and all(
                is_dataclass(v) for v in value) and len(value) <= 60:
            for index, item in enumerate(value):
                label = getattr(item, "name", None) or getattr(item, "y", None) or \
                    getattr(item, "outcome", None) or index
                found += engine_values(item, f"{key}[{label}].", depth + 1)
        if len(found) >= MAX_ENGINE_ROWS:
            break
    return found[:MAX_ENGINE_ROWS]


def seeds_of(entry) -> dict:
    """The random seeds and resampling counts this result was calculated with."""
    found: dict = {}
    result = entry.run.result
    for name, value in engine_values(result):
        last = name.rsplit(".", 1)[-1]
        if last in SEED_FIELDS:
            found[name] = value
    for source in (getattr(result, "provenance", None), getattr(
            getattr(result, "structured", None), "__call__", None) and None):
        if isinstance(source, dict):
            found.update({k: v for k, v in source.items() if k in SEED_FIELDS})
    if hasattr(result, "structured") and callable(result.structured):
        try:
            provenance = result.structured().provenance or {}
            found.update({k: v for k, v in provenance.items() if k in SEED_FIELDS})
        except Exception:
            pass
    for (method, option), fixed in ENGINE_SEEDS.items():
        if entry.method == method and (option is None or
                                       (entry.options or {}).get("method") == option):
            found.setdefault("engine", fixed)
    p_method = getattr(result, "p_method", "")
    if isinstance(p_method, str) and ("seed" in p_method or "permutation" in p_method):
        found.setdefault("p_method", p_method)
    return found


# ============================================================ results sheets
def _t(value) -> tuple:
    return (de.as_text(value) if value is not None else "", "text")


def analysis_rows(number: int, entry, *, method_title: str = "") -> list:
    """One analysis as rows of its own sheet."""
    run = entry.run
    evidence = run.evidence()
    facts = entry.provenance or {}
    rows: list = [[_t(f"R{number}. {run.title}")],
                  [_t("Method"), _t(evidence.method or method_title)],
                  [_t("Dataset"), _t(entry.dataset)],
                  [_t("Rows in the dataset"), entry.rows],
                  [_t("Calculated"), _t(f"{entry.created:%Y-%m-%d %H:%M:%S}")]]
    complete = evidence.n_complete if evidence.n_complete is not None else facts.get("complete")
    if complete is not None:
        rows.append([_t("Complete cases used"), int(complete)])
    if entry.stale_reasons:
        rows.append([_t("Needs review"), _t("; ".join(entry.stale_reasons))])
    rows += [[], [_t("Verified estimates (as shown in the program)")],
             [_t("Parameter"), _t("Estimate"), _t("95% CI"), _t("p")]]
    for row in evidence.rows:
        rows.append([_t(row.parameter), _t(row.estimate),
                     _t("" if row.ci == "Not calculated" else row.ci),
                     _t("" if row.p == "Not calculated" else row.p)])
    if not evidence.rows:
        rows.append([_t("none")])
    for table in run.tables:
        rows += [[], [_t(table.title)], [_t(c) for c in table.columns]]
        rows += [[_t(cell) for cell in row] for row in table.rows]
    values = engine_values(run.result)
    rows += [[], [_t("Engine values (unrounded numbers, for your own tables)")],
             [_t("Quantity"), _t("Value")]]
    if values:
        rows += [[_t(name), value if isinstance(value, (int, float)) else _t(value)]
                 for name, value in values]
    else:
        rows.append([_t("not kept with this result: the shown estimates above are the "
                        "program's record")])
    rows += [[], [_t("Assumption checks"), _t("Reviewed by the researcher")]]
    rows += [[_t(a), _t("yes" if a in entry.reviewed else "no")] for a in evidence.assumptions]
    if evidence.limitation:
        rows.append([_t("Limitation"), _t(evidence.limitation)])
    for warning in (*evidence.warnings,):
        rows.append([_t("Caution"), _t(warning)])
    if entry.note:
        rows.append([_t("Researcher's note"), _t(entry.note)])
    return rows


PROVENANCE_COLUMNS = ("Result", "Title", "Method key", "Options (JSON)", "Variables (JSON)",
                      "Measurement levels (JSON)", "Confirmations", "Dataset", "Dataset SHA-256",
                      "Rows", "Complete cases", "Calculated", "Restored from the project",
                      "Needs review", "Saved run id", "Hypothesis (JSON)", "Seeds (JSON)",
                      "Engine", "Report SHA-256")


def provenance_table(entries: list) -> list:
    rows: list = [[], [_t("Results")], [_t(c) for c in PROVENANCE_COLUMNS]]
    for number, entry in enumerate(entries, start=1):
        facts = entry.provenance or {}
        report_sha = hashlib.sha256(entry.run.report.encode("utf-8")).hexdigest()
        rows.append([
            _t(f"R{number}"), _t(entry.run.title), _t(entry.method or ""),
            _t(json.dumps(entry.options or {}, ensure_ascii=False, sort_keys=True)),
            _t(json.dumps(entry.roles or {}, ensure_ascii=False, sort_keys=True)),
            _t(json.dumps(facts.get("levels") or {}, ensure_ascii=False, sort_keys=True)),
            _t("; ".join(entry.confirmations)), _t(entry.dataset),
            _t(facts.get("dataset_sha256", "")), entry.rows,
            facts.get("complete") if isinstance(facts.get("complete"), int) else _t(""),
            _t(f"{entry.created:%Y-%m-%d %H:%M:%S}"), _t("yes" if entry.restored else "no"),
            _t("; ".join(entry.stale_reasons)), _t(entry.record_id or ""),
            _t(json.dumps(facts.get("hypothesis") or {}, ensure_ascii=False, sort_keys=True)
               if facts.get("hypothesis") else ""),
            _t(json.dumps(de._json_safe(seeds_of(entry)), ensure_ascii=False, sort_keys=True)),
            _t(f"analysis_runs · {entry.run.section}"), _t(report_sha)])
    return rows


def results_sheets(entries: list) -> list[de.Sheet]:
    """The Results overview and one sheet per analysis."""
    from workspace_methods import METHODS

    overview: list = [[_t(c) for c in ("Result", "Title", "Method", "Dataset", "Rows",
                                       "Complete cases", "Calculated", "Sheet")]]
    sheets: list[de.Sheet] = []
    for number, entry in enumerate(entries, start=1):
        spec = METHODS.get(entry.method) if entry.method else None
        title = spec.title if spec is not None else entry.run.section
        evidence = entry.run.evidence()
        sheet_name = f"R{number} {entry.run.title}"[:31]
        overview.append([_t(f"R{number}"), _t(entry.run.title), _t(title), _t(entry.dataset),
                         entry.rows, evidence.n_complete if evidence.n_complete is not None
                         else _t(""), _t(f"{entry.created:%Y-%m-%d %H:%M}"), _t(sheet_name)])
        sheets.append(de.Sheet(sheet_name, analysis_rows(number, entry, method_title=title),
                               widths={"A": 44, "B": 22, "C": 22, "D": 14}, freeze=None))
    return [de.Sheet("Results", overview, widths={"A": 8, "B": 50, "C": 36, "D": 30})] + sheets


def export_results(path: Path, entries: list, *, codebook: de.Codebook | None = None,
                   df: pd.DataFrame | None = None, sections=("results", "provenance"),
                   progress=None) -> dict:
    """The results workbook (sections as chosen: results, provenance, and
    data/codebook/scales when a dataset is given)."""
    if not entries and "results" in sections:
        raise de.ExportError("There are no results to export yet.")
    return de.export_xlsx(path, df, codebook, sections=sections, extra=results_sheets(entries),
                          provenance={"rows": provenance_table(entries)}, progress=progress)


# ================================================================== R syntax
def _r_string(text: str) -> str:
    escaped = (str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
               .replace("\r", "\\r").replace("\t", "\\t"))
    return f'"{escaped}"'


R_HEADER = """# {title}
# R syntax written by Statistical Research Assistant {version} for result R{number}.
# Verified for this method: the program's tests run this script with base R
# (package stats) on the bundle's CSV and compare the check values with the
# engine's unrounded numbers (docs/STAGE37_EXPORT.md).
# Run from anywhere:  Rscript {script} path/to/the/unzipped/bundle
args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args) > 0) args[1] else "."
d <- read.csv(file.path(root, {csv}), check.names = FALSE, na.strings = "",
              fileEncoding = "UTF-8", stringsAsFactors = FALSE)
# Text cells that begin with = + - @ carry a protective apostrophe in the CSV.
unprotect <- function(v) if (is.character(v)) sub("^'('*[-=+@\\t\\r])", "\\\\1", v) else v
check <- function(name, value) cat(sprintf("%s = %.15g\\n", name, value))
"""


def _levels_literal(df: pd.DataFrame, column: str, labels: Iterable[str]) -> str:
    numeric = pd.api.types.is_numeric_dtype(df[column].dtype)
    values = []
    for label in labels:
        if numeric:
            try:
                values.append(de.number_text(float(label)))
                continue
            except ValueError:
                pass
        values.append(_r_string(label))
    return "c(" + ", ".join(values) + ")"


def r_syntax(number: int, entry, df: pd.DataFrame, csv_name: str, version: str
             ) -> tuple[str | None, str, dict]:
    """(script, reason, check values) for one result. ``script`` is None
    when this method has no verified syntax; ``reason`` says why."""
    method, options, roles = entry.method, entry.options or {}, entry.roles or {}
    result = entry.run.result
    if result is None:
        return None, "the engine's result object is not available", {}
    header = R_HEADER.format(title=f"R{number}. {entry.run.title}".replace("\n", " "),
                             version=version, number=number,
                             script=f"syntax/R{number}_{method}.R",
                             csv=_r_string(f"data/{csv_name}"))
    var = lambda name: f"d[[{_r_string(name)}]]"  # noqa: E731
    if method == "correlation" and options.get("method") == "pearson":
        body = (f"x <- {var(roles['x'])}\ny <- {var(roles['y'])}\n"
                "res <- cor.test(x, y, method = \"pearson\")\nprint(res)\n"
                "check(\"r\", unname(res$estimate))\ncheck(\"p\", res$p.value)\n"
                "check(\"ci_low\", res$conf.int[1])\ncheck(\"ci_high\", res$conf.int[2])\n"
                "check(\"n\", sum(complete.cases(x, y)))\n")
        expected = {"r": result.coefficient, "p": result.p_value, "n": result.n_complete}
        if result.ci_low is not None:
            expected.update(ci_low=result.ci_low, ci_high=result.ci_high)
        return header + body, "", expected
    if method == "regression" and options.get("hc3", "no") != "yes":
        predictors = list(roles.get("predictors") or [])
        names = [roles["outcome"], *predictors]
        formula_terms = " + ".join(f"`{p}`" for p in predictors) if all(
            "`" not in n and "\\" not in n for n in names) else None
        if formula_terms is None:
            return None, "a variable name cannot be written in an R formula", {}
        frame = "m <- data.frame(" + ", ".join(f"{_r_string(n)} = {var(n)}" for n in names) + \
            ", check.names = FALSE)\n"
        body = (frame + f"fit <- lm(`{roles['outcome']}` ~ {formula_terms}, data = m)\n"
                "s <- summary(fit)\nprint(s)\n"
                "check(\"r_squared\", s$r.squared)\ncheck(\"adjusted_r_squared\", "
                "s$adj.r.squared)\ncheck(\"f_value\", unname(s$fstatistic[1]))\n"
                "check(\"n\", nobs(fit))\n"
                "co <- coef(s)\nfor (i in seq_len(nrow(co))) {\n"
                "  check(paste0(\"b[\", i, \"]\"), co[i, 1]); check(paste0(\"se[\", i, \"]\"), "
                "co[i, 2]); check(paste0(\"p[\", i, \"]\"), co[i, 4])\n}\n")
        expected = {"r_squared": result.r_squared,
                    "adjusted_r_squared": result.adjusted_r_squared,
                    "f_value": result.f_value, "n": result.n_complete}
        for index, coefficient in enumerate(result.coefficients, start=1):
            expected[f"b[{index}]"] = coefficient.b
            expected[f"se[{index}]"] = coefficient.se
            expected[f"p[{index}]"] = coefficient.p
        return header + body, "", expected
    if method == "groups" and options.get("method") == "welch":
        group, outcome = roles["group"], roles["outcome"]
        levels = _levels_literal(df, group, [result.group_a, result.group_b])
        body = (f"g <- factor(unprotect({var(group)}), levels = {levels})\n"
                f"y <- {var(outcome)}\n"
                "res <- t.test(y ~ g, var.equal = FALSE)\nprint(res)\n"
                "check(\"t\", unname(res$statistic))\ncheck(\"df\", unname(res$parameter))\n"
                "check(\"p\", res$p.value)\n")
        expected = {"t": result.statistic, "df": result.degrees_of_freedom,
                    "p": result.p_value}
        return header + body, "", expected
    if method == "omnibus" and options.get("method") in ("anova", "welch"):
        group, outcome = roles["group"], roles["outcome"]
        equal = "TRUE" if options.get("method") == "anova" else "FALSE"
        body = (f"g <- factor(unprotect({var(group)}))\ny <- {var(outcome)}\n"
                f"res <- oneway.test(y ~ g, var.equal = {equal})\nprint(res)\n"
                "check(\"F\", unname(res$statistic))\ncheck(\"df1\", unname(res$parameter[1]))\n"
                "check(\"df2\", unname(res$parameter[2]))\ncheck(\"p\", res$p.value)\n")
        expected = {"F": result.statistic, "df1": result.df1, "df2": result.df2,
                    "p": result.p_value}
        return header + body, "", expected
    return None, "no verified syntax for this method in this version", {}


# =================================================================== bundle
def _safe_stem(name: str, fallback: str = "data") -> str:
    stem = Path(str(name)).stem if "." in str(name) else str(name)
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_")
    return stem[:60] or fallback


def manifest_for(*, codebook: de.Codebook, entries: list, files: list[dict], app: dict,
                 libraries: dict, sensitive: list, syntax: dict, project: dict | None,
                 rows: int) -> dict:
    analyses = []
    from workspace_methods import METHODS

    for number, entry in enumerate(entries, start=1):
        facts = entry.provenance or {}
        spec = METHODS.get(entry.method) if entry.method else None
        analyses.append(de._json_safe({
            "result": f"R{number}", "title": entry.run.title, "method": entry.method,
            "method_title": spec.title if spec is not None else entry.run.section,
            "section": entry.run.section, "options": entry.options or {},
            "roles": entry.roles or {}, "confirms": entry.confirms or {},
            "confirmations": list(entry.confirmations),
            "dataset": entry.dataset, "dataset_sha256": facts.get("dataset_sha256", ""),
            "rows": entry.rows, "complete": facts.get("complete"),
            "levels": facts.get("levels") or {},
            "calculated": f"{entry.created:%Y-%m-%d %H:%M:%S}",
            "restored": bool(entry.restored), "needs_review": list(entry.stale_reasons),
            "record_id": entry.record_id, "hypothesis": facts.get("hypothesis"),
            "seeds": seeds_of(entry),
            "report_sha256": hashlib.sha256(entry.run.report.encode("utf-8")).hexdigest(),
            "syntax": syntax.get(number, {"r": None,
                                          "reason": "no verified syntax for this method"}),
        }))
    return {
        "format": BUNDLE_FORMAT, "version": BUNDLE_VERSION,
        "created": codebook.created, "app": app, "libraries": libraries,
        "project": project,
        "dataset": {"name": codebook.dataset, "rows": rows, "columns": codebook.columns,
                    "sha256": codebook.sha256,
                    "sha256_of": "the table as CSV text (UTF-8, no index, LF line ends), as "
                                 "every result records it"},
        "analyses": analyses,
        "files": files,
        "privacy": {"row_level_data": True, "uploaded": False,
                    "possibly_identifying_columns": [
                        {"variable": s.name, "why": s.reason, "detail": s.detail}
                        for s in sensitive]},
        "formats": {
            "csv": "UTF-8 without byte-order mark; text quoted, numbers unquoted; an empty "
                   "unquoted field is missing; text cells beginning with = + - @, tab or CR "
                   "carry one protective apostrophe (codebook data_file.formula_protection)",
            "xlsx": "Data, Codebook and Scales sheets; numbers, dates and texts typed",
            "sav": "SPSS names (codebook spss_names), labels, value labels, measurement levels "
                   "and user-missing codes within the format's limits; no audit trail",
        },
        "limitations": [
            "The bundle documents the analyses; it does not prove the study design.",
            "R syntax is included only for methods whose syntax the program's tests verify "
            "against the engine; other analyses have none.",
        ],
    }


def write_bundle(path: Path, *, df: pd.DataFrame, codebook: de.Codebook, entries: list,
                 report_writer: Callable[[Path], object] | None = None,
                 report_name: str = "research_report.docx",
                 app: dict | None = None, libraries: dict | None = None,
                 project: dict | None = None, progress=None) -> dict:
    """The reproducibility bundle (.zip), written atomically and verified."""
    app = app or {}
    libraries = libraries or {}
    stem = _safe_stem(codebook.dataset)
    csv_name, xlsx_name, sav_name = f"{stem}.csv", f"{stem}.xlsx", f"{stem}.sav"
    sensitive = de.sensitive_columns(df, codebook)

    def produce(temporary: Path) -> dict:
        members: list[tuple[str, bytes, str]] = []
        with tempfile.TemporaryDirectory(prefix="sra-bundle-") as folder:
            work = Path(folder)
            csv_facts = de.write_csv(work / csv_name, df, bom=False, layout="comma",
                                     progress=progress)
            members.append((f"data/{csv_name}", (work / csv_name).read_bytes(),
                            "the data: UTF-8 CSV, formula-protected text cells"))
            de.write_xlsx(work / xlsx_name, [de.codebook_sheet(codebook),
                                             de.scales_sheet(codebook)], data=df)
            members.append((f"data/{xlsx_name}", (work / xlsx_name).read_bytes(),
                            "the data with its Codebook and Scales sheets"))
            try:
                de.write_sav(work / sav_name, df, codebook, exported=codebook.created)
            except Exception as error:      # a .sav that cannot be written is reported
                sav_problem = f"{type(error).__name__}: {error}"
            else:
                sav_problem = ""
                members.append((f"data/{sav_name}", (work / sav_name).read_bytes(),
                                "the data for SPSS (names in the codebook)"))
            book = codebook.to_dict()
            book["data_file"] = {
                "name": csv_name, "sha256": hashlib.sha256(members[0][1]).hexdigest(),
                "format": "csv", "encoding": "utf-8", "bom": False, "delimiter": ",",
                "decimal": "dot", "formula_protection": {"rule": csv_safety.RULE,
                                       "cells": csv_facts["protected"]}}
            members.append(("codebook/codebook.json",
                            json.dumps(book, ensure_ascii=False, indent=1).encode("utf-8"),
                            "the codebook (machine-readable)"))
            if entries:
                de.write_xlsx(work / "results.xlsx", [
                    *results_sheets(entries),
                    de.Sheet("Provenance", de.provenance_rows(codebook, {}) +
                             provenance_table(entries), widths={"A": 44, "B": 70})])
                members.append(("results/results.xlsx", (work / "results.xlsx").read_bytes(),
                                "every result: estimates, tables, engine values, provenance"))
            if report_writer is not None:
                target = work / report_name
                written = report_writer(target)
                written = Path(written) if isinstance(written, (str, Path)) else target
                members.append((f"report/{report_name}", written.read_bytes(),
                                "the Word report as composed on the Reports page"))
            for number, entry in enumerate(entries, start=1):
                if entry.run.png:
                    members.append((f"figures/R{number}_{entry.run.section}.png",
                                    bytes(entry.run.png), f"the figure of R{number}"))
                state = getattr(entry, "charts", None)
                if state is not None and getattr(state, "view", None) is not None:
                    try:        # the researcher's Chart Studio view, as SVG
                        svg = state.render("svg", index=0, spec=state.view)
                    except Exception:
                        svg = None
                    if svg:
                        members.append((f"figures/R{number}_{entry.run.section}_view.svg",
                                        bytes(svg), f"the Chart Studio view of R{number}"))
            syntax: dict[int, dict] = {}
            for number, entry in enumerate(entries, start=1):
                script, reason, expected = r_syntax(number, entry, df, csv_name,
                                                    app.get("version", ""))
                if script is None:
                    syntax[number] = {"r": None, "reason": reason}
                    continue
                name = f"syntax/R{number}_{entry.method}.R"
                members.append((name, script.encode("utf-8"), f"R syntax for R{number}"))
                syntax[number] = {"r": name, "check_values": de._json_safe(expected)}
        files = [{"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                  "bytes": len(data), "description": text} for name, data, text in members]
        manifest = manifest_for(codebook=codebook, entries=entries, files=files, app=app,
                                libraries=libraries, sensitive=sensitive, syntax=syntax,
                                project=project, rows=len(df))
        if sav_problem:
            manifest["limitations"].append(f"No .sav file: {sav_problem}")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data, _ in members:
                archive.writestr(name, data)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False,
                                                         indent=1))
        return {"files": len(members) + 1, "rows": len(df),
                "syntax": sum(1 for s in syntax.values() if s.get("r")),
                "analyses": len(entries), "csv": f"data/{csv_name}"}

    def verify(temporary: Path, facts: dict) -> dict:
        checked = de.verify_zip(temporary)
        with zipfile.ZipFile(temporary) as archive:
            text = archive.read(facts["csv"]).decode("utf-8")
        import csv

        rows = sum(1 for _ in csv.reader(io.StringIO(text, newline=""), strict=True)) - 1
        if rows != len(df):
            raise de.VerificationFailed(f"{rows} data rows in the bundle instead of {len(df)}")
        checked["rows"] = rows
        return checked

    return de.save_atomic(path, produce, verify)
