import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import index_store

APP_NAME = "ManageYourLibrary"
CONFIG_VERSION = "catalog_workspace_v2"
DEFAULT_OPERATION_CONFIG = {
    "ocr_max_pages": 12,
    "offline_mode": False,
    "theme": "system",
}


def default_start_dir() -> Path:
    if os.name == "nt":
        return Path("C:/")
    return Path.home()


def app_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / APP_NAME


def _updated_at() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _bounded_ocr_pages(value, fallback: int = 12) -> int:
    try:
        pages = int(value)
    except (TypeError, ValueError):
        pages = int(fallback)
    return max(1, min(200, pages))


def normalize_operation_config(candidate=None, previous=None) -> dict:
    previous = dict(previous or {})
    candidate = dict(candidate or {})
    fallback_pages = _bounded_ocr_pages(previous.get("ocr_max_pages", DEFAULT_OPERATION_CONFIG["ocr_max_pages"]))
    theme = str(candidate.get("theme", previous.get("theme", DEFAULT_OPERATION_CONFIG["theme"])) or "system").lower()
    if theme not in {"system", "light", "dark"}:
        theme = "system"
    return {
        "ocr_max_pages": _bounded_ocr_pages(candidate.get("ocr_max_pages", fallback_pages), fallback_pages),
        "offline_mode": bool(candidate.get("offline_mode", previous.get("offline_mode", False))),
        "theme": theme,
    }


def load_operation_config(config_path: Path) -> dict:
    config = index_store.cargar_json(config_path, {})
    return normalize_operation_config(config.get("operation", {}))


def save_library_config(config_path: Path, *, library: str, language: str) -> None:
    config = index_store.cargar_json(config_path, {})
    config.update(
        {
            "version": CONFIG_VERSION,
            "library": str(library or ""),
            "language": str(language or ""),
            "updated_at": _updated_at(),
        }
    )
    index_store.guardar_json(config_path, config)


def save_operation_config(
    config_path: Path,
    operation_config=None,
    *,
    library: str | None = None,
    language: str = "",
) -> dict:
    config = index_store.cargar_json(config_path, {})
    cleaned = normalize_operation_config(operation_config, config.get("operation", {}))
    config["operation"] = cleaned
    config["version"] = CONFIG_VERSION
    if library is not None:
        config["library"] = str(library)
    else:
        config.setdefault("library", "")
    config["language"] = str(language or "")
    config["updated_at"] = _updated_at()
    index_store.guardar_json(config_path, config)
    return cleaned
