"""Write ``build_info.json`` into the application folder before packaging.

    python tools/write_build_info.py --channel stable --build 123 --commit <sha>
    python tools/write_build_info.py --version 1.0.1-test.1 --channel test \
        --update-key <base64 Ed25519 public key> --test-endpoint http://127.0.0.1:8765/

The version defaults to ``app_identity.VERSION``; on the stable channel it
must equal it (a release tag v1.2.3 is checked against the source). Public
keys only: the private update-signing key never enters the repository or
the application.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_identity  # noqa: E402


def build_info(args) -> dict:
    version = app_identity.parse_version(args.version or app_identity.VERSION)
    if args.channel == "stable" and (version.prerelease or str(version) != app_identity.VERSION):
        raise SystemExit(f"A stable build must be version {app_identity.VERSION} "
                         f"(app_identity.VERSION), not {version}.")
    if args.channel == "preview" and not version.prerelease:
        raise SystemExit("A preview build needs a pre-release version such as 1.1.0-preview.3.")
    if args.test_endpoint and args.channel != "test":
        raise SystemExit("--test-endpoint is only for test builds.")
    if args.test_endpoint and not args.test_endpoint.startswith("http://127.0.0.1:"):
        raise SystemExit("A test endpoint must be http://127.0.0.1:<port>/...")
    keys = list(args.update_key or [])
    for key_file in args.update_key_file or []:
        keys.extend(line.strip() for line in Path(key_file).read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#"))
    return {
        "version": str(version), "channel": args.channel, "build": str(args.build or ""),
        "commit": args.commit or "", "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signed": bool(args.signed), "publisher": args.publisher or "",
        "publisher_thumbprints": [t.upper() for t in args.publisher_thumbprint or []],
        "require_signature": bool(args.require_signature), "update_keys": keys,
        "update_endpoint": args.update_endpoint or "", "test_endpoint": args.test_endpoint or "",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version")
    parser.add_argument("--channel", required=True, choices=("stable", "preview", "test"))
    parser.add_argument("--build")
    parser.add_argument("--commit")
    parser.add_argument("--signed", action="store_true")
    parser.add_argument("--publisher")
    parser.add_argument("--publisher-thumbprint", action="append")
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--update-key", action="append")
    parser.add_argument("--update-key-file", action="append")
    parser.add_argument("--update-endpoint")
    parser.add_argument("--test-endpoint")
    parser.add_argument("--out", type=Path, default=ROOT / app_identity.BUILD_INFO)
    args = parser.parse_args(argv)
    if args.require_signature and not (args.publisher or args.publisher_thumbprint):
        raise SystemExit("--require-signature needs --publisher or --publisher-thumbprint.")
    info = build_info(args)
    args.out.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in info.items() if k != "update_keys"}
                     | {"update_keys": len(info["update_keys"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
