"""User-initiated update UI shared by the native desktop builds."""
from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from core.app_updates import DEFAULT_REPOSITORY, UpdateCancelled, UpdateChannel, process_platform, repository_name
from core.update_apply import UpdateCoordinator


def installed_windows(executable):
    if os.name != "nt":
        return False
    import winreg
    from core.app_updates import APP_ID
    key_name = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_ID + "_is1"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (0, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key_name, 0, winreg.KEY_READ | view) as key:
                    location, _ = winreg.QueryValueEx(key, "InstallLocation")
                if Path(location).resolve() == Path(executable).resolve().parent:
                    return True
            except OSError:
                pass
    return False


class UpdatePanel:
    def __init__(self, app):
        import library_core as core
        import main
        self.app, self.core = app, core
        self.version = main._version()
        self.cancelled = threading.Event()
        self.busy = False
        self.claimed = False
        self.offer = self.plan = None
        config = core._index_store.cargar_json(core.CONFIG_JSON, {})
        self.repository = str(config.get("updates", {}).get("repository", DEFAULT_REPOSITORY))
        self.target = process_platform()
        executable = Path(sys.executable).resolve()
        root = executable.parent
        if self.target.startswith("windows") and installed_windows(executable):
            self.target = "windows-installer-x64"
        elif self.target.startswith("macos"):
            root = executable.parents[2]
        self.coordinator = UpdateCoordinator(core.APP_DATA / "updates", self.version, self.target, root,
            protected=[core.APP_DATA, *([core.FINAL] if core.biblioteca_configurada() else [])])
        self.window = tk.Toplevel(app.root)
        self.window.title("Actualizar Manage Your Library")
        self.window.geometry("640x560")
        self.window.minsize(600, 520)
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        self.window.configure(bg=app.tema_actual.get("bg", "#F7F3ED"))
        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Actualizaciones de la aplicación", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.current = ttk.Label(frame, text=f"Versión actual: {self.version} · {self.target}")
        self.current.pack(anchor="w", pady=(10, 14))
        ttk.Label(frame, text="Canal GitHub · propietario/repositorio").pack(anchor="w")
        self.channel_value = tk.StringVar(value=self.repository)
        ttk.Entry(frame, textvariable=self.channel_value).pack(fill="x", pady=5)
        ttk.Button(frame, text="Guardar canal", command=self.save_channel).pack(anchor="w")
        self.status = tk.StringVar(value="Pulsa Buscar. No se comprueba ni descarga nada al iniciar.")
        ttk.Label(frame, textvariable=self.status, wraplength=570).pack(anchor="w", pady=(16, 10))
        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.pack(fill="x", pady=6)
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=10)
        self.check_button = ttk.Button(controls, text="Buscar actualización", command=self.check)
        self.check_button.pack(side="left", padx=(0, 6))
        self.download_button = ttk.Button(controls, text="Descargar y verificar", command=self.download, state="disabled")
        self.download_button.pack(side="left", padx=6)
        self.apply_button = ttk.Button(controls, text="Instalar y reabrir", command=self.install, state="disabled")
        self.apply_button.pack(side="left", padx=6)
        ttk.Button(frame, text="Cancelar descarga/preparación", command=self.cancelled.set).pack(anchor="w", pady=4)
        ttk.Label(frame, text="Se conserva la biblioteca y el perfil. Windows/Android/macOS mantienen sus confirmaciones de seguridad. Las versiones antiguas necesitan una primera instalación manual.", wraplength=570).pack(anchor="w", pady=12)

    def show(self):
        self.window.deiconify()
        self.window.lift()

    def hide(self):
        self.cancelled.set()
        self.window.withdraw()

    def close(self):
        self.cancelled.set()

    def save_channel(self):
        if self.busy:
            return
        try:
            value = repository_name(self.channel_value.get().strip())
            if value != self.repository and not messagebox.askyesno("Confiar en canal", f"¿Confiar las actualizaciones al repositorio {value}? Su propietario podrá proporcionar ejecutables.", parent=self.window):
                return
            config = self.core._index_store.cargar_json(self.core.CONFIG_JSON, {})
            config["updates"] = {"repository": value}
            self.core._index_store.guardar_json(self.core.CONFIG_JSON, config)
            self.repository = value
            self.offer = self.plan = None
            self.download_button.configure(state="disabled")
            self.apply_button.configure(state="disabled")
            self.status.set("Canal guardado. Busca de nuevo para comprobar su versión.")
        except Exception as exc:
            self.status.set(str(exc))

    def task(self, operation, complete):
        if self.busy:
            return
        self.busy = True
        self.cancelled.clear()
        self.check_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        def run():
            try:
                value = operation()
                self.app._encolar_ui(self.finished, complete, value, None)
            except Exception as exc:
                self.app._encolar_ui(self.finished, complete, None, exc)
        threading.Thread(target=run, daemon=True, name="ApplicationUpdate").start()

    def finished(self, complete, value, error):
        self.busy = False
        self.check_button.configure(state="normal")
        if self.claimed:
            self.app.bloquear(False)
            self.claimed = False
        if error:
            self.status.set(str(error))
        else:
            complete(value)
        try:
            self.download_button.configure(state="normal" if self.offer and getattr(sys, "frozen", False) else "disabled")
            self.apply_button.configure(state="normal" if self.plan and getattr(sys, "frozen", False) else "disabled")
        except tk.TclError:
            pass  # The confirmed handoff can close the entire Tk application.

    def check(self):
        self.offer = self.plan = None
        self.status.set("Consultando las publicaciones del canal…")
        channel = UpdateChannel(self.repository)
        def done(value):
            self.offer = value["offer"]
            if self.offer:
                self.status.set(f"Disponible: {self.offer.version} · {self.offer.size / 1024**2:.1f} MiB. Se verificará SHA-256 y la identidad antes de instalar.")
            elif value["status"] == "no_package":
                self.status.set("El canal no ofrece un paquete para esta plataforma. No se cambiará la aplicación.")
            else:
                self.status.set(f"No hay una versión más reciente. Actual: {self.version}; publicada para esta plataforma: {value['available']}.")
        self.task(lambda: channel.check(self.version, self.target), done)

    def download(self):
        if not self.offer:
            return
        offer = self.offer
        channel = UpdateChannel(self.repository)
        session = self.coordinator.new_session()
        self.status.set("Descargando un paquete de la aplicación; la biblioteca no se envía.")
        def work():
            package = channel.download(offer, self.version, self.target, session, cancelled=self.cancelled,
                progress=lambda n, total: self.app._encolar_ui(lambda: self.progress.configure(value=100*n/total)))
            if self.cancelled.is_set():
                raise UpdateCancelled("Preparación cancelada.")
            return self.coordinator.prepare(offer, package)
        def done(path):
            self.plan = path
            plan = json.loads(path.read_text(encoding="utf-8"))
            signature = plan["signature"]["status"]
            self.status.set(f"{offer.version} verificada · firma: {signature}. Confirma Instalar. " +
                ("Modo código fuente: instala primero un paquete distribuido." if not getattr(sys, "frozen", False) else "Se cerrará esta instancia y se ofrecerá reabrir la nueva versión."))
        self.task(work, done)

    def install(self):
        if self.busy or not self.plan or not getattr(sys, "frozen", False):
            return
        if self.app.trabajando:
            self.status.set("Espera a que termine el trabajo del PC antes de actualizar.")
            return
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        description = f"Actualizar {self.version} → {plan['offer']['version']} y cerrar esta instancia.\n\nLa biblioteca y configuración se conservan."
        if plan["signature"]["status"] == "NotSigned":
            description += "\n\nEl paquete no tiene firma Authenticode. Su origen GitHub, versión y SHA-256 han sido verificados. Windows conservará sus avisos."
        if not messagebox.askyesno("Confirmar actualización", description, parent=self.window):
            return
        self.app.bloquear(True)
        self.claimed = True
        self.status.set("Verificando de nuevo y solicitando instalación…")
        def handoff():
            if self.cancelled.is_set():
                raise UpdateCancelled("Instalación cancelada antes del lanzador.")
            return self.coordinator.handoff(self.plan, confirmed=True, cancelled=self.cancelled)
        self.task(handoff, lambda _value: self.app.cerrar_aplicacion())
