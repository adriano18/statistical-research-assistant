"""Stage 37.0a: the hypothesis workflow as pure functions (research_workflow).

Every check of docs/STAGE37_DESIGN.md §7.7 that 37.0a implements has a case
that produces it and one that does not; acknowledgements are bound to the
facts they were given for; the next action follows its rules in order.
Synthetic facts only: nothing here touches a dataset or the interface.
"""

from __future__ import annotations

from pathlib import Path
import string
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import research_workflow as rw  # noqa: E402
from research_workflow import (  # noqa: E402
    AnalysisFacts, HypothesisFacts, HypothesisProgress, ProjectFacts, ResultFacts, Step, TaskFacts,
)
from workspace_text import LANGS, T  # noqa: E402

H = "0a1b2c3d4e5f"
TASK = "task-1"
SCALES = ("AssertiveAction", "SocialJoining", "CautiousAction")


def hypothesis(**changes) -> HypothesisFacts:
    values = {"id": H, "number": 1, "text": "Loneliness relates to coping",
              "standing": "confirmatory", "question_type": "relate"}
    values.update(changes)
    return HypothesisFacts(**values)


def result(**changes) -> ResultFacts:
    values = {"key": "1", "method": "batch_correlation",
              "options": {"method": "spearman", "adjust": "holm"},
              "names": ("UCLA", *SCALES), "assumptions": ("a", "b"), "reviewed": frozenset({"a", "b"}),
              "estimates": (("AssertiveAction", -0.24), ("SocialJoining", -0.1),
                            ("CautiousAction", 0.08)),
              "snapshot": {"id": H, "plan_version": 1}, "created": "2026-11-13T10:00:00"}
    values.update(changes)
    return ResultFacts(**values)


def analysis(**changes) -> AnalysisFacts:
    values = {"task_id": TASK, "title": "UCLA with 3 variables", "goal": "relate",
              "method": "batch_correlation", "options": {"method": "spearman", "adjust": "holm"},
              "selection": {"x": "UCLA", "y": list(SCALES)}, "family_size": 3,
              "results": (result(),)}
    values.update(changes)
    return AnalysisFacts(**values)


def keys(checks) -> list[str]:
    return [c.key for c in checks]


def check(checks, key):
    found = [c for c in checks if c.key == key]
    assert len(found) == 1, (key, keys(checks))
    return found[0]


def record(kind, check_key, task_id, facts_print, *, rid="r1", **extra) -> dict:
    return {"id": rid, "kind": kind, "check_key": check_key, "hypothesis_id": H,
            "task_id": task_id, "fingerprint": facts_print, "reason": "Because.", **extra}


def every_check() -> list:
    """At least one check of each key, warnings and passes, for the text tests."""
    history = [{"version": 1, "saved_at": "a", "plan": {"hypotheses": [
                    {"id": H, "priority": "primary"}]}, "runs_before": 0},
               {"version": 2, "saved_at": "b", "plan": {"hypotheses": [
                    {"id": H, "priority": "secondary"}]}, "runs_before": 2}]
    reason = {"id": "d1", "kind": "designation", "hypothesis_id": H, "plan_version": 2,
              "reason": "Groups of 3, 47 and 5."}
    groups = analysis(task_id="task-2", goal="compare", method="batch_groups",
                      options={"adjust": "none"}, selection={"group": "UCLA_Level",
                                                             "outcome": list(SCALES)},
                      groups=3, results=(result(key="3", snapshot=None, stale=True,
                                                reviewed=frozenset()),))
    changed = analysis(results=(result(), result(key="2", options={"method": "pearson",
                                                                     "adjust": "holm"})))
    out = []
    out += rw.hypothesis_checks(hypothesis())
    out += rw.hypothesis_checks(
        hypothesis(direction="less", alpha=0.01, standing="added_after_results", runs_before=2,
                   method_key="batch_correlation", method_options={"method": "pearson"},
                   roles={"x": "UCLA", "y": [*SCALES, "Avoidancen"]}),
        (changed, groups), history=rw.designation_history(history, [], H))
    out += rw.hypothesis_checks(hypothesis(standing="added_after_results", runs_before=1,
                                           priority="exploratory"), (analysis(),), [reason],
                                history=rw.designation_history(history, [reason], H))
    out += rw.hypothesis_checks(hypothesis(direction="greater"), (analysis(
        goal="compare", method="omnibus", options={"method": "kruskal"}, family_size=1,
        results=()),))
    # Stage 37.0b (review S8): a result calculated for a direction the plan no longer has.
    out += rw.hypothesis_checks(hypothesis(), (analysis(results=(result(snapshot={
        "id": H, "plan_version": 1, "priority": "primary", "direction": "less",
        "alpha": 0.05}),)),))
    return out


class DraftTests(unittest.TestCase):
    def test_every_question_type_has_a_draft_in_three_languages(self):
        from workspace_methods import GOALS

        self.assertEqual(rw.QUESTION_TYPES, GOALS, "question types are the guided goals")
        for kind in rw.QUESTION_TYPES:
            hint, h0 = rw.draft_keys(kind)
            for key in filter(None, (hint, h0)):
                self.assertIn(key, T, key)
                self.assertEqual(len(T[key]), len(LANGS))
                self.assertTrue(all(text.strip() for text in T[key]), key)
            self.assertEqual(h0 is not None, kind in rw.TESTABLE, kind)

    def test_h1_is_a_hint_and_h0_a_complete_statement(self):
        hint, h0 = rw.draft_keys("relate")
        self.assertIn("‹", T[hint][0], "H1 shows where the researcher's words go")
        self.assertNotIn("‹", T[h0][0], "H0 can be kept as it is")


class StepTests(unittest.TestCase):
    def test_a_new_unlinked_task_starts_at_its_variables(self):
        steps = rw.task_steps(TaskFacts())
        self.assertEqual([s.key for s in steps], list(rw.STEP_KEYS))
        self.assertEqual(steps[0], Step("hypothesis", "skipped"))
        self.assertEqual(steps[1], Step("variables", "current"))
        self.assertEqual(rw.next_step(steps), "variables")

    def test_a_finished_task(self):
        steps = rw.task_steps(TaskFacts(linked=True, variables_filled=True, design_ready=True,
                                        method_chosen=True, result="current", assumptions_total=3,
                                        assumptions_reviewed=3, note=True, report="current"))
        self.assertTrue(all(s.state == "done" for s in steps))
        self.assertEqual(rw.steps_complete(steps), 8)
        self.assertIsNone(rw.next_step(steps))

    def test_what_needs_attention(self):
        steps = {s.key: s.state for s in rw.task_steps(TaskFacts(
            linked=True, hypothesis_in_plan=False, variables_filled=True, variables_missing=True,
            design_ready=True, method_chosen=True, result="stale", assumptions_total=3,
            assumptions_reviewed=1, report="older"))}
        self.assertEqual(steps["hypothesis"], "attention", "its hypothesis left the plan")
        self.assertEqual(steps["variables"], "attention", "a variable left the dataset")
        self.assertEqual(steps["result"], "attention", "calculated before the data changed")
        self.assertEqual(steps["checks"], "attention", "two checks not reviewed")
        self.assertEqual(steps["interpretation"], "current")
        self.assertEqual(steps["report"], "attention", "an older result is in the report")

    def test_every_step_and_state_has_a_label_in_three_languages(self):
        for key in (*(f"steps.{k}" for k in rw.STEP_KEYS),
                    *(f"steps.state.{s}" for s in ("done", "current", "todo", "attention",
                                                   "skipped")), "steps.count"):
            self.assertIn(key, T, key)
            self.assertTrue(all(text.strip() for text in T[key]), key)

    def test_a_skipped_interpretation_counts_as_finished(self):
        steps = rw.task_steps(TaskFacts(linked=True, variables_filled=True, design_ready=True,
                                        method_chosen=True, result="current", note_skipped=True,
                                        report="current"))
        self.assertEqual({s.key: s.state for s in steps}["interpretation"], "skipped")
        self.assertEqual(rw.steps_complete(steps), 8)


class RecordTests(unittest.TestCase):
    def test_a_withdrawal_removes_what_it_withdraws(self):
        records = [{"id": "a", "kind": "acknowledgement"}, {"id": "b", "kind": "deviation"},
                   {"id": "c", "kind": "withdrawal", "supersedes": "a"}]
        self.assertEqual([r["id"] for r in rw.active_records(records)], ["b"])

    def test_the_fingerprint_is_canonical_and_follows_the_facts(self):
        one = rw.fingerprint("H-ALPHA", H, TASK, {"plan": 0.01, "analysis": 0.05})
        self.assertEqual(one, rw.fingerprint("H-ALPHA", H, TASK, {"analysis": 0.05, "plan": 0.01}))
        self.assertRegex(one, r"^[0-9a-f]{64}$")
        self.assertNotEqual(one, rw.fingerprint("H-ALPHA", H, TASK, {"plan": 0.02, "analysis": 0.05}))
        self.assertNotEqual(one, rw.fingerprint("H-ALPHA", H, "task-2", {"plan": 0.01, "analysis": 0.05}))


class CheckTests(unittest.TestCase):
    """One case that produces each check and one that does not."""

    def test_no_task(self):
        self.assertEqual(check(rw.hypothesis_checks(hypothesis()), "H-NO-TASK").state, "open")
        self.assertEqual(check(rw.hypothesis_checks(hypothesis(priority="exploratory")),
                               "H-NO-TASK").severity, "info")
        self.assertNotIn("H-NO-TASK", keys(rw.hypothesis_checks(hypothesis(), (analysis(),))))

    def test_a_directional_hypothesis_and_a_two_sided_test(self):
        checks = rw.hypothesis_checks(hypothesis(direction="less"), (analysis(),))
        found = check(checks, "H-DIR-TWOSIDED")
        self.assertEqual((found.severity, found.state, found.resolution),
                         ("warning", "open", "acknowledge"))
        self.assertNotIn("H-DIR-TWOSIDED", keys(rw.hypothesis_checks(hypothesis(), (analysis(),))))

    def test_a_directional_hypothesis_and_an_omnibus_test(self):
        groups = analysis(goal="compare", method="batch_groups", options={"adjust": "holm"},
                          selection={"group": "UCLA_Level", "outcome": list(SCALES)}, groups=3,
                          results=())
        checks = rw.hypothesis_checks(hypothesis(direction="greater"), (groups,))
        self.assertIn("H-DIR-OMNIBUS", keys(checks))
        self.assertNotIn("H-DIR-TWOSIDED", keys(checks), "one check per analysis")
        two = analysis(goal="compare", method="batch_groups", options={"adjust": "holm"},
                       groups=2, results=())
        self.assertNotIn("H-DIR-OMNIBUS",
                         keys(rw.hypothesis_checks(hypothesis(direction="greater"), (two,))))
        omnibus = analysis(goal="compare", method="omnibus", options={"method": "kruskal"},
                           family_size=1, results=())
        self.assertIn("H-DIR-OMNIBUS",
                      keys(rw.hypothesis_checks(hypothesis(direction="less"), (omnibus,))))

    def test_a_family_without_correction(self):
        found = check(rw.hypothesis_checks(hypothesis(), (analysis(
            options={"method": "spearman", "adjust": "none"}),)), "H-FAMILY-UNCORRECTED")
        self.assertEqual((found.severity, found.params["k"]), ("warning", 3))
        passed = check(rw.hypothesis_checks(hypothesis(), (analysis(),)), "H-FAMILY-UNCORRECTED")
        self.assertEqual(passed.severity, "passed")
        single = analysis(method="correlation", family_size=1, options={"method": "spearman"})
        self.assertNotIn("H-FAMILY-UNCORRECTED",
                         keys(rw.hypothesis_checks(hypothesis(), (single,))))

    def test_the_plans_alpha_and_the_analysis_alpha(self):
        found = check(rw.hypothesis_checks(hypothesis(alpha=0.01), (analysis(),)), "H-ALPHA")
        self.assertEqual(found.facts, {"plan": 0.01, "analysis": 0.05})
        self.assertNotIn("H-ALPHA", keys(rw.hypothesis_checks(hypothesis(), (analysis(),))))

    def test_unreviewed_assumptions(self):
        open_ = analysis(results=(result(reviewed=frozenset({"a"})),))
        found = check(rw.hypothesis_checks(hypothesis(), (open_,)), "H-ASSUMPTIONS-OPEN")
        self.assertEqual((found.state, found.params["count"], found.resolution),
                         ("open", 1, "review"))
        self.assertEqual(check(rw.hypothesis_checks(hypothesis(), (analysis(),)),
                               "H-ASSUMPTIONS-OPEN").severity, "passed")
        self.assertNotIn("H-ASSUMPTIONS-OPEN", [c.key for c in rw.open_checks(
            rw.hypothesis_checks(hypothesis(), (open_,)))], "ticked, not acknowledged")

    def test_a_stale_result(self):
        stale = analysis(results=(result(stale=True),))
        self.assertEqual(check(rw.hypothesis_checks(hypothesis(), (stale,)),
                               "H-RESULT-STALE").resolution, "recalculate")
        self.assertEqual(check(rw.hypothesis_checks(hypothesis(), (analysis(),)),
                               "H-RESULT-STALE").severity, "passed")

    def test_added_after_results(self):
        found = check(rw.hypothesis_checks(hypothesis(standing="added_after_results",
                                                      runs_before=2)), "H-ADDED-AFTER")
        self.assertEqual((found.severity, found.resolution), ("warning", "justify"))
        exploratory = check(rw.hypothesis_checks(hypothesis(
            standing="added_after_results", runs_before=2, priority="exploratory")),
            "H-ADDED-AFTER")
        self.assertEqual(exploratory.severity, "info")
        self.assertNotIn("H-ADDED-AFTER", keys(rw.hypothesis_checks(hypothesis())))

    def test_a_designation_changed_after_results(self):
        history = [{"version": 1, "saved_at": "a", "plan": {"hypotheses": [
                        {"id": H, "priority": "primary"}]}, "runs_before": 0},
                   {"version": 2, "saved_at": "b", "plan": {"hypotheses": [
                        {"id": H, "priority": "secondary"}]}, "runs_before": 2}]
        unexplained = rw.designation_history(history, [], H)
        found = check(rw.hypothesis_checks(hypothesis(), history=unexplained),
                      "H-DESIGNATION-CHANGED")
        self.assertEqual((found.state, found.resolution), ("open", "justify"))
        reason = {"id": "d1", "kind": "designation", "hypothesis_id": H, "plan_version": 2,
                  "reason": "Groups of 3, 47 and 5."}
        explained = rw.designation_history(history, [reason], H)
        found = check(rw.hypothesis_checks(hypothesis(), (), [reason], history=explained),
                      "H-DESIGNATION-CHANGED")
        self.assertEqual((found.state, found.record_id, found.params["reason"]),
                         ("recorded", "d1", "Groups of 3, 47 and 5."))
        before = [{**history[1], "runs_before": 0}]
        self.assertNotIn("H-DESIGNATION-CHANGED", keys(rw.hypothesis_checks(
            hypothesis(), history=rw.designation_history([history[0], *before], [], H))))

    def test_the_method_differs_from_the_plan(self):
        planned = hypothesis(method_key="batch_correlation", method_options={"method": "pearson"})
        found = check(rw.hypothesis_checks(planned, (analysis(),)), "H-METHOD-DIFFERS")
        self.assertEqual((found.resolution, found.facts["actual"]["options"]["method"]),
                         ("deviation", "spearman"))
        same = hypothesis(method_key="batch_correlation", method_options={"method": "spearman"})
        self.assertNotIn("H-METHOD-DIFFERS", keys(rw.hypothesis_checks(same, (analysis(),))))
        self.assertNotIn("H-METHOD-DIFFERS", keys(rw.hypothesis_checks(hypothesis(), (analysis(),))),
                         "nothing planned, nothing to compare")

    def test_the_variables_differ_from_the_plan(self):
        planned = hypothesis(roles={"x": "UCLA", "y": [*SCALES, "Avoidancen"]})
        found = check(rw.hypothesis_checks(planned, (analysis(),)), "H-VARIABLES-DIFFER")
        self.assertEqual((found.params["missing"], found.params["extra"]), ("Avoidancen", "—"))
        same = hypothesis(roles={"x": "UCLA", "y": list(reversed(SCALES))})
        self.assertNotIn("H-VARIABLES-DIFFER", keys(rw.hypothesis_checks(same, (analysis(),))))

    def test_the_analysis_changed_after_its_first_result(self):
        changed = analysis(results=(result(), result(key="2", options={"method": "pearson",
                                                                         "adjust": "holm"})))
        found = check(rw.hypothesis_checks(hypothesis(), (changed,)), "H-SPEC-CHANGED")
        self.assertEqual(found.facts["first"]["options"]["method"], "spearman")
        self.assertEqual(found.facts["later"]["options"]["method"], "pearson")
        again = analysis(results=(result(), result(key="2")))
        self.assertNotIn("H-SPEC-CHANGED", keys(rw.hypothesis_checks(hypothesis(), (again,))))

    def test_linked_after_calculation(self):
        late = analysis(results=(result(snapshot=None),))
        self.assertEqual(check(rw.hypothesis_checks(hypothesis(), (late,)),
                               "H-LINKED-LATE").severity, "info")
        self.assertNotIn("H-LINKED-LATE", keys(rw.hypothesis_checks(hypothesis(), (analysis(),))))

    def test_coefficients_against_the_predicted_direction(self):
        found = check(rw.hypothesis_checks(hypothesis(direction="less"), (analysis(),)),
                      "H-DIR-SIGN")
        self.assertEqual((found.severity, found.params["names"], found.params["total"]),
                         ("info", "CautiousAction", 3))
        self.assertNotIn("H-DIR-SIGN", keys(rw.hypothesis_checks(hypothesis(), (analysis(),))),
                         "a two-sided hypothesis predicts no sign")
        negative = analysis(results=(result(estimates=(("AssertiveAction", -0.24),)),))
        self.assertNotIn("H-DIR-SIGN", keys(rw.hypothesis_checks(hypothesis(direction="less"),
                                                                  (negative,))))

    def test_one_family_split_over_two_analyses(self):
        second = analysis(task_id="task-2", goal="compare", method="batch_groups",
                          options={"adjust": "holm"}, family_size=3)
        found = check(rw.hypothesis_checks(hypothesis(), (analysis(), second)), "H-FAMILY-SPLIT")
        self.assertEqual(found.params["total"], 6)
        peers = ((2, second),)
        self.assertIn("H-FAMILY-SPLIT", keys(rw.hypothesis_checks(
            hypothesis(family="coping"), (analysis(),), peers=peers)), "same family label")
        self.assertNotIn("H-FAMILY-SPLIT", keys(rw.hypothesis_checks(hypothesis(), (analysis(),))))

    def test_checks_follow_one_order_and_never_say_supported(self):
        checks = rw.hypothesis_checks(hypothesis(direction="less", alpha=0.01,
                                                 standing="added_after_results", runs_before=1),
                                      (analysis(options={"method": "spearman", "adjust": "none"},
                                                results=(result(snapshot=None, stale=True),)),))
        order = [rw.CHECK_KEYS.index(c.key) for c in checks]
        self.assertEqual(order, sorted(order))
        for c in checks:
            self.assertNotIn("support", c.text)
            for language in range(len(LANGS)):
                self.assertNotIn("support", T[c.text][language].lower())

    def test_every_check_reads_in_three_languages(self):
        checks = every_check()
        self.assertEqual({c.key for c in checks}, set(rw.CHECK_KEYS), "all 16 checks covered")
        for c in checks:
            for language in LANGS:
                with self.subTest(check=c.key, text=c.text, language=language):
                    message = rw.check_message(c, language)
                    self.assertTrue(message.strip())
                    self.assertNotIn("{", message)
                    self.assertNotRegex(message, r"\b(check|plan)\.[a-z_]+", "a bare key")
        two_sided = check(rw.hypothesis_checks(hypothesis(direction="less"), (analysis(),)),
                          "H-DIR-TWOSIDED")
        self.assertEqual(rw.check_message(two_sided, "en"),
                         "H1 predicts a direction (“Less (one-sided)”), but Spearman’s ρ reports "
                         "two-sided p-values only. The result is a two-sided test of H1.")
        alpha = check(rw.hypothesis_checks(hypothesis(alpha=0.01), (analysis(),)), "H-ALPHA")
        self.assertIn("α = 0.01", rw.check_message(alpha, "en"))
        self.assertIn("α = 0.05", rw.check_message(alpha, "en"))

    def test_every_check_text_exists_with_its_placeholders(self):
        formatter = string.Formatter()
        texts = {"check.no_task", "check.dir_twosided", "check.dir_omnibus", "check.dir_sign",
                 "check.family_uncorrected", "check.family_ok", "check.family_split", "check.alpha",
                 "check.method_differs", "check.variables_differ", "check.spec_changed",
                 "check.assumptions_open", "check.assumptions_ok", "check.result_stale",
                 "check.result_ok", "check.designation_changed", "check.designation_unexplained",
                 "check.added_after", "check.added_after_exploratory", "check.linked_late"}
        for key in texts:
            self.assertIn(key, T, key)
            fields = {f for _, f, _, _ in formatter.parse(T[key][0]) if f}
            self.assertTrue(fields <= {"h", "direction", "method", "test", "groups", "k", "adjust",
                                       "plan", "analysis", "count", "runs", "from", "to", "reason",
                                       "version", "planned", "actual", "missing", "extra", "names",
                                       "total", "label"}, key)


class AcknowledgementTests(unittest.TestCase):
    """An acknowledgement holds while its facts are the same, then reopens."""

    def test_an_acknowledgement_reopens_when_the_facts_change(self):
        h = hypothesis(direction="less")
        first = check(rw.hypothesis_checks(h, (analysis(),)), "H-DIR-TWOSIDED")
        ack = record("acknowledgement", "H-DIR-TWOSIDED", TASK, first.fingerprint)
        held = check(rw.hypothesis_checks(h, (analysis(),), [ack]), "H-DIR-TWOSIDED")
        self.assertEqual((held.state, held.record_id), ("acknowledged", "r1"))
        self.assertFalse(held.needs_decision)
        # Another test (Pearson instead of Spearman): what was acknowledged changed.
        pearson = analysis(options={"method": "pearson", "adjust": "holm"})
        self.assertEqual(check(rw.hypothesis_checks(h, (pearson,), [ack]), "H-DIR-TWOSIDED").state,
                         "open")
        # The other direction: also reopened.
        self.assertEqual(check(rw.hypothesis_checks(hypothesis(direction="greater"),
                                                     (analysis(),), [ack]),
                               "H-DIR-TWOSIDED").state, "open")

    def test_a_withdrawn_acknowledgement_no_longer_holds(self):
        h = hypothesis(direction="less")
        first = check(rw.hypothesis_checks(h, (analysis(),)), "H-DIR-TWOSIDED")
        records = [record("acknowledgement", "H-DIR-TWOSIDED", TASK, first.fingerprint),
                   {"id": "w1", "kind": "withdrawal", "supersedes": "r1", "reason": "Wrong."}]
        self.assertEqual(check(rw.hypothesis_checks(h, (analysis(),), records),
                               "H-DIR-TWOSIDED").state, "open")

    def test_a_deviation_resolves_a_deviation_check_only(self):
        planned = hypothesis(method_key="batch_correlation", method_options={"method": "pearson"})
        found = check(rw.hypothesis_checks(planned, (analysis(),)), "H-METHOD-DIFFERS")
        wrong_kind = record("acknowledgement", "H-METHOD-DIFFERS", TASK, found.fingerprint)
        self.assertEqual(check(rw.hypothesis_checks(planned, (analysis(),), [wrong_kind]),
                               "H-METHOD-DIFFERS").state, "open")
        deviation = record("deviation", "H-METHOD-DIFFERS", TASK, found.fingerprint)
        self.assertEqual(check(rw.hypothesis_checks(planned, (analysis(),), [deviation]),
                               "H-METHOD-DIFFERS").state, "recorded")

    def test_a_justification_resolves_a_hypothesis_added_after_results(self):
        h = hypothesis(standing="added_after_results", runs_before=2)
        found = check(rw.hypothesis_checks(h), "H-ADDED-AFTER")
        justified = record("justification", "H-ADDED-AFTER", None, found.fingerprint)
        self.assertEqual(check(rw.hypothesis_checks(h, (), [justified]), "H-ADDED-AFTER").state,
                         "recorded")


class SnapshotTests(unittest.TestCase):
    def test_a_result_records_the_hypothesis_as_planned_then(self):
        plan = {"version": 3, "plan": {"hypotheses": [
            {"id": H, "priority": "primary", "direction": "less", "alpha": 0.05,
             "question_id": "aaaaaaaaaaaa"}]}}
        status = {H: {"standing": "confirmatory"}}
        self.assertEqual(rw.hypothesis_snapshot(plan, status, H), {
            "id": H, "plan_version": 3, "priority": "primary", "direction": "less",
            "alpha": 0.05, "standing": "confirmatory", "question_id": "aaaaaaaaaaaa"})
        self.assertIsNone(rw.hypothesis_snapshot(plan, status, "ffffffffffff"))
        self.assertIsNone(rw.hypothesis_snapshot(None, status, H))


def progress(**changes) -> HypothesisProgress:
    values = {"id": H, "number": 1, "task_id": TASK, "result_id": 7,
              "steps": rw.task_steps(TaskFacts(linked=True, variables_filled=True,
                                               design_ready=True, method_chosen=True,
                                               result="current", assumptions_total=3,
                                               assumptions_reviewed=3, note=True,
                                               report="current"))}
    values.update(changes)
    return HypothesisProgress(**values)


def steps(**facts):
    base = {"linked": True, "variables_filled": True, "design_ready": True, "method_chosen": True,
            "result": "current", "assumptions_total": 3, "assumptions_reviewed": 3, "note": True,
            "report": "current"}
    base.update(facts)
    return rw.task_steps(TaskFacts(**base))


PLANNED = {"plan_started": True, "has_data": True, "has_results": True, "report_count": 1}


class NextActionTests(unittest.TestCase):
    def rule(self, **facts):
        return rw.next_action(ProjectFacts(**facts))

    def test_without_a_plan_the_stage_34_order_stays(self):
        first = self.rule()
        self.assertEqual((first.rule, first.title), ("add_data", "next.add_data"))
        self.assertEqual([a.data for a in first.actions],
                         ["next-open-data", "next-sample", "next-questionnaire", "next-question"])
        self.assertEqual(self.rule(has_data=True, pending_levels=3).title, "next.levels")
        self.assertEqual(self.rule(has_data=True).title, "next.analyze")
        self.assertEqual(self.rule(has_data=True, has_results=True, stale_results=1).title,
                         "next.stale")
        self.assertEqual(self.rule(has_data=True, has_results=True).title, "next.report")
        self.assertEqual(self.rule(has_data=True, has_results=True, report_count=2).title,
                         "next.export")
        self.assertEqual(self.rule(has_data=True, has_results=True, report_count=2,
                                   exported=True).title, "next.done")

    def test_the_plan_comes_first_once_it_is_started(self):
        self.assertEqual(self.rule(plan_started=True, question_incomplete=1).rule, "N1")
        n2 = self.rule(plan_started=True, question_without_hypothesis=1)
        self.assertEqual((n2.rule, n2.actions[0].data), ("N2", "next-add-hypothesis"))
        self.assertEqual(self.rule(plan_started=True, hypothesis_incomplete=1).title,
                         "next.write_hypothesis")
        n3 = self.rule(plan_started=True, plan_dirty=True)
        self.assertEqual((n3.rule, n3.actions[0].data), ("N3", "next-save-plan"))
        self.assertEqual(self.rule(plan_started=True).title, "next.add_data", "N4")
        self.assertEqual(self.rule(plan_started=True, has_data=True, pending_levels=2).rule, "N5")

    def test_each_hypothesis_in_designation_order(self):
        secondary = progress(id="b" * 12, number=2, priority="secondary", task_id=None)
        primary = progress(id="a" * 12, number=1, task_id=None)
        n6a = self.rule(**PLANNED, hypotheses=(secondary, primary))
        self.assertEqual((n6a.rule, n6a.params, n6a.actions[0].target), ("N6a", {"h": 1}, "a" * 12))
        exploratory = progress(priority="exploratory", task_id=None)
        self.assertEqual(self.rule(**PLANNED, hypotheses=(exploratory,)).title, "next.export",
                         "an exploratory hypothesis needs no analysis")

    def test_each_step_of_a_hypothesis(self):
        cases = {
            "N6b": progress(steps=steps(result="none")),
            "N6c": progress(steps=steps(result="stale")),
            "N6d": progress(open_checks=("H-DIR-TWOSIDED",)),
            "N6e": progress(steps=steps(assumptions_reviewed=1)),
            "N6f": progress(steps=steps(note=False)),
            "N6g": progress(steps=steps(report="none")),
        }
        for rule, item in cases.items():
            with self.subTest(rule=rule):
                self.assertEqual(self.rule(**PLANNED, hypotheses=(item,)).rule, rule)
        skip = self.rule(**PLANNED, hypotheses=(cases["N6f"],))
        self.assertEqual([a.data for a in skip.actions], ["next-note", "next-skip-note"])

    def test_every_action_names_a_button_and_every_title_has_text(self):
        facts = [ProjectFacts(), ProjectFacts(has_data=True, pending_levels=1),
                 ProjectFacts(**PLANNED, hypotheses=(progress(task_id=None),)),
                 ProjectFacts(**PLANNED, hypotheses=(progress(open_checks=("H-ALPHA",)),)),
                 ProjectFacts(**PLANNED, exported=True, hypotheses=(progress(),))]
        for fact in facts:
            action = rw.next_action(fact)
            for key in (action.title, action.body, *(a.label for a in action.actions),
                        *(w[1] for w in action.why)):
                self.assertIn(key, T, key)
            self.assertTrue(all(a.data.startswith("next-") for a in action.actions))

    def test_every_rule_reads_in_three_languages(self):
        """Each rule's title, body, buttons and reasons format with its values."""
        from workspace_text import t

        cases = [ProjectFacts(), ProjectFacts(has_data=True, pending_levels=2),
                 ProjectFacts(has_data=True), ProjectFacts(has_data=True, has_results=True,
                                                           stale_results=1),
                 ProjectFacts(has_data=True, has_results=True),
                 ProjectFacts(has_data=True, has_results=True, report_count=1),
                 ProjectFacts(has_data=True, has_results=True, report_count=1, exported=True),
                 ProjectFacts(plan_started=True, question_incomplete=1),
                 ProjectFacts(plan_started=True, question_without_hypothesis=2),
                 ProjectFacts(plan_started=True, hypothesis_incomplete=1),
                 ProjectFacts(plan_started=True, plan_dirty=True),
                 ProjectFacts(plan_started=True, has_data=True, pending_levels=1),
                 ProjectFacts(**PLANNED, hypotheses=(progress(task_id=None),)),
                 ProjectFacts(**PLANNED, hypotheses=(progress(steps=steps(result="none")),)),
                 ProjectFacts(**PLANNED, hypotheses=(progress(steps=steps(result="stale")),)),
                 ProjectFacts(**PLANNED, hypotheses=(progress(open_checks=("H-ALPHA",)),)),
                 ProjectFacts(**PLANNED, hypotheses=(progress(steps=steps(
                     assumptions_reviewed=1)),)),
                 ProjectFacts(**PLANNED, hypotheses=(progress(steps=steps(note=False)),)),
                 ProjectFacts(**PLANNED, hypotheses=(progress(steps=steps(report="none")),)),
                 ProjectFacts(**PLANNED, exported=True, hypotheses=(progress(),))]
        rules = set()
        for fact in cases:
            action = rw.next_action(fact)
            rules.add(action.rule)
            for language in LANGS:
                texts = [t(language, action.title, **action.params),
                         t(language, action.body, **action.params),
                         *(t(language, a.label, **action.params) for a in action.actions),
                         *(t(language, key, **values) for _, key, values in action.why)]
                for text in texts:
                    self.assertTrue(text.strip())
                    self.assertNotIn("{", text, (action.rule, language, text))
        self.assertEqual(rules, {"add_data", "levels", "analyze", "stale", "report", "export",
                                 "done", "N1", "N2", "N3", "N5", "N6a", "N6b", "N6c", "N6d",
                                 "N6e", "N6f", "N6g"})


if __name__ == "__main__":
    unittest.main()
