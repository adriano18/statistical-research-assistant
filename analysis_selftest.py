"""End-to-end analysis self-test for packaged builds (CI and support diagnostics).

Run from a packaged Windows app by setting ``SRA_ANALYSIS_SELFTEST=<result.json>``
before launching the executable, or from source::

    python analysis_selftest.py result.json

Every statistical procedure the application offers runs once on the bundled
fictional example datasets through the same functions the interface uses
(``analysis_runs``), together with its chart, the APA figure export, the Word
export, the XLSX reader and the local survey database. The JSON verdict lists
each step with its duration and a SHA-256 of the report text, so a packaged
build can be compared with a source checkout: identical hashes mean the build
computes exactly the same reported numbers. No network access, no user data.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
import time
import traceback
import warnings

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"
PNG = b"\x89PNG\r\n\x1a\n"


def _sample(name: str):
    import pandas as pd

    return pd.read_csv(EXAMPLES / name)


def _steps():
    """(id, callable returning an AnalysisRun) for every offered procedure."""
    import analysis_runs as runs

    scale = lambda: _sample("sample_scale.csv")  # noqa: E731
    factor = lambda: _sample("sample_factor.csv")  # noqa: E731
    regression = lambda: _sample("sample_regression.csv")  # noqa: E731
    stress = ["stress_q1", "stress_q2", "stress_q3", "stress_q4"]
    state: dict = {}

    def factor_items(df):
        return [c for c in df.columns if c != "participant_id"]

    def omnibus():
        state["omnibus"] = runs.run_omnibus(_sample("sample_three_groups.csv"), "group",
                                            "score", "kruskal", "ordinal", True, True)
        return state["omnibus"]

    return (
        ("descriptive", lambda: runs.run_descriptive(scale(), "stress_q2", "ordinal")),
        ("explore", lambda: runs.run_explore(scale(), "stress_q1", "group")),
        ("alpha", lambda: runs.run_alpha(scale(), stress, True)),
        ("omega", lambda: runs.run_omega(scale(), stress, True, 0)),
        ("omega_bootstrap", lambda: runs.run_omega(
            _sample("sample_omega_bootstrap.csv"),
            [c for c in _sample("sample_omega_bootstrap.csv").columns if c.startswith("wellbeing_q")],
            True, 200)),
        ("factor", lambda: runs.run_factor(factor(), factor_items(factor()), "efa", 2,
                                           "oblimin", True)),
        ("correlation_matrix", lambda: runs.run_matrix(factor(), factor_items(factor()),
                                                       "spearman", True)),
        ("correlation", lambda: runs.run_correlation(regression(), "study_hours", "stress_score",
                                                     "pearson", "scale", "scale", True)),
        ("regression", lambda: runs.run_regression(regression(), "stress_score",
                                                   ["study_hours", "sleep_hours"], True)),
        ("groups_mannwhitney", lambda: runs.run_groups(scale(), "group", "stress_q1",
                                                       "mannwhitney", "ordinal", True, False)),
        ("groups_welch", lambda: runs.run_groups(scale(), "group", "stress_q1", "welch",
                                                 "scale", True, True)),
        ("paired", lambda: runs.run_paired(_sample("sample_paired.csv"), "before_score",
                                           "after_score", "wilcoxon", "scale", True, True)),
        ("repeated", lambda: runs.run_repeated(
            _sample("sample_repeated.csv"), ["stress_before", "stress_mid", "stress_after"],
            "rm_anova", "scale", True, True)),
        ("chi_square", lambda: runs.run_chi_square(_sample("sample_categorical.csv"), "group",
                                                   "outcome", True)),
        ("omnibus", omnibus),
        ("posthoc", lambda: runs.run_posthoc(state.get("omnibus") or omnibus())),
        ("logistic", lambda: runs.run_logistic(_sample("sample_logistic.csv"),
                                               "wellbeing_improved",
                                               ["sleep_hours", "activity_hours"], True)),
        ("ancova", lambda: runs.run_ancova(_sample("sample_ancova.csv"), "wellbeing", "group",
                                           ["baseline_score"], "ancova", True)),
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_selftest(output: Path) -> int:
    started = time.monotonic()
    result: dict = {
        "ok": False, "python": platform.python_version(), "platform": platform.platform(),
        "executable": sys.executable, "frozen": bool(getattr(sys, "frozen", False)),
        "steps": {}, "errors": [],
    }
    os.environ.setdefault("MPLBACKEND", "Agg")  # charts are rendered off-screen
    warnings.simplefilter("ignore")  # library warnings are noise in this verdict
    try:
        t0 = time.monotonic()
        importlib.import_module("analysis_runs")  # import cost is part of the measurement
        result["import_seconds"] = round(time.monotonic() - t0, 3)
        runs_done = {}
        for step, call in _steps():
            t1 = time.monotonic()
            try:
                run = call()
                png = run.png or b""
                ok = bool(run.report.strip()) and (not png or png.startswith(PNG))
                runs_done[step] = run
                result["steps"][step] = {
                    "ok": ok, "seconds": round(time.monotonic() - t1, 3),
                    "report_sha256": _digest(run.report), "figure_bytes": len(png),
                }
                if not ok:
                    result["errors"].append(f"{step}: empty report or invalid figure")
            except Exception as error:  # report every failing procedure
                result["steps"][step] = {"ok": False, "seconds": round(time.monotonic() - t1, 3),
                                         "error": f"{type(error).__name__}: {error}"}
                result["errors"].append(f"{step}: {type(error).__name__}: {error}")
        result["exports"] = _exports(runs_done.get("groups_mannwhitney"), result["errors"])
        result["ok"] = not result["errors"]
    except Exception as error:  # report everything; this is a diagnostic
        result["errors"].append(f"{type(error).__name__}: {error}")
        result["traceback"] = traceback.format_exc()[-4000:]
    result["seconds"] = round(time.monotonic() - started, 2)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0 if result["ok"] else 1


def _exports(run, errors: list[str]) -> dict:
    """APA figure, Word, XLSX and local survey storage on a temporary folder."""
    done: dict = {}
    with TemporaryDirectory(prefix="sra-selftest-") as folder:
        temp = Path(folder)
        try:
            from apa_figures import make_apa7_export_png
            from interpretation_docx import save_apa_docx

            png = make_apa7_export_png(run.png, run.title, figure_number=1, note="",
                                       strip_embedded_caption=False)
            done["apa_figure_bytes"] = len(png)
            docx = save_apa_docx(temp / "selftest.docx", run.evidence(), figure_title=run.title)
            done["docx_bytes"] = Path(docx).stat().st_size
        except Exception as error:
            errors.append(f"exports: {type(error).__name__}: {error}")
        try:
            from data_loader import load_dataset

            frame = _sample("sample_scale.csv")
            frame.to_excel(temp / "selftest.xlsx", index=False)
            loaded = load_dataset(temp / "selftest.xlsx")
            done["xlsx_rows"] = int(len(loaded))
            if len(loaded) != len(frame):
                errors.append("xlsx: row count changed")
        except Exception as error:
            errors.append(f"xlsx: {type(error).__name__}: {error}")
        try:
            from survey_storage import create_survey, responses_dataframe, submit_response

            survey = create_survey(temp / "surveys", "Self-test", "Synthetic", [
                {"key": "group", "kind": "single_choice", "prompt": "Synthetic group",
                 "required": True, "options": ["A", "B"]},
                {"key": "q1", "kind": "likert5", "prompt": "Synthetic statement",
                 "required": True, "options": []},
            ])
            submit_response(temp / "surveys", survey.survey_id, {"group": "A", "q1": "2"})
            done["survey_rows"] = int(len(responses_dataframe(temp / "surveys", survey.survey_id)))
        except Exception as error:
            errors.append(f"survey storage: {type(error).__name__}: {error}")
    return done


def maybe_run_from_environment() -> None:
    """Hook for the packaged app: run and exit when SRA_ANALYSIS_SELFTEST is set."""
    target = os.environ.get("SRA_ANALYSIS_SELFTEST", "").strip()
    if not target:
        return
    code = run_selftest(Path(target))
    os._exit(code)


def compare(source: dict, packaged: dict) -> list[str]:
    """Differences between two self-test results (empty list = identical numbers)."""
    problems = [f"packaged: {e}" for e in packaged.get("errors", [])]
    for step, expected in source.get("steps", {}).items():
        got = packaged.get("steps", {}).get(step)
        if got is None:
            problems.append(f"{step}: missing in packaged result")
        elif got.get("report_sha256") != expected.get("report_sha256"):
            problems.append(f"{step}: report differs from the source checkout")
    return problems


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--compare":
        found = compare(*(json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:]))
        print("\n".join(found) or "Packaged reports are identical to the source checkout.")
        sys.exit(1 if found else 0)
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(run_selftest(Path(sys.argv[1])))
