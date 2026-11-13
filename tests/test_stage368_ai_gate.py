"""Stage 36.8 release gate, issue #62 Part 9 — AI release safety.

One test class per gate (``Gate01…`` to ``Gate10…``) and three supporting
classes: the application without AI, the default-off state of the packaged
build, and what public CI may run. ``docs/STAGE368_AI_GATE.md`` has the
table of gates, results and what was not tested.

Every test drives the real code — the Settings card, the assistant panel on
the Results page, ``ai_assist``, ``ai_context`` and ``ai_providers`` —
mostly through the workspace harness, where a researcher would click.

**The providers are faked in this process, at the http.client level**
(``FakeProviders``). ``ai_providers`` builds its real ``urllib`` opener, with
its real TLS context, headers and host check; only
``http.client.HTTPSConnection`` is replaced, by a connection whose socket is
a buffer in memory. Requests leave as real HTTP/1.1 bytes, which the fake
parses, and replies come back as real HTTP/1.1 bytes, which http.client
parses (chunked bodies, ``Retry-After``, cut-off bodies, timeouts). No
``base=`` test hook and no local server are used: the production URLs
(``https://api.openai.com/…`` and the others) are what is exercised.

**No test may touch the network** (``NetworkGuard``): a TCP connect, a DNS
lookup, ``socket.create_connection`` or a TLS handshake fails the test, also
when the code under test swallows the error.

Synthetic data and fake keys (``sk-test-…``) only. Where an existing test
already proves part of a gate, the class docstring names it and the part is
not repeated here.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import contextlib
from contextlib import closing
from dataclasses import dataclass
import http.client
import io
import json
import logging
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import sys
from tempfile import TemporaryDirectory
import threading
import time
import tomllib
import traceback
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.parse
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

import ai_assist  # noqa: E402
import ai_context  # noqa: E402
import ai_providers as ap  # noqa: E402
import secret_store  # noqa: E402
import startup_diagnostics  # noqa: E402
from workspace_harness import Workspace  # noqa: E402

KEY = "sk-test-gate-0123456789abcdef"
SENTINEL = "sk-test-SENTINEL-0000"
HOSTS = {"openai": "api.openai.com", "anthropic": "api.anthropic.com",
         "gemini": "generativelanguage.googleapis.com"}
PROVIDER_AT = {host: provider for provider, host in HOSTS.items()}
LIST_PATHS = {"openai": "/v1/models", "anthropic": "/v1/models", "gemini": "/v1beta/models"}
DEFAULT_MODEL = {"openai": "gpt-synth-alpha", "anthropic": "claude-synth-one",
                 "gemini": "gemini-synth-pro"}
AUTH_HEADER = {"openai": "authorization", "anthropic": "x-api-key", "gemini": "x-goog-api-key"}
AI_MODULES = ("ai_providers.py", "ai_assist.py", "ai_context.py", "workspace_ai.py",
              "workspace_assistant.py", "secret_store.py")
EVENT = SimpleNamespace(control=None, data=None)
HOLD_LIMIT = 20.0          # a held reply that is never released becomes a timeout


def generate_path(provider: str, model: str) -> str:
    return {"openai": "/v1/responses", "anthropic": "/v1/messages",
            "gemini": f"/v1beta/models/{model}:generateContent"}[provider]


# ======================================================== the fake providers
@dataclass
class Fault:
    """What the provider does with the next request (one request each).

    ``status`` an HTTP error (headers such as Retry-After); ``timeout`` no
    reply within the time limit; ``truncated`` a reply cut off mid-body;
    ``garbage`` a reply that is not HTTP (a broken proxy); ``refuse`` no
    connection at all; ``hold`` answer only after ``release`` is set (a
    provider that is still thinking); ``reply`` answer with ``text``;
    ``empty`` answer without any text (a reasoning model out of tokens)."""

    kind: str
    status: int = 0
    headers: tuple = ()
    body: object = None
    text: str | None = None
    release: threading.Event | None = None

    @classmethod
    def http(cls, status: int, *headers, body=None) -> "Fault":
        return cls("status", status, tuple(headers), body)


@dataclass
class Exchange:
    """One request exactly as it went over the (fake) wire."""

    provider: str
    host: str
    method: str
    target: str
    headers: dict
    body: bytes
    raw: bytes
    timeout: object
    tls_verified: bool

    @property
    def path(self) -> str:
        return urllib.parse.urlsplit(self.target).path

    @property
    def json(self):
        return json.loads(self.body) if self.body else None

    @property
    def text(self) -> str:
        """Everything the request carried: request line, headers and body."""
        return self.raw.decode("utf-8", "replace")

    @property
    def presented_key(self) -> str:
        value = self.headers.get(AUTH_HEADER[self.provider], "")
        return value.removeprefix("Bearer ") if self.provider == "openai" else value

    @property
    def model(self) -> str:
        if self.provider == "gemini":
            return urllib.parse.unquote(self.path.removeprefix("/v1beta/models/").split(":")[0])
        return (self.json or {}).get("model", "")

    @property
    def prompt(self) -> str:
        body = self.json or {}
        if self.provider == "openai":
            return body["input"]
        if self.provider == "anthropic":
            return body["messages"][0]["content"]
        return body["contents"][0]["parts"][0]["text"]

    @property
    def reply_limit(self) -> int:
        body = self.json or {}
        return {"openai": lambda: body["max_output_tokens"],
                "anthropic": lambda: body["max_tokens"],
                "gemini": lambda: body["generationConfig"]["maxOutputTokens"]}[self.provider]()


REASONS = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
           404: "Not Found", 429: "Too Many Requests", 500: "Internal Server Error",
           503: "Service Unavailable"}


def http_reply(status: int, payload, headers=(), *, chunked: bool = False) -> bytes:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    lines = [f"HTTP/1.1 {status} {REASONS.get(status, 'Status')}",
             "Content-Type: application/json", "Connection: close",
             *[f"{name}: {value}" for name, value in headers]]
    if chunked:
        lines.append("Transfer-Encoding: chunked")
        half = len(body) // 2
        data = b"".join(b"%x\r\n%s\r\n" % (len(part), part)
                        for part in (body[:half], body[half:]) if part) + b"0\r\n\r\n"
    else:
        lines.append(f"Content-Length: {len(body)}")
        data = body
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + data


# A chunked reply that announces 1024 bytes and stops after a few dozen.
TRUNCATED = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
             b"Transfer-Encoding: chunked\r\n\r\n400\r\n"
             b'{"id": "resp_synthetic", "output": [{"type": "message", "content": [{"type": ')


class TimedOutReply(io.BytesIO):
    """A reply that does not come in time: reading it times out, exactly as
    a socket with a timeout does."""

    def readline(self, *args):
        raise TimeoutError("The read operation timed out")

    def read(self, *args):
        raise TimeoutError("The read operation timed out")


def model_entry(model_id: str, name: str = "", methods=("generateContent",)) -> dict:
    return {"id": model_id, "name": name or model_id, "methods": list(methods)}


def default_catalog() -> dict:
    """Synthetic model lists, each with models that cannot answer text."""
    return {
        "openai": [model_entry(m) for m in (
            "gpt-synth-alpha", "gpt-synth-beta", "synth-deep-tools", "text-embedding-synth",
            "whisper-synth", "tts-synth", "dall-e-synth", "omni-moderation-synth",
            "gpt-synth-realtime", "gpt-synth-audio", "gpt-synth-transcribe", "gpt-image-synth",
            "gpt-synth-search", "computer-use-synth")],
        "anthropic": [model_entry("claude-synth-one", "Claude Synth One"),
                      model_entry("claude-synth-two", "Claude Synth Two")],
        "gemini": [model_entry("gemini-synth-pro", "Gemini Synth Pro",
                               ("generateContent", "countTokens")),
                   model_entry("gemini-synth-embedding", methods=("embedContent",)),
                   model_entry("aqa-synth", methods=("generateAnswer",)),
                   model_entry("imagen-synth", methods=("predict",))],
    }


class MemorySocket:
    """The socket of a fake connection: what is sent is kept; the reply is
    made when http.client starts reading it."""

    def __init__(self, transport: "FakeProviders", connection, host: str):
        self.transport, self.connection, self.host = transport, connection, host
        self.sent = bytearray()

    def sendall(self, data) -> None:
        self.sent += bytes(data)

    def makefile(self, mode="rb", *args, **kwargs):
        return self.transport.respond(self)

    def close(self) -> None:
        pass


class FakeProviders:
    """OpenAI (Responses API), Anthropic (Messages API) and Gemini
    (generateContent) with the request and reply shapes of the real APIs
    (no SDK conveniences such as a top-level ``output_text``)."""

    def __init__(self, key: str):
        self.keys = {provider: key for provider in HOSTS}      # the key each one accepts
        self.models = default_catalog()
        # Listed, but refuses a plain text request (as deep-research or
        # completion-only models do): HTTP 400.
        self.unsupported = {"synth-deep-tools"}
        self.reply = "The groups differ, as the engine reported."
        self.faults: list[Fault] = []
        self.exchanges: list[Exchange] = []
        self.connections = 0                 # connections opened (refused ones too)
        self.unexpected_hosts: list[str] = []
        self.arrived = threading.Event()     # set when a request reaches a provider
        self._lock = threading.Lock()

    # ---------------------------------------------------------- set-up
    def install(self, case: unittest.TestCase) -> None:
        transport = self

        class Connection(http.client.HTTPConnection):
            """``http.client.HTTPSConnection`` with a socket in memory."""

            default_port = http.client.HTTPS_PORT

            def __init__(self, host, port=None, *, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                         source_address=None, context=None, blocksize=8192):
                super().__init__(host, port, timeout=timeout, source_address=source_address,
                                 blocksize=blocksize)
                self.context = context

            def connect(self):
                self.sock = transport.open(self)

        for patcher in (mock.patch.object(http.client, "HTTPSConnection", Connection),
                        # No system or environment proxy: the provider is the peer.
                        mock.patch.object(urllib.request, "getproxies", lambda: {})):
            patcher.start()
            case.addCleanup(patcher.stop)
        case.addCleanup(lambda: case.assertEqual(self.unexpected_hosts, [],
                                                 "a request went to a host that is not a provider"))

    def clear(self) -> None:
        with self._lock:
            self.exchanges.clear()
            self.connections = 0
        self.arrived.clear()

    def posts(self) -> list[Exchange]:
        return [e for e in self.exchanges if e.method == "POST"]

    def listed(self, provider: str) -> list[str]:
        return [m["id"] for m in self.models[provider]]

    # --------------------------------------------------------- the wire
    def open(self, connection) -> MemorySocket:
        host = connection._tunnel_host or connection.host
        with self._lock:
            self.connections += 1
            refuse = bool(self.faults) and self.faults[0].kind == "refuse"
            if refuse:
                self.faults.pop(0)
        if host not in PROVIDER_AT:
            self.unexpected_hosts.append(host)
            raise ConnectionRefusedError(111, "Connection refused")
        if refuse:
            raise ConnectionRefusedError(111, "Connection refused")
        return MemorySocket(self, connection, host)

    def respond(self, sock: MemorySocket):
        raw = bytes(sock.sent)
        head, _, rest = raw.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        context = sock.connection.context
        exchange = Exchange(
            PROVIDER_AT[sock.host], sock.host, method, target, headers,
            rest[:int(headers.get("content-length") or 0)], raw, sock.connection.timeout,
            isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_REQUIRED
            and context.check_hostname)
        with self._lock:
            self.exchanges.append(exchange)
            fault = self.faults.pop(0) if self.faults else None
        self.arrived.set()
        if fault is not None and fault.kind == "hold":
            if not fault.release.wait(HOLD_LIMIT):
                return TimedOutReply()
            fault = Fault("reply", text=fault.text) if fault.text is not None else None
        if fault is None or fault.kind in ("reply", "empty"):
            return io.BytesIO(self.answer(exchange, fault))
        if fault.kind == "timeout":
            return TimedOutReply()
        if fault.kind == "truncated":
            return io.BytesIO(TRUNCATED)
        if fault.kind == "garbage":
            return io.BytesIO(b"<html>proxy error</html>\r\n")
        body = fault.body if fault.body is not None else {
            "error": {"message": f"synthetic HTTP {fault.status}", "type": "synthetic"}}
        return io.BytesIO(http_reply(fault.status, body, fault.headers))

    # ------------------------------------------------------- the APIs
    def answer(self, exchange: Exchange, fault: Fault | None) -> bytes:
        provider = exchange.provider
        presented = exchange.presented_key
        if presented != self.keys[provider]:
            # Worst case: the provider's error text repeats the key it was given.
            return http_reply(401, {"error": {"type": "authentication_error",
                                              "message": f"Incorrect API key provided: {presented}"}})
        if provider == "anthropic" and exchange.headers.get("anthropic-version") != "2023-06-01":
            return http_reply(400, {"error": {"message": "anthropic-version header is required"}})
        if exchange.method == "GET":
            if exchange.path != LIST_PATHS[provider]:
                return http_reply(404, {"error": {"message": "no such endpoint"}})
            return http_reply(200, self.catalog(provider))
        model = exchange.model
        if model in self.unsupported:
            return http_reply(400, {"error": {
                "type": "invalid_request_error", "param": "tools",
                "message": f"The model {model} needs tools this request does not have."}})
        if model not in self.listed(provider):
            return http_reply(404, {"error": {"type": "not_found_error",
                                              "message": f"model: {model}"}})
        empty = fault is not None and fault.kind == "empty"
        text = "" if empty else (fault.text if fault is not None and fault.text is not None
                                 else self.reply)
        return http_reply(200, self.generation(provider, model, exchange, text, empty),
                          chunked=True)

    def catalog(self, provider: str) -> dict:
        models = self.models[provider]
        if provider == "openai":
            return {"object": "list", "data": [{"id": m["id"], "object": "model",
                                                "created": 1767225600, "owned_by": "system"}
                                               for m in models]}
        if provider == "anthropic":
            return {"data": [{"type": "model", "id": m["id"], "display_name": m["name"],
                              "created_at": "2026-01-01T00:00:00Z"} for m in models],
                    "has_more": False, "first_id": models[0]["id"] if models else None,
                    "last_id": models[-1]["id"] if models else None}
        return {"models": [{"name": f"models/{m['id']}", "displayName": m["name"],
                            "supportedGenerationMethods": m["methods"]} for m in models]}

    @staticmethod
    def generation(provider, model, exchange, text, empty) -> dict:
        tokens_in = max(1, len(exchange.prompt) // 4)
        tokens_out = exchange.reply_limit if empty else max(1, len(text) // 4)
        if provider == "openai":
            output = [{"type": "reasoning", "id": "rs_synthetic", "summary": []}]
            if not empty:
                output.append({"type": "message", "id": "msg_synthetic", "status": "completed",
                               "role": "assistant", "content": [
                                   {"type": "output_text", "text": text, "annotations": []}]})
            return {"id": "resp_synthetic", "object": "response",
                    "status": "incomplete" if empty else "completed",
                    "incomplete_details": {"reason": "max_output_tokens"} if empty else None,
                    "model": f"{model}-2026-11-01", "output": output,
                    "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out,
                              "total_tokens": tokens_in + tokens_out}}
        if provider == "anthropic":
            return {"id": "msg_synthetic", "type": "message", "role": "assistant",
                    "model": f"{model}-20261101",
                    "content": [] if empty else [{"type": "text", "text": text}],
                    "stop_reason": "max_tokens" if empty else "end_turn", "stop_sequence": None,
                    "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out}}
        candidate = {"index": 0, "finishReason": "MAX_TOKENS" if empty else "STOP"}
        if not empty:
            candidate["content"] = {"role": "model", "parts": [{"text": text}]}
        return {"candidates": [candidate], "modelVersion": f"{model}-001",
                "usageMetadata": {"promptTokenCount": tokens_in,
                                  "candidatesTokenCount": tokens_out,
                                  "totalTokenCount": tokens_in + tokens_out}}


# ================================================================ the guard
class RealNetworkAttempt(AssertionError):
    """A test tried to open a real network connection."""


class NetworkGuard:
    """Refuse — and remember — every real network attempt. The record fails
    the test even when the code under test turns the error into a message."""

    def __init__(self):
        self.attempts: list[str] = []
        self._local = threading.local()

    def install(self, case: unittest.TestCase) -> None:
        guard = self
        real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
        real_socketpair = socket.socketpair

        def refuse(what, target):
            guard.attempts.append(f"{what} {target!r}")
            raise RealNetworkAttempt(f"a test attempted a real connection: {what} {target!r}")

        def connect(sock, address):
            if getattr(guard._local, "socketpair", False):   # asyncio's self-pipe on Windows
                return real_connect(sock, address)
            return refuse("socket.connect", address)

        def connect_ex(sock, address):
            if getattr(guard._local, "socketpair", False):
                return real_connect_ex(sock, address)
            return refuse("socket.connect_ex", address)

        def socketpair(*args, **kwargs):
            guard._local.socketpair = True
            try:
                return real_socketpair(*args, **kwargs)
            finally:
                guard._local.socketpair = False

        patches = (
            mock.patch.object(socket.socket, "connect", connect),
            mock.patch.object(socket.socket, "connect_ex", connect_ex),
            mock.patch.object(socket, "socketpair", socketpair),
            mock.patch.object(socket, "create_connection",
                              lambda address, *a, **k: refuse("socket.create_connection", address)),
            mock.patch.object(socket, "getaddrinfo",
                              lambda host, *a, **k: refuse("socket.getaddrinfo", host)),
            mock.patch.object(ssl.SSLContext, "wrap_socket",
                              lambda self, sock, *a, **k: refuse("ssl.wrap_socket",
                                                                 k.get("server_hostname"))),
            mock.patch.object(ssl.SSLContext, "wrap_bio",
                              lambda self, *a, **k: refuse("ssl.wrap_bio",
                                                           k.get("server_hostname"))),
        )
        for patcher in patches:
            patcher.start()
            case.addCleanup(patcher.stop)

    def verify(self, case: unittest.TestCase) -> None:
        case.assertEqual(self.attempts, [], "the test attempted a real network connection")


class NetworkGuardTests(unittest.TestCase):
    """The guard itself: a request that bypassed the fake would be caught."""

    def test_a_real_request_is_refused_and_recorded(self):
        guard = NetworkGuard()
        guard.install(self)
        with mock.patch.object(urllib.request, "getproxies", lambda: {}), \
                self.assertRaises(RealNetworkAttempt):
            ap.list_models("openai", KEY)
        self.assertEqual(guard.attempts, ["socket.create_connection ('api.openai.com', 443)"])


# ================================================================ helpers
def texts(ws, data: str) -> str:
    found = []
    for control in ws.controls(ws.find(data)):
        if isinstance(control, ft.Text):
            found.append(control.value or "".join(s.text or "" for s in control.spans or []))
        elif isinstance(control, (ft.Button, ft.TextButton)) and isinstance(control.content, str):
            found.append(control.content)
    return " ".join(found)


def controls_with(ws, data: str) -> list:
    return [c for c in ws.controls() if getattr(c, "data", None) == data]


def write_dataset(path: Path, prefix: str) -> Path:
    """40 synthetic rows: two arms and an ordinal score (no real person)."""
    rows = [f"{prefix}_group,{prefix}_stress"]
    for i in range(40):
        rows.append(f"{prefix}_arm{1 + i % 2},{(i * 7) % 5 + 1 + i % 2}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def strings(value) -> list[str]:
    """Every string in a JSON value (keys excluded)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in strings(item)]
    return []


async def until(event: threading.Event, seconds: float = 10.0) -> None:
    for _ in range(int(seconds * 100)):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the request never reached the provider")


class GateCase(unittest.TestCase):
    """A data folder of its own, a fake OS credential store, the fake
    providers, the network guard and the Retry-After spy."""

    key = KEY

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.guard = NetworkGuard()
        self.addCleanup(self.guard.verify, self)        # runs last
        self.guard.install(self)
        self.providers = FakeProviders(self.key)
        self.providers.install(self)
        self.stored: dict[str, str] = {}
        store = mock.Mock(set=lambda t, s: self.stored.__setitem__(t, s),
                          get=lambda t: self.stored.get(t),
                          remove=lambda t: self.stored.pop(t, None) is not None)
        # Back-off waits are recorded, not slept (unless a test asks for them).
        self.waits: list[float] = []
        self.backing_off = threading.Event()
        self.real_waits = False
        real_retry_after = ap._retry_after

        def retry_after(value, attempt):
            wait = real_retry_after(value, attempt)
            self.waits.append(wait)
            self.backing_off.set()
            return wait if self.real_waits else 0.0

        for patcher in (mock.patch.object(secret_store, "backend", return_value=store),
                        mock.patch.object(ap, "_retry_after", side_effect=retry_after),
                        mock.patch("workspace_shell.WorkspaceApp._remember_file"),
                        mock.patch.dict(os.environ, {"SRA_LOG_DIR": str(self.base / "logs")})):
            patcher.start()
            self.addCleanup(patcher.stop)

    # -------------------------------------------------------- researcher
    def workspace(self, **kwargs) -> Workspace:
        ws = Workspace(root=self.base, **kwargs)
        self.addCleanup(ws.close)
        return ws

    def connect(self, ws, provider: str = "openai", model: str | None = None) -> str:
        """Settings → AI providers, as a researcher does it: choose the
        provider, save the key, test the connection (the provider lists its
        models), choose a model."""
        ws.app.navigate("settings")
        ws.choose("ai-provider", provider)
        ws.type("ai-key", self.key)
        ws.click("ai-save-key")
        ws.click("ai-test")
        model = model or DEFAULT_MODEL[provider]
        ws.choose("ai-model", model)
        self.providers.clear()          # listing models is not an assistant request
        return model

    def create_project(self, ws, title: str):
        ws.app.navigate("home")
        ws.type("project-new-title", title)
        ws.click("project-create")
        self.assertEqual(ws.app.projects.info().title, title)
        return ws.app.projects.project

    def analyse(self, ws, prefix: str = "synth"):
        data = write_dataset(self.base / f"{prefix}_data.csv", prefix)
        self.assertTrue(ws.run(ws.app.load_path(str(data))))
        ws.app.session.confirm_level(f"{prefix}_stress", "ordinal")
        ws.app.session.confirm_level(f"{prefix}_group", "nominal")
        entry = ws.run(ws.app.pages["analyze"]._execute(
            "groups", {"outcome": f"{prefix}_stress", "group": f"{prefix}_group"}, {},
            {"independent": True}))
        self.assertIsNotNone(entry)
        ws.app.navigate("results")
        return entry

    def allow(self, ws, *sources: str, anonymous: bool = False) -> None:
        """Settings → AI assistance: the open project's switches."""
        ws.app.navigate("settings")
        if anonymous:
            ws.check("ai-anonymous", True)
        for source in sources:
            ws.check(f"ai-allow-{source}", True)
        ws.app.navigate("results")

    def send(self, ws) -> str:
        """Press Send; returns the text the preview showed."""
        shown = ws.find("ai-preview-text").value
        ws.click("ai-send")
        return shown

    @staticmethod
    def ai_events(project) -> list[dict]:
        return [e["detail"] for e in project.events(limit=10_000) if e["kind"] == "ai_request"]

    def local_log(self) -> list[dict]:
        path = ai_assist.local_log_path(self.base)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def assert_recovered(self, ws) -> None:
        """After a failure: no crash, no draft, Send usable, the result intact."""
        self.assertEqual(controls_with(ws, "ai-draft"), [])
        self.assertEqual(controls_with(ws, "ai-progress"), [])
        self.assertFalse(ws.find("ai-send").disabled)
        self.assertTrue(ws.find("result-table"))


# ============================================================ Gate 1
class Gate01ModelDiscoveryTests(GateCase):
    """Gate 1 — models are discovered through the existing provider adapters
    (``ai_providers.list_models``) and never hard-coded.

    Already proven, not repeated: ``test_ai_providers.ProviderTests.
    test_models_come_from_the_provider_and_only_text_models_are_offered`` and
    ``test_model_lists_are_cached_for_a_day`` (``list_models`` against a
    local server through ``base=``); ``test_workspace_ai`` (the Settings card
    with ``list_models`` patched out). Added: the Settings card on the
    production HTTPS path of all three providers, with model IDs invented
    while the test runs; and a search of the program for model IDs."""

    def test_the_settings_card_offers_exactly_the_models_the_provider_lists_now(self):
        ws = self.workspace()
        for provider in HOSTS:
            with self.subTest(provider=provider):
                token = uuid.uuid4().hex[:8]          # no program can know these IDs
                text_ids = [f"{provider}-synth-{token}-b", f"{provider}-synth-{token}-a"]
                listed = [model_entry(m) for m in text_ids]
                if provider == "openai":
                    listed.append(model_entry(f"text-embedding-{token}"))
                if provider == "gemini":
                    listed.append(model_entry(f"embedding-{token}", methods=("embedContent",)))
                self.providers.models[provider] = listed
                ws.app.navigate("settings")
                ws.choose("ai-provider", provider)
                self.assertEqual(controls_with(ws, "ai-model"), [],
                                 "no model is offered before the provider is asked")
                ws.type("ai-key", self.key)
                ws.click("ai-save-key")
                self.assertEqual(self.providers.exchanges, [], "saving a key sends nothing")
                ws.click("ai-test")
                offered = [option.key for option in ws.find("ai-model", ft.Dropdown).options]
                self.assertEqual(offered, sorted(text_ids))
                self.assertIn("Connected: 2 text models available.", texts(ws, "ai-message"))
                (listing,) = self.providers.exchanges
                self.assertEqual((listing.host, listing.method, listing.path),
                                 (HOSTS[provider], "GET", LIST_PATHS[provider]))
                self.assertEqual(listing.body, b"", "listing models sends no project content")
                self.assertEqual(listing.presented_key, self.key)
                self.assertNotIn(self.key, listing.target, "the key is never in the address")
                self.assertEqual(listing.timeout, ap.TIMEOUT)
                self.assertTrue(listing.tls_verified, "certificate and host name are checked")
                ws.choose("ai-model", offered[0])
                self.assertEqual(ap.load_settings(self.base)["model"], offered[0])
                self.assertEqual(ai_context.readiness(self.base).model, offered[0])
                cache = json.loads((self.base / "ai" / "models.json").read_text(encoding="utf-8"))
                self.assertEqual([m["id"] for m in cache[provider]["models"]], sorted(text_ids))
                self.providers.clear()

    def test_no_model_id_is_written_into_the_program(self):
        model_id = re.compile(r"\b(gpt-?\d|gpt-4o|chatgpt-|o[1-9](-mini|-pro)?\b|"
                              r"claude-(\d|instant|opus|sonnet|haiku)|gemini-(\d|pro|flash|ultra)|"
                              r"gemma-\d|text-davinci|davinci-\d|babbage-\d)", re.I)
        for module in AI_MODULES:
            tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
            literals = [node.value for node in ast.walk(tree)
                        if isinstance(node, ast.Constant) and isinstance(node.value, str)]
            self.assertEqual([s for s in literals if model_id.search(s)], [], module)
        import workspace_text

        ai_texts = [value for key, row in workspace_text.T.items()
                    if key.startswith(("assistant.", "ai.", "help.ai")) for value in row]
        self.assertEqual([s for s in ai_texts if model_id.search(s)], [])
        fresh = ap.load_settings(self.base / "fresh")
        self.assertEqual(fresh["model"], "", "a new installation has no model chosen")


# ============================================================ Gate 2
class Gate02UnsupportedModelTests(GateCase):
    """Gate 2 — models and capabilities the assistant cannot use.

    Already proven, not repeated: the name filter in
    ``test_ai_providers...test_models_come_from_the_provider_and_only_text_
    models_are_offered`` (an embedding model, Whisper, a Gemini model without
    ``generateContent``). Added: every excluded kind through the Settings
    card; a key with no text model; a model the provider does not know
    (404) and a listed model that refuses a text request (400) on the panel;
    replies without text from a reasoning model."""

    def test_models_that_cannot_answer_text_are_not_offered(self):
        ws = self.workspace()
        for provider, expected in (("openai", ["gpt-synth-alpha", "gpt-synth-beta",
                                               "synth-deep-tools"]),
                                   ("gemini", ["gemini-synth-pro"])):
            with self.subTest(provider=provider):
                ws.app.navigate("settings")
                ws.choose("ai-provider", provider)
                ws.type("ai-key", self.key)
                ws.click("ai-save-key")
                ws.click("ai-test")
                self.assertEqual([o.key for o in ws.find("ai-model", ft.Dropdown).options],
                                 expected)

    def test_a_key_that_can_use_no_text_model(self):
        self.providers.models["openai"] = [model_entry("text-embedding-synth"),
                                           model_entry("whisper-synth")]
        ws = self.workspace()
        ws.app.navigate("settings")
        ws.type("ai-key", self.key)
        ws.click("ai-save-key")
        ws.click("ai-test")
        self.assertIn("This key can use no text model.", texts(ws, "ai-message"))
        self.assertEqual(controls_with(ws, "ai-model"), [])
        self.assertEqual(ai_context.readiness(self.base).problem, "no_model")
        self.create_project(ws, "No text model")
        self.analyse(ws)
        self.assertIn("no model is chosen", texts(ws, "ai-not-ready"))
        self.assertEqual(controls_with(ws, "ai-send"), [])

    def test_a_typed_model_the_provider_does_not_know(self):
        ws = self.workspace()
        self.connect(ws)
        ws.app.navigate("settings")
        ws.type("ai-manual-model", "gpt-synth-retired")
        ws.click("ai-use-model")
        project = self.create_project(ws, "Unknown model")
        self.analyse(ws)
        self.assertEqual(texts(ws, "ai-send"), "Send to OpenAI (gpt-synth-retired)")
        self.send(ws)
        self.assertIn("OpenAI does not know the model “gpt-synth-retired”. Choose another model "
                      "in Settings → AI providers.", texts(ws, "ai-error"))
        self.assertTrue(ws.find("ai-error-settings"))
        self.assertEqual(len(self.providers.posts()), 1, "a 4xx is not sent again")
        self.assertEqual([(e["model"], e["outcome"], e["tokens"]) for e in self.ai_events(project)],
                         [("gpt-synth-retired", "not_found", 0)])
        self.assert_recovered(ws)

    def test_a_listed_model_that_refuses_a_text_request(self):
        """HTTP 400: the model is in the provider's list but cannot answer a
        plain text request (deep-research models need tools, legacy models
        another API). The researcher must hear that the model is the
        problem — not that the provider had a server error."""
        ws = self.workspace()
        self.connect(ws, model="synth-deep-tools")
        project = self.create_project(ws, "Unsupported model")
        self.analyse(ws)
        self.send(ws)
        message = texts(ws, "ai-error")
        self.assertIn("OpenAI refused this request for the model “synth-deep-tools”", message)
        self.assertIn("Choose another model in Settings → AI providers.", message)
        self.assertNotIn("server error", message)
        self.assertTrue(ws.find("ai-error-settings"))
        self.assertEqual(len(self.providers.posts()), 1, "a refused request is not sent again")
        self.assertEqual([e["outcome"] for e in self.ai_events(project)], ["unsupported"])
        self.assert_recovered(ws)

    def test_a_reply_without_any_text(self):
        ws = self.workspace()
        project = None
        for provider in ("openai", "gemini"):
            with self.subTest(provider=provider):
                self.connect(ws, provider)
                if project is None:
                    project = self.create_project(ws, "Reasoning out of tokens")
                    self.analyse(ws)
                ws.app.navigate("results")
                self.providers.faults = [Fault("empty")]
                self.send(ws)
                name = ap.PROVIDERS[provider].name
                self.assertIn(f"{name} returned no text. Some models spend the whole reply "
                              "limit on internal reasoning.", texts(ws, "ai-error"))
                self.assertEqual(self.ai_events(project)[0]["outcome"], "empty")
                self.assert_recovered(ws)


# ============================================================ Gate 3
def file_contents(path: Path):
    """The bytes of a file and, for ZIP containers (.sra, .docx), of each member."""
    data = path.read_bytes()
    yield str(path), data
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                yield f"{path}!{name}", archive.read(name)


def downgrade_to_format_4(database: Path) -> None:
    """Make a project database look as a Stage 36.3 build left it, so that
    opening it takes a migration copy into ``.backups``."""
    with closing(sqlite3.connect(database)) as db:
        db.execute("ALTER TABLE runs DROP COLUMN charts")
        db.execute("PRAGMA user_version = 4")
        db.commit()


class Gate03KeyNeverWrittenTests(GateCase):
    """Gate 3 — no API key in logs or project backups (``.sra`` copies,
    ``.backups``, the activity log, the app log, exceptions).

    Already proven, not repeated: ``test_ai_providers`` — the key travels in
    a header, never in the address; a refused key is not echoed; the model
    cache holds no key; keys live only in the OS store, with no plain-text
    fallback. Added: one AI flow with the key ``sk-test-SENTINEL-0000``
    that produces every kind of file the application writes, then a search
    of every produced file (and every member of every ZIP)."""

    key = SENTINEL

    def test_the_key_is_in_no_file_log_backup_or_exception(self):
        logs = self.base / "logs"
        logs.mkdir()
        console = (logs / "console.log").open("w", encoding="utf-8")
        self.addCleanup(console.close)
        # The app log: the packaged build writes the console to console.log;
        # every logger, at DEBUG, goes to app-debug.log as well.
        handler = logging.FileHandler(logs / "app-debug.log", encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        root_logger = logging.getLogger()
        level = root_logger.level
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)
        logging.captureWarnings(True)

        def stop_logging():
            logging.captureWarnings(False)
            root_logger.removeHandler(handler)
            root_logger.setLevel(level)
            handler.close()

        self.addCleanup(stop_logging)
        errors: list[BaseException] = []
        with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
            ws = self.workspace()
            # Settings: the provider first refuses the key; its error text
            # repeats the key (worst case). Then the key is accepted.
            ws.app.navigate("settings")
            ws.choose("ai-provider", "openai")
            ws.type("ai-key", self.key)
            ws.click("ai-save-key")
            self.providers.keys["openai"] = "sk-test-a-different-valid-key"
            ws.click("ai-test")
            self.assertIn("The provider refused the key.", texts(ws, "ai-message"))
            self.providers.keys["openai"] = self.key
            ws.click("ai-test")
            ws.choose("ai-model", "gpt-synth-alpha")
            ws.type("ai-budget", "100000")
            # A project, a result and one allowed source.
            project = self.create_project(ws, "Fictional key audit")
            project_id = project.id
            project.add_question("Does stress differ between the two arms?")
            self.analyse(ws)
            self.allow(ws, "overview")
            ws.check("ai-source-overview", True)
            # Requests: one answered, then every failure a provider can give.
            self.send(ws)
            ws.click("ai-use-note")
            for faults in ([Fault.http(401)],
                           [Fault.http(429, ("Retry-After", "1"))] * (ap.RETRIES + 1),
                           [Fault.http(500)] * (ap.RETRIES + 1), [Fault.http(400)],
                           [Fault.http(404)], [Fault("timeout")] * (ap.RETRIES + 1),
                           [Fault("truncated")], [Fault("garbage")],
                           [Fault("refuse")] * (ap.RETRIES + 1)):
                self.providers.faults = list(faults)
                self.send(ws)
            self.providers.faults = []
            ws.click("export-docx")                 # the Word draft with the AI note
            # The adapters' exceptions, as a crash report would print them.
            cancelled = threading.Event()
            cancelled.set()
            calls = (
                ([Fault.http(401)], lambda: ap.list_models("openai", self.key, refresh=True)),
                ([Fault.http(401)], lambda: ap.generate("anthropic", self.key,
                                                        "claude-synth-one", "Explain.")),
                ([Fault.http(429, ("Retry-After", "1"))] * (ap.RETRIES + 1),
                 lambda: ap.generate("openai", self.key, "gpt-synth-alpha", "Explain.")),
                ([Fault("timeout")] * (ap.RETRIES + 1),
                 lambda: ap.generate("gemini", self.key, "gemini-synth-pro", "Explain.")),
                ([Fault("truncated")],
                 lambda: ap.generate("openai", self.key, "gpt-synth-alpha", "Explain.")),
                ([Fault("garbage")],
                 lambda: ap.generate("anthropic", self.key, "claude-synth-one", "Explain.")),
                ([], lambda: ap.generate("openai", self.key, "gpt-synth-alpha", "Explain.",
                                         cancel=cancelled)),
                ([], lambda: ap.generate("openai", self.key, "a model with spaces", "Explain.")),
                ([], lambda: secret_store.set_key("openai", "not a key")),
                ([], lambda: ai_assist.send(          # a source this project does not allow
                    ai_assist.build_request("explain_method", result="x",
                                            sources=("dictionary",),
                                            project=ws.app.projects.project),
                    setup=ai_context.Readiness("openai", "gpt-synth-alpha", 0, ""),
                    key=self.key, project=ws.app.projects.project, data_root=self.base)),
            )
            for faults, call in calls:
                self.providers.faults = list(faults)
                try:
                    call()
                except Exception as error:      # noqa: BLE001 - every kind is collected
                    errors.append(error)
            self.providers.faults = []
            for error in errors:
                console.write("".join(traceback.format_exception(error)))
                timeline = startup_diagnostics.StartupTimeline()
                timeline.mark("workspace_imported")
                timeline.fail(error)
                startup_diagnostics.write_startup_record(timeline)
            # Backups: a .sra from the hub, restored; a migration copy in .backups.
            ws.app.navigate("home")
            ws.click(f"project-backup-{project_id}")
            backup = ws.saved[-1]
            self.assertTrue(ws.run(ws.app.hub.restore_files(
                [SimpleNamespace(path=str(backup), name=backup.name)])))
            ws.click("project-close")
            downgrade_to_format_4(self.base / "projects" / project_id / "project.sqlite3")
            ws.click(f"project-open-{project_id}")
            self.assertEqual(ws.app.projects.info().id, project_id)
            # A request without a project: the log on this computer.
            ws.click("project-close")
            self.analyse(ws)
            self.send(ws)
            self.assertTrue(ws.find("ai-draft"))
            # Nothing on any screen holds the key.
            for route in ("settings", "results", "home", "reports", "help"):
                ws.app.navigate(route)
                for control in ws.controls():
                    for name in ("value", "label", "semantics_label", "tooltip", "hint_text",
                                 "text", "content"):
                        value = getattr(control, name, None)
                        if isinstance(value, str):
                            self.assertNotIn("SENTINEL", value, f"{route}: {control!r}")
        stop_logging()
        console.flush()
        produced = sorted(path for path in self.base.rglob("*") if path.is_file())
        relative = [path.relative_to(self.base).as_posix() for path in produced]
        # The search: every file, every member of every ZIP, every exception.
        needles = (self.key.encode(), b"SENTINEL", self.key.encode("utf-16-le"),
                   "SENTINEL".encode("utf-16-le"), base64.b64encode(self.key.encode()),
                   urllib.parse.quote(self.key).encode())
        leaks = [name for path in produced for name, data in file_contents(path)
                 if any(needle in data for needle in needles)]
        self.assertEqual(leaks, [])
        for error in errors:
            for text in (str(error), repr(error), repr(error.args),
                         "".join(traceback.format_exception(error))):
                self.assertNotIn("SENTINEL", text)
        # The test produced every kind of file it searched.
        for kind, present in (
                (".sra backup", any(p.endswith(".sra") for p in relative)),
                (".backups copy", any("/.backups/" in f"/{p}" for p in relative)),
                ("project database", any(p.endswith("/project.sqlite3") for p in relative)),
                ("restored project", len([p for p in relative if p.endswith("project.sqlite3")
                                          and "/.backups/" not in f"/{p}"]) >= 2),
                ("AI settings", "ai/settings.json" in relative),
                ("model cache", "ai/models.json" in relative),
                ("token budget", "ai/usage.json" in relative),
                ("local AI log", "ai/requests.jsonl" in relative),
                ("startup log", "logs/startup.log" in relative),
                ("console log", "logs/console.log" in relative),
                ("debug log", "logs/app-debug.log" in relative),
                ("Word draft", any(p.endswith(".docx") for p in relative))):
            self.assertTrue(present, f"the flow did not produce a {kind}: {relative}")
        # The activity log and the backup really hold the AI transfers, and
        # the key really was in use: a leak would have been found.
        with closing(sqlite3.connect(self.base / "projects" / project_id / "project.sqlite3")) as db:
            kinds = [row[0] for row in db.execute("SELECT kind FROM events")]
        self.assertGreaterEqual(kinds.count("ai_request"), 8)
        with zipfile.ZipFile(backup) as archive:
            self.assertIn(b"ai_request", archive.read("project/project.sqlite3"))
        self.assertEqual(len(errors), 10)
        self.assertIn(self.key, self.stored.values())
        self.assertTrue(any(e.presented_key == self.key for e in self.providers.exchanges))


# ============================================================ Gate 4
class Gate04ProjectConsentTests(GateCase):
    """Gate 4 — consent is per project (and every request is its own consent).

    Already proven, not repeated: ``test_project_profile.AiContextTests.
    test_rules_a_future_assistant_must_pass`` (another project starts with
    nothing allowed) and ``test_permissions_travel_with_the_project_backup``;
    ``test_project_profile...test_the_ai_card_allows_sources_per_project_and_
    rows_need_the_statement`` (the switches); ``test_workspace_assistant.
    RefusalTests.test_a_source_the_project_does_not_allow_is_never_sent``.
    Added: two projects through the hub in one session; what one project
    allows does not apply in the other; each Send is one request, recorded
    in its own project's activity log only."""

    def test_a_permission_given_in_one_project_does_not_apply_in_another(self):
        ws = self.workspace()
        self.connect(ws)
        first = self.create_project(ws, "First fictional project")
        first_id = first.id
        self.analyse(ws, "first")
        self.allow(ws, "overview", "plan")
        ws.check("ai-source-overview", True)
        self.assertIn("CONTEXT (overview)", ws.find("ai-preview-text").value)
        self.send(ws)
        self.assertEqual([e["sources"] for e in self.ai_events(first)], [["overview", "result"]])
        # The second project: none of the first project's decisions applies.
        second = self.create_project(ws, "Second fictional project")
        self.assertFalse(any(ai_context.permissions(second).values()))
        self.analyse(ws, "second")
        self.assertEqual([c.data for c in ws.find_all("ai-source-")], ["ai-source-result"])
        self.assertIn("Project overview", texts(ws, "ai-not-allowed"))
        self.assertNotIn("CONTEXT (", ws.find("ai-preview-text").value)
        self.assertIn("recorded in the project’s activity log", texts(ws, "ai-consent"))
        self.providers.clear()
        self.send(ws)
        (post,) = self.providers.posts()
        self.assertNotIn("CONTEXT (", post.prompt)
        self.assertEqual([e["sources"] for e in self.ai_events(second)], [["result"]])
        # Each press of Send is one request.
        ws.click("ai-discard")
        self.send(ws)
        self.assertEqual(len(self.providers.posts()), 2)
        self.assertEqual(len(self.ai_events(second)), 2)
        ws.app.navigate("settings")
        self.assertFalse(any(ws.find(f"ai-allow-{key}").value for key in ai_context.SOURCE_KEYS))
        # Back in the first project: its own permissions, its own log.
        ws.app.navigate("home")
        ws.click(f"project-open-{first_id}")
        first = ws.app.projects.project
        self.assertTrue(ai_context.permissions(first)["overview"])
        self.assertEqual(len(self.ai_events(first)), 1, "the second project's requests are not here")
        ws.app.navigate("results")
        self.assertFalse(ws.find("ai-source-overview").value,
                         "a source is sent only after a new tick in this session")


# ============================================================ Gate 5
class Gate05PayloadPreviewTests(GateCase):
    """Gate 5 — exactly what is sent is shown first, and nothing is sent
    before the researcher confirms.

    Already proven, not repeated: ``test_workspace_assistant.AssistantFlowTests.
    test_connect_analyse_preview_send_check_and_use_as_a_note`` (OpenAI: the
    request text equals the preview; nothing sent before Send) and
    ``test_a_typed_question_is_previewed_before_it_can_be_sent``;
    ``test_ai_assistant.NoNetworkTests``. Added: for all three providers, the
    whole wire request — host, path, model, reply limit and every string in
    the body — is what the preview shows, nothing leaves during any choice
    before Send, and Send goes only to the provider and model on screen."""

    ALLOWED_HEADERS = {"accept-encoding", "host", "content-type", "content-length",
                       "user-agent", "connection"}

    def test_each_provider_receives_exactly_the_preview(self):
        for provider in HOSTS:
            with self.subTest(provider=provider):
                ws = self.workspace()
                model = self.connect(ws, provider)
                project = self.create_project(ws, f"Preview study {provider}")
                project.add_question("Does stress differ between the two arms?")
                self.analyse(ws, provider)
                self.allow(ws, "overview")
                ws.choose("ai-task", "interpretation")
                ws.segment("ai-depth", "professor")
                ws.check("ai-source-overview", True)
                ws.type("ai-question", "Which assumption should I check first?")
                ws.app.render()                       # leaving the field updates the preview
                self.assertEqual(self.providers.exchanges, [], "choosing sends nothing")
                shown = ws.find("ai-preview-text").value
                name, host = ap.PROVIDERS[provider].name, HOSTS[provider]
                self.assertEqual(texts(ws, "ai-preview-to"), f"To: {name} ({host}) · model {model}")
                limit = ai_assist.TASK_SPECS["interpretation"].reply_tokens
                self.assertIn(f"Reply limit: {limit} tokens.", texts(ws, "ai-preview-size"))
                self.assertEqual(texts(ws, "ai-send"), f"Send to {name} ({model})")
                self.assertIn("Which assumption should I check first?", shown)
                self.assertIn("Research question: Does stress differ", shown)
                self.send(ws)
                (post,) = self.providers.exchanges
                self.assertEqual((post.host, post.method, post.path),
                                 (host, "POST", generate_path(provider, model)))
                self.assertEqual(post.model, model)
                self.assertEqual(post.prompt, shown, "the text on screen, character for character")
                self.assertEqual(post.reply_limit, limit)
                self.assertEqual(set(strings(post.json)) - {shown, model, "user"}, set(),
                                 "the body carries nothing the preview does not show")
                self.assertLessEqual(set(post.headers),
                                     self.ALLOWED_HEADERS | {AUTH_HEADER[provider],
                                                             "anthropic-version"})
                for value in post.headers.values():
                    self.assertNotIn("stress", value)
                self.assertTrue(post.tls_verified)
                self.assertTrue(ws.find("ai-draft"))
                ws.close()

    def test_send_goes_only_to_the_provider_and_model_on_screen(self):
        """Another window of the application changes Settings → AI providers
        while this preview is on screen: Send must not go elsewhere."""
        ws = self.workspace()
        self.connect(ws, "openai")
        self.stored["StatisticalResearchAssistant/ai/anthropic"] = self.key   # saved earlier
        project = self.create_project(ws, "Destination study")
        self.analyse(ws)
        self.assertEqual(texts(ws, "ai-send"), "Send to OpenAI (gpt-synth-alpha)")
        ap.save_settings(self.base, {"provider": "anthropic", "model": "claude-synth-one",
                                     "daily_tokens": 0})
        ws.click("ai-send")             # the button on screen still names OpenAI
        self.assertEqual(self.providers.exchanges, [],
                         "nothing goes to a provider or a model the preview did not show")
        self.assertIn("changed after the preview", texts(ws, "ai-notice"))
        self.assertEqual(texts(ws, "ai-preview-to"),
                         "To: Anthropic (api.anthropic.com) · model claude-synth-one")
        self.send(ws)
        (post,) = self.providers.exchanges
        self.assertEqual((post.host, post.model), ("api.anthropic.com", "claude-synth-one"))
        self.assertEqual(self.ai_events(project)[0]["provider"], "anthropic")


# ============================================================ Gate 6
class Gate06RefusalTests(GateCase):
    """Gate 6 — a request without the needed permission is refused, and
    nothing leaves the computer.

    Already proven, not repeated: ``test_ai_assistant.SendTests.
    test_refusals_send_nothing`` (not set up, a source not allowed, data rows
    without the anonymity statement, a permission withdrawn after the preview;
    no request, no audit entry); ``test_workspace_assistant.RefusalTests``
    (the panel: no provider, no model, a source not allowed, permissions
    withdrawn before and during sending, data rows); ``test_ai_assistant.
    ResultTextTests.test_a_request_without_a_project_holds_only_the_result_
    and_the_question``. Added: the key removed or unreadable between the
    preview and Send, and the anonymity statement withdrawn between the
    preview and Send — on the production path, under the network guard."""

    def test_a_key_removed_after_the_preview_is_never_used(self):
        ws = self.workspace()
        self.connect(ws)
        project = self.create_project(ws, "Removed key")
        self.analyse(ws)
        self.assertTrue(ws.find("ai-send"))
        self.stored.clear()                         # removed in another window
        ws.click("ai-send")
        self.assertEqual(self.providers.exchanges, [])
        self.assertIn("No AI provider is connected", texts(ws, "ai-not-ready"))
        self.assertEqual(controls_with(ws, "ai-send"), [])
        self.assertEqual(self.ai_events(project), [])

    def test_an_unreadable_key_sends_nothing(self):
        ws = self.workspace()
        self.connect(ws)
        project = self.create_project(ws, "Unreadable key")
        self.analyse(ws)
        with mock.patch.object(secret_store, "has_key", return_value=True), \
                mock.patch.object(secret_store, "get_key",
                                  side_effect=secret_store.SecretStoreUnavailable("locked")):
            ws.click("ai-send")
        self.assertIn("could not be read from this computer’s credential store, so nothing "
                      "was sent", texts(ws, "ai-error"))
        self.assertEqual(self.providers.exchanges, [])
        self.assertEqual(self.ai_events(project), [])

    def test_data_rows_withdrawn_before_send_are_not_sent(self):
        ws = self.workspace()
        self.connect(ws)
        project = self.create_project(ws, "Rows withdrawn")
        self.analyse(ws)
        self.allow(ws, "raw_data", anonymous=True)
        ws.check("ai-source-raw_data", True)
        self.assertIn("Data rows: 5", texts(ws, "ai-preview-rows"))
        ai_context.state_anonymous(project, False)  # changed where this screen has not redrawn
        ws.click("ai-send")
        self.assertEqual(self.providers.exchanges, [])
        self.assertIn("changed after the preview", texts(ws, "ai-notice"))
        self.assertEqual(texts(ws, "ai-preview-rows"), "Data rows: 0 — no row of the dataset is sent.")
        self.send(ws)
        (post,) = self.providers.posts()
        self.assertNotIn("CONTEXT (raw_data)", post.prompt)
        self.assertNotIn("synth_arm1,", post.prompt, "no data row")
        self.assertEqual(self.ai_events(project)[0]["sources"], ["result"])


# ============================================================ Gate 7
class Gate07TimeoutsAndRateLimitsTests(GateCase):
    """Gate 7 — timeouts and rate limits (HTTP 429, Retry-After): a clear
    message, no crash.

    Already proven, not repeated: ``test_ai_providers.ProviderTests.
    test_rate_limits_and_server_errors_are_retried_then_reported`` and
    ``test_timeouts_and_cancellation``; ``test_ai_assistant.SendTests.
    test_provider_errors_are_reported_and_audited_when_the_request_left`` and
    ``test_offline_is_reported``; ``test_workspace_assistant.ErrorTests``
    (401, 429 and 503 explained on the panel; offline). Added: Retry-After
    honoured (seconds, a date, a cap); a generation that times out is
    explained as a timeout and not sent again; Test connection timeouts;
    replies cut off mid-body or not HTTP at all; every request carries the
    time limit."""

    def ready(self):
        ws = self.workspace()
        self.connect(ws)
        self.project = self.create_project(ws, "Timeouts and limits")
        self.analyse(ws)
        return ws

    def test_retry_after_is_honoured_then_the_rate_limit_is_explained(self):
        ws = self.ready()
        self.providers.faults = [Fault.http(429, ("Retry-After", "7"))] * (ap.RETRIES + 1)
        self.send(ws)
        self.assertIn("still refused after several tries (rate limit). Wait a minute and try "
                      "again.", texts(ws, "ai-error"))
        self.assertEqual(self.waits, [7.0] * ap.RETRIES, "the provider's Retry-After is used")
        self.assertEqual(len(self.providers.posts()), ap.RETRIES + 1)
        self.assertEqual(self.ai_events(self.project)[0]["outcome"], "rate_limited")
        self.assert_recovered(ws)
        for value, expected in (("2", 2.0), ("3600", 30.0), ("Wed, 21 Oct 2026 07:28:00 GMT", 0.5)):
            with self.subTest(retry_after=value):
                self.waits.clear()
                self.providers.clear()
                self.providers.faults = [Fault.http(429, ("Retry-After", value))]
                self.send(ws)
                self.assertEqual(self.waits, [expected])
                self.assertEqual(len(self.providers.posts()), 2)
                self.assertTrue(ws.find("ai-draft"), "answered after the wait")
                ws.click("ai-discard")

    def test_a_generation_that_times_out_is_explained_and_not_sent_again(self):
        ws = self.ready()
        self.providers.faults = [Fault("timeout")] * (ap.RETRIES + 1)
        self.send(ws)
        message = texts(ws, "ai-error")
        self.assertIn("OpenAI did not answer in time", message)
        self.assertNotIn("could not be reached", message, "the provider was reached")
        posts = self.providers.posts()
        self.assertEqual(len(posts), 1, "a generation that may still run (and be billed) is "
                                        "not sent again")
        self.assertEqual(posts[0].timeout, ap.TIMEOUT)
        self.assertEqual(self.ai_events(self.project)[0]["outcome"], "timeout")
        self.assertTrue(ws.find("ai-error-settings"))
        self.assert_recovered(ws)

    def test_test_connection_failures_are_explained_and_never_crash(self):
        ws = self.workspace()
        ws.app.navigate("settings")
        ws.type("ai-key", self.key)
        ws.click("ai-save-key")
        for faults, message, attempts in (
                ([Fault("timeout")] * (ap.RETRIES + 1), "The provider did not answer in time.",
                 ap.RETRIES + 1),
                ([Fault.http(429, ("Retry-After", "1"))] * (ap.RETRIES + 1),
                 "The provider is busy (rate limit).", ap.RETRIES + 1),
                ([Fault("truncated")], "The request failed.", 1),
                ([Fault("garbage")], "The request failed.", 1)):
            with self.subTest(fault=faults[0].kind):
                self.providers.clear()
                self.providers.faults = list(faults)
                try:
                    ws.click("ai-test")
                except Exception as error:       # noqa: BLE001
                    self.fail(f"Test connection crashed: {error!r}")
                self.assertIn(message, texts(ws, "ai-message"))
                self.assertEqual(len(self.providers.exchanges), attempts)
                self.assertTrue(all(e.timeout == ap.TIMEOUT for e in self.providers.exchanges))

    def test_replies_cut_off_or_not_http_and_no_connection_never_crash(self):
        ws = self.ready()
        for name, faults, message, outcome, connections in (
                ("truncated", [Fault("truncated")], "The reply from OpenAI could not be read.",
                 "malformed", 1),
                ("garbage", [Fault("garbage")], "The reply from OpenAI could not be read.",
                 "malformed", 1),
                ("refused", [Fault("refuse")] * (ap.RETRIES + 1), "OpenAI could not be reached",
                 "offline", ap.RETRIES + 1)):
            with self.subTest(fault=name):
                self.providers.clear()
                self.providers.faults = list(faults)
                self.send(ws)
                self.assertIn(message, texts(ws, "ai-error"))
                self.assertEqual(self.ai_events(self.project)[0]["outcome"], outcome,
                                 "the request may have reached the provider: it is on record")
                self.assertEqual(self.providers.connections, connections)
                self.assert_recovered(ws)


# ============================================================ Gate 8
class Gate08CancellationTests(GateCase):
    """Gate 8 — cancellation.

    Already proven, not repeated: ``test_ai_assistant.SendTests.
    test_a_cancelled_request_sends_nothing_and_a_late_reply_is_discarded``;
    ``test_workspace_assistant.ErrorTests.test_a_request_can_be_cancelled_
    while_waiting`` (Cancel while the provider answers: no draft, outcome
    "cancelled"); ``test_ai_providers...test_timeouts_and_cancellation``.
    Added: Cancel during a Retry-After wait ends the wait at once with no
    further attempt; the late reply of a cancelled request never replaces
    the draft of the request sent after it."""

    def ready(self):
        ws = self.workspace()
        self.connect(ws)
        self.project = self.create_project(ws, "Cancellation")
        self.analyse(ws)
        return ws

    def test_cancel_during_a_retry_after_wait_stops_at_once(self):
        ws = self.ready()
        self.real_waits = True
        self.providers.faults = [Fault.http(429, ("Retry-After", "20"))]
        send = ws.find("ai-send").on_click

        async def scenario() -> float:
            started = time.monotonic()
            waiting = asyncio.ensure_future(send(EVENT))
            await until(self.backing_off)
            ws.click("ai-cancel")
            self.assertIn("Cancelled.", texts(ws, "ai-error"))
            await asyncio.wait_for(waiting, timeout=15)
            return time.monotonic() - started

        elapsed = asyncio.run(scenario())
        self.assertEqual(self.waits, [20.0], "the provider asked for 20 seconds")
        self.assertLess(elapsed, 10, "Cancel ended the wait")
        self.assertEqual(len(self.providers.posts()), 1, "nothing is sent after Cancel")
        self.assertEqual([(e["outcome"], e["tokens"]) for e in self.ai_events(self.project)],
                         [("cancelled", 0)])
        self.assertEqual(controls_with(ws, "ai-draft"), [])
        self.assertFalse(ws.find("ai-send").disabled)

    def test_a_late_reply_never_replaces_the_next_draft(self):
        ws = self.ready()
        release = threading.Event()
        self.addCleanup(release.set)
        self.providers.faults = [Fault("hold", release=release, text="FIRST reply, too late."),
                                 Fault("reply", text="SECOND reply, on time.")]

        async def scenario():
            first = asyncio.ensure_future(ws.find("ai-send").on_click(EVENT))
            await until(self.providers.arrived)
            ws.click("ai-cancel")
            second = asyncio.ensure_future(ws.find("ai-send").on_click(EVENT))
            await asyncio.wait_for(second, timeout=15)
            self.assertIn("SECOND reply", texts(ws, "ai-draft"))
            release.set()
            await asyncio.wait_for(first, timeout=15)

        asyncio.run(scenario())
        self.assertIn("SECOND reply, on time.", texts(ws, "ai-draft"))
        self.assertNotIn("FIRST reply", texts(ws, "ai-draft"))
        events = self.ai_events(self.project)
        self.assertEqual(sorted(e["outcome"] for e in events), ["cancelled", "ok"])
        late = next(e for e in events if e["outcome"] == "cancelled")
        self.assertGreater(late["tokens"], 0, "the provider did answer it, and it is on record")


# ============================================================ Gate 9
class Gate09ProjectSwitchTests(GateCase):
    """Gate 9 — changing projects leaks no previous context: none of the
    previous project's data, results or conversation is in the next request.

    Nothing existing covers the request content after a switch
    (``test_project_workspace...test_switching_projects_from_home_keeps_their_
    work_apart`` covers the session only). Added: two projects created
    through the hub, the first with a marker in every source the assistant
    can send (overview, plan, dictionary, results, questionnaires, data
    rows), a typed question and a reply; the second project's whole wire
    request is searched for the markers; and a reply that arrives after the
    switch."""

    def fill(self, ws, project, marker: str) -> None:
        """A project with its marker in every source, all allowed."""
        low = marker.lower()
        project.update(description=f"{marker}-DESCRIPTION of a fictional study")
        project.add_question(f"{marker}-QUESTION: does stress differ between the arms?")
        project.save_plan({"objectives": f"{marker}-OBJECTIVE", "design": f"{marker}-DESIGN",
                           "hypotheses": [{"text": f"{marker}-HYPOTHESIS: stress differs",
                                           "outcome": f"{low}_stress"}]})
        project.link_questionnaire(f"{low}-survey", f"{marker}-QUESTIONNAIRE")
        self.allow(ws, *ai_context.SOURCE_KEYS, anonymous=True)

    def ask(self, ws, marker: str) -> None:
        for key in ai_context.SOURCE_KEYS:
            ws.check(f"ai-source-{key}", True)
        ws.type("ai-question", f"{marker}-ASK: what should I check first?")
        ws.app.render()

    def test_the_next_projects_request_holds_nothing_of_the_previous_one(self):
        ws = self.workspace()
        self.connect(ws)
        first = self.create_project(ws, "ZQXA sleep study")
        self.fill(ws, first, "ZQXA")
        self.analyse(ws, "zqxa")
        self.ask(ws, "ZQXA")
        self.providers.reply = "ZQXA-REPLY: the arms differ."
        self.send(ws)
        (first_post,) = self.providers.posts()
        # The first request did carry the first project: a leak would be seen.
        for fragment in ("ZQXA-DESCRIPTION", "ZQXA-QUESTION", "ZQXA-OBJECTIVE", "ZQXA-HYPOTHESIS",
                         "ZQXA-QUESTIONNAIRE", "zqxa_stress", "zqxa_arm1,", "zqxa_data.csv",
                         "ZQXA-ASK"):
            self.assertIn(fragment, first_post.prompt)
        ws.click("ai-use-note")
        self.providers.clear()
        second = self.create_project(ws, "WVYB reading study")
        self.fill(ws, second, "WVYB")
        self.assertEqual(controls_with(ws, "ai-draft"), [], "the previous draft is gone")
        self.analyse(ws, "wvyb")
        self.assertEqual(ws.find("result-notes").value, "", "and the previous note")
        self.ask(ws, "WVYB")
        self.providers.reply = "WVYB-REPLY"
        shown = self.send(ws)
        (second_post,) = self.providers.posts()
        for fragment in ("WVYB-DESCRIPTION", "WVYB-QUESTIONNAIRE", "wvyb_arm1,", "WVYB-ASK"):
            self.assertIn(fragment, second_post.prompt)
        for request in (shown, second_post.text):
            self.assertNotIn("zqxa", request.lower())
        self.assertEqual(len(self.ai_events(second)), 1)

    def test_a_reply_that_arrives_after_the_switch_is_dropped_and_kept_on_record(self):
        ws = self.workspace()
        self.connect(ws)
        first = self.create_project(ws, "ZQXA sleep study")
        first_id = first.id
        self.analyse(ws, "zqxa")
        release = threading.Event()
        self.addCleanup(release.set)
        self.providers.faults = [Fault("hold", release=release, text="ZQXA-REPLY, late")]

        async def scenario():
            waiting = asyncio.ensure_future(ws.find("ai-send").on_click(EVENT))
            await until(self.providers.arrived)
            ws.app.hub.new_title = "WVYB reading study"
            await ws.app.hub.create()                # the first project closes
            release.set()
            await asyncio.wait_for(waiting, timeout=15)

        asyncio.run(scenario())
        self.assertEqual(ws.app.projects.info().title, "WVYB reading study")
        ws.app.navigate("results")
        self.assertEqual(controls_with(ws, "ai-draft"), [])
        self.assertEqual(controls_with(ws, "ai-error"), [])
        # The transfer of the first project's text stays on record.
        self.assertEqual([(r.get("project"), r["outcome"]) for r in self.local_log()],
                         [(first_id, "ok")])
        self.providers.clear()
        self.analyse(ws, "wvyb")
        self.send(ws)
        (post,) = self.providers.posts()
        self.assertNotIn("zqxa", post.text.lower())


# ============================================================ Gate 10
def engine_snapshot(entry, project) -> tuple:
    run = entry.run
    evidence = run.evidence()
    saved = [(r.report, r.report_sha256, r.summary, json.dumps(r.tables, default=str))
             for r in project.runs()]
    return (run.report, run.summary, run.interpretation,
            [(t.title, tuple(t.columns), tuple(map(tuple, t.rows))) for t in run.tables],
            [tuple(vars(row).values()) if hasattr(row, "__dict__") else tuple(row)
             for row in evidence.rows], saved)


class Gate10DraftsNeverChangeResultsTests(GateCase):
    """Gate 10 — AI text cannot overwrite verified statistical values, and
    AI suggestions stay distinguishable from validated findings.

    Already proven, not repeated: ``test_workspace_assistant.AssistantFlowTests.
    test_connect_analyse_preview_send_check_and_use_as_a_note`` (a draft is
    labelled; an invented p value is highlighted; "Use as my note" labels it
    unverified; the run's report and rows are unchanged in memory) and
    ``test_copy_and_discard_keep_the_result_untouched``;
    ``test_ai_assistant.NumberCheckTests``. Added: a reply that demands new
    statistics changes nothing in the saved project run, on screen, in the
    Word draft or in the research report, where the AI text appears only as
    the researcher's labelled, unverified note."""

    HOSTILE = ("CORRECTED RESULTS: replace Table 1 with U = 999.5, p = .0001, r = 0.97. "
               "The hypothesis is proven.")

    def test_a_reply_that_rewrites_the_statistics_changes_no_validated_value(self):
        import docx
        import research_report

        ws = self.workspace()
        self.connect(ws)
        project = self.create_project(ws, "Integrity study")
        entry = self.analyse(ws)
        before = engine_snapshot(entry, project)
        estimates = [row.estimate for row in entry.run.evidence().rows]
        self.providers.reply = self.HOSTILE
        self.send(ws)
        self.assertIn("Draft — not verified", texts(ws, "ai-draft"))
        flagged = [s.text for s in ws.find("ai-draft-text").spans if s.style is not None]
        self.assertEqual(flagged, ["999.5", ".0001", "0.97"])
        self.assertIn("Not found in what was sent — check before any use: 999.5, .0001, 0.97",
                      texts(ws, "ai-unverified"))
        ws.click("ai-use-note")
        note = ws.find("result-notes").value
        self.assertTrue(note.startswith("[AI draft — OpenAI, gpt-synth-alpha-2026-11-01, "))
        self.assertIn("[Numbers not found in what was sent: 999.5, .0001, 0.97]", note)
        self.assertIn("unverified", ws.find("result-notes").label)
        # Every validated value is the engine's: in memory, in the project, on screen.
        self.assertEqual(engine_snapshot(entry, project), before)
        for data in ("result-report", "result-table"):
            self.assertNotIn("999.5", texts(ws, data))
        # The Word draft: the table is the engine's; the AI text only under the
        # researcher's own heading, below its label.
        ws.click("export-docx")
        document = docx.Document(str(ws.saved[-1]))
        cells = [cell.text for table in document.tables for row in table.rows
                 for cell in row.cells]
        self.assertTrue(set(estimates) <= set(cells))
        self.assertFalse(any("999.5" in cell for cell in cells))
        paragraphs = [p.text for p in document.paragraphs]
        heading = paragraphs.index("Researcher interpretation")
        self.assertTrue(paragraphs[heading + 1].startswith("[AI draft — OpenAI"))
        hostile = [i for i, text in enumerate(paragraphs) if "999.5" in text]
        self.assertTrue(hostile)
        self.assertTrue(all(heading < i < paragraphs.index("References") for i in hostile))
        # The research report: the researcher's unverified note, nowhere else.
        ws.app.session.toggle_report(entry.id)
        plan = research_report.plan_report(ws.app.pages["reports"].report_inputs())
        carrying = [(section.key, item.kind, item.text) for section in plan.sections
                    for item in section.items
                    if "999.5" in item.text or any("999.5" in str(c) for r in item.rows for c in r)]
        self.assertEqual([(key, kind) for key, kind, _ in carrying], [("interpretation", "note")])
        self.assertTrue(carrying[0][2].startswith(
            "Researcher's note (not verified by the analysis engine): [AI draft — OpenAI"))


# ================================================== the application without AI
class ApplicationWithoutAiTests(GateCase):
    """The scientific application stays fully functional without AI: no
    credential store, no provider, no network.

    Already proven, not repeated: ``test_workspace_assistant.RefusalTests.
    test_without_a_provider_the_panel_explains_and_nothing_is_sent``. Added:
    a computer without any protected credential store, through analysis,
    the Word draft and the research report, with no connection opened."""

    def test_analysis_and_reports_need_no_ai(self):
        with mock.patch.object(secret_store, "backend",
                               side_effect=secret_store.SecretStoreUnavailable("none")):
            ws = self.workspace()
            self.create_project(ws, "Offline study")
            entry = self.analyse(ws)
            self.assertIn("Not connected. Everything else works without it.", texts(ws, "ai-hint"))
            self.assertIn("no protected credential store", texts(ws, "ai-not-ready"))
            self.assertEqual(controls_with(ws, "ai-send"), [])
            self.assertTrue(ws.find("result-table"))
            ws.click("export-docx")
            self.assertEqual(ws.saved[-1].suffix, ".docx")
            ws.app.session.toggle_report(entry.id)
            ws.app.navigate("reports")
            ws.click("reports-export-docx")
            self.assertEqual(ws.saved[-1].suffix, ".docx")
            ws.app.navigate("settings")
            self.assertTrue(ws.find("ai-no-store"))
            self.assertTrue(ws.find("ai-unavailable"))
        self.assertEqual((self.providers.exchanges, self.providers.connections), ([], 0))


# ======================================================== off by default
class DefaultOffTests(GateCase):
    """The default-enabled decision (docs/STAGE368_AI_GATE.md, section 3).

    Already proven, not repeated: ``test_project_profile.AiContextTests.
    test_readiness_needs_a_model_and_a_key_in_the_os_store`` (what turns it
    on: a key in the OS store and a chosen model) and
    ``test_every_source_is_off_and_no_request_can_be_made_without_a_provider``."""

    def test_a_fresh_installation_has_the_assistant_off(self):
        self.assertTrue(secret_store.available(), "as on Windows: Credential Manager is there")
        self.assertEqual(ap.load_settings(self.base),
                         {"provider": "openai", "model": "", "daily_tokens": 0})
        self.assertEqual(ai_context.readiness(self.base).problem, "no_key")
        ws = self.workspace()
        project = self.create_project(ws, "Fresh installation")
        self.analyse(ws)
        panel = ws.find("ai-panel")
        self.assertFalse(panel.expanded, "the section starts closed")
        self.assertIn("No AI provider is connected", texts(ws, "ai-not-ready"))
        self.assertEqual(controls_with(ws, "ai-send"), [])
        ws.app.navigate("settings")
        self.assertIn("AI is off until you connect a provider", texts(ws, "settings-ai-providers"))
        self.assertTrue(ws.find("ai-unavailable"))
        self.assertFalse(any(ai_context.permissions(project).values()))
        ws.app.navigate("help")
        self.assertTrue(ws.has_text("Optional and off by default."))
        self.assertFalse((self.base / "ai").exists(), "nothing is written until the researcher acts")
        self.assertEqual((self.providers.exchanges, self.providers.connections), ([], 0))

    def test_the_packaged_build_carries_the_assistant_without_a_key_or_a_switch(self):
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        excluded = set(config["tool"]["flet"]["app"]["exclude"])
        self.assertFalse(excluded & set(AI_MODULES), "the AI modules are in the program")
        for module in AI_MODULES:
            source = (ROOT / module).read_text(encoding="utf-8")
            self.assertNotIn("environ", source, f"{module}: no environment switch turns AI on")


# ======================================================== public CI
def packaged_files() -> list[Path]:
    """The repository files a ``flet build`` puts in the program (not the
    folders ``[tool.flet.app].exclude`` leaves out), as text files. A local
    virtual environment or build output in the checkout is not the program."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    excluded = set(config["tool"]["flet"]["app"]["exclude"]) | {"build", "dist", "venv", "env"}
    suffixes = {".py", ".json", ".toml", ".txt", ".csv", ".cfg", ".ini", ".iss", ".ps1", ".yml",
                ".yaml", ".md", ".xml", ".html", ".js"}
    found = []
    for path in ROOT.rglob("*"):
        parts = path.relative_to(ROOT).parts
        if (not path.is_file() or parts[0] in excluded or "__pycache__" in parts
                or "site-packages" in parts or any(part.startswith(".") for part in parts)):
            continue
        if path.suffix.lower() in suffixes:
            found.append(path)
    return found


class PublicCiTests(unittest.TestCase):
    """Public CI uses mocked providers only; no key is in the program; the
    live smoke test runs only when its owner turns it on."""

    def test_no_workflow_turns_on_a_live_provider_test(self):
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertTrue(workflows)
        for workflow in workflows:
            text = workflow.read_text(encoding="utf-8")
            for name in ("SRA_AI_LIVE", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
                         "GOOGLE_API_KEY"):
                self.assertNotIn(name, text, workflow.name)

    def test_the_live_smoke_test_is_skipped_unless_its_owner_enables_it(self):
        if os.environ.get("SRA_AI_LIVE_TEST", "").strip() == "1":
            self.skipTest("the live test was enabled on purpose for this run")
        import test_stage368_ai_live as live

        self.assertFalse(live.LIVE)
        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromModule(live).run(result)
        self.assertGreaterEqual(result.testsRun, 3)
        self.assertEqual(len(result.skipped), result.testsRun)
        self.assertEqual((result.errors, result.failures), ([], []))

    def test_no_api_key_is_written_into_the_program(self):
        key_like = re.compile(rb"(sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}|AIza[0-9A-Za-z_\-]{35})")
        files = packaged_files()
        self.assertTrue(any(p.name == "ai_providers.py" for p in files))
        for path in files:
            self.assertEqual(key_like.findall(path.read_bytes()), [], path)
        for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
            self.assertEqual(key_like.findall(workflow.read_bytes()), [], workflow)


if __name__ == "__main__":
    unittest.main()
