import os
from datetime import datetime, timezone
from pathlib import Path

PERSISTENT_METADATA_FIELDS = {
    "titulo", "titulo_real", "autor", "isbn", "cover_url", "anio", "year",
    "editorial", "publisher", "idioma", "language", "serie", "series",
    "edicion", "edition", "tags", "collections", "favorite", "favorito", "is_favorite", "read_status",
    "provenance", "procedencia", "evidencias", "fuente", "confianza",
    "confianza_global", "manual_lock", "confirmed_correction",
}


def merge_persistent_metadata(fresh, previous=None, enriched=None):
    """Merge catalog metadata without weakening a confirmed human correction."""
    merged = dict(fresh or {})
    previous = dict(previous or {})
    enriched = dict(enriched or {})
    for key in PERSISTENT_METADATA_FIELDS:
        if key in previous:
            merged[key] = previous[key]
    if previous.get("manual_lock") or previous.get("confirmed_correction"):
        # Automated refreshes cannot overwrite confirmed human values.
        enriched = {
            key: value for key, value in enriched.items()
            if key not in {"titulo", "titulo_real", "autor", "isbn", "anio", "editorial", "idioma", "serie", "edicion"}
        }
    for key, value in enriched.items():
        if key in PERSISTENT_METADATA_FIELDS and value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _path_key(path):
    return os.path.normcase(os.path.abspath(str(path)))


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


def update_paths(index, paths, *, library_root, build_item, ignore_path=None, metadata_by_path=None):
    """Update only affected index rows while preserving every unrelated row."""
    index = dict(index or {})
    rows = {
        _path_key(item.get("ruta", "")): dict(item)
        for item in index.get("archivos", [])
        if item.get("ruta")
    }
    for raw_path in paths or []:
        if not raw_path:
            continue
        path = Path(raw_path)
        path_key = _path_key(path)
        previous = rows.pop(path_key, None)
        if not path.exists() or not path.is_file() or not _inside(path, library_root):
            continue
        if ignore_path and ignore_path(path):
            continue
        enrichment = (metadata_by_path or {}).get(path_key, {})
        fresh = build_item(path, path.name)
        same_content = bool(previous and previous.get("sha256")
                            and previous["sha256"] == fresh.get("sha256"))
        rows[path_key] = merge_persistent_metadata(fresh, previous if same_content else None, enrichment)

    index["creado"] = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    index["library"] = str(Path(library_root))
    index["archivos"] = sorted(
        rows.values(), key=lambda item: str(item.get("ruta", "")).casefold()
    )
    return index
