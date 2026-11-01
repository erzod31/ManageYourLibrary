"""Exercise frozen companion imports, HTTP and safe operations in a fresh profile."""
import hashlib
import http.client
import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch


def run_and_record(output, *, version):
    report = {"version": version, "frozen": bool(getattr(sys, "frozen", False)), "checks": {}}
    checks = report["checks"]
    service = adapter = None
    try:
        if "library_core" in sys.modules:
            raise RuntimeError("Requires a fresh process before profile-dependent imports")
        with tempfile.TemporaryDirectory(prefix="myl_mobile_runtime_") as temp:
            root = Path(temp)
            from core import config_store
            with (patch.dict(os.environ, {name: str(root / name) for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}),
                  patch.object(config_store, "app_data_dir", return_value=root / "profile")):
                import library_core as core
                import ui.mobile_panel  # Validate lazy frozen imports without opening a window.
                assert callable(ui.mobile_panel.MobilePanel)
                assert core.APP_DATA.is_relative_to(root)
                from core.mobile_access import DeviceAccess, MobileService
                from core.mobile_library import DesktopLibraryAdapter
                from core.ocr_runtime import resource_root
                library = root / "library"
                library.mkdir()
                core.FINAL = library
                source = library / "Synthetic desktop fixture.txt"
                source.write_bytes(b"Disposable companion fixture. No personal book.")
                core.guardar_indice({"archivos": [{"ruta": str(source), "nombre": source.name, "titulo": "Synthetic fixture", "autor": "Test Author"}]})
                access = DeviceAccess(core.APP_DATA / "mobile/devices.json")
                adapter = DesktopLibraryAdapter(core)
                apk = adapter.android_apk()
                assert apk.path.name == f"ManageYourLibrary-{version}.apk"
                with zipfile.ZipFile(apk.path) as archive:
                    names = archive.namelist()
                    assert all("\\" not in entry.orig_filename for entry in archive.infolist())
                    assert not any(name.startswith("lib/") for name in names)
                    assert "assets/licenses/PROJECT_LICENSE.txt" in names
                    assert not any("test_ca" in name or name.endswith((".p12", ".dpapi")) for name in names)
                    assert b"QaInstrumentation" not in archive.read("classes.dex")
                assert (resource_root() / "VERSION").read_text().strip() == version
                assert json.loads(apk.path.with_suffix(".update.json").read_text())["sha256"] == apk.digest
                checks["bundled_release_apk_and_lazy_imports"] = "passed"
                service = MobileService(access, adapter)
                port = service.start()
                token = ""
                def request(path, body=None, headers=None, method=None):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                    values = {"Authorization": "Bearer " + token} if token else {}
                    if isinstance(body, dict):
                        body = json.dumps(body).encode()
                        values["Content-Type"] = "application/json"
                    values.update(headers or {})
                    try:
                        connection.request(method or ("POST" if body is not None else "GET"), "/api/v1/" + path, body, values)
                        response = connection.getresponse()
                        result = json.load(response)
                        if response.status != 200:
                            raise RuntimeError(f"HTTP {response.status}: {result}")
                        return result
                    finally:
                        connection.close()
                def job(path, body):
                    job_id = request(path, body)["job_id"]
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        value = request("jobs/" + job_id)
                        if value["state"] == "completed":
                            return value["result"]
                        if value["state"] not in {"running", "queued"}:
                            raise RuntimeError(value["message"])
                        time.sleep(.02)
                    raise RuntimeError("Companion fixture job timed out")
                assert request("health")["protocol"] == 1
                token = request("pair", {"code": access.new_code(), "device": "Disposable frozen check"})["token"]
                checks["private_http_pairing"] = "passed"
                book = request("books")["books"][0]
                job("books/" + book["id"] + "/metadata", {"revision": book["revision"], "favorite": True})
                assert request("books/" + book["id"])["favorite"] is True
                checks["catalog_and_confirmed_metadata"] = "passed"
                content = b"Disposable phone original"
                digest = hashlib.sha256(content).hexdigest()
                received = request("upload", content, {"X-File-Name": "Mobile-fixture.txt", "X-Content-SHA256": digest})
                plan = job("uploads/" + received["upload_id"] + "/import-preview", {"confirmed": True, "title": "Mobile fixture", "author": "Test Author"})
                assert not (library / plan["name"]).exists()
                applied = job("plans/" + plan["plan_id"], {"confirmed": True})
                assert (library / plan["name"]).read_bytes() == content
                job("undo", {"confirmed": True, "batch": applied["undo_batch"]})
                assert not (library / plan["name"]).exists()
                assert source.read_bytes() == b"Disposable companion fixture. No personal book."
                checks["verified_upload_preview_apply_undo"] = "passed"
                access.revoke_all()
                try:
                    request("books")
                except RuntimeError as exc:
                    assert "HTTP 401" in str(exc)
                else:
                    raise AssertionError("Revocation did not block access")
                checks["revocation"] = "passed"
                service.stop()
                service = None
                adapter.jobs.pool.shutdown(wait=True)
                adapter = None
        report["passed"] = len(checks) == 5
    except Exception as exc:
        report.update(passed=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        if service:
            service.stop()
        if adapter:
            adapter.jobs.pool.shutdown(wait=True)
    report["tailscale_configuration"] = "not_modified_by_this_check"
    report["physical_phone"] = "not_tested"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report.get("passed") else 1
