"""Apply the Windows build's package cleanup to any Python environment.

    python tools/prune_packages.py --dry-run          # list what would go
    python tools/prune_packages.py                    # prune this interpreter
    python tools/prune_packages.py --site-packages D  # prune another folder

`flet build` removes files from the bundled site-packages with
serious_python's default globs plus `[tool.flet.cleanup] package_files` from
pyproject.toml. This script applies exactly that list, with the same
matching rules, so CI can run the complete test suite on an environment
pruned like the Windows bundle and prove that nothing the application
imports at runtime was removed (issue #23).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys
import sysconfig
import tomllib

ROOT = Path(__file__).resolve().parents[1]

# serious_python `package` command, junkFilesDesktop (flet-dev/serious-python,
# src/serious_python/bin/package_command.dart). They apply whether or not a
# project adds its own globs.
SERIOUS_PYTHON_DEFAULTS = (
    "**.c", "**.h", "**.cpp", "**.hpp", "**.typed", "**.pyi", "**.pxd", "**.pyx",
    "**.a", "**.pdb", "__pycache__", "**/__pycache__",
)


def project_globs(pyproject: Path = ROOT / "pyproject.toml") -> tuple[str, ...]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    extra = data.get("tool", {}).get("flet", {}).get("cleanup", {}).get("package_files", [])
    if isinstance(extra, str):
        extra = [part for part in extra.split(",")]
    return tuple(g.strip() for g in extra if g.strip())


def glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a cleanup glob into a regex over POSIX paths relative to
    site-packages: ``**/`` = any leading folders (or none), ``**`` = anything,
    ``*`` = anything within one name, ``?`` = one character of a name."""
    out, i = [], 0
    pattern = pattern.replace("\\", "/")
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(relative: str, regexes) -> bool:
    return any(r.match(relative) for r in regexes)


def find_removals(site_packages: Path, globs) -> list[Path]:
    """Top-most paths that match, walking folders like serious_python does."""
    regexes = [glob_regex(g) for g in globs]
    found: list[Path] = []

    def walk(folder: Path) -> None:
        for entry in sorted(folder.iterdir()):
            relative = entry.relative_to(site_packages).as_posix()
            if matches(relative, regexes):
                found.append(entry)
            elif entry.is_dir() and not entry.is_symlink():
                walk(entry)

    walk(site_packages)
    return found


def _size(path: Path) -> int:
    if path.is_file() or path.is_symlink():
        return path.lstat().st_size
    return sum(p.lstat().st_size for p in path.rglob("*") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-packages", type=Path,
                        default=Path(sysconfig.get_paths()["purelib"]))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="print every removed path")
    args = parser.parse_args(argv)

    globs = SERIOUS_PYTHON_DEFAULTS + project_globs()
    removals = find_removals(args.site_packages, globs)
    total = sum(_size(p) for p in removals)
    for path in removals:
        if args.list or args.dry_run:
            print(path.relative_to(args.site_packages).as_posix())
        if not args.dry_run:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    verb = "Would remove" if args.dry_run else "Removed"
    print(f"{verb} {len(removals)} paths ({total / 1024 / 1024:.1f} MiB) from "
          f"{args.site_packages} using {len(globs)} globs", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
