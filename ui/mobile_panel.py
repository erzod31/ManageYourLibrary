"""Visible opt-in desktop controls for the Android companion."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk


class MobilePanel:
    def __init__(self, app):
        self.app = app
        self.service = None
        self.tailscale = None
        self.window = None
        self.stopping = False
        self.cancel_start = threading.Event()
        self.lifecycle_lock = threading.RLock()
        self.start_thread = None
        self._busy_token = None
        self._poll_id = None
        self._build()

    def _build(self):
        self.window = tk.Toplevel(self.app.root)
        self.window.title("Android · Tailscale")
        self.window.geometry("640x670")
        self.window.minsize(600, 650)
        self.window.configure(bg=self.app.tema_actual.get("bg", "#F7F3ED"))
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Tu biblioteca en Android", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(frame, text="El PC conserva la biblioteca y ejecuta Indra. Conecta ambos dispositivos a la misma red Tailscale.",
                  wraplength=540).pack(anchor="w", pady=(8, 14))
        self.status = tk.StringVar(value="Desactivado · no se aceptan conexiones")
        ttk.Label(frame, textvariable=self.status, wraplength=540).pack(anchor="w", pady=4)
        self.url = tk.StringVar()
        self.code = tk.StringVar()
        ttk.Label(frame, text="Dirección HTTPS del PC").pack(anchor="w", pady=(14, 3))
        ttk.Entry(frame, textvariable=self.url, state="readonly").pack(fill="x")
        ttk.Button(frame, text="Copiar dirección", command=lambda: self.copy(self.url.get())).pack(anchor="w", pady=4)
        ttk.Label(frame, text="Código de un solo uso · válido durante 2 minutos").pack(anchor="w", pady=(12, 3))
        ttk.Entry(frame, textvariable=self.code, state="readonly", font=("Consolas", 18)).pack(fill="x")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=14)
        self.start_button = ttk.Button(controls, text="Activar acceso", command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(controls, text="Desactivar", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        self.new_button = ttk.Button(frame, text="Generar otro código", command=self.new_code, state="disabled")
        self.new_button.pack(anchor="w", pady=4)
        ttk.Button(frame, text="Desvincular todos los móviles", command=self.revoke).pack(anchor="w", pady=4)
        ttk.Button(frame, text="Copiar enlace de descarga del APK", command=self.copy_download).pack(anchor="w", pady=4)
        self.devices = tk.StringVar(value="0 dispositivos vinculados")
        ttk.Label(frame, textvariable=self.devices, wraplength=540).pack(anchor="w", pady=(12, 0))

    def show(self):
        if self.window is None or not self.window.winfo_exists():
            self._build()
        self.window.deiconify()
        self.window.lift()

    def hide(self):
        self.stop()
        self.window.withdraw()

    def copy(self, text):
        if text:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(text)

    def copy_download(self):
        if self.service and self.url.get():
            self.copy(self.url.get() + "/api/v1/client.apk")
            self.status.set("Enlace copiado. Ábrelo en el móvil con Tailscale conectado.")
        else:
            messagebox.showinfo("Android", "Activa el acceso para obtener el enlace privado al APK.", parent=self.window)

    def _remote_busy(self, token):
        ready = threading.Event()
        allowed = []
        guard = threading.Lock()
        expired = False
        def update():
            nonlocal expired
            with guard:
                if expired or (token is not None and self.cancel_start.is_set()):
                    ready.set()
                    return
                if token is not None:
                    if self.app.trabajando:
                        allowed.append(False)
                    else:
                        self._busy_token = token
                        self.app.cancel_token = token
                        self.app.bloquear(True)
                        self.app.estado("Android: procesando una solicitud del móvil…")
                        allowed.append(True)
                else:
                    if self._busy_token is self.app.cancel_token:
                        self.app.bloquear(False)
                        self.app.estado("Android: solicitud terminada")
                    self._busy_token = None
                    allowed.append(True)
                ready.set()
        self.app._encolar_ui(update)
        if token is None:
            return True
        if not ready.wait(timeout=5):
            with guard:
                if not ready.is_set():
                    expired = True
                    return False
        return bool(allowed and allowed[0])

    def _changed(self):
        def refresh():
            import library_core as core
            self.app.indice = core.cargar_indice()
            self.app.actualizar_label_indice()
        self.app._encolar_ui(refresh)

    def start(self):
        if self.service or self.stopping or (self.start_thread and self.start_thread.is_alive()):
            return
        self.cancel_start.clear()
        self.start_button.configure(state="disabled")
        self.status.set("Preparando acceso privado…")
        def task():
            from core.mobile_access import DeviceAccess, MobileService
            from core.mobile_library import DesktopLibraryAdapter
            from core.mobile_tailscale import TailscaleAccess
            import library_core as core
            service = tailscale = None
            try:
                access = DeviceAccess(core.APP_DATA / "mobile/devices.json")
                service = MobileService(access, DesktopLibraryAdapter(core, busy=self._remote_busy, changed=self._changed))
                tailscale = TailscaleAccess()
                with self.lifecycle_lock:
                    if self.cancel_start.is_set():
                        service.stop()
                        return
                    self.service, self.tailscale = service, tailscale
                    port = service.start()
                url = tailscale.start(port)
                if self.cancel_start.is_set():
                    raise RuntimeError("Activación cancelada")
                code = access.new_code()
                self.app._encolar_ui(self._started, url, code)
            except Exception as exc:
                if tailscale:
                    tailscale.stop()
                if service:
                    service.stop()
                with self.lifecycle_lock:
                    if self.service is service:
                        self.service, self.tailscale = None, None
                if not self.cancel_start.is_set():
                    self.app._encolar_ui(self._failed, str(exc))
        self.start_thread = threading.Thread(target=task, daemon=True, name="StartMobileAccess")
        self.start_thread.start()

    def _started(self, url, code):
        if self.cancel_start.is_set() or not self.service:
            return
        self.url.set(url)
        self.code.set(code)
        self.status.set("Activo · solo tu red Tailscale y móviles vinculados")
        self.stop_button.configure(state="normal")
        self.new_button.configure(state="normal")
        self.devices.set(f"{len(self.service.access.public_devices())} dispositivos vinculados")
        self._poll()

    def _poll(self):
        if self.service and self.window and self.window.winfo_exists():
            self.devices.set(f"{len(self.service.access.public_devices())} dispositivos vinculados")
            if self.service.access.expires <= __import__("time").time():
                self.code.set("Caducado o utilizado")
            self._poll_id = self.app.root.after(1000, self._poll)

    def _failed(self, error):
        self.status.set("Desactivado · " + error)
        self.start_button.configure(state="normal")

    def new_code(self):
        if self.service:
            self.code.set(self.service.access.new_code())

    def revoke(self):
        from core.mobile_access import DeviceAccess
        import library_core as core
        if not messagebox.askyesno("Desvincular", "¿Revocar el acceso de todos los móviles? La biblioteca se conserva.", parent=self.window):
            return
        if self.service:
            threading.Thread(target=self.service.adapter.jobs.cancel_all, daemon=True).start()
            self.service.access.revoke_all()
            self.new_code()
        else:
            DeviceAccess(core.APP_DATA / "mobile/devices.json").revoke_all()
        self.devices.set("0 dispositivos vinculados")

    def stop(self):
        if self.stopping:
            return
        self.stopping = True
        self.cancel_start.set()
        if self._poll_id:
            self.app.root.after_cancel(self._poll_id)
            self._poll_id = None
        self.status.set("Desactivando y conservando las tareas pendientes…")
        self.stop_button.configure(state="disabled")
        self.new_button.configure(state="disabled")
        def task():
            self.close()
            self.app._encolar_ui(self._stopped)
        threading.Thread(target=task, daemon=True, name="StopMobileAccess").start()

    def _stopped(self):
        self.stopping = False
        self.url.set("")
        self.code.set("")
        self.status.set("Desactivado · no se aceptan conexiones")
        self.start_button.configure(state="normal")

    def close(self):
        self.cancel_start.set()
        with self.lifecycle_lock:
            service, self.service = self.service, None
            tailscale, self.tailscale = self.tailscale, None
        if tailscale:
            tailscale.stop()
        if service:
            service.stop()
