"""Exercise the private companion protocol and recoverable desktop workflows."""
import hashlib
import http.client
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import library_core as core
from core.mobile_access import ApiError, DeviceAccess, FileReply, MobileHttpServer, MobileService
from core.mobile_library import DesktopLibraryAdapter, MobileJobs
from core.mobile_tailscale import TailscaleAccess


class DeviceAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "devices.json"
        self.now = 1000
        self.access = DeviceAccess(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.temp.cleanup()

    def test_pairing_is_single_use_and_persists_only_hash(self):
        code = self.access.new_code()
        paired = self.access.pair(code, "Teléfono de prueba")
        self.assertEqual(self.access.authenticate("Bearer " + paired["token"]), paired["device_id"])
        contents = self.path.read_text(encoding="utf-8")
        self.assertNotIn(paired["token"].split(".")[1], contents)
        self.assertNotIn(code, contents)
        with self.assertRaises(ApiError):
            self.access.pair(code, "Otro")
        self.assertEqual(DeviceAccess(self.path).authenticate("Bearer " + paired["token"]), paired["device_id"])

    def test_expiry_rate_limit_and_revocation(self):
        code = self.access.new_code()
        self.now += 121
        for _ in range(5):
            with self.assertRaises(ApiError) as error:
                self.access.pair(code, "Android")
            self.assertEqual(error.exception.status, 401)
        with self.assertRaises(ApiError) as error:
            self.access.pair(code, "Android")
        self.assertEqual(error.exception.status, 429)
        paired = self.access.pair(self.access.new_code(), "Android")
        self.access.revoke(paired["device_id"])
        with self.assertRaises(ApiError):
            self.access.authenticate("Bearer " + paired["token"])

    def test_corrupt_store_is_preserved_and_refused(self):
        for raw in ('{broken', '{"devices":{"bad":null}}'):
            self.path.write_text(raw, encoding="utf-8")
            with self.assertRaises(RuntimeError):
                DeviceAccess(self.path)
            self.assertEqual(self.path.read_text(encoding="utf-8"), raw)


class MobileHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.access = DeviceAccess(root / "devices.json")
        self.paired = self.access.pair(self.access.new_code(), "QA")
        self.adapter = Mock()
        self.adapter.dispatch.return_value = {"ok": True}
        apk = root / "client.apk"
        apk.write_bytes(b"synthetic APK")
        self.adapter.android_apk.return_value = FileReply(apk)
        self.service = MobileService(self.access, self.adapter)
        self.port = self.service.start()

    def tearDown(self):
        self.service.stop()
        self.temp.cleanup()

    def request(self, path, body=None, *, auth=True, extra=None, method=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Authorization": "Bearer " + self.paired["token"]} if auth else {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra or {})
        try:
            connection.request(method or ("POST" if body is not None else "GET"), path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_every_catalog_route_requires_authentication(self):
        for path in ("/api/v1/status", "/api/v1/books", "/api/v1/books/xxx/file", "/api/v1/jobs", "/api/v1/plans",
                     "/api/v1/android-update", "/api/v1/android-update/file"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, auth=False)[0], 401)
        self.adapter.dispatch.assert_not_called()

    def test_health_and_apk_bootstrap_contain_no_catalog_or_credential(self):
        self.assertEqual(json.loads(self.request("/api/v1/health", auth=False)[1])["protocol"], 1)
        status, raw, headers = self.request("/api/v1/client.apk", auth=False)
        self.assertEqual((status, raw), (200, b"synthetic APK"))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.adapter.dispatch.assert_not_called()

    def test_browser_origin_and_malformed_or_oversize_json_are_rejected(self):
        self.assertEqual(self.request("/api/v1/status", extra={"Origin": "https://example.test"})[0], 403)
        for raw in ('[]', '{"a":NaN}', '{'):
            self.assertIn(self.request("/api/v1/anything", raw)[0], {400, 413})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.putrequest("POST", "/api/v1/pair")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", "65537")
        connection.endheaders()
        self.assertEqual(connection.getresponse().status, 413)
        connection.close()
        self.adapter.dispatch.assert_not_called()

    def test_duplicate_content_length_and_transfer_encoding_are_rejected(self):
        for headers in (("Content-Length", "1", "Content-Length", "2"),
                        ("Content-Length", "2", "Transfer-Encoding", "chunked")):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
            connection.putrequest("POST", "/api/v1/pair")
            connection.putheader("Content-Type", "application/json")
            for position in range(0, len(headers), 2):
                connection.putheader(headers[position], headers[position + 1])
            connection.endheaders(b"{}")
            self.assertIn(connection.getresponse().status, {400, 411})
            connection.close()

    def test_authenticated_native_request_and_self_revocation(self):
        self.assertEqual(self.request("/api/v1/status")[0], 200)
        self.assertEqual(self.request("/api/v1/unpair", "{}")[0], 200)
        self.assertEqual(self.request("/api/v1/status")[0], 401)
        self.adapter.jobs.cancel_owner.assert_called_once_with(self.paired["device_id"])

    def test_server_cannot_bind_lan_or_public_interface(self):
        with self.assertRaises(ValueError):
            MobileHttpServer(("0.0.0.0", 0), self.access, self.adapter)


class MobileLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = self.root / "library"
        self.library.mkdir()
        state = self.root / "state"
        paths = {"FINAL": self.library, "APP_DATA": state}
        paths.update({key: state / name for key, name in {
            "CONFIG_JSON": "config.json", "INDICE_JSON": "index.json", "HISTORIAL_CSV": "history.csv",
            "UNDO_JSONL": "undo.jsonl", "FILE_TRANSACTION_JOURNAL": "journal.jsonl",
            "TRASH_MANIFEST_JSONL": "trash.jsonl", "CATALOG_DB": "catalog.sqlite3",
            "OPERATION_PLANS_DB": "plans.sqlite3"}.items()})
        self.patch = patch.multiple(core, **paths)
        self.patch.start()
        self.book = self.library / "Autor - Libro.txt"
        self.book.write_text("Contenido de prueba. No es un libro personal.", encoding="utf-8")
        core.guardar_indice({"archivos": [{"ruta": str(self.book), "nombre": self.book.name,
                             "titulo": "Libro", "autor": "Autor", "favorite": False}]})
        self.adapter = DesktopLibraryAdapter(core)
        self.owner = "owner_a"

    def tearDown(self):
        self.adapter.close()
        self.adapter.jobs.pool.shutdown(wait=True)
        self.patch.stop()
        self.temp.cleanup()

    def api(self, path, body=None, owner=None, query=None):
        return self.adapter.dispatch("GET" if body is None else "POST", "/api/v1/" + path,
                                     query or {}, body or {}, owner or self.owner)

    def test_android_update_descriptor_and_file_integrity(self):
        import main
        apk = self.root / ("ManageYourLibrary-" + main._version() + ".apk")
        apk.write_bytes(b"synthetic APK, never installed")
        metadata = {"schema": 1, "product": "ManageYourLibrary", "platform": "android-universal",
                    "version": main._version(), "name": apk.name, "packageName": "com.erzod31.manageyourlibrary",
                    "bytes": apk.stat().st_size, "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
                    "certificateSha256": "a" * 64, "minSdk": 26, "versionCode": 5005}
        descriptor = apk.with_suffix(".update.json")
        with patch.object(self.adapter, "android_apk", side_effect=lambda: FileReply(apk, digest=hashlib.sha256(apk.read_bytes()).hexdigest())):
            for invalid in (None, "{broken", "[]", " " * 65537):
                if invalid is not None:
                    descriptor.write_text(invalid, encoding="utf-8")
                with self.assertRaises(ApiError) as error:
                    self.api("android-update")
                self.assertEqual(error.exception.status, 409)
            descriptor.write_text(json.dumps(metadata), encoding="utf-8")
            self.assertEqual(self.api("android-update"), metadata)
            self.assertEqual(self.api("android-update/file").path, apk)
            for field, wrong in (("product", "Other"), ("version", "0.0.1"), ("packageName", "other.app"),
                                 ("certificateSha256", "invalid"), ("minSdk", 1)):
                descriptor.write_text(json.dumps(dict(metadata, **{field: wrong})), encoding="utf-8")
                with self.assertRaises(ApiError):
                    self.api("android-update/file")
            descriptor.write_text(json.dumps(metadata), encoding="utf-8")
            apk.write_bytes(b"tampered APK")
            with self.assertRaises(ApiError):
                self.api("android-update/file")

    def wait(self, value, success=True):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            job = self.adapter.jobs.get(self.owner, value["job_id"])
            if job["state"] not in {"queued", "running"}:
                if success:
                    self.assertEqual(job["state"], "completed", job)
                else:
                    self.assertIn(job["state"], {"failed", "cancelled"}, job)
                return job["result"] if success else job
            time.sleep(.01)
        self.fail("Mobile job did not finish")

    def upload(self, content=b"Synthetic phone original", name="Libro nuevo.txt"):
        from urllib.parse import quote
        return self.adapter.receive_upload(self.owner, {"X-File-Name": quote(name),
            "X-Content-SHA256": hashlib.sha256(content).hexdigest()}, io.BytesIO(content), len(content))

    def preview_import(self, upload):
        return self.wait(self.api("uploads/" + upload["upload_id"] + "/import-preview",
                         {"confirmed": True, "title": "Nuevo libro", "author": "Autora", "tags": ["Revisado"]}))

    def test_list_detail_revision_edit_and_original_integrity(self):
        listed = self.api("books")["books"][0]
        detail = self.api("books/" + listed["id"])
        self.assertEqual(listed["revision"], detail["revision"])
        before = self.book.read_bytes()
        self.wait(self.api("books/" + listed["id"] + "/metadata", {"revision": listed["revision"], "favorite": True, "series": "Colección", "tags": ["Novela"]}))
        edited = self.api("books/" + listed["id"])
        self.assertTrue(edited["favorite"])
        self.assertEqual(edited["series"], "Colección")
        self.assertEqual(self.book.read_bytes(), before)
        self.assertNotEqual(listed["revision"], edited["revision"])
        self.wait(self.api("books/" + listed["id"] + "/metadata", {"revision": listed["revision"], "favorite": False}), False)

    def test_catalog_does_not_expose_files_outside_selected_library(self):
        outside = self.root / "outside.txt"
        outside.write_bytes(b"private outside")
        index = core.cargar_indice()
        index["archivos"].append({"ruta": str(outside), "titulo": "Outside"})
        core.guardar_indice(index)
        self.assertEqual(self.api("books")["total"], 1)
        for bad_id in ("..", "C:/private", self.adapter._id(outside)):
            with self.assertRaises(ApiError):
                self.api("books/" + bad_id)

    def test_upload_partial_and_invalid_names_remain_safe(self):
        for name in ("../bad.txt", "CON.txt", "bad?.txt", "trailing.txt ", "C:\\book.txt"):
            with self.subTest(name=name), self.assertRaises(ApiError):
                self.upload(name=name)
        with self.assertRaises(ApiError):
            self.adapter.receive_upload(self.owner, {"X-File-Name": "short.txt", "X-Content-SHA256": "0" * 64}, io.BytesIO(b"partial"), 100)
        receipt = self.api("uploads")["uploads"][0]
        self.assertEqual(receipt["state"], "interrupted")
        self.assertEqual((self.adapter.inbox / receipt["id"] / "transfer.part").read_bytes(), b"partial")
        self.assertFalse(self.adapter.upload_reservations)

    def test_upload_import_confirm_no_replace_and_undo_preserve_original(self):
        phone = b"Synthetic phone original"
        upload = self.upload(phone)
        with self.assertRaises(ApiError):
            self.api("uploads/" + upload["upload_id"] + "/import-preview", {"title": "Title", "author": "Author"})
        plan = self.preview_import(upload)
        staged = self.adapter.inbox / upload["upload_id"] / upload["name"]
        self.assertEqual(staged.read_bytes(), phone)
        self.assertFalse((self.library / plan["name"]).exists())
        with self.assertRaises(ApiError):
            self.api("plans/" + plan["plan_id"], {})
        applied = self.wait(self.api("plans/" + plan["plan_id"], {"confirmed": True}))
        self.assertEqual((self.library / plan["name"]).read_bytes(), phone)
        self.assertFalse(core.transacciones_archivo_incompletas())
        # A resumed completed plan must not move or duplicate the book again.
        self.wait(self.api("plans/" + plan["plan_id"], {"confirmed": True}))
        self.wait(self.api("undo", {"batch": applied["undo_batch"], "confirmed": True}))
        self.assertEqual(staged.read_bytes(), phone)
        self.assertFalse((self.library / plan["name"]).exists())
        self.assertEqual(self.api("uploads")["uploads"][0]["state"], "received")

    def test_modified_source_and_destination_collision_block_apply(self):
        upload = self.upload()
        plan = self.preview_import(upload)
        staged = self.adapter.inbox / upload["upload_id"] / upload["name"]
        staged.write_bytes(b"Changed after preview")
        self.wait(self.api("plans/" + plan["plan_id"], {"confirmed": True}), False)
        self.assertTrue(staged.exists())
        self.assertFalse((self.library / plan["name"]).exists())
        upload2 = self.upload()
        plan2 = self.preview_import(upload2)
        destination = self.library / plan2["name"]
        destination.write_bytes(b"Existing edition")
        self.wait(self.api("plans/" + plan2["plan_id"], {"confirmed": True}), False)
        self.assertEqual(destination.read_bytes(), b"Existing edition")

    def test_quarantine_is_previewed_and_recoverable(self):
        book = self.api("books")["books"][0]
        before = self.book.read_bytes()
        preview = self.wait(self.api("books/" + book["id"] + "/quarantine-preview", {"revision": book["revision"]}))
        self.assertEqual(self.book.read_bytes(), before)
        applied = self.wait(self.api("plans/" + preview["plan_id"], {"confirmed": True}))
        self.assertFalse(self.book.exists())
        self.assertTrue(self.api("undo")["available"])
        self.assertFalse(self.api("undo", owner="owner_b")["available"])
        self.wait(self.api("undo", {"confirmed": True, "batch": applied["undo_batch"]}))
        self.assertEqual(self.book.read_bytes(), before)

    def test_changed_library_and_other_owner_block_plan(self):
        plan = self.preview_import(self.upload())
        with self.assertRaises(ApiError):
            self.api("plans/" + plan["plan_id"], {"confirmed": True}, owner="owner_b")
        core.FINAL = self.root / "other_library"
        core.FINAL.mkdir()
        self.wait(self.api("plans/" + plan["plan_id"], {"confirmed": True}), False)

    def test_local_analysis_is_preview_only(self):
        book = self.api("books")["books"][0]
        before = self.book.read_bytes()
        with patch.object(core, "obtener_nombre_web", return_value={"titulo": "Sugerencia", "requiere_revision_manual": True}):
            result = self.wait(self.api("books/" + book["id"] + "/analyze", {}))
        self.assertTrue(result["preview_only"])
        self.assertEqual(self.book.read_bytes(), before)

    def test_busy_desktop_and_shutdown_reject_new_mutations(self):
        book = self.api("books")["books"][0]
        self.adapter.busy = lambda token: False
        self.wait(self.api("books/" + book["id"] + "/metadata", {"revision": book["revision"], "favorite": True}), False)
        self.adapter.close()
        with self.assertRaises(ApiError):
            self.api("books/" + book["id"] + "/analyze", {})

    def test_reopening_plan_store_does_not_reset_a_live_plan(self):
        plan = self.preview_import(self.upload())
        store = core.operation_plan_store()
        with store._db() as con:
            con.execute("UPDATE plans SET state='applying' WHERE id=?", (plan["plan_id"],))
            con.execute("UPDATE plan_items SET state='running' WHERE plan_id=?", (plan["plan_id"],))
        self.assertIs(core.operation_plan_store(), store)
        live = core.operation_plan_store().get_plan(plan["plan_id"])
        self.assertEqual(live["state"], "applying")
        self.assertEqual(live["items"][0]["state"], "running")

    def test_change_between_preview_validation_and_move_is_rejected(self):
        upload = self.upload()
        plan = self.preview_import(upload)
        staged = self.adapter.inbox / upload["upload_id"] / upload["name"]
        original_move = core.mover_a_final
        def race(source, name, **kwargs):
            source.write_bytes(b"Another file raced with the operation")
            return original_move(source, name, **kwargs)
        with patch.object(core, "mover_a_final", side_effect=race):
            self.wait(self.api("plans/" + plan["plan_id"], {"confirmed": True}), False)
        self.assertTrue(staged.exists())
        self.assertFalse((self.library / plan["name"]).exists())


class MobileLifecycleTests(unittest.TestCase):
    def test_restart_keeps_jobs_interrupted_and_owner_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "jobs.sqlite3"
            jobs = MobileJobs(path)
            with jobs.db() as con:
                con.execute("INSERT INTO jobs VALUES ('job','a','preview','running','','{}',1,1)")
            jobs.close()
            restarted = MobileJobs(path)
            self.assertEqual(restarted.get("a", "job")["state"], "interrupted")
            self.assertEqual(restarted.get("b")["jobs"], [])
            restarted.close()

    def test_tailscale_refuses_other_app_port_without_mutating_it(self):
        access = TailscaleAccess(executable="not-executed")
        access._run = Mock(side_effect=[json.dumps({"BackendState": "Running", "Self": {"DNSName": "pc.example.ts.net."}}), json.dumps({"TCP": {"10443": {"HTTPS": True}}})])
        with patch("core.mobile_tailscale.subprocess.Popen") as popen, self.assertRaises(RuntimeError):
            access.start(12345)
        popen.assert_not_called()
        self.assertEqual(access._run.call_count, 2)

    def test_tailscale_shutdown_owns_only_its_exact_proxy(self):
        access = TailscaleAccess(executable="not-executed")
        access.url = "https://pc.example.ts.net:10443"
        access.target = "http://127.0.0.1:12345"
        access.process = Mock()
        access.process.poll.return_value = 0
        # Someone else replaced the route: stop must not remove it.
        access._run = Mock(return_value=json.dumps({"Web": {"pc.example.ts.net:10443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:9999"}}}}}))
        access.stop()
        access._run.assert_called_once_with("serve", "status", "--json")
        with self.assertRaises(RuntimeError):
            access.start(12345)

    def test_tailscale_foreground_confirmation_and_occupied_port(self):
        access = TailscaleAccess(executable="not-executed")
        access.url = "https://pc.example.ts.net:10443"
        access.target = "http://127.0.0.1:12345"
        config = {"Foreground": {"test-session": {"TCP": {"10443": {"HTTPS": True}},
                  "Web": {"pc.example.ts.net:10443": {"Handlers": {"/": {"Proxy": access.target}}}}}}}
        self.assertTrue(access._owns(config))
        self.assertFalse(access._owns_root(config))
        access._run = Mock(side_effect=[json.dumps({"BackendState": "Running", "Self": {"DNSName": "pc.example.ts.net"}}), json.dumps(config)])
        with patch("core.mobile_tailscale.subprocess.Popen") as process, self.assertRaises(RuntimeError):
            access.start(12345)
        process.assert_not_called()

    def test_delayed_tk_busy_claim_cannot_lock_ui_after_timeout(self):
        from ui.mobile_panel import MobilePanel
        panel = MobilePanel.__new__(MobilePanel)
        panel.cancel_start = threading.Event()
        panel.app = Mock(trabajando=False)
        callbacks = []
        panel.app._encolar_ui.side_effect = lambda fn: callbacks.append(fn)
        ready = Mock()
        ready.wait.return_value = False
        ready.is_set.return_value = False
        with patch("ui.mobile_panel.threading.Event", return_value=ready):
            self.assertFalse(panel._remote_busy(object()))
        callbacks[0]()
        panel.app.bloquear.assert_not_called()


if __name__ == "__main__":
    unittest.main()
