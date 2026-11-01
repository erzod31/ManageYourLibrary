import hashlib
import io
import json
import os
import plistlib
import stat
import tarfile
import tempfile
import threading
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from core.app_updates import (APP_ID, DEFAULT_REPOSITORY, MAC_BUNDLE_ID, PRODUCT, UpdateCancelled,
    UpdateChannel, UpdateError, UpdateOffer, sha256, trusted_url, version_tuple)
from core.update_apply import (UpdateCoordinator, apply_posix_plan, extract_archive, protect_install_root,
    validate_plan, verify_windows)


class Response(io.BytesIO):
    def __init__(self, raw, headers=None):
        super().__init__(raw)
        self.headers = headers or {}


def offer(target="windows-portable-x64", data=b"fixture", version="2.3.5"):
    names = {"windows-portable-x64": f"ManageYourLibrary-{version}-Windows-x64-portable.zip",
             "windows-installer-x64": f"ManageYourLibrary-{version}-Setup-x64.exe",
             "linux-x64": f"ManageYourLibrary-{version}-Linux-x64.tar.gz",
             "macos-arm64": f"ManageYourLibrary-{version}-macOS-arm64.zip",
             "macos-x64": f"ManageYourLibrary-{version}-macOS-x64.zip"}
    name = names[target]
    return UpdateOffer(PRODUCT, version, target, name,
        f"https://github.com/{DEFAULT_REPOSITORY}/releases/download/v{version}/{name}",
        len(data), hashlib.sha256(data).hexdigest(), DEFAULT_REPOSITORY, "v"+version)


def release(value, **extra):
    return {"tag_name": value.tag, "draft": False, "prerelease": False,
        "published_at": "2026-10-28T10:00:00Z", "assets": [{"name": value.name, "state": "uploaded",
        "size": value.size, "digest": "sha256:"+value.sha256, "browser_download_url": value.url}], **extra}


class ChannelTests(unittest.TestCase):
    def test_windows_signature_verifier_uses_system_modules_and_fails_closed(self):
        from core.update_apply import windows_file_info, windows_powershell
        result = Mock(returncode=0, stdout='{"product":"Manage Your Library","version":"2.3.5","status":"NotSigned","signer":""}')
        with patch.dict(os.environ, {"PSModulePath": "incompatible-user-modules"}), patch("core.update_apply.subprocess.run", return_value=result) as native:
            self.assertEqual(windows_file_info("synthetic.exe")["status"], "NotSigned")
            self.assertEqual(native.call_args.kwargs["env"]["PSModulePath"], str(Path(windows_powershell()).parent / "Modules"))
            self.assertIn("$ErrorActionPreference='Stop'", native.call_args.args[0][-1])
        with patch("core.update_apply.subprocess.run", return_value=Mock(returncode=1)):
            with self.assertRaises(UpdateError):
                windows_file_info("synthetic.exe")

    def check(self, data, current="2.3.4", target="windows-portable-x64"):
        return UpdateChannel(opener=lambda _: Response(json.dumps(data).encode())).check(current, target)

    def test_current_available_and_native_supplement_selection(self):
        value = offer()
        self.assertEqual(self.check([release(value)])["offer"], value)
        self.assertEqual(self.check([release(value)], current="2.3.5")["status"], "up_to_date")
        self.assertEqual(self.check([release(value)], current="9.0.0")["status"], "up_to_date")
        native = offer("linux-x64")
        native = replace(native, tag="v2.3.5-native.2", url=native.url.replace("/v2.3.5/", "/v2.3.5-native.2/"))
        self.assertEqual(self.check([release(native)], target="linux-x64")["offer"], native)

    def test_draft_prerelease_wrong_platform_and_missing_package(self):
        value = offer()
        for item in (release(value, draft=True), release(value, prerelease=True), release(offer("linux-x64"))):
            self.assertEqual(self.check([item])["status"], "no_package")

    def test_malformed_metadata_missing_hash_and_wrong_origin_fail(self):
        value = offer()
        for fields in ({"digest": None}, {"size": True}, {"digest": "sha256:"+"z"*64},
                       {"browser_download_url": "https://evil.example/ManageYourLibrary.zip"}, {"size": -1}):
            data = release(value)
            data["assets"][0].update(fields)
            with self.subTest(fields=fields), self.assertRaises(UpdateError):
                self.check([data])
        with self.assertRaises(UpdateError):
            self.check({"message": "Rate limited"})

    def test_wrong_product_platform_version_and_downgrade_are_rejected(self):
        value = offer()
        for changed in (replace(value, product="Other"), replace(value, platform="linux-x64"),
                        replace(value, name=value.name.replace("2.3.5", "2.3.9")), replace(value, tag="v9.0.0")):
            with self.subTest(changed=changed), self.assertRaises(UpdateError):
                changed.validate("2.3.4", "windows-portable-x64")
        for current in ("2.3.5", "2.3.6"):
            with self.assertRaises(UpdateError):
                value.validate(current, value.platform)
        for invalid in ("v1.2.3", "01.2.3", "1.2", "1.2.3-beta", "../1.2.3"):
            with self.assertRaises(UpdateError):
                version_tuple(invalid)

    def test_redirects_never_accept_http_external_hosts_credentials_or_fragments(self):
        for url in ("http://github.com/a/b", "https://github.com.evil.example/a", "https://user:secret@github.com/a",
                    "https://github.com:8080/a", "file:///tmp/a", "https://github.com/a#fragment"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                trusted_url(url)
        self.assertEqual(trusted_url("https://release-assets.githubusercontent.com/file?token=redacted"), "https://release-assets.githubusercontent.com/file?token=redacted")

    def test_download_validates_size_hash_and_no_requests_when_cancelled(self):
        data = b"binary fixture" * 10000
        value = offer(data=data)
        with tempfile.TemporaryDirectory() as temp:
            for raw, length in ((data+b"extra", len(data)+5), (data[:-1], len(data)), (b"x"*len(data), len(data))):
                with self.subTest(length=length), self.assertRaises(UpdateError):
                    UpdateChannel(opener=lambda _, r=raw, n=length: Response(r, {"Content-Length": str(n)})).download(value, "2.3.4", value.platform, temp)
                self.assertFalse(list(Path(temp).glob("*.part")))
                self.assertFalse((Path(temp)/value.name).exists())
            event = threading.Event(); event.set()
            opener = Mock(return_value=Response(data))
            with self.assertRaises(UpdateCancelled):
                UpdateChannel(opener=opener).download(value, "2.3.4", value.platform, temp, cancelled=event)
            opener.assert_not_called()
            result = UpdateChannel(opener=lambda _: Response(data)).download(value, "2.3.4", value.platform, temp)
            self.assertEqual(result.read_bytes(), data)
            self.assertEqual(sha256(result), value.sha256)

    def test_network_failure_does_not_create_valid_package(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(OSError):
                UpdateChannel(opener=Mock(side_effect=OSError("offline"))).download(offer(), "2.3.4", "windows-portable-x64", temp)
            self.assertFalse(list(Path(temp).glob("*.part")))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.library = self.root / "books"
        self.library.mkdir()
        (self.library / "original.epub").write_bytes(b"protected book")
        self.install = self.root / "Custom app folder"
        (self.install / "_internal").mkdir(parents=True)
        (self.install / "_internal/VERSION").write_text("2.3.4")
        (self.install / "ManageYourLibrary").write_bytes(b"old binary stub")
        (self.install / "ManageYourLibrary.exe").write_bytes(b"old PE stub")
        self.launcher = Mock(return_value=Mock(pid=12345))

    def tearDown(self):
        self.assertEqual((self.library / "original.epub").read_bytes(), b"protected book")
        self.temp.cleanup()

    def coordinator(self, target):
        def inspect(path):
            old = Path(path).parent == self.install
            return {"product": "Manage Your Library", "version": "2.3.4" if old else "2.3.5", "status": "NotSigned", "signer": ""}
        return UpdateCoordinator(self.profile / "updates", "2.3.4", target, self.install,
            protected=[self.profile, self.library], native_inspect=inspect, launcher=self.launcher)

    def package(self, target="windows-portable-x64", *, identity_changes=None):
        manager = self.coordinator(target)
        session = manager.new_session()
        value = offer(target)
        path = session / value.name
        identity = {"product": PRODUCT, "version": value.version, "platform": target, "appId": APP_ID, "macBundleId": MAC_BUNDLE_ID}
        identity.update(identity_changes or {})
        files = {"ManageYourLibrary/_internal/update-identity.json": json.dumps(identity).encode(),
                 "ManageYourLibrary/_internal/VERSION": value.version.encode(),
                 "ManageYourLibrary/"+("ManageYourLibrary.exe" if target.startswith("windows") else "ManageYourLibrary"): b"new binary stub"}
        if target.startswith("macos"):
            files = {"ManageYourLibrary.app/Contents/Frameworks/update-identity.json": json.dumps(identity).encode(),
                     "ManageYourLibrary.app/Contents/Frameworks/VERSION": value.version.encode(),
                     "ManageYourLibrary.app/Contents/MacOS/ManageYourLibrary": b"MachO stub, never executable",
                     "ManageYourLibrary.app/Contents/Info.plist": plistlib.dumps({"CFBundleIdentifier": MAC_BUNDLE_ID,
                         "CFBundleExecutable": "ManageYourLibrary", "CFBundleShortVersionString": value.version})}
            manager.mac_verify = Mock(return_value={"kind":"codesign-and-gatekeeper","status":"Valid","team":"test-fixture"})
        if target == "linux-x64":
            with tarfile.open(path, "w:gz") as archive:
                for name, content in files.items():
                    info = tarfile.TarInfo(name); info.size = len(content); info.mode = 0o755
                    archive.addfile(info, io.BytesIO(content))
        else:
            with zipfile.ZipFile(path, "w") as archive:
                for name, content in files.items():
                    archive.writestr(name, content)
        value = replace(value, size=path.stat().st_size, sha256=sha256(path))
        return manager, value, path

    def test_staging_and_fake_native_handoff_do_not_modify_installed_app_or_books(self):
        manager, value, path = self.package()
        plan = manager.prepare(value, path)
        with self.assertRaises(UpdateError):
            manager.handoff(plan)
        self.launcher.assert_not_called()
        result = manager.handoff(plan, confirmed=True)
        self.assertEqual(Path(result["arguments"][0]).name, "powershell.exe")
        self.assertNotIn("-ExecutionPolicy", result["arguments"])
        self.assertEqual((self.install/"ManageYourLibrary.exe").read_bytes(), b"old PE stub")
        self.launcher.assert_called_once()

    def test_blocked_helper_keeps_application_and_recoverable_failed_plan(self):
        manager, value, package = self.package()
        plan = manager.prepare(value, package)
        manager.real_launcher = True  # Exercise readiness with only a fake process.
        self.launcher.return_value.poll.return_value = 1
        with self.assertRaises(UpdateError):
            manager.handoff(plan, confirmed=True)
        self.assertEqual(json.loads(plan.read_text())["state"], "handoff_failed")
        self.assertEqual((self.install / "ManageYourLibrary.exe").read_bytes(), b"old PE stub")

    def test_wrong_identity_and_tampered_download_or_stage_fail_before_launcher(self):
        for identity in ({"product": "Other"}, {"version": "9.0.0"}, {"platform": "macos-x64"}, {"appId": "Other"}):
            manager, value, path = self.package(identity_changes=identity)
            with self.assertRaises(UpdateError):
                manager.prepare(value, path)
        manager, value, path = self.package()
        plan = manager.prepare(value, path)
        loaded = json.loads(plan.read_text())
        (Path(loaded["stagedRoot"])/"ManageYourLibrary.exe").write_bytes(b"changed")
        with self.assertRaises(UpdateError):
            manager.handoff(plan, confirmed=True)
        self.launcher.assert_not_called()

    def test_native_installer_arguments_are_recorded_with_fake_launcher(self):
        manager = self.coordinator("windows-installer-x64")
        data = b"MZ fixture, never executable"
        value = offer("windows-installer-x64", data=data)
        path = manager.new_session() / value.name; path.write_bytes(data)
        plan = manager.prepare(value, path)
        result = manager.handoff(plan, confirmed=True)
        self.assertEqual(result["arguments"], [str(path), "/DIR="+str(self.install.resolve()), "/RESTARTAPPLICATIONS"])
        self.assertNotIn("/SILENT", result["arguments"])
        self.launcher.assert_called_once()

    def test_cancel_before_handoff_and_launcher_failure_preserve_state(self):
        manager, value, path = self.package()
        plan = manager.prepare(value, path)
        event = threading.Event(); event.set()
        with self.assertRaises(UpdateCancelled):
            manager.handoff(plan, confirmed=True, cancelled=event)
        self.launcher.assert_not_called()
        self.launcher.side_effect = OSError("launcher failed")
        with self.assertRaises(OSError):
            manager.handoff(plan, confirmed=True)
        self.assertEqual(json.loads(plan.read_text())["state"], "handoff_failed")

    def test_changed_installation_and_protected_root_block_deployment(self):
        manager, value, path = self.package()
        plan = manager.prepare(value, path)
        (self.install/"_internal/VERSION").write_text("2.3.9")
        with self.assertRaises(UpdateError):
            validate_plan(plan, manager.state)
        for root in (self.library, self.profile, self.library / "nested"):
            with self.assertRaises(UpdateError):
                protect_install_root(root, [self.library, self.profile])

    def test_macos_native_gate_and_fake_restart_handoff(self):
        manager, value, path = self.package("macos-arm64")
        plan = manager.prepare(value, path)
        manager.mac_verify.assert_called_once()
        result = manager.handoff(plan, confirmed=True)
        self.assertEqual(result["arguments"][1], "--apply-update")
        self.launcher.assert_called_once()
        manager2, value2, path2 = self.package("macos-x64")
        manager2.mac_verify.side_effect = UpdateError("Gatekeeper requires an approved developer/notarization")
        with self.assertRaises(UpdateError):
            manager2.prepare(value2, path2)

    @unittest.skipIf(os.name == "nt", "POSIX swap runs only on isolated POSIX fixtures; Windows uses fake launchers")
    def test_posix_swap_and_restart_use_fake_executable_and_keep_rollback(self):
        manager, value, path = self.package("linux-x64")
        plan = manager.prepare(value, path)
        manager.handoff(plan, confirmed=True)
        completed = apply_posix_plan(plan, manager.state, launcher=self.launcher, wait_parent=False)
        self.assertEqual(completed["state"], "completed")
        self.assertEqual((self.install / "ManageYourLibrary").read_bytes(), b"new binary stub")
        self.assertEqual((Path(completed["rollbackRoot"])/"ManageYourLibrary").read_bytes(), b"old binary stub")

    @unittest.skipIf(os.name == "nt", "POSIX fixture only; no actual Windows updater execution")
    def test_posix_restart_failure_restores_old_stub_and_records_failure(self):
        manager, value, path = self.package("linux-x64")
        plan = manager.prepare(value, path); manager.handoff(plan, confirmed=True)
        with self.assertRaises(OSError):
            apply_posix_plan(plan, manager.state, launcher=Mock(side_effect=OSError("restart rejected")), wait_parent=False)
        self.assertEqual((self.install/"ManageYourLibrary").read_bytes(), b"old binary stub")
        self.assertEqual(json.loads(plan.read_text())["state"], "rolled_back")


class ArchiveSignatureTests(unittest.TestCase):
    def test_inno_padded_version_resources_are_trimmed_without_weakening_identity(self):
        inspect = lambda _: {"product": "Manage Your Library        ", "version": "2.3.5       ", "status": "NotSigned"}
        self.assertEqual(verify_windows("synthetic.exe", "2.3.5", inspect=inspect)["status"], "NotSigned")
        with self.assertRaises(UpdateError):
            verify_windows("synthetic.exe", "2.3.4", inspect=inspect)

    def test_zip_traversal_and_external_symlink_rejected(self):
        for name, link in (("../outside", None), ("App/evil", "../../outside")):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); archive = root/"archive.zip"
                with zipfile.ZipFile(archive, "w") as target:
                    info = zipfile.ZipInfo(name)
                    if link:
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    target.writestr(info, link or b"bad")
                with self.assertRaises(UpdateError):
                    extract_archive(archive, root/"stage")
                self.assertFalse((root.parent/"outside").exists())

    def test_tar_hardlinks_and_devices_rejected(self):
        for kind in (tarfile.LNKTYPE, tarfile.CHRTYPE):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp); archive=root/"archive.tar.gz"
                with tarfile.open(archive,"w:gz") as target:
                    item=tarfile.TarInfo("App/unsafe"); item.type=kind;item.linkname="outside";target.addfile(item)
                with self.assertRaises(UpdateError):
                    extract_archive(archive,root/"stage")

    def test_invalid_signature_and_signed_publisher_change_rejected(self):
        for status in ("HashMismatch", "NotTrusted", "UnknownError"):
            with self.assertRaises(UpdateError):
                verify_windows("new.exe", "2.3.5", inspect=lambda _: {"product":"Manage Your Library","version":"2.3.5","status":status})
        inspect = Mock(side_effect=[{"product":"Manage Your Library","version":"2.3.5","status":"NotSigned"},
                                   {"product":"Manage Your Library","version":"2.3.4","status":"Valid","signer":"old"}])
        with self.assertRaises(UpdateError):
            verify_windows("new.exe","2.3.5",installed="old.exe",inspect=inspect)

    def test_macos_verification_keeps_gatekeeper_and_signer_checks(self):
        from core.update_apply import verify_mac
        result=Mock(returncode=0,stderr="TeamIdentifier=EXPECTED\n")
        native=Mock()
        with patch("core.update_apply.subprocess.run",return_value=result):
            self.assertEqual(verify_mac("new.app","old.app",run=native)["team"],"EXPECTED")
        self.assertEqual(native.call_args_list[-1].args[0][:3], ["/usr/sbin/spctl", "--assess", "--type"])
        with patch("core.update_apply.subprocess.run",side_effect=[result,Mock(returncode=0,stderr="TeamIdentifier=OTHER\n")]):
            with self.assertRaises(UpdateError):
                verify_mac("new.app","old.app",run=Mock())


if __name__ == "__main__":
    unittest.main()
