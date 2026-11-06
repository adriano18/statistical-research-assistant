"""Signed update manifests (Stage 35, #45).

An update is described by a small JSON manifest that the release workflow
publishes next to the installer on GitHub Releases. The manifest is
**untrusted** until every check below passes; nothing it says is used
before that.

Envelope (one file, ``sra-update-<channel>.json``)::

    {"format": "sra-update/1",
     "payload": "<base64 of the manifest JSON bytes>",
     "signatures": [{"key": "<key id>", "ed25519": "<base64 signature>"}]}

The Ed25519 signature covers the exact payload bytes, so no JSON
canonicalisation is involved. The public keys a build trusts come from its
``build_info.json`` (written at build time from the signing secret's public
half); the private key exists only as a GitHub Actions secret.

Manifest (the payload)::

    {"format": 1, "app_id": "{8467540D-...}", "channel": "stable",
     "version": "1.1.0", "build": "57", "published_at": "2026-12-01T10:00:00Z",
     "minimum_version": "1.0.0", "project_format": 2,
     "installer": {"url": "https://github.com/.../StatisticalResearchAssistant-1.1.0-Setup.exe",
                   "size": 158000000, "sha256": "<64 hex>", "signed": true,
                   "publisher": "CN=..."},
     "changelog": {"en": "...", "lv": "...", "ru": "..."},
     "known_limitations": {"en": "..."},
     "release_notes_url": "https://github.com/.../releases/tag/v1.1.0"}
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app_identity import INSTALLER_APP_ID, BuildInfo, Version, parse_version

ENVELOPE_FORMAT = "sra-update/1"
MANIFEST_FORMAT = 1
MAX_ENVELOPE_BYTES = 256 * 1024
MIN_INSTALLER_BYTES = 1 * 1024 * 1024
MAX_INSTALLER_BYTES = 1024 * 1024 * 1024
MAX_TEXT = 20_000
# Hosts an update may be downloaded from (GitHub Releases and its CDN).
ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com")
LANGUAGES = ("en", "lv", "ru")


class ManifestError(Exception):
    """The manifest is not acceptable; ``reason`` is a stable key for the UI."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Installer:
    url: str
    size: int
    sha256: str
    signed: bool = False
    publisher: str = ""


@dataclass(frozen=True)
class Manifest:
    app_id: str
    channel: str
    version: Version
    build: str
    published_at: str
    minimum_version: Version
    project_format: int
    installer: Installer
    changelog: dict = field(default_factory=dict)
    known_limitations: dict = field(default_factory=dict)
    release_notes_url: str = ""

    def text(self, kind: str, language: str) -> str:
        values = self.changelog if kind == "changelog" else self.known_limitations
        return values.get(language) or values.get("en") or ""


def key_id(public_key_b64: str) -> str:
    raw = base64.b64decode(public_key_b64, validate=True)
    return hashlib.sha256(raw).hexdigest()[:16]


def _b64(value, what: str) -> bytes:
    if not isinstance(value, str):
        raise ManifestError("malformed", f"{what} is not text")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ManifestError("malformed", f"{what} is not base64") from error


def verify_envelope(data: bytes, trusted_keys: tuple[str, ...]) -> bytes:
    """The payload bytes, if at least one signature by a trusted key is valid."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not trusted_keys:
        raise ManifestError("no_keys", "this build trusts no update key")
    if len(data) > MAX_ENVELOPE_BYTES:
        raise ManifestError("malformed", "the update description is too large")
    try:
        envelope = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ManifestError("malformed", "the update description is not JSON") from error
    if not isinstance(envelope, dict) or envelope.get("format") != ENVELOPE_FORMAT:
        raise ManifestError("malformed", "unknown update description format")
    payload = _b64(envelope.get("payload"), "payload")
    signatures = envelope.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        raise ManifestError("unsigned", "the update description carries no signature")
    keys = {}
    for public in trusted_keys:
        try:
            keys[key_id(public)] = Ed25519PublicKey.from_public_bytes(base64.b64decode(public))
        except (binascii.Error, ValueError):
            continue
    for entry in signatures[:8]:
        if not isinstance(entry, dict):
            continue
        key = keys.get(entry.get("key"))
        if key is None:
            continue
        try:
            key.verify(_b64(entry.get("ed25519"), "signature"), payload)
            return payload
        except (InvalidSignature, ManifestError):
            continue
    raise ManifestError("bad_signature", "no valid signature by a key this build trusts")


def _text_map(value) -> dict:
    if not isinstance(value, dict):
        return {}
    return {lang: value[lang][:MAX_TEXT] for lang in LANGUAGES
            if isinstance(value.get(lang), str)}


def _https_url(value, *, allowed_origin: str = "") -> str:
    if not isinstance(value, str) or len(value) > 2000:
        raise ManifestError("bad_url", "the download address is missing")
    parts = urlsplit(value)
    if allowed_origin and value.startswith(allowed_origin):
        return value
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.port:
        raise ManifestError("bad_url", f"downloads are only accepted from GitHub over HTTPS, "
                                       f"not {parts.scheme}://{parts.hostname}")
    return value


def test_origin(build: BuildInfo) -> str:
    """http://127.0.0.1:<port> of a test build's local update server, else ''."""
    if build.channel != "test" or not build.test_endpoint:
        return ""
    parts = urlsplit(build.test_endpoint)
    if parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.port:
        return f"http://127.0.0.1:{parts.port}/"
    return ""


def parse_manifest(payload: bytes, build: BuildInfo) -> Manifest:
    """Validate a verified payload against this build; raise ManifestError."""
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ManifestError("malformed", "the manifest is not JSON") from error
    if not isinstance(raw, dict) or raw.get("format") != MANIFEST_FORMAT:
        raise ManifestError("malformed", "unknown manifest format")
    if raw.get("app_id") != INSTALLER_APP_ID:
        raise ManifestError("wrong_app", "the update is for another application")
    channel = raw.get("channel")
    accepted = {"stable": ("stable",), "preview": ("preview", "stable"),
                "test": ("test",)}.get(build.channel, ())
    if channel not in accepted:
        raise ManifestError("wrong_channel", f"a {channel!r} update is not offered to "
                                             f"{build.channel!r} builds")
    try:
        version = parse_version(raw.get("version", ""))
        minimum = parse_version(raw.get("minimum_version", "0.0.0"))
    except ValueError as error:
        raise ManifestError("malformed", str(error)) from error
    if channel == "stable" and version.prerelease:
        raise ManifestError("wrong_channel", "a stable update cannot be a pre-release")
    installer = raw.get("installer")
    if not isinstance(installer, dict):
        raise ManifestError("malformed", "the manifest names no installer")
    size, digest = installer.get("size"), installer.get("sha256")
    if not isinstance(size, int) or isinstance(size, bool) \
            or not MIN_INSTALLER_BYTES <= size <= MAX_INSTALLER_BYTES:
        raise ManifestError("malformed", "the installer size is not plausible")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ManifestError("malformed", "the installer checksum is not a SHA-256")
    url = _https_url(installer.get("url"), allowed_origin=test_origin(build))
    if not urlsplit(url).path.lower().endswith(".exe"):
        raise ManifestError("bad_url", "the download is not a Windows installer")
    project_format = raw.get("project_format", 0)
    if not isinstance(project_format, int) or isinstance(project_format, bool):
        project_format = 0
    notes = raw.get("release_notes_url", "")
    if not isinstance(notes, str) or not notes.startswith("https://github.com/"):
        notes = ""
    return Manifest(
        app_id=INSTALLER_APP_ID, channel=channel, version=version,
        build=str(raw.get("build", ""))[:40], published_at=str(raw.get("published_at", ""))[:40],
        minimum_version=minimum, project_format=project_format,
        installer=Installer(url=url, size=size, sha256=digest,
                            signed=installer.get("signed") is True,
                            publisher=str(installer.get("publisher", ""))[:300]),
        changelog=_text_map(raw.get("changelog")),
        known_limitations=_text_map(raw.get("known_limitations")),
        release_notes_url=notes,
    )


@dataclass(frozen=True)
class Offer:
    """What a check found: ``state`` is "update", "latest" or "manual"."""
    state: str
    manifest: Manifest | None = None
    reason: str = ""


def decide(manifest: Manifest, build: BuildInfo) -> Offer:
    """Whether this build should offer ``manifest``: never an older or equal
    version (no downgrade, no replay of an old manifest), never one this
    version cannot update to directly, never an unsigned installer when the
    build requires a signature."""
    current = build.parsed_version
    if manifest.version <= current:
        return Offer("latest", manifest)
    if manifest.minimum_version > current:
        return Offer("manual", manifest, "too_old")
    if build.require_signature:
        expected = build.publisher
        if not manifest.installer.signed:
            return Offer("manual", manifest, "unsigned")
        if expected and manifest.installer.publisher != expected:
            return Offer("manual", manifest, "wrong_publisher")
    return Offer("update", manifest)


def sign_payload(payload: bytes, private_key_b64: str) -> dict:
    """Release tooling only: an envelope with one signature."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    public = private.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
    public_b64 = base64.b64encode(public).decode()
    return {"format": ENVELOPE_FORMAT, "payload": base64.b64encode(payload).decode(),
            "signatures": [{"key": key_id(public_b64),
                            "ed25519": base64.b64encode(private.sign(payload)).decode()}]}
