"""Researcher-facing wizard guidance in Latvian and Russian.

English remains the canonical scientific export wording. Translation never
changes stable assumption keys or numeric calculation values.
"""

METHOD_TEXT = {
  "descriptive": {
    "lv": {
      "rationale": "Aprakstiet mainīgo atbilstoši apstiprinātajam mērījumu līmenim; aprakstošā statistika nepārbauda cēloņsakarības.",
      "limitation": "Sadalījums pats par sevi nepierāda cēloņsakarības vai reprezentativitāti."
    },
    "ru": {
      "rationale": "Описывайте переменную с учётом подтверждённой шкалы измерения; описательная статистика не проверяет причинность.",
      "limitation": "Распределение само по себе не доказывает причинность или репрезентативность."
    }
  },
  "reliability": {
    "lv": {
      "rationale": "Novērtējiet vienu konstruktu mērošu punktu iekšējo saskaņotību.",
      "limitation": "Alfa vai omega nepierāda validitāti vai stabilitāti laika gaitā."
    },
    "ru": {
      "rationale": "Оцените внутреннюю согласованность пунктов, предназначенных для измерения одного конструкта.",
      "limitation": "Альфа или омега не доказывают валидность либо стабильность во времени."
    }
  },
  "factor": {
    "lv": {
      "rationale": "Izpētiet EFA kopīgo faktoru struktūru vai PCA kopējās dispersijas komponentes.",
      "limitation": "Izpētes slodzes nav apstiprinošas faktoru analīzes pierādījums."
    },
    "ru": {
      "rationale": "Исследуйте общие факторы (EFA) или компоненты общей дисперсии (PCA).",
      "limitation": "Эксплораторные нагрузки не подтверждают измерительную модель."
    }
  },
  "correlation": {
    "lv": {
      "rationale": "Novērtējiet saistību starp mainīgajiem: Pīrsons — lineāru, Spīrmens — monotonu rangu saistību.",
      "limitation": "Korelācija nepierāda cēloņsakarību."
    },
    "ru": {
      "rationale": "Оцените связь переменных: Пирсон — линейную, Спирмен — монотонную ранговую.",
      "limitation": "Корреляция не доказывает причинность."
    }
  },
  "batch_correlation": {
    "lv": {
      "rationale": "Saistiet vienu mainīgo ar vairākiem vienā aprēķinā; pāri veido vienu hipotēžu kopu ar norādītu daudzkārtējo salīdzinājumu korekciju.",
      "limitation": "Korelācijas nav cēloņsakarības pierādījums, un nenozīmīgs pāris nepierāda, ka sakarības nav."
    },
    "ru": {
      "rationale": "Свяжите одну переменную с несколькими за один запуск; пары образуют одно семейство гипотез с указанной поправкой на множественные сравнения.",
      "limitation": "Корреляции не доказывают причинность, а незначимая пара не доказывает отсутствие связи."
    }
  },
  "batch_groups": {
    "lv": {
      "rationale": "Salīdziniet tās pašas grupas vairākos rezultātos vienā aprēķinā; rezultāti veido vienu kopu ar norādītu daudzkārtējo salīdzinājumu korekciju.",
      "limitation": "Grupu atšķirības nepierāda cēloņsakarību; nenozīmīgs rezultāts nepierāda, ka grupas ir vienādas."
    },
    "ru": {
      "rationale": "Сравните одни и те же группы по нескольким переменным за один запуск; переменные образуют одно семейство с указанной поправкой на множественные сравнения.",
      "limitation": "Различия групп не доказывают причинность; незначимый результат не доказывает, что группы одинаковы."
    }
  },
  "matrix": {
    "lv": {
      "rationale": "Izpētiet pāru korelācijas, ņemot vērā vairākkārtējus testus un atšķirīgus pāru izlases apjomus.",
      "limitation": "Siltumkarte nepārbauda cēloņsakarības."
    },
    "ru": {
      "rationale": "Исследуйте попарные корреляции с учётом множественных проверок и размера выборки для каждой пары.",
      "limitation": "Тепловая карта не проверяет причинную структуру."
    }
  },
  "groups": {
    "lv": {
      "rationale": "Salīdziniet divas neatkarīgas grupas ar iznākuma skalai atbilstošu testu.",
      "limitation": "Grupu atšķirības automātiski nenozīmē cēloņietekmi."
    },
    "ru": {
      "rationale": "Сравните две независимые группы критерием, соответствующим шкале зависимой переменной.",
      "limitation": "Различия групп автоматически не означают причинный эффект."
    }
  },
  "paired": {
    "lv": {
      "rationale": "Salīdziniet divus mērījumus tiem pašiem dalībniekiem.",
      "limitation": "Individuālas pārmaiņas pašas par sevi nepierāda intervences efektu."
    },
    "ru": {
      "rationale": "Сравните два измерения одних и тех же участников.",
      "limitation": "Изменения внутри участников сами по себе не доказывают эффект вмешательства."
    }
  },
  "chi": {
    "lv": {
      "rationale": "Pārbaudiet saistību starp kategoriskiem mainīgajiem pēc novērotajām un sagaidāmajām frekvencēm.",
      "limitation": "Statistiskā saistība nav cēloņsakarība."
    },
    "ru": {
      "rationale": "Проверьте связь категориальных переменных по наблюдаемым и ожидаемым частотам.",
      "limitation": "Статистическая связь не является причинностью."
    }
  },
  "omnibus": {
    "lv": {
      "rationale": "Salīdziniet vismaz trīs neatkarīgas grupas ar ANOVA vai rangu alternatīvu.",
      "limitation": "Kopējais tests nenorāda, kuras grupas atšķiras."
    },
    "ru": {
      "rationale": "Сравните три и более независимые группы с ANOVA или ранговой альтернативой.",
      "limitation": "Общий тест не указывает, какие именно группы различаются."
    }
  },
  "regression": {
    "lv": {
      "rationale": "Novērtējiet nosacītas saistības starp kvantitatīvu iznākumu un prediktoriem lineārā modelī.",
      "limitation": "Izlasē izskaidrotā dispersija nepierāda cēloņsakarību vai ārējo prognozēšanas kvalitāti."
    },
    "ru": {
      "rationale": "Оцените условную связь количественного исхода с предикторами в линейной модели.",
      "limitation": "Объяснённая дисперсия в выборке не доказывает причинность или внешнюю прогностическую точность."
    }
  },
  "logistic": {
    "lv": {
      "rationale": "Modelējiet bināra iznākuma izredzes atbilstoši prediktoriem.",
      "limitation": "Izredžu attiecība nav riska attiecība; ROC izlasē nav ārējā validācija."
    },
    "ru": {
      "rationale": "Моделируйте шансы бинарного исхода в зависимости от предикторов.",
      "limitation": "Отношение шансов не равно отношению рисков; ROC в выборке не является внешней валидацией."
    }
  },
  "ancova": {
    "lv": {
      "rationale": "Novērtējiet grupu atšķirības, kas koriģētas pēc kovariātu noteiktām vērtībām.",
      "limitation": "Koriģētie vidējie ir modeļa novērtējumi, nevis neapstrādātie vidējie."
    },
    "ru": {
      "rationale": "Оцените различия групп после корректировки по значениям ковариат.",
      "limitation": "Скорректированные средние — модельные оценки, а не исходные средние."
    }
  },
  "repeated": {
    "lv": {
      "rationale": "Salīdziniet vismaz trīs mērījumus tiem pašiem dalībniekiem.",
      "limitation": "Atkārtoti novērojumi un laika tendences nepierāda cēloņsakarību."
    },
    "ru": {
      "rationale": "Сравните три и более измерения одних и тех же участников.",
      "limitation": "Повторные наблюдения и временные тенденции сами по себе не доказывают причинность."
    }
  }
}

ASSUMPTION_TEXT = {
  "Confirm categorical, ordinal, or quantitative scale": {
    "lv": "Pārbaudīt nominālu, ordinālu vai kvantitatīvu skalu",
    "ru": "Подтвердить номинальную, порядковую или количественную шкалу"
  },
  "Inspect missing values and outliers": {
    "lv": "Pārbaudīt trūkstošās vērtības un ekstrēmos novērojumus",
    "ru": "Проверить пропуски и выбросы"
  },
  "Check that any grouping is meaningful": {
    "lv": "Pārbaudīt grupu jēgu pētījuma kontekstā",
    "ru": "Проверить содержательный смысл групп"
  },
  "Confirm theoretical coherence and dimensionality of items": {
    "lv": "Pārbaudīt punktu teorētisko vienotību un dimensijas",
    "ru": "Проверить теоретическую согласованность и размерность пунктов"
  },
  "Reverse-score keyed items before estimation": {
    "lv": "Reversi pārkodēt punktus pirms aprēķina",
    "ru": "Перекодировать реверсивные пункты до расчёта"
  },
  "Check missingness, sample size and factor-model assumptions": {
    "lv": "Pārbaudīt iztrūkstošos datus, izlases apjomu un faktoru modeļa pieņēmumus",
    "ru": "Проверить пропуски, размер выборки и предпосылки факторной модели"
  },
  "Verify sample adequacy and factorability": {
    "lv": "Pārbaudīt izlases pietiekamību un faktorizējamību",
    "ru": "Проверить достаточность выборки и пригодность для факторизации"
  },
  "Review dimensionality, retention and rotation decisions": {
    "lv": "Pārskatīt dimensiju skaitu, atlasi un rotāciju",
    "ru": "Проверить число факторов, критерий отбора и вращение"
  },
  "Check measurement level, outliers and interpretation of factors": {
    "lv": "Pārbaudīt mērījumu līmeni, ekstrēmus un faktoru interpretāciju",
    "ru": "Проверить уровень измерения, выбросы и интерпретацию факторов"
  },
  "Confirm measurement levels and independence": {
    "lv": "Pārbaudīt mērījumu līmeņus un novērojumu neatkarību",
    "ru": "Подтвердить шкалы измерения и независимость наблюдений"
  },
  "Inspect scatterplot, outliers and linearity/monotonicity": {
    "lv": "Pārbaudīt izkliedi, ekstrēmus un linearitāti/monotonitāti",
    "ru": "Проверить диаграмму рассеяния, выбросы и линейность/монотонность"
  },
  "Check how incomplete pairs were handled": {
    "lv": "Pārbaudīt nepilnu pāru apstrādi",
    "ru": "Проверить обработку неполных пар"
  },
  "Review variable measurement levels": {
    "lv": "Pārskatīt mainīgo mērījumu līmeņus",
    "ru": "Проверить шкалы переменных"
  },
  "Confirm measurement levels and independence of observations": {
    "lv": "Apstiprināt mērījumu līmeņus un novērojumu neatkarību",
    "ru": "Подтвердить уровни измерения и независимость наблюдений"
  },
  "Inspect each pair's scatterplot for outliers and non-monotonic patterns": {
    "lv": "Pārskatīt katra pāra izkliedes diagrammu: izlēcēji un nemonotoni modeļi",
    "ru": "Просмотреть диаграмму рассеяния каждой пары: выбросы и немонотонные закономерности"
  },
  "Report raw and adjusted p-values together with the family size": {
    "lv": "Ziņot neapstrādātās un koriģētās p vērtības kopā ar testu skaitu",
    "ru": "Сообщать исходные и скорректированные p вместе с числом проверок"
  },
  "Confirm independent groups and the outcome measurement levels": {
    "lv": "Apstiprināt neatkarīgas grupas un rezultātu mērījumu līmeņus",
    "ru": "Подтвердить независимость групп и уровни измерения переменных"
  },
  "Review group sizes: small or unequal groups limit the comparison": {
    "lv": "Pārskatīt grupu lielumus: mazas vai nevienādas grupas ierobežo salīdzinājumu",
    "ru": "Проверить размеры групп: малые или неравные группы ограничивают сравнение"
  },
  "Report raw and adjusted p-values and the effect-size definitions": {
    "lv": "Ziņot neapstrādātās un koriģētās p vērtības un efekta lieluma definīcijas",
    "ru": "Сообщать исходные и скорректированные p и определения размеров эффекта"
  },
  "Inspect missing data and pairwise sample sizes": {
    "lv": "Pārbaudīt trūkstošos datus un pāru izlases apjomus",
    "ru": "Проверить пропуски и размеры выборок для пар"
  },
  "Account for multiple testing before confirmatory claims": {
    "lv": "Ņemt vērā vairākkārtējus testus pirms apstiprinošiem secinājumiem",
    "ru": "Учесть множественные проверки перед подтверждающими выводами"
  },
  "Confirm independent participants and grouping": {
    "lv": "Pārbaudīt dalībnieku neatkarību un grupu izveidi",
    "ru": "Подтвердить независимость участников и группировку"
  },
  "Review outcome scale, distributions and outliers": {
    "lv": "Pārskatīt rezultāta skalu, sadalījumus un ekstrēmus",
    "ru": "Проверить шкалу исхода, распределения и выбросы"
  },
  "Check missingness and variance assumptions where relevant": {
    "lv": "Pārbaudīt trūkstošās vērtības un dispersijas pieņēmumus",
    "ru": "Проверить пропуски и предпосылки дисперсий"
  },
  "Verify subject-level matching and order of measurements": {
    "lv": "Pārbaudīt dalībnieku atbilstību un mērījumu secību",
    "ru": "Проверить соответствие участников и порядок измерений"
  },
  "Inspect paired differences and their distribution": {
    "lv": "Pārbaudīt pāru starpības un to sadalījumu",
    "ru": "Проверить распределение парных разностей"
  },
  "Check missing pairs and unusual changes": {
    "lv": "Pārbaudīt trūkstošos pārus un neparastas izmaiņas",
    "ru": "Проверить неполные пары и необычные изменения"
  },
  "Confirm nominal/ordinal categories and independent observations": {
    "lv": "Pārbaudīt nominālas/ordinālas kategorijas un neatkarību",
    "ru": "Подтвердить категории и независимость наблюдений"
  },
  "Check expected cell counts and sparse tables": {
    "lv": "Pārbaudīt sagaidāmās šūnu frekvences un retas kategorijas",
    "ru": "Проверить ожидаемые частоты и редкие ячейки"
  },
  "Consider exact tests when asymptotic assumptions fail": {
    "lv": "Apsvērt precīzos testus, ja asimptotiskie pieņēmumi nav izpildīti",
    "ru": "Рассмотреть точные тесты при нарушении асимптотических предпосылок"
  },
  "Confirm independence and outcome scale": {
    "lv": "Pārbaudīt neatkarību un rezultāta skalu",
    "ru": "Подтвердить независимость и шкалу исхода"
  },
  "Inspect group distributions and variance heterogeneity": {
    "lv": "Pārbaudīt grupu sadalījumus un dispersiju nevienādību",
    "ru": "Проверить распределения групп и неоднородность дисперсий"
  },
  "Define post-hoc comparison family and adjustment": {
    "lv": "Definēt post-hoc salīdzinājumu saimi un korekciju",
    "ru": "Определить семейство пост-хок сравнений и поправку"
  },
  "Inspect linearity, residual patterns and influential observations": {
    "lv": "Pārbaudīt linearitāti, atlikumus un ietekmīgus novērojumus",
    "ru": "Проверить линейность, остатки и влиятельные наблюдения"
  },
  "Check independence, multicollinearity and model specification": {
    "lv": "Pārbaudīt neatkarību, multikolinearitāti un modeļa specifikāciju",
    "ru": "Проверить независимость, мультиколлинеарность и спецификацию модели"
  },
  "Review heteroskedasticity and missing-data exclusions": {
    "lv": "Pārskatīt heteroskedasticitāti un datu izslēgšanu",
    "ru": "Проверить гетероскедастичность и исключённые пропуски"
  },
  "Verify 0/1 outcome and events per predictor": {
    "lv": "Pārbaudīt 0/1 iznākumu un notikumu skaitu uz prediktoru",
    "ru": "Проверить кодировку исхода 0/1 и число событий на предиктор"
  },
  "Inspect separation, influential cases and linearity in the logit": {
    "lv": "Pārbaudīt separāciju, ietekmīgus gadījumus un linearitāti logitā",
    "ru": "Проверить сепарацию, влиятельные случаи и линейность логита"
  },
  "Check calibration and external validation separately": {
    "lv": "Atsevišķi pārbaudīt kalibrāciju un ārējo validāciju",
    "ru": "Отдельно проверить калибровку и внешнюю валидацию"
  },
  "Review covariate measurement and group independence": {
    "lv": "Pārskatīt kovariātu mērījumus un grupu neatkarību",
    "ru": "Проверить измерение ковариат и независимость групп"
  },
  "Check homogeneous slopes or use a justified interaction model": {
    "lv": "Pārbaudīt slīpumu vienādību vai pamatot mijiedarbības modeli",
    "ru": "Проверить однородность наклонов или обосновать взаимодействие"
  },
  "Inspect residual assumptions and extrapolation": {
    "lv": "Pārbaudīt atlikumu pieņēmumus un ekstrapolāciju",
    "ru": "Проверить предпосылки остатков и экстраполяцию"
  },
  "Verify a stable participant across each occasion": {
    "lv": "Pārbaudīt dalībnieka atbilstību visos mērījumos",
    "ru": "Проверить соответствие участника во всех измерениях"
  },
  "Review missing complete cases and time ordering": {
    "lv": "Pārskatīt nepilnos gadījumus un laika secību",
    "ru": "Проверить пропуски и временной порядок"
  },
  "Check sphericity or justified correction for RM ANOVA": {
    "lv": "Pārbaudīt sfēriskumu vai korekciju atkārtotu mērījumu ANOVA",
    "ru": "Проверить сферичность или коррекцию ANOVA повторных измерений"
  }
}


def translate_method(section: str, field: str, original: str, language: str) -> str:
    return METHOD_TEXT.get(section, {}).get(language, {}).get(field, original)


def translate_assumption(original: str, language: str) -> str:
    return ASSUMPTION_TEXT.get(original, {}).get(language, original)
