"""Checking for, downloading, verifying and starting an update (#45).

The researcher's side of an update, in order:

1. ``check``: fetch the channel's signed manifest over HTTPS (GitHub only),
   verify its signature, then the app, channel and version rules
   (``update_manifest``). A failed check never blocks anything.
2. ``download``: the installer, into ``<data folder>/updates`` (resumable,
   cancellable, never larger than announced); then its SHA-256.
3. ``verify_installer``: the checksum again and the Windows code signature.
   A build that requires a signature accepts only the pinned publisher;
   an unsigned preview build accepts an unsigned installer (its integrity
   then rests on the signed manifest and the checksum) but never a
   tampered or unknown signature.
4. ``prepare``: back up every project database and the profile, and record
   the update in ``updates/pending.json``.
5. ``launch_installer``: start the verified installer with
   ``/UPDATEFROMAPP``; the application then closes itself. Setup waits for
   it, replaces the program (never the data folder) and starts it again.
6. ``finish`` (next start): confirm the new version, check that every
   project is still there and report it.

Nothing downloaded is executed before steps 2 and 3 pass, and only the
installer file this module wrote is ever started.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import sqlite3
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import app_identity
import update_manifest as um

CHUNK = 256 * 1024
MANIFEST_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60
CHECK_INTERVAL = timedelta(hours=20)
KEEP_UPDATE_BACKUPS = 3
STATE = "state.json"
PENDING = "pending.json"
HISTORY = "history.json"


class UpdateError(Exception):
    """``reason`` is a stable key for the interface, ``detail`` for the log."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


# ------------------------------------------------------------------- HTTP

def _allowed(url: str, build: app_identity.BuildInfo) -> bool:
    origin = um.test_origin(build)
    if origin and url.startswith(origin):
        return True
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.hostname in um.ALLOWED_HOSTS
            and not parts.username and not parts.port)


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to an allowed host over HTTPS (GitHub sends
    release downloads to its own download hosts)."""

    def __init__(self, build):
        super().__init__()
        self.build = build

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed(newurl, self.build):
            raise UpdateError("bad_url", f"redirected to a host that is not allowed: "
                                         f"{urlsplit(newurl).hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, build: app_identity.BuildInfo, *, headers=None, timeout: float):
    if not _allowed(url, build):
        raise UpdateError("bad_url", f"not an allowed update address: {url}")
    opener = urllib.request.build_opener(
        _CheckedRedirects(build), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={
        "User-Agent": f"StatisticalResearchAssistant/{build.version}", **(headers or {})})
    try:
        return opener.open(request, timeout=timeout)
    except UpdateError:
        raise
    except urllib.error.HTTPError as error:
        raise UpdateError("unavailable", f"HTTP {error.code}") from error
    except (urllib.error.URLError, OSError, ssl.SSLError, http.client.HTTPException) as error:
        raise UpdateError("offline", str(getattr(error, "reason", error))) from error


# ------------------------------------------------------------------ check

def manifest_url(build: app_identity.BuildInfo) -> str:
    return build.test_endpoint if um.test_origin(build) else build.endpoint


def check(build: app_identity.BuildInfo | None = None) -> um.Offer:
    """Ask the channel's update server; raise UpdateError on any failure."""
    build = build or app_identity.build_info()
    url = manifest_url(build)
    if not build.distributed or not url or not build.update_keys:
        raise UpdateError("not_configured", "this build has no update channel")
    with _open(url, build, timeout=MANIFEST_TIMEOUT) as response:
        try:
            data = response.read(um.MAX_ENVELOPE_BYTES + 1)
        except (OSError, http.client.HTTPException) as error:
            raise UpdateError("offline", str(error)) from error
    try:
        payload = um.verify_envelope(data, build.update_keys)
        manifest = um.parse_manifest(payload, build)
    except um.ManifestError as error:
        raise UpdateError(error.reason, error.detail) from error
    except ImportError as error:        # no signature library: never trust unverified data
        raise UpdateError("no_keys", str(error)) from error
    return um.decide(manifest, build)


# --------------------------------------------------------------- download

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def installer_path(folder: Path, manifest: um.Manifest) -> Path:
    return Path(folder) / f"StatisticalResearchAssistant-{manifest.version}-Setup.exe"


def download(manifest: um.Manifest, folder: Path, build: app_identity.BuildInfo, *,
             progress=None, cancel=None) -> Path:
    """The verified installer in ``folder``; resumes an interrupted download."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    final = installer_path(folder, manifest)
    expected = manifest.installer
    if final.is_file():
        if final.stat().st_size == expected.size and sha256(final) == expected.sha256:
            return final
        final.unlink()
    part = final.with_name(final.name + ".part")
    have = part.stat().st_size if part.is_file() else 0
    if have >= expected.size:
        part.unlink()
        have = 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with _open(expected.url, build, headers=headers, timeout=DOWNLOAD_TIMEOUT) as response:
        resumed = bool(have) and getattr(response, "status", 200) == 206
        done = have if resumed else 0
        with open(part, "ab" if resumed else "wb") as out:
            while True:
                if cancel is not None and cancel.is_set():
                    raise UpdateError("cancelled")
                try:
                    chunk = response.read(CHUNK)
                except (OSError, ssl.SSLError, http.client.HTTPException) as error:
                    raise UpdateError("interrupted", str(error) or type(error).__name__) from error
                if not chunk:
                    break
                done += len(chunk)
                if done > expected.size:
                    out.close()
                    part.unlink(missing_ok=True)
                    raise UpdateError("damaged", "the download is larger than announced")
                out.write(chunk)
                if progress is not None:
                    progress(done, expected.size)
    if part.stat().st_size != expected.size:
        raise UpdateError("interrupted", f"{part.stat().st_size} of {expected.size} bytes")
    if sha256(part) != expected.sha256:
        part.unlink(missing_ok=True)
        raise UpdateError("damaged", "the checksum of the download does not match")
    os.replace(part, final)
    return final


# ------------------------------------------------------- code signature

_STATUS = {0: "Valid", 0x800B0100: "NotSigned", 0x800B0003: "NotSigned", 0x800B0001: "NotSigned",
           0x80096010: "HashMismatch", 0x800B0109: "NotTrusted", 0x800B010A: "NotTrusted",
           0x800B0004: "NotTrusted", 0x800B0111: "NotTrusted", 0x800B0101: "NotTrusted"}


def _win_verify_trust(path: Path) -> str:
    """Windows' own Authenticode verification (WinVerifyTrust), no network."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class FILE_INFO(ctypes.Structure):
        _fields_ = [("cbStruct", wintypes.DWORD), ("pcwszFilePath", wintypes.LPCWSTR),
                    ("hFile", wintypes.HANDLE), ("pgKnownSubject", ctypes.c_void_p)]

    class TRUST_DATA(ctypes.Structure):
        _fields_ = [("cbStruct", wintypes.DWORD), ("pPolicyCallbackData", ctypes.c_void_p),
                    ("pSIPClientData", ctypes.c_void_p), ("dwUIChoice", wintypes.DWORD),
                    ("fdwRevocationChecks", wintypes.DWORD), ("dwUnionChoice", wintypes.DWORD),
                    ("pFile", ctypes.POINTER(FILE_INFO)), ("dwStateAction", wintypes.DWORD),
                    ("hWVTStateData", wintypes.HANDLE), ("pwszURLReference", wintypes.LPCWSTR),
                    ("dwProvFlags", wintypes.DWORD), ("dwUIContext", wintypes.DWORD),
                    ("pSignatureSettings", ctypes.c_void_p)]

    action = GUID(0x00AAC56B, 0xCD44, 0x11D0, (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE))
    file_info = FILE_INFO(ctypes.sizeof(FILE_INFO), str(path), None, None)
    data = TRUST_DATA()
    data.cbStruct = ctypes.sizeof(TRUST_DATA)
    data.dwUIChoice = 2                  # WTD_UI_NONE
    data.fdwRevocationChecks = 0         # WTD_REVOKE_NONE
    data.dwUnionChoice = 1               # WTD_CHOICE_FILE
    data.pFile = ctypes.pointer(file_info)
    data.dwProvFlags = 0x1000            # WTD_CACHE_ONLY_URL_RETRIEVAL: never the network
    verify = ctypes.WinDLL("wintrust").WinVerifyTrust
    verify.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), ctypes.POINTER(TRUST_DATA)]
    verify.restype = ctypes.c_long
    result = verify(wintypes.HANDLE(-1), ctypes.byref(action), ctypes.byref(data)) & 0xFFFFFFFF
    return _STATUS.get(result, "UnknownError")


def _signer(path: Path) -> tuple[str, str]:
    """Subject and thumbprint of a signed file (only asked for signed files)."""
    system = os.environ.get("SystemRoot", r"C:\Windows")
    shell = Path(system) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    environment = {**os.environ, "SRA_VERIFY_PATH": str(path)}
    for name, value in (("SystemDrive", system[:2]), ("ProgramFiles", system[:2] + r"\Program Files"),
                        ("ProgramData", system[:2] + r"\ProgramData")):
        environment.setdefault(name, value)
    script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:SRA_VERIFY_PATH; "
              "[pscustomobject]@{subject = [string]$s.SignerCertificate.Subject; "
              "thumbprint = [string]$s.SignerCertificate.Thumbprint} | ConvertTo-Json -Compress")
    try:
        done = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, text=True, timeout=90, check=False, env=environment,
                              stdin=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        result = json.loads(done.stdout.strip() or "{}")
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return "", ""
    return str(result.get("subject") or ""), str(result.get("thumbprint") or "").upper()


def authenticode(path: Path) -> dict:
    """Windows code signature of ``path``: status, signer subject, thumbprint."""
    if os.name != "nt":
        return {"status": "unavailable"}
    status = _win_verify_trust(path)
    subject = thumbprint = ""
    if status not in ("NotSigned", "UnknownError"):
        subject, thumbprint = _signer(path)
    return {"status": status, "subject": subject, "thumbprint": thumbprint}


def verify_installer(path: Path, manifest: um.Manifest, build: app_identity.BuildInfo) -> dict:
    """Checksum and code signature; raise UpdateError unless both are right."""
    if sha256(path) != manifest.installer.sha256:
        raise UpdateError("damaged", "the checksum does not match the signed manifest")
    signature = authenticode(path)
    status = signature["status"]
    if build.require_signature:
        if status != "Valid":
            raise UpdateError("bad_code_signature", f"code signature status {status}")
        pinned = set(build.publisher_thumbprints)
        if pinned and signature["thumbprint"] not in pinned:
            raise UpdateError("wrong_publisher", signature["subject"])
        if build.publisher and signature["subject"] != build.publisher:
            raise UpdateError("wrong_publisher", signature["subject"])
    elif status not in ("NotSigned", "Valid", "unavailable"):
        # Signed, but the signature is broken or unknown: never run it.
        raise UpdateError("bad_code_signature", f"code signature status {status}")
    return signature


# ------------------------------------------------------------ the handoff

def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=1)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def project_ids(projects_root: Path) -> list[str]:
    return sorted(p.parent.name for p in Path(projects_root).glob("*/project.sqlite3")
                  if not p.parent.name.startswith("."))


def backup_before_update(data_root: Path, label: str) -> Path:
    """A copy of every project database and of the profile (small: datasets
    and figures are immutable files the update never touches)."""
    data_root = Path(data_root)
    target = data_root / "projects" / ".backups" / f"update-{label}"
    target.mkdir(parents=True, exist_ok=True)
    for database in sorted((data_root / "projects").glob("*/project.sqlite3")):
        if database.parent.name.startswith("."):
            continue
        uri = database.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as source, \
                closing(sqlite3.connect(target / f"{database.parent.name}.sqlite3")) as copy:
            source.backup(copy)
    profile = data_root / "profile" / "profile.json"
    if profile.is_file():
        shutil.copy2(profile, target / "profile.json")
    older = sorted((p for p in target.parent.glob("update-*") if p.is_dir()),
                   key=lambda p: p.stat().st_mtime)
    for stale in older[:-KEEP_UPDATE_BACKUPS]:
        shutil.rmtree(stale, ignore_errors=True)
    return target


def prepare(data_root: Path, installer: Path, manifest: um.Manifest,
            build: app_identity.BuildInfo) -> dict:
    data_root = Path(data_root)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_before_update(data_root, f"{build.version}-to-{manifest.version}-{stamp}")
    record = {"from": build.version, "to": str(manifest.version), "installer": str(installer),
              "sha256": manifest.installer.sha256, "started_at": _now(), "backup": str(backup),
              "projects": project_ids(data_root / "projects"),
              "log": str(data_root / "updates" / f"install-{manifest.version}.log"),
              "changelog": manifest.changelog, "release_notes_url": manifest.release_notes_url}
    _write_json(data_root / "updates" / PENDING, record)
    return record


def launch_installer(record: dict) -> subprocess.Popen:
    """Start the verified installer; the caller then closes the application."""
    installer = Path(record["installer"])
    flags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_BREAKAWAY_FROM_JOB"):
        flags |= getattr(subprocess, name, 0)
    command = [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATEFROMAPP",
               f"/LOG={record['log']}"]
    try:
        return subprocess.Popen(command, cwd=str(installer.parent), creationflags=flags,
                                close_fds=True)
    except OSError:
        # Some job objects forbid breaking away: start it inside the job then.
        flags &= ~getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        return subprocess.Popen(command, cwd=str(installer.parent), creationflags=flags,
                                close_fds=True)


def finish(data_root: Path, build: app_identity.BuildInfo | None = None) -> dict | None:
    """On start: the outcome of an update started by an earlier run, if any."""
    build = build or app_identity.build_info()
    data_root = Path(data_root)
    pending_path = data_root / "updates" / PENDING
    record = _read_json(pending_path)
    if not record:
        return None
    present = set(project_ids(data_root / "projects"))
    missing = [pid for pid in record.get("projects", []) if pid not in present]
    try:
        reached = app_identity.parse_version(build.version) == app_identity.parse_version(
            record.get("to", "0.0.0"))
    except ValueError:
        reached = False
    outcome = {**record, "state": "updated" if reached else "not_installed",
               "finished_at": _now(), "now": build.version, "missing_projects": missing,
               "projects_kept": len(record.get("projects", [])) - len(missing)}
    history = _read_json(data_root / "updates" / HISTORY)
    history.setdefault("updates", []).append(outcome)
    history["updates"] = history["updates"][-20:]
    _write_json(data_root / "updates" / HISTORY, history)
    pending_path.unlink(missing_ok=True)
    if reached:
        clean_cache(data_root)
    return outcome


def clean_cache(data_root: Path) -> list[str]:
    """Remove downloaded installers no pending update needs. An installer
    that is still running (it starts the new version, then exits) cannot be
    deleted yet; it is removed on a later start."""
    folder = Path(data_root) / "updates"
    keep = _read_json(folder / PENDING).get("installer", "")
    removed = []
    for path in folder.glob("StatisticalResearchAssistant-*-Setup.exe*"):
        if keep and os.path.normcase(str(path)) == os.path.normcase(keep):
            continue
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue
    return removed


# ------------------------------------------------------------- preferences

def state(data_root: Path) -> dict:
    value = _read_json(Path(data_root) / "updates" / STATE)
    value.setdefault("automatic", True)
    return value


def save_state(data_root: Path, value: dict) -> None:
    _write_json(Path(data_root) / "updates" / STATE, value)


def due(data_root: Path, now: datetime | None = None) -> bool:
    """Automatic checks: enabled and not done in the last CHECK_INTERVAL."""
    current = state(data_root)
    if not current.get("automatic", True):
        return False
    try:
        last = datetime.fromisoformat(current.get("last_check", ""))
    except ValueError:
        return True
    return (now or datetime.now(timezone.utc)) - last >= CHECK_INTERVAL


def remember_check(data_root: Path, offer: um.Offer | None) -> None:
    current = state(data_root)
    current["last_check"] = _now()
    if offer is not None and offer.manifest is not None:
        current["last_seen"] = str(offer.manifest.version)
    save_state(data_root, current)


def snooze(data_root: Path, version: str, days: int = 7) -> None:
    current = state(data_root)
    current["snoozed"] = {"version": version,
                          "until": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()}
    save_state(data_root, current)


def snoozed(data_root: Path, version: str) -> bool:
    entry = state(data_root).get("snoozed") or {}
    if entry.get("version") != version:
        return False
    try:
        return datetime.now(timezone.utc) < datetime.fromisoformat(entry.get("until", ""))
    except ValueError:
        return False
