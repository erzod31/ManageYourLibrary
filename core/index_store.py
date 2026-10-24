import json
from pathlib import Path

from .file_transactions import escritura_atomica_texto


class IndexRecoveryError(ValueError):
    """Existing state must be recovered, never silently replaced with an empty index."""


def validate_index(data):
    if not isinstance(data, dict) or not isinstance(data.get("archivos"), list):
        raise IndexRecoveryError("El catálogo tiene un esquema incompatible. Restaura una copia verificada.")
    if any(not isinstance(row, dict) for row in data["archivos"]):
        raise IndexRecoveryError("El catálogo contiene registros inválidos. No se ha modificado.")
    return data


def cargar_json(ruta, defecto):
    ruta = Path(ruta)
    if not ruta.exists():
        return defecto
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return defecto


def guardar_json(ruta, data):
    texto = json.dumps(data, ensure_ascii=False, indent=2)
    escritura_atomica_texto(ruta, texto, encoding="utf-8")


def cargar_indice(ruta_indice):
    try:
        with Path(ruta_indice).open("r", encoding="utf-8") as stream:
            return validate_index(json.load(stream))
    except FileNotFoundError:
        return {"creado": None, "archivos": []}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IndexRecoveryError("No se puede leer el catálogo. Se conserva el original; "
                                 "restaura una copia de seguridad antes de continuar.") from exc


def guardar_indice(ruta_indice, indice):
    validate_index(indice)
    cargar_indice(ruta_indice)  # Refuse to overwrite corrupt or unreadable existing state.
    guardar_json(ruta_indice, indice)
