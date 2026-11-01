"""Own a dedicated foreground Serve endpoint; never reset another app's routes."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path


class TailscaleAccess:
    def __init__(self, *, https_port=10443, executable=None):
        self.https_port = https_port
        self.executable = executable or shutil.which("tailscale")
        if not self.executable and os.name == "nt":
            candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tailscale/tailscale.exe"
            if candidate.is_file():
                self.executable = str(candidate)
        self.process = None
        self.target = ""
        self.url = ""
        self.lines = []
        self.closing = threading.Event()
        self.lock = threading.RLock()

    def _run(self, *arguments):
        if not self.executable:
            raise RuntimeError("Instala Tailscale y conecta el PC y el móvil a tu misma red privada.")
        result = subprocess.run([self.executable, *arguments], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise RuntimeError("Tailscale no está disponible o no permite esta operación. Comprueba su conexión en el PC.")
        return result.stdout

    def start(self, local_port):
        if self.closing.is_set():
            raise RuntimeError("El acceso móvil se ha cancelado.")
        if self.process is not None:
            raise RuntimeError("Tailscale ya está activo para esta ventana.")
        state = json.loads(self._run("status", "--json"))
        host = str(state.get("Self", {}).get("DNSName", "")).rstrip(".")
        if state.get("BackendState") != "Running" or not host.endswith(".ts.net"):
            raise RuntimeError("Conecta Tailscale en el PC y habilita MagicDNS/HTTPS en tu red privada.")
        config = json.loads(self._run("serve", "status", "--json"))
        if any(str(self.https_port) in row.get("TCP", {}) for row in self._configs(config)):
            raise RuntimeError(f"El puerto HTTPS {self.https_port} ya pertenece a otro servicio. No se ha modificado.")
        self.target = f"http://127.0.0.1:{local_port}"
        self.url = f"https://{host}:{self.https_port}"
        with self.lock:
            if self.closing.is_set():
                raise RuntimeError("El acceso móvil se ha cancelado.")
            process = subprocess.Popen([self.executable, "serve", f"--https={self.https_port}", self.target],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.process = process
        def drain():
            for line in process.stdout:
                self.lines.append(line.strip())
                del self.lines[:-12]
        threading.Thread(target=drain, daemon=True, name="TailscaleMobileOutput").start()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.closing.is_set() or process.poll() is not None:
                self.stop()
                raise RuntimeError("Tailscale Serve no pudo iniciarse. Revisa HTTPS en la consola de Tailscale.")
            config = json.loads(self._run("serve", "status", "--json"))
            if self._owns(config):
                return self.url
            time.sleep(0.15)
        self.stop()
        raise RuntimeError("Tailscale no confirmó la conexión. No se abrió ningún puerto público.")

    @staticmethod
    def _configs(config):
        yield config
        yield from config.get("Foreground", {}).values()

    def _owns_root(self, config):
        host_port = self.url.removeprefix("https://")
        handlers = config.get("Web", {}).get(host_port, {}).get("Handlers", {})
        return (config.get("TCP", {}).get(str(self.https_port), {}).get("HTTPS") is True and
                len(handlers) == 1 and handlers.get("/", {}).get("Proxy") == self.target)

    def _owns(self, config):
        return any(self._owns_root(row) for row in self._configs(config))

    def stop(self):
        self.closing.set()
        with self.lock:
            process, self.process = self.process, None
        if process:
            # Remove only the exact endpoint we own. No `serve reset`, Funnel,
            # daemon shutdown, firewall rule or unrelated endpoint is touched.
            try:
                config = json.loads(self._run("serve", "status", "--json"))
                # Current Serve versions keep foreground endpoints in their
                # IPC session. Closing our child removes only that session.
                # The legacy explicit-off path applies only to an exact root
                # endpoint; it must never delete another foreground session.
                if self._owns_root(config):
                    self._run("serve", f"--https={self.https_port}", "off")
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

