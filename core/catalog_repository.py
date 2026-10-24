"""Transactional catalog authority. The legacy JSON remains an untouched backup.

Schema activation and file projection commit together. Whole-index writes use
optimistic revisions; single-record edits merge against durable current data.
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from .catalog_store import CatalogStore, _path_key
from .index_store import IndexRecoveryError, cargar_indice, validate_index


class CatalogConflictError(RuntimeError):
    pass


class CatalogRepository:
    def __init__(self, database, legacy_json):
        self.store = CatalogStore(database)
        self.legacy = Path(legacy_json)

    def ensure(self, initial=None):
        self._backup_projection_before_migration()
        with self.store._db() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("""CREATE TABLE IF NOT EXISTS catalog_snapshot
                        (id INTEGER PRIMARY KEY CHECK(id=1), metadata_json TEXT NOT NULL,
                         revision INTEGER NOT NULL, legacy_signature TEXT NOT NULL)""")
            state = con.execute("SELECT * FROM catalog_snapshot WHERE id=1").fetchone()
            if state:
                if state['legacy_signature'] != self._legacy_signature():
                    raise IndexRecoveryError("El índice antiguo cambió después de migrar. "
                                             "Se conservan ambas copias; recupera o importa los cambios explícitamente.")
                return
            # Existing corrupt JSON always blocks migration, even when a caller
            # supplies a seemingly valid empty in-memory catalog.
            legacy = cargar_indice(self.legacy)
            index = legacy if self.legacy.exists() else initial or legacy
            validate_index(index)
            self.store.sync_index(index, connection=con)
            count = con.execute("SELECT COUNT(*) FROM book_files WHERE present=1").fetchone()[0]
            keys = {_path_key(row['ruta']) for row in index['archivos'] if row.get('ruta')}
            if count != len(keys) or len(keys) != len(index['archivos']):
                raise IndexRecoveryError("La migración contiene rutas ausentes o duplicadas. No se ha activado.")
            metadata = {key: value for key, value in index.items() if key not in {'archivos', '_revision'}}
            con.execute("INSERT INTO catalog_snapshot VALUES (1, ?, 1, ?)",
                        (json.dumps(metadata, ensure_ascii=False), self._legacy_signature()))
            return not self.legacy.exists() and initial is not None

    def _backup_projection_before_migration(self):
        with self.store._db(read_only=True) as source:
            exists = source.execute("SELECT 1 FROM sqlite_master WHERE name='catalog_snapshot'").fetchone()
            if exists and source.execute('SELECT 1 FROM catalog_snapshot WHERE id=1').fetchone():
                return
            if not source.execute('SELECT 1 FROM book_files LIMIT 1').fetchone():
                return
            folder = self.store.path.parent / 'backups'
            folder.mkdir(exist_ok=True)
            target = folder / f'catalog_pre_migration_{time.time_ns()}_{uuid.uuid4().hex[:8]}.sqlite3'
            with target.open('xb'):
                pass
            with closing(sqlite3.connect(target)) as destination:
                source.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise IndexRecoveryError('No se pudo verificar la copia anterior a la migración.')

    def _legacy_signature(self):
        try:
            stat = self.legacy.stat()
            return f'{stat.st_size}:{stat.st_mtime_ns}'
        except FileNotFoundError:
            return 'missing'

    def load(self):
        self.ensure()
        with self.store._db(read_only=True) as con:
            con.execute("BEGIN")
            state = con.execute("SELECT * FROM catalog_snapshot WHERE id=1").fetchone()
            result = json.loads(state['metadata_json'])
            result['archivos'] = [json.loads(row[0]) for row in con.execute(
                "SELECT metadata_json FROM book_files WHERE present=1 ORDER BY rowid")]
            result['_revision'] = state['revision']
            return result

    def save(self, index):
        validate_index(index)
        keys = {_path_key(row['ruta']) for row in index['archivos'] if isinstance(row.get('ruta'), str) and row['ruta'].strip()}
        if len(keys) != len(index['archivos']):
            raise IndexRecoveryError('Hay rutas ausentes o duplicadas. No se guardará un catálogo incompleto.')
        if self.ensure(index):
            index['_revision'] = 1
            return
        with self.store._db() as con:
            con.execute("BEGIN IMMEDIATE")
            revision = con.execute("SELECT revision FROM catalog_snapshot WHERE id=1").fetchone()[0]
            if '_revision' in index and index['_revision'] != revision:
                raise CatalogConflictError("El catálogo cambió durante la operación. Recarga antes de guardar.")
            self.store.sync_index(index, connection=con)
            metadata = {key: value for key, value in index.items() if key not in {'archivos', '_revision'}}
            con.execute("UPDATE catalog_snapshot SET metadata_json=?, revision=revision+1 WHERE id=1",
                        (json.dumps(metadata, ensure_ascii=False),))
        index['_revision'] = revision + 1

    def update(self, path, transform, *, initial=None):
        self.ensure(initial)
        with self.store._db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT metadata_json FROM book_files WHERE path_key=? AND present=1",
                              (_path_key(path),)).fetchone()
            if row is None:
                raise FileNotFoundError(str(path))
            updated = transform(json.loads(row[0]))
            if _path_key(updated.get('ruta')) != _path_key(path):
                raise ValueError('Una edición de metadatos no puede cambiar la ubicación del archivo.')
            self.store.sync_index({'archivos': [updated]}, complete=False, connection=con)
            con.execute("UPDATE catalog_snapshot SET revision=revision+1 WHERE id=1")
            revision = con.execute("SELECT revision FROM catalog_snapshot WHERE id=1").fetchone()[0]
        return updated, revision

    def export_json(self, target):
        target = Path(target)
        if target.resolve() in {self.legacy.resolve(), self.store.path.resolve()}:
            raise ValueError("Exporta a un archivo nuevo, no sobre el perfil activo.")
        if target.exists():
            raise FileExistsError(str(target))
        index = self.load()
        index.pop('_revision', None)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(index, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name == 'nt':
                os.rename(temporary, target)  # Fails if another writer reserved target.
            else:
                os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def backup(self, target):
        target = Path(target)
        self.ensure()
        # Exclusive reservation avoids overwriting an existing backup.
        with target.open('xb'):
            pass
        with self.store._db(read_only=True) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise IndexRecoveryError("La copia no superó la comprobación de integridad.")
        return target
