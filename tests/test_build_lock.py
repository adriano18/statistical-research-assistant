"""Stage 36.8 (issue #62): the build is pinned, hashed and checked.

- requirements.txt pins every bundled package with SHA-256 hashes and
  satisfies the ranges of requirements.in; requirements-dev.txt does the same
  for build and test tools and agrees with the runtime lock.
- Every CI job uses the exact Python of packaging/build_toolchain.lock.json
  and installs only hashed locks; every Windows build uses the verified
  toolchain (Flutter SDK, flet build template) and the Inno Setup of the lock.
- tools/build_toolchain.py: lock parsing, marker evaluation for the bundled
  Windows runtime, bundle package checks, template and SDK preparation, and
  the two-build comparison (PE timestamps, .pyc headers, zip metadata).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_toolchain as toolchain  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
ACTION = ROOT / ".github" / "actions" / "pinned-windows-toolchain" / "action.yml"
LOCK = toolchain.load_lock()


def _pins(path: Path) -> dict[str, toolchain.Pin]:
    return {toolchain.canonical(p.name): p for p in toolchain.parse_lock(path)}


def _direct(path: Path) -> list[Requirement]:
    lines = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [Requirement(line) for line in lines if line]


def _jobs(text: str) -> dict[str, str]:
    """Job name → its YAML text (the workflows use two-space job keys)."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\n", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class LockFileTests(unittest.TestCase):
    def test_runtime_lock_pins_every_package_with_hashes(self):
        pins = toolchain.parse_lock(toolchain.RUNTIME_LOCK)
        self.assertGreater(len(pins), 40)
        for pin in pins:
            self.assertTrue(pin.hashes, f"{pin.name} has no hash")
            self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", h) for h in pin.hashes))

    def test_dev_lock_pins_every_package_with_hashes(self):
        for pin in toolchain.parse_lock(toolchain.DEV_LOCK):
            self.assertTrue(pin.hashes, f"{pin.name} has no hash")

    def test_lock_satisfies_the_direct_requirements(self):
        pins = _pins(toolchain.RUNTIME_LOCK)
        for requirement in _direct(ROOT / "requirements.in"):
            name = toolchain.canonical(requirement.name)
            self.assertIn(name, pins, f"{name} of requirements.in is not locked")
            self.assertIn(pins[name].version, requirement.specifier, name)

    def test_dev_lock_satisfies_its_inputs(self):
        pins = _pins(toolchain.DEV_LOCK)
        for requirement in _direct(ROOT / "requirements-dev.in"):
            name = toolchain.canonical(requirement.name)
            self.assertIn(name, pins, name)
            self.assertIn(pins[name].version, requirement.specifier, name)

    def test_shared_packages_have_one_version(self):
        runtime, dev = _pins(toolchain.RUNTIME_LOCK), _pins(toolchain.DEV_LOCK)
        for name in set(runtime) & set(dev):
            self.assertEqual(runtime[name].version, dev[name].version, name)

    def test_one_flet_release_everywhere(self):
        version = LOCK["flet"]["version"]
        runtime, dev = _pins(toolchain.RUNTIME_LOCK), _pins(toolchain.DEV_LOCK)
        self.assertEqual(runtime["flet"].version, version)
        self.assertEqual(dev["flet-cli"].version, version)
        self.assertEqual(dev["flet-web"].version, version)
        self.assertEqual(LOCK["flet_build_template"]["url"],
                         f"https://github.com/flet-dev/flet/releases/download/v{version}/flet-build-template.zip")

    def test_lock_inputs_and_build_tools_stay_out_of_the_bundle(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        exclude = re.search(r"(?s)\[tool\.flet\.app\]\s*exclude = \[(.*?)\]", pyproject).group(1)
        for name in ("requirements.in", "requirements-dev.in", "requirements-dev.txt",
                     "tests", "tools", "docs", "packaging"):
            self.assertIn(f'"{name}"', exclude)
        self.assertNotRegex(pyproject, r"(?m)^\[project\]",
                            "a [project] table would make flet build ignore requirements.txt")


class ToolchainLockTests(unittest.TestCase):
    def test_downloads_are_https_with_sha256(self):
        for entry in (LOCK["flutter"]["windows_x64"], LOCK["flet_build_template"],
                      LOCK["python"]["python_build_manifest"]):
            self.assertTrue(entry["url"].startswith("https://"), entry["url"])
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_python_build_manifest_is_the_pinned_file(self):
        manifest = LOCK["python"]["python_build_manifest"]
        path = ROOT / manifest["path"]
        self.assertEqual(toolchain.sha256_file(path), manifest["sha256"])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["pythons"]["3.12"]["full_version"], LOCK["python"]["embedded"])

    def test_flutter_archive_is_the_release_of_the_lock(self):
        flutter = LOCK["flutter"]
        self.assertIn(f"flutter_windows_{flutter['version']}-stable.zip", flutter["windows_x64"]["url"])
        self.assertRegex(flutter["framework_revision"], r"^[0-9a-f]{40}$")

    def test_dart_lock_parses_when_present(self):
        path = ROOT / LOCK["flet_build_template"]["dart_lock"]
        if path.is_file():
            packages = toolchain.dart_packages(path)
            pinned = LOCK["flet_build_template"]["pinned_by_template"]
            for name in ("flet", "serious_python"):
                self.assertEqual(packages[name]["version"], pinned[name])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflows = {p.name: p.read_text(encoding="utf-8") for p in sorted(WORKFLOWS.glob("*.yml"))}

    def test_every_job_uses_the_exact_python_of_the_lock(self):
        action = ACTION.read_text(encoding="utf-8")
        self.assertIn(f'default: "{LOCK["python"]["windows_host"]}"', action)
        for name, text in self.workflows.items():
            for job, body in _jobs(text).items():
                versions = re.findall(r'python-version: "([^"]+)"', body)
                windows = "runs-on: windows" in body
                want = LOCK["python"]["windows_host" if windows else "linux_host"]
                for version in versions:
                    self.assertEqual(version, want, f"{name}/{job}")
                if "actions/setup-python" in body:
                    self.assertTrue(versions, f"{name}/{job} sets up Python without a version")

    def test_installs_come_only_from_hashed_locks(self):
        allowed_unhashed = {("windows-packaging-experiments.yml", 'python -m pip install "pyinstaller>=6.10,<7"')}
        texts = dict(self.workflows, **{"action.yml": ACTION.read_text(encoding="utf-8")})
        for name, text in texts.items():
            for line in re.findall(r"python -m pip install[^\n]*", text):
                if (name, line.strip()) in allowed_unhashed:
                    continue
                self.assertIn("--require-hashes", line, f"{name}: {line}")
                files = re.findall(r"-r (\S+)", line)
                self.assertTrue(files, f"{name}: {line}")
                self.assertTrue(set(files) <= {"requirements.txt", "requirements-dev.txt"}, f"{name}: {line}")
                self.assertNotRegex(line, r'"[A-Za-z]', f"{name} installs an unlocked package: {line}")

    def test_windows_builds_use_the_verified_toolchain(self):
        for name, text in self.workflows.items():
            if name == "windows-packaging-experiments.yml" or "flet build windows" not in text:
                continue
            self.assertIn("uses: ./.github/actions/pinned-windows-toolchain", text, name)
            for command in re.findall(r"flet build windows \.[^\n]*\n(?:\s+--[^\n]*\n)*", text):
                self.assertIn('--template "$env:SRA_FLET_TEMPLATE"', command, name)

    def test_inno_setup_comes_from_the_lock(self):
        for name, text in self.workflows.items():
            self.assertNotIn("choco install innosetup", text, name)
            if "build_installer.py" in text:
                self.assertIn("python tools/build_toolchain.py iscc", text, name)

    def test_release_build_is_checked_strictly(self):
        release = self.workflows["release.yml"]
        self.assertIn("build_toolchain.py identity --bundle build/windows --strict", release)
        self.assertIn("dist\\sbom.cdx.json", release)


def _wheelish_lock(text: str) -> Path:
    folder = Path(tempfile.mkdtemp())
    path = folder / "lock.txt"
    path.write_text(text, encoding="utf-8")
    return path


class ParseLockTests(unittest.TestCase):
    SAMPLE = (
        "# header\n"
        "anyio==4.16.0 ; sys_platform != 'emscripten' \\\n"
        "    --hash=sha256:" + "a" * 64 + " \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n"
        "    # via httpx\n"
        "pywin32==312 ; sys_platform == 'win32' \\\n"
        "    --hash=sha256:" + "c" * 64 + "\n"
        "numpy==2.5.4 \\\n"
        "    --hash=sha256:" + "d" * 64 + "\n"
    )

    def test_continuation_lines_markers_and_hashes(self):
        pins = toolchain.parse_lock(_wheelish_lock(self.SAMPLE))
        self.assertEqual([(p.name, p.version) for p in pins],
                         [("anyio", "4.16.0"), ("pywin32", "312"), ("numpy", "2.5.4")])
        self.assertEqual(len(pins[0].hashes), 2)
        self.assertEqual(pins[1].marker, "sys_platform == 'win32'")

    def test_markers_for_the_bundled_windows_runtime(self):
        pins = toolchain.parse_lock(_wheelish_lock(self.SAMPLE))
        windows = toolchain.applicable(pins, toolchain.marker_environment(windows=True, python="3.12.16"))
        self.assertEqual(windows, {"anyio": "4.16.0", "pywin32": "312", "numpy": "2.5.4"})
        linux = toolchain.applicable(pins, {"sys_platform": "linux"})
        self.assertNotIn("pywin32", linux)

    def test_an_unpinned_line_is_refused(self):
        with self.assertRaises(ValueError):
            toolchain.parse_lock(_wheelish_lock("pandas>=2.2\n"))


class BundleCheckTests(unittest.TestCase):
    def test_versions_from_metadata_or_folder_name(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            (site / "numpy-2.5.4.dist-info").mkdir()
            (site / "numpy-2.5.4.dist-info" / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: numpy\nVersion: 2.5.4\n\nbody", encoding="utf-8")
            (site / "python_docx-1.2.0.dist-info").mkdir()
            found = toolchain.bundled_distributions(site)
            self.assertEqual(found, {"numpy": "2.5.4", "python-docx": "1.2.0"})
            result = toolchain.compare_packages({"numpy": "2.5.4", "python-docx": "1.1.0", "scipy": "1.18.1"},
                                                dict(found, extra_pkg="1"))
            self.assertEqual(result["missing"], ["scipy"])
            self.assertEqual(result["extra"], ["extra_pkg"])
            self.assertEqual(result["mismatched"], {"python-docx": {"lock": "1.1.0", "found": "1.2.0"}})


class PrepareTests(unittest.TestCase):
    def test_template_is_checked_and_receives_the_dart_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            archive = temp / "template.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("build/cookiecutter.json", "{}")
                handle.writestr("build/{{cookiecutter.out_dir}}/pubspec.yaml", "name: x\n")
            dart_lock = temp / "pubspec.lock"
            dart_lock.write_text("packages:\n", encoding="utf-8")
            lock = {"flet_build_template": {"url": "https://example.invalid/t.zip",
                                            "sha256": toolchain.sha256_file(archive),
                                            "dart_lock": str(dart_lock)}}
            root = toolchain.prepare_template(lock, temp / "out", archive=archive)
            self.assertTrue((root / "cookiecutter.json").is_file())
            self.assertEqual((root / "{{cookiecutter.out_dir}}" / "pubspec.lock").read_text(), "packages:\n")
            identity = json.loads((temp / "out" / "template-identity.json").read_text())
            self.assertTrue(identity["dart_lock"])
            lock["flet_build_template"]["sha256"] = "0" * 64
            with self.assertRaises(SystemExit):
                toolchain.prepare_template(lock, temp / "out2", archive=archive)

    def test_an_existing_sdk_must_be_the_locked_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            sdk = Path(temp) / "3.47.9"
            (sdk / ".git").mkdir(parents=True)
            revision = LOCK["flutter"]["framework_revision"]
            (sdk / ".git" / "HEAD").write_text(revision + "\n", encoding="utf-8")
            self.assertEqual(toolchain.prepare_flutter(LOCK, home=sdk), sdk)
            (sdk / ".git" / "HEAD").write_text("ref: refs/heads/stable\n", encoding="utf-8")
            (sdk / ".git" / "packed-refs").write_text(f"{'f' * 40} refs/heads/stable\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                toolchain.prepare_flutter(LOCK, home=sdk)

    def test_only_https_downloads(self):
        with self.assertRaises(SystemExit):
            toolchain.download("http://example.invalid/x", Path(tempfile.mkdtemp()) / "x", "0" * 64)

    def test_the_real_iscc_is_found_before_the_chocolatey_shim(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "Inno Setup 6" / "ISCC.exe"
            real.parent.mkdir()
            real.write_bytes(b"MZ")
            shim = r"C:\ProgramData\chocolatey\bin\ISCC.exe"
            with mock.patch.dict("os.environ", {"ProgramFiles(x86)": temp, "ProgramFiles": ""}), \
                    mock.patch("shutil.which", return_value=shim):
                self.assertEqual(toolchain.find_iscc(), real)
            with mock.patch.dict("os.environ", {"ProgramFiles(x86)": "", "ProgramFiles": ""}), \
                    mock.patch("shutil.which", return_value=shim):
                self.assertIsNone(toolchain.find_iscc(), "the shim reports version 0.0.0")

    def test_version_numbers_are_normalised(self):
        self.assertEqual(toolchain.normalize_version("6.7.1.0"), "6.7.1")
        self.assertEqual(toolchain.normalize_version(" 6.7.1 "), "6.7.1")


def _pe(timestamp: int, guid: bytes, body: bytes = b"code") -> bytes:
    """A minimal PE32+ image with one section holding a CodeView debug entry."""
    e_lfanew = 0x40
    optional_size = 240
    section_table = e_lfanew + 4 + 20 + optional_size
    raw_pointer = 0x200
    debug_rva = 0x1000
    image = bytearray(0x400)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, e_lfanew)
    image[e_lfanew:e_lfanew + 4] = b"PE\0\0"
    coff = e_lfanew + 4
    struct.pack_into("<HHIIIHH", image, coff, 0x8664, 1, timestamp, 0, 0, optional_size, 0x22)
    optional = coff + 20
    struct.pack_into("<H", image, optional, 0x20B)
    struct.pack_into("<I", image, optional + 64, timestamp ^ 0x5A5A)       # CheckSum
    struct.pack_into("<II", image, optional + 112 + 6 * 8, debug_rva, 28)  # debug directory
    struct.pack_into("<8sIIII", image, section_table, b".rdata", 0x100, debug_rva, 0x100, raw_pointer)
    codeview = raw_pointer + 28
    struct.pack_into("<IIHHIIII", image, raw_pointer, 0, timestamp, 0, 0, 2, 24, 0, codeview)
    image[codeview:codeview + 4] = b"RSDS"
    image[codeview + 4:codeview + 20] = guid
    struct.pack_into("<I", image, codeview + 20, 1)
    image[0x300:0x300 + len(body)] = body
    return bytes(image)


class ManifestCompareTests(unittest.TestCase):
    def _zip(self, path: Path, when: tuple) -> None:
        with zipfile.ZipFile(path, "w") as handle:
            info = zipfile.ZipInfo("a.txt", date_time=when)
            handle.writestr(info, "same contents")

    def test_deviations_are_classified(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a", Path(temp) / "b"
            for folder in (a, b):
                (folder / "app").mkdir(parents=True)
                (folder / "same.txt").write_text("identical", encoding="utf-8")
            (a / "app" / "build_info.json").write_text('{"built_at": "1"}', encoding="utf-8")
            (b / "app" / "build_info.json").write_text('{"built_at": "2"}', encoding="utf-8")
            (a / "runner.exe").write_bytes(_pe(1000, b"\x01" * 16))
            (b / "runner.exe").write_bytes(_pe(2000, b"\x02" * 16))
            (a / "changed.dll").write_bytes(_pe(1000, b"\x01" * 16, b"one"))
            (b / "changed.dll").write_bytes(_pe(1000, b"\x01" * 16, b"two"))
            (a / "m.pyc").write_bytes(b"\x01" * 16 + b"body")
            (b / "m.pyc").write_bytes(b"\x02" * 16 + b"body")
            self._zip(a / "lib.zip", (2026, 1, 1, 0, 0, 0))
            self._zip(b / "lib.zip", (2026, 2, 2, 0, 0, 0))
            (a / "notes.txt").write_text("x", encoding="utf-8")
            (b / "notes.txt").write_text("y", encoding="utf-8")
            (a / "only-a.txt").write_text("a", encoding="utf-8")
            result = toolchain.compare_manifests(toolchain.manifest(a), toolchain.manifest(b))
        kinds = {d["path"]: d["kind"] for d in result["deviations"]}
        self.assertEqual(result["identical"], 1)
        self.assertEqual(result["only_in_a"], ["only-a.txt"])
        self.assertEqual(kinds["app/build_info.json"], "build metadata (version, commit, build time)")
        self.assertEqual(kinds["runner.exe"], "PE link timestamp, checksum or PDB id only")
        self.assertEqual(kinds["changed.dll"], "content differs")
        self.assertEqual(kinds["m.pyc"], ".pyc header (source timestamp) only")
        self.assertEqual(kinds["lib.zip"], "zip metadata (timestamps, order) only, same members")
        self.assertEqual(kinds["notes.txt"], "content differs")
        markdown = toolchain.comparison_markdown(result, "Test")
        self.assertIn("| PE link timestamp, checksum or PDB id only | 1 |", markdown)

    def test_not_a_pe_image(self):
        self.assertIsNone(toolchain.pe_normalized_sha256(b"not an executable"))
        self.assertIsNone(toolchain.pe_normalized_sha256(b"MZ" + b"\0" * 10))


class PubspecLockTests(unittest.TestCase):
    def test_hosted_sdk_and_path_packages(self):
        text = (
            "# Generated by pub\n"
            "packages:\n"
            "  async:\n"
            "    dependency: transitive\n"
            "    description:\n"
            "      name: async\n"
            '      sha256: "' + "e" * 64 + '"\n'
            '      url: "https://pub.dev"\n'
            "    source: hosted\n"
            '    version: "2.13.0"\n'
            "  flutter:\n"
            '    dependency: "direct main"\n'
            "    description: flutter\n"
            "    source: sdk\n"
            '    version: "0.0.0"\n'
            "sdks:\n"
            '  dart: ">=3.7.0 <4.0.0"\n'
        )
        packages = toolchain.parse_pubspec_lock(text)
        self.assertEqual(packages["async"], {"version": "2.13.0", "source": "hosted", "sha256": "e" * 64})
        self.assertEqual(packages["flutter"]["source"], "sdk")
        self.assertNotIn("dart", packages)
        drift = toolchain.compare_dart(packages, {**packages, "async": {**packages["async"], "version": "2.14.0"}})
        self.assertEqual(list(drift["changed"]), ["async"])


if __name__ == "__main__":
    unittest.main()
