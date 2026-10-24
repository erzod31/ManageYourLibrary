"""Resumable copy import: exclusive destinations, no deletion of originals."""
import hashlib
import os
from pathlib import Path
import uuid

from .file_identity import validated_sha256_file
from .file_transactions import (
    FileTransactionError, iniciar_transaccion_archivo, actualizar_transaccion_archivo,
    destino_sin_colision, leer_jsonl,
)


def copy_verified(source, destination, *, expected_hash, journal_path, app_data, cancellation=None):
    source, destination = Path(source), Path(destination)
    size, digest = validated_sha256_file(source, cancellation=cancellation)
    if not expected_hash or digest != expected_hash:
        raise FileTransactionError('El origen cambió desde la previsualización. No se copiará.')
    if source.resolve() == destination.resolve() or destination.exists():
        raise FileExistsError(str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f'.{destination.name}.{uuid.uuid4().hex}.part')
    operation = iniciar_transaccion_archivo(journal_path, app_data, 'copy', source, destination,
                                            cuarentena=staging, hash_archivo=digest)
    try:
        copied = hashlib.sha256()
        count = 0
        with source.open('rb') as reader, staging.open('xb') as writer:
            while chunk := reader.read(1024 * 1024):
                if cancellation:
                    cancellation.raise_if_cancelled()
                writer.write(chunk)
                copied.update(chunk)
                count += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        if count != size or copied.hexdigest() != digest:
            raise FileTransactionError('El contenido cambió durante la copia; se conserva para revisión.')
        if validated_sha256_file(source, cancellation=cancellation) != (size, digest):
            raise FileTransactionError('El origen cambió antes de confirmar la copia.')
        actualizar_transaccion_archivo(journal_path, app_data, operation, 'staged', 'copy',
                                      source, destination, cuarentena=staging, hash_archivo=digest)
        # Atomic publication without overwriting a competing destination.
        if os.name == 'nt':
            os.rename(staging, destination)  # Windows rename fails if target exists.
        else:
            os.link(staging, destination)
            staging.unlink()  # Only our own verified staging link; original untouched.
        if validated_sha256_file(destination, cancellation=cancellation) != (size, digest):
            raise FileTransactionError('No se pudo verificar la copia publicada.')
        actualizar_transaccion_archivo(journal_path, app_data, operation, 'committed', 'copy',
                                      source, destination, hash_archivo=digest)
        return {'destination': str(destination), 'sha256': digest, 'operation_id': operation}
    except Exception as exc:
        actualizar_transaccion_archivo(journal_path, app_data, operation, 'needs_review', 'copy',
                                      source, destination, cuarentena=staging, hash_archivo=digest, error=str(exc))
        raise


def import_copies(plan, store, *, library, journal_path, app_data, cancellation, catalog_copy):
    """Each copy is catalogued durably before the plan advances to completion.

    A retry reuses only its previously reserved, hash-verified destination.
    A crash before reservation cannot publish a copy. Ambiguity remains pending.
    """
    from .import_preview import needs_review
    library = Path(library).resolve()
    store.set_plan_state(plan['id'], 'applying')
    try:
        store.update_metadata(plan['id'], {**plan['metadata'], 'import_mode': 'copy'})
        for item in plan['items']:
            cancellation.raise_if_cancelled()
            if item['state'] in {'completed', 'skipped'}:
                continue
            meta = plan['metadata']['prepared_metadata'].get(item['source'], {})
            if needs_review(meta):
                store.set_item_state(plan['id'], item['ordinal'], 'pending', result={'review_required': True})
                continue
            store.validate_item(plan['id'], item['ordinal'], cancellation=cancellation)
            name = str(meta.get('nombre_sugerido') or Path(item['source']).name)
            if Path(name).name != name or name in {'', '.', '..'} or '/' in name or '\\' in name:
                raise ValueError('Nombre de copia no válido')
            previous = item.get('result', {})
            reserved = previous.get('copy_destination')
            destination = Path(reserved) if reserved else destino_sin_colision(library / name)
            if destination.parent.resolve() != library:
                raise ValueError('El destino de copia no pertenece a la biblioteca autorizada')
            store.set_item_state(plan['id'], item['ordinal'], 'running',
                                 result={'copy_destination': str(destination), 'copy_mode': True})
            if reserved and destination.is_file():
                owned = any(record.get('type') == 'copy' and record.get('state') in {'committed', 'committed_recovered'}
                            and record.get('origin') == item['source'] and record.get('destination') == str(destination)
                            and record.get('hash') == item['expected_hash'] for record in leer_jsonl(journal_path))
                if not owned:
                    raise FileTransactionError('El destino existe sin una copia confirmada; no se adoptará automáticamente')
                size, digest = validated_sha256_file(destination, cancellation=cancellation)
                if (size, digest) != (item['expected_size'], item['expected_hash']):
                    raise FileTransactionError('La copia pendiente cambió; revisión manual requerida')
            else:
                copy_verified(item['source'], destination, expected_hash=item['expected_hash'],
                              journal_path=journal_path, app_data=app_data, cancellation=cancellation)
            cancellation.raise_if_cancelled()
            catalog_copy(Path(item['source']), destination, meta, item['expected_hash'])
            store.set_item_state(plan['id'], item['ordinal'], 'completed',
                                 result={'copy_destination': str(destination), 'copy_mode': True})
        return store.finalize_tracked_plan(plan['id'])
    except Exception:
        store.set_plan_state(plan['id'], 'paused')
        raise
