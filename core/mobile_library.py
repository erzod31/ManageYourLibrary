"""Android adapter: shared desktop catalog, local OCR, durable reviewed actions."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PureWindowsPath

from .cancellation import CancellationToken, OperationCancelled
from .document_context import DocumentContext
from .file_transactions import calcular_sha256_archivo
from .index_store import guardar_json
from .library_view_model import LibraryViewIndex, display_item, item_is_favorite
from .mobile_access import ApiError, FileReply, MAX_UPLOAD_BYTES


class MobileJobs:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS jobs
                (id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
                 state TEXT NOT NULL, message TEXT NOT NULL, result TEXT NOT NULL,
                 created REAL NOT NULL, updated REAL NOT NULL)""")
            con.execute("UPDATE jobs SET state='interrupted',message='Interrumpida; revisa el plan antes de reanudar' WHERE state IN ('queued','running')")
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MobileJob")
        self.tokens = {}

    def db(self):
        from contextlib import contextmanager

        @contextmanager
        def connection():
            con = sqlite3.connect(self.path, timeout=10)
            con.row_factory = sqlite3.Row
            try:
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("PRAGMA synchronous=FULL")
                yield con
                con.commit()
            except Exception:
                con.rollback()
                raise
            finally:
                con.close()
        return connection()

    def update(self, job_id, state, message="", result=None):
        with self.db() as con:
            con.execute("UPDATE jobs SET state=?,message=?,result=?,updated=? WHERE id=?",
                        (state, str(message)[:1000], json.dumps(result or {}, ensure_ascii=False), time.time(), job_id))

    def submit(self, owner, kind, task):
        with self.lock:
            if len(self.tokens) >= 8:
                raise ApiError(429, "Hay varias tareas pendientes. Espera a que terminen.")
            job_id = uuid.uuid4().hex
            token = CancellationToken()
            now = time.time()
            with self.db() as con:
                con.execute("INSERT INTO jobs VALUES (?,?,?,'queued','','{}',?,?)", (job_id, owner, kind, now, now))
            self.tokens[job_id] = (owner, token)

            def run():
                try:
                    token.raise_if_cancelled()
                    self.update(job_id, "running", "Procesando en el PC")
                    result = task(token, lambda message: self.update(job_id, "running", message))
                    self.update(job_id, "completed", "Completada", result)
                except OperationCancelled:
                    self.update(job_id, "cancelled", "Cancelada; los archivos y planes siguen recuperables")
                except Exception as exc:
                    self.update(job_id, "failed", str(exc))
                finally:
                    with self.lock:
                        self.tokens.pop(job_id, None)
            try:
                self.pool.submit(run)
            except RuntimeError as exc:
                self.tokens.pop(job_id, None)
                self.update(job_id, "interrupted", "El acceso móvil se ha detenido")
                raise ApiError(503, "El acceso móvil se ha detenido") from exc
            return {"job_id": job_id}

    def get(self, owner, job_id=None):
        with self.db() as con:
            if job_id:
                rows = con.execute("SELECT * FROM jobs WHERE owner=? AND id=?", (owner, job_id)).fetchall()
            else:
                rows = con.execute("SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 80", (owner,)).fetchall()
        results = []
        for row in rows:
            value = dict(row)
            value["result"] = json.loads(value["result"])
            value.pop("owner")
            results.append(value)
        if job_id:
            if not results:
                raise ApiError(404, "Tarea no encontrada.")
            return results[0]
        return {"jobs": results}

    def cancel(self, owner, job_id):
        self.get(owner, job_id)
        with self.lock:
            entry = self.tokens.get(job_id)
            if entry and entry[0] == owner:
                entry[1].cancel()
        return {"ok": True}

    def cancel_all(self):
        with self.lock:
            tokens = list(self.tokens.values())
        for _, token in tokens:
            token.cancel()

    def cancel_owner(self, owner):
        with self.lock:
            tokens = [token for device, token in self.tokens.values() if device == owner]
        for token in tokens:
            token.cancel()

    def close(self):
        self.cancel_all()
        # Queued tasks run their cancellation handler and remain recorded.
        self.pool.shutdown(wait=False, cancel_futures=False)


class DesktopLibraryAdapter:
    def __init__(self, core, *, busy=None, changed=None):
        self.core = core
        self.state = core.APP_DATA / "mobile"
        self.inbox = self.state / "inbox"
        self.jobs = MobileJobs(self.state / "jobs.sqlite3")
        self.plans = core.operation_plan_store()
        self.lock = threading.RLock()
        self.busy = busy or (lambda _token: True)
        self.changed = changed or (lambda: None)
        self._view = None
        self._view_stamp = None
        self._map = {}
        self.closed = threading.Event()
        self.upload_reservations = {}

    def close(self):
        self.closed.set()
        self.jobs.close()

    def _library(self):
        if not self.core.biblioteca_configurada():
            raise ApiError(409, "Elige primero una carpeta de biblioteca en el PC.")
        return Path(self.core.FINAL).resolve()

    @staticmethod
    def _id(path):
        return hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode("utf-8", "surrogatepass")).hexdigest()

    def _snapshot(self):
        with self.lock:
            try:
                stat = self.core.INDICE_JSON.stat()
                stamp = (stat.st_mtime_ns, stat.st_size, str(self.core.FINAL))
            except OSError:
                stamp = (0, 0, str(self.core.FINAL))
            if self._view is None or stamp != self._view_stamp:
                index = self.core.cargar_indice()
                try:
                    root = self._library()
                except ApiError:
                    rows = []
                else:
                    rows = []
                    for row in index.get("archivos", []):
                        path = Path(row.get("ruta", "")).resolve()
                        if path.is_relative_to(root) and path.is_file() and not self.core.ignorar_por_carpeta(path):
                            rows.append(row)
                self._view = LibraryViewIndex(rows)
                self._map = {self._id(row["ruta"]): row for row in rows}
                self._view_stamp = stamp
            return self._view

    def _book(self, book_id):
        self._snapshot()
        with self.lock:
            raw = self._map.get(book_id)
            if raw is None:
                raise ApiError(404, "El libro ya no está en la biblioteca. Actualiza la lista.")
            row = display_item(dict(raw))
        path = Path(row["ruta"]).resolve()
        if not path.is_relative_to(self._library()) or not path.is_file() or self.core.ignorar_por_carpeta(path):
            raise ApiError(404, "Archivo no disponible.")
        return row, path

    def _public_book(self, raw):
        row = display_item(raw)
        stat = Path(row["ruta"]).stat()
        identity = [row.get(key) for key in ("titulo", "autor_mostrar", "serie_mostrar", "tags_mostrar",
                    "isbn", "anio_mostrar", "idioma_mostrar", "editorial_mostrar", "read_status")]
        revision = hashlib.sha256(json.dumps([identity, item_is_favorite(row), stat.st_size, stat.st_mtime_ns],
                                            sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        return {"id": self._id(row["ruta"]), "revision": revision, "title": row["titulo"],
                "author": row["autor_mostrar"], "format": row["formato"], "name": row["nombre"],
                "path": row["ruta"], "size": stat.st_size, "size_label": row["tamano_mostrar"],
                "series": row["serie_mostrar"], "tags": row["tags_mostrar"],
                "favorite": item_is_favorite(row), "isbn": row.get("isbn", ""),
                "year": row["anio_mostrar"], "language": row["idioma_mostrar"],
                "publisher": row["editorial_mostrar"], "read_status": str(row.get("read_status", "por_leer"))}

    @staticmethod
    def _text(value, maximum=240):
        if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise ApiError(400, "Texto no válido o demasiado largo.")
        return value.strip()

    def _fields(self, body):
        mapping = {"title": "titulo", "author": "autor", "series": "serie", "year": "anio",
                   "isbn": "isbn", "language": "idioma", "publisher": "editorial", "read_status": "read_status"}
        fields = {}
        for source, target in mapping.items():
            if source in body:
                fields[target] = self._text(body[source])
        if "favorite" in body:
            if not isinstance(body["favorite"], bool):
                raise ApiError(400, "Favorito debe ser verdadero o falso.")
            fields["favorite"] = body["favorite"]
        if "tags" in body:
            values = body["tags"]
            if not isinstance(values, list) or len(values) > 20:
                raise ApiError(400, "Usa como máximo 20 etiquetas.")
            fields["tags"] = list(dict.fromkeys(self._text(value, 60) for value in values if value))
        if not fields:
            raise ApiError(400, "No hay cambios para guardar.")
        return fields

    def _task(self, owner, kind, function):
        if self.closed.is_set():
            raise ApiError(503, "El acceso móvil está desactivado.")
        def execute(token, progress):
            if not self.busy(token):
                raise ApiError(409, "El PC está ocupado. Espera a que termine la operación actual.")
            try:
                token.raise_if_cancelled()
                return function(token, progress)
            finally:
                self._view = None
                self.busy(None)
                self.changed()
        return self.jobs.submit(owner, kind, execute)

    @staticmethod
    def _metadata(value):
        fields = ("titulo", "autor", "isbn", "anio", "editorial", "idioma", "serie", "edicion",
                  "fuente", "metodo", "nombre_sugerido", "motivo", "confianza", "confianza_global",
                  "requiere_revision_manual", "encontrado", "decision_bibliografica")
        return {key: value[key] for key in fields if key in value and isinstance(value[key], (str, bool, int, float))}

    def _upload_record(self, owner, upload_id):
        if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
            raise ApiError(404, "Envío no encontrado.")
        path = self.inbox / upload_id / "receipt.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ApiError(404, "Envío no disponible; se conserva cualquier archivo recibido.") from exc
        if record.get("owner") != owner:
            raise ApiError(404, "Envío no encontrado.")
        source = path.parent / record["name"]
        if source.parent != path.parent or not source.resolve().is_relative_to(self.inbox.resolve()):
            raise ApiError(400, "Ruta de envío no válida.")
        return record, path, source

    def _uploads(self, owner):
        rows = []
        if self.inbox.exists():
            for directory in sorted(self.inbox.iterdir(), key=lambda p: p.name):
                try:
                    record, _, _ = self._upload_record(owner, directory.name)
                except ApiError:
                    continue
                rows.append({key: value for key, value in record.items() if key not in {"owner", "sha256"}})
        return {"uploads": sorted(rows, key=lambda x: x["created"], reverse=True)[:100]}

    def receive_upload(self, owner, headers, stream, length):
        from urllib.parse import unquote_to_bytes

        if length <= 0:
            raise ApiError(400, "El archivo está vacío.")
        try:
            name = unquote_to_bytes(headers.get("X-File-Name", "")).decode("utf-8")
        except UnicodeError as exc:
            raise ApiError(400, "Nombre de archivo no válido.") from exc
        if (not name or len(name.encode("utf-8")) > 180 or
                any(c in name for c in '/\\:<>"|?*') or any(ord(c) < 32 for c in name) or
                name.endswith((".", " ")) or PureWindowsPath(name).is_reserved() or
                name in {".", "..", "receipt.json"}):
            raise ApiError(400, "Nombre de archivo no válido.")
        if Path(name).suffix.lower() not in self.core.EXTENSIONES_LIBROS:
            raise ApiError(415, "Formato no admitido. Usa un libro compatible, por ejemplo PDF o EPUB.")
        expected = headers.get("X-Content-SHA256", "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ApiError(400, "Falta la firma SHA-256 del envío.")
        # Staging cannot grow without bound; never delete an existing receipt or book.
        with self.lock:
            staged = list(self.inbox.glob("*/*")) if self.inbox.exists() else []
            occupied = sum(p.stat().st_size for p in staged if p.is_file() and p.parent.name not in self.upload_reservations)
            if occupied + sum(self.upload_reservations.values()) + length > 2 * 1024**3:
                raise ApiError(507, "La bandeja del PC está llena. Resuelve los envíos pendientes antes de continuar.")
            upload_id = uuid.uuid4().hex
            directory = self.inbox / upload_id
            directory.mkdir(parents=True)
            receipt = directory / "receipt.json"
            record = {"id": upload_id, "owner": owner, "name": name, "bytes": length,
                      "sha256": expected, "created": time.time(), "state": "receiving"}
            guardar_json(receipt, record)
            self.upload_reservations[upload_id] = length
        digest = hashlib.sha256()
        try:
            with (directory / "transfer.part").open("xb") as target:
                remaining = length
                while remaining:
                    if self.closed.is_set():
                        raise ApiError(503, "El acceso móvil se ha desactivado; el envío sigue recuperable.")
                    data = stream.read(min(64 * 1024, remaining))
                    if not data:
                        raise ApiError(400, "Transferencia interrumpida. El original del móvil sigue intacto.")
                    target.write(data)
                    digest.update(data)
                    remaining -= len(data)
                target.flush()
                os.fsync(target.fileno())
            if digest.hexdigest() != expected:
                raise ApiError(409, "La firma del archivo recibido no coincide. Vuelve a enviarlo.")
            os.replace(directory / "transfer.part", directory / name)
            record["state"] = "received"
        except Exception:
            record["state"] = "interrupted"
            guardar_json(receipt, record)
            raise
        finally:
            with self.lock:
                self.upload_reservations.pop(upload_id, None)
        guardar_json(receipt, record)
        return {"upload_id": upload_id, "name": name, "sha256": expected, "bytes": length}

    def android_apk(self):
        import sys
        import main
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        name = f"ManageYourLibrary-{main._version()}.apk"
        path = root / "android" / name
        if not path.is_file():
            path = root / "dist/android" / name
        if not path.is_file():
            raise ApiError(404, "El APK no está incluido en este paquete de escritorio.")
        return FileReply(path, "application/vnd.android.package-archive", path.name, calcular_sha256_archivo(path))

    def dispatch(self, method, path, query, body, owner):
        parts = path.strip("/").split("/")
        if parts[:2] != ["api", "v1"]:
            raise ApiError(404, "Recurso no encontrado.")
        route = parts[2:]
        if method == "GET" and route in (["android-update"], ["android-update", "file"]):
            reply = self.android_apk()
            descriptor = reply.path.with_suffix(".update.json")
            try:
                if descriptor.stat().st_size > 65536:
                    raise ValueError("Oversized Android descriptor")
                metadata = json.loads(descriptor.read_text(encoding="utf-8"))
                if not isinstance(metadata, dict):
                    raise ValueError("Invalid Android descriptor")
            except (OSError, ValueError) as exc:
                raise ApiError(409, "Faltan los datos verificados del APK. Actualiza el paquete de escritorio.") from exc
            import main
            if (metadata.get("schema") != 1 or metadata.get("product") != "ManageYourLibrary" or
                    metadata.get("platform") != "android-universal" or
                    metadata.get("version") != main._version() or metadata.get("name") != reply.path.name or
                    metadata.get("packageName") != "com.erzod31.manageyourlibrary" or
                    metadata.get("bytes") != reply.path.stat().st_size or metadata.get("sha256") != reply.digest or
                    metadata.get("minSdk") != 26 or not isinstance(metadata.get("versionCode"), int) or
                    not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("certificateSha256", "")))):
                raise ApiError(409, "El paquete Android del PC cambió o no tiene una identidad válida.")
            return reply if len(route) == 2 else metadata
        if method == "GET" and route == ["status"]:
            view = self._snapshot()
            import main
            return {"version": main._version(), "protocol": 1,
                    "library_configured": self.core.biblioteca_configurada(), "stats": view.stats,
                    "ocr": "Indra OCR (PC)", "offline_mode": self.core.cargar_configuracion_operacion()["offline_mode"]}
        if method == "GET" and route == ["license"]:
            from .ocr_runtime import resource_root
            return {"name": "Indra OCR by Datalab", "text": (resource_root() / "third_party/indra/MODEL_LICENSE.txt").read_text(encoding="utf-8"),
                    "source": "https://huggingface.co/datalab-to/indra-ocr"}
        if method == "GET" and route == ["books"]:
            try:
                offset = max(0, min(1_000_000, int(query.get("offset", ["0"])[0])))
                limit = max(1, min(60, int(query.get("limit", ["30"])[0])))
            except ValueError as exc:
                raise ApiError(400, "Paginación no válida.") from exc
            search = query.get("q", [""])[0][:200]
            rows = self._snapshot().filter(search, query.get("format", ["all"])[0])
            scope = query.get("scope", ["library"])[0]
            if scope == "favorites":
                rows = [row for row in rows if item_is_favorite(row)]
            if scope == "series":
                rows = [row for row in rows if row.get("serie_mostrar")]
            if scope == "tags":
                rows = [row for row in rows if row.get("tags_mostrar")]
            result = []
            for row in rows[offset:offset + limit]:
                try:
                    result.append(self._public_book(row))
                except OSError:
                    continue
            return {"books": result, "total": len(rows), "offset": offset, "limit": limit}
        if len(route) >= 2 and route[0] == "books":
            book_id = route[1]
            row, source = self._book(book_id)
            if method == "GET" and len(route) == 2:
                return self._public_book(row)
            if method == "GET" and route[2:] == ["cover"]:
                from .cover_service import CoverService
                thumbnail = CoverService(self.core.APP_DATA / "mobile_covers", size=(180, 252)).thumbnail_path(source, row.get("cover_url", ""))
                if not thumbnail:
                    raise ApiError(404, "Portada no disponible.")
                return FileReply(thumbnail, "image/webp")
            if method == "GET" and route[2:] == ["file"]:
                if source.stat().st_size > MAX_UPLOAD_BYTES:
                    raise ApiError(413, "Este archivo supera los 512 MB. Ábrelo desde el PC.")
                context = DocumentContext(source)
                digest = context.sha256
                context.assert_unchanged()
                return FileReply(source, mimetypes.guess_type(source.name)[0] or "application/octet-stream", source.name, digest)
            if method == "POST" and route[2:] == ["metadata"]:
                fields = self._fields(body)
                revision = body.get("revision")
                def edit(token, progress):
                    current, current_path = self._book(book_id)
                    if self._public_book(current)["revision"] != revision:
                        raise ApiError(409, "El libro cambió. Vuelve a abrir sus detalles antes de editar.")
                    token.raise_if_cancelled()
                    self.core.aplicar_correccion_manual_indice(current_path, fields)
                    self._view = None
                    progress("Metadatos guardados; el archivo original no se ha renombrado")
                    return {"book_id": book_id}
                return self._task(owner, "metadata", edit)
            if method == "POST" and route[2:] == ["analyze"]:
                def analyze(token, progress):
                    context = DocumentContext(source)
                    value = self.core.obtener_nombre_web(source, callback=progress, cancellation=token)
                    context.assert_unchanged()
                    return {"book_id": book_id, "metadata": self._metadata(value), "preview_only": True}
                return self._task(owner, "analyze", analyze)
            if method == "POST" and route[2:] == ["quarantine-preview"]:
                if body.get("revision") != self._public_book(row)["revision"]:
                    raise ApiError(409, "El libro cambió. Actualiza sus detalles.")
                def preview(token, progress):
                    token.raise_if_cancelled()
                    plan = self.plans.create_plan("mobile_quarantine", [{"action": "quarantine", "source": source}],
                        metadata={"owner": owner, "library": str(self._library()), "name": source.name})
                    return {"plan_id": plan["id"], "name": source.name, "action": "quarantine", "preview_only": True}
                return self._task(owner, "preview", preview)
        if method == "GET" and route == ["uploads"]:
            return self._uploads(owner)
        if len(route) == 3 and route[0] == "uploads" and method == "POST":
            upload_id, action = route[1:]
            record, receipt, source = self._upload_record(owner, upload_id)
            if action == "analyze":
                def analyze_upload(token, progress):
                    if not source.is_file() or calcular_sha256_archivo(source) != record["sha256"]:
                        raise ApiError(409, "El archivo recibido cambió o está incompleto.")
                    value = self._metadata(self.core.obtener_nombre_web(source, callback=progress, cancellation=token))
                    token.raise_if_cancelled()
                    if calcular_sha256_archivo(source) != record["sha256"]:
                        raise ApiError(409, "El archivo cambió durante el análisis.")
                    latest, _, _ = self._upload_record(owner, upload_id)
                    latest.update(state="review", metadata=value)
                    guardar_json(receipt, latest)
                    return {"upload_id": upload_id, "metadata": value, "preview_only": True}
                return self._task(owner, "analyze_upload", analyze_upload)
            if action == "import-preview":
                fields = self._fields(body)
                if body.get("confirmed") is not True:
                    raise ApiError(400, "Confirma los metadatos revisados antes de preparar la importación.")
                def preview_import(token, progress):
                    token.raise_if_cancelled()
                    if record["state"] in {"completed", "receiving", "interrupted"}:
                        raise ApiError(409, "Este envío ya se importó o está incompleto.")
                    if calcular_sha256_archivo(source) != record["sha256"]:
                        raise ApiError(409, "El archivo recibido cambió.")
                    title, author = fields.get("titulo", ""), fields.get("autor", "")
                    if not title or not author:
                        raise ApiError(400, "Revisa el título y el autor antes de importar.")
                    name = self.core.crear_nombre_sugerido(author, title, fields.get("anio", ""), fields.get("isbn", ""), source.suffix)
                    destination = self._library() / name
                    if destination.parent != self._library():
                        raise ApiError(400, "Nombre de destino no válido.")
                    if destination.exists():
                        raise ApiError(409, "Ya existe ese nombre. Revisa edición, idioma o volumen; no se reemplazará ningún libro.")
                    plan = self.plans.create_plan("mobile_import", [{"action": "import", "source": source, "destination": destination}],
                        metadata={"owner": owner, "library": str(self._library()), "name": name,
                                  "upload_id": upload_id, "fields": fields, "receipt": str(receipt)})
                    return {"plan_id": plan["id"], "name": name, "action": "import", "preview_only": True}
                return self._task(owner, "preview", preview_import)
        if len(route) == 2 and route[0] == "plans" and method == "POST":
            plan = self.plans.get_plan(route[1])
            if not plan or plan["metadata"].get("owner") != owner or plan["kind"] not in {"mobile_import", "mobile_quarantine"}:
                raise ApiError(404, "Plan no encontrado.")
            if body.get("confirmed") is not True:
                raise ApiError(400, "Confirma expresamente este plan.")
            def apply_plan(token, progress):
                if plan["metadata"]["library"] != str(self._library()):
                    raise ApiError(409, "La biblioteca seleccionada en el PC cambió. Prepara otro plan.")
                batch_id = f"mobile_{plan['id']}"
                def execute(item, cancellation):
                    source = Path(item["source"])
                    cancellation.raise_if_cancelled()
                    self.plans.validate_item(plan["id"], item["ordinal"])
                    if item["action"] == "import":
                        if not source.resolve().is_relative_to(self.inbox.resolve()):
                            raise ApiError(403, "Origen de importación no válido.")
                        destination = self._library() / plan["metadata"]["name"]
                        if destination.exists():
                            raise ApiError(409, "El destino ya existe. Se conserva el envío para revisión.")
                        destination = self.core.mover_a_final(source, destination.name, motivo="Importación móvil confirmada", op_id=f"{plan['id']}_{item['ordinal']}", expected_hash=item["expected_hash"])
                        self.core.registrar_undo(batch_id, "mover", source, destination, "Importación móvil")
                        self.core.actualizar_indice_rutas([source, destination])
                        self.core.aplicar_correccion_manual_indice(destination, plan["metadata"]["fields"])
                        record_path = Path(plan["metadata"]["receipt"])
                        record = json.loads(record_path.read_text(encoding="utf-8"))
                        record.update(state="completed", destination=str(destination), plan_id=plan["id"])
                        guardar_json(record_path, record)
                    else:
                        if not source.resolve().is_relative_to(self._library()) or self.core.ignorar_por_carpeta(source):
                            raise ApiError(403, "El origen ya no es un libro activo de la biblioteca.")
                        destination = self.core.descartar_archivo_seguro(source, motivo="Cuarentena móvil confirmada", op_id=f"{plan['id']}_{item['ordinal']}", expected_hash=item["expected_hash"])
                        if destination is None:
                            raise ApiError(409, "No se completó el traslado a cuarentena.")
                        self.core.registrar_undo(batch_id, "descartar", source, destination, "Cuarentena móvil")
                        self.core.actualizar_indice_rutas([source])
                    self.core.escribir_historial("movil", source, destination, "completado", "Acción confirmada; recuperable mediante Deshacer")
                    self.core.actualizar_transaccion_archivo(f"{plan['id']}_{item['ordinal']}", "committed",
                        "move_to_library" if item["action"] == "import" else "quarantine", source, destination,
                        hash_archivo=item["expected_hash"])
                    return {"destination": str(destination), "undo_batch": batch_id}
                applied = self.plans.apply(plan["id"], execute, cancellation=token)
                if applied["state"] == "paused" and token.cancelled:
                    raise OperationCancelled()
                if applied["state"] != "completed":
                    errors = [item["error"] for item in applied["items"] if item.get("error")]
                    raise ApiError(409, "; ".join(errors) or "El plan sigue pendiente; revisa Actividad.")
                return {"plan_id": plan["id"], "undo_batch": batch_id, "completed": True}
            return self._task(owner, "apply_plan", apply_plan)
        if method == "GET" and route == ["plans"]:
            return {"plans": [{"id": p["id"], "kind": p["kind"], "state": p["state"], "name": p["metadata"].get("name", "")}
                    for p in self.plans.list_resumable() if p["metadata"].get("owner") == owner]}
        if method == "GET" and route == ["jobs"]:
            return self.jobs.get(owner)
        if len(route) == 2 and route[0] == "jobs" and method == "GET":
            return self.jobs.get(owner, route[1])
        if len(route) == 3 and route[0] == "jobs" and route[2] == "cancel" and method == "POST":
            return self.jobs.cancel(owner, route[1])
        if method == "GET" and route == ["undo"]:
            batch, items = self.core.obtener_ultima_accion_undo()
            if not batch or not batch.startswith("mobile_"):
                return {"available": False}
            plan = self.plans.get_plan(batch.removeprefix("mobile_"))
            if not plan or plan["metadata"].get("owner") != owner:
                return {"available": False}
            return {"available": True, "batch": batch, "files": [Path(item["destino"]).name for item in items]}
        if method == "POST" and route == ["undo"]:
            batch = body.get("batch")
            if body.get("confirmed") is not True or not isinstance(batch, str) or not batch.startswith("mobile_"):
                raise ApiError(400, "Confirma la operación que quieres deshacer.")
            plan = self.plans.get_plan(batch.removeprefix("mobile_"))
            if not plan or plan["metadata"].get("owner") != owner:
                raise ApiError(404, "Operación no encontrada.")
            def undo(token, progress):
                latest, items = self.core.obtener_ultima_accion_undo()
                if latest != batch:
                    raise ApiError(409, "Hay otra operación más reciente. Revisa Deshacer en el PC.")
                restored = 0
                for item in reversed(items):
                    token.raise_if_cancelled()
                    ok, message = self.core.restaurar_accion_undo(item)
                    if not ok:
                        raise ApiError(409, message)
                    self.core.mark_undo_item_restored(batch, item)
                    self.core.actualizar_indice_rutas([item["origen"], item["destino"], message])
                    if plan["kind"] == "mobile_import":
                        receipt = Path(plan["metadata"]["receipt"])
                        record = json.loads(receipt.read_text(encoding="utf-8"))
                        record.update(state="review" if record.get("metadata") else "received", name=Path(message).name)
                        record.pop("destination", None)
                        record.pop("plan_id", None)
                        guardar_json(receipt, record)
                    restored += 1
                self.core.mark_action_undone(batch)
                return {"restored": restored}
            return self._task(owner, "undo", undo)
        raise ApiError(404, "Recurso no encontrado.")
