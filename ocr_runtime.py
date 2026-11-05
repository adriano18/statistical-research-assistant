"""Locate and run a LOCAL Tesseract OCR engine with bounded resources.

Resolution order (first match wins):

1. ``TESSERACT_CMD`` — explicit developer override. If it is set but does
   not point to a file, OCR is reported as misconfigured; there is no
   silent fallback to another engine.
2. The bundled runtime shipped inside the Windows desktop package:
   ``ocr_runtime/windows-x64/`` containing ``bin/tesseract.exe``, its DLLs,
   ``tessdata/{eng,lav,rus,osd}.traineddata`` and ``MANIFEST.json``.
   ``SRA_OCR_RUNTIME_DIR`` may point to such a directory explicitly.
3. ``tesseract`` on the system ``PATH``.

``SRA_DISABLE_OCR=1`` disables OCR completely. No network access is used:
the engine runs as a subprocess on local temporary files that are removed
immediately afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time

BUNDLE_FOLDER = "ocr_runtime"
REQUIRED_LANGUAGES = ("eng", "lav", "rus")
MAX_OUTPUT_BYTES = 16_000_000
MAX_DIAGNOSTIC_CHARS = 400
ENV_OVERRIDE = "TESSERACT_CMD"
ENV_BUNDLE = "SRA_OCR_RUNTIME_DIR"
ENV_DISABLE = "SRA_DISABLE_OCR"


class OCRCancelled(RuntimeError):
    """Raised when a user cancels a running OCR job."""


def platform_tag() -> str | None:
    machine = platform.machine().lower()
    if os.name == "nt" and machine in {"amd64", "x86_64"}:
        return "windows-x64"
    return None


def _executable_name() -> str:
    return "tesseract.exe" if os.name == "nt" else "tesseract"


def bundle_candidates() -> list[Path]:
    """Bounded list of directories that may contain the packaged runtime."""
    found: list[Path] = []
    explicit = os.environ.get(ENV_BUNDLE, "").strip()
    if explicit:
        found.append(Path(explicit))
    tag = platform_tag()
    if tag:
        roots = [Path(__file__).resolve().parent]
        for anchor in (sys.executable, sys.argv[0] if sys.argv else ""):
            if anchor:
                roots.append(Path(anchor).resolve().parent)
        for root in roots:
            for candidate in (root / BUNDLE_FOLDER / tag,
                              root.parent / BUNDLE_FOLDER / tag):
                if candidate not in found:
                    found.append(candidate)
    return found[:8]


@dataclass(frozen=True)
class TesseractRuntime:
    executable: Path
    origin: str  # "override" | "bundled" | "path"
    tessdata_dir: Path | None = None
    bundle_dir: Path | None = None

    def command(self, *arguments: str) -> list[str]:
        command = [str(self.executable)]
        if self.tessdata_dir is not None:
            command += ["--tessdata-dir", str(self.tessdata_dir)]
        return command + list(arguments)

    def environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env["OMP_THREAD_LIMIT"] = env.get("OMP_THREAD_LIMIT", "2")
        if self.tessdata_dir is not None:
            env["TESSDATA_PREFIX"] = str(self.tessdata_dir)
        if self.origin == "bundled":
            # Prefer bundled DLLs; Windows also searches the exe folder first.
            env["PATH"] = str(self.executable.parent) + os.pathsep + env.get("PATH", "")
        return env


@dataclass(frozen=True)
class BundleCheck:
    ok: bool
    problems: tuple[str, ...]
    files_checked: int
    hashed: bool


def verify_bundle(folder: Path, *, full_hash: bool = False) -> BundleCheck:
    """Check a bundled runtime against its MANIFEST (size, optional SHA-256)."""
    folder = Path(folder)
    manifest_path = folder / "MANIFEST.json"
    problems = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest["files"]
        if not isinstance(files, list) or not files:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        return BundleCheck(False, ("Bundled OCR manifest is missing or unreadable.",), 0, False)
    checked = 0
    for entry in files[:5000]:
        try:
            relative = Path(entry["path"])
            size, digest = int(entry["size"]), str(entry["sha256"])
        except (KeyError, TypeError, ValueError):
            problems.append("Manifest contains an invalid entry.")
            continue
        if relative.is_absolute() or ".." in relative.parts:
            problems.append(f"Unsafe manifest path: {relative}")
            continue
        target = folder / relative
        try:
            actual = target.stat().st_size
        except OSError:
            problems.append(f"Missing bundled file: {relative.as_posix()}")
            continue
        if actual != size:
            problems.append(f"Corrupt bundled file (size): {relative.as_posix()}")
            continue
        if full_hash:
            sha = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    sha.update(chunk)
            if sha.hexdigest() != digest:
                problems.append(f"Corrupt bundled file (SHA-256): {relative.as_posix()}")
                continue
        checked += 1
    for code in REQUIRED_LANGUAGES:
        if not (folder / "tessdata" / f"{code}.traineddata").is_file():
            problems.append(f"Bundled language data missing: {code}")
    return BundleCheck(not problems, tuple(problems[:20]), checked, full_hash)


def _bundle_runtime(folder: Path) -> TesseractRuntime | None:
    executable = folder / "bin" / _executable_name()
    if not executable.is_file():
        return None
    tessdata = folder / "tessdata"
    return TesseractRuntime(
        executable, "bundled", tessdata if tessdata.is_dir() else None, folder,
    )


class OCRConfigurationError(RuntimeError):
    """OCR is disabled or points at a missing engine."""


def resolve_tesseract() -> TesseractRuntime:
    """Return the engine to use or raise :class:`OCRConfigurationError`."""
    if os.environ.get(ENV_DISABLE, "").strip() in {"1", "true", "yes"}:
        raise OCRConfigurationError("Local OCR is disabled by SRA_DISABLE_OCR.")
    override = os.environ.get(ENV_OVERRIDE, "").strip().strip('"')
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return TesseractRuntime(path, "override")
        found = shutil.which(override)
        if found:
            return TesseractRuntime(Path(found), "override")
        raise OCRConfigurationError(
            f"TESSERACT_CMD is set but does not point to an executable: {override}"
        )
    for folder in bundle_candidates():
        runtime = _bundle_runtime(folder)
        if runtime is not None:
            return runtime
    found = shutil.which("tesseract")
    if found:
        return TesseractRuntime(Path(found), "path")
    raise OCRConfigurationError(
        "Local Tesseract OCR is not installed. The Windows desktop package "
        "includes it; for a source checkout install Tesseract with the eng, "
        "lav and rus language packs or set TESSERACT_CMD."
    )


def tesseract_available() -> bool:
    try:
        resolve_tesseract()
    except OCRConfigurationError:
        return False
    return True


def run_tesseract(
    runtime: TesseractRuntime, arguments: list[str], *, image: bytes | None = None,
    timeout: float = 60, cancel: threading.Event | None = None,
    max_output: int = MAX_OUTPUT_BYTES,
) -> tuple[int, bytes, str]:
    """Run Tesseract with a deadline, cancellation and bounded stdout.

    When ``image`` is given it is written to a private temporary PNG whose
    path replaces the literal argument ``"{image}"``. All temporary files are
    deleted before returning.
    """
    if not 0 < timeout <= 600:
        raise ValueError("OCR timeout must be 1–600 seconds.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with TemporaryDirectory(prefix="sra-ocr-") as folder:
        args = list(arguments)
        if image is not None:
            source = Path(folder) / "page.png"
            source.write_bytes(image)
            args = [str(source) if a == "{image}" else a for a in args]
        error_path = Path(folder) / "stderr.txt"
        with error_path.open("wb") as error_stream:
            try:
                process = subprocess.Popen(
                    runtime.command(*args), stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=error_stream,
                    env=runtime.environment(), cwd=folder, creationflags=flags,
                )
            except OSError as error:
                raise RuntimeError(
                    "The OCR engine could not start. A bundled DLL may be "
                    f"missing or blocked: {error}"
                ) from error
            reason = []

            def watchdog():
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    if cancel is not None and cancel.is_set():
                        reason.append("cancel")
                        process.kill()
                        return
                    if time.monotonic() > deadline:
                        reason.append("timeout")
                        process.kill()
                        return
                    time.sleep(0.05)

            guard = threading.Thread(target=watchdog, daemon=True)
            guard.start()
            chunks, total = [], 0
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_output:
                    reason.append("output")
                    process.kill()
                    break
                chunks.append(chunk)
            process.stdout.close()
            code = process.wait()
            guard.join(timeout=1)
        diagnostic = error_path.read_text(
            encoding="utf-8", errors="replace",
        ).strip()[-MAX_DIAGNOSTIC_CHARS:]
    if "cancel" in reason:
        raise OCRCancelled("OCR was cancelled. No results were applied.")
    if "timeout" in reason:
        raise RuntimeError("Local OCR exceeded its time limit.")
    if "output" in reason:
        raise RuntimeError("Local OCR output exceeded the safety limit.")
    return code, b"".join(chunks), diagnostic


@dataclass(frozen=True)
class OCRReadiness:
    available: bool
    origin: str | None
    executable: str | None
    version: str | None
    languages: tuple[str, ...]
    missing_languages: tuple[str, ...]
    problems: tuple[str, ...]
    bundle_verified: bool | None

    def summary(self) -> str:
        if not self.available:
            return "Local OCR unavailable: " + "; ".join(self.problems or ("unknown",))
        origin = {
            "bundled": "bundled with this application",
            "override": "TESSERACT_CMD developer override",
            "path": "system installation on PATH",
        }.get(self.origin or "", self.origin or "")
        languages = ", ".join(self.languages) or "none"
        text = f"{self.version or 'Tesseract'} · {origin} · languages: {languages}"
        if self.missing_languages:
            text += " · missing: " + ", ".join(self.missing_languages)
        if self.bundle_verified is True:
            text += " · bundle integrity verified"
        if self.problems:
            text += " · " + "; ".join(self.problems)
        return text


_READINESS_CACHE: dict[tuple, OCRReadiness] = {}


def ocr_readiness(*, full_hash: bool = False, use_cache: bool = True) -> OCRReadiness:
    """Probe engine version and installed languages (bounded, cached)."""
    key = (
        os.environ.get(ENV_OVERRIDE), os.environ.get(ENV_BUNDLE),
        os.environ.get(ENV_DISABLE), os.environ.get("PATH"), full_hash,
    )
    if use_cache and key in _READINESS_CACHE:
        return _READINESS_CACHE[key]
    try:
        runtime = resolve_tesseract()
    except OCRConfigurationError as error:
        result = OCRReadiness(False, None, None, None, (), REQUIRED_LANGUAGES,
                              (str(error),), None)
        _READINESS_CACHE[key] = result
        return result
    problems: list[str] = []
    verified = None
    if runtime.origin == "bundled" and runtime.bundle_dir is not None:
        check = verify_bundle(runtime.bundle_dir, full_hash=full_hash)
        verified = check.ok
        problems.extend(check.problems)
    version = None
    languages: tuple[str, ...] = ()
    try:
        code, out, err = run_tesseract(runtime, ["--version"], timeout=20)
        text = (out.decode("utf-8", "replace") + "\n" + err).strip()
        first = next((l.strip() for l in text.splitlines() if l.strip()), "")
        if code == 0 and first.lower().startswith("tesseract"):
            version = first
        else:
            problems.append("Engine did not report a version. " + err[-160:])
        code, out, err = run_tesseract(runtime, ["--list-langs"], timeout=20)
        if code == 0:
            listed = (out.decode("utf-8", "replace") + "\n" + err).splitlines()
            languages = tuple(sorted({
                l.strip() for l in listed
                if l.strip() and " " not in l.strip() and ":" not in l
            }))
        else:
            problems.append("Engine could not list language data. " + err[-160:])
    except RuntimeError as error:
        problems.append(str(error))
    missing = tuple(code for code in REQUIRED_LANGUAGES if code not in languages)
    result = OCRReadiness(
        version is not None, runtime.origin, str(runtime.executable), version,
        languages, missing, tuple(problems), verified,
    )
    _READINESS_CACHE[key] = result
    return result
