"""Explicitly enabled, authenticated Android access over a local Tailscale proxy."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import index_store

PROTOCOL_VERSION = 1
MAX_JSON_BYTES = 64 * 1024
MAX_UPLOAD_BYTES = 512 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


@dataclass
class FileReply:
    path: Path
    mime: str = "application/octet-stream"
    filename: str = ""
    digest: str = ""


class DeviceAccess:
    """Store hashes of device tokens. Pairing codes are short-lived, memory-only."""

    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.lock = threading.RLock()
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or not isinstance(value.get("devices"), dict):
                    raise ValueError("Invalid device store")
                for key, row in value["devices"].items():
                    if (not isinstance(key, str) or len(key) != 32 or
                            any(c not in "0123456789abcdef" for c in key) or
                            not isinstance(row, dict) or not isinstance(row.get("token_hash"), str) or
                            len(row["token_hash"]) != 64 or
                            any(c not in "0123456789abcdef" for c in row["token_hash"]) or
                            not isinstance(row.get("name"), str) or
                            not isinstance(row.get("created"), (int, float))):
                        raise ValueError("Invalid device entry")
            except (OSError, ValueError) as exc:
                raise RuntimeError("No se pudo leer el registro móvil; se conserva para recuperación.") from exc
            self.devices = value["devices"]
        else:
            self.devices = {}
        self.code_hash = ""
        self.expires = 0
        self.failures = []

    def new_code(self):
        with self.lock:
            code = f"{secrets.randbelow(100_000_000):08d}"
            self.code_hash = hashlib.sha256(code.encode()).hexdigest()
            self.expires = self.clock() + 120
            self.failures.clear()
            return code

    def pair(self, code, name):
        with self.lock:
            now = self.clock()
            self.failures = [value for value in self.failures if now - value < 60]
            if len(self.failures) >= 5:
                raise ApiError(429, "Demasiados intentos. Espera un minuto y genera otro código en el PC.")
            if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit():
                self.failures.append(now)
                raise ApiError(401, "Código de conexión incorrecto o caducado.")
            digest = hashlib.sha256(code.encode()).hexdigest()
            if now >= self.expires or not self.code_hash or not hmac.compare_digest(digest, self.code_hash):
                self.failures.append(now)
                raise ApiError(401, "Código de conexión incorrecto o caducado.")
            if len(self.devices) >= 16:
                raise ApiError(409, "Desvincula un dispositivo en el PC antes de añadir otro.")
            device_id = uuid.uuid4().hex
            secret = secrets.token_urlsafe(32)
            updated = {**self.devices, device_id: {"name": str(name or "Android")[:80],
                       "token_hash": hashlib.sha256(secret.encode()).hexdigest(), "created": now}}
            index_store.guardar_json(self.path, {"version": 1, "devices": updated})
            self.devices = updated
            self.code_hash = ""
            self.expires = 0
            return {"device_id": device_id, "token": f"{device_id}.{secret}", "protocol": PROTOCOL_VERSION}

    def authenticate(self, header):
        if not isinstance(header, str) or not header.startswith("Bearer ") or len(header) > 256:
            raise ApiError(401, "Vuelve a vincular el móvil desde la aplicación de escritorio.")
        device_id, separator, secret = header[7:].partition(".")
        with self.lock:
            expected = self.devices.get(device_id, {}).get("token_hash", "0" * 64)
            actual = hashlib.sha256(secret.encode()).hexdigest()
            valid = separator and hmac.compare_digest(expected, actual)
        if not valid:
            raise ApiError(401, "Vuelve a vincular el móvil desde la aplicación de escritorio.")
        return device_id

    def revoke_all(self):
        with self.lock:
            index_store.guardar_json(self.path, {"version": 1, "devices": {}})
            self.devices = {}
            self.code_hash = ""
            self.expires = 0

    def revoke(self, device_id):
        with self.lock:
            updated = {key: row for key, row in self.devices.items() if key != device_id}
            index_store.guardar_json(self.path, {"version": 1, "devices": updated})
            self.devices = updated

    def public_devices(self):
        with self.lock:
            return [{"id": key, "name": row.get("name", "Android"), "created": row.get("created", 0)}
                    for key, row in self.devices.items()]


class MobileHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, address, access, adapter):
        if address[0] != "127.0.0.1":
            raise ValueError("Mobile access must bind only to loopback behind Tailscale Serve")
        self.access = access
        self.adapter = adapter
        self.slots = threading.BoundedSemaphore(12)
        super().__init__(address, MobileHandler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class MobileHandler(BaseHTTPRequestHandler):
    server_version = "ManageYourLibraryMobile/1"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, *args):
        # Credentials, filenames and pairing codes must never reach access logs.
        pass

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _length(self, maximum):
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(400, "Usa una transferencia con tamaño conocido.")
        values = self.headers.get_all("Content-Length") or []
        if len(values) != 1 or not values[0].isascii() or not values[0].isdigit():
            raise ApiError(411, "Falta el tamaño de la solicitud.")
        length = int(values[0])
        if length > maximum:
            raise ApiError(413, "El archivo o la solicitud supera el límite permitido.")
        return length

    def _json_body(self):
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "Se requiere JSON.")
        length = self._length(MAX_JSON_BYTES)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ApiError(400, "Solicitud incompleta.")
        try:
            value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError) as exc:
            raise ApiError(400, "JSON no válido.") from exc

    def _handle(self, method):
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or len(self.path) > 4096:
                raise ApiError(400, "Ruta no válida.")
            if self.headers.get("Origin"):
                raise ApiError(403, "Este acceso está reservado a la aplicación Android vinculada.")
            if method == "GET" and parsed.path == "/api/v1/health":
                self._json({"protocol": PROTOCOL_VERSION, "app": "ManageYourLibrary"})
                return
            if method == "GET" and parsed.path == "/api/v1/client.apk":
                self._file(self.server.adapter.android_apk())
                return
            if method == "POST" and parsed.path == "/api/v1/pair":
                body = self._json_body()
                self._json(self.server.access.pair(body.get("code"), body.get("device")))
                return
            owner = self.server.access.authenticate(self.headers.get("Authorization"))
            query = parse_qs(parsed.query, max_num_fields=12)
            if method == "POST" and parsed.path == "/api/v1/unpair":
                self._json_body()
                self.server.adapter.jobs.cancel_owner(owner)
                self.server.access.revoke(owner)
                self._json({"ok": True})
                return
            if method == "POST" and parsed.path == "/api/v1/upload":
                length = self._length(MAX_UPLOAD_BYTES)
                result = self.server.adapter.receive_upload(owner, self.headers, self.rfile, length)
            else:
                body = self._json_body() if method == "POST" else {}
                result = self.server.adapter.dispatch(method, parsed.path, query, body, owner)
            if isinstance(result, FileReply):
                self._file(result)
            else:
                self._json(result)
        except ApiError as exc:
            self.close_connection = True
            self._json({"error": str(exc)}, status=exc.status)
        except (BrokenPipeError, ConnectionError, TimeoutError):
            self.close_connection = True
        except Exception:
            self.close_connection = True
            self._json({"error": "No se pudo completar la solicitud. Revisa la conexión o el estado del PC."}, status=500)

    def _headers(self, status, mime, length):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")

    def _json(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(raw))
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, reply):
        from urllib.parse import quote

        with reply.path.open("rb") as stream:
            import os
            size = os.fstat(stream.fileno()).st_size
            self._headers(200, reply.mime, size)
            if reply.digest:
                self.send_header("X-Content-SHA256", reply.digest)
            if reply.filename:
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(reply.filename, safe=""))
            self.end_headers()
            remaining = size
            while remaining:
                chunk = stream.read(min(64 * 1024, remaining))
                if not chunk:
                    self.close_connection = True
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class MobileService:
    def __init__(self, access, adapter):
        self.access, self.adapter = access, adapter
        self.server = None
        self.thread = None

    def start(self):
        if self.server is not None:
            raise RuntimeError("El acceso móvil ya está activo.")
        self.server = MobileHttpServer(("127.0.0.1", 0), self.access, self.adapter)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True, name="MobileAccess")
        self.thread.start()
        return self.server.server_port

    def stop(self):
        server, self.server = self.server, None
        if server:
            server.shutdown()
            server.server_close()
        self.adapter.close()
        if self.thread:
            self.thread.join(timeout=2)
