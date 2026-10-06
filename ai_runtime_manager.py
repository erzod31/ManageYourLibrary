import json
import subprocess
import time
import urllib.request
from pathlib import Path

from ai_model_catalog import default_model_id, get_model_option, is_allowed_model
from ai_paths import ai_folder_status, model_path, runtime_server_path


DEFAULT_AI_PORT = 39241


def get_ai_status(config=None, root: Path | None = None):
    config = config or {}
    model_id = config.get("model_id") or default_model_id()
    if not is_allowed_model(model_id):
        model_id = default_model_id()
    status = ai_folder_status(
        root=root,
        model_id=model_id,
        configured_models_dir=config.get("models_dir", ""),
    )
    enabled = bool(config.get("enabled", False))
    status.update({
        "enabled": enabled,
        "model_id": model_id,
        "model_label": get_model_option(model_id).label,
        "port": int(config.get("port") or DEFAULT_AI_PORT),
    })
    if not enabled:
        status["state"] = "IA desactivada"
    elif not status["runtime_found"]:
        status["state"] = "Runtime llama.cpp no encontrado"
    elif not status["model_found"]:
        status["state"] = "Modelo no instalado"
    else:
        status["state"] = "Modelo instalado"
    return status


def can_use_ai(config=None, root: Path | None = None):
    status = get_ai_status(config, root=root)
    return bool(status["enabled"] and status["runtime_found"] and status["model_found"]), status


class LlamaCppServer:
    def __init__(self, config=None, root: Path | None = None):
        self.config = config or {}
        self.root = root
        self.process = None
        self.status = get_ai_status(self.config, root=self.root)

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.status['port']}"

    def is_ready(self):
        try:
            with urllib.request.urlopen(self.endpoint + "/health", timeout=1.5) as response:
                return response.status == 200
        except Exception:
            return False

    def start(self, timeout_seconds=20):
        usable, status = can_use_ai(self.config, root=self.root)
        self.status = status
        if not usable:
            return False, status["state"]
        if self.is_ready():
            return True, "IA local activa"

        server = runtime_server_path(self.root)
        model = model_path(status["model_id"], root=self.root, models_dir=status["models_dir"])
        cmd = [
            str(server),
            "-m",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(status["port"]),
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(server.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as exc:
            return False, f"Error al iniciar llama.cpp: {exc}"

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.is_ready():
                return True, "IA local activa"
            if self.process and self.process.poll() is not None:
                return False, "Error al iniciar llama.cpp"
            time.sleep(0.25)
        return False, "Error al iniciar llama.cpp"

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()


def llama_completion(endpoint, system_prompt, user_prompt, timeout=45):
    body = json.dumps(
        {
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "temperature": 0.0,
            "n_predict": 900,
            "stop": ["</s>"],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/completion",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8", errors="ignore"))
    return data.get("content", "")
