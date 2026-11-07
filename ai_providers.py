"""AI provider adapters, bring-your-own-key (Stage 35, #43).

OpenAI (Responses API), Anthropic (Messages API) and Google Gemini
(generateContent), called directly over HTTPS with the researcher's own key
from the OS credential store (``secret_store``). Model menus are never
hard-coded: ``list_models`` asks the provider which models the key can use
(cached for a day; a model ID can also be typed in). The exact model ID that
answered is returned with every reply, for the project's audit record.

Requests are made only when the researcher asks; nothing is sent because a
project was opened. Every call has a timeout. 429 and 5xx are retried with
back-off (honouring Retry-After) and can be cancelled between attempts. A
daily token budget is enforced locally. Errors never contain the key.
Streaming is not used yet: replies arrive whole.
"""

from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

TIMEOUT = 30
RETRIES = 3
MODEL_CACHE_SECONDS = 24 * 3600
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    host: str
    privacy_url: str


PROVIDERS = {
    "openai": Provider("openai", "OpenAI", "api.openai.com",
                       "https://openai.com/policies/api-data-usage-policies"),
    "anthropic": Provider("anthropic", "Anthropic", "api.anthropic.com",
                          "https://www.anthropic.com/legal/commercial-terms"),
    "gemini": Provider("gemini", "Google Gemini", "generativelanguage.googleapis.com",
                       "https://ai.google.dev/gemini-api/terms"),
}
# Listed models that cannot answer text (embeddings, images, audio, moderation).
NOT_TEXT = ("embedding", "whisper", "tts", "dall-e", "moderation", "transcribe", "image",
            "audio", "realtime", "search", "computer-use", "aqa")


class ProviderError(Exception):
    """``reason`` is a stable key for the interface; the key is never in it."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Model:
    id: str
    name: str = ""


@dataclass(frozen=True)
class Reply:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""
    raw_usage: dict = field(default_factory=dict)


# ------------------------------------------------------------------- HTTP

def _request(provider: str, method: str, path: str, key: str, *, body: dict | None = None,
             cancel: threading.Event | None = None, timeout: float = TIMEOUT,
             opener=None, base: str | None = None) -> dict:
    info = PROVIDERS[provider]
    url = (base or f"https://{info.host}") + path
    parts = urlsplit(url)
    if base is None and (parts.scheme != "https" or parts.hostname != info.host):
        raise ProviderError("bad_url", "requests go only to the provider's own HTTPS host")
    headers = {"Content-Type": "application/json", "User-Agent": "StatisticalResearchAssistant"}
    if provider == "openai":
        headers["Authorization"] = f"Bearer {key}"
    elif provider == "anthropic":
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["x-goog-api-key"] = key      # a header, never in the URL (logs, proxies)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    opener = opener or urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    for attempt in range(RETRIES + 1):
        if cancel is not None and cancel.is_set():
            raise ProviderError("cancelled")
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProviderError("too_large", "the reply is too large")
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as error:
            status = error.code
            if status in (401, 403):
                raise ProviderError("bad_key", f"HTTP {status}") from None
            if status == 404:
                raise ProviderError("not_found", "HTTP 404 (model or endpoint)") from None
            if (status == 429 or status >= 500) and attempt < RETRIES:
                wait = _retry_after(error.headers.get("Retry-After"), attempt)
                if cancel is not None and cancel.wait(wait):
                    raise ProviderError("cancelled") from None
                if cancel is None:
                    time.sleep(wait)
                continue
            raise ProviderError("rate_limited" if status == 429 else "unavailable",
                                f"HTTP {status}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if attempt < RETRIES and not isinstance(error, ssl.SSLError):
                wait = _retry_after(None, attempt)
                if cancel is not None and cancel.wait(wait):
                    raise ProviderError("cancelled") from None
                if cancel is None:
                    time.sleep(wait)
                continue
            raise ProviderError("offline", type(error).__name__) from None
        except ValueError as error:
            raise ProviderError("malformed", "the reply is not JSON") from error
    raise ProviderError("unavailable")


def _retry_after(value, attempt: int) -> float:
    try:
        return min(30.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return min(30.0, 0.5 * (2 ** attempt))


# ----------------------------------------------------------------- models

def _parse_models(provider: str, payload: dict) -> list[Model]:
    found = []
    if provider == "gemini":
        for entry in payload.get("models", []) or []:
            if "generateContent" not in (entry.get("supportedGenerationMethods") or []):
                continue
            model_id = str(entry.get("name", "")).removeprefix("models/")
            found.append(Model(model_id, str(entry.get("displayName") or model_id)))
    else:
        for entry in payload.get("data", []) or []:
            model_id = str(entry.get("id", ""))
            found.append(Model(model_id, str(entry.get("display_name") or model_id)))
    text_models = [m for m in found if m.id and not any(word in m.id.lower() for word in NOT_TEXT)]
    return sorted(text_models, key=lambda m: m.id)


def list_models(provider: str, key: str, *, cache: Path | None = None, refresh: bool = False,
                cancel=None, **http) -> list[Model]:
    """The text models this key can use (the provider's own list)."""
    if provider not in PROVIDERS:
        raise ProviderError("unknown_provider", provider)
    if cache is not None and not refresh:
        cached = _read_cache(cache).get(provider)
        if cached and time.time() - cached.get("at", 0) < MODEL_CACHE_SECONDS:
            return [Model(**m) for m in cached["models"]]
    path = {"openai": "/v1/models", "anthropic": "/v1/models?limit=1000",
            "gemini": "/v1beta/models?pageSize=1000"}[provider]
    models = _parse_models(provider, _request(provider, "GET", path, key, cancel=cancel, **http))
    if not models:
        raise ProviderError("no_models", "this key can use no text model")
    if cache is not None:
        values = _read_cache(cache)
        values[provider] = {"at": time.time(), "models": [m.__dict__ for m in models]}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(values, indent=1), encoding="utf-8")
    return models


def _read_cache(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def test_connection(provider: str, key: str, **http) -> int:
    """Number of text models the key can use; raises ProviderError otherwise."""
    return len(list_models(provider, key, refresh=True, **http))


# --------------------------------------------------------------- generate

def generate(provider: str, key: str, model: str, prompt: str, *, max_output_tokens: int = 800,
             budget: "Budget | None" = None, cancel=None, **http) -> Reply:
    """One reply to ``prompt``. Raises ProviderError; never retries a 4xx."""
    if not model or len(model) > 200 or any(ch.isspace() for ch in model):
        raise ProviderError("bad_model", "choose a model")
    if budget is not None:
        budget.check(len(prompt) // 3 + max_output_tokens)
    if provider == "openai":
        body = {"model": model, "input": prompt, "max_output_tokens": max_output_tokens}
        payload = _request(provider, "POST", "/v1/responses", key, body=body, cancel=cancel, **http)
        text = payload.get("output_text") or "".join(
            part.get("text", "") for item in payload.get("output", []) or []
            for part in item.get("content", []) or [] if part.get("type") in ("output_text", "text"))
        usage = payload.get("usage") or {}
        reply = Reply(text, str(payload.get("model") or model), int(usage.get("input_tokens", 0)),
                      int(usage.get("output_tokens", 0)), provider, usage)
    elif provider == "anthropic":
        body = {"model": model, "max_tokens": max_output_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        payload = _request(provider, "POST", "/v1/messages", key, body=body, cancel=cancel, **http)
        text = "".join(part.get("text", "") for part in payload.get("content", []) or []
                       if part.get("type") == "text")
        usage = payload.get("usage") or {}
        reply = Reply(text, str(payload.get("model") or model), int(usage.get("input_tokens", 0)),
                      int(usage.get("output_tokens", 0)), provider, usage)
    elif provider == "gemini":
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_output_tokens}}
        path = f"/v1beta/models/{quote(model, safe='-._')}:generateContent"
        payload = _request(provider, "POST", path, key, body=body, cancel=cancel, **http)
        candidates = payload.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
        text = "".join(part.get("text", "") for part in parts)
        usage = payload.get("usageMetadata") or {}
        reply = Reply(text, str(payload.get("modelVersion") or model),
                      int(usage.get("promptTokenCount", 0)), int(usage.get("candidatesTokenCount", 0)),
                      provider, usage)
    else:
        raise ProviderError("unknown_provider", provider)
    if not reply.text.strip():
        raise ProviderError("empty", "the provider returned no text")
    if budget is not None:
        budget.spend(reply.input_tokens + reply.output_tokens)
    return reply


class Budget:
    """A daily token limit kept on this computer (``0`` = no limit)."""

    def __init__(self, path: Path, daily_tokens: int):
        self.path, self.daily_tokens = Path(path), int(daily_tokens)

    def _today(self) -> dict:
        value = _read_cache(self.path)
        if value.get("day") != date.today().isoformat():
            value = {"day": date.today().isoformat(), "tokens": 0}
        return value

    def used(self) -> int:
        return int(self._today().get("tokens", 0))

    def check(self, estimate: int) -> None:
        if self.daily_tokens and self.used() + estimate > self.daily_tokens:
            raise ProviderError("budget", f"{self.used()} of {self.daily_tokens} tokens used today")

    def spend(self, tokens: int) -> None:
        value = self._today()
        value["tokens"] = int(value.get("tokens", 0)) + max(0, int(tokens))
        value["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value), encoding="utf-8")
