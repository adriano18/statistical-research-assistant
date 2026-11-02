# Statistical Research Assistant

A Python project for exploring research datasets and, later, selecting and interpreting statistical methods.

**Goal:** a small, transparent alternative to common SPSS workflows for psychology, marketing and business research. The program will calculate statistics using established Python libraries. A future assistant may explain results, but it must not invent numbers or choose tests without checking their assumptions.

## Development plan
1. **v0.1 Data inspection** — import CSV/XLSX, review variables, missing values and their inferred data types.
2. **v0.2 Descriptive statistics** — N, mean, median, SD, distributions and plots.
3. **v0.3 Research methods** — Cronbach's alpha, correlations, group comparison tests, effect sizes and confidence intervals.
4. **v0.4 Method advisor** — ask about the study design, propose tests and explain their assumptions.
5. **v0.5 Flet interface and reports** — interactive analysis, plots, Excel/PDF export.

## v0.1 Quick start

Requires Python 3.12 or newer. In PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python inspect_data.py examples/sample_survey.csv
python -m unittest discover -s tests -v
```

The sample dataset is fictional and is **not suitable for scientific conclusions**.

## Privacy and analysis notes
- Keep actual participants' data in the ignored `data/` folder. Do not commit identifiable research data.
- Numeric codes such as 1–5 can represent ordinal Likert responses or categorical groups. A numeric data type is not enough to determine the measurement scale or justify a statistical test.
- The first version inspects datasets only. It does **not** perform inferential statistics or automatically interpret research findings.

Developed as a learning project, with AI assistance for code explanations, documentation and debugging.
