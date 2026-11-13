# Stage 36.8: Latvian and Russian text review (issue #62)

> **No native-speaker review has taken place yet.** This document is the
> input for one. It was prepared from an automated audit
> (`tools/locale_audit.py`), runs of the workspace in Russian on synthetic
> data and a reading of the LV/RU texts by an author who is not a native
> speaker of either language. Nothing in it is approved. Every correction
> marked *proposed, needs native review* is a suggestion only and has **not**
> been applied; the texts changed in this stage are listed in §3.

Branch `claude/stage368-locale`, based on `dff65c8` (the head of the
release-candidate branch `claude/stage368-rc`).

## 1. How to use this list

* Work through §4 screen by screen, in the priority order of the issue:
  import wizard, groups, Chart Studio, reports, AI assistant, then the rest.
  Each row gives the text key (search for it in `workspace_text.py`, or in
  the table named in the key), the three texts and the reason for review.
* Reasons are one or more of: **terminology** (a statistical or interface term
  used differently elsewhere), **agreement** (gender, case or number
  agreement; in LV/RU the noun after a number changes with the number),
  **too literal**, **length** (layout risk), **unclear**, **new** (written in
  this stage, never reviewed).
* §5 is the terminology glossary: decide each term once, then the rows of §4
  that only repeat a glossary decision can be fixed in one pass.
* §6 lists English text that the analysis engine and the report builder
  produce. It is not in any text table, so translators cannot fix it there;
  it needs code changes in modules other work is changing now.
* Rerun the checker after each batch of corrections:

  ```
  python tools/locale_audit.py --markdown locale-audit.md
  python -m unittest discover -s tests -p "test_locale_audit.py"
  ```

  The command never fails on findings; `--strict missing,placeholder` makes
  it exit 1 for those categories (the unit tests keep both at zero).

## 2. Checker results before and after this stage

`tools/locale_audit.py` reads 20 text tables (2 034 texts after this stage)
and the source of the workspace screens (`workspace_*.py`). Both columns were
produced by the same final version of the checker: "before" on an unchanged
export of `dff65c8`, "after" on this branch.

| Category | What it reports | Before (`dff65c8`) | After |
|---|---|---:|---:|
| `missing` | LV/RU text absent or empty; an English source text (scale-group message, method profile, method option label or choice) without a translation entry; a key the workspace asks `ui.t` for that is not defined | 11 | **0** |
| `identical` | LV/RU text equal to English although words remain after removing allowed names, abbreviations and symbols | 0 | 0 |
| `placeholder` | `{name}` fields of LV/RU differ from English, or malformed braces | 0 | **0** |
| `style` | doubled spaces; Latin words in Russian text; mixed-script words; Cyrillic in Latvian; Latvian without diacritics; edge whitespace differing from English; a key written twice | 10 | 10 |
| `length` | button or step label more than 1.6 × the English length (and at least 12 characters): layout risk only | 17 | 17 |
| `hardcoded` | English string literal passed to a visible-text parameter (`wc.text`, `wc.button`, `wc.caption`, `ft.Text`, the other `wc` helpers, dropdown choices, `(value, label)` choice lists) in `workspace_*.py` | 49 | **2** |
| Texts audited | | 1 972 | 2 034 |

* The 11 `missing` findings before were the method choices of the guided
  analysis (e.g. "Mann–Whitney U", "Welch’s independent t", "One-way
  ANOVA"): the dropdown translates them through `workspace_text.LABELS`, which
  had no entry, so LV/RU users saw English.
* The 49 `hardcoded` findings before were the import options (19, the
  review's U11 item), the sample-dataset labels (11), the questionnaire
  builder's templates, condition operator and operators, and scale-library
  labels (12), the reverse-items field of the import wizard (1), the table
  number "Table N" and the "Enlarge" fallback (2), the page-failure title and
  the path field (2) — and the two that remain, both in
  `workspace_analyze.py`, which this stage must not change: "{title}:
  verified estimates" (`ResultsPage._detail`) and "Figure number"
  (`ResultsPage._exports`).
* `style` and `length` are review input (§4), not errors. The 10 style
  findings are all in the classic interface's table (`localization.TEXT`).
* The checker cannot see English that the engine builds at run time; §6
  lists what a run of the Russian workspace showed.

Not counted by the checker but fixed in this stage: the "N unique" summary of
the data dictionary (`workspace_state.value_summary` ignored its `language`)
and the assumption list of the Word report (translations existed in
`interpretation_i18n.ASSUMPTION_TEXT` but `research_report.plan_report` wrote
the English).

## 3. Texts changed in this stage

All new LV/RU texts below are **new** and unreviewed. Where the classic
interface already translated the same English text, its wording was reused,
so that both interfaces say the same thing.

| Where | Change |
|---|---|
| `workspace_shell.py` `DataPage._import_options` | Import options: labels and choices moved to `data.opt.*` keys (EN unchanged). |
| `workspace_shell.py` `SAMPLES`, `_sample_picker` | Sample-dataset labels moved to `sample.*` keys. The ANCOVA sample's English label changed from "ANCOVA" to "ANCOVA with a covariate": a bare acronym fails the all-caps rule of `test_workspace_foundations`, and the new label pairs with "ANCOVA with interaction". No GUI journey uses it. |
| `workspace_shell.py` `WorkspaceApp.render`, `_path_fallback`, dictionary row | `page.failed`, `data.path_field`; `value_summary(name, ui.language)`. |
| `workspace_state.py` `value_summary` | "{count} unique" through `data.values_unique`. |
| `workspace_components.py` `apa_table`, `figure` | "Table {number}" through `results.table_number`; the fallbacks of `figure` through existing keys: the screen-reader name "Figure" (`results.figure`) and the enlarge button (`results.enlarge`, "Enlarge figure", which the only caller passes anyway). |
| `workspace_questionnaires.py` | Templates (`q.template.*`), condition operator and operators (`q.condition_operator`, `q.operator.*`), scale-library labels (`q.scale.*`), reverse-items field of the import scale step (`imp.reverse_items`). |
| `workspace_text.py` `LABELS` | 11 method choices (see §4.6, "Method names"). |
| `research_report.py` `plan_report` | Assumption checks are written in the report language (`interpretation_i18n.translate_assumption`); reviews are still recorded against the English text. |

New `workspace_text.T` entries (all *new*):

| Key | English | Latvian | Russian |
|---|---|---|---|
| `data.opt.sheet` | Excel worksheet | Excel lapa | Лист Excel |
| `data.opt.header_row` | Header row (1-based) | Galvenes rindas numurs (no 1) | Строка заголовков (с 1) |
| `data.opt.data_start` | Data begins at row (optional) | Datu sākuma rinda (neobligāti) | Первая строка данных (необязательно) |
| `data.opt.separator` | CSV separator | CSV atdalītājs | Разделитель CSV |
| `data.opt.separator.auto` | Auto detect | Noteikt automātiski | Определить автоматически |
| `data.opt.separator.comma` | Comma , | Komats , | Запятая , |
| `data.opt.separator.semicolon` | Semicolon ; | Semikols ; | Точка с запятой ; |
| `data.opt.separator.tab` | Tab | Tabulācija | Табуляция |
| `data.opt.separator.pipe` | Pipe \| | Vertikāla svītra \| | Вертикальная черта \| |
| `data.opt.decimal` | Decimal notation | Decimālo skaitļu formāts | Десятичный формат |
| `data.opt.decimal.auto` | Auto (conservative) | Automātiski (piesardzīgi) | Автоматически (осторожно) |
| `data.opt.decimal.dot` | Dot decimal / 1,234.5 | Decimālpunkts / 1,234.5 | Десятичная точка / 1,234.5 |
| `data.opt.decimal.comma` | Comma decimal / 1.234,5 | Decimālkomats / 1.234,5 | Десятичная запятая / 1.234,5 |
| `data.opt.encoding` | Text encoding | Teksta kodējums | Кодировка текста |
| `data.opt.encoding.auto` | Auto detect / UTF-8 | Noteikt automātiski / UTF-8 | Определить автоматически / UTF-8 |
| `data.opt.encoding.cp1257` | Windows Baltic (CP1257) | Windows baltiešu (CP1257) | Windows, балтийская (CP1257) |
| `data.opt.encoding.cp1251` | Windows Cyrillic (CP1251) | Windows kirilica (CP1251) | Windows, кириллица (CP1251) |
| `data.opt.encoding.cp1252` | Windows Western (CP1252) | Windows Rietumeiropas (CP1252) | Windows, западноевропейская (CP1252) |
| `data.opt.missing` | Missing text markers (semicolon-separated) | Trūkstošu vērtību marķieri (ar ;) | Обозначения пропусков (через ;) |
| `data.path_field` | Full local file path | Pilns faila ceļš šajā datorā | Полный путь к файлу на этом компьютере |
| `data.values_unique` | {count} unique | unikālu vērtību: {count} | уникальных значений: {count} |
| `sample.scale` | Questionnaire scale · two groups | Anketas skala · divas grupas | Шкала анкеты · две группы |
| `sample.survey` | Small survey | Neliela aptauja | Небольшой опрос |
| `sample.three_groups` | Three groups | Trīs grupas | Три группы |
| `sample.paired` | Before / after | Pirms / pēc | До / после |
| `sample.repeated` | Three occasions | Trīs mērījumu reizes | Три измерения |
| `sample.categorical` | Two categorical variables | Divi kategoriāli mainīgie | Две категориальные переменные |
| `sample.regression` | Regression | Regresija | Регрессия |
| `sample.logistic` | Binary outcome | Binārs iznākums | Бинарный исход |
| `sample.ancova` | ANCOVA with a covariate | ANCOVA ar kovariātu | ANCOVA с ковариатой |
| `sample.ancova_interaction` | ANCOVA with interaction | ANCOVA ar mijiedarbību | ANCOVA с взаимодействием |
| `sample.omega_bootstrap` | Reliability with bootstrap CI | Ticamība ar bootstrap TI | Надёжность с бутстреп-ДИ |
| `sample.factor` | Factor analysis | Faktoru analīze | Факторный анализ |
| `page.failed` | This page could not be shown | Šo lapu neizdevās parādīt | Не удалось показать эту страницу |
| `results.table_number` | Table {number} | Tabula {number} | Таблица {number} |
| `q.template.psychology` | Psychology / Likert | Psiholoģija / Likerta skala | Психология / шкала Лайкерта |
| `q.template.demographics` | Demographics | Demogrāfija | Демография |
| `q.template.hr` | HR / Workplace | Personāls / darbavieta | HR / рабочая среда |
| `q.template.marketing` | Marketing / Feedback | Mārketings / atsauksmes | Маркетинг / отзывы |
| `q.condition_operator` | Condition operator | Nosacījuma operators | Оператор условия |
| `q.operator.equals` | Equals | Vienāds ar | Равно |
| `q.operator.not_equals` | Not equal | Nav vienāds ar | Не равно |
| `q.operator.greater` | Greater than | Lielāks par | Больше |
| `q.operator.less` | Less than | Mazāks par | Меньше |
| `q.scale.agreement` | Agreement | Piekrišana | Согласие |
| `q.scale.frequency` | Frequency | Biežums | Частота |
| `q.scale.quality` | Quality: poor → good | Kvalitāte: slikti → labi | Качество: плохо → хорошо |
| `q.scale.points` | {scale} · {count} points | {scale} · {count} punkti | {scale} · {count} баллов |
| `q.scale.semantic` | Semantic differential −3…3 | Semantiskais diferenciālis −3…3 | Семантический дифференциал −3…3 |
| `q.scale.from_draft` | From this draft: {labels} | No šī melnraksta: {labels} | Из этого черновика: {labels} |
| `imp.reverse_items` | Reverse-keyed items (as documented) | Apgriezti vērtējamie jautājumi (kā dokumentēts) | Обратные пункты (как в методике) |

Points for the reviewer in the new texts: `q.scale.points` ("5 points" of a
rating scale; RU «5 баллов» or «5-балльная»?), `data.opt.decimal.auto`
(«piesardzīgi»/«осторожно» for "conservative" detection), the RU comma style
of `data.opt.encoding.*`, and `sample.omega_bootstrap` (LV keeps the English
word "bootstrap", as `LABELS["Omega 95% bootstrap CI"]` already does).

## 4. Review list by screen

### 4.1 Import wizard (`imp.*`, `impnote.*`, `impblock.*`)

| Key | English | Latvian | Russian | Reason | Proposal |
|---|---|---|---|---|---|
| `imp.items` | Extracted items | Atpazītie jautājumi | Распознанные вопросы | terminology: RU calls an item «пункт» in the same wizard (`imp.step.items` «Пункты», `impblock.items`, `imp.counts`) but «вопрос» here | RU «Распознанные пункты» — proposed, needs native review |
| `imp.check_items` | Item count and order match the source | Jautājumu skaits un secība atbilst avotam | Число и порядок вопросов совпадают с источником | terminology (as above); `impblock.items` says «число и порядок пунктов» | RU «Число и порядок пунктов совпадают с источником» — proposed, needs native review |
| `imp.scale_items` | {count} linked items | Saistītie jautājumi: {count} | Связанных вопросов: {count} | terminology (as above) | RU «Связанных пунктов: {count}» — proposed, needs native review |
| `imp.item_reviewed` | I compared this item with the source page | Es salīdzināju šo jautājumu ar avota lapu | Я сверил(а) этот вопрос со страницей источника | terminology: RU «вопрос»/«пункт»; LV «lapa» here, «lappuse» in `impnote.ocr_read` | RU «этот пункт»; LV «ar avota lappusi» — proposed, needs native review |
| `imp.page`, `imp.prev_page`, `imp.next_page`, `imp.ocr_page` | Page {page} of {count} / Previous page / Next page / Run offline OCR on this page | Lapa … / Iepriekšējā lapa / Nākamā lapa / … šai lapai | Страница … | terminology: LV uses «lapa» and «lappuse» for a document page within one screen (`imp.ocr_progress`, `imp.scan_status`, `imp.form.evidence` say «lappuse»); the Word report footer says «Lappuse» | one LV word for a document page (§5) |
| `imp.excluded` | Lines kept out as references ({count}) | Rindas, kas izslēgtas kā atsauces ({count}) | Строки, исключённые как источники ({count}) | unclear: «источник» is this wizard's word for the questionnaire's Source; `impnote.references` says «список литературы» | RU «Строки, исключённые как список литературы ({count})» — proposed, needs native review |
| `imp.text_layer` | PDF text layer — OCR confidence does not apply | PDF teksta slānis — OCR ticamība nav attiecināma | Текстовый слой PDF — уверенность OCR не применяется | terminology: LV «ticamība» is also the app's word for reliability and part of «ticamības intervāls» (confidence interval) | a different LV word for OCR confidence (e.g. «pārliecība»?) — needs native review |
| `imp.scale_labels`, `imp.confirm_structure`, `imp.evidence.row` | Labels as printed / Confirm structure and labels / labels printed in every row | Iespiestās etiķetes / … etiķetes / katrā rindā drukātās etiķetes | Подписи как в источнике / … подписи / подписи в каждой строке | terminology: LV «etiķete» (a tag or sticker) for answer labels; "printed" is «iespiests» in two keys and «drukāts» in others (`imp.form.no_options`, `imp.scan.detail`) | needs native review |
| `imp.evidence.codebook` | codebook | kodu grāmata | кодовая книга | too literal? | needs native review |
| `imp.apply_scale` | Apply scale review | Lietot skalas pārskatu | Применить проверку шкалы | too literal: what is applied is the reviewed scale, not the review | LV «Lietot pārbaudīto skalu», RU «Применить проверенную шкалу» — proposed, needs native review |
| `imp.cancelling` | Stopping OCR; the text already read is kept… | OCR tiek apturēta; … | OCR останавливается; … | agreement: LV treats OCR as feminine throughout; RU uses «локальный OCR» (m.) in `imp.ocr_progress`, `imp.scan.*` and «распознавание» (n.) in `imp.ocr_done`, `impnote.ocr_cancelled` | one RU form for the engine and one for the process — needs native review |
| `imp.discard`, `imp.discard_confirm`, `imp.resume_discard` | Discard this review / Discard review / Discard | Atmest … | Удалить эту проверку / Удалить проверку / Удалить | terminology: the assistant's "Discard" is «Отбросить» (`assistant.discard`) | needs native review (the body text says the review is deleted, so «Удалить» may be right) |
| `imp.counts` | {total} items · {attention} need attention · {checked} compared with the source | {total} jautājumi · jāpārbauda: {attention} · salīdzināti ar avotu: {checked} | пунктов: {total} · … | agreement: LV «1 jautājumi», «21 jautājumi» (singular after 1 and 21) | LV «jautājumi: {total} · …», like the rest of the line — proposed, needs native review |
| `impnote.count_mismatch` | Found {found} items, but the document says {expected}. … | Atrasti {found} jautājumi, bet dokumentā norādīti {expected}. … | Найдено пунктов: {found}, а в документе указано {expected}. … | agreement (LV, as above) | LV «Atrasto jautājumu skaits: {found}, dokumentā norādīts: {expected}. …» — proposed, needs native review |
| `impnote.count_match`, `imp.state.restored` | Found {found} of {expected} expected items. / … {checked} of {total} items checked … | Atrasti {found} no {expected} gaidītajiem jautājumiem. / … no {total} jautājumiem … | Найдено {found} из {expected} ожидаемых пунктов. / … из {total} пунктов … | agreement: the noun after "of {n}" changes with the number in both languages («из 1 пункта», «no 1 jautājuma») | needs native review |
| `impblock.unreviewed` | {count} item(s) still need comparing with the source (items {items}; step 3). | {count} jautājums(-i) vēl jāsalīdzina … | Ещё нужно сверить с источником пунктов: {count} … | agreement: LV «jautājums(-i)» | LV «Ar avotu vēl jāsalīdzina jautājumi: {count} …» — proposed, needs native review |
| `imp.reverse_items` | Reverse-keyed items (as documented) | Apgriezti vērtējamie jautājumi (kā dokumentēts) | Обратные пункты (как в методике) | new; terminology "reverse-keyed" (§5) | — |

The wizard also shows engine text in English: two warnings of the
scientific importer and the scale step's issue list (§6).

### 4.2 Groups (`groups.*`, Data → Create groups from a scale)

| Key | English | Latvian | Russian | Reason | Proposal |
|---|---|---|---|---|---|
| `groups.cuts` | Cut points (comma-separated) | Sliekšņi (atdalīti ar komatu) | Пороги (через точку с запятой или запятую) | unclear: the example (`groups.cuts_hint`, `groups.need_cuts`: "39; 59") and the parser (`workspace_groups`: semicolons, commas only when there is no semicolon) use semicolons; EN and LV say comma; RU differs from EN | the English needs a decision first (e.g. "Cut points (separated by ;)"); no GUI journey waits for this key |
| `groups.method` | Rule | Likums | Правило | terminology: LV «likums» is "law" | LV «Noteikums»/«Kārtula»? — needs native review |
| `groups.source` | Scale | Skala | Шкала | unclear: the field asks for a score (`groups.choose_source`: «rādītāju», «показатель») | needs native review (the English is used by a GUI journey; change it only together with `tools/windows_gui_e2e.py`) |
| `groups.counts` | {valid} values grouped · {missing} missing · {outside} outside every group | {valid} vērtības grupētas · {missing} trūkst · {outside} ārpus grupām | сгруппировано значений: {valid} · пропусков: {missing} · вне групп: {outside} | agreement (LV «1 vērtības grupētas») | LV «grupētas vērtības: {valid} · trūkst: {missing} · ārpus grupām: {outside}» — proposed, needs native review |
| `groups.statement.equal_width` | Data-derived groups: {k} intervals of equal width from {low} to {high} ({span}). … | … {k} vienāda platuma intervāli … | … {k} интервала(ов) равной ширины … | agreement: RU «интервала(ов)»; LV plural after {k} | RU «Группы по данным: интервалы равной ширины ({k}) от {low} до {high} ({span}).» — proposed, needs native review |
| `groups.small`, `groups.out_of_range`, `groups.missing`, `groups.non_numeric`, `groups.overlap_values` | {n} value(s) … | {n} … vērtība(s) … | {n} знач. … | agreement/style: RU abbreviates «знач.» in running text to avoid the plural; LV «vērtība(s)» | needs native review; the code could use the plural helper `workspace_text.count_text` |
| `groups.created` | {target} was created from {source}: {groups}. {source} itself is unchanged; … | {target} izveidots no {source}: … Pats {source} nav mainīts … | Переменная {target} создана по {source}: … Сама {source} не изменена … | agreement: «Сама {source}» before a variable name reads oddly | RU «Исходная переменная {source} не изменена» — proposed, needs native review |

Engine and scale-group messages (`scale_groups.TEXT`) are translated through
the same `groups.*` keys; the audit checks that every message has a key with
the same placeholders.

### 4.3 Chart Studio (`chart.*`)

| Key | English | Latvian | Russian | Reason | Proposal |
|---|---|---|---|---|---|
| `chart.title`, `nav.charts` | Chart Studio | Diagrammu studija | Редактор графиков | terminology: LV keeps "studio", RU says "editor" | decide whether the area has a product-like name — needs native review |
| `chart.kind.boxplot`, `chart.kind.multi_boxplot`, `chart.facet.boxplot` | Boxplot / Multi-boxplot / Boxplots | Kastes diagramma / Vairākas kastes diagrammas / … | Ящичковая диаграмма / … | terminology: LV says «kastes grafiks» in the analysis texts (`why.explore`, `alt.explore`); established terms may differ («диаграмма размаха», «ящик с усами») | needs native review |
| `chart.kind.violin` | Violin plot | Vijoles diagramma | Скрипичная диаграмма | terminology | needs native review |
| `chart.kind.faceted` | Small multiples | Mazo paneļu sērija | Серия малых панелей | too literal (a term of Tufte's) | needs native review |
| `chart.kind.qq` | Normal Q–Q plot | Normālā Q–Q diagramma | Нормальный Q–Q график | terminology: the analysis texts (`why.explore`, `alt.explore`) say «Q–Q grafiks», «Q–Q-график» | needs native review |
| `chart.palette.okabe_ito` | Okabe–Ito (colour-blind safe) | Okabe–Ito (droša daltoniķiem) | Окабе–Ито (для цветовой слепоты) | unclear: RU reads "for colour blindness" | RU «Окабе–Ито (различима при дальтонизме)» — proposed, needs native review |
| `chart.palette` with `chart.palette.*` | Colours / Scientific blue / Muted (Tol) / Grayscale for print | Krāsas / Zinātniskā zilā / Klusinātā (Tol) / Pelēktoņi drukai | Цвета / Научная синяя / Приглушённая (Tol) / Оттенки серого для печати | agreement: the options are feminine singular (a palette) under a plural label | label «Palete»/«Палитра», or plural options — proposed, needs native review |
| `chart.open`, `chart.copy`, `chart.add_view` | Edit chart / Copy image / New view | Rediģēt diagrammu / … | Редактировать график / Копировать изображение / Новый вариант | length (§4.6) | — |

The chart content itself (default titles, axis labels, the text alternative
read by screen readers, "Note.") is English in every language (§6,
`chart_studio.py`).

### 4.4 Reports (`reports.*`, `research_report.TEXT`, `report_docx.LABELS`)

| Key | English | Latvian | Russian | Reason | Proposal |
|---|---|---|---|---|---|
| `research_report.TEXT` `descriptives` | Descriptive statistics | Aprakstošā statistika | Описательные статистики | terminology: everywhere else «Описательная статистика» | RU «Описательная статистика» — proposed, needs native review |
| `research_report.TEXT` `instruments` | Instruments and scales | Instrumenti un skalas | Инструменты и шкалы | terminology: the import wizard calls an instrument «методика» | RU «Методики и шкалы» — proposed, needs native review |
| `research_report.TEXT` `reliability`, `limit.reliability` | Reliability and measurement quality / Reliability below .70 | Ticamība … | Надёжность … | terminology: LV «ticamība» and «uzticamība» (§5) | — |
| `research_report.TEXT` `data_columns[4]`, `report_docx.LABELS` `columns[5]` | Rows | Rindas | Строк | agreement: RU column header in the genitive plural | RU «Строки» or «Число строк» — proposed, needs native review |
| `research_report.TEXT` `version_line`, `report_docx.LABELS` `dataset` | Data: {name} ({rows} rows), … | … ({rows} rindas) … | … ({rows} строк) … | agreement: «21 строк», «22 строк»; LV «21 rindas» | needs native review; the plural helper `count_text` exists |
| `research_report.TEXT` `limit.versions` | The results draw on {count} versions of the data. | Rezultāti balstās uz {count} datu versijām. | Результаты опираются на {count} версии данных. | agreement: RU «на 5 версии» is wrong | RU «Результаты опираются на версии данных: {count}.» — proposed, needs native review |
| `research_report.TEXT` `duplicate` | Calculated {count} times with an identical result; written once. | Aprēķināts {count} reizes … | Рассчитано {count} раз(а) … | agreement | needs native review |
| `report_docx.LABELS` `generated` | Generated by Statistical Research Assistant {version} on {date} from the project “{project}”. … | Izveidoja Statistical Research Assistant {version} {date} no projekta … | Создано в Statistical Research Assistant {version} {date} по проекту … | too literal: the date has no preposition or case ending | needs native review |
| `reports.move_up`, `reports.move_down` | Move up / Move down | Pārvietot augšup / lejup | Выше / Ниже | terminology: Chart Studio's same action is «Pārvietot uz augšu», «Переместить вверх» | needs native review |
| `reports.*`, `report_docx.LABELS` `default_title` | Report(s) | Atskaite(s) | Отчёт(ы) | terminology: the classic interface says «Pārskati» (§5) | — |

Newly visible in the Word report: the assumption checks are now written from
`interpretation_i18n.ASSUMPTION_TEXT`. These texts existed before but had
never been read in a document. The ones of the two batch analyses:

| English | Latvian | Russian | Reason |
|---|---|---|---|
| Confirm measurement levels and independence of observations | Apstiprināt mērījumu līmeņus un novērojumu neatkarību | Подтвердить уровни измерения и независимость наблюдений | newly visible |
| Inspect each pair's scatterplot for outliers and non-monotonic patterns | Pārskatīt katra pāra izkliedes diagrammu: izlēcēji un nemonotoni modeļi | Просмотреть диаграмму рассеяния каждой пары: выбросы и немонотонные закономерности | too literal (LV «modeļi» = models for "patterns") |
| Report raw and adjusted p-values together with the family size | Ziņot neapstrādātās un koriģētās p vērtības kopā ar testu skaitu | Сообщать исходные и скорректированные p вместе с числом проверок | terminology ("raw p", §5) |
| Confirm independent groups and the outcome measurement levels | Apstiprināt neatkarīgas grupas un rezultātu mērījumu līmeņus | Подтвердить независимость групп и уровни измерения переменных | terminology ("outcome", §5) |
| Review group sizes: small or unequal groups limit the comparison | Pārskatīt grupu lielumus: … | Проверить размеры групп: … | newly visible |
| Report raw and adjusted p-values and the effect-size definitions | Ziņot … efekta lieluma definīcijas | Сообщать … определения размеров эффекта | newly visible |

The rest of the report's English (table titles and columns, "Interpretation:
/ Methods: / Notes:", the limitations taken from engine warnings, figure
text) comes from the engine (§6).

### 4.5 AI assistant (`assistant.*`, `ai.*`, `depth.*`, `workspace_ai.TEXT`)

| Key | English | Latvian | Russian | Reason | Proposal |
|---|---|---|---|---|---|
| `assistant.title`, `settings.ai`, `assistant.off_title`, `assistant.permissions` vs `workspace_ai.TEXT` `title` and every "Settings → AI providers" reference | AI assistant / AI assistance / AI providers | «MI asistents», «MI palīdzība», «MI pakalpojumu sniedzējs» but «AI pakalpojumu sniedzēji» (card title and references) | «ИИ-помощник», «Провайдеры ИИ» | terminology: LV mixes «MI» and «AI»; references must name the settings card exactly as it is titled | one LV abbreviation (§5) |
| `desktop_shell_text.SHELL_TEXT` `ai`, `ai_status`, `ai_note` | AI assistant | AI asistents | AI-помощник | terminology: the workspace says «ИИ-помощник» | needs native review |
| `assistant.task.hypotheses.detail` | … Hypotheses written after seeing a result are exploratory. | … ir pētnieciskas (exploratory). | … — разведочные. | untranslated English word in the LV text | LV without «(exploratory)» — proposed, needs native review |
| `depth.professor` | Professor | Profesors | Преподаватель | meaning differs: RU «преподаватель» (teacher), the other languages name the expert level | RU «Профессор» or «Эксперт» — needs native review |
| `ai.preview` | What it would contain now | Ko tas saturētu tagad | Что бы это содержало сейчас | too literal (the preview of one project source) | RU «Содержимое сейчас» — proposed, needs native review |
| `ai.ready` vs `ai.unavailable` | Connected: {provider} · {model} / Not connected | Pievienots / Nav pievienots | Подключено / Не подключён | agreement: neuter and masculine for the same status | needs native review |
| `assistant.discard` | Discard | Atmest | Отбросить | terminology: the import wizard's "Discard" is «Удалить» | needs native review |

The text that is sent to a provider and shown in "Exact text to be sent" and
in the project's AI permission preview is built in English by `ai_assist.py`
and `ai_context.py` (§6); the reply is requested in the interface language.

### 4.6 The rest

**Data and variables**

| Key | English | Latvian | Russian | Reason | Proposal |
|---|---|---|---|---|---|
| `role.outcome`, `role.outcomes`, `block.*` (e.g. `block.outcome_scale`, `block.batch_nominal_outcomes`) | Outcome | Rezultāts | Зависимая переменная | terminology: LV «rezultāts» is also "result" (the Results area, every result); the logistic confirmation in `LABELS` says «iznākums» | LV «Iznākums» or «Atkarīgais mainīgais» — proposed, needs native review |
| `level.nominal`, `level.ordinal`, `level.scale`, `level.binary` | Nominal (categories) / Ordinal (ordered) / Quantitative / Binary 0/1 | Nominālais … / Ordinālais … / Kvantitatīvs / Binārs 0/1 | Номинальный (категории) / Порядковый / Количественный / Бинарный 0/1 | agreement: LV mixes definite («-ais») and indefinite («-s») adjectives in one list; RU drops "(ordered)" | needs native review |
| `data.values_unique` | {count} unique | unikālu vērtību: {count} | уникальных значений: {count} | new | — |

**Analysis and results**

| Key | English | Latvian | Russian | Reason | Proposal |
|---|---|---|---|---|---|
| `alt.kruskal` vs `why.batch_kruskal`, `block.small_groups_parametric`, `warn.small_groups_permutation`, `why.small_groups_rank` | Kruskal–Wallis … | «Kruskala–Volisa» vs «Kraskela–Volisa» | «Краскела–Уоллиса» | terminology: two LV spellings in one table; the classic menu says «Kruskals» | one LV form (§5) |
| `alt.unadjusted` | The same comparison without adjustment (Welch), … | … (Welch), … | … (Уэлч), … | terminology: LV elsewhere «Velča» | LV «(Velča)» — proposed, needs native review |
| `alt.alpha`, `why.omega`, `why.alpha_many`, `why.item_diagnostics_many` | Cronbach’s α … / McDonald’s ω … | «Kronbaha α … tas pieņem», «ω … mazāk ierobežojošs», «pārbaudītais … ω» but «pārbaudītā … ω» | «α Кронбаха … предполагает», «однофакторная ω» | agreement: the LV gender of α and ω varies («alfa» and «omega» end in -a) | needs native review |
| `alt.mannwhitney` vs `block.two_groups_for_omnibus` and the new `LABELS` choice | Mann–Whitney U | Manna–Vitnija U | «U Манна–Уитни» vs «U-критерий Манна–Уитни» | terminology | one RU form (§5) |

**Method names (new `LABELS` entries, shown in the method dropdown of the
guided analysis)** — all *new*; the rendering follows how the sentences of the
same table already write the names. Note the LV choice «Kraskela–Volisa»
(the majority form, §5).

| English | Latvian | Russian |
|---|---|---|
| Spearman’s ρ | Spīrmena ρ | ρ Спирмена |
| Pearson’s r | Pīrsona r | r Пирсона |
| Mann–Whitney U | Manna–Vitnija U | U-критерий Манна–Уитни |
| Welch’s independent t | Velča t neatkarīgām izlasēm | t-критерий Уэлча для независимых выборок |
| Kruskal–Wallis H | Kraskela–Volisa H | H-критерий Краскела–Уоллиса |
| Welch ANOVA | Velča ANOVA | ANOVA Уэлча |
| One-way ANOVA | Vienfaktora ANOVA | Однофакторный ANOVA |
| Wilcoxon signed-rank | Vilkoksona zīmju rangu tests | Критерий знаковых рангов Уилкоксона |
| Paired-samples t-test | Pāru izlašu t tests | t-критерий для парных выборок |
| Friedman test | Frīdmena tests | Критерий Фридмана |
| Repeated-measures ANOVA | Atkārtoto mērījumu ANOVA | ANOVA повторных измерений |

**Number agreement in other screens.** A number placeholder followed by a
fixed plural is wrong for some numbers (LV: 1, 21, 31 … take the singular;
RU: 1, 21 … singular, 2–4, 22–24 … genitive singular, the rest genitive
plural). The app has a plural helper (`workspace_text.count_text`,
`PLURALS`); the alternative is the "noun: {count}" pattern already used by
many RU texts.

| Key | Latvian | Russian |
|---|---|---|
| `task.title_compare` | {count} rezultāti pēc {group} | {count} переменных по {group} («2 переменных») |
| `task.title_relate` | {x} ar {count} mainīgajiem | {x} и {count} переменных |
| `task.versions` | Šim uzdevumam ir {count} aprēķini; … | У задачи {count} запусков; … |
| `why.batch_family` | {count} analīzes atbild … | {count} анализов отвечают … |
| `why.repeated` | … mērīti {count} reizes … | … измерили {count} раз(а) … |
| `design.groups_found` | {name}: datos ir {count} grupas: {labels} | {name}: в данных {count} групп(ы): {labels} |
| `block.group_count`, `block.group_count_adjusted` | {name} ir {count} grupas; … | (uses «групп: {count}») |
| `data.preview` | Datu priekšskatījums (pirmās {count} rindas) | Просмотр данных (первые {count} строк) |
| `plan.history` | Plāna vēsture ({count} versijas) | — |
| `why.alpha_many`, `why.item_diagnostics_many` | {count} jautājumi: … | (uses «Пунктов: {count}») |
| `update_ui.TEXT` `updated_checked`, `updated_missing` | Visi {n} projekti … / {n} projekti … | — |

**Long button and step labels (layout risk; check on screen at 100 % and
150 %)** — the 17 `length` findings:

| Key | English | Latvian | Russian |
|---|---|---|---|
| `analyze.mode.guided` | Guided | — | С подсказками (2.2×) |
| `chart.add_view` | New view | — | Новый вариант (1.6×) |
| `chart.copy` | Copy image | — | Копировать изображение (2.2×) |
| `chart.open` | Edit chart | Rediģēt diagrammu (1.7×) | Редактировать график (2.0×) |
| `groups.preview` | Preview | Priekšskatījums (2.1×) | Предпросмотр (1.7×) |
| `home.current_analyze` | Analyze | — | Анализировать (1.9×) |
| `imp.list_next` | Next items | Nākamie jautājumi (1.7×) | — |
| `project.backup` | Back up… | Rezerves kopija… (2.0×) | Резервная копия… (2.0×) |
| `project.restore_backup` | Restore a backup… | Atjaunot no rezerves kopijas… (1.7×) | Восстановить из резервной копии… (1.9×) |
| `project.restore_deleted` | Restore | — | Восстановить (1.7×) |
| `task.new` | New task | Jauns uzdevums (1.8×) | — |
| `task.rerun` | Run again | Aprēķināt vēlreiz (1.9×) | Повторить расчёт (1.8×) |

**Classic interface (`localization.TEXT`, `desktop_shell_text.SHELL_TEXT`)**

| Key | Finding | Reason |
|---|---|---|
| `localization_extended.EXTRA_TEXT` "Statistical Research Assistant" | The classic interface translates the product name («Statistiskās pētniecības asistents», «Статистический исследовательский ассистент»); the workspace, the splash screen and the Word report keep the English name | terminology (open question, §7) |
| `desktop_shell_text` `reliability` vs `localization.TEXT` "Scale reliability" | LV «Skalas ticamība» vs «Skalas uzticamība» | terminology (§5) |
| `desktop_shell_text` `reports`, `word` | LV «Pārskati», «APA pārskata vednis»; the workspace says «Atskaites» | terminology (§5) |
| `localization.TEXT` "Compare groups", "Correlation matrix", "Import diagnostics", "Import research data and inspect its variables before analysis." | Written twice: `localization_extended.EXTRA_TEXT` replaces the entry of `localization.py` (e.g. RU «Корреляционная матрица», not «Матрица корреляций»), so the first text is never shown | review only the shown text; remove the dead one |
| `localization.TEXT` "Dataset" | Written twice in `localization.py` with the same text | cleanup |
| `localization.TEXT` "Both methods use the chosen complete-case items. Omega … Optional CI resamples whole respondents with a fixed random seed." | LV and RU leave out the last sentence (the bootstrap interval) | incomplete translation |
| `localization.TEXT` "PCA uses unrotated total-variance components. …" | RU «с varimax или oblimin», LV «ar varimax vai oblimin» in lower case; elsewhere «Varimax», «Oblimin» | terminology |
| `localization.TEXT` "1  Prepare or collect data    →    2  Review variable types …" | Runs of spaces in all three languages: deliberate spacing around the arrows of the classic home screen (`interface_layout.py` uses the same English as the key) | style, probably intended; keep LV/RU spacing the same as English |
| `localization.TEXT` "Scale / subscale ID, e.g. stress" | RU «например stress»: an identifier example, probably correct as is | style |

## 5. Terminology glossary

What the app uses now. "Proposed" entries are suggestions for the native
reviewers; nothing was changed for them.

| Term | English in the app | Latvian now | Russian now | Inconsistencies found | Proposal |
|---|---|---|---|---|---|
| reliability | Reliability; Scale reliability | «ticamība» (report sections, shell menu, `sample.omega_bootstrap`) and «uzticamība» (`block.totals_not_items`, `block.total_among_items`, classic "Scale reliability") | «надёжность» | LV: two words; «ticamība» is also in «ticamības intervāls» (CI) and in «OCR ticamība» | LV «ticamība» (the established psychometric term), no «uzticamība» — proposed, needs native review |
| Cronbach's alpha | Cronbach’s α | «Kronbaha α» | «α Кронбаха» | LV pronouns and adjectives for α are masculine although «alfa» is feminine | needs native review |
| McDonald's omega | McDonald’s ω; one-factor ω | «Makdonalda ω», «viena faktora ω» | «ω Макдональда», «однофакторная ω» | LV gender of ω varies («pārbaudītais»/«pārbaudītā») | needs native review |
| item (of an instrument) | item | workspace «jautājums» (question); classic «punkts» | «пункт»; «вопрос» in `imp.items`, `imp.check_items`, `imp.scale_items`, `imp.item_reviewed` | both languages differ between screens or interfaces | RU «пункт» for instrument items, «вопрос» for builder questions — proposed, needs native review |
| item–total correlation | item–total correlation (workspace); item–rest correlations (classic omega figure) | «korelācija ar kopsummu»; classic «punktu korelācijas» | «корреляция с итогом»; classic «корреляции пунктов» | the classic texts drop "total/rest"; the corrected (item–rest) and uncorrected forms are not distinguished in LV/RU | needs native review |
| adjusted p | p(adjusted), adjusted p-values | «p(koriģēts)», «koriģētās p vērtības» | «p(скорр.)», «скорректированные p» | consistent | — |
| raw p | raw p-values | «neapstrādātās p vērtības» ("unprocessed") | «исходные p» | — | LV «nekoriģētās p vērtības» — proposed, needs native review |
| multiple-comparison adjustment | Multiple-comparison adjustment | «Daudzkārtējo salīdzinājumu korekcija» | «Поправка на множественные сравнения» | consistent; engine tables still say "p (Holm)" (§6) | — |
| Holm | Holm (familywise error) | «Holms (kopējā kļūda)», «Holma korekcija» | «Холм (групповая ошибка)», «поправка Холма» | consistent | — |
| Benjamini–Hochberg | Benjamini–Hochberg (false discovery rate) | «Benjamini–Hohbergs (kļūdaino atklājumu daļa)» | «Бенджамини–Хохберг (доля ложных открытий)» | LV adapts only the second name | needs native review |
| Bonferroni | Bonferroni (familywise error) | «Bonferoni (kopējā kļūda)» | «Бонферрони (групповая ошибка)» | "familywise error rate": LV «kopējā kļūda» ("overall error") | needs native review |
| confidence interval | 95% CI | «ticamības intervāls», «95% TI» | «доверительный интервал», «95% ДИ» | consistent in the tables; engine columns stay "95% CI" (§6) | — |
| effect size | effect size | «efekta lielums» | «размер эффекта» | consistent; engine texts English (§6) | — |
| Kruskal–Wallis | Kruskal–Wallis H | «Kruskala–Volisa» (`alt.kruskal`, classic "ANOVA & Kruskal–Wallis") and «Kraskela–Volisa» (4 workspace texts and the new `LABELS` choice); classic menu «Kruskals» | «Краскела–Уоллиса» | LV: two spellings | one LV spelling — needs native review |
| Mann–Whitney | Mann–Whitney U | «Manna–Vitnija U» | «U Манна–Уитни», «U-критерий Манна–Уитни» | RU: two forms | needs native review |
| Spearman | Spearman’s ρ | «Spīrmena ρ», «Spīrmens» | «ρ Спирмена» | consistent | — |
| Welch | Welch’s t | «Velča t»; `alt.unadjusted` keeps «(Welch)» | «t-критерий Уэлча» | LV | — |
| measurement level | measurement level | «mērījumu līmenis» | «уровень измерения»; «шкала измерения» for the same English in `interpretation_i18n.METHOD_TEXT` `descriptive.rationale` | RU: two terms | needs native review |
| nominal / ordinal | Nominal (categories) / Ordinal (ordered) | «Nominālais» / «Ordinālais» | «Номинальный» / «Порядковый» | LV definiteness (§4.6) | — |
| interval / ratio | not separate levels: both are "Quantitative" (`level.scale`) | «Kvantitatīvs» | «Количественный» | the app does not distinguish interval and ratio scales | reviewers may want the help texts to say so |
| reverse-scored item | reverse-keyed items; Reverse-score an item (classic) | workspace «apgrieztie jautājumi», «apgriezti vērtējamie jautājumi»; classic «reversi kodēt punktu», «reversais punkts» | workspace «обратные пункты»; classic «реверсивно кодировать пункт», «реверсивный пункт» | two sets of terms in each language | needs native review |
| subscale | subscale | «apakšskala» | «подшкала» | consistent | — |
| instrument | instrument | «instruments» | «методика» (import wizard), «инструмент» (report section) | RU | RU «методика» — proposed, needs native review |
| outcome | outcome | «rezultāts» (also "result"), «iznākums» (logistic) | «зависимая переменная», «исход» (logistic) | LV clashes with "result" | LV «iznākums»/«atkarīgais mainīgais» — proposed, needs native review |
| bootstrap | bootstrap CI | «bootstrap TI» (English word) | «бутстреп-ДИ» | LV | needs native review |
| report | report | workspace «atskaite»; classic «pārskats» | «отчёт» | LV | needs native review |
| AI | AI assistant | «MI …» and «AI …» | «ИИ» (workspace), «AI» (classic) | both | needs native review |
| page (of a document) | page | «lapa» and «lappuse» | «страница» | LV | LV «lappuse» — proposed, needs native review |

## 6. English-only text produced by engine and report modules

These texts are built by the analysis engine or the report builder and
reach LV/RU screens and documents in English. They are not in a text table,
so the checker does not count them; the modules marked † are being changed by
other work at the same time and were deliberately left untouched here.
Found in a run of the Russian workspace (synthetic data: the Stage 36
fixture `synthetic_ucla_sacs_55.csv`, eight correlations and one group
comparison, the synthetic 30-item PDF of `tests/synthetic_documents.py`) and
by reading the code.

| File:function | English text (examples) | Shown where |
|---|---|---|
| `batch_correlation.py:CorrelationFamily.table` † | title "{method}: {focal} with {n} variables"; columns "Variable 1", "Variable 2", "N", "95% CI", "p (raw)", "p (Holm)", "Magnitude"; cells "Calculation failed", "Unavailable" | task card, result table, Word report table, AI request |
| `batch_correlation.py:magnitude_label`, `MAGNITUDE_RULES` † | magnitudes "negligible", "small", "moderate", "large"; rule "Cohen (1988) benchmarks …" (`MAGNITUDE_WORDS` translates the same words, for the interpretation sentences only) | result table, Word report |
| `batch_correlation.py:correlate_many` † | family warnings "Each coefficient is the effect size for its pair; …", "Raw p-values are reported unchanged next to the adjusted ones.", "Correlation does not establish causation.", "A p-value at or above α is not evidence that there is no association." | result cautions, Word report "Notes:" and Limitations |
| `batch_correlation.py:_pair`, `_kendall` † | "Small sample: the estimate and its interval are imprecise."; p-method texts such as "two-sided t approximation with n − 2 df (as reported by SPSS)" | result cautions, Methods text |
| `batch_correlation.py:CorrelationFamily.structured` † | estimate labels "Spearman ρ: UCLA – AssertiveAction" | estimates table, Word "Effects" table |
| `batch_groups.py:GroupFamily.table`, `TwoGroupFamily.table` † | title "Kruskal–Wallis: {n} outcomes by {group}"; columns "Outcome", "n per group", "H", "df", "p", "p (Holm)", "η²_H", "ε²_R" | task card, result table, Word report |
| `batch_groups.py:GroupFamily.structured`, `TwoGroupFamily.structured` † | estimate labels "Kruskal–Wallis H: {outcome} by {group}" | estimates table, Word "Effects" table |
| `batch_groups.py:compare_many`, `compare_two_many`, `_outcome_row` † | "Kruskal–Wallis compares rank distributions; …", "The outcomes form one family (…); raw p-values are kept.", "Group differences do not establish causation; …", "Small groups: the permutation p-value is primary …", "Very unequal group sizes: the test is dominated by the largest group." | result cautions, Word report |
| `multiple_comparisons.py:PROCEDURES` | "Holm (1979) step-down; familywise error rate", "Benjamini–Hochberg (1995) step-up; false discovery rate", "Bonferroni; familywise error rate" | inside the warnings and the Methods text |
| `analysis_runs.py:_family_report` † | report layout "Interpretation:", "Methods:", "Notes:" and the table drawn with "\|" | result report text, Word "Hypothesis tests" |
| `analysis_runs.py:run_batch_correlation`, `run_batch_groups` † | Methods lines "Coefficient: …; complete pairs per pair (N per row).", "p-values: …", "Intervals: …", "Adjustment: …; {n} tests.", "Test: Kruskal–Wallis H, tie-corrected.", "Effect sizes: η²_H = …" | report text, Word report |
| `analysis_runs.py:run_*` † with the `*_reporting.py` modules | the APA report text of every single analysis (by design, see the docstring of `localization.py`: reports stay English until their terminology is reviewed) | result report, TXT and Word exports |
| `*_charts.py`, `batch_charts.py`, `apa_figures.py:SECTION_NOTES` | figure titles, axis labels and notes drawn into the PNG ("Note. …") | result figure, Word figures |
| `chart_studio.py:_default_title`, `describe` (with `_heatmap_sentences`), `_note_text`, `_group_warnings`, `_draw_histogram`, `ChartSpec` | "{method} Correlations Among {n} Variables", "Frequency", "Density", "Note. …", text alternative "Correlation heatmap of {n} variables (…) showing …", "… observations are unstable; …" | Chart Studio preview, its text alternative, saved and copied charts |
| `interpretation_wizard.py:build_analysis_evidence`, `_structured_evidence`, `EvidenceRow`, `_METHOD_LABELS`, `interpretation_summary` | "No confidence interval is available in this analysis summary. Do not infer one from the point estimate."; "Not calculated"; method names; the "Professor" explanation ("Method: …") | result cautions and explanations |
| `interpretation_wizard.py:METHOD_PROFILES` (rationale, assumptions, limitation) | e.g. "Confirm measurement levels and independence of observations", "Correlations are not causal evidence, …" — translated in `interpretation_i18n` and used by the classic wizard and (from this stage) by the Word report | the workspace result screen shows the English (next row) |
| `workspace_analyze.py:ResultsPage._detail` † | estimates table columns "Parameter", "Estimate", "95% CI", "p" and title "{title}: verified estimates"; assumption check boxes, the "not yet verified" list and the limitation in English (translations exist: `interpretation_i18n.translate_assumption`, `translate_method`) | result screen |
| `workspace_analyze.py:ResultsPage._exports` † | text field "Figure number" | result exports |
| `workspace_analyze.py:method_label`, `AnalyzePage._catalog`, the recommendation and the provenance line † | method titles and summaries of `workspace_methods.METHODS` ("Groups compared on several outcomes", "Correlations: one variable with several", …), shown without translation (e.g. «Выполнить: Groups compared on several outcomes»); option choices in `method_label` without `workspace_text.label()` | method catalog, recommendation button, result provenance |
| `workspace_analyze.py` result provenance † | recorded confirmations in English ("I confirm the groups contain independent participants; …"; `LABELS` translations exist) | result provenance |
| `workspace_methods.py:METHODS` | method titles and summaries (English source; no translation table yet) | through `workspace_analyze.py` |
| `ai_assist.py:result_tables` | "Table 1. {title}: verified estimates", "Parameter \| Estimate \| 95% CI \| p" | "Exact text to be sent" |
| `ai_context.py:preview` | "Title: …", "Description: …", level codes "scale", "nominal", "id" | Settings → AI assistance preview |
| `data_loader.py:ImportReport.as_text`, `load_dataset_with_report`, `_validate_options` | "Import: {rows} rows × {n} variables · header row 1 · data starts row 2 · encoding … · separator …", "Numeric conversion: …", warnings such as "Only one variable detected. Confirm the CSV separator and header row." | Data → Import options → Import diagnostics; import errors |
| `scientific_survey_import.py:parse_scientific_lines` (`finish_instrument`), module text at line 869 | "Numeric anchors were found in a mixed or short questionnaire; automatic rating conversion disabled.", "Shared response scale(s) detected and proposed for the linked questions — NOT verified. …"; the scale issues and label problems listed in the scale step | import wizard, source and scale steps |
| `preparation_ui.py:build_preparation_workspace` | the whole data-preparation panel hosted in the Data area: "Transformation", "Mark missing-value codes", "Recode values", "Apply transformation", "Use working copy in analysis", "Save prepared CSV + steps JSON", "Working copy: {n} rows, {m} columns.", "Transformation history", "No transformations yet.", error texts | Data → Prepare data (the classic interface translates a few of these through `ui_i18n`, most are not in its table either) |
| `research_report.py:plan_report` | the Limitations section repeats the engine warnings above; Hypothesis tests include the engine report text | Word report |

The preparation panel was not translated here: hosting it with the classic
translator (`ui_i18n.UITranslator`) would also translate the column-name
labels of its item check boxes, which `build_preparation_workspace` then
passes to `score_scale` as column names, so a column whose name happens to be
a key of the classic table (for example "Frequency", "Agreement" or
"Language") would break the scale score. The classic interface applies that
translator to its whole window, this panel included, when the language is
changed (`research_app.store_language`), so a language change while such a
dataset is loaded has this effect there today (not changed here; worth a
separate fix). A text-key version of the panel, or its planned replacement,
is the safe fix.

## 7. Open questions for the reviewers

1. **Product name.** Translate "Statistical Research Assistant" (as the
   classic interface does) or keep it as a name everywhere (workspace, splash
   screen, Word report)?
2. **Method names.** International form ("Mann–Whitney U") or adapted forms
   («Manna–Vitnija U», «U-критерий Манна–Уитни»)? The sentences of the
   workspace already use adapted forms; this stage gave the method dropdown
   the same treatment.
3. **First-person confirmations** such as «Я проверил(а) …»: keep the
   «(а)» form or rephrase neutrally («Проверено: …»)?
4. **Date answers.** The respondent view shows the ISO mask "YYYY-MM-DD" in
   every language (as the classic builder does). Should LV/RU show
   «GGGG-MM-DD» / «ГГГГ-ММ-ДД»? (A key was not added: an all-caps text fails
   `test_workspace_foundations`, so the change needs that rule's exemption or
   another wording.)
5. **Engine text in LV/RU reports.** Should the report tables, methods and
   notes be translated at all, or stay English for international journals
   while the surrounding text is localized? This decides the scope of the
   work in §6.
6. **LV abbreviation for AI**: «MI» or «AI»?
