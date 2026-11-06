# Stage 34 UX refinements (part D) — first increment

The product owner approved the Stage 33 direction and asked for better
progressive disclosure in Guided Analysis, better visibility of primary
results and graphs, and a smoother reporting workflow, without losing access
to any statistical procedure or advanced setting. This increment changes
three screens; each change is small, measured on the review screenshots
(fictional data, 1440 × 900 unless stated) and covered by
`tests/test_workspace_disclosure.py`.

| Change | Before (`docs/images/stage33/`) | After (`docs/images/stage34/`) |
|---|---|---|
| **Guided Analysis — the chosen question folds to one line.** After a goal is chosen, the eight-question grid collapses into "Compare groups · Do independent groups differ on an outcome?" with *Change question*, which shows all eight again (the current one stays selected and the answers given so far are kept). | `analyze_guided.png`: step 4 starts ≈ 955 px down; the *Run* button sits at the bottom edge of a 1300 px tall window | `analyze_guided_fold.png`: step 4 starts ≈ 757 px down — about 200 px higher, so the recommendation is on the first screen |
| **Results — the primary result first.** The figure follows the summary directly, before the key estimates and the APA tables; when the detail column is at least 1000 px wide (e.g. a 1920 px window) summary and figure stand side by side. | `results_detail.png`: the figure starts ≈ 1340 px down, below three cards | `results_detail.png`: the figure starts ≈ 615 px down; `results_wide.png`: summary and figure both on the first screen |
| **Reports — see what will be exported.** *Preview the exported text* (folded by default) shows exactly what *Export combined TXT* saves, with the study title; each item has *Show this result*. | `reports.png`: no preview; a result could only be found again in Results | `reports.png`: preview and a link per item |

Nothing else moved: the estimates, tables, checks, interpretation, full report,
provenance and exports are all still on the result page in the same order,
*All methods* keeps every procedure with its options, and the calculations
are unchanged (the preview is the same `combined_report()` text that is
exported, which the test compares byte for byte).

Still open from part D, for later increments: the Scientific Import PDF
viewer (zoom, fit width, page list), the questionnaire editor, and a Word
version of the combined report.
