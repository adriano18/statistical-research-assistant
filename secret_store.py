"""API keys in the operating system's credential store (Stage 35, #43).

Bring-your-own-key: the researcher's key for an AI provider is kept in the
Windows Credential Manager (a generic credential named
``StatisticalResearchAssistant/ai/<provider>``), or in the system keychain
through ``keyring`` elsewhere. It is never written to a project, a ``.sra``
backup, the preferences, a log or a report, and the application contains no
key of its own. Without an OS-protected store, keys are not kept at all:
there is no plain-text fallback.
"""

from __future__ import annotations

import os

SERVICE = "StatisticalResearchAssistant"
MAX_KEY_LENGTH = 512


class SecretStoreUnavailable(Exception):
    """No OS-protected credential store on this computer."""


def _target(provider: str) -> str:
    if not provider.isidentifier():
        raise ValueError(f"Not a provider name: {provider!r}")
    return f"{SERVICE}/ai/{provider}"


class _WindowsCredentials:
    """CredWriteW / CredReadW / CredDeleteW (generic credentials)."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                        ("LastWritten", FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        self.ctypes, self.CREDENTIAL = ctypes, CREDENTIAL
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self.write = advapi.CredWriteW
        self.write.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        self.write.restype = wintypes.BOOL
        self.read = advapi.CredReadW
        self.read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        self.read.restype = wintypes.BOOL
        self.delete = advapi.CredDeleteW
        self.delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.delete.restype = wintypes.BOOL
        self.free = advapi.CredFree
        self.free.argtypes = [ctypes.c_void_p]

    GENERIC, LOCAL_MACHINE, NOT_FOUND = 1, 2, 1168

    def set(self, target: str, secret: str) -> None:
        ctypes = self.ctypes
        blob = secret.encode("utf-16-le")
        credential = self.CREDENTIAL()
        credential.Type = self.GENERIC
        credential.TargetName = target
        credential.UserName = SERVICE
        credential.CredentialBlobSize = len(blob)
        buffer = ctypes.create_string_buffer(blob, len(blob))     # alive during the call
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        credential.Persist = self.LOCAL_MACHINE    # this user, this computer
        if not self.write(ctypes.byref(credential), 0):
            raise OSError(ctypes.get_last_error(), "CredWriteW failed")

    def get(self, target: str) -> str | None:
        ctypes = self.ctypes
        pointer = ctypes.POINTER(self.CREDENTIAL)()
        if not self.read(target, self.GENERIC, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == self.NOT_FOUND:
                return None
            raise OSError(ctypes.get_last_error(), "CredReadW failed")
        try:
            size = pointer.contents.CredentialBlobSize
            return ctypes.string_at(pointer.contents.CredentialBlob, size).decode("utf-16-le")
        finally:
            self.free(pointer)

    def remove(self, target: str) -> bool:
        if self.delete(target, self.GENERIC, 0):
            return True
        if self.ctypes.get_last_error() == self.NOT_FOUND:
            return False
        raise OSError(self.ctypes.get_last_error(), "CredDeleteW failed")


class _Keyring:
    def __init__(self):
        import keyring  # noqa: F401 - optional, the system keychain elsewhere

        self.keyring = keyring

    def set(self, target, secret):
        self.keyring.set_password(SERVICE, target, secret)

    def get(self, target):
        return self.keyring.get_password(SERVICE, target)

    def remove(self, target):
        try:
            self.keyring.delete_password(SERVICE, target)
            return True
        except Exception:
            return False


_BACKEND = None


def backend():
    """The OS credential store, or raise SecretStoreUnavailable."""
    global _BACKEND
    if _BACKEND is None:
        try:
            _BACKEND = _WindowsCredentials() if os.name == "nt" else _Keyring()
        except Exception as error:
            raise SecretStoreUnavailable(
                "This computer offers no protected credential store; keys are not kept.") from error
    return _BACKEND


def available() -> bool:
    try:
        backend()
        return True
    except SecretStoreUnavailable:
        return False


def set_key(provider: str, key: str) -> None:
    key = (key or "").strip()
    if not key or len(key) > MAX_KEY_LENGTH or any(ch.isspace() for ch in key):
        raise ValueError("This does not look like an API key.")
    backend().set(_target(provider), key)


def get_key(provider: str) -> str | None:
    return backend().get(_target(provider))


def has_key(provider: str) -> bool:
    try:
        return bool(get_key(provider))
    except (SecretStoreUnavailable, OSError):
        return False


def remove_key(provider: str) -> bool:
    return backend().remove(_target(provider))


def redact(text: str, *secrets: str) -> str:
    """``text`` with every given secret (and anything key-like) masked."""
    import re

    for secret in secrets:
        if secret:
            text = text.replace(secret, "••••")
    return re.sub(r"(sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,})", "••••", text)
