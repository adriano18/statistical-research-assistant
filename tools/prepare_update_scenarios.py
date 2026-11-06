"""Prepare the local update server's scenarios for the Windows update
journeys (#45, CI only). All manifests use a throwaway test key.

    python tools/prepare_update_scenarios.py --installer dist-b/StatisticalResearchAssistant-1.0.1-test.7-Setup.exe \
        --version 1.0.1-test.7 --key-file test-update.key --out served

served/good/      sra-update-test.json (signed by the test key) + the installer
served/tampered/  the same manifest signed by ANOTHER key (must be rejected)
served/older/     a correctly signed manifest for an OLDER version (never offered)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import update_manifest as um  # noqa: E402
from update_signing import manifest_payload, new_key  # noqa: E402

NAME = "sra-update-test.json"
CHANGELOG = {
    "changelog": {
        "en": "Fictional change list for the update test: a clearer results page and faster start.",
        "lv": "Izdomāts izmaiņu saraksts atjaunināšanas testam.",
        "ru": "Вымышленный список изменений для теста обновления.",
    },
    "known_limitations": {"en": "This is a test build; nothing here is a real release."},
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    key = args.key_file.read_text(encoding="utf-8").strip()
    changelog = args.out / "changelog.json"
    args.out.mkdir(parents=True, exist_ok=True)
    changelog.write_text(json.dumps(CHANGELOG, ensure_ascii=False), encoding="utf-8")

    def payload(version: str) -> bytes:
        namespace = argparse.Namespace(
            installer=str(args.installer), version=version, channel="test",
            url=f"http://127.0.0.1:{args.port}/{args.installer.name}", build="", minimum_version="0.0.0",
            project_format=__import__("project_store").SCHEMA_VERSION, signed=False, publisher="",
            changelog_file=str(changelog),
            release_notes_url="https://github.com/adriano18/statistical-research-assistant/releases")
        return manifest_payload(namespace)

    other_key, _ = new_key()
    scenarios = {"good": um.sign_payload(payload(args.version), key),
                 "tampered": um.sign_payload(payload(args.version), other_key),
                 "older": um.sign_payload(payload("0.9.0-test.1"), key)}
    for name, envelope in scenarios.items():
        folder = args.out / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / NAME).write_text(json.dumps(envelope), encoding="utf-8")
    shutil.copy2(args.installer, args.out / "good" / args.installer.name)
    print(json.dumps({"served": str(args.out), "scenarios": sorted(scenarios),
                      "installer": args.installer.name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
