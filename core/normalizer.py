import os
import re
import unicodedata
from pathlib import Path


def quitar_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def texto_busqueda_unicode(texto: str) -> str:
    texto = quitar_acentos(str(texto).casefold())
    texto = re.sub(r"\[[^\]]*\]", " ", texto)
    texto = re.sub(r"\([^\)]*\)", " ", texto)
    texto = re.sub(r"[_\-.]+", " ", texto)
    return "".join(c if c.isalnum() else " " for c in texto)


def normalizar_texto(texto: str) -> str:
    texto = texto_busqueda_unicode(texto)
    ruido = {
        "ebook", "pdf", "epub", "mobi", "azw", "azw3", "scan", "digital",
        "spanish", "espanol", "español", "castellano", "libro", "books", "book",
        "copia", "copy", "duplicado", "duplicate", "version", "edicion",
        "vol", "volume", "tomo", "completo", "complete",
    }
    tokens = [t for t in texto.split() if t not in ruido and len(t) > 1]
    return " ".join(tokens)


def normalizar_titulo_para_dobles_texto(texto: str) -> str:
    texto = texto_busqueda_unicode(texto)
    ruido = {
        "ebook", "pdf", "epub", "mobi", "azw", "azw3", "scan", "digital",
        "spanish", "espanol", "español", "castellano", "books", "book",
        "copia", "copy", "duplicado", "duplicate", "version", "edicion",
        "vol", "volume", "tomo", "completo", "complete",
    }
    tokens = [t for t in texto.split() if t not in ruido]
    return " ".join(tokens)


def clave_ruta_resuelta(ruta) -> str:
    try:
        valor = str(Path(ruta).resolve())
    except (OSError, RuntimeError, TypeError, ValueError):
        valor = str(ruta or "")
    return valor.lower() if os.name == "nt" else valor
