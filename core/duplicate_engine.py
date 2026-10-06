import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path

from .normalizer import (
    clave_ruta_resuelta,
    normalizar_texto,
    normalizar_titulo_para_dobles_texto,
    quitar_acentos,
)

FORMATO_PREFERENCIA = {
    ".epub": 0,
    ".mobi": 1,
    ".azw3": 2,
    ".azw": 3,
    ".pdf": 4,
    ".fb2": 5,
    ".txt": 6,
    ".rtf": 7,
    ".docx": 8,
    ".doc": 9,
    ".odt": 10,
    ".cbz": 11,
    ".cbr": 12,
    ".djvu": 13,
}

PALABRAS_NO_DISTINTIVAS_TITULO = {
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "el",
    "en", "entre", "hacia", "hasta", "la", "las", "lo", "los", "para",
    "por", "sin", "sobre", "tras", "un", "una", "unos", "unas", "y", "o",
    "the", "an", "and", "of", "to", "in", "on", "for", "from", "with",
    "le", "les", "du", "des", "et",
    "libro", "volumen", "tomo", "parte", "saga", "serie", "coleccion",
}


def default_similitud(a: str, b: str) -> float:
    a = normalizar_texto(a)
    b = normalizar_texto(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _calcular_sha256(ruta: Path, bloque=1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(ruta, "rb") as handle:
        while True:
            chunk = handle.read(bloque)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def diferencia_tamano(a: int, b: int) -> float:
    mayor = max(a, b)
    if mayor == 0:
        return 1.0
    return abs(a - b) / mayor


def numeros_significativos_nombre(nombre: str):
    texto = str(nombre or "")
    texto = re.sub(r"\[[^\]]*\]", " ", texto)
    texto = re.sub(r"\((?:19|20)\d{2}\)", " ", texto)
    texto = re.sub(r"(?i)(?:^|[._\s-])(?:v|ver|version)?\d+(?:[._]\d+)+(?:$|[._\s-])", " ", texto)
    texto = re.sub(r"(?i)(?:^|[_\s-])\d+$", " ", texto)
    texto = quitar_acentos(texto.lower())
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    return set(re.findall(r"\d+", texto))


def numeros_de_titulo_en_conflicto(nombre_a: str, nombre_b: str) -> bool:
    nums_a = numeros_significativos_nombre(nombre_a)
    nums_b = numeros_significativos_nombre(nombre_b)
    if not nums_a or not nums_b:
        return False
    comunes = nums_a & nums_b
    if comunes and (nums_a <= nums_b or nums_b <= nums_a):
        extras = (nums_a | nums_b) - comunes
        return bool(extras and all(n.isdigit() and int(n) <= 20 for n in extras))
    return nums_a != nums_b


def _stem_limpio_para_dobles(nombre: str, parece_autor_func=None, corregir_compactos_titulo_func=None) -> str:
    stem = Path(str(nombre or "")).stem
    stem = re.sub(r"\[[^\]]*\]", " ", stem)
    stem = re.sub(r"\((?:15|16|17|18|19|20)\d{2}\)", " ", stem)
    stem = re.sub(r"(?i)\b(?:autor\s+desconocido|unknown\s+author|anonimo|anonymous)\b", " ", stem)
    partes = [p.strip(" _.,;") for p in re.split(r"\s+-\s+", stem) if p.strip(" _.,;")]
    if len(partes) >= 2:
        izquierda = partes[0]
        derecha = partes[-1]
        izquierda_con_numero_serie = bool(re.search(r"\b\d{1,2}\b", izquierda))
        derecha_con_particula_titulo = bool(
            set(normalizar_texto(derecha).split()) & {"a", "al", "de", "del", "el", "la", "lo", "los", "las", "un", "una"}
        )
        if parece_autor_func and parece_autor_func(izquierda):
            stem = " - ".join(partes[1:])
        elif parece_autor_func and parece_autor_func(derecha) and not (izquierda_con_numero_serie and derecha_con_particula_titulo):
            stem = " - ".join(partes[:-1])
    stem = re.sub(r"(?i)\b(?:copia|copy|duplicado|duplicate|version|edicion|v\d+(?:\.\d+)*)\b", " ", stem)
    stem = re.sub(r"(?i)(?:^|[_\s-])\d+$", " ", stem)
    if corregir_compactos_titulo_func:
        try:
            stem = corregir_compactos_titulo_func(stem)
        # Optional compatibility callback: failure must leave the conservative
        # unmodified title instead of aborting duplicate review.
        except Exception:  # noqa: BLE001,S110
            pass
    return re.sub(r"\s+", " ", stem).strip(" -_.,;")


def titulo_normalizado_para_dobles(nombre: str, parece_autor_func=None, corregir_compactos_titulo_func=None) -> str:
    stem = _stem_limpio_para_dobles(nombre, parece_autor_func, corregir_compactos_titulo_func)
    return normalizar_titulo_para_dobles_texto(stem)


def _variante_titulo_doble_valida(valor: str) -> bool:
    tokens = normalizar_titulo_para_dobles_texto(valor).split()
    if not tokens:
        return False
    if len(tokens) == 1 and len(tokens[0]) < 4:
        return False
    if len(tokens) > 14:
        return False
    ruido = {"orden", "lectura", "cronologia", "indice"}
    return not set(tokens) <= ruido


def variantes_titulo_normalizado_para_dobles(nombre: str, parece_autor_func=None, corregir_compactos_titulo_func=None):
    stem = _stem_limpio_para_dobles(nombre, parece_autor_func, corregir_compactos_titulo_func)
    variantes = []

    def agregar(valor):
        norm = normalizar_titulo_para_dobles_texto(valor)
        if norm and _variante_titulo_doble_valida(norm) and norm not in variantes:
            variantes.append(norm)

    agregar(stem)
    partes = [p.strip(" _.,;") for p in re.split(r"\s+-\s+", stem) if p.strip(" _.,;")]
    if len(partes) >= 2:
        for parte in partes:
            tokens_parte = normalizar_texto(parte).split()
            if len(tokens_parte) <= 1:
                continue
            if not parece_autor_func or not parece_autor_func(parte):
                agregar(parte)
        izquierda = partes[0]
        derecha = partes[-1]
        if re.search(r"\b\d{1,2}\b", izquierda) and _variante_titulo_doble_valida(derecha):
            agregar(derecha)

    return variantes


def similitud_titulo_doble(titulo_a: str, titulo_b: str) -> float:
    a = normalizar_titulo_para_dobles_texto(titulo_a)
    b = normalizar_titulo_para_dobles_texto(titulo_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if set(a.split()) == set(b.split()):
        return 0.99
    return SequenceMatcher(None, a, b).ratio()


def tokens_distintivos_titulo(titulo: str):
    tokens = []
    for token in normalizar_titulo_para_dobles_texto(titulo).split():
        if token in PALABRAS_NO_DISTINTIVAS_TITULO:
            continue
        if token.isdigit():
            tokens.append(token)
            continue
        if len(token) >= 1:
            tokens.append(token)
    return tokens


def titulo_doble_requiere_autor(titulo: str) -> bool:
    tokens = tokens_distintivos_titulo(titulo)
    if len(tokens) <= 1:
        return True
    genericos = {
        "alquimista", "camino", "gen", "capote", "botchan", "principe",
        "medico", "atlantida", "cementerio", "sotano", "viajero",
    }
    return len(tokens) == 2 and len(set(tokens) - genericos) <= 1


def autor_probable_desde_nombre_archivo(nombre: str, extraer_metadatos_desde_nombre_func=None, limpiar_nombre_como_pista_func=None) -> str:
    if not extraer_metadatos_desde_nombre_func:
        return ""
    nombre_limpio = limpiar_nombre_como_pista_func(nombre) if limpiar_nombre_como_pista_func else nombre
    meta = extraer_metadatos_desde_nombre_func(nombre_limpio)
    return meta.get("autor", "")


def autor_doble_es_informativo(autor: str, autores_mononimos=None) -> bool:
    norm = normalizar_texto(autor)
    if not norm:
        return False
    genericos = {
        "autor desconocido", "unknown author", "desconocido", "unknown",
        "anonimo", "anonymous", "varios", "varios autores", "vv aa", "vv a",
        "sin autor", "no author",
    }
    if norm in genericos:
        return False
    autores_mononimos = autores_mononimos or set()
    return not (len(norm.split()) == 1 and norm not in autores_mononimos)


def autores_dobles_compatibles(autor_a: str, autor_b: str, autores_mononimos=None, limpiar_nombre_archivo_func=None, similitud_func=None) -> bool:
    limpiar = limpiar_nombre_archivo_func or (lambda value, max_len=90: str(value or "")[:max_len])
    similitud = similitud_func or default_similitud
    autor_a = limpiar(autor_a, 90) if autor_a else ""
    autor_b = limpiar(autor_b, 90) if autor_b else ""
    if not autor_doble_es_informativo(autor_a, autores_mononimos) or not autor_doble_es_informativo(autor_b, autores_mononimos):
        return False
    norm_a = normalizar_texto(autor_a)
    norm_b = normalizar_texto(autor_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b or set(norm_a.split()) == set(norm_b.split()):
        return True
    return similitud(autor_a, autor_b) >= 0.82


def autores_dobles_en_conflicto(autor_a: str, autor_b: str, autores_mononimos=None, limpiar_nombre_archivo_func=None, similitud_func=None) -> bool:
    if not autor_doble_es_informativo(autor_a, autores_mononimos) or not autor_doble_es_informativo(autor_b, autores_mononimos):
        return False
    return not autores_dobles_compatibles(autor_a, autor_b, autores_mononimos, limpiar_nombre_archivo_func, similitud_func)


def autor_item_para_dobles(item, extraer_metadatos_desde_nombre_func=None, limpiar_nombre_como_pista_func=None) -> str:
    return (
        item.get("autor", "")
        or item.get("autor_normalizado", "")
        or autor_probable_desde_nombre_archivo(item.get("nombre", ""), extraer_metadatos_desde_nombre_func, limpiar_nombre_como_pista_func)
    )


def titulos_dobles_compatibles(titulo_a: str, titulo_b: str, umbral=0.96):
    a = normalizar_titulo_para_dobles_texto(titulo_a)
    b = normalizar_titulo_para_dobles_texto(titulo_b)
    if not a or not b:
        return False, 0.0
    sim = similitud_titulo_doble(a, b)
    if a == b or set(a.split()) == set(b.split()):
        return True, max(sim, 0.99)
    if sim < umbral:
        return False, sim

    tokens_a = tokens_distintivos_titulo(a)
    tokens_b = tokens_distintivos_titulo(b)
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    if not set_a or not set_b:
        return False, sim
    comunes = set_a & set_b
    cobertura_a = len(comunes) / len(set_a)
    cobertura_b = len(comunes) / len(set_b)

    if min(len(set_a), len(set_b)) <= 1 and max(cobertura_a, cobertura_b) == 1 and min(cobertura_a, cobertura_b) < 0.82:
        return False, sim
    if cobertura_a < 0.82 or cobertura_b < 0.82:
        return False, sim
    return True, sim


def mtime_item(item) -> float:
    try:
        mtime = float(item.get("mtime", 0))
        if mtime:
            return mtime
        return Path(item.get("ruta", "")).stat().st_mtime
    except (OSError, TypeError, ValueError):
        return 0.0


def formato_rank(extension: str) -> int:
    return FORMATO_PREFERENCIA.get(str(extension or "").lower(), 99)


def elegir_item_preferido_por_fecha_y_formato(a, b):
    def quality(item):
        score = 0.0
        if item.get("sha256"):
            score += 5
        if item.get("isbn") or item.get("identificador"):
            score += 25
        if item.get("titulo") or item.get("titulo_real"):
            score += 8
        if item.get("autor"):
            score += 8
        score += min(40.0, float(item.get("confianza_global", item.get("confianza", 0)) or 0) * 0.4)
        score += max(0, 14 - formato_rank(item.get("extension", "")))
        if item.get("integrity_valid") is False:
            score -= 100
        return score

    quality_a = quality(a)
    quality_b = quality(b)
    if abs(quality_a - quality_b) >= 1:
        return "a" if quality_a > quality_b else "b"

    # Modification time is only a final tie-breaker; copying a file must not
    # make it the preferred edition by itself.
    mtime_a = mtime_item(a)
    mtime_b = mtime_item(b)
    rank_a = formato_rank(a.get("extension", ""))
    rank_b = formato_rank(b.get("extension", ""))
    if rank_a != rank_b:
        return "a" if rank_a < rank_b else "b"
    if abs(mtime_a - mtime_b) > 2:
        return "a" if mtime_a > mtime_b else "b"
    return "a"


def _autor_kwargs(kwargs):
    return {
        "autores_mononimos": kwargs.get("autores_mononimos"),
        "limpiar_nombre_archivo_func": kwargs.get("limpiar_nombre_archivo_func"),
        "similitud_func": kwargs.get("similitud_func"),
    }


def coincidencias_por_titulo_real(titulo: str, indice, umbral=0.96, autor: str = "", excluir_rutas=None, **kwargs):
    variantes_titulo = variantes_titulo_normalizado_para_dobles(
        titulo,
        kwargs.get("parece_autor_func"),
        kwargs.get("corregir_compactos_titulo_func"),
    )
    if not variantes_titulo:
        return []
    path_key_func = kwargs.get("path_key_func") or clave_ruta_resuelta
    ignorar_por_carpeta_func = kwargs.get("ignorar_por_carpeta_func") or (lambda _ruta: False)
    rutas_excluidas = {path_key_func(ruta) for ruta in (excluir_rutas or [])}
    requiere_autor = titulo_doble_requiere_autor(titulo)
    coincidencias = []
    for item in indice.get("archivos", []):
        ruta = Path(item.get("ruta", ""))
        if not ruta.exists() or ignorar_por_carpeta_func(ruta):
            continue
        if path_key_func(ruta) in rutas_excluidas:
            continue
        autor_item = autor_item_para_dobles(
            item,
            kwargs.get("extraer_metadatos_desde_nombre_func"),
            kwargs.get("limpiar_nombre_como_pista_func"),
        )
        if autor and autor_item and autores_dobles_en_conflicto(autor, autor_item, **_autor_kwargs(kwargs)):
            continue
        if requiere_autor and autor and not autores_dobles_compatibles(
            autor,
            autor_item,
            **_autor_kwargs(kwargs),
        ):
            continue
        variantes_item = []
        for valor in item.get("titulos_normalizados", []) or []:
            if valor and valor not in variantes_item:
                variantes_item.append(valor)
        titulo_item = item.get("titulo_normalizado") or titulo_normalizado_para_dobles(
            item.get("nombre", ""),
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        )
        if titulo_item and titulo_item not in variantes_item:
            variantes_item.append(titulo_item)
        for valor in variantes_titulo_normalizado_para_dobles(
            item.get("nombre", ""),
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        ):
            if valor not in variantes_item:
                variantes_item.append(valor)
        if not variantes_item:
            continue
        if numeros_de_titulo_en_conflicto(titulo, item.get("nombre", "")):
            continue
        sim = 0.0
        compatible = False
        for a in variantes_titulo:
            for b in variantes_item:
                ok, score = titulos_dobles_compatibles(a, b, umbral=umbral)
                sim = max(sim, score)
                if ok:
                    compatible = True
        if compatible:
            copia = dict(item)
            copia["similitud_titulo"] = round(sim, 3)
            coincidencias.append(copia)
    return sorted(coincidencias, key=lambda x: (-float(x.get("similitud_titulo", 0)), formato_rank(x.get("extension", "")), x.get("ruta", "").lower()))


def item_indice_ligero_desde_ruta(ruta: Path, titulo_real: str = "", **kwargs):
    stat = ruta.stat()
    titulo_base = titulo_real or ruta.name
    variantes_base = variantes_titulo_normalizado_para_dobles(
        titulo_base,
        kwargs.get("parece_autor_func"),
        kwargs.get("corregir_compactos_titulo_func"),
    )
    variantes_nombre = variantes_titulo_normalizado_para_dobles(
        ruta.name,
        kwargs.get("parece_autor_func"),
        kwargs.get("corregir_compactos_titulo_func"),
    )
    extraer = kwargs.get("extraer_metadatos_desde_nombre_func")
    limpiar_pista = kwargs.get("limpiar_nombre_como_pista_func") or (lambda value: value)
    meta_nombre = extraer(limpiar_pista(ruta.name)) if extraer else {}
    return {
        "ruta": str(ruta),
        "nombre": ruta.name,
        "extension": ruta.suffix.lower(),
        "tamano_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": "",
        "nombre_normalizado": normalizar_texto(ruta.name),
        "autor": meta_nombre.get("autor", ""),
        "autor_normalizado": normalizar_texto(meta_nombre.get("autor", "")),
        "titulo_normalizado": titulo_normalizado_para_dobles(
            titulo_base,
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        ),
        "titulos_normalizados": variantes_base + [v for v in variantes_nombre if v not in variantes_base],
    }


def item_indice_desde_ruta(ruta: Path, titulo_real: str = "", **kwargs):
    stat = ruta.stat()
    extraer = kwargs.get("extraer_metadatos_desde_nombre_func")
    limpiar_pista = kwargs.get("limpiar_nombre_como_pista_func") or (lambda value: value)
    meta_nombre = extraer(limpiar_pista(ruta.name)) if extraer else {}
    hash_func = kwargs.get("calcular_hash_func")
    return {
        "ruta": str(ruta),
        "nombre": ruta.name,
        "extension": ruta.suffix.lower(),
        "tamano_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": hash_func(ruta) if hash_func else "",
        "nombre_normalizado": normalizar_texto(ruta.name),
        "autor": meta_nombre.get("autor", ""),
        "autor_normalizado": normalizar_texto(meta_nombre.get("autor", "")),
        "titulo_normalizado": titulo_normalizado_para_dobles(
            titulo_real or ruta.name,
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        ),
        "titulos_normalizados": variantes_titulo_normalizado_para_dobles(
            titulo_real or ruta.name,
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        ),
    }


def verificar_libro(libro: Path, indice, **kwargs):
    tr_func = kwargs.get("tr_func") or (lambda key, **params: key.format(**params))
    if not libro.exists():
        return {"estado": "error", "mensaje": tr_func("file_missing_msg", path=libro), "exactos": [], "posibles": []}
    es_libro_func = kwargs.get("es_libro_func") or (lambda _ruta: True)
    if not es_libro_func(libro):
        return {"estado": "error", "mensaje": tr_func("incompatible_book_msg", path=libro), "exactos": [], "posibles": []}
    biblioteca_configurada_func = kwargs.get("biblioteca_configurada_func") or (lambda: False)
    en_raiz_biblioteca_func = kwargs.get("en_raiz_biblioteca_func") or (lambda _ruta: False)
    en_carpeta_revisar_nuevamente_func = kwargs.get("en_carpeta_revisar_nuevamente_func") or (lambda _ruta: False)
    if biblioteca_configurada_func() and en_raiz_biblioteca_func(libro) and not en_carpeta_revisar_nuevamente_func(libro):
        return {"estado": "ya_esta_dentro", "mensaje": f"Este archivo ya está dentro de la biblioteca:\n{libro}", "exactos": [], "posibles": []}

    stat = libro.stat()
    sha_nuevo = None
    nombre_norm = normalizar_texto(libro.name)
    titulo_norm = titulo_normalizado_para_dobles(
        libro.name,
        kwargs.get("parece_autor_func"),
        kwargs.get("corregir_compactos_titulo_func"),
    )
    variantes_titulo = variantes_titulo_normalizado_para_dobles(
        libro.name,
        kwargs.get("parece_autor_func"),
        kwargs.get("corregir_compactos_titulo_func"),
    )
    extraer = kwargs.get("extraer_metadatos_desde_nombre_func")
    limpiar_pista = kwargs.get("limpiar_nombre_como_pista_func") or (lambda value: value)
    meta_nuevo = extraer(limpiar_pista(libro.name)) if extraer else {}
    autor_nuevo = meta_nuevo.get("autor", "")
    exactos = []
    posibles = []
    ignorar_por_carpeta_func = kwargs.get("ignorar_por_carpeta_func") or (lambda _ruta: False)
    calcular_hash_func = kwargs.get("calcular_hash_func") or _calcular_sha256
    similitud_func = kwargs.get("similitud_func") or default_similitud
    umbral_alto = kwargs.get("umbral_nombre_alto", 0.93)
    umbral_medio = kwargs.get("umbral_nombre_medio", 0.86)
    umbral_tamano = kwargs.get("umbral_tamano", 0.18)

    for item in indice.get("archivos", []):
        ruta_existente = Path(item.get("ruta", ""))
        if not ruta_existente.exists():
            continue
        if ignorar_por_carpeta_func(ruta_existente):
            continue
        try:
            if ruta_existente.resolve() == libro.resolve():
                continue
        except (OSError, RuntimeError):
            pass

        tamano_item = item.get("tamano_bytes", None)
        try:
            posible_exacto = tamano_item in (None, "") or int(tamano_item) == stat.st_size
        except (TypeError, ValueError):
            posible_exacto = True

        if posible_exacto and item.get("sha256"):
            if sha_nuevo is None:
                sha_nuevo = calcular_hash_func(libro)
            # A persisted hash is only a hint. Revalidate the live library file
            # before allowing an exact-duplicate decision.
            sha_existente = calcular_hash_func(ruta_existente)
            stat_existente = ruta_existente.stat()
            item["sha256"] = sha_existente
            item["tamano_bytes"] = stat_existente.st_size
            item["mtime"] = stat_existente.st_mtime
            if sha_existente == sha_nuevo:
                exactos.append(item)
                continue

        nombre_existente = item.get("nombre_normalizado", "")
        variantes_existente = []
        for valor in item.get("titulos_normalizados", []) or []:
            if valor and valor not in variantes_existente:
                variantes_existente.append(valor)
        titulo_existente = item.get("titulo_normalizado") or titulo_normalizado_para_dobles(
            item.get("nombre", ""),
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        )
        if titulo_existente and titulo_existente not in variantes_existente:
            variantes_existente.append(titulo_existente)
        for valor in variantes_titulo_normalizado_para_dobles(
            item.get("nombre", ""),
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        ):
            if valor not in variantes_existente:
                variantes_existente.append(valor)
        sim = similitud_func(nombre_norm, nombre_existente)
        sim_titulo = 0.0
        titulo_compatible = False
        pares_titulo = [(a, b) for a in variantes_titulo for b in variantes_existente] or [(titulo_norm, titulo_existente)]
        for a, b in pares_titulo:
            ok, score_titulo = titulos_dobles_compatibles(a, b, umbral=0.96)
            sim_titulo = max(sim_titulo, score_titulo)
            if ok:
                titulo_compatible = True
        dif = diferencia_tamano(stat.st_size, int(item.get("tamano_bytes", 0)))
        mismo_nombre = libro.name.lower() == item.get("nombre", "").lower()
        mismo_titulo = titulo_norm and titulo_existente and titulo_compatible
        conflicto_numerico = numeros_de_titulo_en_conflicto(libro.name, item.get("nombre", ""))
        autor_existente = autor_item_para_dobles(item, extraer, limpiar_pista)
        conflicto_autor = autores_dobles_en_conflicto(autor_nuevo, autor_existente, **_autor_kwargs(kwargs))
        if mismo_titulo and (
            conflicto_autor
            or (titulo_doble_requiere_autor(titulo_norm) and not autores_dobles_compatibles(autor_nuevo, autor_existente, **_autor_kwargs(kwargs)))
        ):
            mismo_titulo = False

        if not conflicto_numerico and (mismo_titulo or mismo_nombre or sim >= umbral_alto or (sim >= umbral_medio and dif <= umbral_tamano)):
            copia = dict(item)
            copia["similitud_nombre"] = round(sim, 3)
            copia["similitud_titulo"] = round(sim_titulo, 3)
            copia["diferencia_tamano"] = round(dif, 3)
            posibles.append(copia)

    posibles = sorted(posibles, key=lambda x: (-float(x.get("similitud_nombre", 0)), float(x.get("diferencia_tamano", 1)), x.get("ruta", "").lower()))

    if exactos:
        return {"estado": "duplicado_exacto", "mensaje": tr_func("duplicate_exact_msg", name=libro.name), "exactos": exactos, "posibles": posibles}
    if posibles:
        return {"estado": "posible_duplicado", "mensaje": tr_func("possible_duplicate_msg", name=libro.name), "exactos": [], "posibles": posibles}
    return {"estado": "unico", "mensaje": tr_func("unique_book_msg", name=libro.name), "exactos": [], "posibles": []}


def _clave_rapida_duplicado(nombre_normalizado: str):
    tokens = [t for t in str(nombre_normalizado or "").split() if len(t) >= 3]
    numeros = re.findall(r"\d+", str(nombre_normalizado or ""))
    if numeros:
        return "num:" + numeros[0]
    return tokens[0] if tokens else ""


def variantes_item_para_dobles(item, **kwargs):
    variantes = []

    def agregar(valor):
        for variante in variantes_titulo_normalizado_para_dobles(
            valor,
            kwargs.get("parece_autor_func"),
            kwargs.get("corregir_compactos_titulo_func"),
        ):
            if variante and variante not in variantes:
                variantes.append(variante)

    for campo in ("titulo_real", "titulo", "titulo_clave", "titulo_normalizado"):
        agregar(item.get(campo, ""))

    for valor in item.get("titulos_normalizados", []) or []:
        agregar(valor)

    agregar(item.get("nombre", ""))
    return variantes


def claves_item_para_dobles(item, **kwargs):
    claves = []
    for variante in variantes_item_para_dobles(item, **kwargs):
        clave = _clave_rapida_duplicado(variante)
        if clave and clave not in claves:
            claves.append(clave)
    return claves


def buscar_dobles_biblioteca(indice, limite=None, ignorar_carpetas=True, **kwargs):
    ignorar_por_carpeta_func = kwargs.get("ignorar_por_carpeta_func") or (lambda _ruta: False)
    cancellation = kwargs.get("cancellation")
    archivos = []
    for item in indice.get("archivos", []):
        if cancellation:
            cancellation.raise_if_cancelled()
        ruta = Path(item.get("ruta", ""))
        if not ruta.exists() or (ignorar_carpetas and ignorar_por_carpeta_func(ruta)):
            continue
        archivos.append(item)

    resultados = []
    vistos = set()

    calcular_hash_func = kwargs.get("calcular_hash_func") or _calcular_sha256
    por_hash = {}
    for item in archivos:
        if cancellation:
            cancellation.raise_if_cancelled()
        ruta = Path(item.get("ruta", ""))
        try:
            sha = calcular_hash_func(ruta)
            stat = ruta.stat()
            item["sha256"] = sha
            item["tamano_bytes"] = stat.st_size
            item["mtime"] = stat.st_mtime
        except (OSError, ValueError):
            continue
        if sha:
            por_hash.setdefault(sha, []).append(item)

    for grupo in por_hash.values():
        if cancellation:
            cancellation.raise_if_cancelled()
        if len(grupo) < 2:
            continue
        base = grupo[0]
        for otro in grupo[1:]:
            clave = tuple(sorted([base.get("ruta", ""), otro.get("ruta", "")]))
            if clave in vistos:
                continue
            vistos.add(clave)
            resultados.append({
                "tipo": "duplicado_exacto",
                "confianza": 100,
                "motivo": "Hash SHA-256 idéntico",
                "archivo_a": base,
                "archivo_b": otro,
                "recomendado": elegir_item_preferido_por_fecha_y_formato(base, otro),
            })
            if limite is not None and len(resultados) >= limite:
                return resultados

    buckets = {}
    for item in archivos:
        variantes_item = variantes_item_para_dobles(item, **kwargs)
        if variantes_item:
            item["titulo_normalizado"] = variantes_item[0]
        for clave in claves_item_para_dobles(item, **kwargs):
            buckets.setdefault(clave, []).append(item)

    for grupo in buckets.values():
        if cancellation:
            cancellation.raise_if_cancelled()
        if len(grupo) < 2:
            continue
        for i, a in enumerate(grupo):
            for b in grupo[i + 1:]:
                clave = tuple(sorted([a.get("ruta", ""), b.get("ruta", "")]))
                if clave in vistos:
                    continue
                if numeros_de_titulo_en_conflicto(a.get("nombre", ""), b.get("nombre", "")):
                    continue
                variantes_a = variantes_item_para_dobles(a, **kwargs) or [titulo_normalizado_para_dobles(
                    a.get("nombre", ""),
                    kwargs.get("parece_autor_func"),
                    kwargs.get("corregir_compactos_titulo_func"),
                )]
                variantes_b = variantes_item_para_dobles(b, **kwargs) or [titulo_normalizado_para_dobles(
                    b.get("nombre", ""),
                    kwargs.get("parece_autor_func"),
                    kwargs.get("corregir_compactos_titulo_func"),
                )]
                compatible = False
                sim = 0.0
                titulo_a = variantes_a[0] if variantes_a else ""
                titulo_b = variantes_b[0] if variantes_b else ""
                for posible_a in variantes_a:
                    for posible_b in variantes_b:
                        ok, score = titulos_dobles_compatibles(posible_a, posible_b, umbral=0.96)
                        if ok and score >= sim:
                            compatible = True
                            sim = score
                            titulo_a = posible_a
                            titulo_b = posible_b
                        elif score > sim:
                            sim = score
                autor_a = autor_item_para_dobles(
                    a,
                    kwargs.get("extraer_metadatos_desde_nombre_func"),
                    kwargs.get("limpiar_nombre_como_pista_func"),
                )
                autor_b = autor_item_para_dobles(
                    b,
                    kwargs.get("extraer_metadatos_desde_nombre_func"),
                    kwargs.get("limpiar_nombre_como_pista_func"),
                )
                if compatible and autores_dobles_en_conflicto(autor_a, autor_b, **_autor_kwargs(kwargs)):
                    continue
                if compatible and (
                    titulo_doble_requiere_autor(titulo_a)
                    or titulo_doble_requiere_autor(titulo_b)
                ) and not autores_dobles_compatibles(autor_a, autor_b, **_autor_kwargs(kwargs)):
                    continue
                if compatible:
                    vistos.add(clave)
                    recomendado = elegir_item_preferido_por_fecha_y_formato(a, b)
                    resultados.append({
                        "tipo": "duplicado_de_titulo",
                        "confianza": round(sim * 100, 1),
                        "motivo": f"Mismo título: {round(sim * 100, 1)}% | conservar por fecha más reciente; si empata, preferir EPUB y luego MOBI",
                        "archivo_a": a,
                        "archivo_b": b,
                        "recomendado": recomendado,
                    })
                if limite is not None and len(resultados) >= limite:
                    return resultados

    return resultados


def ruta_en_carpeta(ruta, carpeta, path_key_func=None) -> bool:
    path_key_func = path_key_func or clave_ruta_resuelta
    ruta_key = str(path_key_func(ruta) or "").rstrip("\\/")
    carpeta_key = str(path_key_func(carpeta) or "").rstrip("\\/")
    if not ruta_key or not carpeta_key:
        return False
    return ruta_key == carpeta_key or ruta_key.startswith(
        (carpeta_key + "\\", carpeta_key + "/")
    )


def item_en_carpeta(item, carpeta, path_key_func=None) -> bool:
    return ruta_en_carpeta((item or {}).get("ruta", ""), carpeta, path_key_func)


def doble_entre_carpetas(doble, carpeta_a, carpeta_b, path_key_func=None) -> bool:
    archivo_a = (doble or {}).get("archivo_a") or {}
    archivo_b = (doble or {}).get("archivo_b") or {}
    a_en_a = item_en_carpeta(archivo_a, carpeta_a, path_key_func)
    a_en_b = item_en_carpeta(archivo_a, carpeta_b, path_key_func)
    b_en_a = item_en_carpeta(archivo_b, carpeta_a, path_key_func)
    b_en_b = item_en_carpeta(archivo_b, carpeta_b, path_key_func)
    return (a_en_a and b_en_b) or (a_en_b and b_en_a)


def filtrar_dobles_entre_carpetas(dobles, carpeta_a, carpeta_b, path_key_func=None):
    return [
        doble for doble in (dobles or [])
        if doble_entre_carpetas(doble, carpeta_a, carpeta_b, path_key_func)
    ]
