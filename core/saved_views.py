"""Strict saved-view storage: an unreadable file must not be silently replaced."""
import json
from pathlib import Path

from .index_store import IndexRecoveryError, guardar_json


def load_views(path: Path) -> dict[str, dict]:
    try:
        with Path(path).open(encoding='utf-8') as stream:
            value = json.load(stream)
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IndexRecoveryError('No se pueden leer las vistas guardadas. El archivo original se conserva.') from exc
    if not isinstance(value, dict) or any(not isinstance(item, dict) for item in value.values()):
        raise IndexRecoveryError('Formato de vistas incompatible. El archivo original se conserva.')
    return value


def save_view(path: Path, name: str, settings: dict) -> None:
    existing = load_views(path)
    existing[name] = settings
    guardar_json(path, existing)
