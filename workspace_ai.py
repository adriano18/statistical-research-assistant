"""Settings → AI providers (Stage 35, #43).

AI is off until the researcher connects a provider with their own key.
- **Where the key is kept:** the operating system's credential store (``secret_store``), never a project, a backup, the preferences, a log or a report.
- **When anything is sent:** only on an explicit action. **Test connection** sends just the key, to list the models the key can use. Nothing is sent when a project is opened.
- **Choosing a model:** the list comes from the provider (``ai_providers``), or a model ID can be typed in.
- **Spending:** a daily token limit is kept on this computer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import flet as ft

import ai_providers as ap
import secret_store
import workspace_components as wc
import workspace_tokens as tk

TEXT = {
    "en": {"title": "AI providers", "body": "AI is off until you connect a provider with your own API key. The key is kept in Windows Credential Manager, never in projects, backups, logs or reports. Nothing is sent when a project opens; every request is shown to you first.",
           "provider": "Provider", "key": "API key", "save_key": "Save key", "remove_key": "Remove key",
           "stored": "A key for {provider} is stored in the credential store.", "no_key": "No key stored for {provider}.",
           "test": "Test connection", "testing": "Contacting {provider}…", "connected": "Connected: {n} text models available.",
           "model": "Model", "manual": "Or type a model ID", "use_model": "Use this model", "model_set": "Model in use: {model}",
           "budget": "Daily token limit (0 = none)", "privacy": "{provider}: data processing terms",
           "no_store": "This computer offers no protected credential store, so no key can be kept.",
           "error.bad_key": "The provider refused the key.", "error.offline": "The provider could not be reached.",
           "error.rate_limited": "The provider is busy (rate limit). Try again later.", "error.unavailable": "The provider did not answer.",
           "error.no_models": "This key can use no text model.", "error.cancelled": "Cancelled.",
           "error.budget": "Today's token limit is reached.", "error.unknown": "The request failed.",
           "invalid_key": "This does not look like an API key.", "invalid_budget": "Enter a whole number of tokens."},
    "lv": {"title": "AI pakalpojumu sniedzēji", "body": "AI ir izslēgts, līdz pievienojat pakalpojumu sniedzēju ar savu API atslēgu. Atslēga glabājas Windows akreditācijas datu pārvaldniekā, nekad projektos, rezerves kopijās, žurnālos vai atskaitēs. Atverot projektu, nekas netiek nosūtīts; katru pieprasījumu vispirms redzat jūs.",
           "provider": "Pakalpojumu sniedzējs", "key": "API atslēga", "save_key": "Saglabāt atslēgu", "remove_key": "Noņemt atslēgu",
           "stored": "{provider} atslēga glabājas akreditācijas datu krātuvē.", "no_key": "{provider} atslēga nav saglabāta.",
           "test": "Pārbaudīt savienojumu", "testing": "Sazinās ar {provider}…", "connected": "Savienots: pieejami {n} teksta modeļi.",
           "model": "Modelis", "manual": "Vai ierakstiet modeļa ID", "use_model": "Izmantot šo modeli", "model_set": "Izmantotais modelis: {model}",
           "budget": "Dienas tokenu limits (0 = nav)", "privacy": "{provider}: datu apstrādes noteikumi",
           "no_store": "Šajā datorā nav aizsargātas akreditācijas datu krātuves, tāpēc atslēgu nevar saglabāt.",
           "error.bad_key": "Pakalpojumu sniedzējs noraidīja atslēgu.", "error.offline": "Pakalpojumu sniedzējs nav sasniedzams.",
           "error.rate_limited": "Pakalpojumu sniedzējs ir aizņemts (pieprasījumu limits). Mēģiniet vēlāk.", "error.unavailable": "Pakalpojumu sniedzējs neatbildēja.",
           "error.no_models": "Ar šo atslēgu nav pieejams neviens teksta modelis.", "error.cancelled": "Atcelts.",
           "error.budget": "Šodienas tokenu limits ir sasniegts.", "error.unknown": "Pieprasījums neizdevās.",
           "invalid_key": "Tā neizskatās pēc API atslēgas.", "invalid_budget": "Ievadiet veselu tokenu skaitu."},
    "ru": {"title": "Провайдеры ИИ", "body": "ИИ выключен, пока вы не подключите провайдера со своим API-ключом. Ключ хранится в диспетчере учётных данных Windows и никогда — в проектах, резервных копиях, журналах или отчётах. При открытии проекта ничего не отправляется; каждый запрос вы сначала видите сами.",
           "provider": "Провайдер", "key": "API-ключ", "save_key": "Сохранить ключ", "remove_key": "Удалить ключ",
           "stored": "Ключ для {provider} хранится в хранилище учётных данных.", "no_key": "Ключ для {provider} не сохранён.",
           "test": "Проверить подключение", "testing": "Связь с {provider}…", "connected": "Подключено: доступно текстовых моделей — {n}.",
           "model": "Модель", "manual": "Или введите ID модели", "use_model": "Использовать эту модель", "model_set": "Используемая модель: {model}",
           "budget": "Дневной лимит токенов (0 = без лимита)", "privacy": "{provider}: условия обработки данных",
           "no_store": "На этом компьютере нет защищённого хранилища учётных данных, поэтому ключ сохранить нельзя.",
           "error.bad_key": "Провайдер отклонил ключ.", "error.offline": "Провайдер недоступен.",
           "error.rate_limited": "Провайдер перегружен (лимит запросов). Повторите позже.", "error.unavailable": "Провайдер не ответил.",
           "error.no_models": "С этим ключом недоступна ни одна текстовая модель.", "error.cancelled": "Отменено.",
           "error.budget": "Дневной лимит токенов исчерпан.", "error.unknown": "Запрос не удался.",
           "invalid_key": "Это не похоже на API-ключ.", "invalid_budget": "Введите целое число токенов."},
}


def t(language: str, key: str, **values) -> str:
    return TEXT.get(language, TEXT["en"]).get(key, TEXT["en"].get(key, key)).format(**values)


# The settings live in ``ai_providers`` so that the assistant's availability
# check (``ai_context.readiness``) reads them without the interface.
settings_path, load_settings, save_settings = ap.settings_path, ap.load_settings, ap.save_settings


class AiProvidersCard:
    def __init__(self, app):
        self.app = app
        self.message: tuple[str, str] | None = None
        self.models: list[ap.Model] = []
        self.key_draft = ""
        self.manual_model = ""

    @property
    def root(self) -> Path:
        return self.app.project_root.parent

    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        language = app.session.language
        settings = load_settings(self.root)
        provider = settings["provider"]
        name = ap.PROVIDERS[provider].name
        rows: list[ft.Control] = [wc.caption(ui, t(language, "body"))]
        rows.append(wc.dropdown(ui, t(language, "provider"),
                                [(k, p.name) for k, p in ap.PROVIDERS.items()], provider,
                                on_select=self._provider, data="ai-provider"))
        if not secret_store.available():
            rows.append(wc.notice(ui, t(language, "no_store"), "warning", data="ai-no-store"))
        else:
            stored = secret_store.has_key(provider)
            rows.append(wc.text(ui, t(language, "stored" if stored else "no_key", provider=name),
                                data="ai-key-state"))
            key_field = ft.TextField(label=t(language, "key"), password=True, width=420,
                                     on_change=lambda e: setattr(self, "key_draft", e.control.value or ""),
                                     data="ai-key")
            rows.append(ft.Row([key_field,
                                wc.button(ui, t(language, "save_key"), self._save_key, data="ai-save-key"),
                                wc.button(ui, t(language, "remove_key"), self._remove_key,
                                          disabled=not stored, data="ai-remove-key")],
                               wrap=True, spacing=tk.SPACE_2))
            rows.append(wc.button(ui, t(language, "test"), self._test, disabled=not stored,
                                  icon=ft.Icons.WIFI_TETHERING, data="ai-test"))
        options = [(m.id, m.name or m.id) for m in self.models]
        if settings["model"] and settings["model"] not in {m.id for m in self.models}:
            options.insert(0, (settings["model"], settings["model"]))
        if options:
            rows.append(wc.dropdown(ui, t(language, "model"), options, settings["model"] or None,
                                    on_select=self._choose_model, width=420, data="ai-model"))
        rows.append(ft.Row([
            wc.text_field(ui, t(language, "manual"), self.manual_model, width=320,
                          on_change=lambda e: setattr(self, "manual_model", e.control.value or ""),
                          data="ai-manual-model"),
            wc.button(ui, t(language, "use_model"), self._use_manual, data="ai-use-model")],
            wrap=True, spacing=tk.SPACE_2))
        if settings["model"]:
            rows.append(wc.caption(ui, t(language, "model_set", model=settings["model"]),
                                   data="ai-model-set"))
        rows.append(wc.text_field(ui, t(language, "budget"), str(settings["daily_tokens"]), width=260,
                                  on_change=self._budget, data="ai-budget"))
        rows.append(wc.button(ui, t(language, "privacy", provider=name),
                              lambda e: app.page.launch_url(ap.PROVIDERS[provider].privacy_url),
                              icon=ft.Icons.OPEN_IN_NEW, data="ai-privacy"))
        if self.message:
            rows.append(wc.notice(ui, self.message[0], self.message[1], data="ai-message"))
        return wc.card(ui, rows, title=t(language, "title"), data="settings-ai-providers")

    # ------------------------------------------------------------- actions
    def _update(self, **changes) -> None:
        settings = load_settings(self.root)
        settings.update(changes)
        save_settings(self.root, settings)

    def _provider(self, e):
        self._update(provider=e.control.value, model="")
        self.models, self.message = [], None
        self.app.render()

    def _save_key(self, e=None):
        language = self.app.session.language
        try:
            secret_store.set_key(load_settings(self.root)["provider"], self.key_draft)
            self.message = None
        except ValueError:
            self.message = (t(language, "invalid_key"), "danger")
        except (secret_store.SecretStoreUnavailable, OSError):
            self.message = (t(language, "no_store"), "danger")
        self.key_draft = ""
        self.app.render()

    def _remove_key(self, e=None):
        try:
            secret_store.remove_key(load_settings(self.root)["provider"])
        except (secret_store.SecretStoreUnavailable, OSError):
            pass
        self.models, self.message = [], None
        self.app.render()

    async def _test(self, e=None):
        language = self.app.session.language
        provider = load_settings(self.root)["provider"]
        self.message = (t(language, "testing", provider=ap.PROVIDERS[provider].name), "info")
        self.app.render()
        try:
            key = secret_store.get_key(provider) or ""
            self.models = await asyncio.to_thread(ap.list_models, provider, key,
                                                  cache=self.root / "ai" / "models.json", refresh=True)
            self.message = (t(language, "connected", n=len(self.models)), "success")
        except ap.ProviderError as error:
            key = f"error.{error.reason}"
            self.message = (t(language, key if key in TEXT["en"] else "error.unknown"), "danger")
        except (secret_store.SecretStoreUnavailable, OSError):
            self.message = (t(language, "no_store"), "danger")
        self.app.render()

    def _choose_model(self, e):
        self._update(model=e.control.value or "")
        self.app.render()

    def _use_manual(self, e=None):
        model = self.manual_model.strip()
        if model and len(model) <= 200 and not any(ch.isspace() for ch in model):
            self._update(model=model)
        self.app.render()

    def _budget(self, e):
        try:
            value = int(e.control.value or 0)
        except ValueError:
            return
        if value >= 0:
            self._update(daily_tokens=value)
