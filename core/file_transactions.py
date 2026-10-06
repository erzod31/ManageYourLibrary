import errno
import json
import os
import re
import shutil
import threading
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

from . import file_identity

TRASH_DIR_NAME = ".trash_manageyourlibrary"
_JOURNAL_LOCK = threading.RLock()


class FileTransactionError(RuntimeError):
    """Base error for durable file operations."""


class JournalWriteError(FileTransactionError):
    """Raised when a safety record cannot be persisted."""


class JournalCorruptionWarning(RuntimeWarning):
    """Emitted when a malformed JSONL record is found."""


class VerifiedMoveError(FileTransactionError):
    """Raised when a physical move could not be verified or rolled back cleanly."""

    def __init__(self, message: str, *, expected_hash: str = "", rolled_back: bool = False):
        super().__init__(message)
        self.expected_hash = expected_hash
        self.rolled_back = rolled_back


def timestamp():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def escritura_atomica_texto(ruta, texto, encoding="utf-8"):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.tmp.{os.getpid()}.{time.time_ns()}")
    try:
        with open(temporal, "w", encoding=encoding, newline="") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    finally:
        try:
            if temporal.exists():
                temporal.unlink()
        except OSError:
            pass


def append_texto_durable(ruta, texto, encoding="utf-8"):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with _JOURNAL_LOCK, open(ruta, "a", encoding=encoding, newline="") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())


def append_jsonl_durable(ruta, registro):
    append_texto_durable(ruta, json.dumps(registro, ensure_ascii=False) + "\n", encoding="utf-8")


def nuevo_transaction_id(tipo):
    seguro = re.sub(r"[^a-zA-Z0-9_]+", "_", str(tipo or "fileop")).strip("_") or "fileop"
    now = datetime.now(timezone.utc).astimezone()
    return f"{seguro}_{now.strftime('%Y%m%d_%H%M%S_%f')}_{os.getpid()}"


def calcular_sha256_archivo(ruta: Path, bloque=1024 * 1024) -> str:
    return file_identity.sha256_file(ruta, block_size=bloque)


def _validar_archivo_origen(ruta: Path, hash_esperado="") -> tuple[int, str]:
    ruta = Path(ruta)
    if not ruta.exists() or not ruta.is_file():
        raise FileTransactionError(f"No existe el archivo de origen: {ruta}")
    try:
        tamano, hash_actual = file_identity.validated_sha256_file(ruta)
    except file_identity.FileChangedDuringReadError as exc:
        raise FileTransactionError(f"El archivo cambió durante la validación: {ruta}") from exc
    if hash_esperado and hash_actual != hash_esperado:
        raise FileTransactionError(f"El archivo cambió antes de aplicar la operación: {ruta}")
    return tamano, hash_actual


def _validar_destino(ruta: Path, tamano_esperado: int, hash_esperado: str):
    ruta = Path(ruta)
    if not ruta.exists() or not ruta.is_file():
        raise FileTransactionError(f"No se pudo verificar el destino: {ruta}")
    try:
        tamano_actual, hash_actual = file_identity.validated_sha256_file(ruta)
    except file_identity.FileChangedDuringReadError as exc:
        raise FileTransactionError(f"El destino cambió durante la verificación: {ruta}") from exc
    if tamano_actual != tamano_esperado:
        raise FileTransactionError(f"El tamaño del destino no coincide: {ruta}")
    if hash_actual != hash_esperado:
        raise FileTransactionError(f"El contenido del destino no coincide: {ruta}")


def registrar_evento_transaccion(journal_path, app_data, op_id, tipo, estado, origen="", destino="", cuarentena="", motivo="", hash_archivo="", error=""):
    try:
        Path(app_data).mkdir(parents=True, exist_ok=True)
        registro = {
            "id": str(op_id),
            "type": str(tipo),
            "state": str(estado),
            "origin": str(origen or ""),
            "destination": str(destino or ""),
            "quarantine": str(cuarentena or ""),
            "timestamp": timestamp(),
            "reason": str(motivo or ""),
            "hash": str(hash_archivo or ""),
            "error": str(error or ""),
        }
        append_jsonl_durable(journal_path, registro)
        return registro
    except JournalWriteError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise JournalWriteError(f"No se pudo escribir el diario transaccional {journal_path}: {exc}") from exc


def iniciar_transaccion_archivo(journal_path, app_data, tipo, origen="", destino="", cuarentena="", motivo="", hash_archivo=""):
    op_id = nuevo_transaction_id(tipo)
    registrar_evento_transaccion(journal_path, app_data, op_id, tipo, "pending", origen, destino, cuarentena, motivo, hash_archivo)
    return op_id


def actualizar_transaccion_archivo(journal_path, app_data, op_id, estado, tipo="update", origen="", destino="", cuarentena="", motivo="", hash_archivo="", error=""):
    if not op_id:
        return
    registrar_evento_transaccion(journal_path, app_data, op_id, tipo, estado, origen, destino, cuarentena, motivo, hash_archivo, error)


def leer_jsonl(ruta, *, strict=False):
    registros = []
    ruta = Path(ruta)
    if not ruta.exists():
        return registros
    try:
        with _JOURNAL_LOCK, open(ruta, "r", encoding="utf-8") as f:
            lineas = list(f)
        for numero, linea in enumerate(lineas, start=1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                registros.append(json.loads(linea))
            except (json.JSONDecodeError, TypeError) as exc:
                mensaje = f"Registro JSONL dañado en {ruta}, línea {numero}: {exc}"
                if strict:
                    raise FileTransactionError(mensaje) from exc
                warnings.warn(mensaje, JournalCorruptionWarning, stacklevel=2)
                continue
    except FileTransactionError:
        raise
    except (OSError, UnicodeError) as exc:
        if strict:
            raise FileTransactionError(f"No se pudo leer {ruta}: {exc}") from exc
        warnings.warn(f"No se pudo leer {ruta}: {exc}", JournalCorruptionWarning, stacklevel=2)
    return registros


def transacciones_archivo_incompletas(journal_path):
    ultimos = {}
    for registro in leer_jsonl(journal_path):
        op_id = registro.get("id")
        if op_id:
            ultimos[op_id] = registro
    incompletos = {"pending", "validated", "old_quarantined", "moved", "failed", "needs_review"}
    return [registro for registro in ultimos.values() if registro.get("state") in incompletos]


def recuperar_transacciones_archivo_pendientes(journal_path, app_data):
    incompletas = transacciones_archivo_incompletas(journal_path)
    for item in incompletas:
        origen = Path(item.get("origin", "")) if item.get("origin") else None
        destino = Path(item.get("destination", "")) if item.get("destination") else None
        origen_existe = bool(origen and origen.exists())
        destino_existe = bool(destino and destino.exists())
        cuarentena = Path(item.get("quarantine", "")) if item.get("quarantine") else None
        estado = "needs_review"
        motivo = "No se pudo determinar automáticamente el resultado físico de la operación."

        if origen_existe and not destino_existe:
            if cuarentena and cuarentena.exists() and destino:
                try:
                    if restaurar_descartado(cuarentena, destino):
                        estado = "rolled_back_recovered"
                        motivo = "Se restauró desde cuarentena el archivo anterior; el nuevo origen permanece intacto."
                    else:
                        raise FileTransactionError("No se pudo restaurar el archivo en cuarentena")
                except (OSError, RuntimeError) as exc:
                    estado = "needs_review"
                    motivo = f"No se pudo revertir el reemplazo interrumpido: {exc}"
            else:
                estado = "rolled_back"
                motivo = "El origen permanece intacto y el destino no existe; no hay movimiento que recuperar."
        elif not origen_existe and destino_existe:
            esperado = str(item.get("hash", "") or "")
            try:
                if esperado and calcular_sha256_archivo(destino) != esperado:
                    raise FileTransactionError("El hash del destino no coincide con el registrado.")
                estado = "committed_recovered"
                motivo = "El destino fue verificado y el movimiento quedó confirmado durante la recuperación."
            except (OSError, RuntimeError) as exc:
                estado = "needs_review"
                motivo = f"El destino existe pero no superó la verificación: {exc}"
        elif origen_existe and destino_existe:
            motivo = "Existen tanto origen como destino; se requiere revisión para evitar sobrescrituras."
        else:
            motivo = "No existen ni el origen ni el destino registrados; se requiere revisión manual."

        registrar_evento_transaccion(
            journal_path, app_data, item.get("id", ""), item.get("type", "file_operation"),
            estado, origen or "", destino or "", item.get("quarantine", ""), motivo,
            item.get("hash", ""), item.get("error", ""),
        )
    return incompletas


def destino_sin_colision(destino: Path) -> Path:
    destino = Path(destino)
    if not destino.exists():
        return destino
    carpeta = destino.parent
    base = destino.stem
    ext = destino.suffix
    contador = 2
    while True:
        candidato = carpeta / f"{base}_{contador}{ext}"
        if not candidato.exists():
            return candidato
        contador += 1


def _move_no_replace(origen: Path, destino: Path, tamano: int, digest: str):
    """Publish without replacing an existing file, including cross-volume moves."""
    try:
        if os.name == "nt":
            # Windows rename is atomic and rejects an occupied destination.
            os.rename(origen, destino)
        else:
            # POSIX rename overwrites; an exclusive hard link does not.
            os.link(origen, destino)
            origen.unlink()
        return
    except OSError as exc:
        if exc.errno not in {errno.EXDEV, errno.EPERM, errno.ENOTSUP} and getattr(exc, "winerror", None) != 17:
            raise
    # Never use shutil.move's overwriting copy fallback. Keep both files on
    # failure so recovery can review an interrupted or partially copied file.
    with origen.open("rb") as source, destino.open("xb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    shutil.copystat(origen, destino)
    _validar_destino(destino, tamano, digest)
    _validar_archivo_origen(origen, digest)
    origen.unlink()


def _mover_verificado(origen: Path, destino: Path, *, journal_path, app_data, op_id, tipo, motivo="", cuarentena="", hash_esperado="") -> str:
    """Move one file only after live validation and verify the resulting bytes."""
    origen = Path(origen)
    destino = Path(destino)
    before = file_identity._live_signature(origen)
    tamano, hash_archivo = _validar_archivo_origen(origen, hash_esperado)
    actualizar_transaccion_archivo(
        journal_path, app_data, op_id, "validated", tipo, origen, destino,
        cuarentena, motivo, hash_archivo,
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    if file_identity._live_signature(origen) != before:
        raise FileTransactionError(f"El archivo cambió antes del movimiento: {origen}")
    _move_no_replace(origen, destino, tamano, hash_archivo)
    try:
        _validar_destino(destino, tamano, hash_archivo)
    except (OSError, RuntimeError) as verification_error:
        rolled_back = False
        rollback_error = None
        if destino.exists() and not origen.exists():
            try:
                _validar_archivo_origen(destino, hash_archivo)
                origen.parent.mkdir(parents=True, exist_ok=True)
                _move_no_replace(destino, origen, tamano, hash_archivo)
                _validar_destino(origen, tamano, hash_archivo)
                rolled_back = True
                actualizar_transaccion_archivo(
                    journal_path,
                    app_data,
                    op_id,
                    "rolled_back",
                    tipo,
                    origen,
                    destino,
                    cuarentena,
                    motivo,
                    hash_archivo,
                    verification_error,
                )
            except (OSError, RuntimeError) as exc:
                rollback_error = exc
        if not rolled_back:
            detail = f"{verification_error}; rollback_error={rollback_error or 'not_possible'}"
            actualizar_transaccion_archivo(
                journal_path,
                app_data,
                op_id,
                "needs_review",
                tipo,
                origen,
                destino,
                cuarentena,
                motivo,
                hash_archivo,
                detail,
            )
        raise VerifiedMoveError(
            f"No se pudo verificar el movimiento {origen} -> {destino}: {verification_error}",
            expected_hash=hash_archivo,
            rolled_back=rolled_back,
        ) from verification_error
    actualizar_transaccion_archivo(
        journal_path, app_data, op_id, "moved", tipo, origen, destino,
        cuarentena, motivo, hash_archivo,
    )
    return hash_archivo


def carpeta_cuarentena(base: Path | None, library_root: Path | None, app_data: Path, trash_dir_name=TRASH_DIR_NAME) -> Path:
    if base is not None:
        return Path(base) / trash_dir_name
    if library_root:
        return Path(library_root) / trash_dir_name
    return Path(app_data) / trash_dir_name


def registrar_manifest_cuarentena(manifest_path, destino, origen, motivo="", conservado="", op_id=""):
    destino = Path(destino)
    registro = {
        "operation_id": str(op_id or ""),
        "timestamp": timestamp(),
        "origin": str(origen or ""),
        "quarantine_path": str(destino),
        "reason": str(motivo or ""),
        "kept_file": str(conservado or ""),
    }
    append_jsonl_durable(destino.parent / "manifest.jsonl", registro)
    append_jsonl_durable(manifest_path, registro)


def descartar_archivo_seguro(ruta: Path, base_cuarentena: Path | None = None, motivo: str = "", conservado: Path | str | None = None, op_id: str | None = None, *, journal_path, app_data, manifest_path, library_root=None, trash_dir_name=TRASH_DIR_NAME) -> Path | None:
    ruta = Path(ruta)
    if not ruta.exists() or not ruta.is_file():
        return None

    carpeta = carpeta_cuarentena(base_cuarentena, library_root, app_data, trash_dir_name)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = destino_sin_colision(carpeta / ruta.name)
    transaccion_propia = op_id is None
    op_id = op_id or iniciar_transaccion_archivo(journal_path, app_data, "quarantine", ruta, destino, "", motivo)
    try:
        hash_archivo = _mover_verificado(
            ruta, destino, journal_path=journal_path, app_data=app_data,
            op_id=op_id, tipo="quarantine", motivo=motivo, cuarentena=destino,
        )
        registrar_manifest_cuarentena(manifest_path, destino, ruta, motivo, conservado or "", op_id)
        estado = "committed" if transaccion_propia else "pending"
        actualizar_transaccion_archivo(journal_path, app_data, op_id, estado, "quarantine", ruta, destino, destino, motivo, hash_archivo)
        return destino
    except (OSError, RuntimeError, ValueError) as error:
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "failed", "quarantine", ruta, destino, "", motivo,
            hash_archivo=getattr(error, "expected_hash", ""), error=error,
        )
        raise


def restaurar_descartado(cuarentena: Path | None, destino_original: Path) -> bool:
    if not cuarentena:
        return False
    cuarentena = Path(cuarentena)
    destino_original = Path(destino_original)
    if not cuarentena.exists() or destino_original.exists():
        return False
    destino_original.parent.mkdir(parents=True, exist_ok=True)
    tamano, hash_archivo = _validar_archivo_origen(cuarentena)
    _move_no_replace(cuarentena, destino_original, tamano, hash_archivo)
    _validar_destino(destino_original, tamano, hash_archivo)
    return True


def mover_a_revisar_nuevamente(ruta: Path, carpeta: Path, motivo: str = "", op_id: str | None = None, *, journal_path, app_data) -> Path:
    ruta = Path(ruta)
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = destino_sin_colision(carpeta / ruta.name)
    transaccion_propia = op_id is None
    op_id = op_id or iniciar_transaccion_archivo(journal_path, app_data, "move_to_review", ruta, destino, motivo=motivo)
    try:
        hash_archivo = _mover_verificado(
            ruta, destino, journal_path=journal_path, app_data=app_data,
            op_id=op_id, tipo="move_to_review", motivo=motivo,
        )
        estado = "committed" if transaccion_propia else "pending"
        actualizar_transaccion_archivo(journal_path, app_data, op_id, estado, "move_to_review", ruta, destino, motivo=motivo, hash_archivo=hash_archivo)
        return destino
    except (OSError, RuntimeError, ValueError) as error:
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "failed", "move_to_review", ruta, destino,
            motivo=motivo, hash_archivo=getattr(error, "expected_hash", ""), error=error,
        )
        raise


def mover_a_final(libro: Path, nombre_destino: str, library_root: Path, motivo: str = "", op_id: str | None = None, *, journal_path, app_data, cuarentena="") -> Path:
    library_root = Path(library_root)
    library_root.mkdir(parents=True, exist_ok=True)
    destino = destino_sin_colision(library_root / nombre_destino)
    transaccion_propia = op_id is None
    op_id = op_id or iniciar_transaccion_archivo(journal_path, app_data, "move_to_library", libro, destino, motivo=motivo)
    try:
        hash_archivo = _mover_verificado(
            libro, destino, journal_path=journal_path, app_data=app_data,
            op_id=op_id, tipo="move_to_library", motivo=motivo, cuarentena=cuarentena,
        )
        estado = "committed" if transaccion_propia else "pending"
        actualizar_transaccion_archivo(journal_path, app_data, op_id, estado, "move_to_library", libro, destino, cuarentena, motivo, hash_archivo)
        return destino
    except (OSError, RuntimeError, ValueError) as error:
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "failed", "move_to_library", libro, destino,
            motivo=motivo, hash_archivo=getattr(error, "expected_hash", ""), error=error,
        )
        raise


def mover_a_final_reemplazando(libro: Path, nombre_destino: str, existente: Path, library_root: Path, motivo: str = "", *, journal_path, app_data, manifest_path, trash_dir_name=TRASH_DIR_NAME) -> tuple[Path, Path | None]:
    library_root = Path(library_root)
    existente = Path(existente)
    cuarentena = None
    destino_previsto = library_root / nombre_destino
    op_id = iniciar_transaccion_archivo(journal_path, app_data, "replace_to_library", libro, destino_previsto, motivo=motivo or f"Reemplazar {existente}")
    if existente.exists():
        cuarentena = descartar_archivo_seguro(existente, library_root, motivo=motivo or f"Reemplazo por {libro}", conservado=libro, op_id=op_id, journal_path=journal_path, app_data=app_data, manifest_path=manifest_path, library_root=library_root, trash_dir_name=trash_dir_name)
        if not cuarentena:
            raise FileTransactionError(f"No se pudo mover a cuarentena: {existente}")
        _, hash_nuevo = _validar_archivo_origen(libro)
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "old_quarantined", "replace_to_library",
            libro, destino_previsto, cuarentena, motivo, hash_nuevo,
        )

    try:
        destino = mover_a_final(
            libro, nombre_destino, library_root, motivo=motivo, op_id=op_id,
            journal_path=journal_path, app_data=app_data, cuarentena=cuarentena or "",
        )
        if not destino.exists():
            raise FileTransactionError(f"No se pudo verificar el destino: {destino}")
        hash_archivo = calcular_sha256_archivo(destino)
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "committed", "replace_to_library",
            libro, destino, cuarentena, motivo, hash_archivo,
        )
        return destino, cuarentena
    except (OSError, RuntimeError, ValueError) as error:
        restaurado = restaurar_descartado(cuarentena, existente)
        hash_archivo = calcular_sha256_archivo(libro) if libro.exists() and libro.is_file() else ""
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "failed", "replace_to_library",
            libro, destino_previsto, cuarentena,
            f"{motivo} | restored_old={restaurado}", hash_archivo, error,
        )
        raise


def reemplazar_archivo_transaccional(nuevo: Path, destino_existente: Path, base_cuarentena: Path | None = None, motivo: str = "", *, journal_path, app_data, manifest_path, trash_dir_name=TRASH_DIR_NAME) -> tuple[Path, Path | None]:
    nuevo = Path(nuevo)
    destino_existente = Path(destino_existente)
    try:
        if nuevo.resolve() == destino_existente.resolve():
            return destino_existente, None
    except OSError:
        pass
    if not nuevo.exists():
        raise FileTransactionError(f"No existe el archivo nuevo: {nuevo}")

    cuarentena = None
    op_id = iniciar_transaccion_archivo(journal_path, app_data, "replace_existing", nuevo, destino_existente, motivo=motivo or f"Reemplazar {destino_existente}")
    if destino_existente.exists():
        cuarentena = descartar_archivo_seguro(destino_existente, base_cuarentena, motivo=motivo or f"Reemplazo por {nuevo}", conservado=nuevo, op_id=op_id, journal_path=journal_path, app_data=app_data, manifest_path=manifest_path, library_root=base_cuarentena, trash_dir_name=trash_dir_name)
        if not cuarentena:
            raise FileTransactionError(f"No se pudo mover a cuarentena: {destino_existente}")
        _, hash_nuevo = _validar_archivo_origen(nuevo)
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "old_quarantined", "replace_existing",
            nuevo, destino_existente, cuarentena, motivo, hash_nuevo,
        )

    try:
        destino_existente.parent.mkdir(parents=True, exist_ok=True)
        hash_archivo = _mover_verificado(
            nuevo, destino_existente, journal_path=journal_path, app_data=app_data,
            op_id=op_id, tipo="replace_existing", motivo=motivo, cuarentena=cuarentena or "",
        )
        actualizar_transaccion_archivo(journal_path, app_data, op_id, "committed", "replace_existing", nuevo, destino_existente, cuarentena, motivo, hash_archivo)
        return destino_existente, cuarentena
    except (OSError, RuntimeError, ValueError) as error:
        restaurado = restaurar_descartado(cuarentena, destino_existente)
        hash_archivo = calcular_sha256_archivo(nuevo) if nuevo.exists() and nuevo.is_file() else ""
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "failed", "replace_existing",
            nuevo, destino_existente, cuarentena,
            f"{motivo} | restored_old={restaurado}", hash_archivo, error,
        )
        raise


def renombrar_en_sitio_seguro(origen: Path, nuevo_nombre: str, motivo: str = "", *, journal_path, app_data) -> Path:
    origen = Path(origen)
    if not origen.exists():
        raise FileTransactionError(f"No existe el archivo para renombrar: {origen}")
    destino = destino_sin_colision(origen.parent / nuevo_nombre)
    if destino.parent.resolve() != origen.parent.resolve():
        raise FileTransactionError("Search metadata solo puede renombrar dentro de la carpeta original.")
    op_id = iniciar_transaccion_archivo(journal_path, app_data, "rename_in_place", origen, destino, motivo=motivo)
    try:
        hash_archivo = _mover_verificado(
            origen, destino, journal_path=journal_path, app_data=app_data,
            op_id=op_id, tipo="rename_in_place", motivo=motivo,
        )
        actualizar_transaccion_archivo(journal_path, app_data, op_id, "committed", "rename_in_place", origen, destino, motivo=motivo, hash_archivo=hash_archivo)
        return destino
    except (OSError, RuntimeError, ValueError) as error:
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "failed", "rename_in_place", origen, destino,
            motivo=motivo, hash_archivo=getattr(error, "expected_hash", ""), error=error,
        )
        raise


def restaurar_accion_undo(item, *, journal_path, app_data):
    actual = Path(item.get("destino", ""))
    original = Path(item.get("origen", ""))
    if not actual.exists():
        return False, f"No existe el archivo a restaurar: {actual}"
    expected = str(item.get("sha256") or item.get("hash") or "")
    if not expected:
        # Older undo rows can only be recovered with durable movement evidence.
        candidates = set()
        for record in reversed(leer_jsonl(journal_path)):
            if (record.get("state") in {"committed", "committed_recovered"}
                    and record.get("origin") == str(original)
                    and record.get("destination") == str(actual)
                    and (not item.get("fecha") or record.get("timestamp", "") <= item["fecha"])
                    and record.get("hash")):
                candidates.add(record["hash"])
        if len(candidates) == 1:
            expected = candidates.pop()
    original.parent.mkdir(parents=True, exist_ok=True)
    destino_final = original
    if destino_final.exists():
        destino_final = destino_sin_colision(destino_final)
    op_id = iniciar_transaccion_archivo(journal_path, app_data, "undo_restore", actual, destino_final, motivo=item.get("detalle", ""))
    try:
        if not expected:
            raise FileTransactionError("Deshacer requiere revisión: no hay hash original verificable.")
        hash_archivo = _mover_verificado(
            actual, destino_final, journal_path=journal_path, app_data=app_data,
            op_id=op_id, tipo="undo_restore", motivo=item.get("detalle", ""), hash_esperado=expected,
        )
        actualizar_transaccion_archivo(journal_path, app_data, op_id, "committed", "undo_restore", actual, destino_final, motivo=item.get("detalle", ""), hash_archivo=hash_archivo)
        return True, str(destino_final)
    except (OSError, RuntimeError, ValueError) as error:
        actualizar_transaccion_archivo(
            journal_path, app_data, op_id, "needs_review", "undo_restore", actual, destino_final,
            motivo=item.get("detalle", ""), hash_archivo=expected, error=error,
        )
        return False, str(error)
