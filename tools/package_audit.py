"""Measure what a Windows desktop build is made of (Stage 34, issue #23).

    python tools/package_audit.py build/windows --markdown size.md --json size.json
    python tools/package_audit.py StatisticalResearchAssistant-Windows-x64.zip
    python tools/package_audit.py downloaded-artifact.zip      # nested ZIP

The input may be an extracted build folder, the distributed ZIP, or a CI
artifact ZIP that wraps the distributed ZIP. Every number is measured from the
bytes given: file sizes, per-file deflate sizes (taken from the ZIP when
there is one, otherwise compressed here with the same zlib settings), SHA-256
duplicates and the effect of leaving out a category. A category's saving is
the sum of its entries' compressed sizes plus their ZIP headers, which is
exactly how much smaller a ZIP without those files is.

Removal candidates are only *reported*; nothing is deleted. Each one carries
the reason it is not needed at runtime, so a reviewer can check the claim.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable, Iterator
import zipfile
import zlib

MiB = 1024 * 1024
# Local file header (30) + central directory entry (46) + name twice; ZIP64
# extras are not used for files this small.
ZIP_ENTRY_OVERHEAD = 76

# Category rules: (id, label, reason, predicate on the POSIX relative path).
_TESTS = re.compile(r"^site-packages/(?:[^/]+/)+(?:tests|test)/")


@dataclass(frozen=True)
class Entry:
    path: str           # POSIX path relative to the build root
    size: int           # uncompressed bytes
    compressed: int     # deflate bytes as stored (or as it would be stored)
    sha256: str


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    reason: str


CANDIDATES = (
    Candidate(
        "package-tests", "Test suites inside Python packages",
        "`tests`/`test` folders of installed packages (e.g. scipy/special/tests) "
        "are never imported by the application; `testing` modules that "
        "libraries import at runtime (numpy.testing, pandas._testing) are kept.",
    ),
    Candidate(
        "build-only-files", "Headers, stubs and build-only files",
        "C/C++ headers, Cython sources, import libraries and typing stubs are "
        "used to compile or type-check against a package, not to run it.",
    ),
    Candidate(
        "pillow-avif", "Pillow AVIF codec",
        "The application reads and writes PNG/JPEG/TIFF/PDF pages only; Pillow "
        "loads its AVIF plugin lazily and simply reports AVIF as unavailable "
        "without it.",
    ),
    Candidate(
        "app-dev-files", "Developer files copied with the application source",
        "Repository tests, developer tools, design documents with screenshots "
        "and README/ROADMAP are not read by the running application (checked "
        "with a source search; bundled OCR notices and licences are kept).",
    ),
)

_BUILD_ONLY = re.compile(r"\.(h|hpp|hxx|pxd|pyx|pxi|lib|a|pyi)$", re.IGNORECASE)
_APP_DEV = re.compile(
    r"^app/(tests|tools|docs|packaging)/|^app/(README|ROADMAP)\.md$|^app/\.github/"
)


def candidate_of(path: str) -> str | None:
    """The removal candidate a path belongs to, or None."""
    if path.startswith("app/bundled_ocr/"):
        return None  # verified runtime with its own manifest, notices, licences
    if _APP_DEV.search(path):
        return "app-dev-files"
    if not path.startswith("site-packages/"):
        return None
    if _TESTS.search(path):
        return "package-tests"
    if re.fullmatch(r"site-packages/PIL/_avif[^/]*\.pyd", path):
        return "pillow-avif"
    if _BUILD_ONLY.search(path):
        return "build-only-files"
    return None


# ------------------------------------------------------------------ readers

def _zip_entries(archive: zipfile.ZipFile) -> Iterator[Entry]:
    for info in archive.infolist():
        if info.is_dir():
            continue
        digest = hashlib.sha256()
        with archive.open(info) as stream:
            while chunk := stream.read(1 << 20):
                digest.update(chunk)
        yield Entry(_normalise(info.filename), info.file_size, info.compress_size,
                    digest.hexdigest())


def _deflate_size(data: bytes, level: int) -> int:
    packer = zlib.compressobj(level, zlib.DEFLATED, -15)
    return len(packer.compress(data)) + len(packer.flush())


def _dir_entries(root: Path, level: int) -> Iterator[Entry]:
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        data = path.read_bytes()
        stored = min(_deflate_size(data, level), len(data))
        yield Entry(path.relative_to(root).as_posix(), len(data), stored,
                    hashlib.sha256(data).hexdigest())


def _normalise(name: str) -> str:
    name = name.replace("\\", "/").lstrip("/")
    parts = PurePosixPath(name).parts
    if ".." in parts:
        raise ValueError(f"Unsafe path in archive: {name!r}")
    return name


@dataclass
class Layers:
    artifact_bytes: int | None = None
    distributed_zip_bytes: int | None = None
    wrapper_extras: list[tuple[str, int]] = field(default_factory=list)
    startup: list[dict] = field(default_factory=list)


def read_build(source: Path, *, level: int = 6) -> tuple[list[Entry], Layers]:
    """Entries of the build and the sizes of every packaging layer."""
    layers = Layers()
    if source.is_dir():
        layers.startup = _startup_results(source.rglob("gui-startup-result.json"))
        return list(_dir_entries(source, level)), layers
    with zipfile.ZipFile(source) as outer:
        names = [i.filename for i in outer.infolist() if not i.is_dir()]
        inner = [n for n in names if n.lower().endswith(".zip")]
        if len(inner) == 1 and not any(n.lower().endswith(".exe") for n in names):
            layers.artifact_bytes = source.stat().st_size
            info = outer.getinfo(inner[0])
            layers.distributed_zip_bytes = info.file_size
            layers.wrapper_extras = [(i.filename, i.compress_size) for i in outer.infolist()
                                     if not i.is_dir() and i.filename != inner[0]]
            layers.startup = [json.loads(outer.read(n)) | {"file": n} for n in names
                              if n.endswith("gui-startup-result.json")]
            data = outer.read(inner[0])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return list(_zip_entries(archive)), layers
        layers.distributed_zip_bytes = source.stat().st_size
        return list(_zip_entries(outer)), layers


def _startup_results(paths: Iterable[Path]) -> list[dict]:
    found = []
    for path in paths:
        try:
            found.append(json.loads(path.read_text(encoding="utf-8")) | {"file": path.name})
        except (OSError, ValueError):
            continue
    return found


# ------------------------------------------------------------- classifiers

def package_owners(entries: list[Entry], record_texts: dict[str, str]) -> dict[str, str]:
    """Top-level site-packages name → distribution, from installed RECORD files."""
    owners: dict[str, str] = {}
    for dist_info, text in record_texts.items():
        name = re.sub(r"-[^-]+\.dist-info$", "", dist_info)
        for line in text.splitlines():
            top = line.split(",", 1)[0].replace("\\", "/").split("/", 1)[0]
            if top and not top.endswith(".dist-info") and top not in ("..", "__pycache__"):
                owners.setdefault(_module_stem(top), name)
        owners.setdefault(dist_info, name)
    return owners


def _module_stem(top: str) -> str:
    return re.sub(r"\.(py|pyc|pyd|so)$", "", re.sub(r"\.cp\d+.*$", "", top))


def component_of(path: str, owners: dict[str, str]) -> tuple[str, str]:
    """(component, detail) of a build path."""
    parts = path.split("/")
    if parts[0] == "site-packages" and len(parts) > 1:
        top = parts[1]
        dist = owners.get(top) or owners.get(_module_stem(top))
        if dist is None:
            dist = re.sub(r"(-[^-]+)?\.dist-info$", "", re.sub(r"\.libs$", "", _module_stem(top)))
        return "Python packages", dist
    if parts[0] in ("Lib", "DLLs") or re.fullmatch(r"python3\d*\.dll", parts[0], re.IGNORECASE):
        return "Python runtime", parts[0]
    if parts[0] == "data":
        return "Flutter engine and UI", "data/" + (parts[1] if len(parts) > 1 else "")
    if parts[0] == "app":
        if len(parts) > 2 and parts[1] == "bundled_ocr":
            if "tessdata" in parts:
                return "Bundled OCR", "language data " + Path(parts[-1]).stem
            return "Bundled OCR", "engine and libraries" if "bin" in parts else "notices and manifest"
        if len(parts) > 2:
            return "Application", parts[1] + "/"
        return "Application", "code" if path.endswith(".pyc") else "other files"
    name = parts[0].lower()
    if re.fullmatch(r"(vcruntime|msvcp|concrt)\d+(_\d+)?\.dll", name):
        return "Microsoft C++ runtime", parts[0]
    if name.endswith(".exe"):
        return "Flutter engine and UI", "launcher"
    if name == "flutter_windows.dll":
        return "Flutter engine and UI", parts[0]
    if name.endswith(".dll"):
        return "Flutter engine and UI", "plugins"
    return "Other", parts[0]


# ----------------------------------------------------------------- report

def _stored(entries: Iterable[Entry]) -> int:
    return sum(e.compressed + ZIP_ENTRY_OVERHEAD + 2 * len(e.path.encode()) for e in entries)


def analyse(entries: list[Entry], layers: Layers, record_texts: dict[str, str],
            *, top: int = 25) -> dict:
    owners = package_owners(entries, record_texts)
    components: dict[str, dict] = defaultdict(lambda: {"files": 0, "bytes": 0,
                                                      "compressed": 0, "details": defaultdict(lambda: [0, 0, 0])})
    candidates: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        component, detail = component_of(entry.path, owners)
        bucket = components[component]
        bucket["files"] += 1
        bucket["bytes"] += entry.size
        bucket["compressed"] += entry.compressed
        row = bucket["details"][detail]
        row[0] += 1
        row[1] += entry.size
        row[2] += entry.compressed
        if (cid := candidate_of(entry.path)) is not None:
            candidates[cid].append(entry)

    by_hash: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        if entry.size >= 4096:
            by_hash[entry.sha256].append(entry)
    duplicates = sorted(
        ([g[0].size * (len(g) - 1), [e.path for e in g]] for g in by_hash.values() if len(g) > 1),
        reverse=True,
    )
    total = {"files": len(entries), "bytes": sum(e.size for e in entries),
             "compressed": sum(e.compressed for e in entries), "zip_estimate": _stored(entries)}
    return {
        "layers": {
            "artifact_bytes": layers.artifact_bytes,
            "distributed_zip_bytes": layers.distributed_zip_bytes,
            "wrapper_extras": layers.wrapper_extras,
        },
        "total": total,
        "components": {
            name: {
                "files": c["files"], "bytes": c["bytes"], "compressed": c["compressed"],
                "details": sorted(([k, *v] for k, v in c["details"].items()),
                                  key=lambda row: -row[2]),
            }
            for name, c in sorted(components.items(), key=lambda kv: -kv[1]["compressed"])
        },
        "candidates": [
            {
                "id": c.id, "label": c.label, "reason": c.reason,
                "files": len(candidates[c.id]),
                "bytes": sum(e.size for e in candidates[c.id]),
                "zip_saving": _stored(candidates[c.id]),
                "examples": [e.path for e in sorted(candidates[c.id], key=lambda e: -e.compressed)[:5]],
            }
            for c in CANDIDATES
        ],
        "duplicates": [{"wasted_bytes": w, "paths": p} for w, p in duplicates[:15]],
        "largest": [[e.path, e.size, e.compressed] for e in
                    sorted(entries, key=lambda e: -e.compressed)[:top]],
        "startup": layers.startup,
    }


def record_texts_of(source: Path) -> dict[str, str]:
    """RECORD files of the build, keyed by their dist-info folder name."""
    texts: dict[str, str] = {}
    if source.is_dir():
        for record in source.glob("site-packages/*.dist-info/RECORD"):
            texts[record.parent.name] = record.read_text(encoding="utf-8", errors="replace")
        return texts

    def collect(archive: zipfile.ZipFile) -> None:
        for name in archive.namelist():
            m = re.fullmatch(r"site-packages/([^/]+\.dist-info)/RECORD", _normalise(name))
            if m:
                texts[m.group(1)] = archive.read(name).decode("utf-8", errors="replace")

    with zipfile.ZipFile(source) as outer:
        inner = [n for n in outer.namelist() if n.lower().endswith(".zip")]
        if len(inner) == 1 and not any(n.lower().endswith(".exe") for n in outer.namelist()):
            with zipfile.ZipFile(io.BytesIO(outer.read(inner[0]))) as archive:
                collect(archive)
        else:
            collect(outer)
    return texts


def _mb(value: int | None) -> str:
    return "—" if value is None else f"{value / MiB:,.1f} MiB"


def _seconds(value) -> str:
    return f"{value:.2f} s" if isinstance(value, (int, float)) else "—"


def to_markdown(report: dict, title: str = "Windows package composition") -> str:
    total, layers = report["total"], report["layers"]
    lines = [f"## {title}", "", "| Layer | Size |", "|---|---|"]
    if layers["artifact_bytes"] is not None:
        lines.append(f"| CI artifact download (wrapper ZIP) | {_mb(layers['artifact_bytes'])} "
                     f"({layers['artifact_bytes']:,} B) |")
    if layers["distributed_zip_bytes"] is not None:
        lines.append(f"| Distributed ZIP | {_mb(layers['distributed_zip_bytes'])} "
                     f"({layers['distributed_zip_bytes']:,} B) |")
    lines.append(f"| Installed (extracted) | {_mb(total['bytes'])} ({total['bytes']:,} B, "
                 f"{total['files']:,} files) |")
    lines.append(f"| Sum of per-file deflate sizes | {_mb(total['compressed'])} |")
    lines += ["", "| Component | Files | Installed | Compressed | Largest parts (compressed) |",
              "|---|---:|---:|---:|---|"]
    for name, c in report["components"].items():
        parts = ", ".join(f"{detail} {_mb(compressed)}"
                          for detail, _files, _bytes, compressed in c["details"][:4])
        lines.append(f"| {name} | {c['files']:,} | {_mb(c['bytes'])} | {_mb(c['compressed'])} | {parts} |")
    lines += ["", "| Not needed at runtime (candidate) | Files | Installed | ZIP saving | Why |",
              "|---|---:|---:|---:|---|"]
    for c in report["candidates"]:
        lines.append(f"| {c['label']} | {c['files']:,} | {_mb(c['bytes'])} | "
                     f"{_mb(c['zip_saving'])} | {c['reason']} |")
    if report["duplicates"]:
        lines += ["", "| Identical copies (≥ 4 KiB) | Wasted |", "|---|---:|"]
        for d in report["duplicates"][:8]:
            lines.append(f"| {' = '.join(d['paths'][:3])} | {_mb(d['wasted_bytes'])} |")
    if report["startup"]:
        lines += ["", "| Startup check | Window visible | Interface ready | Longest black |",
                  "|---|---:|---:|---:|"]
        for s in report["startup"]:
            lines.append(f"| {s.get('file')} | {_seconds(s.get('window_visible_after_s'))} | "
                         f"{_seconds(s.get('interface_ready_reported_s'))} | "
                         f"{_seconds(s.get('longest_black_s'))} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="build folder, distributed ZIP or CI artifact ZIP")
    parser.add_argument("--json", type=Path, help="write the full report as JSON")
    parser.add_argument("--markdown", type=Path, help="write a Markdown summary")
    parser.add_argument("--title", default="Windows package composition")
    parser.add_argument("--level", type=int, default=6, help="zlib level for folders (default 6)")
    parser.add_argument("--budget-installed-mib", type=float,
                        help="fail when the installed size exceeds this many MiB")
    parser.add_argument("--budget-zip-mib", type=float,
                        help="fail when the (estimated) distributed ZIP exceeds this many MiB")
    args = parser.parse_args(argv)

    entries, layers = read_build(args.source, level=args.level)
    report = analyse(entries, layers, record_texts_of(args.source))
    markdown = to_markdown(report, args.title)
    if args.json:
        args.json.write_text(json.dumps(report, indent=1), encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown, encoding="utf-8")
    print(markdown)

    failures = []
    installed = report["total"]["bytes"] / MiB
    zipped = (layers.distributed_zip_bytes or report["total"]["zip_estimate"]) / MiB
    if args.budget_installed_mib is not None and installed > args.budget_installed_mib:
        failures.append(f"installed size {installed:,.1f} MiB > budget {args.budget_installed_mib:,.1f} MiB")
    if args.budget_zip_mib is not None and zipped > args.budget_zip_mib:
        failures.append(f"ZIP size {zipped:,.1f} MiB > budget {args.budget_zip_mib:,.1f} MiB")
    for failure in failures:
        print(f"Size budget exceeded: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
