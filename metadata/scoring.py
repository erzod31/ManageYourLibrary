from difflib import SequenceMatcher

from core.normalizer import normalizar_texto


ROLES_AUTOR_VALIDOS = {"author", "coauthor", "corporate_author"}
ROLES_CREDITO_SECUNDARIO = {
    "translator",
    "illustrator",
    "foreword_author",
    "editor",
    "compiler",
    "coordinator",
    "publisher",
    "series",
}
UMBRAL_RENOMBRAR_DEFAULT = 90


def default_similitud(a: str, b: str) -> float:
    a = normalizar_texto(a)
    b = normalizar_texto(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _limpiar_valor_default(value: str, max_len=180) -> str:
    value = str(value or "").replace("\r", " ").replace("\n", " ")
    value = " ".join(value.split())
    return value[:max_len].strip()


def _tokens_distintivos_default(titulo: str):
    return [token for token in normalizar_texto(titulo).split() if len(token) > 2]


def _autor_usable_default(autor: str, editorial: str = "", **_kwargs) -> bool:
    autor_norm = normalizar_texto(autor)
    editorial_norm = normalizar_texto(editorial)
    return bool(autor_norm and autor_norm != editorial_norm)


def deduplicar_candidatos(candidatos):
    vistos = set()
    out = []
    for c in candidatos:
        if not c.get("titulo"):
            continue
        clave = (
            normalizar_texto(c.get("titulo", ""))[:80],
            normalizar_texto(c.get("autor", ""))[:40],
            c.get("isbn", ""),
            c.get("fuente", ""),
        )
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append(c)
    return out


def puntuar_candidato(
    libro,
    c,
    datos,
    *,
    candidato_web_parece_ficha_de_autor_func=None,
    linea_parece_nombre_autor_func=None,
    limpiar_nombre_como_pista_func=None,
    limpiar_titulo_para_busqueda_func=None,
    similitud_func=default_similitud,
    similitud_titulo_compacto_func=None,
    similitud_titulo_compacto_datos_func=None,
    titulo_compacto_confirmado_por_candidato_func=None,
    autor_es_usable_func=None,
    tokens_distintivos_titulo_func=None,
    normalizar_texto_func=normalizar_texto,
):
    candidato_web_parece_ficha_de_autor_func = candidato_web_parece_ficha_de_autor_func or (lambda *_args, **_kwargs: False)
    linea_parece_nombre_autor_func = linea_parece_nombre_autor_func or (lambda _texto: False)
    limpiar_nombre_como_pista_func = limpiar_nombre_como_pista_func or (lambda nombre: normalizar_texto_func(nombre))
    limpiar_titulo_para_busqueda_func = limpiar_titulo_para_busqueda_func or (lambda titulo: str(titulo or ""))
    similitud_titulo_compacto_func = similitud_titulo_compacto_func or similitud_func
    similitud_titulo_compacto_datos_func = similitud_titulo_compacto_datos_func or (lambda *_args, **_kwargs: 0)
    titulo_compacto_confirmado_por_candidato_func = titulo_compacto_confirmado_por_candidato_func or (lambda *_args, **_kwargs: False)
    autor_es_usable_func = autor_es_usable_func or _autor_usable_default
    tokens_distintivos_titulo_func = tokens_distintivos_titulo_func or _tokens_distintivos_default

    isbn = c.get("isbn", "")
    isbns_locales = set(datos.get("isbns", []))
    if isbn and isbn in isbns_locales:
        return 98, "ISBN local coincide con la base web"
    if c.get("metodo") == "DOI":
        return 96, "DOI local coincide con la base web"

    titulo = c.get("titulo", "")
    autor = c.get("autor", "")
    if candidato_web_parece_ficha_de_autor_func(titulo, autor, datos):
        return 0, "descartado: ficha de autor, no obra bibliográfica"
    anio_web = c.get("anio", "")
    anio_local = datos.get("anio_local", "") or datos.get("anio_texto", "")
    archivo = limpiar_nombre_como_pista_func(libro.name) or libro.stem
    consulta_titulo = limpiar_titulo_para_busqueda_func(
        datos.get("titulo_local", "")
        or datos.get("titulo_texto", "")
        or datos.get("titulo_nombre", "")
        or archivo
    )
    titulo_local = datos.get("titulo_local", "")
    titulo_texto = datos.get("titulo_texto", "")
    titulo_nombre = datos.get("titulo_nombre", "")
    autor_local = datos.get("autor_local", "")
    autor_ambiguo = datos.get("autor_ambiguo", "")
    autor_nombre = datos.get("autor_nombre", "")

    sim_archivo = similitud_func(titulo, archivo)
    sim_consulta = similitud_func(titulo, consulta_titulo)
    sim_titulo_local = similitud_func(titulo, titulo_local) if titulo_local else 0
    sim_titulo_texto = similitud_func(titulo, titulo_texto) if titulo_texto else 0
    sim_titulo_nombre = similitud_func(titulo, titulo_nombre) if titulo_nombre else 0
    sim_titulo_compacto = 0
    if datos.get("titulo_nombre_compacto"):
        sim_titulo_compacto = max(
            similitud_titulo_compacto_func(titulo, titulo_nombre),
            similitud_titulo_compacto_func(titulo, consulta_titulo),
            similitud_titulo_compacto_datos_func(titulo, datos, libro),
        )
    sim_autor_archivo = similitud_func(autor, archivo) if autor else 0
    sim_autor_local = similitud_func(autor, autor_local) if autor and autor_local else 0
    sim_autor_ambiguo = similitud_func(autor, autor_ambiguo) if autor and autor_ambiguo else 0
    sim_autor_nombre = similitud_func(autor, autor_nombre) if autor and autor_nombre else 0
    mejor_titulo = max(
        sim_archivo,
        sim_consulta,
        sim_titulo_local,
        sim_titulo_texto,
        sim_titulo_nombre,
        sim_titulo_compacto,
    )

    score = mejor_titulo * 78
    titulo_norm = normalizar_texto_func(titulo)
    archivo_norm = normalizar_texto_func(archivo)
    consulta_norm = normalizar_texto_func(consulta_titulo)
    titulo_referencia = titulo_local or titulo_texto or titulo_nombre or consulta_titulo
    ref_tokens = set(tokens_distintivos_titulo_func(titulo_referencia))
    cand_tokens = set(tokens_distintivos_titulo_func(titulo))
    extras_web = cand_tokens - ref_tokens if ref_tokens and cand_tokens else set()

    if not autor and linea_parece_nombre_autor_func(titulo) and max(sim_titulo_local, sim_titulo_texto, sim_titulo_nombre) < 0.72:
        score -= 28
    if ref_tokens and ref_tokens <= cand_tokens and len(extras_web) >= 3 and not (isbn and isbn in isbns_locales):
        score -= min(38, 12 + len(extras_web) * 4)
    if titulo_norm and (titulo_norm in archivo_norm or titulo_norm in consulta_norm):
        score += 8
    if sim_titulo_compacto >= 0.94:
        score += 18
        if titulo_compacto_confirmado_por_candidato_func(datos, c, libro):
            score += 6
    if sim_autor_archivo >= 0.70:
        score += 6
    if sim_autor_local >= 0.80:
        score += 8
    if sim_autor_ambiguo >= 0.55:
        score += 4
    if sim_autor_nombre >= 0.78:
        score += 6
    if (
        not autor
        and autor_local
        and autor_es_usable_func(autor_local, datos.get("editorial_local", "") or datos.get("editorial_texto", ""))
        and mejor_titulo >= 0.95
    ):
        score += 7
    if autor and sim_autor_local >= 0.80 and mejor_titulo >= 0.85:
        score += 12
    if autor and sim_autor_nombre >= 0.78 and mejor_titulo >= 0.86:
        score += 8
    if datos.get("titulo_nombre_compacto") and sim_titulo_compacto >= 0.94:
        autor_referencia = autor_local or autor_nombre or autor_ambiguo
        mejor_autor = max(sim_autor_archivo, sim_autor_local, sim_autor_ambiguo, sim_autor_nombre)
        if autor_referencia and autor and mejor_autor < 0.55:
            score -= 28
        elif autor_referencia and not autor:
            score -= 10
    if mejor_titulo >= 0.90 and autor_es_usable_func(autor, datos.get("editorial_local", "") or datos.get("editorial_texto", "")):
        score += 5
    if isbn:
        score += 3
    if anio_web and anio_local and mejor_titulo < 0.97:
        try:
            diferencia_anio = abs(int(anio_web) - int(anio_local))
        except Exception:
            diferencia_anio = 0
        if diferencia_anio > 10:
            score -= 18
        elif diferencia_anio > 3:
            score -= 10
    if c.get("fuente") in {"Crossref", "Wikidata"} and c.get("metodo") == "Búsqueda":
        score -= 5
    if c.get("fuente") in {"Internet Archive", "Gutendex / Project Gutenberg"}:
        fuente_auxiliar_confirmada = (
            bool(datos.get("isbns") and isbn and isbn in isbns_locales)
            or (sim_autor_local >= 0.80 or sim_autor_nombre >= 0.78 or sim_autor_ambiguo >= 0.60)
            or (mejor_titulo >= 0.94 and (datos.get("titulo_texto") or datos.get("titulo_local")))
        )
        if fuente_auxiliar_confirmada:
            score += 2
        else:
            score -= 9

    return max(0, min(100, round(score, 1))), (
        f"sim_titulo={round(mejor_titulo, 3)}, "
        f"sim_autor={round(max(sim_autor_archivo, sim_autor_local, sim_autor_ambiguo, sim_autor_nombre), 3)}"
    )


def completar_resultado_estandar(resultado, datos, metodo="", accion=None):
    out = dict(resultado)
    out.setdefault("encontrado", False)
    out.setdefault("titulo", "")
    out.setdefault("autor", "")
    out.setdefault("isbn", "")
    out.setdefault("anio", "")
    out.setdefault("editorial", datos.get("editorial_local", "") or datos.get("editorial_texto", ""))
    out.setdefault("idioma", datos.get("idioma", ""))
    out.setdefault("tipo_documento", datos.get("tipo_documento", "documento_desconocido"))
    out.setdefault("fuente", "")
    out.setdefault("confianza", 0)
    out.setdefault("motivo", "")
    out.setdefault("advertencias", [])
    out.setdefault("misma_obra_otro_formato", False)
    out.setdefault("formatos_existentes", [])
    out["metodo"] = metodo or out.get("metodo", "sin_confianza")
    out["accion_recomendada"] = accion or ("renombrar" if out.get("encontrado") else "dejar_igual")
    out["titulo_canonico"] = out.get("titulo", "")
    out.setdefault("error", None)
    return out


def crear_evidencia(
    source,
    field,
    value,
    confidence=0,
    role="",
    page_type="",
    positive=None,
    negative=None,
    warnings=None,
    *,
    limpiar_nombre_archivo_func=None,
):
    cleaner = limpiar_nombre_archivo_func or _limpiar_valor_default
    value = cleaner(value, 180) if isinstance(value, str) else value
    return {
        "source": source,
        "field": field,
        "value": value or "",
        "role": role or "",
        "page_type": page_type or "",
        "confidence": float(confidence or 0),
        "positive_signals": list(positive or []),
        "negative_signals": list(negative or []),
        "warnings": list(warnings or []),
    }


def agregar_evidencia(
    evidencias,
    source,
    field,
    value,
    confidence=0,
    role="",
    page_type="",
    positive=None,
    negative=None,
    warnings=None,
    *,
    limpiar_nombre_archivo_func=None,
):
    if not value:
        return
    key = (source, field, normalizar_texto(value))
    for ev in evidencias:
        if (ev.get("source"), ev.get("field"), normalizar_texto(ev.get("value", ""))) == key:
            if warnings:
                ev["warnings"] = list(dict.fromkeys(list(ev.get("warnings", [])) + list(warnings)))
            if negative:
                ev["negative_signals"] = list(dict.fromkeys(list(ev.get("negative_signals", [])) + list(negative)))
            if positive:
                ev["positive_signals"] = list(dict.fromkeys(list(ev.get("positive_signals", [])) + list(positive)))
            return
    evidencias.append(
        crear_evidencia(
            source,
            field,
            value,
            confidence,
            role=role,
            page_type=page_type,
            positive=positive,
            negative=negative,
            warnings=warnings,
            limpiar_nombre_archivo_func=limpiar_nombre_archivo_func,
        )
    )


def evidencias_desde_resultado_y_candidatos(resultado, candidatos, *, detectar_rol_bibliografico_func=None, limpiar_nombre_archivo_func=None):
    detectar_rol_bibliografico_func = detectar_rol_bibliografico_func or (lambda _value: "")
    evidencias = []
    if resultado.get("titulo"):
        agregar_evidencia(
            evidencias,
            resultado.get("fuente", "decision"),
            "title",
            resultado["titulo"],
            resultado.get("confianza", 0),
            positive=["selected_candidate"],
            limpiar_nombre_archivo_func=limpiar_nombre_archivo_func,
        )
    if resultado.get("autor"):
        agregar_evidencia(
            evidencias,
            resultado.get("fuente", "decision"),
            "author",
            resultado["autor"],
            resultado.get("confianza", 0),
            role=detectar_rol_bibliografico_func(resultado["autor"]),
            positive=["selected_candidate"],
            limpiar_nombre_archivo_func=limpiar_nombre_archivo_func,
        )
    if resultado.get("isbn"):
        agregar_evidencia(
            evidencias,
            resultado.get("fuente", "decision"),
            "isbn",
            resultado["isbn"],
            resultado.get("confianza", 0),
            positive=["selected_candidate"],
            limpiar_nombre_archivo_func=limpiar_nombre_archivo_func,
        )
    for c in (candidatos or [])[:12]:
        fuente = c.get("fuente", "external")
        score = float(c.get("score", 0) or 0)
        base = max(45, min(92, score or 65))
        source_scope = c.get("source_scope", "")
        warnings = []
        if source_scope in {"authority_label", "catalog_auxiliary"} and not (c.get("autor") or c.get("isbn")):
            base = min(base, 58)
            warnings.append("candidato externo incompleto: solo pista de autoridad/catalogo")
        elif source_scope == "authority_label" and not c.get("isbn"):
            base = min(base, 72)
            warnings.append("candidato de autoridad sin edicion confirmada")
        if c.get("titulo"):
            agregar_evidencia(
                evidencias,
                fuente,
                "title",
                c["titulo"],
                base,
                positive=["external_candidate"],
                warnings=warnings,
                limpiar_nombre_archivo_func=limpiar_nombre_archivo_func,
            )
        if c.get("autor"):
            agregar_evidencia(
                evidencias,
                fuente,
                "author",
                c["autor"],
                base,
                role=detectar_rol_bibliografico_func(c["autor"]),
                positive=["external_candidate"],
                warnings=warnings,
                limpiar_nombre_archivo_func=limpiar_nombre_archivo_func,
            )
        if c.get("isbn"):
            agregar_evidencia(
                evidencias,
                fuente,
                "isbn",
                c["isbn"],
                base,
                positive=["external_candidate"],
                warnings=warnings,
                limpiar_nombre_archivo_func=limpiar_nombre_archivo_func,
            )
    return evidencias


def score_campo_consenso(valor_final, evidencias, field, *, similitud_func=default_similitud):
    if not valor_final:
        return 0, []
    total = 0.0
    razones = []
    fuentes = set()
    max_confianza_confirmada = 0.0
    for ev in evidencias:
        if ev.get("field") != field or not ev.get("value"):
            continue
        sim = similitud_func(str(valor_final), str(ev.get("value", "")))
        if sim >= 0.86 or normalizar_texto(valor_final) == normalizar_texto(ev.get("value", "")):
            fuentes.add(ev.get("source", ""))
            max_confianza_confirmada = max(max_confianza_confirmada, float(ev.get("confidence", 0) or 0))
            aporte = min(24, ev.get("confidence", 0) / 5)
            total += aporte
            razones.append(f"{field} confirmado por {ev.get('source')}")
        elif sim < 0.45 and ev.get("confidence", 0) >= 80:
            total -= 12
            razones.append(f"conflicto de {field} con {ev.get('source')}")
    if len(fuentes) >= 2:
        total += 12
        if max_confianza_confirmada >= 80:
            total = max(total, 82)
    elif len(fuentes) == 1:
        total += 5
        if max_confianza_confirmada >= 85:
            total = max(total, 70)
    return max(0, min(100, round(total, 1))), razones[:6]


def calculate_confidence(
    resultado,
    evidencias,
    datos=None,
    *,
    similitud_func=default_similitud,
    roles_credito_secundario=ROLES_CREDITO_SECUNDARIO,
    umbral_renombrar=UMBRAL_RENOMBRAR_DEFAULT,
):
    datos = datos or {}
    titulo = resultado.get("titulo", "")
    autor = resultado.get("autor", "")
    confianza_base = float(resultado.get("confianza", 0) or 0)
    title_score, title_reasons = score_campo_consenso(titulo, evidencias, "title", similitud_func=similitud_func)
    author_score, author_reasons = score_campo_consenso(autor, evidencias, "author", similitud_func=similitud_func)
    isbn_score, isbn_reasons = score_campo_consenso(resultado.get("isbn", ""), evidencias, "isbn", similitud_func=similitud_func)

    if titulo and title_score < confianza_base:
        title_score = min(100, round((title_score + confianza_base) / 2, 1))
    if autor and author_score < confianza_base:
        author_score = min(100, round((author_score + confianza_base) / 2, 1))
    if resultado.get("isbn") and isbn_score < 80:
        isbn_score = 80

    conflicts = []
    warnings = []
    for ev in evidencias:
        if (
            ev.get("field") == "author"
            and ev.get("role") in roles_credito_secundario
            and similitud_func(autor, ev.get("value", "")) >= 0.86
        ):
            conflicts.append(f"Autor candidato aparece como {ev.get('role')}")
        if ev.get("negative_signals"):
            warnings.extend(ev.get("negative_signals", []))
        if ev.get("warnings"):
            warnings.extend(ev.get("warnings", []))
        if (
            ev.get("field") == "author"
            and ev.get("source") in {"metadata_structured", "digital_text"}
            and ev.get("confidence", 0) >= 74
            and autor
            and ev.get("value")
            and similitud_func(autor, ev.get("value", "")) < 0.45
        ):
            conflicts.append(f"Autor contradice evidencia local de {ev.get('source')}")
        if (
            ev.get("field") == "title"
            and ev.get("source") in {"metadata_structured", "digital_text"}
            and ev.get("confidence", 0) >= 78
            and titulo
            and ev.get("value")
            and similitud_func(titulo, ev.get("value", "")) < 0.45
        ):
            conflicts.append(f"Título contradice evidencia local de {ev.get('source')}")

    if datos.get("tipo_documento") == "paper_academico" and resultado.get("fuente") not in {"Crossref", "OpenAlex"}:
        warnings.append("documento académico sin confirmación académica fuerte")

    global_score = round((max(confianza_base, title_score) * 0.45) + (author_score * 0.35) + (isbn_score * 0.20), 1)
    if confianza_base >= umbral_renombrar and titulo and autor and not conflicts:
        global_score = max(global_score, confianza_base)
    if not autor:
        global_score = min(global_score, 74)
    if not titulo:
        global_score = min(global_score, 49)
    if conflicts:
        global_score = min(global_score, 74)

    return {
        "confidence_title": max(0, min(100, title_score)),
        "confidence_author": max(0, min(100, author_score)),
        "confidence_isbn": max(0, min(100, isbn_score)),
        "confidence_total": max(0, min(100, global_score)),
        "reasons": list(dict.fromkeys(title_reasons + author_reasons + isbn_reasons))[:8],
        "conflicts": list(dict.fromkeys(conflicts))[:6],
        "warnings": list(dict.fromkeys(warnings))[:8],
    }


def normalize_book_identity(resultado, datos=None, evidencias=None):
    datos = datos or {}
    evidencias = evidencias or []
    otros_creditos = {
        "traductor": "",
        "editor": "",
        "compilador": "",
        "ilustrador": "",
        "prologuista": "",
    }
    role_map = {
        "translator": "traductor",
        "editor": "editor",
        "compiler": "compilador",
        "illustrator": "ilustrador",
        "foreword_author": "prologuista",
    }
    for ev in evidencias:
        key = role_map.get(ev.get("role", ""))
        if key and not otros_creditos[key]:
            otros_creditos[key] = ev.get("value", "")
    return {
        "titulo": resultado.get("titulo", ""),
        "subtitulo": "",
        "titulo_completo": resultado.get("titulo", ""),
        "autor_principal": resultado.get("autor", ""),
        "autores_secundarios": [],
        "otros_creditos": otros_creditos,
        "coleccion_o_saga": "",
        "editorial": resultado.get("editorial", "") or datos.get("editorial_local", "") or datos.get("editorial_texto", ""),
        "isbn": resultado.get("isbn", ""),
        "anio": resultado.get("anio", ""),
        "idioma_probable": resultado.get("idioma", "") or datos.get("idioma", ""),
        "fuente_titulo": resultado.get("fuente", ""),
        "fuente_autor": resultado.get("fuente", ""),
        "paginas_usadas": list(range(1, int(datos.get("ocr_paginas", 0) or 0) + 1)),
        "candidatos_descartados": [],
        "evidencia": [
            {
                "campo": ev.get("field", ""),
                "valor": ev.get("value", ""),
                "pagina": 0,
                "fuente": ev.get("source", ""),
                "peso": ev.get("confidence", 0),
            }
            for ev in evidencias[:25]
        ],
        "nombre_archivo_sugerido": resultado.get("nombre_sugerido", ""),
    }


def decide_final_action(resultado, consensus):
    if resultado.get("no_es_libro"):
        return "rechazar"
    if consensus.get("conflicts"):
        return "revisar_nuevamente"
    if resultado.get("encontrado") and consensus.get("confidence_total", 0) >= 85 and consensus.get("confidence_title", 0) >= 80:
        if resultado.get("autor") and consensus.get("confidence_author", 0) >= 70:
            return "renombrar"
    if consensus.get("confidence_total", 0) >= 70:
        return "revision_rapida"
    if consensus.get("confidence_total", 0) >= 50:
        return "revisar_nuevamente"
    return "rechazar"
