"""English, Latvian and Russian text of the path models (Stage 37, Issue #66).

Pure data, imported by :mod:`process_models` (the English notes stored with
a result) and :mod:`process_reporting` (tables, summaries, interpretation and
the methods text in the researcher's language). The table is audited by
``tools/locale_audit.py`` (``process_text.TEXT``): every key has all three
languages and the same ``{placeholders}``.

LV/RU drafts — needs native review by a methodologist before a release.

Wording rules (tested in ``tests/test_process_workspace.py``):
* no causal wording: no "causes", "leads to", "influences", "impact";
  "effect" is used only as the conventional name of a model quantity
  (direct, indirect, conditional effect) and every result says so;
* mediators, the model number and the moderated path are the researcher's
  choices; no text suggests choosing them by p-values.
"""

from __future__ import annotations

TEXT: dict[str, dict[str, str | tuple[str, ...]]] = {
    "en": {
        "report.header": "APA 7-style reporting (researcher review required)",
        "report.interpretation": "Interpretation:",
        "report.notes": "Notes:",
        # Model names
        "model.1": "Model 1: moderation (W moderates X → Y)",
        "model.4": "Model 4: mediation (X → M → Y)",
        "model.7": "Model 7: W moderates X → M (first-stage moderated mediation)",
        "model.14": "Model 14: W moderates M → Y (second-stage moderated mediation)",
        "methods": "Structure equivalent to PROCESS Model {model} (Hayes, 2022); computed by this "
                   "program, not by the PROCESS macro. Each equation is an ordinary least squares "
                   "regression of the {n} complete cases (listwise deletion of {excluded} of "
                   "{total} rows){covariates}. {se}",
        "methods.covariates": ", with the covariates {names} in every equation",
        "methods.se.ols": "Path standard errors are the classical OLS standard errors; p-values "
                          "and 95% intervals use the t distribution.",
        "methods.se.hc3": "Path standard errors are HC3 heteroskedasticity-consistent standard "
                          "errors; p-values and 95% intervals use the t distribution.",
        "methods.boot": "Indirect effects are tested with a {level} percentile bootstrap "
                        "interval from {resamples} resamples of the complete cases (seed "
                        "{seed}; {valid} valid); no p-value is computed for them.",
        "methods.center": "The variables that form products ({names}) were mean-centred "
                          "before the products were formed.",
        "methods.nocenter": "No variable was mean-centred.",
        "methods.w_values": "Conditional effects are evaluated at W = mean − 1 SD, mean and "
                            "mean + 1 SD and at the 16th, 50th and 84th percentiles of W "
                            "(linear interpolation, Hyndman–Fan type 7) in the analysis sample.",
        "methods.w_binary": "W has two values in the analysis sample; conditional effects are "
                            "evaluated at both.",
        "methods.jn": "Johnson–Neyman: values of W where the conditional effect of X has p = "
                      "{alpha} exactly, solved in closed form from the coefficient covariance "
                      "matrix.",
        # Labels of quantities
        "q.a": "a path: X → {m}",
        "q.b": "b path: {m} → Y",
        "q.direct": "Direct effect c′: X → Y (with M in the model)",
        "q.total": "Total effect c: X → Y (without M)",
        "q.indirect": "Indirect effect via {m} (a × b)",
        "q.indirect_total": "Total indirect effect",
        "q.indirect_std": "Completely standardized indirect effect via {m}",
        "q.indirect_std_total": "Completely standardized total indirect effect",
        "q.indirect_pstd": "Partially standardized indirect effect via {m}",
        "q.indirect_pstd_total": "Partially standardized total indirect effect",
        "q.interaction": "Interaction {product}",
        "q.delta_r2": "ΔR² of {product} ({outcome} equation)",
        "q.f2": "Cohen’s f² of {product} ({outcome} equation)",
        "q.cond": "Conditional effect of {focal} on {outcome} at W = {w} ({where})",
        "q.cond_indirect": "Conditional indirect effect via {m} at W = {w} ({where})",
        "q.index": "Index of moderated mediation via {m}",
        "q.r2": "R² of the {outcome} equation",
        # Where W is evaluated
        "w.minus": "mean − 1 SD",
        "w.mean": "mean",
        "w.plus": "mean + 1 SD",
        "w.p16": "16th percentile",
        "w.p50": "50th percentile",
        "w.p84": "84th percentile",
        "w.low": "lower value",
        "w.high": "higher value",
        "w.chosen": "chosen by the researcher",
        # Table titles and columns
        "table.paths": "Model {model}: coefficients of every equation",
        "table.paths.columns": ("Equation", "Term", "b", "SE", "t", "p", "95% CI", "β", "VIF"),
        "table.fit": "Model {model}: fit of each equation",
        "table.fit.columns": ("Equation", "N", "R²", "Adjusted R²", "F", "df", "p"),
        "table.indirect": "Model {model}: indirect effects (percentile bootstrap)",
        "table.indirect.columns": ("Path", "Effect", "Bootstrap SE", "95% CI"),
        "table.effects": "Model {model}: direct and total effects",
        "table.effects.columns": ("Effect", "b", "SE", "t", "p", "95% CI"),
        "table.interaction": "Model {model}: test of the interaction",
        "table.interaction.columns": ("Product", "Equation", "ΔR²", "F", "df", "p", "f²"),
        "table.conditional": "Model {model}: conditional effects of {focal} at values of W",
        "table.conditional.columns": ("W", "Where", "Effect", "SE", "t", "p", "95% CI"),
        "table.cond_indirect": "Model {model}: conditional indirect effects (percentile "
                               "bootstrap)",
        "table.cond_indirect.columns": ("Mediator", "W", "Where", "Effect", "Bootstrap SE",
                                        "95% CI"),
        "table.index": "Model {model}: index of moderated mediation (percentile bootstrap)",
        "table.index.columns": ("Mediator", "Index", "Bootstrap SE", "95% CI"),
        "table.jn": "Model 1: Johnson–Neyman values of W",
        "table.jn.columns": ("W", "Share of the sample below", "Share of the sample above",
                             "Effect", "SE", "p"),
        "table.diagnostics": "Model {model}: residual diagnostics of each equation",
        "table.diagnostics.columns": ("Equation", "Shapiro–Wilk p", "Breusch–Pagan p",
                                      "Max Cook’s D", "Cook’s D > 4/N", "Max leverage",
                                      "Leverage > 2p/N", "Max VIF"),
        "table.missing": "Missing data (listwise deletion)",
        "table.missing.columns": ("Variable", "Missing", "Missing %"),
        "table.excluded": "Cases left out compared with cases analysed (descriptive)",
        "table.excluded.columns": ("Variable", "Analysed: n", "Analysed: M (SD)",
                                   "Left out: n observed", "Left out: M (SD)", "SMD"),
        "table.sensitivity": "Monte Carlo sensitivity simulation (assumed population values; "
                             "not a result about these data)",
        "table.sensitivity.columns": ("Focal quantity", "Assumed standardized value", "N",
                                      "Replications", "Detected (power)", "Monte Carlo SE"),
        # Cells
        "cell.constant": "Constant",
        "cell.not_defined": "not defined",
        "cell.na": "—",
        "cell.total_eq": "{outcome} (total effect: X and covariates only)",
        # Summary and interpretation
        "summary.n": "N = {n} complete cases of {total} (listwise).",
        "summary.indirect": "Indirect effect via {m}: {est}, 95% bootstrap CI [{low}, {high}].",
        "summary.interaction": "Interaction {product}: b = {est}, 95% CI [{low}, {high}], {p}; "
                               "ΔR² = {dr2}.",
        "summary.index": "Index of moderated mediation via {m}: {est}, 95% bootstrap CI "
                         "[{low}, {high}].",
        "interp.indirect.excludes": "Via {m}: the 95% bootstrap interval of the indirect effect "
                                    "({est}) does not include zero, so these data are "
                                    "compatible with a non-zero indirect path in the model the "
                                    "researcher specified.",
        "interp.indirect.includes": "Via {m}: the 95% bootstrap interval of the indirect effect "
                                    "({est}) includes zero, so these data do not provide "
                                    "evidence of an indirect path; this does not show that "
                                    "there is none.",
        "interp.interaction.yes": "The association of {focal} with {outcome} differs across "
                                  "values of W in these data (interaction {p}); see the "
                                  "conditional effects.",
        "interp.interaction.no": "These data do not provide evidence that the association of "
                                 "{focal} with {outcome} differs across values of W "
                                 "(interaction {p}); this does not show that it is the same.",
        "interp.index.excludes": "Via {m}: the 95% bootstrap interval of the index of moderated "
                                 "mediation ({est}) does not include zero: the conditional "
                                 "indirect effects differ across W in these data.",
        "interp.index.includes": "Via {m}: the 95% bootstrap interval of the index of moderated "
                                 "mediation ({est}) includes zero: these data do not provide "
                                 "evidence that the indirect effect depends on W.",
        "interp.inconsistent.both": "Via {m}: the indirect effect ({ab}) has the opposite sign "
                                    "to the direct effect c′ ({direct}) and to the total effect "
                                    "c ({total}): inconsistent mediation (suppression; MacKinnon, "
                                    "Krull & Lockwood, 2000).",
        "interp.inconsistent.direct": "Via {m}: the indirect effect ({ab}) has the opposite sign "
                                      "to the direct effect c′ ({direct}): inconsistent mediation "
                                      "(suppression; MacKinnon, Krull & Lockwood, 2000).",
        "interp.inconsistent.total": "Via {m}: the indirect effect ({ab}) has the opposite sign "
                                     "to the total effect c ({total}): inconsistent mediation "
                                     "(suppression; MacKinnon, Krull & Lockwood, 2000).",
        "interp.inconsistent.conditional": "Via {m}, at W = {values}: the conditional indirect "
                                           "effect has the opposite sign to the direct effect c′ "
                                           "({direct}): inconsistent mediation at those values of "
                                           "W (suppression; MacKinnon, Krull & Lockwood, 2000).",
        "interp.not_causal": "These are conditional associations in the data as analysed. "
                             "“Effect” is the conventional name of these model quantities "
                             "(Hayes, 2022); it does not mean that one variable changes another.",
        "interp.cross_sectional": "Cross-sectional data cannot establish temporal order or "
                                  "causal mediation.",
        # Notes and warnings (English versions are stored with the result)
        "warn.listwise": "{excluded} of {total} rows were left out because a model variable was "
                         "missing (listwise deletion); every equation uses the same {n} "
                         "complete cases.",
        "warn.small_n": "Small sample (N = {n}): estimates, bootstrap intervals and diagnostics "
                        "may be unstable.",
        "warn.shapiro": "{outcome} equation: residual Shapiro–Wilk p = {p}; examine the Q–Q "
                        "plot (the coefficients do not need normal residuals; small-sample t "
                        "tests do).",
        "warn.bp": "{outcome} equation: Breusch–Pagan p = {p} suggests non-constant residual "
                   "variance; HC3 standard errors are an option.",
        "warn.cooks": "{outcome} equation: {count} case(s) with Cook’s distance above 4/N; "
                      "review them, do not delete them automatically.",
        "warn.leverage": "{outcome} equation: {count} case(s) with leverage above 2p/N.",
        "warn.vif": "{outcome} equation: VIF above 5 for {terms}. Products of uncentred "
                    "variables are collinear with their components by construction; this "
                    "does not change the test of the product.",
        "warn.w_outside": "W = {value} ({where}) lies outside the observed values of {w} "
                          "({low} to {high}); the conditional effect there is an "
                          "extrapolation.",
        "warn.boot_invalid": "{invalid} of {total} bootstrap resamples had a singular design "
                             "and were left out.",
        "warn.hc3": "HC3 standard errors apply to the paths and conditional effects; the "
                    "bootstrap intervals do not depend on them; model F and ΔR² tests are "
                    "the classical OLS tests.",
        "warn.cross_sectional": "Cross-sectional data cannot establish temporal order: an "
                                "indirect path is a pattern of conditional associations, not "
                                "evidence of causal mediation.",
        "warn.effect_word": "“Effect” is the conventional name of these model quantities "
                            "(Hayes, 2022); here they are conditional associations.",
        "warn.no_screening": "The mediators were named by the researcher, not selected by "
                             "p-values; a significant total effect is not required for an "
                             "indirect effect (Hayes, 2022).",
        "warn.interaction": "An interaction shows that an association differs across values "
                            "of W in these data; it does not show why.",
        "warn.binary_x": "X has two values; the completely standardized indirect effect is "
                         "not defined, the partially standardized one (a × b / SD of Y) is "
                         "reported.",
        "warn.excluded_few": "Only {count} case(s) were left out; a comparison of analysed and "
                             "left-out cases is not meaningful.",
        "warn.excluded_compare": "The comparison of analysed and left-out cases is descriptive; "
                                 "it cannot show whether values are missing at random.",
        "jn.none": "No Johnson–Neyman value lies within the observed range of W: the "
                   "conditional effect is {state} at p < {alpha} across the whole range.",
        "jn.state.significant": "different from zero",
        "jn.state.not_significant": "not different from zero",
        "sensitivity.note": "Simulated with the same model and N: X, W and covariate rows are "
                            "resampled from the data, the other coefficients and the residual "
                            "variances are the sample estimates, and the focal quantity takes "
                            "the assumed standardized values. {test} {replications} "
                            "replications, seed {seed}. This is not ‘observed power’ and says "
                            "nothing about whether the result above is true.",
        "sensitivity.test.t": "Detected: two-sided p < {alpha} for the product term.",
        "sensitivity.test.mc": "Detected: the 95% Monte Carlo interval (2000 draws) of the "
                               "focal product of coefficients excludes zero.",
        "sensitivity.focal.interaction": "Interaction {product}",
        "sensitivity.focal.indirect": "Indirect effect via {m} (a and b paths at the assumed "
                                      "value)",
        "sensitivity.focal.index7": "Index of moderated mediation via {m} (X × W → {m} at the "
                                    "assumed value)",
        "sensitivity.focal.index14": "Index of moderated mediation via {m} ({m} × W → Y at the "
                                     "assumed value)",
    },
    "lv": {
        "report.header": "Ziņojums APA 7 stilā (pētniekam jāpārskata)",
        "report.interpretation": "Interpretācija:",
        "report.notes": "Piezīmes:",
        "model.1": "1. modelis: moderācija (W moderē X → Y)",
        "model.4": "4. modelis: mediācija (X → M → Y)",
        "model.7": "7. modelis: W moderē X → M (pirmās pakāpes moderēta mediācija)",
        "model.14": "14. modelis: W moderē M → Y (otrās pakāpes moderēta mediācija)",
        "methods": "Struktūra atbilst PROCESS {model}. modelim (Hayes, 2022); to aprēķināja šī "
                   "programma, nevis PROCESS makross. Katrs vienādojums ir mazāko kvadrātu "
                   "(OLS) regresija {n} pilnajiem gadījumiem (izslēgtas {excluded} no {total} "
                   "rindām){covariates}. {se}",
        "methods.covariates": ", ar kovariātiem {names} katrā vienādojumā",
        "methods.se.ols": "Ceļu standartkļūdas ir klasiskās OLS standartkļūdas; p vērtības un "
                          "95% intervāli izmanto t sadalījumu.",
        "methods.se.hc3": "Ceļu standartkļūdas ir heteroskedasticitātei noturīgās HC3 "
                          "standartkļūdas; p vērtības un 95% intervāli izmanto t sadalījumu.",
        "methods.boot": "Netiešie efekti pārbaudīti ar {level} procentiļu bootstrap intervālu no "
                        "{resamples} pilno gadījumu atkārtotām izlasēm (sākumvērtība {seed}; "
                        "derīgas {valid}); p vērtība tiem netiek aprēķināta.",
        "methods.center": "Mainīgie, kas veido reizinājumus ({names}), pirms reizinājumu "
                          "izveides centrēti ap vidējo.",
        "methods.nocenter": "Neviens mainīgais nav centrēts.",
        "methods.w_values": "Nosacītie efekti novērtēti pie W = vidējais − 1 SD, vidējais un "
                            "vidējais + 1 SD un pie W 16., 50. un 84. procentiles (lineārā "
                            "interpolācija, Hyndman–Fan 7. tips) analīzes izlasē.",
        "methods.w_binary": "W analīzes izlasē ir divas vērtības; nosacītie efekti novērtēti pie "
                            "abām.",
        "methods.jn": "Džonsona–Neimana metode: W vērtības, kur X nosacītajam efektam p = "
                      "{alpha} tieši; aprēķinātas slēgtā formā no koeficientu kovariāciju "
                      "matricas.",
        "q.a": "a ceļš: X → {m}",
        "q.b": "b ceļš: {m} → Y",
        "q.direct": "Tiešais efekts c′: X → Y (ar M modelī)",
        "q.total": "Kopējais efekts c: X → Y (bez M)",
        "q.indirect": "Netiešais efekts caur {m} (a × b)",
        "q.indirect_total": "Kopējais netiešais efekts",
        "q.indirect_std": "Pilnībā standartizēts netiešais efekts caur {m}",
        "q.indirect_std_total": "Pilnībā standartizēts kopējais netiešais efekts",
        "q.indirect_pstd": "Daļēji standartizēts netiešais efekts caur {m}",
        "q.indirect_pstd_total": "Daļēji standartizēts kopējais netiešais efekts",
        "q.interaction": "Mijiedarbība {product}",
        "q.delta_r2": "{product} ΔR² ({outcome} vienādojumā)",
        "q.f2": "{product} Koena f² ({outcome} vienādojumā)",
        "q.cond": "{focal} nosacītais efekts uz {outcome} pie W = {w} ({where})",
        "q.cond_indirect": "Nosacītais netiešais efekts caur {m} pie W = {w} ({where})",
        "q.index": "Moderētās mediācijas indekss caur {m}",
        "q.r2": "{outcome} vienādojuma R²",
        "w.minus": "vidējais − 1 SD",
        "w.mean": "vidējais",
        "w.plus": "vidējais + 1 SD",
        "w.p16": "16. procentile",
        "w.p50": "50. procentile",
        "w.p84": "84. procentile",
        "w.low": "zemākā vērtība",
        "w.high": "augstākā vērtība",
        "w.chosen": "pētnieka izvēlēta",
        "table.paths": "{model}. modelis: visu vienādojumu koeficienti",
        "table.paths.columns": ("Vienādojums", "Loceklis", "b", "SE", "t", "p", "95% TI", "β",
                                "VIF"),
        "table.fit": "{model}. modelis: katra vienādojuma atbilstība",
        "table.fit.columns": ("Vienādojums", "N", "R²", "Koriģētais R²", "F", "bp", "p"),
        "table.indirect": "{model}. modelis: netiešie efekti (procentiļu bootstrap)",
        "table.indirect.columns": ("Ceļš", "Efekts", "Bootstrap SE", "95% TI"),
        "table.effects": "{model}. modelis: tiešais un kopējais efekts",
        "table.effects.columns": ("Efekts", "b", "SE", "t", "p", "95% TI"),
        "table.interaction": "{model}. modelis: mijiedarbības pārbaude",
        "table.interaction.columns": ("Reizinājums", "Vienādojums", "ΔR²", "F", "bp", "p",
                                      "f²"),
        "table.conditional": "{model}. modelis: {focal} nosacītie efekti pie W vērtībām",
        "table.conditional.columns": ("W", "Kur", "Efekts", "SE", "t", "p", "95% TI"),
        "table.cond_indirect": "{model}. modelis: nosacītie netiešie efekti (procentiļu "
                               "bootstrap)",
        "table.cond_indirect.columns": ("Mediators", "W", "Kur", "Efekts", "Bootstrap SE",
                                        "95% TI"),
        "table.index": "{model}. modelis: moderētās mediācijas indekss (procentiļu bootstrap)",
        "table.index.columns": ("Mediators", "Indekss", "Bootstrap SE", "95% TI"),
        "table.jn": "1. modelis: Džonsona–Neimana W vērtības",
        "table.jn.columns": ("W", "Izlases daļa zemāk", "Izlases daļa augstāk", "Efekts",
                             "SE", "p"),
        "table.diagnostics": "{model}. modelis: katra vienādojuma atlikumu diagnostika",
        "table.diagnostics.columns": ("Vienādojums", "Šapiro–Vilka p", "Breuša–Pagana p",
                                      "Maks. Kuka D", "Kuka D > 4/N", "Maks. svira",
                                      "Svira > 2p/N", "Maks. VIF"),
        "table.missing": "Trūkstošie dati (pilno gadījumu analīze)",
        "table.missing.columns": ("Mainīgais", "Trūkst", "Trūkst %"),
        "table.excluded": "Izslēgtie gadījumi salīdzinājumā ar analizētajiem (aprakstoši)",
        "table.excluded.columns": ("Mainīgais", "Analizēti: n", "Analizēti: M (SD)",
                                   "Izslēgti: n ar vērtību", "Izslēgti: M (SD)", "SMD"),
        "table.sensitivity": "Monte Karlo jutīguma simulācija (pieņemtas populācijas vērtības; "
                             "nav rezultāts par šiem datiem)",
        "table.sensitivity.columns": ("Galvenais lielums", "Pieņemtā standartizētā vērtība",
                                      "N", "Atkārtojumi", "Atklāts (jauda)",
                                      "Monte Karlo SE"),
        "cell.constant": "Konstante",
        "cell.not_defined": "nav definēts",
        "cell.na": "—",
        "cell.total_eq": "{outcome} (kopējais efekts: tikai X un kovariāti)",
        "summary.n": "N = {n} pilnie gadījumi no {total} (pilno gadījumu analīze).",
        "summary.indirect": "Netiešais efekts caur {m}: {est}, 95% bootstrap TI [{low}, {high}].",
        "summary.interaction": "Mijiedarbība {product}: b = {est}, 95% TI [{low}, {high}], {p}; "
                               "ΔR² = {dr2}.",
        "summary.index": "Moderētās mediācijas indekss caur {m}: {est}, 95% bootstrap TI "
                         "[{low}, {high}].",
        "interp.indirect.excludes": "Caur {m}: netiešā efekta ({est}) 95% bootstrap intervāls "
                                    "neietver nulli, tātad šie dati ir saderīgi ar nenulles "
                                    "netiešo ceļu pētnieka noteiktajā modelī.",
        "interp.indirect.includes": "Caur {m}: netiešā efekta ({est}) 95% bootstrap intervāls "
                                    "ietver nulli, tātad šie dati nesniedz pierādījumus par "
                                    "netiešo ceļu; tas nenozīmē, ka tāda nav.",
        "interp.interaction.yes": "{focal} saistība ar {outcome} šajos datos atšķiras pie "
                                  "dažādām W vērtībām (mijiedarbība {p}); skatiet nosacītos "
                                  "efektus.",
        "interp.interaction.no": "Šie dati nesniedz pierādījumus, ka {focal} saistība ar "
                                 "{outcome} atšķiras pie dažādām W vērtībām (mijiedarbība {p}); "
                                 "tas nenozīmē, ka tā ir vienāda.",
        "interp.index.excludes": "Caur {m}: moderētās mediācijas indeksa ({est}) 95% bootstrap "
                                 "intervāls neietver nulli: nosacītie netiešie efekti šajos "
                                 "datos atšķiras pie dažādām W vērtībām.",
        "interp.index.includes": "Caur {m}: moderētās mediācijas indeksa ({est}) 95% bootstrap "
                                 "intervāls ietver nulli: šie dati nesniedz pierādījumus, ka "
                                 "netiešais efekts ir atkarīgs no W.",
        "interp.inconsistent.both": "Caur {m}: netiešajam efektam ({ab}) ir pretēja zīme nekā "
                                    "tiešajam efektam c′ ({direct}) un kopējam efektam c "
                                    "({total}): nekonsekventa mediācija (supresija; MacKinnon, "
                                    "Krull & Lockwood, 2000).",
        "interp.inconsistent.direct": "Caur {m}: netiešajam efektam ({ab}) ir pretēja zīme nekā "
                                      "tiešajam efektam c′ ({direct}): nekonsekventa mediācija "
                                      "(supresija; MacKinnon, Krull & Lockwood, 2000).",
        "interp.inconsistent.total": "Caur {m}: netiešajam efektam ({ab}) ir pretēja zīme nekā "
                                     "kopējam efektam c ({total}): nekonsekventa mediācija "
                                     "(supresija; MacKinnon, Krull & Lockwood, 2000).",
        "interp.inconsistent.conditional": "Caur {m} pie W = {values}: nosacītajam netiešajam "
                                           "efektam ir pretēja zīme nekā tiešajam efektam c′ "
                                           "({direct}): nekonsekventa mediācija pie šīm W "
                                           "vērtībām (supresija; MacKinnon, Krull & Lockwood, "
                                           "2000).",
        "interp.not_causal": "Tās ir nosacītas saistības analizētajos datos. “Efekts” ir šo "
                             "modeļa lielumu ierastais nosaukums (Hayes, 2022); tas nenozīmē, "
                             "ka viens mainīgais maina citu.",
        "interp.cross_sectional": "Šķērsgriezuma dati nevar noteikt laika secību vai cēlonisku "
                                  "mediāciju.",
        "warn.listwise": "Izslēgtas {excluded} no {total} rindām, jo trūka kāda modeļa mainīgā "
                         "vērtības (pilno gadījumu analīze); visi vienādojumi izmanto tos "
                         "pašus {n} pilnos gadījumus.",
        "warn.small_n": "Maza izlase (N = {n}): novērtējumi, bootstrap intervāli un diagnostika "
                        "var būt nestabili.",
        "warn.shapiro": "{outcome} vienādojums: atlikumu Šapiro–Vilka p = {p}; apskatiet Q–Q "
                        "grafiku (koeficientiem nav vajadzīgi normāli atlikumi; mazas izlases "
                        "t testiem ir).",
        "warn.bp": "{outcome} vienādojums: Breuša–Pagana p = {p} norāda uz nevienādu atlikumu "
                   "dispersiju; iespējams izmantot HC3 standartkļūdas.",
        "warn.cooks": "{outcome} vienādojums: {count} gadījumi ar Kuka attālumu virs 4/N; "
                      "pārskatiet tos, neizdzēsiet automātiski.",
        "warn.leverage": "{outcome} vienādojums: {count} gadījumi ar sviru virs 2p/N.",
        "warn.vif": "{outcome} vienādojums: VIF virs 5 locekļiem {terms}. Necentrētu mainīgo "
                    "reizinājumi pēc konstrukcijas ir kolineāri ar saviem komponentiem; tas "
                    "nemaina reizinājuma pārbaudi.",
        "warn.w_outside": "W = {value} ({where}) ir ārpus novērotajām {w} vērtībām ({low} līdz "
                          "{high}); nosacītais efekts tur ir ekstrapolācija.",
        "warn.boot_invalid": "{invalid} no {total} bootstrap atkārtotajām izlasēm bija "
                             "singulārs plāns, un tās netika izmantotas.",
        "warn.hc3": "HC3 standartkļūdas attiecas uz ceļiem un nosacītajiem efektiem; bootstrap "
                    "intervāli no tām nav atkarīgi; modeļa F un ΔR² pārbaudes ir klasiskās OLS "
                    "pārbaudes.",
        "warn.cross_sectional": "Šķērsgriezuma dati nevar noteikt laika secību: netiešais ceļš "
                                "ir nosacītu saistību kopums, nevis cēloniskas mediācijas "
                                "pierādījums.",
        "warn.effect_word": "“Efekts” ir šo modeļa lielumu ierastais nosaukums (Hayes, 2022); "
                            "šeit tās ir nosacītas saistības.",
        "warn.no_screening": "Mediatorus noteica pētnieks, nevis atlasīja pēc p vērtībām; "
                             "netiešajam efektam nav vajadzīgs nozīmīgs kopējais efekts "
                             "(Hayes, 2022).",
        "warn.interaction": "Mijiedarbība rāda, ka saistība šajos datos atšķiras pie dažādām W "
                            "vērtībām; tā nerāda, kāpēc.",
        "warn.binary_x": "X ir divas vērtības; pilnībā standartizēts netiešais efekts nav "
                         "definēts, tiek norādīts daļēji standartizētais (a × b / Y SD).",
        "warn.excluded_few": "Izslēgti tikai {count} gadījumi; analizēto un izslēgto gadījumu "
                             "salīdzinājums nav jēgpilns.",
        "warn.excluded_compare": "Analizēto un izslēgto gadījumu salīdzinājums ir aprakstošs; "
                                 "tas nevar parādīt, vai vērtības trūkst nejauši.",
        "jn.none": "Neviena Džonsona–Neimana vērtība nav novērotajā W diapazonā: nosacītais "
                   "efekts visā diapazonā ir {state} pie p < {alpha}.",
        "jn.state.significant": "atšķirīgs no nulles",
        "jn.state.not_significant": "neatšķiras no nulles",
        "sensitivity.note": "Simulēts ar to pašu modeli un N: X, W un kovariātu rindas tiek "
                            "atkārtoti izlasītas no datiem, pārējie koeficienti un atlikumu "
                            "dispersijas ir izlases novērtējumi, un galvenajam lielumam ir "
                            "pieņemtās standartizētās vērtības. {test} {replications} "
                            "atkārtojumi, sākumvērtība {seed}. Tā nav ‘novērotā jauda’, un tā "
                            "neko nesaka par to, vai iepriekš minētais rezultāts ir patiess.",
        "sensitivity.test.t": "Atklāts: divpusējs p < {alpha} reizinājuma loceklim.",
        "sensitivity.test.mc": "Atklāts: galvenā koeficientu reizinājuma 95% Monte Karlo "
                               "intervāls (2000 izlozes) neietver nulli.",
        "sensitivity.focal.interaction": "Mijiedarbība {product}",
        "sensitivity.focal.indirect": "Netiešais efekts caur {m} (a un b ceļi pie pieņemtās "
                                      "vērtības)",
        "sensitivity.focal.index7": "Moderētās mediācijas indekss caur {m} (X × W → {m} pie "
                                    "pieņemtās vērtības)",
        "sensitivity.focal.index14": "Moderētās mediācijas indekss caur {m} ({m} × W → Y pie "
                                     "pieņemtās vērtības)",
    },
    "ru": {
        "report.header": "Отчёт в стиле APA 7 (требует проверки исследователем)",
        "report.interpretation": "Интерпретация:",
        "report.notes": "Примечания:",
        "model.1": "Модель 1: модерация (W модерирует X → Y)",
        "model.4": "Модель 4: медиация (X → M → Y)",
        "model.7": "Модель 7: W модерирует X → M (модерируемая медиация первого этапа)",
        "model.14": "Модель 14: W модерирует M → Y (модерируемая медиация второго этапа)",
        "methods": "Структура соответствует модели {model} PROCESS (Hayes, 2022); рассчитано "
                   "этой программой, а не макросом PROCESS. Каждое уравнение — регрессия "
                   "методом наименьших квадратов (OLS) по {n} полным случаям (построчное "
                   "исключение {excluded} из {total} строк){covariates}. {se}",
        "methods.covariates": ", с ковариатами {names} в каждом уравнении",
        "methods.se.ols": "Стандартные ошибки путей — классические ошибки OLS; p-значения и "
                          "95% интервалы используют t-распределение.",
        "methods.se.hc3": "Стандартные ошибки путей — устойчивые к гетероскедастичности ошибки "
                          "HC3; p-значения и 95% интервалы используют t-распределение.",
        "methods.boot": "Косвенные эффекты проверены {level} процентильным бутстреп-интервалом "
                        "по {resamples} повторным выборкам полных случаев (зерно {seed}; "
                        "пригодных {valid}); p-значение для них не вычисляется.",
        "methods.center": "Переменные, образующие произведения ({names}), центрированы по "
                          "среднему до построения произведений.",
        "methods.nocenter": "Ни одна переменная не центрирована.",
        "methods.w_values": "Условные эффекты оценены при W = среднее − 1 SD, среднее и "
                            "среднее + 1 SD и при 16-м, 50-м и 84-м процентилях W (линейная "
                            "интерполяция, тип 7 по Hyndman–Fan) в анализируемой выборке.",
        "methods.w_binary": "В анализируемой выборке у W два значения; условные эффекты "
                            "оценены при обоих.",
        "methods.jn": "Метод Джонсона–Неймана: значения W, при которых для условного эффекта X "
                      "p = {alpha} точно; найдены в замкнутой форме по ковариационной матрице "
                      "коэффициентов.",
        "q.a": "Путь a: X → {m}",
        "q.b": "Путь b: {m} → Y",
        "q.direct": "Прямой эффект c′: X → Y (с M в модели)",
        "q.total": "Общий эффект c: X → Y (без M)",
        "q.indirect": "Косвенный эффект через {m} (a × b)",
        "q.indirect_total": "Общий косвенный эффект",
        "q.indirect_std": "Полностью стандартизованный косвенный эффект через {m}",
        "q.indirect_std_total": "Полностью стандартизованный общий косвенный эффект",
        "q.indirect_pstd": "Частично стандартизованный косвенный эффект через {m}",
        "q.indirect_pstd_total": "Частично стандартизованный общий косвенный эффект",
        "q.interaction": "Взаимодействие {product}",
        "q.delta_r2": "ΔR² для {product} (уравнение {outcome})",
        "q.f2": "f² Коэна для {product} (уравнение {outcome})",
        "q.cond": "Условный эффект {focal} на {outcome} при W = {w} ({where})",
        "q.cond_indirect": "Условный косвенный эффект через {m} при W = {w} ({where})",
        "q.index": "Индекс модерируемой медиации через {m}",
        "q.r2": "R² уравнения {outcome}",
        "w.minus": "среднее − 1 SD",
        "w.mean": "среднее",
        "w.plus": "среднее + 1 SD",
        "w.p16": "16-й процентиль",
        "w.p50": "50-й процентиль",
        "w.p84": "84-й процентиль",
        "w.low": "меньшее значение",
        "w.high": "большее значение",
        "w.chosen": "выбрано исследователем",
        "table.paths": "Модель {model}: коэффициенты всех уравнений",
        "table.paths.columns": ("Уравнение", "Член", "b", "SE", "t", "p", "95% ДИ", "β", "VIF"),
        "table.fit": "Модель {model}: согласие каждого уравнения",
        "table.fit.columns": ("Уравнение", "N", "R²", "Скорректированный R²", "F", "сс", "p"),
        "table.indirect": "Модель {model}: косвенные эффекты (процентильный бутстреп)",
        "table.indirect.columns": ("Путь", "Эффект", "Бутстреп SE", "95% ДИ"),
        "table.effects": "Модель {model}: прямой и общий эффекты",
        "table.effects.columns": ("Эффект", "b", "SE", "t", "p", "95% ДИ"),
        "table.interaction": "Модель {model}: проверка взаимодействия",
        "table.interaction.columns": ("Произведение", "Уравнение", "ΔR²", "F", "сс", "p", "f²"),
        "table.conditional": "Модель {model}: условные эффекты {focal} при значениях W",
        "table.conditional.columns": ("W", "Где", "Эффект", "SE", "t", "p", "95% ДИ"),
        "table.cond_indirect": "Модель {model}: условные косвенные эффекты (процентильный "
                               "бутстреп)",
        "table.cond_indirect.columns": ("Медиатор", "W", "Где", "Эффект", "Бутстреп SE",
                                        "95% ДИ"),
        "table.index": "Модель {model}: индекс модерируемой медиации (процентильный бутстреп)",
        "table.index.columns": ("Медиатор", "Индекс", "Бутстреп SE", "95% ДИ"),
        "table.jn": "Модель 1: значения W по Джонсону–Нейману",
        "table.jn.columns": ("W", "Доля выборки ниже", "Доля выборки выше", "Эффект", "SE",
                             "p"),
        "table.diagnostics": "Модель {model}: диагностика остатков каждого уравнения",
        "table.diagnostics.columns": ("Уравнение", "p Шапиро–Уилка", "p Бройша–Пагана",
                                      "Макс. D Кука", "D Кука > 4/N", "Макс. рычаг",
                                      "Рычаг > 2p/N", "Макс. VIF"),
        "table.missing": "Пропущенные данные (построчное исключение)",
        "table.missing.columns": ("Переменная", "Пропущено", "Пропущено, %"),
        "table.excluded": "Исключённые случаи в сравнении с проанализированными (описательно)",
        "table.excluded.columns": ("Переменная", "Проанализировано: n",
                                   "Проанализировано: M (SD)", "Исключено: n со значением",
                                   "Исключено: M (SD)", "SMD"),
        "table.sensitivity": "Симуляция чувствительности методом Монте-Карло (принятые "
                             "значения в популяции; не результат по этим данным)",
        "table.sensitivity.columns": ("Основная величина", "Принятое стандартизованное "
                                      "значение", "N", "Повторения", "Обнаружено (мощность)",
                                      "SE Монте-Карло"),
        "cell.constant": "Константа",
        "cell.not_defined": "не определено",
        "cell.na": "—",
        "cell.total_eq": "{outcome} (общий эффект: только X и ковариаты)",
        "summary.n": "N = {n} полных случаев из {total} (построчное исключение).",
        "summary.indirect": "Косвенный эффект через {m}: {est}, 95% бутстреп-ДИ [{low}, {high}].",
        "summary.interaction": "Взаимодействие {product}: b = {est}, 95% ДИ [{low}, {high}], "
                               "{p}; ΔR² = {dr2}.",
        "summary.index": "Индекс модерируемой медиации через {m}: {est}, 95% бутстреп-ДИ "
                         "[{low}, {high}].",
        "interp.indirect.excludes": "Через {m}: 95% бутстреп-интервал косвенного эффекта "
                                    "({est}) не включает ноль, то есть эти данные совместимы с "
                                    "ненулевым косвенным путём в модели, заданной "
                                    "исследователем.",
        "interp.indirect.includes": "Через {m}: 95% бутстреп-интервал косвенного эффекта "
                                    "({est}) включает ноль, то есть эти данные не дают "
                                    "свидетельств косвенного пути; это не доказывает, что его "
                                    "нет.",
        "interp.interaction.yes": "Связь {focal} с {outcome} в этих данных различается при "
                                  "разных значениях W (взаимодействие {p}); см. условные "
                                  "эффекты.",
        "interp.interaction.no": "Эти данные не дают свидетельств, что связь {focal} с "
                                 "{outcome} различается при разных значениях W "
                                 "(взаимодействие {p}); это не доказывает, что она одинакова.",
        "interp.index.excludes": "Через {m}: 95% бутстреп-интервал индекса модерируемой "
                                 "медиации ({est}) не включает ноль: условные косвенные эффекты "
                                 "в этих данных различаются при разных W.",
        "interp.index.includes": "Через {m}: 95% бутстреп-интервал индекса модерируемой "
                                 "медиации ({est}) включает ноль: эти данные не дают "
                                 "свидетельств, что косвенный эффект зависит от W.",
        "interp.inconsistent.both": "Через {m}: косвенный эффект ({ab}) имеет знак, "
                                    "противоположный прямому эффекту c′ ({direct}) и общему "
                                    "эффекту c ({total}): несогласованная медиация (супрессия; "
                                    "MacKinnon, Krull & Lockwood, 2000).",
        "interp.inconsistent.direct": "Через {m}: косвенный эффект ({ab}) имеет знак, "
                                      "противоположный прямому эффекту c′ ({direct}): "
                                      "несогласованная медиация (супрессия; MacKinnon, Krull & "
                                      "Lockwood, 2000).",
        "interp.inconsistent.total": "Через {m}: косвенный эффект ({ab}) имеет знак, "
                                     "противоположный общему эффекту c ({total}): "
                                     "несогласованная медиация (супрессия; MacKinnon, Krull & "
                                     "Lockwood, 2000).",
        "interp.inconsistent.conditional": "Через {m} при W = {values}: условный косвенный "
                                           "эффект имеет знак, противоположный прямому эффекту c′ "
                                           "({direct}): несогласованная медиация при этих "
                                           "значениях W (супрессия; MacKinnon, Krull & Lockwood, "
                                           "2000).",
        "interp.not_causal": "Это условные связи в проанализированных данных. «Эффект» — "
                             "принятое название этих величин модели (Hayes, 2022); оно не "
                             "означает, что одна переменная изменяет другую.",
        "interp.cross_sectional": "Одномоментные (поперечные) данные не позволяют установить "
                                  "временной порядок или причинную медиацию.",
        "warn.listwise": "Исключено {excluded} из {total} строк, так как отсутствовало значение "
                         "переменной модели (построчное исключение); все уравнения используют "
                         "одни и те же {n} полных случаев.",
        "warn.small_n": "Малая выборка (N = {n}): оценки, бутстреп-интервалы и диагностика "
                        "могут быть неустойчивы.",
        "warn.shapiro": "Уравнение {outcome}: p Шапиро–Уилка для остатков = {p}; посмотрите "
                        "Q–Q-график (коэффициентам не нужны нормальные остатки, t-критериям в "
                        "малых выборках нужны).",
        "warn.bp": "Уравнение {outcome}: p Бройша–Пагана = {p} указывает на непостоянную "
                   "дисперсию остатков; можно использовать стандартные ошибки HC3.",
        "warn.cooks": "Уравнение {outcome}: случаев с расстоянием Кука выше 4/N: {count}; "
                      "проверьте их, не удаляйте автоматически.",
        "warn.leverage": "Уравнение {outcome}: случаев с рычагом выше 2p/N: {count}.",
        "warn.vif": "Уравнение {outcome}: VIF выше 5 для {terms}. Произведения "
                    "нецентрированных переменных по построению коллинеарны своим компонентам; "
                    "это не меняет проверку произведения.",
        "warn.w_outside": "W = {value} ({where}) лежит вне наблюдаемых значений {w} (от {low} "
                          "до {high}); условный эффект там — экстраполяция.",
        "warn.boot_invalid": "{invalid} из {total} бутстреп-выборок имели вырожденный план и "
                             "были исключены.",
        "warn.hc3": "Ошибки HC3 относятся к путям и условным эффектам; бутстреп-интервалы от "
                    "них не зависят; F модели и проверки ΔR² — классические проверки OLS.",
        "warn.cross_sectional": "Одномоментные данные не позволяют установить временной "
                                "порядок: косвенный путь — это набор условных связей, а не "
                                "свидетельство причинной медиации.",
        "warn.effect_word": "«Эффект» — принятое название этих величин модели (Hayes, 2022); "
                            "здесь это условные связи.",
        "warn.no_screening": "Медиаторы заданы исследователем, а не отобраны по p-значениям; "
                             "для косвенного эффекта не требуется значимый общий эффект "
                             "(Hayes, 2022).",
        "warn.interaction": "Взаимодействие показывает, что связь в этих данных различается "
                            "при разных значениях W; оно не показывает почему.",
        "warn.binary_x": "У X два значения; полностью стандартизованный косвенный эффект не "
                         "определён, приводится частично стандартизованный (a × b / SD Y).",
        "warn.excluded_few": "Исключено только {count} случаев; сравнение проанализированных и "
                             "исключённых случаев не имеет смысла.",
        "warn.excluded_compare": "Сравнение проанализированных и исключённых случаев "
                                 "описательное; оно не может показать, случайны ли пропуски.",
        "jn.none": "Ни одно значение Джонсона–Неймана не лежит в наблюдаемом диапазоне W: "
                   "условный эффект во всём диапазоне {state} при p < {alpha}.",
        "jn.state.significant": "отличается от нуля",
        "jn.state.not_significant": "не отличается от нуля",
        "sensitivity.note": "Смоделировано с той же моделью и N: строки X, W и ковариат "
                            "извлекаются с возвращением из данных, остальные коэффициенты и "
                            "дисперсии остатков — выборочные оценки, а основная величина "
                            "принимает заданные стандартизованные значения. {test} "
                            "{replications} повторений, зерно {seed}. Это не «наблюдаемая "
                            "мощность», и она ничего не говорит о том, верен ли результат "
                            "выше.",
        "sensitivity.test.t": "Обнаружено: двусторонний p < {alpha} для члена-произведения.",
        "sensitivity.test.mc": "Обнаружено: 95% интервал Монте-Карло (2000 розыгрышей) для "
                               "основного произведения коэффициентов не включает ноль.",
        "sensitivity.focal.interaction": "Взаимодействие {product}",
        "sensitivity.focal.indirect": "Косвенный эффект через {m} (пути a и b при принятом "
                                      "значении)",
        "sensitivity.focal.index7": "Индекс модерируемой медиации через {m} (X × W → {m} при "
                                    "принятом значении)",
        "sensitivity.focal.index14": "Индекс модерируемой медиации через {m} ({m} × W → Y при "
                                     "принятом значении)",
    },
}

LANGUAGES = ("en", "lv", "ru")


def t(language: str, key: str, **values) -> str:
    """The text of ``key`` in ``language`` (English when the language or key is missing)."""
    table = TEXT.get(language if language in TEXT else "en", TEXT["en"])
    text = table.get(key, TEXT["en"][key])
    return text.format(**values) if values else text


def columns(language: str, key: str) -> tuple[str, ...]:
    """Column headers of a table (a tuple of texts)."""
    table = TEXT.get(language if language in TEXT else "en", TEXT["en"])
    return tuple(table.get(key, TEXT["en"][key]))
