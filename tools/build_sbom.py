"""Software bill of materials of the Windows program (CycloneDX 1.5 JSON).

    python tools/build_sbom.py --out diagnostics/sbom.cdx.json \
        [--pubspec-lock build/flutter/pubspec.lock] [--licenses-md diagnostics/licenses.md]

Components, each with version, source and SHA-256 where one exists:
- the Python packages bundled into the program (requirements.txt, evaluated
  for 64-bit Windows and the embedded CPython), with licence metadata read
  from the installed distributions of the same versions;
- the embedded CPython, the Flutter SDK and the flet build template
  (packaging/build_toolchain.lock.json);
- the Dart packages of the app shell (pubspec.lock of the build, if given);
- Tesseract, its language models and the MSYS2 libraries it loads
  (packaging/windows_ocr_runtime.lock.json, used packages only).

--licenses-md writes the licence table that docs/STAGE368_BUILD_LOCK.md
summarises; copyleft terms are flagged for review before a public release.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import build_toolchain as toolchain  # noqa: E402

COPYLEFT = re.compile(r"\b(A?GPL|LGPL|MPL|EPL|CDDL|EUPL)\b", re.I)
# Packages whose metadata hold no SPDX expression, only a classifier or the
# full licence text: the expression read from the licence file each wheel
# ships (checked for the versions of requirements.txt, 2026-11-13).
FROM_LICENCE_FILE = {
    "cycler": "BSD-3-Clause", "kiwisolver": "BSD-3-Clause", "scipy": "BSD-3-Clause",
    "seaborn": "BSD-3-Clause", "matplotlib": "LicenseRef-Matplotlib (PSF-based)",
}
# Libraries compiled into a package's wheel under their own licence, as the
# licence file of that wheel states (checked for requirements.txt,
# 2026-11-13): listed as components of the package (CycloneDX assembly).
BUNDLED_IN_WHEEL = {
    "pyreadstat": ({"name": "ReadStat", "licence": "MIT",
                    "url": "https://github.com/WizardMac/ReadStat",
                    "note": "C library compiled into pyreadstat's extension modules; "
                            "licence text in pyreadstat's dist-info/licenses/LICENSE"},),
}


def installed_license(name: str) -> tuple[str, str]:
    """(licence, where it came from) of an installed distribution."""
    import importlib.metadata as metadata
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return FROM_LICENCE_FILE.get(name, "unknown (not installed here)"), "none"
    if meta.get("License-Expression"):
        return meta["License-Expression"], "License-Expression"
    if name in FROM_LICENCE_FILE:
        return FROM_LICENCE_FILE[name], "licence file"
    field = (meta.get("License") or "").strip()
    if field and len(field) < 80 and "\n" not in field:
        return field, "License"
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or []
                   if c.startswith("License ::")]
    if classifiers:
        return " AND ".join(classifiers), "classifier"
    return "unknown", "none"


def _license_entry(value: str) -> list[dict]:
    if re.fullmatch(r"[A-Za-z0-9.+\-() ]+", value) and any(c.isdigit() or c == "-" for c in value):
        return [{"expression": value}]
    return [{"license": {"name": value[:200]}}]


def python_components(lock: dict) -> list[dict]:
    pins = toolchain.parse_lock(toolchain.RUNTIME_LOCK)
    environment = toolchain.marker_environment(windows=True, python=lock["python"]["embedded"])
    wanted = toolchain.applicable(pins, environment)
    components = []
    for pin in pins:
        name = toolchain.canonical(pin.name)
        if name not in wanted:
            continue
        licence, origin = installed_license(name)
        components.append({
            "type": "library", "bom-ref": f"pkg:pypi/{name}@{pin.version}",
            "name": name, "version": pin.version, "purl": f"pkg:pypi/{name}@{pin.version}",
            "licenses": _license_entry(licence),
            "externalReferences": [{"type": "distribution",
                                    "url": f"https://pypi.org/project/{name}/{pin.version}/",
                                    "hashes": [{"alg": "SHA-256", "content": h} for h in pin.hashes]}],
            "properties": [{"name": "sra:licence-source", "value": origin},
                           {"name": "sra:lock", "value": "requirements.txt"}],
        })
        bundled = [{"type": "library",
                    "bom-ref": f"pkg:pypi/{name}@{pin.version}#{inner['name']}",
                    "name": inner["name"], "licenses": [{"expression": inner["licence"]}],
                    "description": inner["note"],
                    "externalReferences": [{"type": "website", "url": inner["url"]}]}
                   for inner in BUNDLED_IN_WHEEL.get(name, ())]
        if bundled:
            components[-1]["components"] = bundled
    return components


def toolchain_components(lock: dict) -> list[dict]:
    flutter, template, python = lock["flutter"], lock["flet_build_template"], lock["python"]
    return [
        {"type": "platform", "bom-ref": f"pkg:generic/cpython@{python['embedded']}",
         "name": "CPython (embedded)", "version": python["embedded"],
         "licenses": [{"expression": "PSF-2.0"}],
         "description": python["embedded_source"],
         "externalReferences": [{"type": "distribution", "url": python["python_build_manifest"]["url"],
                                 "hashes": [{"alg": "SHA-256",
                                             "content": python["python_build_manifest"]["sha256"]}]}]},
        {"type": "framework", "bom-ref": f"pkg:generic/flutter@{flutter['version']}",
         "name": "Flutter SDK (engine and framework)", "version": flutter["version"],
         "licenses": [{"expression": "BSD-3-Clause"}],
         "properties": [{"name": "sra:framework-revision", "value": flutter["framework_revision"]},
                        {"name": "sra:dart-sdk", "value": flutter["dart_sdk"]}],
         "externalReferences": [{"type": "distribution", "url": flutter["windows_x64"]["url"],
                                 "hashes": [{"alg": "SHA-256", "content": flutter["windows_x64"]["sha256"]}]}]},
        {"type": "application", "bom-ref": f"pkg:generic/flet-build-template@{lock['flet']['version']}",
         "name": "flet build template", "version": lock["flet"]["version"],
         "licenses": [{"expression": "Apache-2.0"}],
         "externalReferences": [{"type": "distribution", "url": template["url"],
                                 "hashes": [{"alg": "SHA-256", "content": template["sha256"]}]}]},
    ]


def dart_components(pubspec_lock: Path) -> list[dict]:
    components = []
    for name, entry in sorted(toolchain.dart_packages(pubspec_lock).items()):
        if entry["source"] not in ("hosted", None):
            continue
        component = {"type": "library", "bom-ref": f"pkg:pub/{name}@{entry['version']}",
                     "name": name, "version": entry["version"], "purl": f"pkg:pub/{name}@{entry['version']}",
                     "licenses": [{"license": {"name": "see data/flutter_assets/NOTICES.Z in the program"}}]}
        if entry.get("sha256"):
            component["hashes"] = [{"alg": "SHA-256", "content": entry["sha256"]}]
        components.append(component)
    return components


def ocr_components() -> list[dict]:
    lock = json.loads(toolchain.OCR_LOCK.read_text(encoding="utf-8"))
    components = []
    for package in lock["packages"]:
        if not package.get("used"):
            continue
        name = package["name"].replace("mingw-w64-ucrt-x86_64-", "")
        licence = package["license"].replace("spdx:", "")
        components.append({
            "type": "library", "bom-ref": f"pkg:generic/msys2/{name}@{package['version']}",
            "name": name, "version": package["version"],
            "licenses": [{"license": {"name": licence}}],
            "hashes": [{"alg": "SHA-256", "content": package["sha256"]}],
            "externalReferences": [{"type": "distribution",
                                    "url": lock["repositories"][0] + package["filename"]},
                                   {"type": "website", "url": package.get("url", "")}],
            "properties": [{"name": "sra:lock", "value": "packaging/windows_ocr_runtime.lock.json"}],
        })
    return components


def sbom(pubspec_lock: Path | None = None) -> dict:
    lock = toolchain.load_lock()
    import app_identity
    components = (python_components(lock) + toolchain_components(lock)
                  + (dart_components(pubspec_lock) if pubspec_lock and pubspec_lock.is_file() else [])
                  + ocr_components())
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}", "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tools": [{"name": "tools/build_sbom.py"}],
            "component": {"type": "application", "bom-ref": "statistical-research-assistant",
                          "name": "Statistical Research Assistant", "version": app_identity.VERSION,
                          "licenses": [{"license": {"name": "not declared: no LICENSE file in the repository"}}]},
        },
        "components": components,
    }


def licence_of(component: dict) -> str:
    entry = component["licenses"][0]
    return entry.get("expression") or entry.get("license", {}).get("name", "")


def all_components(document: dict) -> list[dict]:
    """Every component, those compiled into another one included."""
    found = []
    for component in document["components"]:
        found.append(component)
        found.extend(component.get("components", ()))
    return found


def licences_markdown(document: dict) -> str:
    lines = ["| Component | Version | Licence | Copyleft | Kind |", "|---|---|---|---|---|"]
    for component in document["components"]:
        for item in (component, *component.get("components", ())):
            licence = licence_of(item)
            flag = "yes" if COPYLEFT.search(licence) else ""
            kind = component["bom-ref"].split("/")[0].replace("pkg:", "")
            if item is not component:
                kind += f" (inside {component['name']})"
            version = item.get("version") or (
                "" if item is component else f"in {component['name']} {component['version']}")
            lines.append(f"| {item['name']} | {version} | {licence} | {flag} | {kind} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pubspec-lock", type=Path)
    parser.add_argument("--licenses-md", type=Path)
    args = parser.parse_args(argv)
    document = sbom(args.pubspec_lock)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    everything = all_components(document)
    copyleft = [c for c in everything if COPYLEFT.search(licence_of(c))]
    print(f"{len(everything)} components, {len(copyleft)} with copyleft terms: "
          + ", ".join(f"{c['name']} ({licence_of(c)})" for c in copyleft))
    if args.licenses_md:
        args.licenses_md.write_text(licences_markdown(document), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
