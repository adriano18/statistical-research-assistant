"""Shell-only UI labels; never translate respondent values or research metadata."""

SHELL_TEXT = {
    "en": {
        "data_folder": "Your data…",
        "ocr_status": "Offline OCR engine…",
        "ocr_note": "Local OCR (no uploads): ",
        "ocr_checking": "Checking the local OCR engine…",
        "file": "File", "data": "Data", "analysis": "Analysis",
        "reports": "Reports", "database": "Database",
        "settings": "Settings", "help": "Help", "ai": "AI assistant",
        "open_data": "Import CSV / Excel…",
        "import_questionnaire": "Import Word / PDF questionnaire…",
        "new_survey": "New questionnaire",
        "recent": "Recent files / Dataset",
        "prepare": "Prepare data",
        "survey_db": "Saved questionnaires and responses",
        "descriptive": "Descriptive statistics",
        "reliability": "Scale reliability",
        "factor": "EFA / PCA", "correlation": "Correlations",
        "regression": "Regression",
        "word": "APA report wizard",
        "method": "Methodology and references",
        "windows": "Windows · square corners",
        "macos": "macOS · soft corners",
        "style": "Appearance",
        "privacy": "Data privacy",
        "ai_status": "AI assistant status",
        "ai_note": "AI assistant is planned, not connected. The method guide "
                   "and interpretation wizard work offline; no data is sent "
                   "to external AI services.",
        "privacy_note": "Research datasets, survey responses and calculations "
                        "stay local in desktop mode. Do not run an external "
                        "server with identifiable participant data.",
    },
    "lv": {
        "data_folder": "Jūsu dati…",
        "ocr_status": "Bezsaistes OCR dzinējs…",
        "ocr_note": "Lokālais OCR (bez augšupielādes): ",
        "ocr_checking": "Pārbauda lokālo OCR dzinēju…",
        "file": "Fails", "data": "Dati", "analysis": "Analīze",
        "reports": "Pārskati", "database": "Datu bāze",
        "settings": "Iestatījumi", "help": "Palīdzība", "ai": "AI asistents",
        "open_data": "Importēt CSV / Excel…",
        "import_questionnaire": "Importēt Word / PDF anketu…",
        "new_survey": "Jauna anketa",
        "recent": "Nesenie faili / Dati",
        "prepare": "Datu sagatavošana",
        "survey_db": "Saglabātās anketas un atbildes",
        "descriptive": "Aprakstošā statistika",
        "reliability": "Skalas ticamība",
        "factor": "EFA / PCA", "correlation": "Korelācijas",
        "regression": "Regresija",
        "word": "APA pārskata vednis",
        "method": "Metodika un avoti",
        "windows": "Windows · taisni stūri",
        "macos": "macOS · noapaļoti stūri",
        "style": "Izskats",
        "privacy": "Datu privātums",
        "ai_status": "AI asistenta statuss",
        "ai_note": "AI asistents ir plānots, bet nav pieslēgts. "
                   "Metodiskais ceļvedis un interpretācijas vednis darbojas "
                   "bezsaistē; dati netiek nosūtīti AI pakalpojumiem.",
        "privacy_note": "Darbvirsmas režīmā pētniecības dati un anketu atbildes "
                        "paliek lokāli. Neizmantojiet ārēju serveri ar "
                        "identificējamu dalībnieku informāciju.",
    },
    "ru": {
        "data_folder": "Ваши данные…",
        "ocr_status": "Офлайн-движок OCR…",
        "ocr_note": "Локальное OCR (без загрузки в сеть): ",
        "ocr_checking": "Проверка локального движка OCR…",
        "file": "Файл", "data": "Данные", "analysis": "Анализ",
        "reports": "Отчёты", "database": "База данных",
        "settings": "Настройки", "help": "Справка", "ai": "AI-помощник",
        "open_data": "Импорт CSV / Excel…",
        "import_questionnaire": "Импорт анкеты Word / PDF…",
        "new_survey": "Новая анкета",
        "recent": "Недавние файлы / Данные",
        "prepare": "Подготовка данных",
        "survey_db": "Сохранённые анкеты и ответы",
        "descriptive": "Описательная статистика",
        "reliability": "Надёжность шкалы",
        "factor": "EFA / PCA", "correlation": "Корреляции",
        "regression": "Регрессия",
        "word": "Мастер отчёта APA",
        "method": "Методика и источники",
        "windows": "Windows · прямые углы",
        "macos": "macOS · мягкие углы",
        "style": "Оформление",
        "privacy": "Конфиденциальность",
        "ai_status": "Статус AI-помощника",
        "ai_note": "AI-помощник запланирован, но пока не подключён. "
                   "Методические справки и мастер интерпретации работают "
                   "локально; данные не отправляются внешним AI-сервисам.",
        "privacy_note": "В режиме настольного приложения данные исследований "
                        "и ответы остаются локальными. Не запускайте "
                        "внешний сервер с идентифицируемыми данными участников.",
    },
}


def shell_label(code: str, key: str) -> str:
    return SHELL_TEXT.get(code, SHELL_TEXT["en"]).get(
        key, SHELL_TEXT["en"].get(key, key)
    )
