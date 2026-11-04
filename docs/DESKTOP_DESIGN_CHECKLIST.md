# Desktop design and document questionnaire import acceptance checklist

This document covers the Stage 29 shell and document importer. Code-level CI
covers control creation and parser logic; these UI cases require a *real* Windows
or macOS desktop session. Use non-identifying fictional files only.

## Windows-first desktop shell

- Start in English with **Windows · square corners** selected.
- At a 1280 × 800 or larger window, verify the left navigation is approximately
  288 px wide and all menu entries remain readable in EN, LV and RU. Buttons
  should be at least 44 px high.
- Inspect Home, Dataset, Questionnaire Builder, Scale reliability and EFA/PCA.
  Panels, action buttons, sidebar entries and the title region should have
  square corners in the Windows setting.
- Resize from 1280 px down below 1060 px. Sidebar should disappear and compact
  navigation and Language/Appearance selectors should appear; statistics and
  questionnaire forms should remain accessible without clipped controls.
- Ensure the horizontal command menu (File, Data, Analysis, Reports, Database,
  Settings, AI assistant, Help) remains reachable when the window is narrow.
- Use Settings to choose **macOS · soft corners**, verify a visible difference,
  and restart the application. The preference should persist without changing
  survey answers or previously loaded datasets.
- In Russian and Latvian, inspect long navigation labels, selection states,
  focus rings and keyboard navigation; not all source-generated report text
  is translated yet.

## Top-level desktop actions

- File: Open Data workspace; navigate to Word/PDF import in questionnaire
  builder. The import path must remain local to the desktop app.
- Data: Dataset and data preparation open correctly without modifying data.
- Analysis: choose a real statistical module and run a fictional test.
- Reports: open the APA 7 interpretation wizard; if no calculation exists,
  it must transparently ask for an analysis rather than invent statistics.
- Database: navigate to saved local questionnaires/responses (SQLite).
- Settings: Windows and macOS inspired appearance can be selected.
- AI assistant: status honestly says **not connected / planned**, with no
  external data transfer.
- Help: privacy note visible.

## Import a questionnaire from Word/PDF

1. Create a fictional DOCX with numbered items (1., 2., Q3:), marked answer
   options (A), B)) and a short text question.
2. In Questionnaires > Build > Import questionnaire from Word / PDF, select
   the document. Check that the preview shows proposed prompts, options,
   a warning and no database changes.
3. Click **Use extracted questions as editable draft**, then inspect each
   question in the existing editor. All fields must be optional by default,
   numeric scale codes must not be fabricated, and conditional logic must not
   be guessed.
4. Start a new unsaved draft, attempt another import, and verify that existing
   questions are not replaced without checking the explicit confirmation.
5. Import a simple text-based PDF and confirm the same manual review flow.
6. Import a scanned PDF with no selectable text. It must show an OCR/manual
   review warning, not pretend it extracted responses.
7. Try an unnumbered document. It should report that numbered questions were
   not found rather than creating arbitrary questions.
8. After manual review, publish a fictional form and submit a test answer.
   Confirm that the resulting SQLite response/CSV codebook is intact.

## Known remaining work

- Native Windows and macOS screen recordings, 125%/150% DPI test, keyboard
  and screen reader audit.
- Full dark mode, visually comparable native WinUI/AppKit controls, menu
  keyboard accelerators, project file persistence and database backups.
- Table/matrix reconstruction from Word/PDF, scan OCR and faithful original
  question/section ordering.
- A true opt-in AI advisor with verified statistical facts, transparent
  provenance and explicit consent for any cloud access.
- Signed Windows installer and macOS packaging.
