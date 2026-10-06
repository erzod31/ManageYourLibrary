import json
from pathlib import Path

from .file_transactions import escritura_atomica_texto


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
    return cargar_json(ruta_indice, {"creado": None, "archivos": []})


def guardar_indice(ruta_indice, indice):
    guardar_json(ruta_indice, indice)
