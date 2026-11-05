"""Prepare the pinned, offline Tesseract 5 runtime for the Windows bundle.

Source: MSYS2 UCRT64 binary packages (https://repo.msys2.org/mingw/ucrt64/),
the same MinGW-w64 toolchain family used by the common Windows Tesseract
installers. Every package is pinned by file name and SHA-256 in
``packaging/windows_ocr_runtime.lock.json`` and every extracted file is
pinned again by SHA-256. Nothing unpinned is ever copied into the bundle.

Usage (CI / maintainers, any OS, needs ``pip install zstandard``)::

    python tools/prepare_windows_ocr_runtime.py fetch --out bundled_ocr/windows-x64

Refreshing the lock (maintainers only; also needs ``pefile``) re-resolves
the package closure from the MSYS2 database and recomputes the exact DLL
import closure of ``tesseract.exe``::

    python tools/prepare_windows_ocr_runtime.py lock

Review the diff of the lock file (versions, licenses, DLL list) before
committing it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "packaging" / "windows_ocr_runtime.lock.json"
REPOSITORIES = (
    "https://repo.msys2.org/mingw/ucrt64/",
    "https://mirror.msys2.org/mingw/ucrt64/",
)
SOURCE_REPOSITORIES = (
    "https://repo.msys2.org/mingw/sources/",
    "https://mirror.msys2.org/mingw/sources/",
)
PREFIX = "ucrt64/"
# Packages whose binary archives ship no licence file: take the upstream
# licence text from the pinned MSYS2 *source* package instead.
LICENSE_SOURCES = (
    ("mingw-w64-ucrt-x86_64-giflib", "giflib", ("COPYING",)),
    ("mingw-w64-ucrt-x86_64-lz4", "lz4", ("LICENSE", "lib/LICENSE")),
    ("mingw-w64-ucrt-x86_64-libidn2", "libidn2",
     ("COPYING", "COPYING.LESSERv3", "COPYINGv2", "COPYING.unicode")),
)
LANGUAGES = ("eng", "lav", "rus", "osd")
MAX_DOWNLOAD = 80_000_000
USER_AGENT = "statistical-research-assistant-ocr-bundler/1.0"

# Licence notes reviewed for the runtime closure. Keys are MSYS2 package
# names without the "mingw-w64-ucrt-x86_64-" prefix.
LICENSE_NOTES = {
    "jbigkit": "GPL-2.0-or-later (libjbig source headers: 'version 2 of the "
               "License, or (at your option) any later version'; MSYS2 metadata "
               "says GPL-2.0). It is loaded by libtiff inside tesseract.exe, so "
               "that program is redistributed under terms compatible with "
               "GPL-3.0-or-later; its corresponding source is the MSYS2 source "
               "packages listed in this file plus the pinned lock file.",
    "libidn2": "Dual GPL-2.0-or-later / LGPL-3.0-or-later; used as a dynamic library.",
    "libunistring": "LGPL-3.0-or-later OR GPL-3.0-or-later; used as a dynamic library.",
    "libiconv": "LGPL-2.1-or-later; used as a dynamic library.",
    "gettext-runtime": "libintl: LGPL-2.1-or-later; used as a dynamic library.",
    "libgcc": "GPL-3.0-or-later WITH GCC Runtime Library Exception 3.1.",
    "libstdc++": "GPL-3.0-or-later WITH GCC Runtime Library Exception 3.1.",
    "libgomp": "GPL-3.0-or-later WITH GCC Runtime Library Exception 3.1.",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(name: str, expected: str | None = None, *, cache: Path | None = None,
             repositories=REPOSITORIES) -> bytes:
    if cache is not None:
        cached = cache / name
        if cached.is_file():
            data = cached.read_bytes()
            if expected is None or sha256(data) == expected:
                return data
    last = None
    for base in repositories:
        for attempt in range(4):
            try:
                request = urllib.request.Request(base + name, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=120) as response:
                    data = response.read(MAX_DOWNLOAD + 1)
                if len(data) > MAX_DOWNLOAD:
                    raise RuntimeError(f"{name} exceeds the download limit")
                if expected is not None and sha256(data) != expected:
                    raise RuntimeError(f"SHA-256 mismatch for {name}")
                if cache is not None:
                    cache.mkdir(parents=True, exist_ok=True)
                    (cache / name).write_bytes(data)
                return data
            except Exception as error:  # retry with backoff, then next mirror
                last = error
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not download {name}: {last}")


def open_package(data: bytes) -> tarfile.TarFile:
    import zstandard

    raw = zstandard.ZstdDecompressor().decompress(data, max_output_size=400_000_000)
    return tarfile.open(fileobj=io.BytesIO(raw), mode="r:")


def safe_relative(path: str) -> PurePosixPath:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise RuntimeError(f"Unsafe archive path: {path}")
    return pure


# ----------------------------------------------------------------- fetch

def fetch(out: Path, *, cache: Path | None = None) -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in lock["packages"]}
    wanted: dict[str, list[dict]] = {}
    for entry in lock["files"]:
        wanted.setdefault(entry["package"], []).append(entry)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written = []
    for name, entries in sorted(wanted.items()):
        package = packages[name]
        data = download(package["filename"], package["sha256"], cache=cache)
        members = {e["archive_path"]: e for e in entries}
        with open_package(data) as archive:
            for member in archive.getmembers():
                entry = members.pop(member.name, None)
                if entry is None:
                    continue
                if not member.isfile():
                    raise RuntimeError(f"{member.name} is not a regular file")
                content = archive.extractfile(member).read()
                if sha256(content) != entry["sha256"] or len(content) != entry["size"]:
                    raise RuntimeError(f"Pinned file hash mismatch: {member.name}")
                target = out / safe_relative(entry["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                written.append(entry)
        if members:
            raise RuntimeError(f"{name} lacks pinned files: {sorted(members)}")
    for source in lock.get("license_sources", []):
        data = download(source["filename"], source["sha256"], cache=cache,
                        repositories=SOURCE_REPOSITORIES)
        for member, content in _source_members(data, source["inner"], [
            m["member"] for m in source["members"]
        ]).items():
            entry = next(m for m in source["members"] if m["member"] == member)
            if sha256(content) != entry["sha256"]:
                raise RuntimeError(f"Pinned licence hash mismatch: {member}")
            target = out / safe_relative(entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    # tessdata language models are Apache-2.0, like Tesseract itself.
    apache = out / "licenses" / "tesseract-ocr" / "LICENSE"
    if apache.is_file():
        target = out / "licenses" / "tesseract-data" / "LICENSE"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(apache.read_bytes())
    notices = third_party_notices(lock)
    (out / "THIRD_PARTY_NOTICES.txt").write_text(notices, encoding="utf-8")
    (out / "README.txt").write_text(
        "Bundled offline OCR runtime for Statistical Research Assistant.\n"
        f"Tesseract {lock['tesseract_version']} (MSYS2 UCRT64 build) with "
        f"{', '.join(LANGUAGES)} language data.\n"
        "Runs locally only; documents are never uploaded.\n"
        "See THIRD_PARTY_NOTICES.txt and licenses/ for licence terms.\n",
        encoding="utf-8",
    )
    manifest = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        content = path.read_bytes()
        manifest.append({
            "path": path.relative_to(out).as_posix(), "size": len(content),
            "sha256": sha256(content),
        })
    (out / "MANIFEST.json").write_text(json.dumps({
        "format": 1, "tesseract_version": lock["tesseract_version"],
        "source": lock["source"], "languages": list(LANGUAGES), "files": manifest,
    }, indent=1), encoding="utf-8")
    total = sum(e["size"] for e in manifest)
    print(f"Prepared {len(manifest)} files ({total/1e6:.1f} MB) in {out}")


def _source_members(data: bytes, inner: str, members: list[str]) -> dict[str, bytes]:
    """Read files from the upstream tarball nested in an MSYS2 source package."""
    with open_package(data) as outer:
        nested = next(m for m in outer.getmembers() if m.name.endswith("/" + inner))
        payload = outer.extractfile(nested).read()
    found = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name in members:
                found[member.name] = archive.extractfile(member).read()
    missing = set(members) - set(found)
    if missing:
        raise RuntimeError(f"Licence files missing from {inner}: {sorted(missing)}")
    return found


def third_party_notices(lock: dict) -> str:
    lines = [
        "THIRD-PARTY NOTICES — bundled offline OCR runtime",
        "=" * 52, "",
        "Statistical Research Assistant redistributes the following unmodified",
        "binary packages from the MSYS2 project (UCRT64 repository). Full licence",
        "texts shipped with the packages are in the licenses/ folder. Corresponding",
        "source code for every package is available from the MSYS2 source archive:",
        "https://repo.msys2.org/mingw/sources/ (file names listed below) and from",
        "each upstream project. The tesseract.exe process is invoked as a separate",
        "program; the application does not link against these libraries.",
        "",
        "GPL/LGPL components (jbigkit, libidn2, libunistring, libiconv, libintl)",
        "are provided under their licences, which permit replacing the DLLs. On",
        "request, the maintainers provide the exact corresponding source packages",
        "named here; they are also published by MSYS2 at the URL above.",
        "",
        "Tesseract language data (eng, lav, rus, osd; tessdata_fast 4.1.0) is",
        "Apache-2.0: see licenses/tesseract-data/LICENSE.",
        "",
    ]
    for package in sorted(lock["packages"], key=lambda p: p["name"]):
        if not package.get("used"):
            continue
        short = package["name"].replace("mingw-w64-ucrt-x86_64-", "")
        lines += [
            f"* {short} {package['version']}",
            f"  Licence (MSYS2 metadata): {package['license']}",
            f"  Upstream: {package.get('url', '')}",
            f"  Binary: {package['filename']} (SHA-256 {package['sha256']})",
            f"  Source: mingw-w64-{package['base'].replace('mingw-w64-', '')}-{package['version']}.src.tar.zst",
        ]
        if short in LICENSE_NOTES:
            lines.append(f"  Note: {LICENSE_NOTES[short]}")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ lock

def _parse_db(data: bytes) -> dict[str, dict[str, list[str]]]:
    packages = {}
    with open_package(data) as archive:
        for member in archive.getmembers():
            if not member.name.endswith("/desc"):
                continue
            text = archive.extractfile(member).read().decode("utf-8")
            fields = {}
            for block in text.split("\n\n"):
                rows = block.strip().split("\n")
                if rows and rows[0].startswith("%"):
                    fields[rows[0].strip("%")] = rows[1:]
            packages[fields["NAME"][0]] = fields
    return packages


def lock_runtime() -> None:
    import pefile

    db = _parse_db(download("ucrt64.db"))
    provides = {}
    for name, fields in db.items():
        for item in fields.get("PROVIDES", []):
            provides[re.split("[<>=]", item)[0]] = name

    def resolve(dep: str) -> str:
        base = re.split("[<>=]", dep)[0]
        return base if base in db else provides[base]

    roots = ["mingw-w64-ucrt-x86_64-tesseract-ocr"] + [
        f"mingw-w64-ucrt-x86_64-tesseract-data-{code}" for code in LANGUAGES
    ]
    closure, todo = [], list(roots)
    while todo:
        name = todo.pop()
        if name in closure:
            continue
        closure.append(name)
        todo += [resolve(d) for d in db[name].get("DEPENDS", [])]
    contents: dict[str, dict[str, bytes]] = {}
    for name in closure:
        fields = db[name]
        data = download(fields["FILENAME"][0], fields["SHA256SUM"][0])
        with open_package(data) as archive:
            contents[name] = {
                m.name: archive.extractfile(m).read()
                for m in archive.getmembers() if m.isfile() and (
                    m.name.startswith(PREFIX + "bin/") and m.name.lower().endswith((".exe", ".dll"))
                    or m.name.startswith(PREFIX + "share/licenses/")
                    or m.name.startswith(PREFIX + "share/tessdata/") and m.name.endswith(".traineddata")
                )
            }
    binaries = {
        PurePosixPath(path).name.lower(): (name, path)
        for name, files in contents.items() for path in files
        if path.startswith(PREFIX + "bin/")
    }
    needed, todo = [], ["tesseract.exe"]
    while todo:
        dll = todo.pop().lower()
        if dll in needed or dll not in binaries:
            continue
        needed.append(dll)
        name, path = binaries[dll]
        image = pefile.PE(data=contents[name][path], fast_load=True)
        image.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
        ])
        for attribute in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for item in getattr(image, attribute, []):
                todo.append(item.dll.decode())
    files, used = [], set()
    for dll in sorted(needed):
        name, path = binaries[dll]
        used.add(name)
        content = contents[name][path]
        files.append({"package": name, "archive_path": path,
                      "path": "bin/" + PurePosixPath(path).name,
                      "sha256": sha256(content), "size": len(content)})
    for code in LANGUAGES:
        name = f"mingw-w64-ucrt-x86_64-tesseract-data-{code}"
        path = f"{PREFIX}share/tessdata/{code}.traineddata"
        content = contents[name][path]
        used.add(name)
        files.append({"package": name, "archive_path": path,
                      "path": f"tessdata/{code}.traineddata",
                      "sha256": sha256(content), "size": len(content)})
    for name in sorted(used):
        for path, content in sorted(contents[name].items()):
            if path.startswith(PREFIX + "share/licenses/"):
                relative = PurePosixPath(path).relative_to(PREFIX + "share/licenses")
                files.append({"package": name, "archive_path": path,
                              "path": "licenses/" + relative.as_posix(),
                              "sha256": sha256(content), "size": len(content)})
    packages = []
    for name in sorted(closure):
        fields = db[name]
        packages.append({
            "name": name, "version": fields["VERSION"][0],
            "base": fields.get("BASE", [name])[0],
            "filename": fields["FILENAME"][0], "sha256": fields["SHA256SUM"][0],
            "license": " / ".join(fields.get("LICENSE", ["unknown"])),
            "url": fields.get("URL", [""])[0], "used": name in used,
        })
    license_sources = []
    for name, stem, wanted in LICENSE_SOURCES:
        if name not in used:
            continue
        fields = db[name]
        package_version = fields["VERSION"][0]
        upstream = package_version.rsplit("-", 1)[0]
        filename = f"{fields.get('BASE', [name])[0]}-{package_version}.src.tar.zst"
        data = download(filename, repositories=SOURCE_REPOSITORIES)
        inner = f"{stem}-{upstream}.tar.gz"
        members = [f"{stem}-{upstream}/{w}" for w in wanted]
        found = _source_members(data, inner, members)
        license_sources.append({
            "package": name, "filename": filename, "sha256": sha256(data),
            "inner": inner, "members": [
                {"member": m, "path": f"licenses/{stem}/{m.split('/', 1)[1].replace('/', '-')}",
                 "sha256": sha256(found[m]), "size": len(found[m])}
                for m in members
            ],
        })
    version = db["mingw-w64-ucrt-x86_64-tesseract-ocr"]["VERSION"][0]
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps({
        "format": 1, "source": "MSYS2 UCRT64 binary repository",
        "repositories": list(REPOSITORIES), "tesseract_version": version,
        "languages": list(LANGUAGES), "packages": packages, "files": files,
        "license_sources": license_sources,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"Locked Tesseract {version}: {len(needed)} binaries, "
          f"{len(used)} packages used of {len(closure)} resolved.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download pinned packages and build the runtime")
    f.add_argument("--out", type=Path, default=ROOT / "bundled_ocr" / "windows-x64")
    f.add_argument("--cache", type=Path, default=None)
    sub.add_parser("lock", help="re-resolve the pinned package/DLL closure")
    args = parser.parse_args(argv)
    if args.command == "fetch":
        fetch(args.out, cache=args.cache)
    else:
        lock_runtime()
    return 0


if __name__ == "__main__":
    sys.exit(main())
