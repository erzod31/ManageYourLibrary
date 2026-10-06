"""Exercise an empty Tk workspace with isolated state, never an existing profile."""
from __future__ import annotations

import json
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REQUIRED_CHECKS = {"clean_defaults", "empty_workspace", "fresh_state",
                   "no_background_operations", "no_automatic_network"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_checks(version: str) -> dict:
    report = {"version": version, "frozen": bool(getattr(sys, "frozen", False)),
              "created_at": datetime.now(timezone.utc).isoformat(), "checks": {}}
    checks = report["checks"]
    # This diagnostic must run in a fresh CLI process, before profile-dependent
    # modules have captured paths. Never redirect a running user's workspace.
    if "library_core" in sys.modules or "library_app" in sys.modules:
        report.update(passed=False, error="Requires a fresh process before application imports")
        return report

    network_attempts = []
    callback_errors = []

    def deny_network(*args, **kwargs):
        network_attempts.append(True)
        raise RuntimeError("Unexpected network activity during first launch")

    with tempfile.TemporaryDirectory(prefix="myl_first_use_") as directory:
        base = Path(directory)
        state = base / "fresh-profile"
        payload = base / "payload"
        payload.mkdir()
        from core import config_store
        import cache_engine
        import ai_paths

        with (patch.object(config_store, "app_data_dir", return_value=state),
              patch.object(cache_engine, "APP_DATA", state),
              patch.object(cache_engine, "DB_PATH", state / "analysis_cache.sqlite3"),
              patch.object(ai_paths, "app_data_dir", return_value=state),
              patch.object(ai_paths, "app_root", return_value=payload),
              patch.object(socket.socket, "connect", side_effect=deny_network),
              patch.object(socket, "create_connection", side_effect=deny_network)):
            import library_core as core
            from library_app import App
            import tkinter as tk

            root = None
            app = None
            try:
                require(core.APP_DATA == state, "State is not isolated")
                require(core.FINAL is None and not core.biblioteca_configurada(), "Library already selected")
                require(core.cargar_indice().get("archivos") == [], "Index is not empty")
                require(not core.CONFIG_JSON.exists(), "Unexpected configuration")
                require(core.cargar_configuracion_operacion() == config_store.DEFAULT_OPERATION_CONFIG, "Non-default preferences")
                require(core.cargar_configuracion_ia()["enabled"] is False, "Local AI enabled by default")
                require(core.IDIOMA_ACTUAL == core._idioma_sistema(), "Language does not follow the system")
                checks["clean_defaults"] = "passed"

                root = tk.Tk()
                root.withdraw()
                root.report_callback_exception = lambda kind, value, tb: callback_errors.append(kind.__name__)
                app = App(root)

                def verify():
                    try:
                        require(not callback_errors, "Tk callback error")
                        require(app.indice.get("archivos") == [], "Startup imported books")
                        require(app.biblioteca_var.get() == "", "Library field is prefilled")
                        require(app.workspace.filtered_items == [], "Workspace contains books")
                        require(app.workspace.selected_item is None, "A book is preselected")
                        require(app.workspace._empty_library_frame is not None, "Empty-state guidance missing")
                        require(app.workspace._empty_library_action.winfo_manager() == "pack", "Choose-folder action missing")
                        checks["empty_workspace"] = "passed"
                        require(not app.trabajando, "Automatic book operation started")
                        require(not core.operation_plan_store().list_resumable(), "Pending plans found")
                        require(core.obtener_ultima_accion_undo() == (None, []), "Undo history found")
                        checks["no_background_operations"] = "passed"
                        require(not network_attempts, "Automatic network request attempted")
                        checks["no_automatic_network"] = "passed"
                        require(not core.CONFIG_JSON.exists(), "Configuration written before user choice")
                        require(not core.INDICE_JSON.exists(), "Index written before user choice")
                        require(not core.HISTORIAL_CSV.exists(), "History written before user choice")
                        require(all(count == 0 for count in core.catalog_store().stats().values()), "Catalog is not empty")
                        require(not any(path.is_file() for path in payload.rglob("*")), "State file written beside the executable")
                        checks["fresh_state"] = "passed"
                    except Exception as exc:
                        report["error"] = f"{type(exc).__name__}: {exc}"
                    finally:
                        root.quit()

                root.after(1400, verify)
                root.after(6000, root.quit)
                root.mainloop()
            except Exception as exc:
                report["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if app is not None:
                    app.cerrar_aplicacion()
                elif root is not None:
                    root.destroy()

    report["passed"] = set(checks) == REQUIRED_CHECKS and all(value == "passed" for value in checks.values())
    report["manual_installed_ui"] = "not_run"
    return report


def run_and_record(output: Path, *, version: str) -> int:
    report = run_checks(version)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1
