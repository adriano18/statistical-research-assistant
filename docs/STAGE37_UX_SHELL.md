# Stage 37 — the workspace as the normal start, one settings file, language, typography (Issue #68)

> Branch `claude/stage37-ux-shell` (on `claude/stage37-ux`, the UX baseline `b83567c`). It implements the parts UX-1 and UX-2 of the independent review (`docs/STAGE37_FABLE_NARROW_REVIEW.md` §8) and the owner's requirements of `docs/STAGE37_NEXT_SPEC.md` §3: findings **D1, D2, D6, D11, U1, U10, U11, U12**. UX-3 (variable panel with search, prefix and range; eligible variables only: D7, U2) and the number formats of D10 are other branches. Synthetic data only. Everything below was run on Linux; the two new Windows journeys are written and walked in the harness, not yet run on a Windows runner (§7).

## 1. What a researcher sees

| Before (review evidence) | Now |
|---|---|
| The classic interface opened first; the workspace needed *Open the preview* and was labelled "Preview" and "Prototype" (U1). | The program starts in the **research workspace**. No Preview/Prototype label. The classic interface is one click away: *Classic interface* in the sidebar, a card in Help, a button in Settings; its Home leads back (*Open the research workspace*). **Settings → Start → Interface at start** chooses which one opens. |
| A language chosen in the workspace was lost at the next start without a researcher profile (D1). | Every language choice is kept, profile or not. The classic screens follow it when the researcher switches back. |
| Theme and window were not kept; every start opened 1200 × 720 (D2). | Theme (light, dark, **system**), accent, corner style, typeface, text size, density, window size, position and maximized state, the sidebar, and the last project with its page are kept. |
| The top bar showed EN, LV and RU (U12). | **EN** and **LV** quick buttons; a **globe menu** next to them lists English, Latviešu and Русский (the current one ticked) and *Language settings…*; Settings → Language lists all three. A Russian preference of an earlier version starts the program in Russian and is never reset. |
| No text size or density; Segoe UI only as Flutter's platform default; charts in DejaVu Sans (U12, H3). | **Segoe UI** (or **Segoe UI Variable**, Windows 11) named in the theme with a fallback list that covers Latvian and Cyrillic; no font file is shipped. **Text size 90 / 100 / 110 / 125 %**, **comfortable / compact** density. Charts use Segoe UI where matplotlib finds it, else DejaVu Sans. |
| Settings on one long page without structure. | One **Settings hub**: Appearance · Text and density · Language · Start · Projects and data folder · Backups · Updates · AI privacy · Researcher profile · OCR · Reset settings or delete data, with an index at the top. Other features add a section with one entry (§5). |
| The hosted *Prepare data* caption was 2.06:1 on white (D6). | 5.8:1 in the classic screens; the theme's text colour in the workspace (light and dark). |
| Reports: "2. Pētījuma jautājums · 1 parts" (D11). | "1 part", "2 parts" (and LV/RU plural forms); a line says that section titles are shown in the report's language when it differs from the interface. |
| The research question field was about 300 px wide (U10). | It takes the card's width. |
| No focus management (U11). | After *Create project* the keyboard focus is on *Open data…*; after opening a project, on its next step; after *Create the analysis for H…*, on the first variable choice; dialogs open with their safe answer (Cancel, Close) or their main action focused. |

Mandatory scientific confirmations are untouched: no setting skips, pre-ticks or hides one.

## 2. One settings file (`user_settings.py`)

**Where.** `<data folder>/settings.json`, beside `projects/`, `surveys/` and `profile/` (`app_paths.data_root`: `%LOCALAPPDATA%\StatisticalResearchAssistant` for the installed program, `$SRA_DATA_DIR` for tests and portable use). Per user, outside the program folder: installing, updating and uninstalling never change it. Settings → Projects and data folder shows the path.

**Keys** (anything else is kept as written):

| Key | Values (default first) |
|---|---|
| `language` | `en`, `lv`, `ru` |
| `theme` | `light`, `dark`, `system` |
| `accent` | `blue`, `teal`, `violet`, `graphite` |
| `corners` | `windows`, `macos` (the classic interface's style too) |
| `typeface` | `segoe` (Segoe UI), `segoe_variable` (Segoe UI Variable Text) |
| `text_scale` | `100`, `90`, `110`, `125` (per cent) |
| `density` | `comfortable`, `compact` |
| `start_interface` | `workspace`, `classic` |
| `sidebar_expanded` | none (by window width), `true`, `false` |
| `last_project`, `last_route` | the project and page of the last session (Home offers *Continue*) |
| `window` | `width`, `height`, `left`, `top` (logical px), `maximized` |
| `recent_files` | up to 8 paths |

**Rules.**
- *Migration, once.* When the file does not exist, it is made from what earlier versions kept: `~/.statistical_research_assistant/preferences.json` (language, recent files, classic style → `corners`), `workspace.json` beside it (accent) and the researcher profile's language. These files are only read: never changed, moved or deleted, so an earlier version still finds them. `migrated` records which were read and when.
- *Language of an earlier version.* English is the default everywhere, so another language is a choice: it is kept over English wherever it was stored (preferences or profile). If both name different non-English languages, the profile's (the workspace's) is kept. A preferences file with `"language": "ru"` therefore starts the program in Russian.
- *Unknown values are never rewritten.* A value this version does not offer (a language, theme or key of a later version, or a hand-edited one) stays in the file as it is; the program shows its default. A save writes only the keys that changed, after reading the file again. `app_preferences` (the classic screens) follows the same rule: it no longer writes a language it read as unknown.
- *Atomic, never fatal.* Temporary file, fsync, replace. A write that fails leaves the change for this session and says so in the status line. An unreadable file gives the defaults and is kept aside as `settings.damaged.json` before anything new is saved; it is not migrated over.
- *Reset settings* (Settings → Reset settings or delete data, confirmed in a dialog whose focused answer is Cancel) writes the defaults and keeps the migration record, so the old files are not read again. It never touches projects, questionnaires, responses, backups, the researcher profile or AI keys.
- *Delete research data* is a separate, explained section: a reset never deletes data; a project is deleted on Home (first into *Recently deleted*); to remove everything, back up, close the program and delete the data folder (button: open it). Uninstalling keeps that folder.
- *Elsewhere, on purpose:* the update check's state (`updates/state.json`, read by the updater and its helper), the researcher profile (personal entries, own Delete button), AI provider keys (Windows credential store). The Settings hub shows all three.

**Window** (`window_state.py`, `app.py`). The launcher restores the saved size and position before the splash is painted, and saves them (debounced, 0.8 s after a move or resize ends; while maximized the normal bounds are kept and `maximized` is set). A position is restored only if at least half of the window, and its title bar, lie on a screen Windows reports now (`EnumDisplayMonitors` work areas); otherwise the saved size, shrunk to the screen, is centred. Elsewhere than on Windows only the size and the maximized state are restored. `research_app.main` no longer forces 1200 × 720.

**Last place.** The open project and its page (Project, Data, Analyze, Results, Reports, Questionnaires; Import and Chart Studio continue on the page they belong to) are saved as the researcher moves. The program still starts on Home and opens no project by itself (locks, journeys, no surprises); Home shows *Continue where you left off* with one button that opens the project on that page.

## 3. Start interface and parity with the classic interface

`research_app.start_interface()`: a caller's request (`research_app.main(page, interface=…)`, used by the classic-interface tests), else `SRA_UI=workspace|classic` (one run, nothing saved), else the setting; the workspace is the default for new and existing researchers (no earlier version stored a choice). With the workspace start the classic interface is still built (the workspace's bridge needs it) but never painted first. The classic Home's entry is now *Research workspace · Open the research workspace* (data key `open-workspace-preview` kept).

**Features that exist only in the classic interface** (from `workspace_routes.py`, the parity contract that `tests/test_workspace_foundations.py` checks against the live inventory):

| Classic item | Workspace route | Status | What stays classic |
|---|---|---|---|
| screen `preparation` | data#prepare | hosted | Classic non-destructive preparation tools inside Data |
| screen `survey` | questionnaires | partial | In the workspace: three-pane builder, templates, reusable scales, conditions, drag-and-drop, live preview, publish, collect, CSV + codebook, analyze, scientific import with scale review. Still classic: page titles and page-wise section reordering, DK/PNA missing options, free-form value-label editing, clone a published survey, multi-page respondent navigation, response table, matrix grid editor, region edits, 20-page OCR batch, binary-format bulk action |
| menu Data → Prepare data | data#prepare | hosted | Prepare data card |
| action `register_import_navigation` | home | retired | Workspace routing replaces the classic screen switcher |
| action `set_active_screen` | home | retired | Results log replaces the per-screen output cache |
| export Save prepared CSV + steps JSON | data#prepare | hosted | hosted classic preparation tools |

The hosted *Prepare data* panel (scale scoring, recoding, missing codes) is the classic component inside Data: it is still English only (its replacement is UX-3). The survey items marked *still classic* are reached through *Classic interface*. Nothing in the analysis engine is classic-only: every classic analysis screen has its workspace route with the same engine (`tests/test_analysis_runs.py`).

## 4. Language, typography, text size, density

- **Language.** `user_settings.LANGUAGES` = en, lv, ru; `QUICK_LANGUAGES` = en, lv (top bar, data key `context-language`, buttons named EN and LV). The globe (`context-language-menu`, named "Language: Русский. All languages") lists all three and *Language settings…* (Settings, scrolled to Language). The translations and Russian reports are untouched; `workspace_text` keeps (EN, LV, RU) tuples and `app_preferences.LANGUAGES` still includes `ru`.
- **Typeface** (`workspace_tokens.TYPEFACES`): `Segoe UI` with the fallbacks `Segoe UI Variable Text, Tahoma, Arial, Helvetica Neue, Noto Sans, DejaVu Sans, Liberation Sans, Roboto`; or `Segoe UI Variable Text` first. Set as the theme's `font_family` and, through the Material text theme, as `font_family_fallback` of every text role. A test checks with fontTools that DejaVu Sans (and on Windows `segoeui.ttf`) has every Latvian and Russian letter.
- **Text size.** `Ui.text_scale`; `Ui.size(px)` scales every type token in `wc.text` and the components (buttons, fields, dropdowns, checkboxes, segmented controls, chips, sidebar, status line) and the Material text theme (field labels, menus, tooltips). Text that is at least 12 px at 100 % never goes below 12 px (so 90 % keeps captions at 12 px). The chrome is rebuilt; the page and its state stay.
- **Density.** `workspace_tokens.apply_density`: comfortable is the design (`SPACE_3…8` = 12/16/24/32/40/48, controls 40 px, top bar 56 px); compact uses 8/12/16/24/32/40, 36-px controls, a 48-px top bar and Material's compact visual density. Buttons stay at least 32 px (the accessibility test).
- **Charts** (`chart_studio.DEFAULT_FONT`): Segoe UI where matplotlib finds it installed, else DejaVu Sans; DejaVu Sans remains the per-glyph fallback. Chart Studio's font list starts with Segoe UI. Report figures of the engine modules (`apa_figures`, `item_diagnostics`) keep DejaVu Sans: their output is compared byte-for-byte by the packaged analysis self-test.

## 5. The Settings hub and its registry (`workspace_settings.py`)

`SECTIONS` holds `SettingsSection(key, title, order, build, description=None, framed=True)`; the page draws them in `order` with an index of jump chips (`settings-jump-<key>`; each card is `settings-section-<key>`, also a scroll key for `navigate("settings", section=key)`). Built in: appearance 10, typography 20, language 30, start 40, projects 50, backups 60, updates 70, ai 80, profile 90, ocr 95, reset 100. **Export defaults** and **research-library privacy** plug in with one entry each, e.g. `register(SettingsSection("export", "settings.section.export", 65, build_export))` and `…("library", …, 85, …)`; `build(page)` returns the section's controls. A failing section shows its error and never hides the others. The update channel is shown, not offered: the updater supports one channel per build.

Data keys kept: `settings-language`, `settings-theme` (now light/dark/system), `settings-accent`, `settings-corners`, `settings-data` and its `-folder`, `-open`, `-find`, `settings-updates` and its `-automatic`, `-check`, `settings-version`, `settings-profile`, `settings-ai`, `settings-ocr`. New: `settings-text-size` (segments `90`, `100`, `110`, `125`), `settings-density`, `settings-typeface`, `settings-start-interface` (a dropdown, so that its entry "Classic interface" cannot be confused with the sidebar item of the same name), `settings-open-classic`, `settings-file`, `settings-recent-*`, `settings-backups-*`, `settings-backup-project`, `settings-restore-backup`, `settings-ai-privacy`, `settings-reset`, `settings-reset-confirm`, `settings-delete-data-*`, `home-continue`, `help-classic`, `help-settings`, `context-language-menu-*`.

## 6. Behaviour changes to know

1. The packaged program starts in the workspace; `tools/check_gui_startup.py` without options now expects the workspace (`interface_errors`), `--classic` starts and checks the classic interface, `--workspace` is kept.
2. `research_app.main(page, interface="classic")` builds the classic interface; `tools/ux_inventory.build_classic` and the classic screenshot scenarios use it.
3. `WorkspaceApp(language=…, corners=…)` apply only when the settings file holds none (a fresh installation); `settings=` passes a `UserSettings`. The profile's language no longer overrides the start language (it is migrated once and kept in sync, as before).
4. `app_preferences.load_preferences()`/`save_preferences()` without a path use the settings file; `update_preferences(**changes)` writes single keys. With a path, the old file format as before.
5. The e2e driver no longer sets `SRA_UI`: every journey starts as a researcher starts the program (`Gui.start_ui` forces one). For `--real-data` runs it sets language en, 100 % and the workspace start in the installed program's settings file (the old `preferences.json` is still deleted, as before).
6. Recent data files are shared by both interfaces through the settings file; the classic list is read fresh before a file is added.

## 7. Windows journeys and workflows

`tools/windows_gui_e2e.py`, appended after the 18 journeys (each restores English, 100 % and the workspace start, also after a failure):

- **startup-workspace** — a normal start (no `SRA_UI`) shows the workspace, not the classic Home; *Classic interface* in the sidebar, the classic Home's *Open the research workspace* back; Settings: *Interface at start* → Classic interface; restart: the classic Home; back to the workspace, workspace as the start again, restart. Checks the settings file after each choice.
- **settings-language** — the upgrade: `preferences.json` of an earlier version with `{"language": "ru"}`, no settings file. Starts in Russian; the old file is byte-identical; the top bar has EN and LV buttons and no RU; Settings show Русский; LV in the top bar; restart: Latvian; Settings: 125 % makes the page heading at least 15 % taller on screen (UI Automation rectangles); back to 100 % and EN.

`tests/test_stage37_shell_journeys.py` walks both flows through the real start (`research_app.main`, no `SRA_UI`) with the journeys' own texts and helpers.

Workflows: `windows-package.yml` — the normal start check now expects the workspace; the former workspace-preview step checks the classic interface (`--classic`). `windows-installer.yml` — the installed program's normal start (workspace) and a classic start. `release.yml` and `startup_ab.py` use the normal start (workspace) unchanged. The new modules are in the path filters of the package, GUI, installer and update workflows.

**Not run here:** no Windows runner was available to this branch. The journeys, the window placement on real monitors (DPI scale of `work_areas`), Segoe UI Variable rendering and the focus moves need the Windows workflows (`windows-gui-e2e`, `windows-installer`, `windows-package`) before merging.

## 8. Measured interaction cost (tools/ux_metrics.py)

Same command and synthetic fixtures as `docs/STAGE37_UX_METRICS.md` (window 1440 × 800). The tool now uses *Continue* on Home where it is offered for the task's project, and finds the text-size control in Settings.

| Task | Baseline (b83567c) | This branch |
|---|---|---|
| T1 first start to an open project with data | 3 inter., 3 pages | **2 inter., 2 pages** (no *Open the preview*) |
| T2–T6 | 4 · 51 · 10 · 5 · 2 | unchanged (UX-3 and other branches) |
| T7 reopen after a restart, review every result | 4 inter., 3 pages | **3 inter., 2 pages** (*Continue*) |
| T8 language and text size, next start | 5 inter. — text size **not available**; next start: *Open the preview*, LV again (D1), open project, back to Reports | 5 inter. **with the text size done** (LV 1; Settings, 125 %, back 3); next start: **1** (*Continue*: Latvian kept, project and Reports in one click) |
| novice / supervisor totals | 68 / 16 interactions | **67 / 15** |

At 1200 × 720: novice 67, supervisor 16 (T7 4: the results list is a dropdown there).

## 9. Tests

- `tests/test_stage37_settings.py` (40 tests): migration (copied once, old files byte-identical, language precedence, unknown and newer values never rewritten, damaged file kept aside, refused values, failed writes, reset keeps research data); `app_preferences` compatibility; D1, D2 (theme incl. system, sidebar, accent, text size, density, typeface, window placement and saving), the last place and *Continue*, U10, U11 (focus after create/open/dialogs); RU upgrade start, top bar EN/LV only, globe menu, unknown language; text size scales every token text and keeps 12 px; typeface fallbacks with Latvian/Cyrillic glyph coverage; chart default font; density tokens; the hub's sections, registry, reset dialog, start interface, recent files; start-interface resolution; the classic interface follows the workspace's language; Help/Settings offer the classic interface; D6; D11; `check_gui_startup` expectations; every new text in three languages and listed below.
- `tests/test_stage37_shell_journeys.py` (6 tests): the two journeys, `restore_settings`, the journey order, no `SRA_UI` by default, segmented buttons found with or without their tooltip in the UI Automation name.
- Updated: `test_app_startup.py` (the normal start is the workspace; classic by setting or `SRA_UI`; a temporary data folder), `test_workspace_shell.py` (RU through the globe menu; no preview labels), `test_stage368_review_journeys.py` (journeys appended after the 18).

## 10. New texts: LV and RU drafts for native review

`workspace_text.DRAFT_KEYS` lists these keys; the classic interface's three new strings (`localization.py`: "Research workspace", its description, "Open the research workspace") are drafts too. None has been reviewed by a native speaker.

| Key | English | Latviešu (draft) | Русский (draft) |
|---|---|---|---|
| `context.language_menu` | Language: {name}. All languages | Valoda: {name}. Visas valodas | Язык: {name}. Все языки |
| `context.language_settings` | Language settings… | Valodas iestatījumi… | Настройки языка… |
| `help.interfaces` | Research workspace and classic interface | Pētījumu darba vide un klasiskā saskarne | Исследовательская среда и классический интерфейс |
| `help.interfaces.body` | The research workspace is the normal start of the program. The classic interface, with the same engine and the same data, stays available: “Classic interface” in the sidebar or the button below. Settings choose which of the two opens at start. | Pētījumu darba vide ir programmas parastais sākums. Klasiskā saskarne ar to pašu dzinēju un tiem pašiem datiem paliek pieejama: “Klasiskā saskarne” sānjoslā vai poga zemāk. Iestatījumos var izvēlēties, kura no tām atveras startā. | Исследовательская среда — обычный запуск программы. Классический интерфейс с тем же движком и теми же данными остаётся доступным: «Классический интерфейс» на боковой панели или кнопка ниже. В настройках можно выбрать, какой из них открывается при запуске. |
| `help.settings_open` | Open Settings | Atvērt iestatījumus | Открыть настройки |
| `home.continue_body` | Your last session ended in the project “{title}”, on {page}. The project opens only when you choose it. | Jūsu pēdējā sesija beidzās projektā “{title}”, lapā “{page}”. Projekts tiek atvērts tikai tad, kad to izvēlaties. | Последний сеанс закончился в проекте «{title}», на странице «{page}». Проект открывается, только когда вы его выберете. |
| `home.continue_button` | Continue: {page} | Turpināt: {page} | Продолжить: {page} |
| `home.continue_title` | Continue where you left off | Turpiniet, kur pārtraucāt | Продолжить с того места, где вы остановились |
| `reports.section_names` | Section titles are shown in the language of the report ({name}). | Sadaļu nosaukumi ir parādīti atskaites valodā ({name}). | Названия разделов показаны на языке отчёта ({name}). |
| `settings.ai_body` | The AI assistant stays off until you connect a provider with your own key, which is kept in the Windows credential store. What it may see is chosen per project, every source off by default, and nothing is sent before you have seen the exact text. | MI asistents paliek izslēgts, kamēr nepievienojat pakalpojumu sniedzēju ar savu atslēgu, kas tiek glabāta Windows akreditācijas datu krātuvē. Ko tas drīkst redzēt, izvēlas katram projektam, visi avoti pēc noklusējuma izslēgti, un nekas netiek nosūtīts, pirms neesat redzējis precīzu tekstu. | ИИ-помощник выключен, пока вы не подключите провайдера со своим ключом, который хранится в диспетчере учётных данных Windows. Что ему можно видеть, выбирается для каждого проекта, все источники по умолчанию выключены, и ничего не отправляется, пока вы не увидели точный текст. |
| `settings.backup_open_project` | Back up “{title}”… | Rezerves kopija: “{title}”… | Резервная копия «{title}»… |
| `settings.backups_body` | Before the program updates itself or opens a project saved in an older format, it copies the projects into the folder below. A portable backup of one project (.sra) is made with “Back up” on Home or on the project's page; it can be restored on any computer. | Pirms programma atjaunina sevi vai atver projektu, kas saglabāts vecākā formātā, tā nokopē projektus zemāk norādītajā mapē. Pārnēsājamu viena projekta rezerves kopiju (.sra) izveido ar pogu “Rezerves kopija” sākumlapā vai projekta lapā; to var atjaunot jebkurā datorā. | Перед самообновлением или открытием проекта, сохранённого в старом формате, программа копирует проекты в папку ниже. Переносимая резервная копия проекта (.sra) создаётся кнопкой «Резервная копия» на главной или на странице проекта; её можно восстановить на любом компьютере. |
| `settings.backups_open` | Open the backup folder | Atvērt rezerves kopiju mapi | Открыть папку резервных копий |
| `settings.backups_privacy` | Backups are not encrypted and contain the participants' answers: keep them where only you can read them. | Rezerves kopijas nav šifrētas un satur dalībnieku atbildes: glabājiet tās tur, kur tās varat lasīt tikai jūs. | Резервные копии не зашифрованы и содержат ответы участников: храните их там, где их можете прочитать только вы. |
| `settings.delete_data` | Delete research data | Dzēst pētījuma datus | Удалить данные исследования |
| `settings.delete_data_body` | Resetting settings never deletes research data. A project is deleted with Delete on Home and is kept in “Recently deleted” first. To remove all research data, make a backup if you need one, close the program and delete the data folder shown under “Projects and data folder”. Uninstalling the program keeps that folder. | Iestatījumu atiestatīšana nekad nedzēš pētījuma datus. Projektu dzēš ar pogu “Dzēst” sākumlapā, un vispirms tas tiek saglabāts sadaļā “Nesen dzēstie”. Lai noņemtu visus pētījuma datus, vajadzības gadījumā izveidojiet rezerves kopiju, aizveriet programmu un izdzēsiet datu mapi, kas norādīta sadaļā “Projekti un datu mape”. Atinstalējot programmu, šī mape tiek saglabāta. | Сброс настроек никогда не удаляет данные исследования. Проект удаляется кнопкой «Удалить» на главной и сначала сохраняется в «Недавно удалённых». Чтобы удалить все данные исследования, при необходимости сделайте резервную копию, закройте программу и удалите папку данных, указанную в разделе «Проекты и папка данных». При удалении программы эта папка сохраняется. |
| `settings.delete_data_projects` | Projects on Home | Projekti sākumlapā | Проекты на главной |
| `settings.density` | Density | Blīvums | Плотность |
| `settings.density.comfortable` | Comfortable | Ērts | Свободная |
| `settings.density.compact` | Compact | Kompakts | Компактная |
| `settings.language_note` | English and Latviešu are also in the top bar. Every language, Русский included, is in the globe menu beside them. Your choice is kept for the next start. | English un Latviešu ir arī augšējā joslā. Visas valodas, arī Русский, ir globusa izvēlnē blakus tām. Jūsu izvēle tiek saglabāta nākamajai palaišanai. | English и Latviešu есть также на верхней панели. Все языки, включая русский, есть в меню с глобусом рядом с ними. Ваш выбор сохраняется для следующего запуска. |
| `settings.not_saved` | The setting applies now but could not be kept for the next start: {error} | Iestatījums darbojas tagad, bet to nevarēja saglabāt nākamajai palaišanai: {error} | Настройка действует сейчас, но её не удалось сохранить для следующего запуска: {error} |
| `settings.recent_clear` | Clear the list of recent data files | Notīrīt neseno datu failu sarakstu | Очистить список недавних файлов данных |
| `settings.recent_cleared` | The list of recent data files is empty. The files themselves are unchanged. | Neseno datu failu saraksts ir tukšs. Paši faili nav mainīti. | Список недавних файлов данных пуст. Сами файлы не изменены. |
| `settings.recent_files` | Recent data files | Nesenie datu faili | Недавние файлы данных |
| `settings.recent_none` | Nothing yet. | Vēl nekā nav. | Пока ничего. |
| `settings.recent_projects` | Recent projects | Nesenie projekti | Недавние проекты |
| `settings.reset` | Reset settings | Atiestatīt iestatījumus | Сбросить настройки |
| `settings.reset_body` | Language, appearance, text size, density, the interface at start, the window, the sidebar and the list of recent data files go back to their defaults. Projects, questionnaires, responses, backups, your researcher profile and AI keys are not changed. | Valoda, izskats, teksta lielums, blīvums, saskarne palaišanas brīdī, logs, sānjosla un neseno datu failu saraksts atgriežas pie noklusējuma. Projekti, anketas, atbildes, rezerves kopijas, jūsu pētnieka profils un MI atslēgas netiek mainīti. | Язык, внешний вид, размер текста, плотность, интерфейс при запуске, окно, боковая панель и список недавних файлов данных возвращаются к значениям по умолчанию. Проекты, анкеты, ответы, резервные копии, профиль исследователя и ключи ИИ не меняются. |
| `settings.reset_confirm` | Reset settings | Atiestatīt iestatījumus | Сбросить настройки |
| `settings.reset_done` | Settings were reset to their defaults. No research data was changed. | Iestatījumi ir atiestatīti uz noklusējuma vērtībām. Pētījuma dati netika mainīti. | Настройки сброшены к значениям по умолчанию. Данные исследования не изменены. |
| `settings.reset_title` | Reset all settings? | Atiestatīt visus iestatījumus? | Сбросить все настройки? |
| `settings.section.ai` | AI privacy | MI un privātums | ИИ и конфиденциальность |
| `settings.section.appearance` | Appearance | Izskats | Внешний вид |
| `settings.section.backups` | Backups | Rezerves kopijas | Резервные копии |
| `settings.section.language` | Language | Valoda | Язык |
| `settings.section.projects` | Projects and data folder | Projekti un datu mape | Проекты и папка данных |
| `settings.section.reset` | Reset settings or delete data | Atiestatīt iestatījumus vai dzēst datus | Сброс настроек или удаление данных |
| `settings.section.start` | Start | Palaišana | Запуск |
| `settings.section.typography` | Text and density | Teksts un blīvums | Текст и плотность |
| `settings.section.typography_body` | The interface uses the Windows fonts Segoe UI or Segoe UI Variable. Text size and density apply to every page. | Saskarne izmanto Windows fontus Segoe UI vai Segoe UI Variable. Teksta lielums un blīvums attiecas uz visām lapām. | Интерфейс использует шрифты Windows Segoe UI или Segoe UI Variable. Размер текста и плотность применяются ко всем страницам. |
| `settings.section.updates` | Updates | Atjauninājumi | Обновления |
| `settings.sections` | On this page | Šajā lapā | На этой странице |
| `settings.settings_file` | Settings file: {path} | Iestatījumu fails: {path} | Файл настроек: {path} |
| `settings.start.classic` | Classic interface | Klasiskā saskarne | Классический интерфейс |
| `settings.start.workspace` | Research workspace | Pētījumu darba vide | Исследовательская среда |
| `settings.start_interface` | Interface at start | Saskarne palaišanas brīdī | Интерфейс при запуске |
| `settings.start_note` | The research workspace is the normal start. The classic interface stays one click away: “Classic interface” in the sidebar, in Help and here. | Pētījumu darba vide ir parastais sākums. Klasiskā saskarne ir viena klikšķa attālumā: “Klasiskā saskarne” sānjoslā, palīdzībā un šeit. | Исследовательская среда — обычный запуск. Классический интерфейс доступен в один щелчок: «Классический интерфейс» на боковой панели, в справке и здесь. |
| `settings.subtitle` | Everything you choose here is kept on this computer for the next start and applies at once. | Viss, ko šeit izvēlaties, tiek saglabāts šajā datorā nākamajai palaišanai un darbojas uzreiz. | Всё, что вы выбираете здесь, сохраняется на этом компьютере для следующего запуска и действует сразу. |
| `settings.text_size` | Text size | Teksta lielums | Размер текста |
| `settings.text_size_note` | Applies to every page at once. Small helper text never becomes smaller than 12 px. | Attiecas uz visām lapām uzreiz. Mazais palīgteksts nekad nekļūst mazāks par 12 px. | Применяется сразу ко всем страницам. Мелкий вспомогательный текст никогда не становится меньше 12 px. |
| `settings.theme.system` | System | Kā sistēmā | Как в системе |
| `settings.theme_note` | System follows the app mode chosen in Windows (light or dark). | “Kā sistēmā” seko Windows izvēlētajam lietotņu režīmam (gaišs vai tumšs). | «Как в системе» следует режиму приложений, выбранному в Windows (светлый или тёмный). |
| `settings.typeface` | Typeface | Burtveidols | Шрифт |
| `settings.typeface.segoe` | Segoe UI · Windows | Segoe UI · Windows | Segoe UI · Windows |
| `settings.typeface.segoe_variable` | Segoe UI Variable · Windows 11 | Segoe UI Variable · Windows 11 | Segoe UI Variable · Windows 11 |
| `settings.typeface_note` | Fonts come from Windows; the program installs none. Where a font is missing, the next one with Latvian and Cyrillic letters is used. | Fonti tiek ņemti no Windows; programma neinstalē nevienu. Ja fonta nav, tiek izmantots nākamais, kurā ir latviešu un kirilicas burti. | Шрифты берутся из Windows; программа не устанавливает ни одного. Если шрифта нет, используется следующий, в котором есть латышские и кириллические буквы. |
| `settings.updates_channel` | The release channel comes with the installed program; switching channels is not offered. | Laidienu kanāls ir noteikts instalētajā programmā; kanāla maiņa netiek piedāvāta. | Канал выпусков задан установленной программой; смена канала не предусмотрена. |
| plural `parts` (`count_text`) | part / parts | daļa / daļas / daļu | часть / части / частей |
