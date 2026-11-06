"""Update-signing keys and signed update manifests (Stage 35, #45).

    python tools/update_signing.py new-key --private-out update-signing.key
        Creates an Ed25519 key pair. Store the private key (the file's one
        line) as the GitHub Actions secret SRA_UPDATE_SIGNING_KEY, then
        delete the file. Never commit it. The public key is printed; builds
        derive it from the secret themselves.

    python tools/update_signing.py public-key            (reads SRA_UPDATE_SIGNING_KEY)
    python tools/update_signing.py manifest --installer dist/X-Setup.exe --version 1.1.0 \
        --channel stable --url https://github.com/.../X-Setup.exe \
        --changelog-file CHANGELOG-1.1.0.json --out sra-update-stable.json

The private key is read from the environment (SRA_UPDATE_SIGNING_KEY) or
from --private-key-file, never from the command line.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_identity  # noqa: E402
import update_manifest as um  # noqa: E402


def _private_key(args) -> str:
    if getattr(args, "private_key_file", None):
        return Path(args.private_key_file).read_text(encoding="utf-8").strip()
    value = os.environ.get("SRA_UPDATE_SIGNING_KEY", "").strip()
    if not value:
        raise SystemExit("SRA_UPDATE_SIGNING_KEY is not set (GitHub Actions secret).")
    return value


def public_key_of(private_b64: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_b64))
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def new_key() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
    private_b64 = base64.b64encode(raw).decode()
    return private_b64, public_key_of(private_b64)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_payload(args) -> bytes:
    version = app_identity.parse_version(args.version)
    installer = Path(args.installer)
    texts = json.loads(Path(args.changelog_file).read_text(encoding="utf-8")) if args.changelog_file else {}
    payload = {
        "format": um.MANIFEST_FORMAT, "app_id": app_identity.INSTALLER_APP_ID,
        "channel": args.channel, "version": str(version), "build": args.build or "",
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "minimum_version": args.minimum_version, "project_format": args.project_format,
        "installer": {"url": args.url, "size": installer.stat().st_size, "sha256": sha256(installer),
                      "signed": bool(args.signed), "publisher": args.publisher or ""},
        "changelog": texts.get("changelog", {}), "known_limitations": texts.get("known_limitations", {}),
        "release_notes_url": args.release_notes_url or "",
    }
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    key = commands.add_parser("new-key")
    key.add_argument("--private-out", type=Path, required=True)
    public = commands.add_parser("public-key")
    public.add_argument("--private-key-file")
    make = commands.add_parser("manifest")
    for name in ("--installer", "--version", "--channel", "--url", "--out"):
        make.add_argument(name, required=True)
    make.add_argument("--build")
    make.add_argument("--minimum-version", default="1.0.0")
    from project_store import SCHEMA_VERSION
    make.add_argument("--project-format", type=int, default=SCHEMA_VERSION)
    make.add_argument("--signed", action="store_true")
    make.add_argument("--publisher")
    make.add_argument("--changelog-file")
    make.add_argument("--release-notes-url")
    make.add_argument("--private-key-file")
    args = parser.parse_args(argv)
    if args.command == "new-key":
        private_b64, public_b64 = new_key()
        if args.private_out.exists():
            raise SystemExit(f"{args.private_out} exists; not overwriting a key.")
        args.private_out.write_text(private_b64 + "\n", encoding="utf-8")
        print(json.dumps({"public_key": public_b64, "key_id": um.key_id(public_b64),
                          "private_key_file": str(args.private_out)}))
        return 0
    if args.command == "public-key":
        public_b64 = public_key_of(_private_key(args))
        print(public_b64)
        return 0
    payload = manifest_payload(args)
    envelope = um.sign_payload(payload, _private_key(args))
    Path(args.out).write_text(json.dumps(envelope, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": args.out, "version": args.version, "channel": args.channel,
                      "key": envelope["signatures"][0]["key"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
