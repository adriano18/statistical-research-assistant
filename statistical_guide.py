"""Research-method glossary with checked bibliographic references.

Explanations are contextual aids, not automated validity decisions.
All references are external scholarly sources; no network connection needed.
"""

from dataclasses import dataclass
from localization import tr


@dataclass(frozen=True)
class Source:
    label: str
    url: str


SOURCES = {
    "cronbach": Source(
        "Cronbach, L. J. (1951). Coefficient alpha and the internal structure "
        "of tests. Psychometrika, 16, 297–334.",
        "https://doi.org/10.1007/BF02310555",
    ),
    "omega": Source(
        "Hayes, A. F., & Coutts, J. J. (2020). Use omega rather than "
        "Cronbach's alpha for estimating reliability. But… "
        "Communication Methods and Measures, 14(1), 1–24.",
        "https://doi.org/10.1080/19312458.2020.1718629",
    ),
    "factor": Source(
        "Fabrigar, L. R., Wegener, D. T., MacCallum, R. C., & "
        "Strahan, E. J. (1999). Evaluating the use of exploratory factor "
        "analysis in psychological research. Psychological Methods, 4(3), 272–299.",
        "https://doi.org/10.1037/1082-989X.4.3.272",
    ),
    "effect": Source(
        "Lakens, D. (2013). Calculating and reporting effect sizes to "
        "facilitate cumulative science: A practical primer for t-tests "
        "and ANOVAs. Frontiers in Psychology, 4, Article 863.",
        "https://doi.org/10.3389/fpsyg.2013.00863",
    ),
    "uncertainty": Source(
        "Cumming, G. (2014). The new statistics: Why and how. "
        "Psychological Science, 25(1), 7–29.",
        "https://doi.org/10.1177/0956797613504966",
    ),
    "pvalue": Source(
        "Wasserstein, R. L., & Lazar, N. A. (2016). The ASA statement "
        "on p-values: Context, process, and purpose. "
        "The American Statistician, 70(2), 129–133.",
        "https://doi.org/10.1080/00031305.2016.1154108",
    ),
    "apa": Source(
        "American Psychological Association. (2020). Publication manual "
        "of the American Psychological Association (7th ed.).",
        "https://doi.org/10.1037/0000165-000",
    ),
}


@dataclass(frozen=True)
class Term:
    key: str
    symbol: str
    en: str
    lv: str
    ru: str
    source: str

    def explanation(self, language: str) -> str:
        if language == "lv":
            return self.lv
        if language == "ru":
            return self.ru
        return self.en


TERMS = {
    term.key: term for term in [
        Term("n", "N", "Sample size. State how many independent observations "
             "contributed to this estimate; missing values may reduce N.",
             "Izlases apjoms. Norādiet analīzē izmantoto novērojumu skaitu; "
             "trūkstošas vērtības var samazināt N.",
             "Размер выборки. Указывайте число наблюдений в анализе; "
             "пропуски могут уменьшать N.", "uncertainty"),
        Term("missing", "Missing", "Absent responses; identify the mechanism "
             "and whether deletion or coding affects estimates.",
             "Trūkstošas atbildes; pārbaudiet iemeslus un ietekmi uz rezultātu.",
             "Пропущенные ответы; уточните причину и влияние на расчёты.",
             "uncertainty"),
        Term("mean", "M", "Arithmetic mean of numeric scores. It may be "
             "misleading for heavily skewed or merely ordinal data.",
             "Aritmētiskais vidējais. Var būt maldinošs asimetriskiem "
             "vai tikai ordināliem datiem.",
             "Среднее арифметическое. Может вводить в заблуждение при "
             "асимметрии и чисто порядковых данных.", "uncertainty"),
        Term("median", "Mdn", "The middle ordered value; less sensitive to "
             "extreme observations than the mean.",
             "Sakārtotu datu vidējā vērtība; mazāk jutīga pret ekstrēmiem.",
             "Серединное значение упорядоченных данных; устойчивее к выбросам.",
             "uncertainty"),
        Term("sd", "SD", "Sample standard deviation: variation around the "
             "mean in the original units, not a confidence interval.",
             "Standartnovirze: izkliede ap vidējo sākotnējās mērvienībās.",
             "Стандартное отклонение: разброс значений вокруг среднего.",
             "uncertainty"),
        Term("ci", "95% CI", "Interval from a repeated-sampling procedure. "
             "A 95% confidence level describes long-run coverage, not a "
             "95% probability that a fixed parameter lies in this interval.",
             "Intervāls no atkārtotas izlases metodes; 95% attiecas uz "
             "ilgtermiņa pārklājumu, ne parametra varbūtību.",
             "Доверительный интервал: 95% относится к частоте покрытия "
             "при повторных выборках, а не вероятности фиксированного параметра.",
             "uncertainty"),
        Term("se", "SE", "Standard error describes sampling uncertainty of "
             "an estimator; do not confuse it with SD of observations.",
             "Standartkļūda raksturo novērtējuma izlases nenoteiktību, nevis SD.",
             "Стандартная ошибка оценки; это не SD наблюдений.", "uncertainty"),
        Term("p", "p", "Probability of data at least this incompatible with "
             "the null model, under its assumptions. Not the probability "
             "that the hypothesis is true or the effect is important.",
             "Varbūtība datiem pie nulles modeļa pieņēmumiem; tā nav "
             "hipotēzes patiesuma vai efekta nozīmīguma varbūtība.",
             "Вероятность столь же экстремальных данных при нулевой модели; "
             "не вероятность истинности гипотезы или важности эффекта.",
             "pvalue"),
        Term("effect", "Effect size", "Quantifies how large an association or "
             "difference is. Interpret in the units, design and domain.",
             "Efekta lielums raksturo atšķirības vai saistības apjomu kontekstā.",
             "Размер эффекта характеризует величину различия или связи.",
             "effect"),
        Term("normality", "Shapiro–Wilk W", "Checks a specific normality null "
             "model; sample size influences sensitivity. Inspect Q–Q plots.",
             "Normalitātes tests; jutība atkarīga no izlases apjoma. "
             "Pārbaudiet arī Q–Q grafiku.",
             "Проверяет гипотезу нормальности; чувствителен к объёму выборки. "
             "Изучайте также Q–Q график.", "uncertainty"),
        Term("levene", "Levene / Brown–Forsythe", "Assesses group-variance "
             "heterogeneity; a large p is not proof of equal variances.",
             "Pārbauda grupu dispersiju atšķirības; liels p nepierāda "
             "dispersiju vienādību.",
             "Проверяет неоднородность дисперсий; большое p не доказывает "
             "их равенство.", "pvalue"),
        Term("alpha", "Cronbach’s α", "Internal-consistency coefficient under "
             "specific assumptions. It does not establish scale validity, "
             "unidimensionality or test–retest stability.",
             "Iekšējās saskaņotības koeficients ar pieņēmumiem; tas "
             "nepierāda validitāti, viendimensionalitāti vai stabilitāti.",
             "Коэффициент внутренней согласованности; не доказывает валидность, "
             "одномерность или стабильность измерения.", "cronbach"),
        Term("omega", "McDonald’s ω", "Model-based internal-consistency "
             "estimate using factor loadings. Check one-factor model fit "
             "and data type; not evidence of construct validity.",
             "Uz faktoru slodzēm balstīts saskaņotības novērtējums; "
             "pārbaudiet modeļa pieņēmumus un datu tipu.",
             "Модельная оценка согласованности на основе факторных нагрузок; "
             "проверьте предпосылки и тип данных.", "omega"),
        Term("itemrest", "Item–rest r / ρ", "Association of an item with the "
             "total of the other items, excluding the item itself.",
             "Punkta korelācija ar pārējo punktu kopējo rezultātu.",
             "Корреляция пункта с суммой остальных пунктов, без самого пункта.",
             "omega"),
        Term("alphadelete", "α if deleted", "Recomputed coefficient without "
             "one item; changes do not alone justify dropping an item.",
             "Koeficients bez konkrētā punkta; izmaiņas vien nav pamats "
             "punkta dzēšanai.",
             "Коэффициент без пункта; изменение само по себе не основание "
             "удалять вопрос.", "cronbach"),
        Term("loading", "Factor loading", "Association between an observed "
             "variable and a factor in a specified exploratory model.",
             "Novērotā mainīgā saistība ar faktoru konkrētā modelī.",
             "Связь наблюдаемой переменной с фактором в выбранной модели.",
             "factor"),
        Term("eigen", "Eigenvalue", "Amount of variance summarized by a "
             "component or factor criterion; alone is not enough to "
             "choose dimensionality.",
             "Dispersijas apjoma rādītājs; viens pats nenosaka faktoru skaitu.",
             "Показатель объясняемой дисперсии; одного недостаточно для "
             "выбора числа факторов.", "factor"),
        Term("parallel", "Parallel analysis", "Compares observed eigenvalues "
             "with values from simulated random datasets.",
             "Salīdzina empīriskās īpašvērtības ar nejaušu datu rezultātiem.",
             "Сравнивает собственные значения с моделированными случайными "
             "данными.", "factor"),
        Term("r", "Pearson r", "Linear association of quantitative variables "
             "from −1 to 1; not causation.",
             "Lineāra saistība starp kvantitatīviem mainīgajiem; "
             "nepierāda cēloņsakarību.",
             "Линейная связь количественных переменных; не причинность.",
             "uncertainty"),
        Term("rho", "Spearman ρ", "Rank-based monotonic association; appropriate "
             "when a monotonic relation is scientifically meaningful.",
             "Rangu korelācija monotonai saistībai.",
             "Ранговая корреляция монотонной связи.", "uncertainty"),
        Term("t", "t", "Standardized test statistic for a mean difference "
             "under a chosen t-test design; report degrees of freedom.",
             "Standartizēta vidējo starpības testa statistika; "
             "norādiet brīvības pakāpes.",
             "Статистика проверки разности средних; указывайте степени свободы.",
             "effect"),
        Term("d", "Cohen’s d / Hedges’ g", "Standardized mean difference; "
             "the denominator and small-sample correction depend on design.",
             "Standartizēta vidējo starpība; definīcija atkarīga no dizaina.",
             "Стандартизованная разность средних; формула зависит от дизайна.",
             "effect"),
        Term("u", "Mann–Whitney U", "Rank-based comparison of two independent "
             "groups; not automatically a test of medians.",
             "Rangu salīdzinājums divām neatkarīgām grupām; "
             "ne vienmēr mediānu tests.",
             "Ранговое сравнение двух независимых групп; не всегда тест медиан.",
             "effect"),
        Term("w", "Kendall’s W", "Effect-size-style agreement measure for "
             "Friedman/repeated ranks, from 0 to 1.",
             "Saskaņotības rādītājs atkārtotām rangotām atbildēm (0–1).",
             "Мера согласованности рангов в повторных измерениях (0–1).",
             "effect"),
        Term("f", "F", "Variance-ratio test statistic; its interpretation "
             "depends on design and numerator/denominator df.",
             "Dispersiju attiecības statistika; nepieciešamas divas "
             "brīvības pakāpes.",
             "Отношение дисперсий; указывайте степени свободы числителя "
             "и знаменателя.", "effect"),
        Term("eta", "η² / partial η²", "Proportion of variance attributed "
             "to a term under a specific model; partial and total η² "
             "are not interchangeable.",
             "Dispersijas daļa konkrētā modelī; η² un daļējais η² "
             "nav savstarpēji aizvietojami.",
             "Доля дисперсии в конкретной модели; η² и частичная η² "
             "не взаимозаменяемы.", "effect"),
        Term("holm", "Holm adjusted p", "Sequential familywise multiple-test "
             "correction. State the tested family.",
             "Secīga korekcija vairākiem testiem; definējiet testu saimi.",
             "Поправка на множественные сравнения; укажите семейство тестов.",
             "pvalue"),
        Term("chi", "χ²", "Compares observed and expected categorical counts; "
             "inspect sparse expected cells.",
             "Salīdzina novērotās un sagaidāmās kategoriju frekvences; "
             "pārbaudiet retas šūnas.",
             "Сравнивает наблюдаемые и ожидаемые частоты; проверяйте "
             "малые ожидаемые значения.", "effect"),
        Term("cramer", "Cramér’s V", "Nonnegative association-size measure "
             "for contingency tables; magnitude depends on table structure.",
             "Saistības lielums kontingenču tabulām; atkarīgs no "
             "tabulas struktūras.",
             "Мера силы связи в таблицах сопряжённости; зависит от "
             "структуры таблицы.", "effect"),
        Term("b", "B / β", "Regression coefficient: B is an unstandardized "
             "conditional slope; standardized β depends on measurement SDs.",
             "Regresijas koeficients: B ir slīpums oriģinālajās mērvienībās, "
             "β — standartizēts.",
             "Коэффициент регрессии: B — наклон в исходных единицах, "
             "β — стандартизованный.", "uncertainty"),
        Term("r2", "R² / adjusted R²", "Variance explained in-sample. "
             "Adjusted R² penalizes predictor count; neither proves "
             "predictive validity outside the sample.",
             "Izlasē izskaidrotā dispersija; koriģētais R² ņem vērā "
             "prediktoru skaitu.",
             "Объяснённая дисперсия в выборке; скорректированный R² "
             "учитывает число предикторов.", "uncertainty"),
        Term("vif", "VIF", "Variance inflation factor for collinear "
             "predictors; investigate design and estimation instability.",
             "Prediktoru multikolinearitātes rādītājs; pārbaudiet "
             "novērtējumu stabilitāti.",
             "Показатель мультиколлинеарности; проверьте устойчивость "
             "оценок.", "uncertainty"),
        Term("or", "Odds ratio (OR)", "Exponentiated logistic coefficient: "
             "multiplicative change in odds per unit of predictor; not "
             "a risk ratio unless special conditions hold.",
             "Loģistiskā koeficienta eksponente; izredžu attiecība, "
             "ne automātiski riska attiecība.",
             "Экспонента логистического коэффициента; отношение шансов, "
             "не автоматически отношение рисков.", "uncertainty"),
        Term("roc", "ROC / AUC", "In-sample discrimination between binary "
             "outcome classes; not calibrated probability or external validation.",
             "Bināro klašu atšķiršana izlasē; ne ārēja validācija.",
             "Разделение бинарных классов в выборке; не внешняя валидация.",
             "uncertainty"),
        Term("gg", "Greenhouse–Geisser ε", "Correction for repeated-measures "
             "sphericity violations; interpretation requires within-subject design.",
             "Korekcija sfēriskuma pieņēmumam atkārtotos mērījumos.",
             "Коррекция нарушений сферичности повторных измерений.",
             "effect"),
        Term("adjusted", "Adjusted means", "Model-estimated group means at "
             "specified covariate values; not raw group means.",
             "Modeļa grupu vidējie pie noteiktām kovariātu vērtībām.",
             "Модельные средние групп при заданных ковариатах; "
             "не исходные средние.", "uncertainty"),
    ]
}

SCREEN_TERMS = {
    "home": ("n", "missing", "effect", "p", "ci"),
    "dataset": ("n", "missing", "mean", "sd"),
    "preparation": ("missing", "mean", "sd"),
    "survey": ("missing", "alpha", "omega", "itemrest"),
    "descriptive": ("n", "missing", "mean", "median", "sd", "normality", "levene"),
    "reliability": ("alpha", "omega", "ci", "itemrest", "alphadelete"),
    "factor": ("loading", "eigen", "parallel", "ci"),
    "correlation": ("r", "rho", "p", "ci"),
    "matrix": ("r", "rho", "p", "holm"),
    "groups": ("t", "d", "u", "p", "ci"),
    "paired": ("t", "d", "p", "ci"),
    "chi": ("chi", "cramer", "p"),
    "omnibus": ("f", "eta", "holm", "p"),
    "regression": ("b", "r2", "vif", "se", "ci"),
    "logistic": ("b", "or", "roc", "ci", "p"),
    "ancova": ("f", "eta", "adjusted", "p", "ci"),
    "repeated": ("f", "w", "gg", "eta", "holm"),
}

GUIDE_LABELS = {
    "en": {
        "title": "Understanding the statistics · Sources",
        "caution": "Definitions are educational. Verify coding, study design, "
                   "model assumptions and complete-case handling before drawing conclusions.",
        "reference": "Scientific source",
    },
    "lv": {
        "title": "Statistikas skaidrojumi · Avoti",
        "caution": "Skaidrojumi ir informatīvi. Pirms secinājumiem pārbaudiet "
                   "kodēšanu, pētījuma dizainu un modeļa pieņēmumus.",
        "reference": "Zinātniskais avots",
    },
    "ru": {
        "title": "Объяснение показателей · Источники",
        "caution": "Пояснения учебные. Перед выводами проверьте кодирование, "
                   "дизайн исследования, предпосылки модели и пропуски.",
        "reference": "Научный источник",
    },
}


def method_guide_items(screen: str, language: str = "en") -> list[dict[str, str]]:
    """Structured explanations with reproducible original-source references."""
    if language not in GUIDE_LABELS:
        language = "en"
    output = []
    for key in SCREEN_TERMS.get(screen, ()):
        item = TERMS[key]
        source = SOURCES[item.source]
        output.append({
            "key": key,
            "symbol": item.symbol,
            "explanation": item.explanation(language),
            "reference": source.label,
            "url": source.url,
        })
    return output


def method_guide_text(screen: str, language: str = "en") -> str:
    """Copyable methodological notes; never introduce artificial statistics."""
    language = language if language in GUIDE_LABELS else "en"
    labels = GUIDE_LABELS[language]
    lines = [labels["title"], labels["caution"], ""]
    for item in method_guide_items(screen, language):
        lines.extend([
            f"{item['symbol']} — {item['explanation']}",
            f"{labels['reference']}: {item['reference']}",
            item["url"],
            "",
        ])
    return "\n".join(lines).rstrip()
