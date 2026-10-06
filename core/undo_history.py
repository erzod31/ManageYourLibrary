import csv
import json
import uuid
import warnings
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from .file_transactions import append_jsonl_durable, append_texto_durable
from .file_identity import validated_sha256_file


class UndoHistoryCorruptionWarning(RuntimeWarning):
    """Warn that damaged undo rows were preserved and skipped."""


def _local_now():
    return datetime.now(timezone.utc).astimezone()


def timestamp():
    return _local_now().strftime("%Y-%m-%d %H:%M:%S")


def nuevo_batch_id(prefijo):
    return f"{prefijo}_{_local_now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:12]}"


def registrar_undo(undo_jsonl, app_data, batch_id, tipo, origen, destino, detalle=""):
    Path(app_data).mkdir(parents=True, exist_ok=True)
    registro = {
        "batch_id": batch_id,
        "action_id": uuid.uuid4().hex,
        "fecha": timestamp(),
        "tipo": tipo,
        "origen": str(origen),
        "destino": str(destino),
        "detalle": str(detalle),
    }
    if Path(destino).is_file():
        size, digest = validated_sha256_file(Path(destino))
        registro.update(sha256=digest, size_bytes=size)
    append_jsonl_durable(undo_jsonl, registro)
    return registro


def mark_action_undone(undo_jsonl, app_data, batch_id):
    Path(app_data).mkdir(parents=True, exist_ok=True)
    registro = {
        "batch_id": batch_id,
        "fecha": timestamp(),
        "tipo": "undone",
    }
    append_jsonl_durable(undo_jsonl, registro)
    return registro


def mark_undo_item_restored(undo_jsonl, app_data, batch_id, item):
    """Persist progress so a partially completed undo can be retried safely."""
    Path(app_data).mkdir(parents=True, exist_ok=True)
    action_id = item.get("action_id") or _legacy_action_id(item)
    registro = {
        "batch_id": batch_id,
        "action_id": action_id,
        "fecha": timestamp(),
        "tipo": "undo_item_restored",
    }
    append_jsonl_durable(undo_jsonl, registro)
    return registro


def _legacy_action_id(item):
    return "legacy:" + "|".join(
        str(item.get(key, "")) for key in ("batch_id", "tipo", "origen", "destino", "fecha")
    )


def obtener_ultima_accion_undo(undo_jsonl):
    undo_jsonl = Path(undo_jsonl)
    if not undo_jsonl.exists():
        return None, []

    registros = []
    undone = set()
    restored = set()
    corrupt_lines = 0

    try:
        with open(undo_jsonl, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    item = json.loads(linea)
                except (json.JSONDecodeError, TypeError):
                    corrupt_lines += 1
                    continue

                if item.get("tipo") == "undone":
                    undone.add(item.get("batch_id"))
                elif item.get("tipo") == "undo_item_restored":
                    restored.add(item.get("action_id"))
                elif item.get("batch_id"):
                    registros.append(item)
    except (OSError, UnicodeError):
        return None, []

    if corrupt_lines:
        warnings.warn(
            f"El historial de deshacer contiene {corrupt_lines} línea(s) dañada(s); se conservaron y omitieron.",
            UndoHistoryCorruptionWarning,
            stacklevel=2,
        )

    for item in reversed(registros):
        batch = item.get("batch_id")
        if batch and batch not in undone:
            accion = [
                r for r in registros
                if r.get("batch_id") == batch
                and (r.get("action_id") or _legacy_action_id(r)) not in restored
            ]
            if accion:
                return batch, accion

    return None, []


def escribir_historial(historial_csv, app_data, accion, origen, destino="", resultado="", detalle="", nombre_sugerido="", fuente="", confianza=""):
    Path(app_data).mkdir(parents=True, exist_ok=True)
    historial_csv = Path(historial_csv)
    existe = historial_csv.exists()
    campos = ["fecha", "accion", "origen", "destino", "resultado", "detalle", "nombre_sugerido", "fuente", "confianza"]

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=campos)
    if not existe:
        writer.writeheader()
    writer.writerow({
        "fecha": timestamp(),
        "accion": accion,
        "origen": str(origen),
        "destino": str(destino),
        "resultado": resultado,
        "detalle": detalle,
        "nombre_sugerido": nombre_sugerido,
        "fuente": fuente,
        "confianza": confianza,
    })
    append_texto_durable(historial_csv, buffer.getvalue(), encoding="utf-8-sig")
