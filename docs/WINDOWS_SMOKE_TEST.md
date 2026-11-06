# Windows desktop smoke test: data → questionnaire → analysis → APA Word

Run these steps on a **local Windows desktop** with fictional data. Python CI cannot verify the native file dialog, display scaling, layout, or Microsoft Word rendering on the researcher's device.

## Preparation

Open PowerShell inside the repository checkout:

```powershell
git pull
python -m pip install -U -r requirements.txt
flet run app.py
```

Confirm that the Home screen appears. Change language from English to Русский, then Latviešu. Language changes must not alter loaded data or already published survey responses.

## A. External files and diagnostics

1. On Home select **Open CSV / Excel** and choose a CSV or XLSX file. The program should navigate to Dataset and show the filename, row and column counts and import diagnostics.
2. In Dataset → Import settings, verify that the **Full local file path** input is one normal-height field and never fills the viewport with gray. Paste an absolute path if the native dialog is blocked.
3. Attempt to import a missing file. The existing data must remain visible and an explicit error should appear. Cancelling the picker must not claim success.
4. Select another worksheet or a non-first header row if relevant to your workbook. Review any diagnostic warnings rather than assuming the file was correctly decoded.

## B. Marketing questionnaire and response import

1. Go to **Questionnaires → 1. Build**. Choose **Marketing / Feedback**, then **Load template**. This is fictional training content, not a validated instrument.
2. Open **2. Preview**. The screen must show questions rather than a black error page. Switch between Build and Preview three times. Choose **No** to hide the conditional experience rating; choose **Yes** to reveal it.
3. Set a meaningful survey title and choose **Create local questionnaire**. The published definition should remain immutable.
4. Under **3. Fill survey**, submit one or two synthetic answers. Inspect the row count and sample data under **4. Responses & export**.
5. Press **Load responses into Dataset**. On success the program should switch to Dataset, show **Questionnaire: [your title]**, and keep the source name outside the analytical columns. Skipped questions should be missing, not zero. Original scale answers should not be silently reverse-scored.
6. Repeat with a published survey that has no answers. The program must report the empty response set and remain in Questionnaires, not show a false successful import.

## C. Reliability, interpretation and editable Word

1. Under Dataset, load bundled `examples/sample_scale.csv` (fictional practice data). Check that the displayed dimensions match the file.
2. Open **Scale reliability**, select four same-construct items and confirm their scoring/direction. Calculate Cronbach's α.
3. Review the sample size, α, confidence interval, diagnostics and chart. Reverse-keyed questions must be explicitly recoded before analysis.
4. Expand **Interpretation wizard**, inspect the method, assumptions and estimates, write a fictional conclusion and export an editable DOCX.
5. Open the DOCX in Microsoft Word: check the numerical values against the calculation output, table cell editability, caption visibility, bibliography location and print layout. A raster chart is replaceable, not point-by-point editable.
6. Load a different dataset and check that older statistics and interpretations are not reused.

## D. Packaged preview: startup and True/False import

1. Extract the latest `StatisticalResearchAssistant-Windows-x64.zip` to a new folder and start `StatisticalResearchAssistant.exe`. Within about a second you should see a light screen with a spinner ("Starting…"), never a black window, and then the Home screen.
2. Close the app and start it again; note how long it takes until Home appears. Then open `%LOCALAPPDATA%\StatisticalResearchAssistant\logs\startup.log`. The last line shows timings such as `splash_shown` and `interface_ready`.
3. Import a fictional True/False questionnaire (PDF, DOCX or scan). The items must appear as **Single choice** with the printed labels (for example `T`/`F`), not as Short text. Use **BINARY ANSWERS** to rename them to `True`/`False` if needed.

## When reporting a problem

Include the operating system version, application language, the exact action, terminal traceback (or `startup.log` for the packaged app) and a screenshot. Do not provide real identifying participant data.

```powershell
python --version
python -m pip show flet
git rev-parse --short HEAD
```

**Acceptance:** All workflows run without frozen controls, oversized blank fields, false import claims, stale results or fabricated numerical estimates. Native keyboard and screen-reader testing and journal-specific APA quality assurance remain open.
