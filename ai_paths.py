import os
import sys
from pathlib import Path

from ai_model_catalog import default_model_id, get_model_option
from core.config_store import app_data_dir


AI_DIR_NAME = "ai"
RUNTIME_DIR_NAME = "runtime"
MODELS_DIR_NAME = "models"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_ai_dir(root: Path | None = None) -> Path:
    return (root or app_root()) / AI_DIR_NAME


def bundled_runtime_dir(root: Path | None = None) -> Path:
    return bundled_ai_dir(root) / RUNTIME_DIR_NAME


def bundled_models_dir(root: Path | None = None) -> Path:
    return bundled_ai_dir(root) / MODELS_DIR_NAME


def user_ai_dir() -> Path:
    return app_data_dir() / AI_DIR_NAME


def user_models_dir() -> Path:
    return user_ai_dir() / MODELS_DIR_NAME


def runtime_server_path(root: Path | None = None) -> Path:
    return bundled_runtime_dir(root) / "llama-server.exe"


def runtime_cli_path(root: Path | None = None) -> Path:
    return bundled_runtime_dir(root) / "llama-cli.exe"


def is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test_manageyourlibrary"
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
            handle.flush()
            os.fsync(handle.fileno())
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def preferred_models_dir(root: Path | None = None, configured: str = "") -> Path:
    if configured:
        return Path(configured)
    bundled = bundled_models_dir(root)
    if is_writable_directory(bundled):
        return bundled
    return user_models_dir()


def model_path(model_id: str | None = None, root: Path | None = None, models_dir: str | Path | None = None) -> Path:
    model_id = model_id or default_model_id()
    option = get_model_option(model_id)
    if option is None:
        option = get_model_option(default_model_id())
    base = Path(models_dir) if models_dir else preferred_models_dir(root)
    relative = Path(option.relative_model_path)
    if relative.parts and relative.parts[0] == MODELS_DIR_NAME:
        relative = Path(*relative.parts[1:])
    return base / relative


def ai_folder_status(root: Path | None = None, model_id: str | None = None, configured_models_dir: str = ""):
    server = runtime_server_path(root)
    cli = runtime_cli_path(root)
    models = preferred_models_dir(root, configured_models_dir)
    model = model_path(model_id, root=root, models_dir=models)
    return {
        "app_root": str(root or app_root()),
        "ai_dir": str(bundled_ai_dir(root)),
        "runtime_dir": str(bundled_runtime_dir(root)),
        "models_dir": str(models),
        "runtime_server": str(server),
        "runtime_cli": str(cli),
        "runtime_found": server.exists() or cli.exists(),
        "server_found": server.exists(),
        "cli_found": cli.exists(),
        "models_dir_writable": is_writable_directory(models),
        "model_path": str(model),
        "model_found": model.exists(),
    }
