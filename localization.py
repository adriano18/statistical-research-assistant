"""Selected desktop navigation and onboarding text in English, Latvian, Russian.

Research-method instructions and statistical reports stay English until their
terminology has been reviewed; never silently translate numerical results.
"""

LANGUAGES = {
    "en": "English",
    "lv": "Latviešu",
    "ru": "Русский",
}

TEXT = {
    "Home": ("Sākums", "Главная"),
    "Dataset": ("Datu kopa", "Данные"),
    "Data preparation": ("Datu sagatavošana", "Подготовка данных"),
    "Questionnaires": ("Anketas", "Анкеты"),
    "Descriptive": ("Aprakstošā statistika", "Описательная статистика"),
    "Scale reliability": ("Skalas uzticamība", "Надёжность шкалы"),
    "EFA / PCA": ("EFA / PCA", "Факторный анализ / PCA"),
    "Correlations": ("Korelācijas", "Корреляции"),
    "Correlation matrix": ("Korelāciju matrica", "Матрица корреляций"),
    "Compare groups": ("Grupu salīdzināšana", "Сравнение групп"),
    "Paired measures": ("Saistītie mērījumi", "Парные измерения"),
    "Chi-square": ("Hī kvadrāts", "Хи-квадрат"),
    "ANOVA / Kruskal": ("ANOVA / Kruskals", "ANOVA / Краскел"),
    "Linear regression": ("Lineārā regresija", "Линейная регрессия"),
    "Logistic regression": ("Loģistiskā regresija", "Логистическая регрессия"),
    "ANCOVA / GLM": ("ANCOVA / GLM", "ANCOVA / GLM"),
    "Repeated measures": ("Atkārtoti mērījumi", "Повторные измерения"),
    "DATA & MEASUREMENT": ("DATI UN MĒRĪJUMI", "ДАННЫЕ И ИЗМЕРЕНИЯ"),
    "RELATIONSHIPS": ("SAKARĪBAS", "СВЯЗИ"),
    "GROUP COMPARISONS": ("GRUPU SALĪDZINĀŠANA", "СРАВНЕНИЕ ГРУПП"),
    "STATISTICAL MODELS": ("STATISTISKIE MODEĻI", "СТАТИСТИЧЕСКИЕ МОДЕЛИ"),
    "Research · Analysis · Reports": (
        "Pētījumi · Analīze · Pārskati",
        "Исследования · Анализ · Отчёты",
    ),
    "Start on Home. The advanced modules are grouped so you can open only what you need.": (
        "Sāciet sākumlapā. Papildu analīzes metodes ir sagrupētas.",
        "Начните с главной. Расширенные методы сгруппированы в меню.",
    ),
    "YOUR RESEARCH WORKSPACE": ("JŪSU PĒTNIECĪBAS VIDE", "ВАША ИССЛЕДОВАТЕЛЬСКАЯ СРЕДА"),
    "Start with a question. We'll help with the data.": (
        "Sāciet ar jautājumu. Mēs palīdzēsim ar datiem.",
        "Начните с вопроса. Мы поможем с данными.",
    ),
    "Create questionnaires, prepare datasets and run statistical analyses on this computer. Choose a starting point below; no previous SPSS experience is needed.": (
        "Veidojiet anketas, sagatavojiet datus un veiciet statistisko analīzi savā datorā. Izvēlieties sākumpunktu.",
        "Создавайте анкеты, подготавливайте данные и выполняйте анализ на своём компьютере. Выберите, с чего начать.",
    ),
    "What would you like to do?": (
        "Ko vēlaties darīt?", "Что вы хотите сделать?",
    ),
    "Open research data": ("Atvērt pētījuma datus", "Открыть данные исследования"),
    "Import a CSV or Excel file, check variables and missing responses, then choose an analysis.": (
        "Importējiet CSV vai Excel, pārbaudiet mainīgos un trūkstošās atbildes.",
        "Импортируйте CSV или Excel, проверьте переменные и пропущенные ответы.",
    ),
    "Open CSV / Excel": ("Atvērt CSV / Excel", "Открыть CSV / Excel"),
    "Design a questionnaire": ("Izveidot anketu", "Создать анкету"),
    "Build pages and rating scales, preview the respondent experience, collect local test answers.": (
        "Veidojiet lapas un skalas, pārbaudiet respondenta skatījumu un lokālās atbildes.",
        "Создавайте страницы и шкалы, проверяйте вид для респондента и локальные ответы.",
    ),
    "Create questionnaire": ("Izveidot anketu", "Создать анкету"),
    "Try a guided example": ("Izmēģināt piemēru", "Попробовать пример"),
    "Load fictional sample responses and learn how to inspect data without using real participant records.": (
        "Ielādējiet izdomātus piemēra datus un izpētiet tos.",
        "Загрузите учебные данные и ознакомьтесь с анализом.",
    ),
    "Explore sample data": ("Izpētīt piemēra datus", "Изучить учебные данные"),
    "A simple research workflow": ("Vienkārša pētījuma gaita", "Простой порядок исследования"),
    "1  Prepare or collect data    →    2  Review variable types and missingness    →    3  Choose a statistical method     →    4  Inspect assumptions and export the result": (
        "1  Iegūt datus → 2  Pārbaudīt mainīgos → 3  Izvēlēties metodi → 4  Eksportēt rezultātu",
        "1  Собрать данные → 2  Проверить переменные → 3  Выбрать метод → 4  Экспортировать результат",
    ),
    "Browse statistical methods": ("Pārlūkot analīzes metodes", "Выбрать метод анализа"),
    "See loaded dataset": ("Skatīt datu kopu", "Посмотреть данные"),
    "Private by design: local files and survey responses are not automatically uploaded. Check consent and data-retention requirements before collecting real participant data.": (
        "Dati paliek datorā. Pirms īstu atbilžu vākšanas pārbaudiet piekrišanu un glabāšanas nosacījumus.",
        "Данные остаются на компьютере. Перед сбором реальных ответов проверьте согласие и сроки хранения.",
    ),
    "Dataset": ("Datu kopa", "Данные"),
    "Import research data and inspect its variables before analysis.": (
        "Importējiet datus un pārbaudiet mainīgos pirms analīzes.",
        "Импортируйте данные и проверьте переменные перед анализом.",
    ),
    "Choose a data source": ("Izvēlieties datu avotu", "Выберите источник данных"),
    "Try a fictional example dataset": ("Izmēģināt mācību datu kopu", "Открыть учебный набор данных"),
    "Variable overview": ("Mainīgo pārskats", "Обзор переменных"),
    "Check missing values and types. Numeric storage does not prove that a measurement is continuous.": (
        "Pārbaudiet trūkstošās vērtības un mainīgo tipus. Skaitlisks kods nenozīmē nepārtrauktu skalu.",
        "Проверьте пропуски и типы переменных. Числовой код не означает непрерывную шкалу.",
    ),
    "Files are processed locally. Real participant records should not be committed to a public repository.": (
        "Faili tiek apstrādāti lokāli. Neaugšupielādējiet dalībnieku datus publiskā repozitorijā.",
        "Файлы обрабатываются локально. Не загружайте данные участников в публичный репозиторий.",
    ),
    "Go to workspace": ("Pāriet uz sadaļu", "Перейти в раздел"),
    "Language": ("Valoda", "Язык"),
    "Import settings": ("Importa iestatījumi", "Настройки импорта"),
    "Apply import settings": ("Pielietot importa iestatījumus", "Применить настройки импорта"),
    "Recent files": ("Nesenie faili", "Недавние файлы"),
    "Import diagnostics": ("Importa diagnostika", "Проверка импорта"),
    "No file imported yet.": ("Fails vēl nav importēts.", "Файл пока не импортирован."),
    "Try the new research workspace (Stage 33 preview)": (
        "Izmēģiniet jauno pētījumu darba vidi (33. posma priekšskatījums)",
        "Попробуйте новое рабочее пространство (предпросмотр этапа 33)",
    ),
    "Guided analysis, a results log, a three-pane questionnaire builder and a focused "
    "scientific import. Same engine, same data; this classic interface stays available.": (
        "Vadīta analīze, rezultātu žurnāls, trīs paneļu anketu veidotājs un mērķtiecīgs "
        "zinātniskais imports. Tas pats dzinējs un dati; klasiskā saskarne paliek pieejama.",
        "Пошаговый анализ, журнал результатов, конструктор анкет в три панели и отдельный "
        "научный импорт. Тот же движок и данные; классический интерфейс остаётся доступным.",
    ),
    "Open the preview": ("Atvērt priekšskatījumu", "Открыть предпросмотр"),
    # Stage 37 (#68): the research workspace is the normal start. LV/RU are
    # drafts for native review (docs/STAGE37_UX_SHELL.md).
    "Research workspace": ("Pētījumu darba vide", "Исследовательская среда"),
    "The normal start of the program: projects, guided analysis, results, reports and "
    "questionnaires. Same engine, same data; this classic interface stays available, "
    "and Settings in the workspace choose which interface opens at start.": (
        "Programmas parastais sākums: projekti, vadīta analīze, rezultāti, atskaites un "
        "anketas. Tas pats dzinējs un dati; klasiskā saskarne paliek pieejama, un darba "
        "vides iestatījumos var izvēlēties, kura saskarne atveras startā.",
        "Обычный запуск программы: проекты, пошаговый анализ, результаты, отчёты и анкеты. "
        "Тот же движок и данные; классический интерфейс остаётся доступным, а в настройках "
        "рабочей среды можно выбрать, какой интерфейс открывается при запуске.",
    ),
    "Open the research workspace": ("Atvērt pētījumu darba vidi",
                                    "Открыть исследовательскую среду"),
}


# Keep UI translations separate from stable numeric/scoring codes.
from localization_extended import EXTRA_TEXT
TEXT.update(EXTRA_TEXT)


def tr(language: str, english: str) -> str:
    if language not in LANGUAGES:
        language = "en"
    if language == "en":
        return english
    value = TEXT.get(english)
    if value is None:
        return english
    return value[0] if language == "lv" else value[1]
