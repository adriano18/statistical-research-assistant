"""Stage 37 (Issue #66): mediation, moderation, conditional process and the
linear model in the research workspace.

* The catalog: roles X, M (one or more), Y, W and covariates; design
  confirmations (mediators named before results, the explicit choice of
  Model 7 or 14, the cross-sectional limit) and a data confirmation.
* Nothing is chosen for the researcher: the guided advice never returns
  Model 7 or 14, Run waits for the moderated path, and mediators are never
  suggested by p-values.
* Texts in EN/LV/RU: tables, summary, interpretation, methods and notes;
  no causal verb in any language; the suppression guard of review S5.
* Report integration (plan and Word) and persistence after a restart.
* The guided flow through the real handlers (workspace harness).

Only fictional, simulated data appear in this file.
"""

from __future__ import annotations

from dataclasses import replace
import itertools
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import process_models as pm  # noqa: E402
from process_models import ProcessSpec, fit_process  # noqa: E402
from workspace_methods import (  # noqa: E402
    GOALS, METHODS, RoleProblems, advise, default_options, required_confirmations,
    role_problems, run_method, unchosen_options,
)
from workspace_state import ResearchSession  # noqa: E402

LEVELS = {"x": "scale", "m1": "scale", "m2": "scale", "w": "scale", "y": "scale",
          "age": "scale", "employed": "nominal", "group": "nominal", "w01": "nominal"}

# Causal verbs and phrases that must not appear (forms of "cause", "lead
# to", "influence", "impact", "drive", "determine", "result in", in the
# three languages). Disclaimers use the noun/adjective "causal" and the
# words "effect"/"efekts"/"эффект" as names of model quantities only.
CAUSAL = {
    "en": r"\b(causes|caused|causing|leads? to|led to|results? in|influences?|influenced|"
          r"impacts?|impacted|drives|drove|determines|determined by|produces|because of|"
          r"due to)\b",
    "lv": r"\b(izraisa|izraisīja|ietekmē|ietekmēja|ietekmēt|noved pie|nosaka|veicina|"
          r"rada)\b",
    "ru": r"(вызывает|вызвал|приводит к|привёл к|привел к|влияет|повлиял|влиянием|"
          r"обусловливает|обусловлен|определяет|способствует|порождает)",
}
MEDIATION_LABELS = {
    "en": r"(partial|full|complete) mediation",
    "lv": r"(daļēj|pilnīg)\w* mediācij",
    "ru": r"(частичн|полн)\w* медиаци",
}


def synthetic(seed: int = 3766, n: int = 150) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(50, 10, n)
    w = rng.normal(4, 1, n)
    age = rng.integers(18, 31, n).astype(float)
    employed = rng.integers(0, 2, n).astype(float)
    m1 = 1 + 0.03 * x + 0.012 * (x - 50) * (w - 4) + rng.normal(0, 0.6, n)
    m2 = 2 + 0.02 * x + rng.normal(0, 0.5, n)
    y = 40 + 0.3 * x + 4 * m1 + 3 * m2 + 2 * w + rng.normal(0, 8, n)
    return pd.DataFrame({"x": x, "m1": m1, "m2": m2, "w": w, "y": y, "age": age,
                         "employed": employed, "group": rng.choice([1, 2, 3], n),
                         "w01": (w > 4).astype(float)})


def session_for(frame: pd.DataFrame, language: str = "en") -> ResearchSession:
    session = ResearchSession()
    session.set_dataset(frame, "synthetic_process.csv")
    for name, level in LEVELS.items():
        if name in frame.columns:
            session.confirm_level(name, level)
    session.language = language
    return session


def run(key, session, roles, **options):
    spec = METHODS[key]
    chosen = {**default_options(spec), **options}
    confirms = {c.key: True for c in required_confirmations(spec, chosen)}
    return run_method(key, session, roles, chosen, confirms)


def stage37_fixture() -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "stage37"))
    import generate_master_fixture as fixture

    with tempfile.TemporaryDirectory() as folder:
        csv_path, _ = fixture.generate(Path(folder))
        return pd.read_csv(csv_path)


ROLES = {
    "mediation": {"x": "x", "mediators": ["m1", "m2"], "y": "y", "covariates": ["age",
                                                                             "employed"]},
    "moderation": {"x": "x", "w": "w", "y": "y", "covariates": ["age"]},
    "conditional_process": {"x": "x", "mediators": ["m1"], "w": "w", "y": "y",
                            "covariates": ["employed"]},
}


# ------------------------------------------------------------------ catalog
class CatalogTests(unittest.TestCase):
    def test_the_methods_roles_and_confirmations(self):
        for key in ("linear_model", "mediation", "moderation", "conditional_process"):
            self.assertIn(key, METHODS)
            self.assertEqual(METHODS[key].family, "models")
        roles = {r.key for r in METHODS["conditional_process"].roles}
        self.assertEqual(roles, {"x", "mediators", "w", "y", "covariates"})
        mediators = next(r for r in METHODS["mediation"].roles if r.key == "mediators")
        self.assertTrue(mediators.multiple)
        self.assertEqual(mediators.minimum, 1)
        kinds = {c.key: c.kind for c in METHODS["conditional_process"].confirmations}
        self.assertEqual(kinds, {"mediators_a_priori": "design", "model7_path": "design",
                                 "model14_path": "design", "cross_sectional": "design",
                                 "assumptions": "data"})
        self.assertEqual({c.key: c.kind for c in METHODS["mediation"].confirmations},
                         {"mediators_a_priori": "design", "cross_sectional": "design",
                          "assumptions": "data"})

    def test_the_moderated_path_has_no_default_and_its_own_confirmation(self):
        spec = METHODS["conditional_process"]
        option = next(o for o in spec.options if o.key == "method")
        self.assertTrue(option.required)
        self.assertEqual(option.default, "")
        self.assertEqual({k for k, _ in option.choices}, {"7", "14"})
        self.assertEqual(unchosen_options(spec, default_options(spec)), (option,))
        self.assertEqual(unchosen_options(spec, {"method": "14"}), ())
        seven = {c.key for c in required_confirmations(spec, {**default_options(spec),
                                                               "method": "7"})}
        fourteen = {c.key for c in required_confirmations(spec, {**default_options(spec),
                                                                 "method": "14"})}
        self.assertIn("model7_path", seven)
        self.assertNotIn("model14_path", seven)
        self.assertIn("model14_path", fourteen)
        self.assertNotIn("model7_path", fourteen)

    def test_run_waits_for_the_moderated_path_and_for_every_confirmation(self):
        session = session_for(synthetic())
        roles = ROLES["conditional_process"]
        with self.assertRaises(RoleProblems) as caught:
            run("conditional_process", session, roles)
        self.assertEqual(caught.exception.problems,
                         [("block.choose_option", {"option": "option.moderated_path"})])
        spec = METHODS["conditional_process"]
        options = {**default_options(spec), "method": "7"}
        confirms = {c.key: True for c in required_confirmations(spec, options)}
        for key in list(confirms):
            partial = {k: v for k, v in confirms.items() if k != key}
            with self.assertRaises(ValueError, msg=key):
                run_method("conditional_process", session, roles, options, partial)

    def test_the_workspace_run_equals_the_engine(self):
        frame = synthetic()
        session = session_for(frame)
        expectations = {
            "mediation": ProcessSpec("4", "x", "y", ("m1", "m2"), covariates=("age", "employed")),
            "moderation": ProcessSpec("1", "x", "y", w="w", covariates=("age",)),
        }
        for key, spec in expectations.items():
            result = run(key, session, ROLES[key]).result
            direct = fit_process(frame, spec)
            for a, b in zip(result.effects + result.indirect, direct.effects + direct.indirect):
                self.assertEqual((a.key, a.value, a.ci_low, a.ci_high),
                                 (b.key, b.value, b.ci_low, b.ci_high))
        for model in ("7", "14"):
            result = run("conditional_process", session, ROLES["conditional_process"],
                         method=model, center="mean", hc3="yes").result
            direct = fit_process(frame, ProcessSpec(model, "x", "y", ("m1",), w="w",
                                                    covariates=("employed",), center=True,
                                                    hc3=True))
            self.assertEqual(result.spec.model, model)
            self.assertEqual(result.estimate("index:m0").ci_low,
                             direct.estimate("index:m0").ci_low)

    def test_a_nominal_variable_needs_codes(self):
        session = session_for(synthetic())
        problems = role_problems(METHODS["mediation"],
                                 {"x": "x", "mediators": ["m1"], "y": "y",
                                  "covariates": ["group"]}, session)
        self.assertIn(("block.process_nominal", {"name": "group"}), problems)
        # A 0/1 nominal covariate or moderator is accepted.
        self.assertEqual(role_problems(METHODS["moderation"],
                                       {"x": "x", "w": "w01", "y": "y",
                                        "covariates": ["employed"]}, session), [])
        # The linear model takes a category variable only as dummy codes.
        problems = role_problems(METHODS["linear_model"],
                                 {"outcome": "y", "predictors": ["x", "group"]}, session)
        self.assertIn("block.level_for_role", [k for k, _ in problems])
        self.assertEqual(role_problems(METHODS["linear_model"],
                                       {"outcome": "y", "predictors": ["x"],
                                        "factors": ["group"], "product_a": "x",
                                        "product_b": "group"}, session), [])
        problems = role_problems(METHODS["linear_model"],
                                 {"outcome": "y", "predictors": ["x"], "product_a": "x",
                                  "product_b": "w"}, session)
        self.assertIn(("block.product_not_in_model", {"name": "w"}), problems)

    def test_the_linear_model_runs_with_dummy_codes_and_a_product(self):
        session = session_for(synthetic())
        run_ = run("linear_model", session,
                   {"outcome": "y", "predictors": ["x", "w"], "factors": ["group"],
                    "product_a": "x", "product_b": "w"}, center="yes", reference="last")
        self.assertEqual(run_.section, "linear_model")
        self.assertEqual(run_.result.references, {"group": "3"})
        self.assertIn("x × w", [c.term for c in run_.result.coefficients])
        self.assertIn("reference category", run_.report)


# ------------------------------------------------------------------ guided advice
class GuidedAdviceTests(unittest.TestCase):
    def test_the_process_goal_is_a_question_type(self):
        import research_workflow as rw

        self.assertIn("process", GOALS)
        self.assertEqual(rw.QUESTION_TYPES, GOALS)
        self.assertIn("process", rw.TESTABLE)

    def test_the_advice_never_returns_model_7_or_14(self):
        session = session_for(synthetic())
        names = ["x", "m1", "m2", "w", "y", "age", "employed"]
        seen = set()
        for x, y in itertools.permutations(["x", "y", "w"], 2):
            rest = [n for n in names if n not in (x, y)]
            for mediators in ([], ["m1"], ["m1", "m2"]):
                for w in (None, "w", "w01"):
                    if w in (x, y) or w in mediators:
                        continue
                    selection = {"x": x, "y": y, "mediators": mediators, "w": w,
                                 "covariates": [n for n in ("age",) if n in rest]}
                    advice = advise("process", selection, session)
                    seen.add(advice.method)
                    if advice.method == "conditional_process":
                        self.assertEqual(advice.options, {"method": ""})
                        self.assertEqual({a.options["method"] for a in advice.alternatives},
                                         {"7", "14"})
                    self.assertNotIn(advice.options.get("method"), ("7", "14"))
        self.assertEqual(seen, {None, "mediation", "moderation", "conditional_process"})

    def test_the_structure_follows_the_roles_the_researcher_named(self):
        session = session_for(synthetic())
        base = {"x": "x", "y": "y"}
        self.assertEqual(advise("process", base, session).blockers,
                         (("block.process_structure", {}),))
        self.assertEqual(advise("process", {**base, "mediators": ["m1"]}, session).method,
                         "mediation")
        self.assertEqual(advise("process", {**base, "w": "w"}, session).method, "moderation")

    def test_categorical_predictors_lead_to_the_linear_model(self):
        session = session_for(synthetic())
        advice = advise("predict", {"outcome": "y", "predictors": ["x", "group", "employed"]},
                        session)
        self.assertEqual(advice.method, "linear_model")
        self.assertEqual(advice.roles["factors"], ["group", "employed"])
        self.assertTrue(advice.ready)
        # One category variable with up to three quantitative covariates stays ANCOVA.
        self.assertEqual(advise("predict", {"outcome": "y", "predictors": ["x", "group"]},
                                session).method, "ancova")


# ------------------------------------------------------------------ texts
def all_texts(result, sensitivity=None) -> dict[str, str]:
    from process_reporting import (format_process_report, methods_text, notes,
                                   process_interpretation, process_summary, process_tables)

    out = {}
    for language in ("en", "lv", "ru"):
        parts = [format_process_report(result, sensitivity, language),
                 process_summary(result, language), methods_text(result, language),
                 *process_interpretation(result, language), *notes(result, language)]
        for table in process_tables(result, language, sensitivity):
            parts += [table.title, *table.columns, *(" ".join(r) for r in table.rows)]
        out[language] = "\n".join(parts)
    return out


class TextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frame = synthetic()
        cls.results = [fit_process(frame, spec) for spec in (
            ProcessSpec("4", "x", "y", ("m1", "m2"), covariates=("age",), resamples=400),
            ProcessSpec("1", "x", "y", w="w", center=True, hc3=True),
            ProcessSpec("7", "x", "y", ("m1",), w="w", resamples=400),
            ProcessSpec("14", "x", "y", ("m1", "m2"), w="w", resamples=400, center=True))]
        cls.sensitivity = pm.sensitivity_simulation(cls.results[2], replications=30, seed=1)

    def test_every_text_exists_in_three_languages(self):
        from process_text import TEXT

        self.assertEqual(set(TEXT["en"]), set(TEXT["lv"]))
        self.assertEqual(set(TEXT["en"]), set(TEXT["ru"]))
        for result in self.results:
            texts = all_texts(result, self.sensitivity if result.spec.model == "7" else None)
            for language, text in texts.items():
                self.assertNotRegex(text, r"\b(q|w|table|warn|interp|methods|summary)\.[a-z_]+"
                                          r"\b(?![\w(])", language)
            self.assertNotEqual(texts["en"], texts["lv"])
            self.assertNotEqual(texts["en"], texts["ru"])

    def test_no_causal_wording_and_no_mediation_labels_in_any_language(self):
        from process_text import TEXT

        sources = {language: "\n".join(v if isinstance(v, str) else " ".join(v)
                                       for v in TEXT[language].values())
                   for language in ("en", "lv", "ru")}
        for result in self.results:
            sensitivity = self.sensitivity if result.spec.model == "7" else None
            for language, text in all_texts(result, sensitivity).items():
                sources[language] += "\n" + text
        fixture = stage37_fixture()
        core = fixture.dropna(subset=["SYN_LON_TOTAL", "SYN_COPE_DIM1_MEAN", "SYN_SUP_MEAN",
                                      "SYN_WELL_0_100"])
        suppression = fit_process(core, ProcessSpec("4", "SYN_LON_TOTAL", "SYN_WELL_0_100",
                                                    ("SYN_COPE_DIM1_MEAN",), resamples=400))
        for language, text in all_texts(suppression).items():
            sources[language] += "\n" + text
        for language, text in sources.items():
            found = re.findall(CAUSAL[language], text, flags=re.IGNORECASE)
            self.assertEqual(found, [], language)
            self.assertIsNone(re.search(MEDIATION_LABELS[language], text, re.IGNORECASE),
                              language)

    def test_opposite_signs_are_called_inconsistent_mediation(self):
        """Review S5: on the fixture ab = +0.0716 and c = −0.4084 (n = 175)."""
        from process_reporting import process_interpretation

        fixture = stage37_fixture()
        core = fixture.dropna(subset=["SYN_LON_TOTAL", "SYN_COPE_DIM1_MEAN", "SYN_SUP_MEAN",
                                      "SYN_WELL_0_100"])
        result = fit_process(core, ProcessSpec("4", "SYN_LON_TOTAL", "SYN_WELL_0_100",
                                               ("SYN_COPE_DIM1_MEAN",), resamples=400))
        self.assertGreater(result.estimate("indirect:m0").value, 0)
        self.assertLess(result.estimate("total").value, 0)
        expected = {"en": "inconsistent mediation (suppression",
                    "lv": "nekonsekventa mediācija (supresija",
                    "ru": "несогласованная медиация (супрессия"}
        for language, phrase in expected.items():
            text = "\n".join(process_interpretation(result, language))
            self.assertIn(phrase, text, language)
        # Same signs: no such sentence.
        consistent = fit_process(synthetic(), ProcessSpec("4", "x", "y", ("m1",),
                                                          resamples=400))
        self.assertGreater(consistent.estimate("indirect:m0").value, 0)
        self.assertGreater(consistent.estimate("total").value, 0)
        self.assertNotIn("inconsistent", "\n".join(process_interpretation(consistent)))

    def test_the_methods_text_names_the_structure_and_this_program(self):
        from process_reporting import methods_text

        for result in self.results:
            text = methods_text(result)
            self.assertIn(f"Structure equivalent to PROCESS Model {result.spec.model} "
                          "(Hayes, 2022); computed by this program, not by the PROCESS "
                          "macro", text)
            for language in ("lv", "ru"):
                self.assertIn(f"{result.spec.model}", methods_text(result, language))
                self.assertIn("PROCESS", methods_text(result, language))


# ------------------------------------------------------------------ report and storage
class ReportTests(unittest.TestCase):
    def test_the_result_reaches_the_report_plan_and_the_word_document(self):
        import docx

        import research_report as rr
        from report_docx import build_research_docx, save_report_docx

        session = session_for(synthetic())
        entries = []
        for key, options in (("mediation", {}), ("moderation", {}),
                             ("conditional_process", {"method": "14"})):
            run_ = run(key, session, ROLES[key], **options)
            entries.append(session.add_result(run_, (), method=key, roles=ROLES[key],
                                              options={**default_options(METHODS[key]),
                                                       **options}))
        infos = [rr.result_info(entry) for entry in entries]
        plan = rr.plan_report(rr.ReportInputs(title="Fictional path models", results=infos))
        tests = plan.section("tests")
        titles = [item.text for item in tests.items if item.kind == "subheading"]
        self.assertEqual(titles, [e.run.title for e in entries])
        tables = [item.title for item in tests.items if item.kind == "table"]
        self.assertIn("Model 4: indirect effects (percentile bootstrap)", tables)
        self.assertIn("Model 14: index of moderated mediation (percentile bootstrap)", tables)
        effects = plan.section("effects").items[0].rows
        indirect = [row for row in effects if row[1].startswith("Indirect effect via m1")]
        self.assertEqual(len(indirect), 1)
        self.assertNotEqual(indirect[0][3], "Not calculated")      # its bootstrap interval
        assumptions = plan.section("assumptions").items
        self.assertTrue(any("cross-sectional" in (item.text or "") for item in assumptions))
        with tempfile.TemporaryDirectory() as folder:
            path = save_report_docx(Path(folder) / "report.docx", build_research_docx(plan))
            text = "\n".join(p.text for p in docx.Document(path).paragraphs)
        self.assertIn("Mediation (PROCESS-equivalent Model 4)", text)
        self.assertIn("not by the PROCESS macro", text)

    def test_a_stored_result_comes_back_with_its_intervals(self):
        from analysis_runs import AnalysisRun
        from project_session import run_from_record
        from project_store import ProjectStore

        frame = synthetic()
        session = session_for(frame)
        run_ = run("mediation", session, ROLES["mediation"])
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(Path(folder))
            info = store.create("Fictional storage")
            with store.open(info.id) as project:
                dataset = project.import_table(frame, "synthetic.csv")
                record = project.record_run(run_, method="mediation", dataset_id=dataset.id,
                                            roles=ROLES["mediation"], options={},
                                            confirms={})
            with ProjectStore(Path(folder)).open(info.id) as project:
                again = run_from_record(project.run(record.id), None)
        self.assertIsInstance(again, AnalysisRun)
        rows = {row.parameter: row for row in again.evidence().rows}
        label = "Indirect effect via m1 (a × b)"
        estimate = run_.result.estimate("indirect:m0")
        self.assertEqual(rows[label].ci, f"[{estimate.ci_low:.2f}, {estimate.ci_high:.2f}]")
        self.assertEqual(again.inputs["seed"], pm.DEFAULT_SEED)
        self.assertEqual(again.inputs["resamples"], 5000)
        self.assertEqual(again.tables, run_.tables)


# ------------------------------------------------------------------ the interface
class GuidedFlowTests(unittest.TestCase):
    def test_conditional_process_waits_for_the_researchers_model(self):
        from workspace_harness import Workspace

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_process.csv"
            synthetic().to_csv(path, index=False)
            ws = Workspace(root=Path(folder) / "data")
            try:
                ws.app.projects.create("Fictional conditional process")
                self.assertTrue(ws.run(ws.app.load_path(str(path))))
                for name, level in LEVELS.items():
                    ws.app.session.confirm_level(name, level)
                ws.click("nav-analyze")
                ws.click("goal-process")
                ws.choose("role-x", "x")
                ws.choose("role-y", "y")
                ws.check("role-mediators-m1")
                ws.choose("role-w", "w")
                self.assertTrue(ws.find("guided-run").disabled)
                self.assertTrue(ws.find_all("guided-choose-option"))
                self.assertTrue(ws.has_text("Model 7: W moderates the a path"))
                self.assertTrue(ws.has_text("Model 14: W moderates the b path"))
                ws.click("alt-conditional_process-14")
                for key in ("mediators_a_priori", "model14_path", "cross_sectional",
                            "assumptions"):
                    ws.check(f"design-confirm-{key}")
                self.assertFalse(ws.find("guided-run").disabled)
                ws.click("guided-run")
                entry = ws.app.session.results[-1]
                self.assertEqual(entry.run.title,
                                 "Conditional process (PROCESS-equivalent Model 14)")
                self.assertEqual(entry.options["method"], "14")
                self.assertEqual(entry.run.result.spec.model, "14")
                self.assertIn("I chose Model 14 (W moderates M → Y) from theory, before seeing "
                              "results", entry.confirmations)
            finally:
                ws.close()

    def test_the_form_shows_what_is_still_to_choose_in_latvian_and_russian(self):
        from workspace_harness import Workspace
        from workspace_text import t

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_process.csv"
            synthetic().to_csv(path, index=False)
            for language in ("lv", "ru"):
                ws = Workspace(root=Path(folder) / f"data-{language}", language=language)
                try:
                    self.assertTrue(ws.run(ws.app.load_path(str(path))))
                    for name, level in LEVELS.items():
                        ws.app.session.confirm_level(name, level)
                    page = ws.app.pages["analyze"]
                    page.mode, page.method = "all", "conditional_process"
                    page.form_roles = dict(ROLES["conditional_process"])
                    page.form_options = default_options(METHODS["conditional_process"])
                    ws.click("nav-analyze")
                    self.assertTrue(ws.find("form-run").disabled)
                    notice = t(language, "block.choose_option",
                               option=t(language, "option.moderated_path"))
                    self.assertTrue(ws.has_text(notice), language)
                finally:
                    ws.close()


if __name__ == "__main__":
    unittest.main()
