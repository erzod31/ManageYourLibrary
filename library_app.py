import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import library_core as core
from core.cancellation import CancellationToken
from core.contracts import BatchProgressEvent
from library_core import (
    APP_DATA,
    DEFAULT_START_DIR,
    FINAL,
    IDIOMA_ACTUAL,
    LANGUAGE_CODES_BY_NAME,
    LANGUAGE_NAMES,
    biblioteca_configurada,
    buscar_dobles_biblioteca,
    cargar_indice,
    crear_o_actualizar_indice,
    descartar_archivo_seguro,
    es_libro,
    escribir_historial,
    guardar_config_biblioteca,
    guardar_indice,
    ignorar_por_carpeta,
    item_indice_desde_ruta,
    mark_action_undone,
    mark_undo_item_restored,
    mover_a_final,
    mover_a_revisar_nuevamente,
    normalizar_texto,
    nuevo_batch_id,
    obtener_nombre_web,
    obtener_ultima_accion_undo,
    recuperar_transacciones_archivo_pendientes,
    reemplazar_archivo_transaccional,
    registrar_undo,
    renombrar_en_sitio_seguro,
    restaurar_accion_undo,
    tr,
    verificar_libro,
)
from rounded_widgets import RoundedButton, RoundedCard
from ui.workspace import build_workspace

OCR_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return Path(base_path) / relative_path


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(tr("window_title"))
        self.aplicar_icono_ventana()
        self.root.geometry("1080x840")
        self.root.minsize(760, 560)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar_aplicacion)
        self.ui_events = core.UiEventQueue()
        self.indice = cargar_indice()
        self.trabajando = False
        self.cancel_token = CancellationToken()
        self.worker_threads = set()
        self.worker_threads_lock = threading.RLock()
        operation_config = core.cargar_configuracion_operacion()
        self._aplicar_configuracion_operacion(operation_config)
        self.theme_preference = operation_config.get("theme", "system")
        self.modo_oscuro = self._tema_sistema_oscuro() if self.theme_preference == "system" else self.theme_preference == "dark"
        self.theme_widgets = []
        self.crear_interfaz()
        self.actualizar_label_indice()
        self.actualizar_estado_botones()
        self.root.after(50, self._drenar_eventos_ui)
        self.root.after(250, self.revisar_transacciones_archivo_pendientes)
        self.root.after(400, self.revisar_planes_pendientes)
        self.root.after(650, self.sincronizar_catalogo_en_segundo_plano)
        if biblioteca_configurada():
            self.root.after(500, self.actualizar_indice_automatico)
        else:
            self.root.after(200, lambda: self.estado(tr("first_state")))

    def _encolar_ui(self, callback, *args, **kwargs):
        self.ui_events.post(callback, *args, **kwargs)

    def _drenar_eventos_ui(self):
        try:
            # Give mouse/keyboard/paint events a turn even during cover bursts.
            self.ui_events.drain(time_budget_ms=8)
            self.root.after(16 if not self.ui_events.empty() else 32, self._drenar_eventos_ui)
        except tk.TclError:
            pass

    def _evento_progreso_lote(self, event: BatchProgressEvent) -> None:
        key = "pipeline_ocr_batch_status" if event["phase"] == "ocr" else "pipeline_fast_batch_status"
        self._encolar_ui(
            self.estado,
            tr(
                key,
                done=event["completed"],
                total=event["total"],
                name=Path(event["path"]).name,
            ),
        )

    def _precalcular_metadatos(self, libros, incluir_ocr=False, solo_analizar=False):
        operation_config = core.cargar_configuracion_operacion()
        self._aplicar_configuracion_operacion(operation_config)
        analisis_rapidos = core.analizar_archivos_rapido_en_paralelo(
            libros,
            event_callback=self._evento_progreso_lote,
            solo_analizar=solo_analizar,
            cancellation=self.cancel_token,
        )
        metadatos = {
            core.clave_ruta_resuelta(resultado["original_path"]): resultado["identity_result"]
            for resultado in analisis_rapidos
            if resultado.get("status") == core.FAST_OK and resultado.get("identity_result")
        }
        if incluir_ocr:
            for resultado in core.procesar_cola_ocr_diferido(
                analisis_rapidos,
                event_callback=self._evento_progreso_lote,
                solo_analizar=solo_analizar,
                cancellation=self.cancel_token,
                max_paginas_ocr=operation_config["ocr_max_pages"],
            ):
                if resultado.get("identity_result"):
                    metadatos[core.clave_ruta_resuelta(resultado["original_path"])] = resultado["identity_result"]
        return metadatos

    def _aplicar_configuracion_operacion(self, config):
        if config.get("offline_mode"):
            os.environ["MANAGE_YOUR_LIBRARY_OFFLINE"] = "1"
        else:
            os.environ.pop("MANAGE_YOUR_LIBRARY_OFFLINE", None)

    def _registrar(self, widget, rol):
        self.theme_widgets.append((widget, rol))
        return widget

    def cerrar_aplicacion(self):
        self.cancel_token.cancel()
        try:
            workspace = getattr(self, "workspace", None)
            if workspace is not None:
                workspace.shutdown()
        except Exception:
            pass
        with self.worker_threads_lock:
            workers = list(self.worker_threads)
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=1.5)
        try:
            from ocr_engine import limpiar_cache_ocr

            limpiar_cache_ocr()
        except Exception:
            pass

        try:
            self._cerrar_popup_idioma()
            self._cerrar_ventana_metadatos()
        except Exception:
            pass

        self.root.destroy()

    def _start_worker(self, target):
        self.cancel_token = CancellationToken()

        def wrapped():
            try:
                target()
            finally:
                with self.worker_threads_lock:
                    self.worker_threads.discard(threading.current_thread())

        worker = threading.Thread(target=wrapped, daemon=True)
        with self.worker_threads_lock:
            self.worker_threads.add(worker)
        worker.start()
        return worker

    def sincronizar_catalogo_en_segundo_plano(self):
        """Upgrade the legacy index into the richer catalog without blocking UI."""
        snapshot = {**(self.indice or {}), "archivos": [dict(row) for row in (self.indice or {}).get("archivos", [])]}

        def task():
            try:
                core.sincronizar_catalogo(snapshot)
            except Exception as exc:
                self._encolar_ui(self.escribir, f"Catálogo: no se pudo sincronizar: {exc}\n")
            finally:
                with self.worker_threads_lock:
                    self.worker_threads.discard(threading.current_thread())

        worker = threading.Thread(target=task, daemon=True, name="catalog-sync")
        with self.worker_threads_lock:
            self.worker_threads.add(worker)
        worker.start()

    def cancelar_operacion(self):
        if self.trabajando:
            self.cancel_token.cancel()
            self.estado("Cancelando de forma segura…")

    def revisar_transacciones_archivo_pendientes(self):
        try:
            pendientes = recuperar_transacciones_archivo_pendientes()
        except Exception:
            pendientes = []
        if pendientes:
            self.escribir(tr("file_transactions_recovered_log", count=len(pendientes)))

    def aplicar_icono_ventana(self):
        try:
            icon_path = resource_path("app_icon.ico")
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass

    def revisar_planes_pendientes(self):
        if self.trabajando:
            return
        try:
            planes = core.operation_plan_store().list_resumable()
        except Exception as exc:
            self.escribir(f"No se pudieron revisar los planes pendientes: {exc}\n")
            return
        if not planes:
            return
        plan = planes[0]
        pendientes = [
            item for item in plan["items"]
            if item["state"] in {"pending", "failed", "running"} and Path(item["source"]).exists()
        ]
        if not pendientes:
            return
        if messagebox.askyesno(
            "Plan pendiente",
            f"Hay una operación interrumpida con {len(pendientes)} archivos pendientes.\n\n¿Reanudarla ahora?",
        ):
            self.agregar_libros(
                rutas=[item["source"] for item in pendientes],
                plan_existente=plan,
            )

    def alternar_tema(self):
        try:
            if hasattr(self, "popup_idioma") and self.popup_idioma is not None:
                self.popup_idioma.destroy()
                self.popup_idioma = None
        except Exception:
            self.popup_idioma = None

        self.modo_oscuro = not self.modo_oscuro
        self.theme_preference = "dark" if self.modo_oscuro else "light"
        config = core.cargar_configuracion_operacion()
        config["theme"] = self.theme_preference
        core.guardar_configuracion_operacion(config)
        self.aplicar_tema()

    @staticmethod
    def _tema_sistema_oscuro():
        if os.name != "nt":
            return False
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except Exception:
            return False

    def establecer_preferencia_tema(self, preference):
        preference = str(preference or "system").lower()
        if preference not in {"system", "light", "dark"}:
            preference = "system"
        self.theme_preference = preference
        self.modo_oscuro = self._tema_sistema_oscuro() if preference == "system" else preference == "dark"
        self.aplicar_tema()

    def aplicar_tema(self):
        claro = {
            "bg": "#faf8f4",
            "card": "#fffdf9",
            "border": "#ded8d0",
            "text": "#2d2a27",
            "muted": "#706a64",
            "log_bg": "#f6f2ec",
            "entry_bg": "#fffdf9",
            "button_bg": "#fffdf9",
            "button_active": "#eee6df",
            "button_disabled": "#f1ede8",
            "primary_bg": "#a9573e",
            "primary_active": "#8f4935",
            "primary_text": "#ffffff",
            "quiet_bg": "#f0ece7",
            "quiet_active": "#e8ded6",
            "disabled_text": "#aaa19a",
            "credits": "#7b736c",
            "accent": "#a9573e",
            "success": "#4f8a72",
            "progress": "#a9573e",
        }
        oscuro = {
            "bg": "#1f1b18",
            "card": "#2a2420",
            "border": "#493e37",
            "text": "#f4eee7",
            "muted": "#b8ada3",
            "log_bg": "#181411",
            "entry_bg": "#241f1b",
            "button_bg": "#2a2420",
            "button_active": "#3b312b",
            "button_disabled": "#2b2622",
            "primary_bg": "#c9785b",
            "primary_active": "#b5654b",
            "primary_text": "#1d1612",
            "quiet_bg": "#2e2824",
            "quiet_active": "#40362f",
            "disabled_text": "#756b64",
            "credits": "#aa9d93",
            "accent": "#c9785b",
            "success": "#6faa8b",
            "progress": "#c9785b",
        }

        self.tema_actual = oscuro if self.modo_oscuro else claro
        c = self.tema_actual

        try:
            self.root.configure(bg=c["bg"])
        except Exception:
            pass

        for widget, rol in self.theme_widgets:
            try:
                if rol == "bg":
                    widget.configure(bg=c["bg"])
                elif rol == "rounded_card":
                    widget.set_theme(c["bg"], c["card"], c["border"])
                elif rol == "rounded_entry":
                    widget.set_theme(c["card"], c["entry_bg"], c["border"])
                elif rol == "rounded_log":
                    widget.set_theme(c["card"], c["log_bg"], c["border"])
                elif rol == "card_plain":
                    widget.configure(bg=c["card"])
                elif rol == "title":
                    widget.configure(bg=c["bg"], fg=c["text"])
                elif rol == "subtitle":
                    widget.configure(bg=c["bg"], fg=c["muted"])
                elif rol == "card_title":
                    widget.configure(bg=c["card"], fg=c["text"])
                elif rol == "card_text":
                    widget.configure(bg=c["card"], fg=c["muted"])
                elif rol == "status_eta":
                    widget.configure(bg=c["card"], fg=c["text"])
                elif rol == "card_bold":
                    widget.configure(bg=c["card"], fg=c["text"])
                elif rol == "entry":
                    widget.configure(bg=c["entry_bg"], fg=c["text"], insertbackground=c["text"])
                elif rol == "log":
                    widget.configure(bg=c["log_bg"], fg=c["text"], insertbackground=c["text"])
                elif rol == "rounded_button":
                    widget.set_theme(c["button_bg"], c["text"], c["border"], c["button_active"], c["button_disabled"], c["disabled_text"])
                elif rol == "rounded_button_primary":
                    widget.set_theme(c["primary_bg"], c["primary_text"], c["primary_bg"], c["primary_active"], c["button_disabled"], c["disabled_text"])
                elif rol == "rounded_button_quiet":
                    widget.set_theme(c["quiet_bg"], c["text"], c["border"], c["quiet_active"], c["button_disabled"], c["disabled_text"])
                elif rol == "credits":
                    widget.configure(bg=c["bg"], fg=c["credits"])
            except Exception:
                pass

        try:
            if hasattr(self, "main_canvas"):
                self.main_canvas.configure(bg=c["bg"])
        except Exception:
            pass

        try:
            if self.modo_oscuro:
                self.btn_tema.configure(text=tr("light_mode"))
            else:
                self.btn_tema.configure(text=tr("dark_mode"))
        except Exception:
            pass

        try:
            self.style.configure(
                "Visual.Horizontal.TProgressbar",
                troughcolor=c["quiet_bg"],
                background=c["progress"],
                bordercolor=c["border"],
                lightcolor=c["progress"],
                darkcolor=c["progress"]
            )
            self.style.configure(
                "Vertical.TScrollbar",
                troughcolor=c["bg"],
                background=c["border"],
                arrowcolor=c["muted"],
                bordercolor=c["bg"],
                lightcolor=c["border"],
                darkcolor=c["border"]
            )
        except Exception:
            pass

        workspace = getattr(self, "workspace", None)
        if workspace is not None:
            workspace.apply_theme(c)

    def crear_interfaz(self):
        return build_workspace(self)

    def _es_descendiente_de(self, widget, posible_padre):
        try:
            actual = widget
            while actual is not None:
                if actual is posible_padre:
                    return True
                actual = actual.master
        except Exception:
            pass
        return False

    def _widget_existe(self, widget):
        try:
            return widget is not None and bool(widget.winfo_exists())
        except Exception:
            return False

    def _cerrar_popups_click_externo(self, event=None):
        widget = getattr(event, "widget", None)

        try:
            if self._widget_existe(getattr(self, "popup_idioma", None)):
                if not self._es_descendiente_de(widget, self.popup_idioma) and not self._es_descendiente_de(widget, self.btn_idioma):
                    self._cerrar_popup_idioma()
        except Exception:
            pass

        try:
            ventana = getattr(self, "ventana_metadatos", None)
            if (
                self._widget_existe(ventana)
                and not getattr(self, "_ignorar_click_externo_metadatos", False)
                and not self._es_descendiente_de(widget, ventana)
            ):
                self._cerrar_ventana_metadatos()
        except Exception:
            pass

    def _posicion_popup_idioma(self):
        if not hasattr(self, "popup_idioma") or self.popup_idioma is None:
            return

        try:
            if not self.popup_idioma.winfo_exists():
                self.popup_idioma = None
                return

            ancho = getattr(self, "popup_idioma_ancho", max(170, self.btn_idioma.winfo_width()))
            alto = getattr(self, "popup_idioma_alto", 190)

            x = self.btn_idioma.winfo_rootx()
            y = self.btn_idioma.winfo_rooty() + self.btn_idioma.winfo_height() + 4

            self.popup_idioma.geometry(f"{ancho}x{alto}+{x}+{y}")
        except Exception:
            pass

    def _seguir_popup_idioma(self, event=None):
        if event is not None and event.widget is not self.root:
            return

        if hasattr(self, "popup_idioma") and self.popup_idioma is not None:
            self.root.after_idle(self._posicion_popup_idioma)

    def _cerrar_popup_idioma(self, event=None):
        try:
            if hasattr(self, "popup_idioma") and self.popup_idioma is not None:
                if self.popup_idioma.winfo_exists():
                    self.popup_idioma.destroy()
        except Exception:
            pass
        self.popup_idioma = None

    def _cerrar_ventana_metadatos(self, event=None):
        try:
            ventana = getattr(self, "ventana_metadatos", None)
            if self._widget_existe(ventana):
                ventana.destroy()
        except Exception:
            pass
        self.ventana_metadatos = None

    def abrir_menu_idioma(self):
        if hasattr(self, "popup_idioma") and self.popup_idioma is not None:
            try:
                if self.popup_idioma.winfo_exists():
                    self._cerrar_popup_idioma()
                    return
            except Exception:
                self.popup_idioma = None

        self.popup_idioma = tk.Toplevel(self.root)
        self.popup_idioma.overrideredirect(True)
        self.popup_idioma.transient(self.root)

        transparente = "#ff00ff"
        try:
            self.popup_idioma.configure(bg=transparente)
            self.popup_idioma.wm_attributes("-transparentcolor", transparente)
        except Exception:
            transparente = self.tema_actual.get("bg", "#f3f4f6")
            self.popup_idioma.configure(bg=transparente)

        ancho = max(170, self.btn_idioma.winfo_width())
        alto = 0

        self.popup_idioma_ancho = ancho
        self.popup_idioma_alto = 10
        self._posicion_popup_idioma()

        card = RoundedCard(
            self.popup_idioma,
            radius=16,
            padding=6,
            bg_outer=transparente,
            bg_inner=self.tema_actual.get("card", "#ffffff"),
            border=self.tema_actual.get("border", "#e5e7eb"),
            min_height=1,
            auto_height=True
        )
        card.pack(fill="both", expand=True)

        self.botones_idioma_popup = []
        for codigo, nombre in LANGUAGE_NAMES.items():
            texto = f"✓ {nombre}" if codigo == IDIOMA_ACTUAL else f"  {nombre}"

            btn = RoundedButton(
                card.inner,
                text=texto,
                command=lambda c=codigo: self.seleccionar_idioma(c),
                width=ancho - 14,
                height=38,
                radius=13,
                font=("Segoe UI", 10)
            )
            btn.set_theme(
                self.tema_actual.get("button_bg", "#ffffff"),
                self.tema_actual.get("text", "#111827"),
                self.tema_actual.get("border", "#e5e7eb"),
                self.tema_actual.get("button_active", "#f3f4f6"),
                self.tema_actual.get("button_disabled", "#f3f4f6"),
                self.tema_actual.get("disabled_text", "#9ca3af")
            )
            btn.pack(fill="x", pady=2)
            self.botones_idioma_popup.append(btn)
            alto += 42

        alto = max(48, alto + 14)
        self.popup_idioma_ancho = ancho
        self.popup_idioma_alto = alto
        self._posicion_popup_idioma()

        self.popup_idioma.bind("<Escape>", self._cerrar_popup_idioma)

        try:
            self.popup_idioma.lift()
            self.popup_idioma.focus_force()
        except Exception:
            pass

    def seleccionar_idioma(self, codigo):
        global IDIOMA_ACTUAL

        if codigo not in LANGUAGE_NAMES:
            codigo = "en"

        IDIOMA_ACTUAL = codigo
        core.IDIOMA_ACTUAL = codigo
        self.idioma_var.set(LANGUAGE_NAMES.get(IDIOMA_ACTUAL, "English"))

        self._cerrar_popup_idioma()

        guardar_config_biblioteca()
        self.actualizar_textos_interfaz()

    def cambiar_idioma(self, event=None):
        # Compatibility with older UI code paths.
        nombre = self.idioma_var.get().replace("▼", "").strip()
        self.seleccionar_idioma(LANGUAGE_CODES_BY_NAME.get(nombre, "en"))

    def actualizar_textos_interfaz(self):
        try:
            self.root.title(tr("window_title"))
            self.label_titulo.config(text=tr("title"))
            self.label_subtitulo.config(text=tr("subtitle"))
            self.label_idioma.config(text=tr("language"))
            self.btn_idioma.configure(text=f"{LANGUAGE_NAMES.get(IDIOMA_ACTUAL, 'English')}  ▼")
            self.label_biblioteca_activa.config(text=tr("library_active"))
            self.label_biblioteca_help.config(text=tr("library_help"))
            self.label_ruta.config(text=tr("route"))
            self.label_acciones.config(text=tr("actions"))
            self.btn_agregar.configure(text=tr("add_books"))
            if hasattr(self, "btn_agregar_import"):
                self.btn_agregar_import.configure(text=tr("add_books"))
            self.btn_metadatos.configure(text=tr("metadata"))
            self.btn_biblioteca.configure(text=tr("open_library"))
            self.btn_undo.configure(text=tr("undo_last_action"))
            self.btn_dobles_carpeta.configure(text=tr("check_folder_duplicates"))
            self.btn_ia_local.configure(text=tr("ai_reinforce"))
            self.label_estado_titulo.config(text=tr("status_title"))
            self.label_registro.config(text=tr("log_title"))
            self.btn_tema.configure(text=tr("light_mode") if self.modo_oscuro else tr("dark_mode"))
            self.actualizar_label_indice()
            workspace = getattr(self, "workspace", None)
            if workspace is not None:
                workspace.translate()
        except Exception:
            pass

    def escribir(self, txt=""):
        self.texto.insert("end", txt + "\n")
        self.texto.see("end")

    def limpiar(self):
        self.texto.delete("1.0", "end")

    def estado(self, txt):
        self.label_estado.config(text=txt)
        try:
            self.label_estado_tiempo.config(text="")
        except Exception:
            pass
        self.root.update_idletasks()

    def _formatear_tiempo_restante(self, segundos):
        try:
            segundos = int(max(0, segundos))
        except Exception:
            return tr("eta_calculating")
        if segundos < 5:
            return tr("eta_under_5s")
        horas, resto = divmod(segundos, 3600)
        minutos, seg = divmod(resto, 60)
        if horas:
            return tr("eta_hms", h=horas, m=minutos, s=seg)
        if minutos:
            return tr("eta_ms", m=minutos, s=seg)
        return tr("eta_s", s=seg)

    def estado_con_tiempo(self, texto, actual, total, inicio):
        try:
            total = max(1, int(total))
            actual = max(1, int(actual))
            ahora = time.monotonic()
            estado_eta = getattr(self, "_estado_eta", None)
            if (
                not estado_eta
                or estado_eta.get("inicio") != inicio
                or estado_eta.get("total") != total
                or actual < estado_eta.get("actual", 1)
            ):
                estado_eta = {
                    "inicio": inicio,
                    "total": total,
                    "actual": actual,
                    "item_inicio": ahora,
                    "promedio": None,
                }
            elif actual != estado_eta.get("actual"):
                duracion = max(0.0, ahora - estado_eta.get("item_inicio", ahora))
                if duracion >= 0.05:
                    promedio_anterior = estado_eta.get("promedio")
                    estado_eta["promedio"] = duracion if promedio_anterior is None else (promedio_anterior * 0.7 + duracion * 0.3)
                estado_eta["actual"] = actual
                estado_eta["item_inicio"] = ahora

            self._estado_eta = estado_eta
            transcurrido_item = max(0.0, ahora - estado_eta.get("item_inicio", ahora))
            promedio = estado_eta.get("promedio")
            if promedio is None:
                if transcurrido_item < 2.0 and total > 1:
                    raise ValueError("eta still warming up")
                promedio = max(transcurrido_item, max(0.1, ahora - inicio) / max(1, actual))
            restante_item = max(0.0, promedio - transcurrido_item)
            restante = restante_item + max(0, total - actual) * promedio
            eta = self._formatear_tiempo_restante(restante)
        except Exception:
            eta = tr("eta_calculating")
        try:
            self.label_estado.config(text=texto)
            self.label_estado_tiempo.config(text=tr("eta_remaining", eta=eta))
            self.root.update_idletasks()
        except Exception:
            self.estado(f"{texto} | {tr('eta_remaining', eta=eta)}")

    def set_progreso(self, valor):
        try:
            self.progreso_var.set(max(0, min(100, float(valor))))
            self.root.update_idletasks()
        except Exception:
            pass

    def biblioteca_lista(self):
        return biblioteca_configurada() and FINAL.exists()

    def actualizar_estado_botones(self):
        if self.trabajando:
            estado_trabajo = "disabled"
            self.btn_agregar.config(state=estado_trabajo)
            if hasattr(self, "btn_agregar_import"):
                self.btn_agregar_import.config(state=estado_trabajo)
            self.btn_metadatos.config(state=estado_trabajo)
            self.btn_dobles_carpeta.config(state=estado_trabajo)
            self.btn_ia_local.config(state=estado_trabajo)
            self.btn_elegir_biblioteca.config(state=estado_trabajo)
            self.btn_undo.config(state=estado_trabajo)
            self.btn_configuracion.config(state=estado_trabajo)
            self.entry_biblioteca.config(state=estado_trabajo)
            self.btn_cancelar_operacion.config(state="normal")
            return

        estado_biblioteca = "normal" if self.biblioteca_lista() else "disabled"
        self.btn_agregar.config(state=estado_biblioteca)
        if hasattr(self, "btn_agregar_import"):
            self.btn_agregar_import.config(state=estado_biblioteca)
        self.btn_metadatos.config(state=estado_biblioteca)
        self.btn_dobles_carpeta.config(state="normal")
        self.btn_ia_local.config(state="normal")
        self.btn_elegir_biblioteca.config(state="normal")
        self.btn_undo.config(state="normal")
        self.btn_configuracion.config(state="normal")
        self.entry_biblioteca.config(state="normal")
        self.btn_cancelar_operacion.config(state="disabled")

    def abrir_panel_ia_local(self):
        if self._widget_existe(getattr(self, "ventana_ia_local", None)):
            self.ventana_ia_local.lift()
            self.ventana_ia_local.focus_force()
            return

        config = core.cargar_configuracion_ia()
        ventana = tk.Toplevel(self.root)
        self.ventana_ia_local = ventana
        ventana.title(tr("ai_window_title"))
        ventana.transient(self.root)
        ventana.geometry("680x430")
        ventana.minsize(560, 360)
        ventana.configure(bg=self.tema_actual.get("bg", "#f3f4f6"))

        contenedor = tk.Frame(ventana, bg=self.tema_actual.get("bg", "#f3f4f6"))
        contenedor.pack(fill="both", expand=True, padx=18, pady=18)

        titulo = tk.Label(
            contenedor,
            text=tr("ai_window_title"),
            font=("Segoe UI", 15, "bold"),
            bg=self.tema_actual.get("bg", "#f3f4f6"),
            fg=self.tema_actual.get("text", "#111827"),
        )
        titulo.pack(anchor="w")

        intro = tk.Label(
            contenedor,
            text=tr("ai_intro"),
            font=("Segoe UI", 10),
            bg=self.tema_actual.get("bg", "#f3f4f6"),
            fg=self.tema_actual.get("muted", "#475569"),
            wraplength=620,
            justify="left",
        )
        intro.pack(anchor="w", pady=(8, 14))

        enabled_var = tk.BooleanVar(value=bool(config.get("enabled", False)))
        model_var = tk.StringVar(value=config.get("model_id") or core.configuracion_ia_por_defecto()["model_id"])

        activar = tk.Checkbutton(
            contenedor,
            text=tr("ai_enable"),
            variable=enabled_var,
            bg=self.tema_actual.get("bg", "#f3f4f6"),
            fg=self.tema_actual.get("text", "#111827"),
            activebackground=self.tema_actual.get("bg", "#f3f4f6"),
            selectcolor=self.tema_actual.get("card", "#ffffff"),
            font=("Segoe UI", 10),
        )
        activar.pack(anchor="w", pady=(0, 10))

        tk.Label(
            contenedor,
            text=tr("ai_model"),
            font=("Segoe UI", 10, "bold"),
            bg=self.tema_actual.get("bg", "#f3f4f6"),
            fg=self.tema_actual.get("text", "#111827"),
        ).pack(anchor="w")

        for option in core.modelos_ia_local():
            rb = tk.Radiobutton(
                contenedor,
                text=option.label,
                variable=model_var,
                value=option.model_id,
                bg=self.tema_actual.get("bg", "#f3f4f6"),
                fg=self.tema_actual.get("text", "#111827"),
                activebackground=self.tema_actual.get("bg", "#f3f4f6"),
                selectcolor=self.tema_actual.get("card", "#ffffff"),
                font=("Segoe UI", 10),
            )
            rb.pack(anchor="w", pady=2)

        estado_label = tk.Label(
            contenedor,
            text="",
            font=("Segoe UI", 10),
            bg=self.tema_actual.get("bg", "#f3f4f6"),
            fg=self.tema_actual.get("muted", "#475569"),
            wraplength=620,
            justify="left",
        )
        estado_label.pack(anchor="w", pady=(14, 10))

        def config_actual():
            return {
                "enabled": enabled_var.get(),
                "model_id": model_var.get(),
                "models_dir": config.get("models_dir", ""),
                "port": config.get("port") or core.configuracion_ia_por_defecto()["port"],
            }

        def refrescar_estado():
            status = core.estado_ia_local(config_actual())
            estado_label.config(
                text=(
                    f"{tr('ai_state', state=status.get('state', ''))}\n"
                    f"Runtime: {Path(status.get('runtime_server', '')).name} | "
                    f"Modelo: {Path(status.get('model_path', '')).name}"
                )
            )

        def guardar():
            core.guardar_configuracion_ia(config_actual())
            refrescar_estado()
            messagebox.showinfo(tr("result_title"), tr("ai_saved"))

        def probar():
            saved = core.guardar_configuracion_ia(config_actual())
            ok, message, _status = core.probar_ia_local(saved)
            refrescar_estado()
            if ok:
                messagebox.showinfo(tr("ai_window_title"), message)
            else:
                messagebox.showwarning(tr("ai_window_title"), message)

        def abrir_carpeta():
            carpeta = core.carpeta_ia_local()
            if not carpeta.exists():
                messagebox.showwarning(tr("ai_window_title"), tr("ai_folder_missing"))
                return
            try:
                if os.name == "nt":
                    os.startfile(str(carpeta))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(carpeta)])
                else:
                    subprocess.Popen(["xdg-open", str(carpeta)])
            except Exception as exc:
                messagebox.showerror(tr("error_title"), str(exc))

        fila = tk.Frame(contenedor, bg=self.tema_actual.get("bg", "#f3f4f6"))
        fila.pack(fill="x", pady=(8, 0))
        for texto, comando in [
            (tr("ai_save"), guardar),
            (tr("ai_test"), probar),
            (tr("ai_status"), refrescar_estado),
            (tr("ai_open_folder"), abrir_carpeta),
        ]:
            boton = RoundedButton(
                fila,
                text=texto,
                command=comando,
                width=145,
                height=40,
                font=("Segoe UI", 9),
            )
            boton.pack(side="left", padx=(0, 8))

        refrescar_estado()

    def abrir_configuracion(self):
        config = core.cargar_configuracion_operacion()
        ventana = tk.Toplevel(self.root)
        ventana.title(tr("settings"))
        ventana.transient(self.root)
        ventana.resizable(False, False)
        frame = tk.Frame(ventana, padx=22, pady=18)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=tr("ocr_pages"), font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 18), pady=8)
        paginas_var = tk.IntVar(value=config["ocr_max_pages"])
        tk.Spinbox(frame, from_=1, to=200, textvariable=paginas_var, width=8, font=("Segoe UI", 10)).grid(row=0, column=1, sticky="e", pady=8)

        offline_var = tk.BooleanVar(value=config["offline_mode"])
        tk.Checkbutton(frame, text=tr("offline_mode"), variable=offline_var, font=("Segoe UI", 10)).grid(row=1, column=0, columnspan=2, sticky="w", pady=8)

        provider_state = core.estado_proveedores_web()
        if provider_state:
            resumen_proveedores = ", ".join(
                f"{name}: {info.get('status', 'unknown')}"
                for name, info in sorted(provider_state.items())
            )
            tk.Label(frame, text=resumen_proveedores, wraplength=430, justify="left", font=("Segoe UI", 8)).grid(row=2, column=0, columnspan=2, sticky="w", pady=8)

        def guardar():
            saved = core.guardar_configuracion_operacion({
                "ocr_max_pages": paginas_var.get(),
                "offline_mode": offline_var.get(),
            })
            self._aplicar_configuracion_operacion(saved)
            ventana.destroy()

        tk.Button(frame, text=tr("save"), command=guardar, width=14).grid(row=3, column=0, columnspan=2, pady=(14, 0))
        ventana.grab_set()

    def bloquear(self, valor):
        self.trabajando = valor
        self.actualizar_estado_botones()
        workspace = getattr(self, "workspace", None)
        if workspace is not None:
            workspace.set_busy(valor)

    def actualizar_cuadro_biblioteca(self):
        self.biblioteca_var.set(str(FINAL) if biblioteca_configurada() else "")

    def actualizar_label_indice(self):
        cantidad = len(self.indice.get("archivos", []))
        creado = self.indice.get("creado")
        if creado:
            self.label_indice.config(text=tr("index_status", count=cantidad, date=creado))
        else:
            self.label_indice.config(text=tr("index_none"))
        workspace = getattr(self, "workspace", None)
        if workspace is not None:
            workspace.refresh_library()

    def aplicar_ruta_desde_cuadro(self, event=None):
        ruta_texto = self.biblioteca_var.get().strip().strip('"')

        if not ruta_texto:
            messagebox.showwarning(tr("empty_route_title"), tr("empty_route_msg"))
            return

        self.establecer_biblioteca(Path(ruta_texto), preguntar_crear=True)

    def elegir_biblioteca(self):
        if self.trabajando:
            return

        initialdir = str(FINAL) if self.biblioteca_lista() else str(DEFAULT_START_DIR)

        carpeta = filedialog.askdirectory(
            title=tr("choose_library_title"),
            initialdir=initialdir
        )

        if not carpeta:
            return

        self.biblioteca_var.set(carpeta)
        self.establecer_biblioteca(Path(carpeta), preguntar_crear=False)

    def establecer_biblioteca(self, nueva_ruta: Path, preguntar_crear=True):
        global FINAL

        if self.trabajando:
            return

        try:
            nueva_ruta = nueva_ruta.expanduser()

            if not nueva_ruta.exists():
                crear = True
                if preguntar_crear:
                    crear = messagebox.askyesno(
                        tr("create_folder_title"),
                        tr("create_folder_msg", path=nueva_ruta)
                    )

                if not crear:
                    self.actualizar_cuadro_biblioteca()
                    return

                nueva_ruta.mkdir(parents=True, exist_ok=True)

            if not nueva_ruta.is_dir():
                messagebox.showerror(tr("invalid_route_title"), tr("invalid_route_msg"))
                self.actualizar_cuadro_biblioteca()
                return

            FINAL = nueva_ruta
            core.FINAL = nueva_ruta
            guardar_config_biblioteca()

            # Keep the old index until the scan can match unchanged files.
            # Clearing it here erased human corrections even for the same root.
            self.indice = cargar_indice()

            self.actualizar_cuadro_biblioteca()
            self.actualizar_label_indice()
            self.actualizar_estado_botones()

            self.limpiar()
            self.escribir(tr("library_selected", path=FINAL))
            self.escribir(tr("updating_index"))
            self.actualizar_indice_automatico()

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.actualizar_cuadro_biblioteca()
            self.actualizar_estado_botones()

    def actualizar_indice_automatico(self):
        if self.trabajando:
            return

        if not self.biblioteca_lista():
            self.indice = {"creado": None, "library": "", "archivos": []}
            self.actualizar_label_indice()
            self.actualizar_estado_botones()
            self.estado(tr("valid_library"))
            return

        def tarea():
            try:
                self._encolar_ui(self.bloquear, True)
                self._encolar_ui(self.set_progreso, 5)
                self._encolar_ui(self.limpiar)
                self._encolar_ui(self.escribir, tr("updating_index_path", path=FINAL))
                self._encolar_ui(self.escribir, tr("index_first_time"))

                def cb(msg):
                    self._encolar_ui(self.estado, msg)

                self.indice = crear_o_actualizar_indice(cb)
                self._encolar_ui(self.actualizar_label_indice)
                self._encolar_ui(self.set_progreso, 100)
                self._encolar_ui(self.escribir, tr("index_ready", count=len(self.indice.get("archivos", []))))
                self._encolar_ui(self.estado, tr("ready"))
            except Exception as e:
                self._encolar_ui(messagebox.showerror, tr("error_title"), str(e))
                self._encolar_ui(self.estado, "Error al actualizar el índice.")
            finally:
                self._encolar_ui(self.bloquear, False)

        self._start_worker(tarea)

    def deshacer_ultima_accion(self):
        batch, accion = obtener_ultima_accion_undo()

        if not batch or not accion:
            messagebox.showinfo(tr("undo_none_title"), tr("undo_none_msg"))
            return

        if not messagebox.askyesno(tr("undo_confirm_title"), tr("undo_confirm_msg", batch=batch, count=len(accion))):
            return

        hechos = 0
        errores = 0
        rutas_indice_afectadas = set()

        for item in reversed(accion):
            rutas_indice_afectadas.update((item.get("origen", ""), item.get("destino", "")))
            try:
                ok, mensaje = restaurar_accion_undo(item)
                if ok:
                    hechos += 1
                    rutas_indice_afectadas.add(mensaje)
                    mark_undo_item_restored(batch, item)
                else:
                    errores += 1
                    if mensaje:
                        self.escribir(str(mensaje))
            except Exception as e:
                errores += 1
                self.escribir(str(e))

        if errores == 0:
            mark_action_undone(batch)

        try:
            self.indice = core.actualizar_indice_rutas(rutas_indice_afectadas, self.indice)
            self.actualizar_label_indice()
        except Exception:
            pass

        mensaje = tr("undo_done_msg", done=hechos, errors=errores)
        messagebox.showinfo(tr("undo_done_title"), mensaje)
        self.escribir(tr("undo_log_line", done=hechos, errors=errores))

    def agregar_libros(self, rutas=None, plan_existente=None):
        if self.trabajando:
            return

        if not self.biblioteca_lista():
            messagebox.showwarning(tr("missing_library_title"), tr("missing_library_msg"))
            return

        archivos = rutas
        if archivos is None:
            archivos = filedialog.askopenfilenames(
                title=tr("add_dialog_title"),
                filetypes=[
                    (tr("filetype_books"), "*.pdf *.epub *.mobi *.azw *.azw3 *.djvu *.fb2 *.txt *.rtf *.doc *.docx *.odt *.cbr *.cbz"),
                    (tr("filetype_all"), "*.*"),
                ]
            )

        if not archivos:
            return

        libros = [Path(a) for a in archivos]
        try:
            plan_store = core.operation_plan_store()
            if plan_existente:
                plan = plan_existente
            else:
                plan = plan_store.create_plan(
                    "import_books",
                    [
                        {
                            "action": "analyze_and_import",
                            "source": libro,
                            "destination": FINAL,
                            "reason": "Importación seleccionada por el usuario",
                        }
                        for libro in libros
                    ],
                    metadata={"library": str(FINAL)},
                )
        except Exception as exc:
            messagebox.showerror(tr("error_title"), f"No se pudo crear el plan seguro de importación:\n{exc}")
            return

        preview = "\n".join(f"• {libro.name}" for libro in libros[:12])
        if len(libros) > 12:
            preview += f"\n… y {len(libros) - 12} más"
        if not messagebox.askyesno(
            "Previsualización de importación",
            f"Se analizarán {len(libros)} archivos. No se modificará ninguno hasta confirmar.\n\n{preview}\n\n¿Aplicar este plan?",
        ):
            if not plan_existente:
                plan_store.set_plan_state(plan["id"], "cancelled")
            return
        plan_id = plan["id"]
        plan_ordinals = {core.clave_ruta_resuelta(item["source"]): item["ordinal"] for item in plan["items"]}

        def tarea():
            moved_total = 0
            moved_renamed = 0
            moved_original = 0
            rechazados = 0
            posibles = 0
            errores = 0
            duplicados_descartados = 0
            duplicados_reemplazados = 0
            revision_descartados = 0
            titulos_descartados = 0
            batch_id = nuevo_batch_id("agregar")
            rutas_indice_afectadas = set(libros)
            metadata_indice_por_ruta = {}

            try:
                plan_store.set_plan_state(plan_id, "applying")
                self._encolar_ui(self.bloquear, True)
                self._encolar_ui(self.limpiar)
                self._encolar_ui(self.escribir, tr("selected_books", count=len(libros)))
                self._encolar_ui(self.escribir, "=" * 80)

                rutas_entrada = {core.clave_ruta_resuelta(ruta) for ruta in libros}
                indice_actual = dict(self.indice or {})
                indice_actual["archivos"] = [
                    item
                    for item in (self.indice or {}).get("archivos", [])
                    if core.clave_ruta_resuelta(item.get("ruta", "")) not in rutas_entrada
                ]
                inicio_operacion = time.monotonic()
                metadatos_precalculados = self._precalcular_metadatos(libros)

                for i, libro in enumerate(libros, start=1):
                    if self.cancel_token.cancelled:
                        self._encolar_ui(self.escribir, "Operación cancelada; los movimientos completados quedan registrados.\n")
                        break
                    plan_ordinal = plan_ordinals[core.clave_ruta_resuelta(libro)]
                    try:
                        plan_store.validate_item(plan_id, plan_ordinal)
                    except Exception as exc:
                        errores += 1
                        plan_store.set_item_state(plan_id, plan_ordinal, "failed", error=str(exc))
                        self._encolar_ui(self.escribir, f"Plan detenido para {libro.name}: {exc}\n")
                        continue
                    plan_store.set_item_state(plan_id, plan_ordinal, "running")
                    item_plan_error = ""
                    errores_antes_del_item = errores
                    self._encolar_ui(self.set_progreso, (i - 1) * 100 / max(1, len(libros)))
                    self._encolar_ui(
                        self.estado_con_tiempo,
                        tr("verifying", i=i, total=len(libros), name=libro.name),
                        i,
                        len(libros),
                        inicio_operacion,
                    )

                    try:
                        resultado = verificar_libro(libro, indice_actual)

                        if resultado["estado"] in {"unico", "posible_duplicado"}:
                            self._encolar_ui(self.escribir, tr("new_book", name=libro.name))
                            if resultado["estado"] == "posible_duplicado":
                                self._encolar_ui(self.escribir, tr("possible_name_match_deferred"))
                            self._encolar_ui(self.escribir, tr("searching_web_name"))

                            def cb_web(msg):
                                self._encolar_ui(self.estado_con_tiempo, f"{libro.name} | {msg}", i, len(libros), inicio_operacion)

                            meta = metadatos_precalculados.get(core.clave_ruta_resuelta(libro))
                            if not meta:
                                meta = obtener_nombre_web(libro, callback=cb_web, cancellation=self.cancel_token)

                            if meta.get("no_es_libro"):
                                rechazados += 1
                                detalle = meta.get("motivo", "")
                                escribir_historial("agregar", libro, "", "rechazado_no_es_libro", detalle)
                                self._encolar_ui(self.escribir, tr("not_a_book", name=libro.name))
                                self._encolar_ui(self.escribir, detalle + "\n")
                                continue

                            if meta["encontrado"]:
                                nombre_destino = meta["nombre_sugerido"]
                                detalle = f"Renombrado por metadatos | fuente={meta['fuente']} | confianza={meta['confianza']} | {meta['motivo']}"
                                self._encolar_ui(self.escribir, tr("suggested_name", name=nombre_destino))
                                self._encolar_ui(self.escribir, tr("source_conf", source=meta["fuente"], confidence=meta["confianza"]))
                                mover_func = lambda: mover_a_final(libro, nombre_destino, motivo=detalle)
                            else:
                                nombre_destino = libro.name
                                detalle = f"Sin coincidencia fiable. No se movió. Mejor confianza={meta['confianza']} | {meta['motivo']}"
                                self._encolar_ui(self.escribir, tr("no_reliable"))
                                if core.en_carpeta_revisar_nuevamente(libro):
                                    escribir_historial("agregar", libro, libro, "sin_cambios_sigue_en_revision", detalle, nombre_destino, meta.get("fuente", ""), meta.get("confianza", ""))
                                    self._encolar_ui(self.escribir, tr("stays_in_review", name=libro.name))
                                    self._encolar_ui(self.escribir, detalle + "\n")
                                    continue
                                moved_original += 1
                                try:
                                    destino_revision = mover_a_revisar_nuevamente(libro, motivo=detalle)
                                    rutas_indice_afectadas.add(destino_revision)
                                    registrar_undo(batch_id, "mover", libro, destino_revision, detalle)
                                    escribir_historial("agregar", libro, destino_revision, "movido_a_revisar_sin_confianza", detalle, nombre_destino, meta.get("fuente", ""), meta.get("confianza", ""))
                                    self._encolar_ui(self.escribir, tr("moved_to_review", name=destino_revision.name))
                                except Exception as e:
                                    errores += 1
                                    escribir_historial("agregar", libro, "", "sin_cambios_sin_confianza", f"{detalle} | No se pudo mover a revisión: {e}", nombre_destino, meta.get("fuente", ""), meta.get("confianza", ""))
                                    self._encolar_ui(self.escribir, tr("move_original"))
                                self._encolar_ui(self.escribir, detalle + "\n")
                                continue

                            titulo_real = meta.get("titulo") or nombre_destino
                            coincidencias_titulo = core.coincidencias_por_titulo_real_en_biblioteca(
                                titulo_real,
                                indice_actual,
                                autor=meta.get("autor", ""),
                                excluir_rutas=libros,
                            )
                            coincidencias_titulo = [
                                item for item in coincidencias_titulo
                                if core.clave_ruta_resuelta(item.get("ruta", "")) != core.clave_ruta_resuelta(libro)
                            ]
                            if coincidencias_titulo:
                                existente_item = coincidencias_titulo[0]
                                existente = Path(existente_item.get("ruta", ""))
                                motivo_revision = (
                                    "Coincidencia bibliográfica no exacta; puede ser otra edición, "
                                    f"traducción o versión. Coincidencia existente: {existente}"
                                )
                                posibles += 1
                                if core.en_carpeta_revisar_nuevamente(libro):
                                    escribir_historial(
                                        "agregar", libro, libro, "revision_manual_por_titulo",
                                        motivo_revision, nombre_destino, meta.get("fuente", ""),
                                        meta.get("confianza", ""),
                                    )
                                else:
                                    destino_revision = mover_a_revisar_nuevamente(libro, motivo=motivo_revision)
                                    rutas_indice_afectadas.add(destino_revision)
                                    registrar_undo(batch_id, "mover", libro, destino_revision, motivo_revision)
                                    escribir_historial(
                                        "agregar", libro, destino_revision, "movido_a_revision_por_titulo",
                                        motivo_revision, nombre_destino, meta.get("fuente", ""),
                                        meta.get("confianza", ""),
                                    )
                                self._encolar_ui(self.escribir, motivo_revision + "\n")
                                continue

                            origen_original = str(libro)
                            destino = mover_func()
                            rutas_indice_afectadas.add(destino)
                            metadata_indice_por_ruta[str(destino)] = meta
                            registrar_undo(batch_id, "mover", origen_original, destino, detalle)
                            moved_total += 1
                            moved_renamed += 1
                            escribir_historial("agregar", origen_original, destino, "movido_a_final", detalle, nombre_destino, meta.get("fuente", ""), meta.get("confianza", ""))

                            self._encolar_ui(self.escribir, tr("moved_final", name=destino.name))
                            self._encolar_ui(self.escribir, tr("destination", path=destino) + "\n")

                            try:
                                indice_actual.setdefault("archivos", []).append(item_indice_desde_ruta(destino, meta.get("titulo") or destino.name))
                            except Exception:
                                pass

                        elif resultado["estado"] == "duplicado_exacto":
                            exactos = resultado.get("exactos", [])
                            existente_item = exactos[0] if exactos else {}
                            existente = existente_item.get("ruta", "No identificado")
                            if existente and existente != "No identificado":
                                rutas_indice_afectadas.add(Path(existente))
                            destino_cuarentena = None
                            reemplazado = False
                            try:
                                ruta_existente = Path(existente)
                                if not core.archivos_identicos_vivos(libro, ruta_existente):
                                    motivo_revision = "Los archivos cambiaron desde la comprobación de duplicados; se requiere revisión manual."
                                    if not core.en_carpeta_revisar_nuevamente(libro):
                                        destino_revision = mover_a_revisar_nuevamente(libro, motivo=motivo_revision)
                                        rutas_indice_afectadas.add(destino_revision)
                                        registrar_undo(batch_id, "mover", libro, destino_revision, motivo_revision)
                                    posibles += 1
                                    escribir_historial("agregar", libro, "", "duplicado_cambio_detectado", motivo_revision)
                                    self._encolar_ui(self.escribir, motivo_revision + "\n")
                                    continue
                                mtime_nuevo = libro.stat().st_mtime
                                mtime_existente = float(existente_item.get("mtime", 0) or ruta_existente.stat().st_mtime)

                                if core.en_carpeta_revisar_nuevamente(libro):
                                    motivo_descarte = tr("duplicate_exact_deleted_detail", path=existente)
                                    destino_cuarentena = descartar_archivo_seguro(libro, motivo=motivo_descarte, conservado=existente)
                                    if destino_cuarentena:
                                        rutas_indice_afectadas.add(destino_cuarentena)
                                        registrar_undo(batch_id, "mover", libro, destino_cuarentena, motivo_descarte)
                                elif ruta_existente.exists() and mtime_nuevo > mtime_existente:
                                    destino, destino_cuarentena = reemplazar_archivo_transaccional(
                                        libro,
                                        ruta_existente,
                                        core.FINAL,
                                        motivo=tr("duplicate_exact_replaced_detail", path=existente),
                                    )
                                    registrar_undo(batch_id, "mover", ruta_existente, destino_cuarentena, tr("duplicate_exact_replaced_detail", path=existente))
                                    registrar_undo(batch_id, "mover", libro, destino, tr("duplicate_exact_replaced_detail", path=existente))
                                    reemplazado = True
                                    rutas_indice_afectadas.update((destino, destino_cuarentena))
                                else:
                                    motivo_descarte = tr("duplicate_exact_deleted_detail", path=existente)
                                    destino_cuarentena = descartar_archivo_seguro(libro, motivo=motivo_descarte, conservado=existente)
                                    if destino_cuarentena:
                                        rutas_indice_afectadas.add(destino_cuarentena)
                                        registrar_undo(batch_id, "mover", libro, destino_cuarentena, motivo_descarte)
                            except Exception as e:
                                errores += 1
                                escribir_historial("agregar", libro, "", "error_descartando_duplicado", str(e))
                            if reemplazado:
                                duplicados_reemplazados += 1
                                escribir_historial("agregar", libro, existente, "duplicado_exacto_reemplazado", tr("duplicate_exact_replaced_detail", path=destino_cuarentena or existente))
                            elif destino_cuarentena:
                                rechazados += 1
                                duplicados_descartados += 1
                                if core.en_carpeta_revisar_nuevamente(Path(libro)):
                                    revision_descartados += 1
                                escribir_historial("agregar", libro, destino_cuarentena, "duplicado_exacto_descartado", tr("duplicate_exact_deleted_detail", path=existente))
                            else:
                                rechazados += 1
                                escribir_historial("agregar", libro, "", "rechazado_duplicado_exacto", f"Ya existe: {existente}")
                            if reemplazado:
                                self._encolar_ui(self.escribir, tr("moved_final", name=Path(existente).name))
                                self._encolar_ui(self.escribir, tr("destination", path=existente) + "\n")
                                self._encolar_ui(self.escribir, tr("duplicate_exact_replaced_log") + "\n")
                            else:
                                self._encolar_ui(self.escribir, f"NO MOVIDO A FINAL: {libro.name}")
                                self._encolar_ui(self.escribir, tr("reason_exists"))
                                self._encolar_ui(self.escribir, tr("exists_in", path=existente) + "\n")
                                if destino_cuarentena:
                                    self._encolar_ui(self.escribir, tr("duplicate_exact_deleted_log") + "\n")

                        else:
                            errores += 1
                            escribir_historial("agregar", libro, "", "error", resultado.get("mensaje", ""))
                            self._encolar_ui(self.escribir, tr("error_file", name=libro.name))
                            self._encolar_ui(self.escribir, resultado.get("mensaje", "") + "\n")

                    except Exception as e:
                        item_plan_error = str(e)
                        errores += 1
                        escribir_historial("agregar", libro, "", "error", str(e))
                        self._encolar_ui(self.escribir, tr("error_file", name=libro.name))
                        self._encolar_ui(self.escribir, str(e) + "\n")
                    finally:
                        if not item_plan_error and errores > errores_antes_del_item:
                            item_plan_error = "La operación del archivo terminó con errores; puede reintentarse de forma segura."
                        plan_store.set_item_state(
                            plan_id, plan_ordinal,
                            "failed" if item_plan_error else "completed",
                            result={"source_exists": libro.exists()},
                            error=item_plan_error,
                        )

                plan_store.finalize_tracked_plan(plan_id, cancelled=self.cancel_token.cancelled)
                self._encolar_ui(self.estado, tr("updating_final_index"))
                self.indice = core.actualizar_indice_rutas(
                    rutas_indice_afectadas,
                    indice_actual,
                    metadata_por_ruta=metadata_indice_por_ruta,
                )

                resumen = tr(
                    "add_summary",
                    total=moved_total,
                    renamed=moved_renamed,
                    original=moved_original,
                    duplicates=rechazados,
                    possible=posibles,
                    errors=errores
                )

                self._encolar_ui(self.actualizar_label_indice)
                self._encolar_ui(self.set_progreso, 100)
                self._encolar_ui(self.escribir, "=" * 80)
                self._encolar_ui(self.escribir, resumen)
                if duplicados_descartados:
                    self._encolar_ui(self.escribir, tr("exact_duplicates_deleted", count=duplicados_descartados))
                if duplicados_reemplazados:
                    self._encolar_ui(self.escribir, tr("exact_duplicates_replaced", count=duplicados_reemplazados))
                if titulos_descartados:
                    self._encolar_ui(self.escribir, tr("same_title_duplicates_deleted", count=titulos_descartados))
                if revision_descartados:
                    self._encolar_ui(self.escribir, tr("review_deleted_existing_count", count=revision_descartados))
                self._encolar_ui(self.estado, tr("ready"))
                self._encolar_ui(self.revisar_dobles_post_operacion, resumen)

            except Exception as e:
                try:
                    plan_store.set_plan_state(plan_id, "failed")
                except Exception:
                    pass
                self._encolar_ui(messagebox.showerror, tr("error_title"), str(e))
                self._encolar_ui(self.estado, tr("error_title"))
            finally:
                self._encolar_ui(self.bloquear, False)

        self._start_worker(tarea)

    def revisar_dobles_post_operacion(self, resumen_operacion=""):
        try:
            dobles = buscar_dobles_biblioteca(self.indice, cancellation=self.cancel_token)
        except Exception as e:
            messagebox.showinfo(tr("result_title"), f"{resumen_operacion}\n\n{tr('review_doubles_error', error=e)}")
            return
        self.abrir_asistente_dobles(dobles, resumen_operacion)

    def comprobar_dobles_en_carpeta(self):
        if self.trabajando:
            return

        initialdir = str(FINAL) if self.biblioteca_lista() else str(DEFAULT_START_DIR)
        carpeta_base = filedialog.askdirectory(
            title=tr("folder_duplicates_dialog_title"),
            initialdir=initialdir
        )
        if not carpeta_base:
            return

        carpeta_comparar = filedialog.askdirectory(
            title=tr("folder_duplicates_dialog_title_secondary"),
            initialdir=str(Path(carpeta_base).parent)
        )
        if not carpeta_comparar:
            return

        def resolver_carpeta(valor):
            try:
                return Path(valor).resolve()
            except Exception:
                return Path(valor)

        def carpeta_contiene(padre, hija):
            try:
                hija.relative_to(padre)
                return True
            except ValueError:
                return False
            except Exception:
                return False

        carpeta_base = resolver_carpeta(carpeta_base)
        carpeta_comparar = resolver_carpeta(carpeta_comparar)
        if (
            carpeta_base == carpeta_comparar
            or carpeta_contiene(carpeta_base, carpeta_comparar)
            or carpeta_contiene(carpeta_comparar, carpeta_base)
        ):
            messagebox.showwarning(
                tr("folder_duplicates_invalid_pair_title"),
                tr("folder_duplicates_invalid_pair_msg")
            )
            return

        def ignorar_en_revision_seleccionada(ruta, carpeta):
            ruta = Path(ruta)
            if carpeta.name.lower() == "para revisar nuevamente":
                partes_relativas = [
                    parte.lower()
                    for parte in ruta.parts[len(carpeta.parts):]
                ]
                ignoradas = set(core.CARPETAS_IGNORADAS) - {"para revisar nuevamente"}
                return any(nombre in partes_relativas for nombre in ignoradas)
            return ignorar_por_carpeta(ruta)

        self.bloquear(True)
        self.limpiar()
        self.escribir(tr("folder_duplicates_header"))
        self.escribir(tr("folder_duplicates_selected", path_a=carpeta_base, path_b=carpeta_comparar))
        self.escribir(tr("folder_duplicates_indexing"))

        def tarea():
            inicio = time.monotonic()
            errores = 0
            items_por_ruta = {}

            def metadatos_baratos(libro):
                try:
                    extension = libro.suffix.lower()
                    if extension == ".epub":
                        return core.extraer_metadatos_epub(libro)
                    if extension in core.KINDLE_EXTENSIONS:
                        return core.extraer_metadatos_mobi(libro)
                    if extension == ".pdf":
                        return core.extraer_metadatos_pdf(libro)
                except Exception:
                    pass
                return {}

            def aplicar_metadatos_a_item(item, meta):
                titulo = str(meta.get("titulo", "") or "").strip()
                autor = str(meta.get("autor", "") or "").strip()
                isbn = str(meta.get("isbn", "") or "").strip()
                anio = str(meta.get("anio", "") or "").strip()
                editorial = str(meta.get("editorial", "") or "").strip()
                if titulo:
                    item["titulo_real"] = titulo
                    item["titulo"] = titulo
                    item["titulo_normalizado"] = core.titulo_normalizado_para_dobles(titulo)
                    variantes = core.variantes_titulo_normalizado_para_dobles(titulo)
                    for valor in item.get("titulos_normalizados", []) or []:
                        if valor and valor not in variantes:
                            variantes.append(valor)
                    item["titulos_normalizados"] = variantes
                if autor:
                    item["autor"] = autor
                    item["autor_normalizado"] = normalizar_texto(autor)
                if isbn:
                    item["isbn"] = isbn
                if anio:
                    item["anio"] = anio
                if editorial:
                    item["editorial"] = editorial
                return item

            def crear_item_rapido(libro):
                meta = metadatos_baratos(libro)
                titulo = str(meta.get("titulo", "") or "").strip()
                item = core.item_indice_ligero_desde_ruta(libro, titulo or libro.name)
                return aplicar_metadatos_a_item(item, meta)

            def rutas_desde_dobles(dobles, incluir_exactos=False):
                rutas = set()
                for doble in dobles:
                    if not incluir_exactos and doble.get("tipo") == "duplicado_exacto":
                        continue
                    for clave_archivo in ("archivo_a", "archivo_b"):
                        ruta = doble.get(clave_archivo, {}).get("ruta", "")
                        if ruta:
                            rutas.add(ruta)
                return rutas

            def rutas_por_buckets(items):
                buckets = {}
                for item in items:
                    for clave in core.claves_item_para_dobles(item):
                        buckets.setdefault(clave, []).append(item)
                rutas = set()
                for grupo in buckets.values():
                    if len(grupo) < 2:
                        continue
                    grupo = grupo[:120]
                    for idx, a in enumerate(grupo):
                        for b in grupo[idx + 1:]:
                            if not core.doble_entre_carpetas(
                                {"archivo_a": a, "archivo_b": b},
                                carpeta_base,
                                carpeta_comparar,
                            ):
                                continue
                            if core.numeros_de_titulo_en_conflicto(a.get("nombre", ""), b.get("nombre", "")):
                                continue
                            variantes_a = core.variantes_item_para_dobles(a)
                            variantes_b = core.variantes_item_para_dobles(b)
                            compatible = False
                            for titulo_a in variantes_a:
                                for titulo_b in variantes_b:
                                    ok, _score = core.titulos_dobles_compatibles(titulo_a, titulo_b, umbral=0.96)
                                    if ok:
                                        compatible = True
                                        break
                                if compatible:
                                    break
                            if compatible:
                                if a.get("ruta"):
                                    rutas.add(a["ruta"])
                                if b.get("ruta"):
                                    rutas.add(b["ruta"])
                return rutas

            def calcular_hashes_selectivos(items):
                por_tamano = {}
                for item in items:
                    tamano = int(item.get("tamano_bytes", 0) or 0)
                    if tamano > 0:
                        por_tamano.setdefault(tamano, []).append(item)

                for grupo_tamano in por_tamano.values():
                    if len(grupo_tamano) < 2:
                        continue
                    parciales = {}
                    for item in grupo_tamano:
                        ruta = Path(item.get("ruta", ""))
                        try:
                            parcial = core.calcular_hash_parcial(ruta)
                            parciales.setdefault(parcial, []).append(item)
                        except Exception:
                            pass
                    for grupo_parcial in parciales.values():
                        if len(grupo_parcial) < 2:
                            continue
                        for item in grupo_parcial:
                            ruta = Path(item.get("ruta", ""))
                            try:
                                item["sha256"] = core.calcular_hash(ruta)
                            except Exception:
                                pass

            try:
                libros_base = sorted(
                    [
                        p for p in carpeta_base.rglob("*")
                        if es_libro(p) and not ignorar_en_revision_seleccionada(p, carpeta_base)
                    ],
                    key=lambda p: str(p).lower()
                )
                libros_comparar = sorted(
                    [
                        p for p in carpeta_comparar.rglob("*")
                        if es_libro(p) and not ignorar_en_revision_seleccionada(p, carpeta_comparar)
                    ],
                    key=lambda p: str(p).lower()
                )
                if not libros_base or not libros_comparar:
                    self._encolar_ui(messagebox.showinfo, tr("folder_duplicates_no_books_title"), tr("folder_duplicates_no_books_msg"))
                    return
                libros = libros_base + libros_comparar

                for i, libro in enumerate(libros, start=1):
                    if self.cancel_token.cancelled:
                        break
                    self._encolar_ui(self.set_progreso, (i - 1) * 45 / max(1, len(libros)))
                    self._encolar_ui(
                        self.estado_con_tiempo,
                        tr("folder_duplicates_fast_scan", i=i, total=len(libros), name=libro.name),
                        i,
                        len(libros),
                        inicio
                    )
                    try:
                        items_por_ruta[str(libro)] = crear_item_rapido(libro)
                    except Exception as e:
                        errores += 1
                        self._encolar_ui(self.escribir, f"{tr('error_file', name=libro.name)}\n{e}")

                items = list(items_por_ruta.values())
                self._encolar_ui(self.estado, tr("folder_duplicates_hashing"))
                calcular_hashes_selectivos(items)
                candidatos_profundos = set()
                candidatos_profundos.update(rutas_por_buckets(items))

                indice_temporal = {
                    "creado": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "library": f"{carpeta_base} <-> {carpeta_comparar}",
                    "archivos": items,
                }
                dobles_rapidos = buscar_dobles_biblioteca(
                    indice_temporal, limite=None, ignorar_carpetas=False,
                    cancellation=self.cancel_token,
                )
                dobles_rapidos = core.filtrar_dobles_entre_carpetas(dobles_rapidos, carpeta_base, carpeta_comparar)
                candidatos_profundos.update(rutas_desde_dobles(dobles_rapidos))

                if len(libros) <= 20:
                    candidatos_profundos.update(str(libro) for libro in libros)

                candidatos_ordenados = [
                    Path(ruta) for ruta in sorted(candidatos_profundos, key=lambda p: str(p).lower())
                    if ruta and Path(ruta).exists()
                ]
                self._encolar_ui(
                    self.escribir,
                    tr("folder_duplicates_fast_summary", books=len(items), candidates=len(candidatos_ordenados))
                )

                for i, libro in enumerate(candidatos_ordenados, start=1):
                    if self.cancel_token.cancelled:
                        break
                    self._encolar_ui(self.set_progreso, 45 + (i - 1) * 45 / max(1, len(candidatos_ordenados)))
                    self._encolar_ui(
                        self.estado_con_tiempo,
                        tr("folder_duplicates_deep_analyzing", i=i, total=len(candidatos_ordenados), name=libro.name),
                        i,
                        len(candidatos_ordenados),
                        inicio
                    )

                    base = items_por_ruta.get(str(libro), {})
                    titulo_real = str(base.get("titulo_real", "") or base.get("titulo", "") or "").strip()
                    autor_real = str(base.get("autor", "") or "").strip()
                    try:
                        def cb_web(msg):
                            self._encolar_ui(self.estado_con_tiempo, f"{libro.name} | {msg}", i, len(candidatos_ordenados), inicio)

                        meta = obtener_nombre_web(libro, callback=cb_web, cancellation=self.cancel_token)
                        if meta:
                            titulo_real = meta.get("titulo", "") or titulo_real
                            autor_real = meta.get("autor", "") or autor_real
                    except Exception as e:
                        errores += 1
                        self._encolar_ui(self.escribir, f"{tr('error_file', name=libro.name)}\n{e}")

                    try:
                        item = item_indice_desde_ruta(libro, titulo_real or libro.name)
                        if autor_real:
                            item["autor"] = autor_real
                            item["autor_normalizado"] = normalizar_texto(autor_real)
                        if titulo_real:
                            item["titulo_real"] = titulo_real
                            item["titulo"] = titulo_real
                        items_por_ruta[str(libro)] = item
                    except Exception as e:
                        errores += 1
                        self._encolar_ui(self.escribir, f"{tr('error_file', name=libro.name)}\n{e}")

                indice_temporal["archivos"] = list(items_por_ruta.values())
                dobles = buscar_dobles_biblioteca(
                    indice_temporal, limite=None, ignorar_carpetas=False,
                    cancellation=self.cancel_token,
                )
                dobles = core.filtrar_dobles_entre_carpetas(dobles, carpeta_base, carpeta_comparar)
                resumen = tr(
                    "folder_duplicates_summary",
                    path_a=carpeta_base,
                    path_b=carpeta_comparar,
                    books_a=len(libros_base),
                    books_b=len(libros_comparar),
                    books=len(indice_temporal["archivos"]),
                    duplicates=len(dobles),
                    errors=errores
                )
                self._encolar_ui(self.set_progreso, 100)
                self._encolar_ui(self.escribir, resumen)
                if dobles:
                    self._encolar_ui(
                        self.abrir_asistente_dobles,
                        dobles,
                        resumen,
                        carpeta_comparar / "PARA REVISAR NUEVAMENTE",
                        False
                    )
                else:
                    self._encolar_ui(self.escribir, tr("folder_duplicates_no_doubles"))
                    self._encolar_ui(messagebox.showinfo, tr("duplicate_file_title"), tr("folder_duplicates_no_doubles"))
            finally:
                self._encolar_ui(self.bloquear, False)
                self._encolar_ui(self.estado, tr("ready"))

        self._start_worker(tarea)

    def abrir_asistente_dobles(
        self,
        dobles,
        resumen_operacion="",
        review_folder=None,
        refresh_library=True,
        existing_review_session="",
        review_ordinals=None,
    ):
        workspace = getattr(self, "workspace", None)
        if workspace is not None:
            workspace.show_page("reviews")
            workspace.set_import_step(2)
        ventana = tk.Toplevel(self.root)
        ventana.title(tr("review_window_title"))
        ventana.geometry("920x640")
        ventana.minsize(760, 540)
        ventana.transient(self.root)
        ventana.configure(bg=self.tema_actual.get("bg", "#f3f4f6"))

        c = self.tema_actual
        batch_id = nuevo_batch_id("revision_dobles")
        try:
            review_store = core.duplicate_review_store()
            review_session_id = existing_review_session or review_store.create_session(dobles)
        except Exception:
            review_store = None
            review_session_id = ""
        review_ordinals = list(review_ordinals or range(len(dobles)))

        contenedor = tk.Frame(ventana, bg=c["bg"], padx=18, pady=16)
        contenedor.pack(fill="both", expand=True)

        titulo = tk.Label(
            contenedor,
            text="",
            font=("Segoe UI", 17, "bold"),
            anchor="w",
            bg=c["bg"],
            fg=c["text"],
        )
        titulo.pack(fill="x", pady=(0, 8))

        subtitulo = tk.Label(
            contenedor,
            text="",
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            bg=c["bg"],
            fg=c["muted"],
            wraplength=860,
        )
        subtitulo.pack(fill="x", pady=(0, 12))

        resumen_card = RoundedCard(
            contenedor,
            radius=18,
            padding=14,
            bg_outer=c["bg"],
            bg_inner=c["card"],
            border=c["border"],
            min_height=92,
            auto_height=True,
        )
        resumen_card.pack(fill="x", pady=(0, 12))

        recomendacion = tk.Text(
            resumen_card.inner,
            font=("Segoe UI", 11, "bold"),
            bg=c["card"],
            fg=c["accent"],
            height=2,
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            cursor="arrow",
        )
        recomendacion.pack(fill="x")
        recomendacion.configure(state="disabled")

        def set_recomendacion(texto):
            texto = texto or ""
            recomendacion.configure(state="normal")
            recomendacion.delete("1.0", "end")
            recomendacion.insert("1.0", texto)
            recomendacion.configure(state="disabled")

        motivo_label = tk.Label(
            resumen_card.inner,
            text="",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            bg=c["card"],
            fg=c["muted"],
            wraplength=820,
        )
        motivo_label.pack(fill="x", pady=(6, 0))

        tarjetas = tk.Frame(contenedor, bg=c["bg"])
        tarjetas.pack(fill="both", expand=True, pady=(0, 12))
        tarjetas.grid_columnconfigure(0, weight=1, uniform="dup_cards")
        tarjetas.grid_columnconfigure(1, weight=1, uniform="dup_cards")
        tarjetas.grid_rowconfigure(0, weight=1)

        card_a = RoundedCard(tarjetas, radius=18, padding=14, bg_outer=c["bg"], bg_inner=c["card"], border=c["border"], min_height=290, auto_height=False)
        card_b = RoundedCard(tarjetas, radius=18, padding=14, bg_outer=c["bg"], bg_inner=c["card"], border=c["border"], min_height=290, auto_height=False)
        card_a.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        card_b.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        botones = tk.Frame(contenedor, bg=c["bg"])
        botones.pack(fill="x")

        estado = {"idx": -1}
        revisiones_resueltas = set()

        def limpiar_botones():
            for hijo in botones.winfo_children():
                hijo.destroy()

        def limpiar_tarjeta(card):
            for hijo in card.inner.winfo_children():
                hijo.destroy()

        def boton(parent, texto, comando, estilo="normal", ancho=210):
            btn = RoundedButton(
                parent,
                text=texto,
                command=comando,
                width=ancho,
                height=40,
                radius=14,
                font=("Segoe UI", 9, "bold" if estilo == "primary" else "normal"),
            )
            if estilo == "primary":
                btn.set_theme(c["primary_bg"], c["primary_text"], c["primary_bg"], c["primary_active"], c["button_disabled"], c["disabled_text"])
            elif estilo == "quiet":
                btn.set_theme(c["quiet_bg"], c["text"], c["border"], c["quiet_active"], c["button_disabled"], c["disabled_text"])
            else:
                btn.set_theme(c["button_bg"], c["text"], c["border"], c["button_active"], c["button_disabled"], c["disabled_text"])
            return btn

        def fecha_item(item):
            try:
                mtime = float(item.get("mtime", 0))
                if not mtime:
                    ruta = Path(item.get("ruta", ""))
                    mtime = ruta.stat().st_mtime
                return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            except Exception:
                return tr("date_unavailable")

        def item_mtime(item):
            try:
                mtime = float(item.get("mtime", 0))
                if mtime:
                    return mtime
                return Path(item.get("ruta", "")).stat().st_mtime
            except Exception:
                return 0

        def tamano_item(item):
            try:
                return f"{int(item.get('tamano_bytes', 0)):,} bytes"
            except Exception:
                return tr("not_available")

        def aplicar_hover_card(card, activo):
            try:
                if bool(getattr(card, "_pointer_hover", False)) == bool(activo):
                    return
                card._pointer_hover = bool(activo)
                bg_inner = c["quiet_bg"] if activo else c["card"]
                border = c["accent"] if activo else c["border"]
                card.set_theme(c["bg"], bg_inner, border)
                for hijo in card.inner.winfo_children():
                    try:
                        hijo.configure(bg=bg_inner)
                    except Exception:
                        pass
                    try:
                        for nieto in hijo.winfo_children():
                            nieto.configure(bg=bg_inner)
                    except Exception:
                        pass
            except Exception:
                pass

        def puntero_dentro_card(card):
            try:
                x, y = card.winfo_pointerxy()
                current = card.winfo_containing(x, y)
                while current is not None:
                    if current in {card, card.canvas, card.inner}:
                        return True
                    current = getattr(current, "master", None)
            except (AttributeError, tk.TclError):
                pass
            return False

        def entrar_card(card):
            pending = getattr(card, "_pointer_leave_after", None)
            if pending is not None:
                try:
                    card.after_cancel(pending)
                except tk.TclError:
                    pass
                card._pointer_leave_after = None
            aplicar_hover_card(card, True)

        def comprobar_salida_card(card):
            card._pointer_leave_after = None
            if not puntero_dentro_card(card):
                aplicar_hover_card(card, False)

        def salir_card(card):
            pending = getattr(card, "_pointer_leave_after", None)
            if pending is not None:
                try:
                    card.after_cancel(pending)
                except tk.TclError:
                    pass
            # Enter/Leave also fire while crossing child widgets. Checking
            # after Tk has updated the pointer target prevents card flicker.
            card._pointer_leave_after = card.after_idle(lambda: comprobar_salida_card(card))

        def vincular_click_recursivo(widget, comando, card=None):
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass
            try:
                widget.bind("<Button-1>", lambda _event, cmd=comando: cmd())
            except Exception:
                pass
            if card is not None:
                try:
                    widget.bind("<Enter>", lambda _event, target=card: entrar_card(target))
                    widget.bind("<Leave>", lambda _event, target=card: salir_card(target))
                except Exception:
                    pass
            try:
                for hijo in widget.winfo_children():
                    vincular_click_recursivo(hijo, comando, card)
            except Exception:
                pass

        def pintar_archivo(card, etiqueta, item, destacado=False, mas_reciente=False, comando=None):
            limpiar_tarjeta(card)
            ruta = Path(item.get("ruta", ""))

            head = tk.Frame(card.inner, bg=c["card"])
            head.pack(fill="x", pady=(0, 10))
            tk.Label(
                head,
                text=etiqueta,
                font=("Segoe UI", 12, "bold"),
                bg=c["card"],
                fg=c["accent"] if destacado else c["text"],
                anchor="w",
            ).pack(side="left")
            if mas_reciente:
                tk.Label(
                    head,
                    text=tr("newer_tag"),
                    font=("Segoe UI", 9, "bold"),
                    bg=c["quiet_bg"],
                    fg=c["success"],
                    padx=8,
                    pady=3,
                ).pack(side="right")

            nombre = tk.Label(
                card.inner,
                text=item.get("nombre", ruta.name),
                font=("Segoe UI", 11, "bold"),
                bg=c["card"],
                fg=c["text"],
                anchor="w",
                justify="left",
                wraplength=360,
            )
            nombre.pack(fill="x", pady=(0, 10))

            campos = [
                (tr("field_format"), item.get("extension", "")),
                (tr("field_size"), tamano_item(item)),
                (tr("field_modified"), fecha_item(item)),
                (tr("field_hash"), f"{str(item.get('sha256', ''))[:18]}..."),
                (tr("field_path"), str(ruta)),
            ]
            for label, valor in campos:
                fila = tk.Frame(card.inner, bg=c["card"])
                fila.pack(fill="x", pady=3)
                tk.Label(fila, text=label, width=11, anchor="w", bg=c["card"], fg=c["muted"], font=("Segoe UI", 9)).pack(side="left")
                tk.Label(fila, text=valor, anchor="w", justify="left", bg=c["card"], fg=c["text"], font=("Segoe UI", 9), wraplength=300).pack(side="left", fill="x", expand=True)

            indicacion = tk.Label(
                card.inner,
                text=tr("keep_card_hint"),
                font=("Segoe UI", 9, "bold"),
                bg=c["card"],
                fg=c["accent"],
                anchor="w",
            )
            indicacion.pack(fill="x", pady=(12, 0))

            if comando:
                vincular_click_recursivo(card, comando, card)

        def refrescar_indice_ligero():
            try:
                self.indice = crear_o_actualizar_indice(lambda msg: self.estado(msg))
                self.actualizar_label_indice()
            except Exception:
                pass

        def terminar():
            titulo.config(text=tr("review_clean_title"))
            subtitulo.config(text="")
            set_recomendacion(tr("review_clean_message"))
            motivo_label.config(text=tr("review_clean_detail"))
            limpiar_tarjeta(card_a)
            limpiar_tarjeta(card_b)
            limpiar_botones()
            boton(botones, tr("close"), ventana.destroy, "primary", 140).pack(side="right", padx=4)
            if refresh_library:
                refrescar_indice_ligero()

        def siguiente(resultado_anterior=None):
            if review_store and estado["idx"] >= 0 and resultado_anterior:
                try:
                    review_store.mark(review_session_id, review_ordinals[estado["idx"]], resultado_anterior)
                except Exception as exc:
                    self.escribir(f"No se pudo guardar el progreso de revisión: {exc}\n")
            estado["idx"] += 1
            while estado["idx"] in revisiones_resueltas:
                estado["idx"] += 1
            if estado["idx"] >= len(dobles):
                terminar()
                return
            mostrar_actual()

        def lado_recomendado(pair):
            return pair.get("recomendado") or core.elegir_item_preferido_por_fecha_y_formato(pair["archivo_a"], pair["archivo_b"])

        def aplicar_conservacion(pair, lado_conservado, enviar_a_cuarentena):
            conservado = pair["archivo_a"] if lado_conservado == "a" else pair["archivo_b"]
            descartado = pair["archivo_b"] if lado_conservado == "a" else pair["archivo_a"]
            ruta_conservada = Path(conservado.get("ruta", ""))
            ruta_descartada = Path(descartado.get("ruta", ""))

            resultado = {"kept": 0, "discarded": 0, "moved": 0, "skipped": 0, "errors": 0, "message": ""}
            if not ruta_conservada.exists():
                resultado["skipped"] = 1
                resultado["message"] = tr("file_missing_msg", path=ruta_conservada)
                return resultado
            if not ruta_descartada.exists():
                resultado["skipped"] = 1
                resultado["message"] = tr("discard_missing_msg", path=ruta_descartada)
                return resultado

            try:
                if enviar_a_cuarentena:
                    base_cuarentena = Path(review_folder).parent if review_folder is not None else None
                    motivo_descarte = tr("kept_log", path=ruta_conservada)
                    destino = descartar_archivo_seguro(ruta_descartada, base_cuarentena, motivo=motivo_descarte, conservado=ruta_conservada)
                    if not destino:
                        raise RuntimeError(f"No se pudo mover a cuarentena: {ruta_descartada}")
                    registrar_undo(batch_id, "mover", ruta_descartada, destino, motivo_descarte)
                    escribir_historial("revision_dobles", ruta_descartada, destino, "descartado_a_cuarentena", motivo_descarte)
                    self.escribir(tr("kept_log", path=ruta_conservada))
                    self.escribir(tr("discard_deleted_log", path=destino))
                    resultado["discarded"] = 1
                else:
                    if review_folder is not None:
                        destino = mover_a_revisar_nuevamente(
                            ruta_descartada,
                            carpeta_destino=Path(review_folder),
                            motivo=tr("kept_log", path=ruta_conservada),
                        )
                    else:
                        destino = mover_a_revisar_nuevamente(ruta_descartada, motivo=tr("kept_log", path=ruta_conservada))
                    registrar_undo(batch_id, "mover", ruta_descartada, destino, tr("kept_log", path=ruta_conservada))
                    escribir_historial("revision_dobles", ruta_descartada, destino, "movido_a_revisar", tr("kept_log", path=ruta_conservada))
                    self.escribir(tr("kept_log", path=ruta_conservada))
                    self.escribir(tr("discard_moved_review_log", path=destino))
                    resultado["moved"] = 1
                resultado["kept"] = 1
                return resultado
            except Exception as e:
                resultado["errors"] = 1
                resultado["message"] = str(e)
                return resultado

        def conservar_archivo(pair, lado_conservado):
            conservado = pair["archivo_a"] if lado_conservado == "a" else pair["archivo_b"]
            ruta_conservada = Path(conservado.get("ruta", ""))
            enviar_a_cuarentena = messagebox.askyesno(
                tr("duplicate_file_title"),
                tr("duplicate_file_question", kept=ruta_conservada)
            )
            resultado = aplicar_conservacion(pair, lado_conservado, enviar_a_cuarentena)
            if resultado.get("message"):
                if resultado.get("errors"):
                    messagebox.showerror(tr("error_title"), resultado["message"])
                    return
                messagebox.showinfo(tr("file_not_found_title"), resultado["message"])
            siguiente("resolved")

        def conservar_mas_recientes_automaticamente():
            inicio = max(estado["idx"], 0)
            pendientes = dobles[inicio:]
            if not pendientes:
                terminar()
                return

            automaticos = [
                pair for pair in pendientes
                if pair.get("tipo") == "duplicado_exacto"
                and core.archivos_identicos_vivos(
                    Path(pair["archivo_a"].get("ruta", "")),
                    Path(pair["archivo_b"].get("ruta", "")),
                )
            ]
            if not automaticos:
                messagebox.showinfo(
                    tr("auto_process_exact_title"),
                    "No hay duplicados exactos verificados para procesar automáticamente. Las coincidencias bibliográficas requieren selección manual.",
                )
                return

            enviar_a_cuarentena = messagebox.askyesnocancel(
                tr("auto_process_exact_title"),
                tr("auto_process_exact_question", count=len(automaticos))
            )
            if enviar_a_cuarentena is None:
                return

            totales = {"kept": 0, "discarded": 0, "moved": 0, "skipped": 0, "errors": 0}
            for pair in automaticos:
                lado = lado_recomendado(pair)
                resultado = aplicar_conservacion(pair, lado, enviar_a_cuarentena)
                for clave in totales:
                    totales[clave] += int(resultado.get(clave, 0) or 0)
                if resultado.get("message"):
                    self.escribir(resultado["message"])
                if review_store:
                    ordinal = dobles.index(pair)
                    review_store.mark(review_session_id, review_ordinals[ordinal], "resolved" if not resultado.get("errors") else "error")
                    if not resultado.get("errors"):
                        revisiones_resueltas.add(ordinal)

            resumen = tr("auto_keep_newest_done", **totales)
            self.escribir(resumen)
            messagebox.showinfo(tr("auto_process_exact_title"), resumen)
            estado["idx"] = inicio - 1
            siguiente()

        def mostrar_actual():
            pair = dobles[estado["idx"]]
            mtime_a = item_mtime(pair["archivo_a"])
            mtime_b = item_mtime(pair["archivo_b"])
            margen_fecha = 2
            mas_reciente_a = bool(mtime_a and mtime_b and mtime_a > mtime_b + margen_fecha)
            mas_reciente_b = bool(mtime_a and mtime_b and mtime_b > mtime_a + margen_fecha)
            recomendado = lado_recomendado(pair)
            if recomendado == "a":
                reciente = tr("recommend_keep_a")
                destacado_a, destacado_b = True, False
            elif recomendado == "b":
                reciente = tr("recommend_keep_b")
                destacado_a, destacado_b = False, True
            elif mtime_a > mtime_b:
                reciente = tr("file_a_newer")
                destacado_a, destacado_b = True, False
            elif mtime_b > mtime_a:
                reciente = tr("file_b_newer")
                destacado_a, destacado_b = False, True
            else:
                reciente = tr("same_date_unknown")
                destacado_a, destacado_b = False, False

            titulo.config(text=tr("comparison_title", index=estado["idx"] + 1, total=len(dobles)))
            subtitulo.config(text=tr("review_compare_subtitle"))
            set_recomendacion(reciente)
            motivo_label.config(text=tr("review_pair_detail", type=pair.get("tipo", ""), confidence=pair.get("confianza", ""), reason=pair.get("motivo", "")))
            pintar_archivo(card_a, tr("file_label_a"), pair["archivo_a"], destacado_a, mas_reciente_a, lambda: conservar_archivo(pair, "a"))
            pintar_archivo(card_b, tr("file_label_b"), pair["archivo_b"], destacado_b, mas_reciente_b, lambda: conservar_archivo(pair, "b"))
            limpiar_botones()
            boton(botones, tr("auto_process_exact"), conservar_mas_recientes_automaticamente, "primary", 300).pack(side="left", padx=3)
            boton(botones, tr("skip_now"), lambda: siguiente("skipped"), "quiet", 150).pack(side="right", padx=3)

        titulo.config(text=tr("operation_summary_title"))
        subtitulo.config(text=tr("review_summary_subtitle"))
        if dobles:
            set_recomendacion(tr("review_found_count", count=len(dobles)))
            motivo_label.config(text=tr("review_start_detail"))
        else:
            set_recomendacion(tr("review_clean_message"))
            motivo_label.config(text=tr("review_no_doubles"))
        limpiar_tarjeta(card_a)
        limpiar_tarjeta(card_b)
        resumen_texto = tk.Label(
            card_a.inner,
            text=resumen_operacion or tr("operation_finished"),
            font=("Segoe UI", 10),
            bg=c["card"],
            fg=c["text"],
            justify="left",
            anchor="nw",
            wraplength=780,
        )
        resumen_texto.pack(fill="both", expand=True)
        limpiar_botones()
        if dobles:
            boton(botones, tr("auto_keep_newest"), conservar_mas_recientes_automaticamente, "primary", 300).pack(side="left", padx=4)
            boton(botones, tr("next"), siguiente, "primary", 132).pack(side="right", padx=4)
        boton(botones, tr("close"), ventana.destroy, "quiet", 120).pack(side="right", padx=4)

    def abrir_selector_metadatos(self):
        if self.trabajando:
            return

        if self._widget_existe(getattr(self, "ventana_metadatos", None)):
            try:
                self.ventana_metadatos.lift()
                self.ventana_metadatos.focus_force()
            except Exception:
                pass
            return

        ventana = tk.Toplevel(self.root)
        self.ventana_metadatos = ventana
        self._ignorar_click_externo_metadatos = True
        self.root.after(250, lambda: setattr(self, "_ignorar_click_externo_metadatos", False))
        ventana.title(tr("metadata_window_title"))
        ventana.resizable(True, False)
        ventana.minsize(360, 220)
        ventana.transient(self.root)
        ventana.configure(bg=self.tema_actual.get("bg", "#f3f4f6"))
        ventana.protocol("WM_DELETE_WINDOW", self._cerrar_ventana_metadatos)

        card = RoundedCard(
            ventana,
            radius=18,
            padding=16,
            bg_outer=self.tema_actual.get("bg", "#f3f4f6"),
            bg_inner=self.tema_actual.get("card", "#ffffff"),
            border=self.tema_actual.get("border", "#e5e7eb"),
            min_height=210,
            auto_height=True
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        etiqueta = tk.Label(
            card.inner,
            text=tr("metadata_question"),
            font=("Segoe UI", 11, "bold"),
            wraplength=420,
            justify="center"
        )
        etiqueta.configure(
            bg=self.tema_actual.get("card", "#ffffff"),
            fg=self.tema_actual.get("text", "#111827")
        )
        etiqueta.pack(pady=(0, 18))

        frame_botones = tk.Frame(card.inner, bg=self.tema_actual.get("card", "#ffffff"))
        frame_botones.pack(fill="x")
        frame_botones.grid_columnconfigure(0, weight=1, uniform="metadata")
        frame_botones.grid_columnconfigure(1, weight=1, uniform="metadata")

        def elegir_ficheros():
            self._cerrar_ventana_metadatos()
            self.seleccionar_ficheros_metadatos()

        def elegir_carpeta():
            self._cerrar_ventana_metadatos()
            self.seleccionar_carpeta_metadatos()

        btn_ficheros = RoundedButton(
            frame_botones,
            text=tr("files"),
            command=elegir_ficheros,
            width=150,
            height=44,
            radius=15,
            font=("Segoe UI", 10, "bold")
        )
        btn_ficheros.set_theme(
            self.tema_actual.get("button_bg", "#ffffff"),
            self.tema_actual.get("text", "#111827"),
            self.tema_actual.get("border", "#e5e7eb"),
            self.tema_actual.get("button_active", "#f3f4f6"),
            self.tema_actual.get("button_disabled", "#f3f4f6"),
            self.tema_actual.get("disabled_text", "#9ca3af")
        )
        btn_ficheros.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        btn_carpeta = RoundedButton(
            frame_botones,
            text=tr("folder"),
            command=elegir_carpeta,
            width=150,
            height=44,
            radius=15,
            font=("Segoe UI", 10, "bold")
        )
        btn_carpeta.set_theme(
            self.tema_actual.get("button_bg", "#ffffff"),
            self.tema_actual.get("text", "#111827"),
            self.tema_actual.get("border", "#e5e7eb"),
            self.tema_actual.get("button_active", "#f3f4f6"),
            self.tema_actual.get("button_disabled", "#f3f4f6"),
            self.tema_actual.get("disabled_text", "#9ca3af")
        )
        btn_carpeta.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        btn_cancelar = RoundedButton(
            card.inner,
            text=tr("cancel"),
            command=self._cerrar_ventana_metadatos,
            width=145,
            height=40,
            radius=14,
            font=("Segoe UI", 10)
        )
        btn_cancelar.set_theme(
            self.tema_actual.get("button_bg", "#ffffff"),
            self.tema_actual.get("text", "#111827"),
            self.tema_actual.get("border", "#e5e7eb"),
            self.tema_actual.get("button_active", "#f3f4f6"),
            self.tema_actual.get("button_disabled", "#f3f4f6"),
            self.tema_actual.get("disabled_text", "#9ca3af")
        )
        btn_cancelar.pack(pady=(18, 0))

        ventana.update_idletasks()
        ancho = max(470, ventana.winfo_reqwidth())
        alto = max(245, ventana.winfo_reqheight())
        x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - (ancho // 2)
        y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (alto // 2)
        ventana.geometry(f"{ancho}x{alto}+{max(0, x)}+{max(0, y)}")
        ventana.bind("<Escape>", self._cerrar_ventana_metadatos)

        try:
            ventana.lift()
            ventana.focus_force()
        except Exception:
            pass

    def seleccionar_ficheros_metadatos(self):
        archivos = filedialog.askopenfilenames(
            title=tr("metadata_files_title"),
            filetypes=[
                (tr("filetype_books"), "*.pdf *.epub *.mobi *.azw *.azw3 *.djvu *.fb2 *.txt *.rtf *.doc *.docx *.odt *.cbr *.cbz *.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp"),
                (tr("filetype_all"), "*.*"),
            ]
        )
        if not archivos:
            return
        libros = [Path(a) for a in archivos if es_libro(Path(a)) or Path(a).suffix.lower() in OCR_IMAGE_EXTENSIONS]
        self.renombrar_por_metadatos_thread(libros)

    def seleccionar_carpeta_metadatos(self):
        carpeta = filedialog.askdirectory(title=tr("metadata_folder_title"))
        if not carpeta:
            return
        self.renombrar_por_metadatos_thread(Path(carpeta))

    def renombrar_por_metadatos_thread(self, libros):
        if self.trabajando:
            return
        carpeta_metadatos = libros if isinstance(libros, Path) and libros.is_dir() else None
        if carpeta_metadatos is None and not libros:
            messagebox.showinfo(tr("no_books_title"), tr("no_books_msg"))
            return

        def tarea():
            renombrados = 0
            sin_cambio = 0
            errores = 0
            batch_id = nuevo_batch_id("renombrar")
            rutas_indice_afectadas = set()
            metadata_indice_por_ruta = {}
            try:
                self._encolar_ui(self.bloquear, True)
                self._encolar_ui(self.limpiar)
                self._encolar_ui(self.escribir, tr("metadata_header"))
                self._encolar_ui(self.escribir, tr("metadata_only_rename"))
                self._encolar_ui(self.escribir, "=" * 80)
                inicio_operacion = time.monotonic()
                if carpeta_metadatos is not None:
                    libros_proceso = sorted(
                        [
                            p for p in carpeta_metadatos.rglob("*")
                            if (es_libro(p) or p.suffix.lower() in OCR_IMAGE_EXTENSIONS) and not ignorar_por_carpeta(p)
                        ],
                        key=lambda p: str(p).lower()
                    )
                    if not libros_proceso:
                        self._encolar_ui(messagebox.showinfo, tr("no_books_title"), tr("no_books_msg"))
                        return
                else:
                    libros_proceso = list(libros)
                self._encolar_ui(self.escribir, tr("selected_books", count=len(libros_proceso)))
                metadatos_precalculados = self._precalcular_metadatos(libros_proceso, incluir_ocr=True)

                for i, libro in enumerate(libros_proceso, start=1):
                    if self.cancel_token.cancelled:
                        self._encolar_ui(self.escribir, "Operación cancelada; puede reanudarse más adelante.\n")
                        break
                    self._encolar_ui(self.set_progreso, (i - 1) * 100 / max(1, len(libros_proceso)))
                    try:
                        if not libro.exists():
                            sin_cambio += 1
                            self._encolar_ui(self.escribir, tr("does_not_exist", path=libro))
                            continue

                        self._encolar_ui(
                            self.estado_con_tiempo,
                            tr("metadata_status", i=i, total=len(libros_proceso), name=libro.name),
                            i,
                            len(libros_proceso),
                            inicio_operacion,
                        )
                        self._encolar_ui(self.escribir, tr("analyzing", name=libro.name))

                        def cb_web(msg):
                            self._encolar_ui(self.estado_con_tiempo, f"{libro.name} | {msg}", i, len(libros_proceso), inicio_operacion)

                        meta = metadatos_precalculados.get(core.clave_ruta_resuelta(libro))
                        if not meta:
                            meta = obtener_nombre_web(libro, callback=cb_web, cancellation=self.cancel_token)

                        if meta.get("no_es_libro"):
                            sin_cambio += 1
                            self._encolar_ui(self.escribir, tr("not_a_book", name=libro.name))
                            self._encolar_ui(self.escribir, meta.get("motivo", "") + "\n")
                            escribir_historial(
                                "buscar_metadatos", libro, libro, "no_es_libro",
                                meta.get("motivo", ""), nombre_sugerido=libro.name,
                                fuente=meta.get("fuente", ""), confianza=meta.get("confianza", "")
                            )
                            continue

                        if not meta.get("encontrado"):
                            sin_cambio += 1
                            self._encolar_ui(self.escribir, tr("unreliable_leave"))
                            self._encolar_ui(self.escribir, tr("best_confidence", confidence=meta.get("confianza", 0), reason=meta.get("motivo", "")))
                            escribir_historial(
                                "buscar_metadatos", libro, libro, "sin_cambio",
                                meta.get("motivo", ""), nombre_sugerido=libro.name,
                                fuente=meta.get("fuente", ""), confianza=meta.get("confianza", "")
                            )
                            continue

                        nuevo_nombre = meta["nombre_sugerido"]
                        if nuevo_nombre == libro.name:
                            sin_cambio += 1
                            rutas_indice_afectadas.add(libro)
                            metadata_indice_por_ruta[str(libro)] = meta
                            self._encolar_ui(self.escribir, tr("suggested_equal"))
                            escribir_historial(
                                "buscar_metadatos", libro, libro, "sin_cambio_nombre_igual",
                                meta.get("motivo", ""), nombre_sugerido=nuevo_nombre,
                                fuente=meta.get("fuente", ""), confianza=meta.get("confianza", "")
                            )
                            continue

                        origen_original = str(libro)
                        destino = renombrar_en_sitio_seguro(libro, nuevo_nombre, meta.get("motivo", ""))
                        rutas_indice_afectadas.update((origen_original, destino))
                        metadata_indice_por_ruta[str(destino)] = meta
                        registrar_undo(batch_id, "renombrar", origen_original, destino, meta.get("motivo", ""))
                        renombrados += 1

                        self._encolar_ui(self.escribir, tr("renamed"))
                        self._encolar_ui(self.escribir, tr("before", name=Path(origen_original).name))
                        self._encolar_ui(self.escribir, tr("now", name=destino.name))
                        self._encolar_ui(self.escribir, tr("metadata_source_conf", source=meta.get("fuente", ""), confidence=meta.get("confianza", "")))

                        escribir_historial(
                            "buscar_metadatos", origen_original, destino, "renombrado",
                            meta.get("motivo", ""), nombre_sugerido=nuevo_nombre,
                            fuente=meta.get("fuente", ""), confianza=meta.get("confianza", "")
                        )

                    except Exception as e:
                        errores += 1
                        self._encolar_ui(self.escribir, f"{tr('error_title')}: {libro}: {e}\n")
                        escribir_historial("buscar_metadatos", libro, "", "error", str(e))

                self._encolar_ui(self.estado, tr("updating_after_rename"))
                self.indice = core.actualizar_indice_rutas(
                    rutas_indice_afectadas,
                    self.indice,
                    metadata_por_ruta=metadata_indice_por_ruta,
                )

                resumen = tr(
                    "metadata_summary",
                    renamed=renombrados,
                    unchanged=sin_cambio,
                    errors=errores
                )
                self._encolar_ui(self.actualizar_label_indice)
                self._encolar_ui(self.set_progreso, 100)
                self._encolar_ui(self.escribir, "=" * 80)
                self._encolar_ui(self.escribir, resumen)
                self._encolar_ui(self.estado, tr("ready"))
                self._encolar_ui(messagebox.showinfo, tr("result_title"), resumen)

            except Exception as e:
                self._encolar_ui(messagebox.showerror, tr("error_title"), str(e))
                self._encolar_ui(self.estado, tr("error_title"))
            finally:
                self._encolar_ui(self.bloquear, False)

        self._start_worker(tarea)

    def abrir_biblioteca(self):
        if not biblioteca_configurada():
            messagebox.showwarning(tr("missing_library_title"), tr("missing_library_msg"))
            return

        FINAL.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(FINAL))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(FINAL)])
            else:
                subprocess.Popen(["xdg-open", str(FINAL)])
        except Exception as e:
            messagebox.showerror(tr("error_title"), str(e))


def main():
    APP_DATA.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    ventana = tk.Tk()
    App(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()
