"""Stage 35 (#45): in-app updates. Signed manifests, the rules that decide
whether an update is offered, downloads against a local HTTP server
(resume, damage, cancel, redirects, offline), code-signature decisions,
the handoff to the installer and the report after the restart. The A->B
update of the installed program runs on Windows CI."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

import app_identity as ai  # noqa: E402
import project_store as ps  # noqa: E402
import update_client as uc  # noqa: E402
import update_manifest as um  # noqa: E402
import update_ui  # noqa: E402
from update_signing import new_key  # noqa: E402

PRIVATE, PUBLIC = new_key()
OTHER_PRIVATE, OTHER_PUBLIC = new_key()
INSTALLER = os.urandom(1_200_000)   # just over the 1 MiB minimum
DIGEST = hashlib.sha256(INSTALLER).hexdigest()


def manifest(**changes) -> dict:
    value = {
        "format": 1, "app_id": ai.INSTALLER_APP_ID, "channel": "test",
        "version": "1.0.1-test.1", "build": "2", "published_at": "2026-11-06T12:00:00+00:00",
        "minimum_version": "1.0.0-test.0", "project_format": ps.SCHEMA_VERSION,
        "installer": {"url": "http://127.0.0.1:{port}/setup.exe", "size": len(INSTALLER),
                      "sha256": DIGEST, "signed": False, "publisher": ""},
        "changelog": {"en": "Fictional change list.", "ru": "Вымышленный список изменений."},
        "known_limitations": {"en": "None known."},
        "release_notes_url": "https://github.com/adriano18/statistical-research-assistant/releases",
    }
    for key, item in changes.items():
        if key in value["installer"] and key not in value:
            value["installer"][key] = item
        else:
            value[key] = item
    return value


def envelope(payload: dict, *, key: str = PRIVATE, port: int = 1) -> bytes:
    raw = json.dumps(payload).replace("{port}", str(port)).encode()
    return json.dumps(um.sign_payload(raw, key)).encode()


def build(channel="test", version="1.0.0-test.1", port=1, **extra) -> ai.BuildInfo:
    return ai.BuildInfo(version=version, channel=channel, update_keys=(PUBLIC,),
                        test_endpoint=f"http://127.0.0.1:{port}/manifest.json" if channel == "test" else "",
                        **extra)


class ManifestTests(unittest.TestCase):
    def parse(self, payload, info=None, key=PRIVATE):
        info = info or build()
        data = envelope(payload, key=key)
        return um.parse_manifest(um.verify_envelope(data, info.update_keys), info)

    def test_a_signed_manifest_is_read(self):
        parsed = self.parse(manifest())
        self.assertEqual(str(parsed.version), "1.0.1-test.1")
        self.assertEqual(parsed.text("changelog", "ru"), "Вымышленный список изменений.")
        self.assertEqual(parsed.text("changelog", "lv"), "Fictional change list.", "falls back to EN")

    def test_tampering_or_another_key_is_rejected(self):
        data = json.loads(envelope(manifest()))
        payload = bytearray(base64.b64decode(data["payload"]))
        payload[10] ^= 1
        data["payload"] = base64.b64encode(bytes(payload)).decode()
        for case, blob, keys in (
                ("tampered", json.dumps(data).encode(), (PUBLIC,)),
                ("other key", envelope(manifest(), key=OTHER_PRIVATE), (PUBLIC,)),
                ("no signature", json.dumps({**data, "signatures": []}).encode(), (PUBLIC,)),
                ("no trusted key", envelope(manifest()), ()),
                ("too large", b" " * (um.MAX_ENVELOPE_BYTES + 1), (PUBLIC,)),
                ("not json", b"<html>", (PUBLIC,))):
            with self.subTest(case=case), self.assertRaises(um.ManifestError) as caught:
                um.verify_envelope(blob, keys)
            self.assertIn(caught.exception.reason,
                          {"bad_signature", "unsigned", "no_keys", "malformed"})

    def test_app_channel_and_address_rules(self):
        cases = {
            "wrong_app": (manifest(app_id="{00000000-0000-0000-0000-000000000000}"), build()),
            "wrong_channel": (manifest(channel="preview", version="1.0.1-preview.1"), build()),
            "bad_url": (manifest(url="http://example.org/setup.exe"), build()),
        }
        stable = build("stable", "1.0.0")
        cases["stable gets no preview"] = (manifest(channel="preview", version="1.1.0-preview.1",
                                                    url="https://github.com/x/setup.exe"), stable)
        cases["stable is never a pre-release"] = (manifest(channel="stable", version="1.1.0-rc.1",
                                                           url="https://github.com/x/setup.exe"), stable)
        cases["https elsewhere"] = (manifest(channel="stable", version="1.1.0",
                                             url="https://example.org/setup.exe"), stable)
        cases["not an installer"] = (manifest(channel="stable", version="1.1.0",
                                              url="https://github.com/x/setup.zip"), stable)
        cases["bad checksum"] = (manifest(sha256="abc"), build())
        cases["implausible size"] = (manifest(size=10), build())
        for name, (payload, info) in cases.items():
            with self.subTest(case=name), self.assertRaises(um.ManifestError):
                self.parse(payload, info)

    def test_a_preview_build_also_accepts_a_stable_release(self):
        parsed = self.parse(manifest(channel="stable", version="1.1.0",
                                     url="https://github.com/adriano18/x/releases/download/v1.1.0/S.exe"),
                            build("preview", "1.1.0-preview.3"))
        self.assertEqual(parsed.channel, "stable")

    def test_no_downgrade_no_replay_and_signature_requirements(self):
        info = build(version="1.0.1-test.1")
        same = self.parse(manifest(), info)
        self.assertEqual(um.decide(same, info).state, "latest", "same version: nothing to do")
        older = self.parse(manifest(version="1.0.0-test.9"), info)
        self.assertEqual(um.decide(older, info).state, "latest", "an old manifest never downgrades")
        newer = self.parse(manifest(version="1.0.2-test.1", minimum_version="1.0.2-test.0"), info)
        self.assertEqual(um.decide(newer, info).reason, "too_old")
        strict = build(version="1.0.0-test.1", require_signature=True, publisher="CN=Fictional")
        unsigned = self.parse(manifest(), strict)
        self.assertEqual(um.decide(unsigned, strict).reason, "unsigned")
        other = self.parse(manifest(signed=True, publisher="CN=Someone else"), strict)
        self.assertEqual(um.decide(other, strict).reason, "wrong_publisher")
        good = self.parse(manifest(signed=True, publisher="CN=Fictional"), strict)
        self.assertEqual(um.decide(good, strict).state, "update")


class Server:
    """A local update server: manifest and installer, with faults on request."""

    def __init__(self):
        self.files, self.fault, self.requests = {}, None, []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.requests.append((self.path, self.headers.get("Range")))
                if owner.fault == "redirect" and self.path == "/setup.exe":
                    self.send_response(302)
                    self.send_header("Location", "http://localhost:%d/setup.exe" % owner.port)
                    self.end_headers()
                    return
                body = owner.files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                start = 0
                wanted = self.headers.get("Range")
                if wanted and owner.fault != "no-range":
                    start = int(wanted.split("=")[1].split("-")[0])
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                else:
                    self.send_response(200)
                part = body[start:]
                self.send_header("Content-Length", str(len(part)))
                self.end_headers()
                if owner.fault == "interrupt" and self.path == "/setup.exe":
                    self.wfile.write(part[:400_000])
                    self.wfile.flush()
                    owner.fault = None          # the next attempt succeeds
                    self.connection.shutdown(2)
                    return
                self.wfile.write(part)

        class Quiet(http.server.ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass        # the "interrupt" fault resets connections on purpose

        self.httpd = Quiet(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.server = Server()
        self.addCleanup(self.server.close)
        self.info = build(port=self.server.port)
        self.server.files["/manifest.json"] = envelope(manifest(), port=self.server.port)
        self.server.files["/setup.exe"] = INSTALLER
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.folder, True)

    def offer(self):
        return uc.check(self.info)

    def test_check_finds_the_newer_version(self):
        offer = self.offer()
        self.assertEqual((offer.state, str(offer.manifest.version)), ("update", "1.0.1-test.1"))

    def test_download_is_verified_and_reports_progress(self):
        seen = []
        path = uc.download(self.offer().manifest, self.folder, self.info,
                           progress=lambda done, total: seen.append(done))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), DIGEST)
        self.assertEqual(seen[-1], len(INSTALLER))
        self.assertEqual(path.name, "StatisticalResearchAssistant-1.0.1-test.1-Setup.exe")

    def test_an_interrupted_download_resumes_where_it_stopped(self):
        manifest_ = self.offer().manifest
        self.server.fault = "interrupt"
        with self.assertRaises(uc.UpdateError) as caught:
            uc.download(manifest_, self.folder, self.info)
        self.assertEqual(caught.exception.reason, "interrupted")
        self.assertFalse(uc.installer_path(self.folder, manifest_).exists(), "nothing to run yet")
        path = uc.download(manifest_, self.folder, self.info)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), DIGEST)
        self.assertEqual(self.server.requests[-1], ("/setup.exe", "bytes=400000-"))

    def test_a_damaged_download_is_deleted_and_never_offered_to_run(self):
        manifest_ = self.offer().manifest
        self.server.files["/setup.exe"] = INSTALLER[:-1] + bytes([INSTALLER[-1] ^ 1])
        with self.assertRaises(uc.UpdateError) as caught:
            uc.download(manifest_, self.folder, self.info)
        self.assertEqual(caught.exception.reason, "damaged")
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_more_bytes_than_announced_are_refused(self):
        manifest_ = self.offer().manifest
        self.server.files["/setup.exe"] = INSTALLER + b"extra"
        with self.assertRaises(uc.UpdateError) as caught:
            uc.download(manifest_, self.folder, self.info)
        self.assertEqual(caught.exception.reason, "damaged")

    def test_cancel_stops_the_download(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(uc.UpdateError) as caught:
            uc.download(self.offer().manifest, self.folder, self.info, cancel=cancel)
        self.assertEqual(caught.exception.reason, "cancelled")

    def test_a_redirect_to_another_host_is_refused(self):
        manifest_ = self.offer().manifest
        self.server.fault = "redirect"
        with self.assertRaises(uc.UpdateError) as caught:
            uc.download(manifest_, self.folder, self.info)
        self.assertEqual(caught.exception.reason, "bad_url")

    def test_offline_and_missing_files_are_reported_not_raised_further(self):
        self.server.files.pop("/manifest.json")
        with self.assertRaises(uc.UpdateError) as caught:
            self.offer()
        self.assertEqual(caught.exception.reason, "unavailable")
        self.server.close()
        with self.assertRaises(uc.UpdateError) as caught:
            uc.check(build(port=self.server.port))
        self.assertEqual(caught.exception.reason, "offline")
        self.server = Server()       # for cleanup

    def test_a_source_checkout_has_no_update_channel(self):
        with self.assertRaises(uc.UpdateError) as caught:
            uc.check(ai.BuildInfo())
        self.assertEqual(caught.exception.reason, "not_configured")

    def test_production_builds_only_talk_to_github_over_https(self):
        stable = ai.BuildInfo(version="1.0.0", channel="stable", update_keys=(PUBLIC,))
        self.assertTrue(uc.manifest_url(stable).startswith("https://github.com/"))
        for url in ("http://github.com/x", "https://evil.example/x", "http://127.0.0.1:1/x",
                    "https://github.com:8443/x"):
            with self.subTest(url=url):
                self.assertFalse(uc._allowed(url, stable))


class CodeSignatureTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.folder, True)
        self.path = self.folder / "setup.exe"
        self.path.write_bytes(INSTALLER)
        payload = json.dumps(manifest()).replace("{port}", "1").encode()
        self.manifest = um.parse_manifest(payload, build(port=1))

    def verify(self, status, subject="", thumbprint="", **build_args):
        info = build(port=1, **build_args)
        signature = {"status": status, "subject": subject, "thumbprint": thumbprint}
        with mock.patch.object(uc, "authenticode", return_value=signature):
            return uc.verify_installer(self.path, self.manifest, info)

    def test_unsigned_preview_builds_accept_unsigned_but_never_broken_signatures(self):
        self.assertEqual(self.verify("NotSigned")["status"], "NotSigned")
        for status in ("HashMismatch", "NotTrusted", "UnknownError"):
            with self.subTest(status=status), self.assertRaises(uc.UpdateError):
                self.verify(status)

    def test_signed_builds_accept_only_the_pinned_publisher(self):
        strict = {"require_signature": True, "publisher": "CN=Fictional Publisher",
                  "publisher_thumbprints": ("AB12",)}
        self.assertEqual(self.verify("Valid", "CN=Fictional Publisher", "AB12", **strict)["status"],
                         "Valid")
        for status, subject, thumb, reason in (
                ("NotSigned", "", "", "bad_code_signature"),
                ("Valid", "CN=Someone else", "AB12", "wrong_publisher"),
                ("Valid", "CN=Fictional Publisher", "FFFF", "wrong_publisher")):
            with self.subTest(status=status, subject=subject), \
                    self.assertRaises(uc.UpdateError) as caught:
                self.verify(status, subject, thumb, **strict)
            self.assertEqual(caught.exception.reason, reason)

    @unittest.skipUnless(sys.platform == "win32", "Windows' own WinVerifyTrust")
    def test_windows_verifies_signatures_itself(self):
        """Run on Windows CI: an unsigned file is NotSigned, a signed system
        program is Valid, without PowerShell for the status."""
        self.assertEqual(uc._win_verify_trust(self.path), "NotSigned")
        notepad = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "notepad.exe"
        if notepad.is_file():
            self.assertIn(uc._win_verify_trust(notepad), ("Valid", "NotSigned"))

    def test_the_checksum_is_checked_again_before_starting(self):
        self.path.write_bytes(b"x" + INSTALLER[1:])
        with self.assertRaises(uc.UpdateError) as caught:
            self.verify("NotSigned")
        self.assertEqual(caught.exception.reason, "damaged")


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        store = ps.ProjectStore(self.root / "projects")
        self.projects = [store.create(f"Fictional study {n}").id for n in (1, 2)]
        payload = json.dumps(manifest()).replace("{port}", "1").encode()
        self.manifest = um.parse_manifest(payload, build(port=1))
        self.installer = self.root / "updates" / "StatisticalResearchAssistant-1.0.1-test.1-Setup.exe"
        self.installer.parent.mkdir(parents=True)
        self.installer.write_bytes(INSTALLER)

    def test_prepare_backs_up_every_project_database_and_records_the_update(self):
        record = uc.prepare(self.root, self.installer, self.manifest, build(port=1))
        backup = Path(record["backup"])
        self.assertEqual(sorted(p.stem for p in backup.glob("*.sqlite3")), sorted(self.projects))
        pending = json.loads((self.root / "updates" / uc.PENDING).read_text(encoding="utf-8"))
        self.assertEqual((pending["from"], pending["to"]), ("1.0.0-test.1", "1.0.1-test.1"))
        self.assertEqual(sorted(pending["projects"]), sorted(self.projects))
        self.assertEqual(pending["changelog"]["en"], "Fictional change list.")

    def test_the_next_start_confirms_the_new_version_and_every_project(self):
        uc.prepare(self.root, self.installer, self.manifest, build(port=1))
        outcome = uc.finish(self.root, build(version="1.0.1-test.1", port=1))
        self.assertEqual((outcome["state"], outcome["projects_kept"], outcome["missing_projects"]),
                         ("updated", 2, []))
        self.assertFalse(self.installer.exists(), "the downloaded installer is removed")
        self.assertFalse((self.root / "updates" / uc.PENDING).exists())
        self.assertIsNone(uc.finish(self.root, build(version="1.0.1-test.1", port=1)))
        history = json.loads((self.root / "updates" / uc.HISTORY).read_text(encoding="utf-8"))
        self.assertEqual(history["updates"][-1]["state"], "updated")

    def test_an_installer_still_running_does_not_hide_the_outcome(self):
        """On Windows the installer that started the new version may still be
        running, so its file cannot be deleted yet: the outcome is reported
        anyway and the file is removed on a later start."""
        uc.prepare(self.root, self.installer, self.manifest, build(port=1))
        real_unlink = Path.unlink

        def locked(path, *args, **kwargs):
            if path.suffix == ".exe":
                raise PermissionError(32, "The process cannot access the file")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", locked):
            outcome = uc.finish(self.root, build(version="1.0.1-test.1", port=1))
        self.assertEqual(outcome["state"], "updated")
        self.assertTrue(self.installer.exists())
        self.assertEqual(uc.clean_cache(self.root), [self.installer.name])
        self.assertFalse(self.installer.exists())

    def test_an_update_that_did_not_happen_is_reported_and_nothing_is_lost(self):
        uc.prepare(self.root, self.installer, self.manifest, build(port=1))
        outcome = uc.finish(self.root, build(version="1.0.0-test.1", port=1))
        self.assertEqual(outcome["state"], "not_installed")
        self.assertTrue(self.installer.exists(), "kept for a retry")

    def test_a_missing_project_is_named_with_the_backup(self):
        uc.prepare(self.root, self.installer, self.manifest, build(port=1))
        gone = self.root / "projects" / self.projects[0]
        __import__("shutil").rmtree(gone)
        outcome = uc.finish(self.root, build(version="1.0.1-test.1", port=1))
        self.assertEqual(outcome["missing_projects"], [self.projects[0]])
        self.assertTrue((Path(outcome["backup"]) / f"{self.projects[0]}.sqlite3").is_file())

    def test_the_installer_does_not_inherit_this_runtime(self):
        """Found by the A -> B journey: the restarted version stayed on its
        boot screen because it inherited this process's Flet bridge ports."""
        record = uc.prepare(self.root, self.installer, self.manifest, build(port=1))
        inherited = {"FLET_DART_BRIDGE_PORT": "4242", "FLET_APP_STORAGE_DATA": "x",
                     "PYTHONHOME": "y", "SERIOUS_PYTHON_SITE_PACKAGES": "z",
                     "PATH": "C:\\Windows", "SRA_UI": "workspace", "TEMP": "t"}
        with mock.patch.dict(os.environ, inherited), \
                mock.patch.object(uc.subprocess, "Popen") as popen:
            uc.launch_installer(record)
        environment = popen.call_args.kwargs["env"]
        self.assertFalse([k for k in environment if k.upper().startswith(("FLET_", "SERIOUS_PYTHON"))])
        self.assertNotIn("PYTHONHOME", environment)
        self.assertEqual((environment["PATH"], environment["SRA_UI"]), ("C:\\Windows", "workspace"))
        self.assertIn("/UPDATEFROMAPP", popen.call_args.args[0])

    def test_only_the_last_update_backups_are_kept(self):
        for n in range(uc.KEEP_UPDATE_BACKUPS + 2):
            folder = uc.backup_before_update(self.root, f"label-{n}")
            os.utime(folder, (1_000_000 + n, 1_000_000 + n))
        left = sorted(p.name for p in (self.root / "projects" / ".backups").glob("update-*"))
        self.assertEqual(len(left), uc.KEEP_UPDATE_BACKUPS)

    def test_automatic_checks_at_most_daily_and_later_snoozes_that_version(self):
        self.assertTrue(uc.due(self.root))
        uc.remember_check(self.root, None)
        self.assertFalse(uc.due(self.root))
        state = uc.state(self.root)
        state["automatic"] = False
        uc.save_state(self.root, state)
        self.assertFalse(uc.due(self.root))
        uc.snooze(self.root, "1.0.1")
        self.assertTrue(uc.snoozed(self.root, "1.0.1"))
        self.assertFalse(uc.snoozed(self.root, "1.0.2"))


class FakePage:
    def __init__(self):
        self.dialogs, self.tasks, self.urls = [], [], []

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def update(self, *controls):
        pass

    def run_task(self, handler, *args):
        self.tasks.append((handler, args))

    def launch_url(self, url):
        self.urls.append(url)


def texts(control) -> str:
    found = []

    def walk(node):
        if isinstance(node, ft.Text) and isinstance(node.value, str):
            found.append(node.value)
        for name in ("content", "controls", "title", "actions"):
            child = getattr(node, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control) and (not hasattr(item, "visible") or item.visible is not False):
                    walk(item)
    walk(control)
    return " ".join(found)


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.server = Server()
        self.addCleanup(self.server.close)
        self.server.files["/manifest.json"] = envelope(manifest(), port=self.server.port)
        self.server.files["/setup.exe"] = INSTALLER
        self.info = build(port=self.server.port)
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.data, True)
        patcher = mock.patch.dict(os.environ, {"SRA_DATA_DIR": str(self.data)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def dialog(self, language="en"):
        page = FakePage()
        dialog = update_ui.UpdateDialog(page, ROOT, language, build=self.info)
        page.show_dialog(dialog.dialog)
        return page, dialog

    def test_every_language_has_every_text(self):
        for language in ("lv", "ru"):
            with self.subTest(language=language):
                self.assertEqual(set(update_ui.TEXT[language]), set(update_ui.TEXT["en"]))

    def test_a_newer_version_is_offered_with_what_is_new(self):
        page, dialog = self.dialog()
        asyncio.run(dialog.check())
        shown = texts(dialog.dialog)
        self.assertIn("A new version is available — 1.0.1-test.1", shown)
        self.assertIn("Fictional change list.", shown)
        self.assertEqual([a.data for a in dialog.dialog.actions],
                         ["update-later", "update-notes", "update-now"])

    def test_a_rejected_manifest_is_explained_in_words(self):
        self.server.files["/manifest.json"] = envelope(manifest(), key=OTHER_PRIVATE,
                                                       port=self.server.port)
        page, dialog = self.dialog("ru")
        asyncio.run(dialog.check())
        self.assertIn("подписаны не издателем этого приложения", texts(dialog.dialog))

    def test_update_now_downloads_verifies_backs_up_and_starts_the_installer(self):
        page, dialog = self.dialog()
        asyncio.run(dialog.check())
        launched = []
        with mock.patch.object(uc, "authenticode", return_value={"status": "NotSigned"}), \
                mock.patch.object(uc, "launch_installer", side_effect=launched.append), \
                mock.patch.object(update_ui, "close_application", new=mock.AsyncMock()) as closing:
            asyncio.run(dialog.update_now())
        self.assertEqual(len(launched), 1)
        self.assertTrue(Path(launched[0]["installer"]).is_file())
        closing.assert_awaited_once()
        self.assertIn("Installing version 1.0.1-test.1", texts(dialog.dialog))

    def test_a_damaged_download_keeps_the_application_running(self):
        page, dialog = self.dialog()
        asyncio.run(dialog.check())
        self.server.files["/setup.exe"] = b"y" * len(INSTALLER)
        with mock.patch.object(uc, "launch_installer") as launch, \
                mock.patch.object(update_ui, "close_application", new=mock.AsyncMock()) as closing:
            asyncio.run(dialog.update_now())
        launch.assert_not_called()
        closing.assert_not_awaited()
        self.assertIn("does not match the published checksum", texts(dialog.dialog))

    def test_open_projects_are_closed_before_the_handoff(self):
        closed = []

        class Shell:
            def close_project_for_update(self):
                closed.append(True)

        shell = Shell()
        update_ui.register_before_exit(shell.close_project_for_update)
        update_ui.run_before_exit()
        self.assertEqual(closed, [True])
        del shell                       # a closed workspace is not kept alive
        __import__("gc").collect()
        update_ui.run_before_exit()
        self.assertEqual(closed, [True])

    def test_an_unexpected_failure_never_leaves_the_dialog_waiting(self):
        page, dialog = self.dialog()
        asyncio.run(dialog.check())
        with mock.patch.object(uc, "verify_installer", side_effect=RuntimeError("unexpected")), \
                mock.patch.object(uc, "launch_installer") as launch:
            asyncio.run(dialog.update_now())
        launch.assert_not_called()
        self.assertIn("could not be completed. Nothing was changed.", texts(dialog.dialog))
        self.assertEqual([a.data for a in dialog.dialog.actions][-1], "update-now", "it can be retried")

    def test_after_the_restart_the_outcome_is_shown(self):
        installer = self.data / "updates" / "StatisticalResearchAssistant-1.0.1-test.1-Setup.exe"
        installer.parent.mkdir(parents=True)
        installer.write_bytes(INSTALLER)
        ps.ProjectStore(self.data / "projects").create("Fictional study")
        payload = json.dumps(manifest()).replace("{port}", "1").encode()
        uc.prepare(self.data, installer, um.parse_manifest(payload, build(port=1)), self.info)
        page = FakePage()
        with mock.patch.object(ai, "build_info", return_value=build(version="1.0.1-test.1")), \
                mock.patch.object(update_ui, "show_in_front", return_value=True) as front:
            shown = asyncio.run(update_ui.after_start(page, ROOT, "en"))
        self.assertEqual(shown, "outcome")
        front.assert_called_once()          # the installer started it: above other windows
        text = texts(page.dialogs[0])
        self.assertIn("Updated to version 1.0.1-test.1", text)
        self.assertIn("Your projects and research data are preserved.", text)
        self.assertIn("All 1 projects are in place.", text)


class ShowInFrontTests(unittest.TestCase):
    """After an update the new window is raised above other programs' windows."""

    @unittest.skipIf(os.name == "nt", "the Windows behaviour is tested below")
    def test_elsewhere_nothing_is_done(self):
        self.assertFalse(update_ui.show_in_front())

    @unittest.skipUnless(os.name == "nt", "Windows window manager")
    def test_without_a_window_of_this_program_nothing_fails(self):
        self.assertFalse(update_ui.show_in_front(window_class="NoSuchWindowClass", attempts=1))

    @unittest.skipUnless(os.name == "nt", "Windows window manager")
    def test_the_window_is_raised_and_never_left_always_on_top(self):
        import ctypes
        from ctypes import wintypes

        try:
            import tkinter

            root = tkinter.Tk()
        except Exception as error:          # no Tk or no desktop here
            self.skipTest(f"no Tk window: {error}")
        try:
            root.title("Fictional window")
            root.geometry("320x200+140+140")
            root.update()
            frame = int(root.wm_frame(), 16)
            user32 = ctypes.WinDLL("user32")
            user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.WindowFromPoint.argtypes = [wintypes.POINT]
            user32.WindowFromPoint.restype = wintypes.HWND
            user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            user32.GetAncestor.restype = wintypes.HWND
            name = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(frame, name, 128)
            update_ui.show_in_front(window_class=name.value, attempts=3, pause=0.2)
            root.update()
            topmost = user32.GetWindowLongW(frame, -20) & 0x0008      # GWL_EXSTYLE, WS_EX_TOPMOST
            self.assertFalse(topmost, "the window was left always on top")
            x = root.winfo_rootx() + root.winfo_width() // 2
            y = root.winfo_rooty() + root.winfo_height() // 2
            reached = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(x, y)), 2)  # GA_ROOT
            self.assertEqual(reached, frame, "a click on the window would reach another window")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
