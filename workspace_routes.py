"""Traceable old → new route map for Stage 33 (feature parity contract).

Every classic screen, top-menu command and registered classic action has
exactly one destination in the research workspace. ``status`` is honest:

* ``workspace`` — available in the new workspace (same engine/storage);
* ``hosted``    — the validated classic component is shown inside the new
                  workspace unchanged (e.g. data preparation tools);
* ``partial``   — the main workflow is in the workspace; the listed
                  remaining controls are still reached through the classic
                  interface (one click: "Classic interface");
* ``classic``   — reachable from the workspace through the classic
                  interface until its replacement passes tests;
* ``retired``   — replaced by a better mechanism (reason given).

``tests/test_workspace_routes.py`` compares this map with the live
inventory produced by ``tools/ux_inventory.py``; a new classic command
without a destination fails CI.
"""

from __future__ import annotations

SCREENS: dict[str, tuple[str, str, str]] = {
    # classic key: (workspace route, status, note)
    "home": ("home", "workspace", "Start actions, current dataset, recent files, saved questionnaires"),
    "dataset": ("data", "workspace", "Import, diagnostics, variable dictionary, preview, import options"),
    "preparation": ("data#prepare", "hosted", "Classic non-destructive preparation tools inside Data"),
    "survey": ("questionnaires", "partial",
               "In the workspace: three-pane builder, templates, reusable scales, conditions, "
               "drag-and-drop, live preview, publish, collect, CSV + codebook, analyze, "
               "scientific import with scale review. Still classic: page titles and page-wise "
               "section reordering, DK/PNA missing options, free-form value-label editing, "
               "clone a published survey, multi-page respondent navigation, response table, "
               "matrix grid editor, region edits, 20-page OCR batch, binary-format bulk action"),
    "descriptive": ("analyze/all/descriptive", "workspace", "Also Explore distributions"),
    "reliability": ("analyze/all/omega", "workspace", "Cronbach α and McDonald ω (+ item analysis)"),
    "factor": ("analyze/all/factor", "workspace", "EFA / PCA"),
    "correlation": ("analyze/all/correlation", "workspace", "Pearson / Spearman"),
    "matrix": ("analyze/all/matrix", "workspace", "Correlation matrix"),
    "groups": ("analyze/all/groups", "workspace", "Welch t / Mann–Whitney U"),
    "paired": ("analyze/all/paired", "workspace", "Paired t / Wilcoxon"),
    "chi": ("analyze/all/chi", "workspace", "Chi-square"),
    "omnibus": ("analyze/all/omnibus", "workspace", "ANOVA / Welch ANOVA / Kruskal–Wallis + post-hoc in Results"),
    "regression": ("analyze/all/regression", "workspace", "Linear regression (HC3 option)"),
    "logistic": ("analyze/all/logistic", "workspace", "Binary logistic regression"),
    "ancova": ("analyze/all/ancova", "workspace", "ANCOVA / GLM"),
    "repeated": ("analyze/all/repeated", "workspace", "RM ANOVA / Friedman"),
}

# Classic analysis screens → method catalog keys (all methods, same engine).
SCREEN_METHODS: dict[str, tuple[str, ...]] = {
    "descriptive": ("descriptive", "explore"), "reliability": ("alpha", "omega"),
    "factor": ("factor",), "correlation": ("correlation",), "matrix": ("matrix",),
    "groups": ("groups",), "paired": ("paired",), "chi": ("chi",),
    "omnibus": ("omnibus",), "regression": ("regression",), "logistic": ("logistic",),
    "ancova": ("ancova",), "repeated": ("repeated",),
}

MENU: dict[tuple[str, str], tuple[str, str, str]] = {
    ("File", "Import CSV / Excel…"): ("data", "workspace", "Open CSV / Excel (Ctrl+O)"),
    ("File", "Import Word / PDF questionnaire…"): ("questionnaires/import", "workspace", "Scientific import"),
    ("File", "New questionnaire"): ("questionnaires", "workspace", "Add question / template"),
    ("File", "Recent files / Dataset"): ("home", "workspace", "Recent data files on Home"),
    ("Data", "Recent files / Dataset"): ("home", "workspace", "Recent data files on Home"),
    ("Data", "Prepare data"): ("data#prepare", "hosted", "Prepare data card"),
    ("Analysis", "Descriptive statistics"): ("analyze/all/descriptive", "workspace", ""),
    ("Analysis", "Scale reliability"): ("analyze/all/omega", "workspace", ""),
    ("Analysis", "EFA / PCA"): ("analyze/all/factor", "workspace", ""),
    ("Analysis", "Correlations"): ("analyze/all/correlation", "workspace", ""),
    ("Analysis", "Regression"): ("analyze/all/regression", "workspace", ""),
    ("Reports", "APA report wizard"): ("results", "workspace", "Assumption review, interpretation and Word export per result"),
    ("Reports", "Methodology and references"): ("results", "workspace", "Method notes appended to copied/saved reports"),
    ("Database", "Saved questionnaires and responses"): ("questionnaires", "workspace", "Published on this computer"),
    ("Settings", "Windows · square corners"): ("settings", "workspace", "Corner style"),
    ("Settings", "macOS · soft corners"): ("settings", "workspace", "Corner style"),
    ("Settings", "Offline OCR engine…"): ("settings", "workspace", "Check OCR engine"),
    ("Settings", "Your data…"): ("settings", "workspace", "Your data"),
    ("Settings", "Check for updates…"): ("settings", "workspace", "About and updates"),
    ("Help", "About and updates…"): ("settings", "workspace", "About and updates"),
    ("AI assistant", "AI assistant status"): ("help", "workspace", "Help & privacy: not connected"),
    ("AI assistant", "Methodology and references"): ("results", "workspace", ""),
    ("Help", "AI assistant status"): ("help", "workspace", ""),
    ("Help", "Data privacy"): ("help", "workspace", "Privacy section; Local only chip in the context bar"),
    ("Help", "Offline OCR engine…"): ("settings", "workspace", ""),
}

ACTIONS: dict[str, tuple[str, str, str]] = {
    "analyze_variable": ("analyze/all/descriptive", "workspace", "analysis_runs.run_descriptive"),
    "run_explore": ("analyze/all/explore", "workspace", "analysis_runs.run_explore"),
    "calculate_alpha": ("analyze/all/alpha", "workspace", "analysis_runs.run_alpha"),
    "calculate_omega": ("analyze/all/omega", "workspace", "analysis_runs.run_omega"),
    "calculate_factor_exploration": ("analyze/all/factor", "workspace", "analysis_runs.run_factor"),
    "calculate_correlation": ("analyze/all/correlation", "workspace", "analysis_runs.run_correlation"),
    "calculate_matrix": ("analyze/all/matrix", "workspace", "analysis_runs.run_matrix"),
    "calculate_groups": ("analyze/all/groups", "workspace", "analysis_runs.run_groups"),
    "calculate_paired": ("analyze/all/paired", "workspace", "analysis_runs.run_paired"),
    "calculate_chi_square": ("analyze/all/chi", "workspace", "analysis_runs.run_chi_square"),
    "calculate_omnibus": ("analyze/all/omnibus", "workspace", "analysis_runs.run_omnibus (+ run_posthoc)"),
    "run_regression": ("analyze/all/regression", "workspace", "analysis_runs.run_regression"),
    "run_logistic": ("analyze/all/logistic", "workspace", "analysis_runs.run_logistic"),
    "run_ancova": ("analyze/all/ancova", "workspace", "analysis_runs.run_ancova"),
    "run_repeated": ("analyze/all/repeated", "workspace", "analysis_runs.run_repeated"),
    "choose_file": ("data", "workspace", "Ctrl+O / Open CSV / Excel"),
    "choose_file_action": ("data", "workspace", "PickFiles client gesture"),
    "load_sample": ("data", "workspace", "Sample datasets"),
    "load_scale_example": ("data", "workspace", "Sample datasets"),
    "load_factor_example": ("data", "workspace", "Sample datasets"),
    "load_paired_example": ("data", "workspace", "Sample datasets"),
    "load_categorical_example": ("data", "workspace", "Sample datasets"),
    "load_three_groups_example": ("data", "workspace", "Sample datasets"),
    "load_regression_example": ("data", "workspace", "Sample datasets"),
    "load_logistic_example": ("data", "workspace", "Sample datasets"),
    "load_ancova_example": ("data", "workspace", "Sample datasets"),
    "load_ancova_interaction_example": ("data", "workspace", "Sample datasets"),
    "load_repeated_example": ("data", "workspace", "Sample datasets"),
    "open_report_wizard": ("results", "workspace", "Results: assumptions, interpretation, Word"),
    "open_survey_import": ("questionnaires/import", "workspace", "Scientific import"),
    "open_survey_responses": ("questionnaires", "workspace", "Published questionnaires and responses"),
    "open_workspace_preview": ("home", "workspace", "Entry point into this workspace"),
    "register_import_navigation": ("home", "retired", "Workspace routing replaces the classic screen switcher"),
    "set_active_screen": ("home", "retired", "Results log replaces the per-screen output cache"),
}

# Classic output toolbar and per-screen exports → Results exports.
EXPORTS: dict[str, tuple[str, str]] = {
    "Copy report": ("results", "Copy report (report + cited method notes, as classic)"),
    "Save TXT as...": ("results", "Save TXT… (classic save_selected_output)"),
    "Save PNG as...": ("results", "Save APA figure PNG… (classic make_apa7_export_png)"),
    "Save figure PNG": ("results", "Save APA figure PNG…"),
    "Save APA report TXT": ("results", "Save TXT…"),
    "Editable APA 7 Word report": ("results", "Save Word report… (classic save_apa_docx)"),
    "Save prepared CSV + steps JSON": ("data#prepare", "hosted classic preparation tools"),
    "Export CSV + codebook": ("questionnaires", "Export CSV + codebook…"),
    "Load responses into Dataset": ("questionnaires", "Analyze responses"),
}
