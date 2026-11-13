# Stage 36.8 — Real-user acceptance

Two kinds of evidence, never merged into one "all passed":
1. **Automated acceptance**: the installed and packaged Windows program driven through UI Automation with real clicks, keys and dialogs, on GitHub's Windows runners.
2. **Manual acceptance by the owner**: the checklist in §3, on the owner's own PC. It needs no software-development knowledge.

## 1. The four separate statuses

| Status | State | Evidence |
|---|---|---|
| Automated QA passed | *see §2; filled in from the runs of the final RC commit* | GitHub Actions run IDs, artifacts with screenshots, recordings, logs and `*-result.json` |
| Manual user acceptance passed | **not yet**: the owner has not run §3 | the owner's filled-in checklist |
| Language review passed (LV, RU) | **not yet**: no native-speaker review has taken place | `docs/STAGE368_LOCALE_REVIEW.md` is the input for it |
| Production signing configured | **no**: `SRA_UPDATE_SIGNING_KEY` and the code-signing certificate are not configured; this is an **unsigned preview** | `docs/STAGE368_RELEASE_CHECKLIST.md` |

## 2. Automated journeys (installed and packaged Windows program)

Issue #62, Part 8, asks for eight journeys A–H. The table shows which journey covers each, and where its result is. Every journey records its steps, facts, screenshots or a recording, the program's log and the files it checked. A failed step also leaves the UI Automation tree and a screenshot at the moment it failed.

| Spec | Journey (workflow) | What is checked on the real program | Result on the final commit |
|---|---|---|---|
| A — projects | `project-a`, `project-b` (GUI journeys); `installed-data`, `installed-reopen` (installer) | create A, analyses, Word report, backup, restart, reopen; B starts empty; switching A ↔ B shows only each project's own data; the installed program keeps projects in the per-user data folder | |
| B — batch statistics | `stage36-tasks` | UCLA with eight scales in one batch: one table with N, interval, raw and Holm p; back to the task and run again in two actions; restart restores task and result | |
| C — groups | `stage36-groups`, `stage36-charts` | three quantile groups previewed, then created; eight scales by the groups in one Kruskal–Wallis batch | |
| D — charts | `stage36-charts` | chart type changed (violin, multi-boxplot); title typed; the clipboard holds a bitmap of the announced size; the view chosen for the report; restart restores the view | |
| E — questionnaire import | `import-cope-docx`, `import-30`, `import-scan-lv`, `review-120`, `import-resume` (new), `import-damaged` | two 60-item forms, one chosen, exactly 60 items; references kept out; the 52-item image-only PDF read with bundled OCR in Latvian (52 candidates, the legend as one unconfirmed scale); 120-item review keeps its place; an OCR reading cancelled, then completed; the saved review comes back after a restart; a damaged PDF is refused while a review goes on | |
| F — psychometrics | `psychometrics` (new), `stage36-report` | α, ω and α-if-deleted on item-level data, α compared with an independent computation; totals get no reliability coefficient | |
| G — Word report | `stage36-report`, `project-a` | two results in one report; sections "Descriptive statistics" and "Hypothesis tests"; Tables 1 and 2; reproducibility appendix; dataset name; the file is a real Word document | |
| H — install and update | installer workflow; update workflow (`update-refusals`, `update-a-to-b`) | silent per-user install; legacy data copied on request; B installed over A; uninstall keeps the research data; reinstall finds it; in-app update A → B: announced, what's new, interrupted download retried, signature, publisher and downgrade refusals, restart into B, the project opens in B and eight correlations run | |
| Negative paths | `blocked-design`, `import-damaged`, `update-refusals`, `negative-paths` (new) | invalid design refused in words; damaged files; update with another key, older version, damaged download; read-only save location; AI without a key or without project permission | |

Not automated, and why:
- **Reordering report sections, and the report composition surviving a restart.** The composition was not persisted before Stage 36.8 (review finding K2); see §4.
- **Narrator.** Screen-reader speech cannot be asserted on CI runners. UI Automation names and states, which Narrator reads, are checked.
- **Keyboard-only use of a whole journey.** Shortcuts are tested in the harness. A keyboard-only Windows journey is not yet written.

## 3. Manual acceptance checklist for the owner

Use a Windows 10 or 11 PC. You need about 45 minutes. You need two downloads from the release candidate's pull request, both from the run of the "Windows installer" check ("Artifacts" at the bottom of the run page):
- `StatisticalResearchAssistant-Setup-unsigned-preview`, the setup program;
- `synthetic-acceptance-files`: a 55-row UCLA/SACS-style dataset, a Word file with two 60-item forms, a scanned 52-item Latvian PDF and an item-level scale dataset, all invented.

Do **not** use real study data for this check.

The program always starts in the classic interface. Everything in this checklist after step 2 is in the research workspace: after every start, press **Open the preview** on the classic Home screen first. The program does not yet remember which interface was used last (§4).

For each step, tick **Works** or **Problem**. If there is a problem, write down three things, then go on with the next step:
- what you did;
- what you expected;
- what happened.

Add a screenshot (Win + Shift + S, then paste into a document) or the message text. You never need to open GitHub logs: send the checklist with your notes, and every problem becomes a reproducible test before it is fixed.

| # | Do this | You should see | Works / Problem |
|---|---|---|---|
| 1 | Run the setup program. Windows SmartScreen may say "Windows protected your PC": this preview is not signed yet. Choose **More info → Run anyway** only for this preview. | The setup finishes without asking for administrator rights; "Statistical Research Assistant" is in the Start menu | |
| 2 | Start the program from the Start menu. It opens in the **classic interface**. On its Home screen, under "Try the new research workspace", press **Open the preview** | The classic Home screen appears within about 10 seconds, not a black or empty window. After **Open the preview** you see the research workspace with Home, Data, Questionnaires, Analyze, Results and Reports on the left | |
| 3 | Create a project "Test A". Close the program, start it again and press **Open the preview** | "Test A" is offered again, with what you put in it | |
| 4 | Open `synthetic_ucla_sacs_55.csv` (Data → Open), then confirm the measurement levels it asks about | The variables are listed with their levels; nothing is silently changed | |
| 5 | Analyze: choose one scale and "all other scales", Spearman, then Run | One table: every pair with N, coefficient, interval, raw p and corrected p; a text that never claims causation | |
| 6 | Open the result's chart in Chart Studio. Change the chart type and the title, then press **Copy** and paste into Word | The chart in Word looks like the one in the program, with your title | |
| 7 | Questionnaires → Import: choose `synthetic_cope_two_forms_60_unnumbered.docx` | Both forms are shown; you choose one; its items, and no instructions or references, are listed | |
| 8 | Import `synthetic_lv_table_scan_52.pdf` and choose **Read with local OCR** (Latvian) | Progress shows which page is being read; then 52 candidate items, several marked "needs attention"; nothing is confirmed for you | |
| 9 | Close the program during step 8's review. Start it again, press **Open the preview** and open the same PDF | The review comes back where you left it | |
| 10 | Reports: add two results to the report, then **Save as Word** | The Word file opens in Word; its tables are real tables you can edit | |
| 11 | Settings → About and updates | The version number and "Check for updates"; with no newer version, it says so | |
| 12 | Uninstall the program (Windows Settings → Apps), then install it again and press **Open the preview** | Your project "Test A" is still there after reinstalling | |
| 13 | Throughout | You never had to install Python, Tesseract or anything else | |

When a newer preview is published: the program shows it with "What's new". Press **Update now**. The program closes, updates and starts again, and your projects are unchanged.

## 4. Known gaps that affect acceptance (documented, not hidden)

- Review findings K1–K3 were confirmed and are fixed on this RC branch (23f4f4a), with tests that failed before the fix. The details are in `docs/STAGE368_RELEASE_CHECKLIST.md` §3.
  - K1: design and data confirmations are now bound to what they were given for.
  - K2: notes, review ticks, the report title, left-out sections and language are now saved in the project.
  - K3: data preparation keeps the confirmed levels and is recorded in the project history.
  The Windows GUI journeys for K1 (another variable, then run again) and K2 (report order, title and sections after a restart) are listed in §2 when they have run.
- The installer is **unsigned**. SmartScreen warnings are expected and must not be bypassed for anyone but the owner testing this preview.
- **The program starts in the classic interface every time.** The research workspace opens from its Home screen ("Open the preview").
  - The automated journeys start the workspace directly (`SRA_UI=workspace`), so they do not cover this first click.
  - Whether the workspace should open by default, or the program should remember the last interface, is an owner decision for the next stage (`docs/STAGE368_RELEASE_CHECKLIST.md` §4).
