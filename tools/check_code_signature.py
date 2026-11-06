"""Code-signature decisions of the updater on real Windows (#45, CI only).

Signs copies of an installer with a throwaway self-signed certificate
(Set-AuthenticodeSignature) and checks what update_client.verify_installer
decides, using Windows' own signature verification:

- signed by a publisher Windows does not trust            -> refused
- signed and trusted, publisher and thumbprint as pinned  -> accepted
- signed and trusted, another publisher pinned            -> refused
- signed, then one byte changed (hash mismatch)           -> refused, also by unsigned builds
- unsigned, while the build requires a signature          -> refused
- unsigned, unsigned preview build                        -> accepted (checksum + signed manifest)

    python tools/check_code_signature.py dist-b/StatisticalResearchAssistant-1.0.1-test.7-Setup.exe out/code-signature.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_identity as ai  # noqa: E402
import update_client as uc  # noqa: E402
import update_manifest as um  # noqa: E402

SUBJECT = "CN=SRA Update Test Publisher (throwaway)"


def powershell(script: str) -> str:
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, check=False)
    if done.returncode:
        raise SystemExit(f"PowerShell failed: {done.stderr.strip()[:800]}")
    return done.stdout.strip()


def manifest_for(path: Path) -> um.Manifest:
    return um.Manifest(app_id=ai.INSTALLER_APP_ID, channel="test", version=ai.parse_version("9.9.9-test.1"),
                       build="", published_at="", minimum_version=ai.parse_version("0.0.0"),
                       project_format=0,
                       installer=um.Installer(url="http://127.0.0.1:1/x.exe", size=path.stat().st_size,
                                              sha256=uc.sha256(path)))


def decide(path: Path, build: ai.BuildInfo) -> str:
    try:
        signature = uc.verify_installer(path, manifest_for(path), build)
        return f"accepted ({signature['status']})"
    except uc.UpdateError as error:
        return f"refused: {error.reason} ({error.detail})"


def main(argv=None) -> int:
    if os.name != "nt":
        print("Code-signature checks run on Windows only.")
        return 2
    installer, out = Path(sys.argv[1]), Path(sys.argv[2])
    work = Path(tempfile.mkdtemp(prefix="sra-sign-"))
    signed = work / "signed.exe"
    shutil.copy2(installer, signed)
    thumbprint = powershell(
        f"$c = New-SelfSignedCertificate -Type CodeSigningCert -Subject '{SUBJECT}' "
        f"-CertStoreLocation Cert:\\CurrentUser\\My -NotAfter (Get-Date).AddDays(2); $c.Thumbprint")
    results, problems = {}, []
    try:
        powershell(f"$c = Get-Item Cert:\\CurrentUser\\My\\{thumbprint}; "
                   f"Set-AuthenticodeSignature -FilePath '{signed}' -Certificate $c -HashAlgorithm SHA256 | Out-Null")
        tampered = work / "tampered.exe"
        data = bytearray(signed.read_bytes())
        data[len(data) // 2] ^= 0xFF
        tampered.write_bytes(bytes(data))
        strict = ai.BuildInfo(version="1.0.0-test.1", channel="test", require_signature=True,
                              publisher=SUBJECT, publisher_thumbprints=(thumbprint.upper(),))
        other = ai.BuildInfo(version="1.0.0-test.1", channel="test", require_signature=True,
                             publisher="CN=Someone Else")
        relaxed = ai.BuildInfo(version="1.0.0-test.1", channel="test")
        results["untrusted publisher"] = decide(signed, strict)
        powershell(f"Export-Certificate -Cert Cert:\\CurrentUser\\My\\{thumbprint} -FilePath '{work / 't.cer'}' | Out-Null; "
                   f"Import-Certificate -FilePath '{work / 't.cer'}' -CertStoreLocation Cert:\\LocalMachine\\Root | Out-Null")
        results["trusted, pinned publisher"] = decide(signed, strict)
        results["trusted, another publisher pinned"] = decide(signed, other)
        results["tampered after signing (signature required)"] = decide(tampered, strict)
        results["tampered after signing (unsigned preview build)"] = decide(tampered, relaxed)
        results["unsigned, signature required"] = decide(installer, strict)
        results["unsigned, unsigned preview build"] = decide(installer, relaxed)
        results["windows status of the signed copy"] = uc.authenticode(signed)
    finally:
        powershell(f"Get-ChildItem Cert:\\LocalMachine\\Root | Where-Object Thumbprint -eq '{thumbprint}' | Remove-Item; "
                   f"Remove-Item Cert:\\CurrentUser\\My\\{thumbprint}")
    expected = {
        "untrusted publisher": "refused: bad_code_signature",
        "trusted, pinned publisher": "accepted (Valid)",
        "trusted, another publisher pinned": "refused: wrong_publisher",
        "tampered after signing (signature required)": "refused: bad_code_signature",
        "tampered after signing (unsigned preview build)": "refused: bad_code_signature",
        "unsigned, signature required": "refused: bad_code_signature",
        "unsigned, unsigned preview build": "accepted (NotSigned)",
    }
    for case, want in expected.items():
        if not str(results.get(case, "")).startswith(want):
            problems.append(f"{case}: expected {want!r}, got {results.get(case)!r}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": results, "problems": problems}, indent=1), encoding="utf-8")
    for case, outcome in results.items():
        print(f"{'ok  ' if case not in expected or str(outcome).startswith(expected[case]) else 'FAIL'} {case}: {outcome}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
