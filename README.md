# Statistical Research Assistant

A Python project for exploring research datasets and, later, selecting and interpreting statistical methods.

**Goal:** a small, transparent alternative to common SPSS workflows for psychology, marketing and business research. The program will calculate statistics using established Python libraries. A future assistant may explain results, but it must not invent numbers or choose tests without checking their assumptions.

## Development plan
1. **v0.1 Data inspection** — import CSV/XLSX, review variables, missing values and their inferred data types.
2. **v0.2 Descriptive statistics** (in progress) — N, mean, median, SD, distributions and plots.
3. **v0.3 Research methods** (in progress) — Cronbach's alpha, Pearson and Spearman correlations with safeguards; next: group comparisons and effect sizes.
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

The separate `examples/sample_scale.csv` contains 32 invented respondents and two missing answers, so 30 complete cases are analyzed. The result includes Cronbach’s α, a 95% confidence interval, alpha-if-item-deleted and warnings. The UI now shows a copyable APA 7-style sentence with Greek α and decimal notation (e.g., `α = .94, 95% CI [.89, .97]`), plus a PNG figure with the full-scale confidence interval and individual item-deletion estimates.

**Interpretive ranges are not APA 7 rules.** Approximate thresholds (< .60 low; .60–.69 questionable; .70–.79 often acceptable; .80–.89 good; .90–.95 very high; > .95 investigate redundancy) are contextual guidelines, not tests of scale validity. Compare scales with the relevant literature and study design. The figure number `Figure 1` is a placeholder to renumber if inserted into a manuscript. This synthetic dataset is not evidence for the reliability of any real instrument.

Alpha is not a test of scale validity or unidimensionality. Numerical column types alone are not grounds to treat variables as questionnaire items. The prototype uses listwise deletion and does not perform reverse scoring for you.

The sample dataset is fictional and is **not suitable for scientific conclusions**.

## Correlation demo

In the desktop app, click **Load scale example**. Under **CORRELATION ANALYSIS**, choose the two items \`stress_q1\` and \`stress_q2\`. Confirm **Ordinal** for both, keep **Spearman’s ρ**, then click **Calculate correlation**.

For Pearson, choose two genuinely quantitative measurements, confirm their scales, inspect whether a linear association and the study assumptions are appropriate, then select **Pearson’s r** and check its separate assumptions box. Numeric column storage alone does not justify Pearson. Do not include IDs or nominal groups.

Both methods report the correlation coefficient, a two-sided p-value, paired N, a scatterplot and a brief interpretation in APA 7-style notation. Pearson additionally reports a Fisher-transformation 95% CI. Spearman's CI is **not calculated** in this prototype; do not invent one. For datasets with up to 500 complete pairs, Spearman uses a seeded, 1,999-resample permutation p-value because SciPy warns its asymptotic p approximation is inaccurate for small datasets. This is a Monte Carlo estimate, not an exact test.

Plots show associations, not causality. The Figure 2 number is a placeholder and should be renumbered in a manuscript. The app does not choose the method automatically from the column data type; it supplies conditional guidance. For scientific analysis, consider dependence, outliers, monotonicity/linearity, sample design, effect interpretation and multiple testing.

## Privacy and analysis notes
- Keep actual participants' data in the ignored `data/` folder. Do not commit identifiable research data.
- Numeric codes such as 1–5 can represent ordinal Likert responses or categorical groups. A numeric data type is not enough to determine the measurement scale or justify a statistical test.
- The current version inspects datasets and calculates selected statistics and correlation tests. It does **not** automatically validate assumptions, establish causality or replace professional interpretation.

Developed as a learning project, with AI assistance for code explanations, documentation and debugging.
