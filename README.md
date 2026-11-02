# Statistical Research Assistant

A Python project for exploring research datasets and, later, selecting and interpreting statistical methods.

**Goal:** a small, transparent alternative to common SPSS workflows for psychology, marketing and business research. The program will calculate statistics using established Python libraries. A future assistant may explain results, but it must not invent numbers or choose tests without checking their assumptions.

## Development plan
1. **v0.1 Data inspection** — import CSV/XLSX, review variables, missing values and their inferred data types.
2. **v0.2 Descriptive statistics** (in progress) — N, mean, median, SD, distributions and plots.
3. **v0.3 Research methods** (in progress) — Cronbach's alpha with confidence interval and listwise missing-data handling; next: correlations, group comparisons and effect sizes.
4. **v0.4 Method advisor** — ask about the study design, propose tests and explain their assumptions.
5. **v0.5 Flet interface and reports** — interactive analysis, plots, Excel/PDF export.

## Quick start

Requires Python 3.12 or newer. In PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python inspect_data.py examples/sample_survey.csv
python -m unittest discover -s tests -v
flet run app.py
```

The Flet app has **Open CSV / Excel** and **Load example** buttons. Select a variable and confirm its measurement scale before using **Analyze selected variable**. Columns named like `participant_id` are flagged as identifiers and excluded from score statistics. Quantitative variables show N, mean, median, SD and a histogram; nominal and ordinal variables show frequency counts and a bar chart. Brief guidance explains what these descriptive results do and do not establish. Real data is processed locally, not uploaded.

## Scale reliability demo

In the desktop app, click **Load scale example**. Select `stress_q1`, `stress_q2`, `stress_q3` and `stress_q4`. Confirm that the selected items measure a single construct and any reverse-coded items have already been recoded, then click **Calculate Cronbach's alpha**.

The separate `examples/sample_scale.csv` contains 32 invented respondents and two missing answers, so 30 complete cases are analyzed. The result includes alpha, a 95% confidence interval, alpha-if-item-deleted and warnings. This synthetic dataset is not evidence for the reliability of any real instrument.

Alpha is not a test of scale validity or unidimensionality. Numerical column types alone are not grounds to treat variables as questionnaire items. The prototype uses listwise deletion and does not perform reverse scoring for you.

The sample dataset is fictional and is **not suitable for scientific conclusions**.

## Privacy and analysis notes
- Keep actual participants' data in the ignored `data/` folder. Do not commit identifiable research data.
- Numeric codes such as 1–5 can represent ordinal Likert responses or categorical groups. A numeric data type is not enough to determine the measurement scale or justify a statistical test.
- The current version inspects datasets and provides descriptive statistics only. It does **not** perform inferential statistics or automatically interpret research findings.

Developed as a learning project, with AI assistance for code explanations, documentation and debugging.
