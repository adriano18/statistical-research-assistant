"""Install, verify, upgrade and uninstall the Windows installer (#44).

Windows CI only. Every check looks at the real machine: files on disk, the
Start-menu shortcut and its target, the "Installed apps" registration in
the registry, and the research data folder.

    python tools/check_installed_app.py install dist/StatisticalResearchAssistant-1.0.0-Setup.exe --log out/install.log
    python tools/check_installed_app.py verify --version 1.0.0 --json out/installed.json
    python tools/check_installed_app.py snapshot out/program-before.json
    python tools/check_installed_app.py unchanged out/program-before.json
    python tools/check_installed_app.py data out/data.json [--expect "Installed study"]
    python tools/check_installed_app.py uninstall --log out/uninstall.log
    python tools/check_installed_app.py removed
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_identity  # noqa: E402

EXE = "StatisticalResearchAssistant.exe"
UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                 "\\" + app_identity.INSTALLER_APP_ID + "_is1")


def program_folder() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / app_identity.NAME


def data_folder() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / app_identity.APP_ID


def start_menu_shortcut() -> Path:
    return (Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            / f"{app_identity.NAME}.lnk")


def registration() -> dict | None:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        return None
    values = {}
    with key:
        index = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, index)
            except OSError:
                break
            values[name] = value
            index += 1
    return values


def registrations_named(name: str) -> list[str]:
    """Every per-user and per-machine uninstall entry showing ``name``."""
    import winreg

    found = []
    for hive, path in ((winreg.HKEY_CURRENT_USER, UNINSTALL_KEY.rsplit("\\", 1)[0]),
                       (winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY.rsplit("\\", 1)[0])):
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with root:
            index = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(root, sub) as entry:
                        display = winreg.QueryValueEx(entry, "DisplayName")[0]
                except OSError:
                    continue
                if display == name:
                    found.append(sub)
    return found


def shortcut_target(link: Path) -> str:
    script = f"(New-Object -ComObject WScript.Shell).CreateShortcut('{link}').TargetPath"
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, check=False)
    return done.stdout.strip()


def fail(message: str) -> None:
    raise SystemExit(f"FAILED: {message}")


def cmd_install(args) -> dict:
    args.log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    done = subprocess.run([str(args.setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                           "/CURRENTUSER", f"/LOG={args.log}"], check=False)
    if done.returncode != 0:
        fail(f"setup exited with {done.returncode} (see {args.log})")
    return {"installed_in_seconds": round(time.monotonic() - started, 1)}


def cmd_verify(args) -> dict:
    folder = program_folder()
    exe = folder / EXE
    if not exe.is_file():
        fail(f"{exe} is missing")
    info = app_identity.read_build_info(folder / "app" / app_identity.BUILD_INFO)
    if args.version and info.version != args.version:
        fail(f"installed build_info.json says {info.version}, expected {args.version}")
    link = start_menu_shortcut()
    if not link.is_file():
        fail(f"no Start-menu shortcut at {link}")
    target = shortcut_target(link)
    if Path(target).resolve() != exe.resolve():
        fail(f"the Start-menu shortcut points to {target!r}, not {exe}")
    entry = registration()
    if entry is None:
        fail(f"no uninstall registration HKCU\\{UNINSTALL_KEY}")
    for name, expected in (("DisplayName", app_identity.NAME),
                           ("DisplayVersion", args.version or info.version)):
        if entry.get(name) != expected:
            fail(f"registration {name} is {entry.get(name)!r}, expected {expected!r}")
    location = Path(str(entry.get("InstallLocation", "")).rstrip("\\"))
    if location.resolve() != folder.resolve():
        fail(f"registered InstallLocation {location} differs from {folder}")
    duplicates = registrations_named(app_identity.NAME)
    if len(duplicates) != 1:
        fail(f"{len(duplicates)} installations are registered: {duplicates}")
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    return {"program_folder": str(folder), "version": info.version, "channel": info.channel,
            "shortcut": str(link), "publisher": entry.get("Publisher"),
            "uninstall": entry.get("UninstallString"), "registrations": duplicates,
            "installed_bytes": size, "per_user": True}


def _listing(folder: Path) -> dict[str, list]:
    listing = {}
    for path in sorted(folder.rglob("*")):
        if "__pycache__" in path.parts or not path.is_file():
            continue
        stat = path.stat()
        listing[path.relative_to(folder).as_posix()] = [stat.st_size, int(stat.st_mtime)]
    return listing


def cmd_snapshot(args) -> dict:
    listing = _listing(program_folder())
    Path(args.path).parent.mkdir(parents=True, exist_ok=True)
    Path(args.path).write_text(json.dumps(listing), encoding="utf-8")
    return {"files": len(listing)}


def cmd_unchanged(args) -> dict:
    """Nothing in the program folder was added or changed by running it."""
    before = json.loads(Path(args.path).read_text(encoding="utf-8"))
    after = _listing(program_folder())
    added = sorted(set(after) - set(before))
    changed = sorted(name for name in set(after) & set(before) if after[name] != before[name])
    removed = sorted(set(before) - set(after))
    if added or changed or removed:
        fail(f"the program folder changed while the application ran: added {added[:10]}, "
             f"changed {changed[:10]}, removed {removed[:10]}")
    return {"files": len(after), "unchanged": True}


def cmd_data(args) -> dict:
    root = data_folder()
    projects = {}
    for db in sorted((root / "projects").glob("*/project.sqlite3")):
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            title = con.execute("SELECT title FROM project").fetchone()[0]
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                fail(f"{db} failed its integrity check")
        projects[title] = db.parent.name
    surveys = sorted(p.name for p in (root / "surveys").glob("survey_*.sqlite3"))
    for title in args.expect or []:
        if title not in projects:
            fail(f"project {title!r} is not in {root} (found {sorted(projects)})")
    facts = {"data_folder": str(root), "projects": projects, "questionnaires": surveys}
    if args.path:
        Path(args.path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.path).write_text(json.dumps(facts, indent=1, ensure_ascii=False), encoding="utf-8")
    return facts


def cmd_uninstall(args) -> dict:
    entry = registration()
    if entry is None:
        fail("nothing to uninstall")
    command = str(entry["UninstallString"]).strip().strip('"')
    args.log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    subprocess.run([command, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={args.log}"],
                   check=False)
    # The uninstaller restarts itself from a temporary copy; wait for it.
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline and (registration() is not None
                                           or (program_folder() / EXE).exists()
                                           or any(program_folder().glob("unins*.*"))):
        time.sleep(2)
    return {"uninstalled_in_seconds": round(time.monotonic() - started, 1)}


def cmd_removed(args) -> dict:
    folder = program_folder()
    if (folder / EXE).exists():
        fail(f"{folder / EXE} is still there")
    left = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")) if folder.exists() else []
    if any(not name.startswith("app/data") and name != "app" for name in left):
        fail(f"the uninstaller left program files behind: {left[:15]}")
    if start_menu_shortcut().exists():
        fail("the Start-menu shortcut is still there")
    if registration() is not None:
        fail("the uninstall registration is still there")
    if not (data_folder() / "projects").is_dir():
        fail(f"the research data folder {data_folder()} is gone")
    return {"program_folder_left": left, "data_folder_kept": str(data_folder())}


def main(argv=None) -> int:
    if os.name != "nt":
        print("Installer checks run on Windows only.")
        return 2
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install")
    install.add_argument("setup", type=Path)
    install.add_argument("--log", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--version")
    for name in ("snapshot", "unchanged"):
        commands.add_parser(name).add_argument("path")
    data = commands.add_parser("data")
    data.add_argument("path", nargs="?")
    data.add_argument("--expect", action="append")
    uninstall = commands.add_parser("uninstall")
    uninstall.add_argument("--log", type=Path, required=True)
    commands.add_parser("removed")
    for sub in commands.choices.values():
        sub.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    facts = globals()[f"cmd_{args.command}"](args)
    print(json.dumps(facts, ensure_ascii=False))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(facts, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
