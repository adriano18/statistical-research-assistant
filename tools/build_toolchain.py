"""Pinned build toolchain of the Windows program (Stage 36.8, issue #62).

    python tools/build_toolchain.py flutter
        The Flutter SDK of the lock in ~/flutter/<version>, its archive checked
        by SHA-256 first. `flet build` finds it there and uses it; on its own,
        flet-cli downloads the SDK without any check.
    python tools/build_toolchain.py template --out DIR [--github-output]
        The flet build template of the lock, checked by SHA-256, plus the
        locked Dart packages (packaging/flutter/pubspec.lock) once that file
        exists. Pass the printed folder to `flet build --template`.
    python tools/build_toolchain.py iscc
        The Inno Setup compiler of the lock; installs that version with
        Chocolatey when the runner has another one.
    python tools/build_toolchain.py identity --bundle build/windows --out FILE [--strict]
        What a build was made with, checked against the locks: host Python and
        packages, flet and flet-cli, the Flutter SDK, the Dart packages and the
        Python packages inside the bundle. --strict exits 1 on any deviation.
    python tools/build_toolchain.py manifest DIR --out FILE
        SHA-256 of every file of a folder (a bundle or an installed program).
    python tools/build_toolchain.py compare A.json B.json [--markdown FILE]
        Two manifests of the same commit built on two clean runners: identical
        files, and every deviation with its kind (zip metadata, PE link
        timestamp, .pyc header, build metadata, content).

The lock is packaging/build_toolchain.lock.json; the Python package locks are
requirements.txt (bundled) and requirements-dev.txt (build and test tools).
`flutter`, `template`, `manifest` and `compare` use the standard library only,
because they run before any package is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "packaging" / "build_toolchain.lock.json"
RUNTIME_LOCK = ROOT / "requirements.txt"
DEV_LOCK = ROOT / "requirements-dev.txt"
OCR_LOCK = ROOT / "packaging" / "windows_ocr_runtime.lock.json"
# Installer tools of the host Python itself, never in a lock, and pipx with
# its dependencies, which GitHub's Windows toolcache Python ships with
# (seen on windows-2025-vs2026 20261103.298). None of them enters the bundle,
# which is checked against requirements.txt on its own.
HOST_TOOLS = {"pip", "setuptools", "wheel",
              "pipx", "argcomplete", "filelock", "platformdirs", "userpath"}
_CHUNK = 1 << 20


def load_lock(path: Path = LOCK) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path, sha256: str) -> Path:
    """Download ``url`` to ``dest`` and refuse it unless its SHA-256 matches."""
    if not url.startswith("https://"):
        raise SystemExit(f"Refusing a non-HTTPS download: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "sra-build-toolchain"})
    with urllib.request.urlopen(request, timeout=120) as response, open(dest, "wb") as out:
        for block in iter(lambda: response.read(_CHUNK), b""):
            digest.update(block)
            out.write(block)
    if digest.hexdigest() != sha256:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"SHA-256 mismatch for {url}: got {digest.hexdigest()}, "
                         f"the lock says {sha256}")
    return dest


# --- Python package locks ---------------------------------------------------

@dataclass
class Pin:
    name: str
    version: str
    marker: str = ""
    hashes: list = field(default_factory=list)


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(path: Path) -> list[Pin]:
    """Pins of a `uv pip compile --generate-hashes` file (requirements format)."""
    logical, current = [], ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            if current:
                logical.append(current)
                current = ""
            continue
        if line.endswith("\\"):
            current += line[:-1] + " "
        else:
            logical.append(current + line)
            current = ""
    if current:
        logical.append(current)
    pins = []
    for entry in logical:
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", entry)
        spec = re.sub(r"--hash=sha256:[0-9a-f]{64}", "", entry).strip()
        if not spec or spec.startswith("-"):
            continue
        requirement, _, marker = spec.partition(";")
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s=]+)", requirement.strip())
        if not match:
            raise ValueError(f"{path.name}: not an exact pin: {spec}")
        pins.append(Pin(match.group(1), match.group(2), marker.strip(), hashes))
    return pins


def marker_environment(*, windows: bool, python: str) -> dict:
    """PEP 508 marker values of the bundled Windows runtime or this host."""
    if windows:
        return {"os_name": "nt", "sys_platform": "win32", "platform_system": "Windows",
                "platform_machine": "AMD64", "implementation_name": "cpython",
                "platform_python_implementation": "CPython", "platform_release": "",
                "platform_version": "", "python_version": ".".join(python.split(".")[:2]),
                "python_full_version": python, "implementation_version": python}
    from packaging.markers import default_environment
    return default_environment()


def applicable(pins: list[Pin], environment: dict) -> dict[str, str]:
    from packaging.markers import Marker
    return {canonical(p.name): p.version for p in pins
            if not p.marker or Marker(p.marker).evaluate(environment)}


def compare_packages(expected: dict[str, str], found: dict[str, str], *,
                     ignore=frozenset()) -> dict:
    return {
        "expected": len(expected), "found": len(found),
        "missing": sorted(set(expected) - set(found)),
        "extra": sorted(set(found) - set(expected) - set(ignore)),
        "mismatched": {name: {"lock": expected[name], "found": found[name]}
                       for name in sorted(expected) if name in found
                       and found[name] != expected[name]},
    }


def _metadata_fields(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        if not line.strip():
            break
        key, sep, value = line.partition(":")
        if sep and key and not key.startswith(" "):
            fields.setdefault(key.strip(), value.strip())
    return fields


def bundled_distributions(site_packages: Path) -> dict[str, str]:
    """Name → version of the dist-info folders of a bundle's site-packages.

    From METADATA, else from the folder name (``name-version.dist-info``).
    """
    found = {}
    for folder in sorted(site_packages.glob("*.dist-info")):
        meta = folder / "METADATA"
        fields = (_metadata_fields(meta.read_text(encoding="utf-8", errors="replace"))
                  if meta.is_file() else {})
        name, version = fields.get("Name"), fields.get("Version")
        if not (name and version):
            name, _, version = folder.name[:-len(".dist-info")].rpartition("-")
        if name and version:
            found[canonical(name)] = version
    return found


def host_distributions() -> dict[str, str]:
    import importlib.metadata as metadata
    return {canonical(d.metadata["Name"]): d.version for d in metadata.distributions()
            if d.metadata["Name"]}


# --- Flutter SDK and build template ------------------------------------------

def flutter_home(version: str) -> Path:
    """Where flet-cli looks for (and would install) the SDK: ~/flutter/<version>."""
    return Path.home() / "flutter" / version


def flutter_revision(sdk: Path) -> str | None:
    """Framework commit of an SDK folder (version file of the cache, else git HEAD)."""
    version_json = sdk / "bin" / "cache" / "flutter.version.json"
    if version_json.is_file():
        try:
            return json.loads(version_json.read_text(encoding="utf-8")).get("frameworkRevision")
        except (OSError, ValueError):
            pass
    head = sdk / ".git" / "HEAD"
    if not head.is_file():
        return None
    value = head.read_text(encoding="utf-8").strip()
    if not value.startswith("ref:"):
        return value
    ref = value.split(":", 1)[1].strip()
    loose = sdk / ".git" / ref
    if loose.is_file():
        return loose.read_text(encoding="utf-8").strip()
    packed = sdk / ".git" / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0]
    return None


def prepare_flutter(lock: dict, *, home: Path | None = None) -> Path:
    flutter = lock["flutter"]
    target = home or flutter_home(flutter["version"])
    if target.exists():
        revision = flutter_revision(target)
        if revision != flutter["framework_revision"]:
            raise SystemExit(f"{target} holds Flutter {revision or 'of unknown revision'}, "
                             f"not {flutter['framework_revision']} of the lock; remove it.")
        print(f"Flutter {flutter['version']} ({revision[:12]}) already at {target}")
        return target
    archive_info = flutter["windows_x64"]
    # Unpack next to the target so the final move is a rename on one disk.
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sra-flutter-", dir=target.parent,
                                     ignore_cleanup_errors=True) as temp:
        archive = download(archive_info["url"], Path(temp) / "flutter.zip", archive_info["sha256"])
        print(f"Flutter archive verified: {archive_info['sha256']}")
        extracted = Path(temp) / "x"
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(extracted)
        archive.unlink()
        shutil.move(str(extracted / "flutter"), str(target))
    revision = flutter_revision(target)
    if revision is not None and revision != flutter["framework_revision"]:
        raise SystemExit(f"The verified archive holds revision {revision}, "
                         f"the lock says {flutter['framework_revision']}")
    print(f"Flutter {flutter['version']} installed at {target}")
    return target


def prepare_template(lock: dict, out: Path, *, archive: Path | None = None) -> Path:
    """Unpack the verified template; returns the folder with cookiecutter.json."""
    template = lock["flet_build_template"]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if archive is None:
        archive = download(template["url"], out / "flet-build-template.zip", template["sha256"])
    elif sha256_file(archive) != template["sha256"]:
        raise SystemExit(f"{archive} is not the template of the lock")
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(out / "unpacked")
    root = out / "unpacked" / "build"
    if not (root / "cookiecutter.json").is_file():
        raise SystemExit("The template has no build/cookiecutter.json")
    dart_lock = ROOT / template["dart_lock"]
    project = root / "{{cookiecutter.out_dir}}"
    if dart_lock.is_file():
        shutil.copyfile(dart_lock, project / "pubspec.lock")
    identity = {"url": template["url"], "sha256": template["sha256"],
                "dart_lock": dart_lock.is_file(),
                "dart_lock_sha256": sha256_file(dart_lock) if dart_lock.is_file() else None}
    (out / "template-identity.json").write_text(json.dumps(identity, indent=1), encoding="utf-8")
    return root


# --- Inno Setup ----------------------------------------------------------------

def find_iscc() -> Path | None:
    """The real ISCC.exe. The installation folder comes first: on PATH the
    runner has Chocolatey's shim (chocolatey\\bin\\ISCC.exe), whose own
    version resource says 0.0.0 (run 43418623260)."""
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base and Path(base, "Inno Setup 6", "ISCC.exe").is_file():
            return Path(base, "Inno Setup 6", "ISCC.exe")
    for name in ("ISCC", "iscc"):
        found = shutil.which(name)
        if found and "chocolatey" not in found.lower():
            return Path(found)
    return None


def file_version(path: Path) -> str:
    """ProductVersion of an executable, else its FileVersion (x.y.z)."""
    script = (f"$v = (Get-Item -LiteralPath '{path}').VersionInfo; "
              "\"$($v.ProductVersion)|$($v.FileVersion)\"")
    value = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, text=True, check=True).stdout.strip()
    for candidate in value.split("|"):
        version = normalize_version(candidate)
        if version and version.strip("0.") != "":
            return version
    return normalize_version(value.split("|")[0])


def iscc_version(iscc: Path | None) -> tuple[str | None, dict]:
    """Inno Setup's version, and what each source said.

    ISCC.exe itself carries no usable version resource (0.0.0 on the runner,
    run 43421786665). The installer's own uninstall entry ("Inno Setup 6_is1",
    DisplayVersion) is the reliable source; the compiler DLL next to ISCC.exe
    (ISCmplr.dll) is the second.
    """
    seen: dict = {}
    if os.name == "nt":
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
        for hive, name in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")):
            for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as handle:
                        seen[f"{name} uninstall"] = str(winreg.QueryValueEx(handle, "DisplayVersion")[0])
                except OSError:
                    continue
    if os.name == "nt" and shutil.which("choco"):
        # Chocolatey's record of the package it installed ("innosetup|6.7.1").
        try:
            listed = subprocess.run(["choco", "list", "innosetup", "--exact", "--limit-output"],
                                    capture_output=True, text=True, timeout=120).stdout
            for line in listed.splitlines():
                name, _, value = line.partition("|")
                if name.strip().lower() == "innosetup" and value.strip():
                    seen["chocolatey"] = value.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    if iscc is not None:
        for candidate in (iscc.with_name("ISCmplr.dll"), iscc):
            if candidate.is_file():
                try:
                    seen[candidate.name] = file_version(candidate)
                except (OSError, subprocess.CalledProcessError):
                    pass
    for value in seen.values():
        version = normalize_version(value)
        if version and version.strip("0.") != "":
            return version, seen
    return None, seen


def normalize_version(value: str) -> str:
    parts = re.findall(r"\d+", value)[:3]
    return ".".join(parts)


def prepare_iscc(lock: dict) -> dict:
    want = lock["inno_setup"]["version"]
    iscc = find_iscc()
    version, seen = iscc_version(iscc) if iscc else (None, {})
    print(f"ISCC: {iscc}; version {version} ({seen})")
    if version != want:
        print(f"Inno Setup {version or 'missing'} on this runner; installing {want}")
        subprocess.run(["choco", "install", lock["inno_setup"]["chocolatey_package"],
                        f"--version={want}", "--allow-downgrade", "--force", "-y", "--no-progress"],
                       check=True)
        iscc = find_iscc()
        version, seen = iscc_version(iscc) if iscc else (None, {})
        print(f"ISCC: {iscc}; version {version} ({seen})")
    if version != want:
        raise SystemExit(f"Inno Setup {want} of the lock is not available (found {version})")
    return {"iscc": str(iscc), "version": version, "sources": seen}


# --- Dart packages -----------------------------------------------------------------

def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_pubspec_lock(text: str) -> dict[str, dict]:
    """Packages of a pub-generated pubspec.lock (fixed two-space layout)."""
    packages: dict[str, dict] = {}
    section = name = None
    in_description = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, value = line.strip().partition(":")
        if indent == 0:
            section, name = key, None
        elif section != "packages":
            continue
        elif indent == 2:
            name = key
            packages[name] = {"version": None, "source": None, "sha256": None}
            in_description = False
        elif indent == 4 and name:
            in_description = key == "description" and not value.strip()
            if key in ("version", "source"):
                packages[name][key] = _scalar(value)
        elif indent == 6 and name and in_description and key == "sha256":
            packages[name]["sha256"] = _scalar(value)
    return packages


def dart_packages(pubspec_lock: Path) -> dict[str, dict]:
    """Name → version/source/sha256 of a pubspec.lock."""
    return parse_pubspec_lock(pubspec_lock.read_text(encoding="utf-8"))


def compare_dart(expected: dict, found: dict) -> dict:
    changed = {name: {"lock": expected[name], "found": found[name]}
               for name in sorted(set(expected) & set(found)) if expected[name] != found[name]}
    return {"missing": sorted(set(expected) - set(found)),
            "extra": sorted(set(found) - set(expected)), "changed": changed}


# --- Build identity ------------------------------------------------------------------

def _flutter_from_package_config(flutter_project: Path) -> dict:
    config = flutter_project / ".dart_tool" / "package_config.json"
    if not config.is_file():
        return {}
    data = json.loads(config.read_text(encoding="utf-8"))
    root = data.get("flutterRoot") or ""
    if root.startswith("file:"):
        root = urllib.request.url2pathname(urllib.parse.urlparse(root).path)
    return {"version": data.get("flutterVersion"), "root": root,
            "dart_generator": data.get("generatorVersion")}


def build_identity(args) -> tuple[dict, list[str]]:
    lock = load_lock()
    problems: list[str] = []   # deviations from the locks: --strict fails on them
    notes: list[str] = []      # facts this build could not record or check
    on_windows = os.name == "nt"
    host_python = platform.python_version()
    want_python = lock["python"]["windows_host" if on_windows else "linux_host"]
    if host_python != want_python:
        problems.append(f"host Python {host_python}, the lock says {want_python}")
    pins = parse_lock(RUNTIME_LOCK) + parse_lock(DEV_LOCK)
    host = compare_packages(applicable(pins, marker_environment(windows=False, python=host_python)),
                            host_distributions(), ignore=HOST_TOOLS)
    for key in ("missing", "extra"):
        if host[key]:
            problems.append(f"host packages {key}: {', '.join(host[key])}")
    if host["mismatched"]:
        problems.append(f"host packages differ from the lock: {host['mismatched']}")

    identity: dict = {
        "schema": 1,
        "commit": os.environ.get("GITHUB_SHA", ""),
        "run": {k: os.environ.get(v, "") for k, v in (("workflow", "GITHUB_WORKFLOW"),
                ("id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"), ("job", "GITHUB_JOB"))},
        "runner": {"image": os.environ.get("ImageOS", ""), "image_version": os.environ.get("ImageVersion", ""),
                   "platform": platform.platform()},
        "host_python": host_python,
        "host_packages": host,
        "locks": {path.name: sha256_file(path) for path in (RUNTIME_LOCK, DEV_LOCK, LOCK, OCR_LOCK)},
    }

    try:
        import flet.version
        import flet_cli.version
        identity["flet"] = {"python": flet.version.flet_version, "cli": flet_cli.version.version,
                            "flutter_required": flet.version.flutter_version}
        for key, value in (("python", flet.version.flet_version), ("cli", flet_cli.version.version)):
            if value != lock["flet"]["version"]:
                problems.append(f"flet {key} {value}, the lock says {lock['flet']['version']}")
        if flet.version.flutter_version != lock["flutter"]["version"]:
            problems.append(f"flet {flet.version.flet_version} needs Flutter "
                            f"{flet.version.flutter_version}, the lock says {lock['flutter']['version']}")
    except ImportError as error:
        problems.append(f"flet or flet-cli is not installed: {error}")

    flutter_project = Path(args.flutter_project)
    flutter = _flutter_from_package_config(flutter_project)
    sdk = flutter_home(lock["flutter"]["version"])
    flutter["revision"] = flutter_revision(sdk) if sdk.exists() else None
    identity["flutter"] = flutter
    if args.bundle:
        if flutter.get("version") is None:
            notes.append("the app shell records no Flutter version (.dart_tool/package_config.json)")
        elif flutter["version"] != lock["flutter"]["version"]:
            problems.append(f"the app shell was built with Flutter {flutter['version']}, "
                            f"the lock says {lock['flutter']['version']}")
        if flutter.get("root") and Path(flutter["root"]).resolve() != sdk.resolve():
            problems.append(f"flet build used the SDK at {flutter['root']}, not the verified {sdk}")
        if flutter.get("revision") is None:
            notes.append(f"no Flutter revision could be read from {sdk}")
        elif flutter["revision"] != lock["flutter"]["framework_revision"]:
            problems.append(f"Flutter revision {flutter['revision']}, "
                            f"the lock says {lock['flutter']['framework_revision']}")

    template_identity = Path(args.template_identity) if args.template_identity else None
    if template_identity and template_identity.is_file():
        identity["template"] = json.loads(template_identity.read_text(encoding="utf-8"))
    elif args.bundle:
        problems.append("no template identity: was the build made with the verified template?")

    pubspec_lock = flutter_project / "pubspec.lock"
    if pubspec_lock.is_file():
        found = dart_packages(pubspec_lock)
        identity["dart_packages"] = {"count": len(found), "pubspec_lock_sha256": sha256_file(pubspec_lock),
                                     "packages": found}
        locked_path = ROOT / lock["flet_build_template"]["dart_lock"]
        if locked_path.is_file():
            drift = compare_dart(dart_packages(locked_path), found)
            identity["dart_packages"]["drift"] = drift
            if any(drift.values()):
                problems.append(f"Dart packages differ from {lock['flet_build_template']['dart_lock']}: {drift}")
        else:
            identity["dart_packages"]["drift"] = None
            notes.append(f"{lock['flet_build_template']['dart_lock']} is not in the repository yet: "
                         "the Dart packages of this build are recorded, not checked")
        if args.out:
            shutil.copyfile(pubspec_lock, Path(args.out).with_name("flutter-pubspec.lock"))
    elif args.bundle:
        notes.append(f"no {pubspec_lock}: the Dart packages were not recorded")

    if args.bundle:
        bundle = Path(args.bundle)
        expected = applicable(parse_lock(RUNTIME_LOCK),
                              marker_environment(windows=True, python=lock["python"]["embedded"]))
        bundled = compare_packages(expected, bundled_distributions(bundle / "site-packages"))
        identity["bundle"] = {"site_packages": bundled, "top_level": {
            p.name: {"size": p.stat().st_size, "sha256": sha256_file(p)}
            for p in sorted(bundle.iterdir()) if p.is_file()}}
        for key in ("missing", "extra"):
            if bundled[key]:
                problems.append(f"bundled packages {key}: {', '.join(bundled[key])}")
        if bundled["mismatched"]:
            problems.append(f"bundled packages differ from requirements.txt: {bundled['mismatched']}")
    if args.iscc:
        iscc = find_iscc()
        version, seen = iscc_version(iscc) if iscc else (None, {})
        identity["inno_setup"] = {"iscc": str(iscc) if iscc else None, "version": version,
                                  "sources": seen}
        if identity["inno_setup"]["version"] != lock["inno_setup"]["version"]:
            problems.append(f"Inno Setup {identity['inno_setup']['version']}, "
                            f"the lock says {lock['inno_setup']['version']}")
    identity["problems"] = problems
    identity["notes"] = notes
    identity["ok"] = not problems
    return identity, problems


# --- Manifests and comparison -----------------------------------------------------------

PE_SUFFIXES = {".exe", ".dll", ".pyd"}


def pe_normalized_sha256(data: bytes) -> str | None:
    """SHA-256 of a PE image with link timestamps, checksum and PDB id zeroed.

    These are the fields an MSVC/MinGW link writes differently on every run
    (COFF TimeDateStamp, optional-header CheckSum, the debug directory's
    TimeDateStamp and the CodeView RSDS GUID/age). None if not a PE image.
    """
    try:
        if data[:2] != b"MZ":
            return None
        image = bytearray(data)
        pe = struct.unpack_from("<I", image, 0x3C)[0]
        if image[pe:pe + 4] != b"PE\0\0":
            return None
        coff = pe + 4
        sections = struct.unpack_from("<H", image, coff + 2)[0]
        optional_size = struct.unpack_from("<H", image, coff + 16)[0]
        image[coff + 4:coff + 8] = b"\0" * 4                      # TimeDateStamp
        optional = coff + 20
        magic = struct.unpack_from("<H", image, optional)[0]
        image[optional + 64:optional + 68] = b"\0" * 4            # CheckSum
        directories = optional + (96 if magic == 0x10B else 112)
        debug_rva, debug_size = struct.unpack_from("<II", image, directories + 6 * 8)
        table = optional + optional_size
        offset_of = None
        for index in range(sections):
            entry = table + index * 40
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", image, entry + 8)
            if virtual_address <= debug_rva < virtual_address + max(virtual_size, raw_size):
                offset_of = raw_pointer + (debug_rva - virtual_address)
                break
        if offset_of is not None:
            for start in range(offset_of, offset_of + debug_size, 28):
                image[start + 4:start + 8] = b"\0" * 4            # debug TimeDateStamp
                kind, size, _, pointer = struct.unpack_from("<IIII", image, start + 12)
                if kind == 2 and image[pointer:pointer + 4] == b"RSDS":
                    image[pointer + 4:pointer + 24] = b"\0" * 20  # PDB GUID + age
                if kind == 16:                                    # REPRO hash
                    image[pointer:pointer + size] = b"\0" * size
        return hashlib.sha256(bytes(image)).hexdigest()
    except (struct.error, IndexError):
        return None


def describe_file(path: Path) -> dict:
    data = path.read_bytes()
    entry = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    suffix = path.suffix.lower()
    if suffix in PE_SUFFIXES:
        normalized = pe_normalized_sha256(data)
        if normalized:
            entry["pe_normalized_sha256"] = normalized
    elif suffix == ".pyc" and len(data) >= 16:
        entry["pyc_body_sha256"] = hashlib.sha256(data[16:]).hexdigest()
    elif suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as handle:
                entry["zip_members"] = {i.filename: [i.CRC, i.file_size] for i in handle.infolist()}
        except zipfile.BadZipFile:
            pass
    return entry


def manifest(root: Path) -> dict:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = describe_file(path)
    return {"schema": 1, "root": root.name, "files": files,
            "total_bytes": sum(f["size"] for f in files.values())}


BUILD_METADATA = {"app/build_info.json"}


def classify(path: str, a: dict, b: dict) -> str:
    if path in BUILD_METADATA or path.endswith("/build_info.json"):
        return "build metadata (version, commit, build time)"
    if "pe_normalized_sha256" in a and a.get("pe_normalized_sha256") == b.get("pe_normalized_sha256"):
        return "PE link timestamp, checksum or PDB id only"
    if "pyc_body_sha256" in a and a.get("pyc_body_sha256") == b.get("pyc_body_sha256"):
        return ".pyc header (source timestamp) only"
    if "zip_members" in a and a.get("zip_members") == b.get("zip_members"):
        return "zip metadata (timestamps, order) only, same members"
    if "zip_members" in a and "zip_members" in b:
        return "zip members differ"
    return "content differs"


def compare_manifests(a: dict, b: dict) -> dict:
    files_a, files_b = a["files"], b["files"]
    identical, deviations = [], []
    for path in sorted(set(files_a) & set(files_b)):
        if files_a[path]["sha256"] == files_b[path]["sha256"]:
            identical.append(path)
        else:
            deviations.append({"path": path, "kind": classify(path, files_a[path], files_b[path]),
                               "size_a": files_a[path]["size"], "size_b": files_b[path]["size"]})
    kinds: dict[str, int] = {}
    for deviation in deviations:
        kinds[deviation["kind"]] = kinds.get(deviation["kind"], 0) + 1
    return {"files_a": len(files_a), "files_b": len(files_b), "identical": len(identical),
            "only_in_a": sorted(set(files_a) - set(files_b)),
            "only_in_b": sorted(set(files_b) - set(files_a)),
            "deviations": deviations, "kinds": kinds,
            "bytes_a": a.get("total_bytes"), "bytes_b": b.get("total_bytes")}


def comparison_markdown(result: dict, title: str) -> str:
    lines = [f"## {title}", "",
             f"- Files: {result['files_a']} and {result['files_b']}; byte-identical: "
             f"**{result['identical']}**; deviating: **{len(result['deviations'])}**",
             f"- Total size: {result['bytes_a']} and {result['bytes_b']} bytes",
             f"- Only in the first: {len(result['only_in_a'])}; only in the second: {len(result['only_in_b'])}",
             ""]
    if result["kinds"]:
        lines += ["| Kind of deviation | Files |", "|---|---:|"]
        lines += [f"| {kind} | {count} |" for kind, count in sorted(result["kinds"].items())]
        lines += ["", "| File | Kind | Size A | Size B |", "|---|---|---:|---:|"]
        lines += [f"| `{d['path']}` | {d['kind']} | {d['size_a']} | {d['size_b']} |"
                  for d in result["deviations"][:200]]
        if len(result["deviations"]) > 200:
            lines.append(f"| … {len(result['deviations']) - 200} more | | | |")
    for key, label in (("only_in_a", "Only in the first"), ("only_in_b", "Only in the second")):
        if result[key]:
            lines += ["", f"{label}:"] + [f"- `{p}`" for p in result[key][:100]]
    return "\n".join(lines) + "\n"


# --- Command line -------------------------------------------------------------------------

def _github_file(variable: str, line: str) -> None:
    target = os.environ.get(variable)
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("flutter")
    template = commands.add_parser("template")
    template.add_argument("--out", type=Path, required=True)
    template.add_argument("--archive", type=Path)
    template.add_argument("--github-output", action="store_true")
    commands.add_parser("iscc")
    identity = commands.add_parser("identity")
    identity.add_argument("--bundle")
    identity.add_argument("--flutter-project", default=str(ROOT / "build" / "flutter"))
    identity.add_argument("--template-identity", default=os.environ.get("SRA_FLET_TEMPLATE_IDENTITY"))
    identity.add_argument("--iscc", action="store_true")
    identity.add_argument("--out")
    identity.add_argument("--strict", action="store_true")
    build_manifest = commands.add_parser("manifest")
    build_manifest.add_argument("root", type=Path)
    build_manifest.add_argument("--out", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("a", type=Path)
    compare.add_argument("b", type=Path)
    compare.add_argument("--markdown", type=Path)
    compare.add_argument("--title", default="Two clean builds of the same commit")
    args = parser.parse_args(argv)
    lock = load_lock()

    if args.command == "flutter":
        prepare_flutter(lock)
    elif args.command == "template":
        root = prepare_template(lock, args.out, archive=args.archive)
        print(root)
        if args.github_output:
            _github_file("GITHUB_OUTPUT", f"path={root}")
            _github_file("GITHUB_ENV", f"SRA_FLET_TEMPLATE={root}")
            _github_file("GITHUB_ENV", f"SRA_FLET_TEMPLATE_IDENTITY={args.out / 'template-identity.json'}")
    elif args.command == "iscc":
        print(json.dumps(prepare_iscc(lock)))
    elif args.command == "identity":
        result, problems = build_identity(args)
        text = json.dumps(result, indent=1)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        summary = {k: result.get(k) for k in ("host_python", "flet", "flutter")}
        print(json.dumps(summary, indent=1))
        for problem in problems:
            print(f"DEVIATION: {problem}")
        for note in result["notes"]:
            print(f"NOTE: {note}")
        if problems and args.strict:
            return 1
    elif args.command == "manifest":
        data = manifest(args.root)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        print(f"{len(data['files'])} files, {data['total_bytes']} bytes")
    elif args.command == "compare":
        result = compare_manifests(json.loads(args.a.read_text(encoding="utf-8")),
                                   json.loads(args.b.read_text(encoding="utf-8")))
        markdown = comparison_markdown(result, args.title)
        if args.markdown:
            args.markdown.write_text(markdown, encoding="utf-8")
        print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
