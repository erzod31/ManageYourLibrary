"""Verified profile archives; restoration never overwrites an existing file.

Book folders outside the profile are references, not included book backups.
Call while application jobs are idle. SQLite uses its online backup protocol.
"""
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

MANIFEST = 'profile-manifest.json'
MAX_RESTORE_BYTES = 16 * 1024 ** 3


def _copy_and_hash(source, destination):
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(1024 * 1024):
        destination.write(chunk)
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def create_backup(profile, target):
    profile, target = Path(profile).resolve(), Path(target).resolve()
    if target.is_relative_to(profile):
        raise ValueError('Guarda la copia fuera del perfil para evitar copias recursivas.')
    manifest = {'version': 1, 'scope': 'profile; external book folders not included', 'files': {}}
    with target.open('xb') as output, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        with tempfile.TemporaryDirectory(prefix='myl_backup_') as temporary:
            for path in sorted(profile.rglob('*')):
                relative = path.relative_to(profile).as_posix()
                if relative.split('/')[0] == 'ui_thumbnails' or relative == '.profile.lock':
                    continue
                if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                    raise ValueError(f'El perfil contiene un enlace; revisa la copia: {relative}')
                if not path.is_file():
                    continue
                if path.name.endswith(('-wal', '-shm')) and path.with_name(path.name.rsplit('-', 1)[0]).is_file():
                    continue
                if relative == MANIFEST:
                    raise ValueError('Nombre reservado en el perfil')
                stat = path.stat()
                with path.open('rb') as stream:
                    is_sqlite = stream.read(16) == b'SQLite format 3\x00'
                copy_source = path
                if is_sqlite:
                    copy_source = Path(temporary) / 'snapshot.sqlite3'
                    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
                        with closing(sqlite3.connect(copy_source)) as destination:
                            source.backup(destination)
                            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                                raise ValueError(f'Base de datos dañada: {relative}')
                with copy_source.open('rb') as source, archive.open(relative, 'w', force_zip64=True) as destination:
                    digest, size = _copy_and_hash(source, destination)
                after = path.stat()
                if not is_sqlite and (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError(f'El perfil cambió durante la copia: {relative}. Reintenta sin tareas activas.')
                manifest['files'][relative] = {'sha256': digest, 'size': size, 'mtime_ns': stat.st_mtime_ns,
                                               'sqlite': is_sqlite}
                if is_sqlite:
                    copy_source.unlink()
            archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False))
    return manifest


def restore_backup(source, destination):
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError('La restauración requiere una carpeta nueva o vacía. No se sobrescribirá el perfil actual.')
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or len(names) > 100_000 or sum(info.file_size for info in infos) > MAX_RESTORE_BYTES:
            raise ValueError('Archivo de recuperación excesivo o con entradas duplicadas')
        manifest_info = archive.getinfo(MANIFEST)
        if manifest_info.file_size > 32 * 1024 ** 2:
            raise ValueError('Manifiesto excesivo')
        manifest = json.loads(archive.read(MANIFEST))
        if manifest.get('version') != 1 or not isinstance(manifest.get('files'), dict):
            raise ValueError('Versión de copia no admitida')
        if set(names) != set(manifest['files']) | {MANIFEST}:
            raise ValueError('Las entradas no coinciden con el manifiesto')
        for name in manifest['files']:
            path = PurePosixPath(name)
            if path.is_absolute() or '\\' in name or ':' in name or '..' in path.parts or not path.parts:
                raise ValueError('Ruta no segura dentro de la copia')
            if not (destination / name).resolve().is_relative_to(destination):
                raise ValueError('La ruta sale de la carpeta de restauración')
        destination.mkdir(parents=True, exist_ok=True)
        for name, expected in manifest['files'].items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as incoming, target.open('xb') as output:
                digest, size = _copy_and_hash(incoming, output)
            if digest != expected['sha256'] or size != expected['size']:
                raise ValueError(f'Copia no íntegra: {name}. El perfil activo sigue intacto.')
            os.utime(target, ns=(expected['mtime_ns'], expected['mtime_ns']))
            if expected.get('sqlite'):
                with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as con:
                    if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError(f'Base restaurada no íntegra: {name}')
    return manifest
