import re

from core.normalizer import normalizar_texto


def filtrar_consultas_web(consultas, usadas, *, normalizar_texto_func=normalizar_texto):
    consultas_filtradas = []
    vistas_en_esta_llamada = set()
    for query in consultas:
        query = re.sub(r"\s+", " ", str(query or "")).strip()
        key = normalizar_texto_func(query)
        if not query or len(key) < 4 or key in usadas or key in vistas_en_esta_llamada:
            continue
        vistas_en_esta_llamada.add(key)
        consultas_filtradas.append(query)
    return consultas_filtradas


def registrar_consulta_web_usada(datos, usadas, query, *, normalizar_texto_func=normalizar_texto, prefijo=""):
    key = prefijo + normalizar_texto_func(query)
    usadas.add(key)
    datos["_consultas_web_usadas"] = sorted(usadas)
    return key


def invocar_proveedor_seguro(candidatos, proveedor_func, *args, **kwargs):
    try:
        candidatos.extend(proveedor_func(*args, **kwargs))
    except Exception:
        pass
    return candidatos


def construir_proveedores_respaldo_busqueda(
    es_academico,
    *,
    loc_busqueda_func,
    wikidata_busqueda_func,
    crossref_busqueda_func,
    openalex_busqueda_func,
):
    proveedores = [
        ("Library of Congress Search", loc_busqueda_func),
        ("Wikidata Search", wikidata_busqueda_func),
    ]
    if es_academico:
        proveedores.extend([
            ("Crossref Search", crossref_busqueda_func),
            ("OpenAlex Search", openalex_busqueda_func),
        ])
    return proveedores


def resultado_parada_temprana_web(
    libro,
    datos,
    candidatos,
    *,
    umbral,
    hay_candidato_web_fuerte_func,
    deduplicar_candidatos_func,
):
    if not hay_candidato_web_fuerte_func(libro, datos, candidatos, umbral=umbral):
        return None
    return datos, deduplicar_candidatos_func(candidatos)


def invocar_proveedores_con_parada_temprana(
    libro,
    datos,
    candidatos,
    proveedores,
    argumento,
    *,
    umbral,
    invocar_proveedor_seguro_func,
    resultado_parada_temprana_web_func,
    **kwargs,
):
    for _nombre, proveedor_func in proveedores:
        invocar_proveedor_seguro_func(candidatos, proveedor_func, argumento, **kwargs)
    return resultado_parada_temprana_web_func(libro, datos, candidatos, umbral)


def resultado_sin_candidatos(nombre_archivo):
    return {
        "encontrado": False,
        "confianza": 0,
        "nombre_sugerido": nombre_archivo,
        "fuente": "",
        "titulo": "",
        "autor": "",
        "anio": "",
        "isbn": "",
        "motivo": "Sin candidatos web",
    }


def resultado_candidatos_descartados(nombre_archivo):
    return {
        "encontrado": False,
        "confianza": 0,
        "nombre_sugerido": nombre_archivo,
        "fuente": "",
        "titulo": "",
        "autor": "",
        "anio": "",
        "isbn": "",
        "motivo": "Los candidatos web encontrados eran fichas de autor, no libros",
    }


def preparar_candidatos_puntuados(
    candidatos,
    datos,
    libro,
    *,
    limpiar_titulo_legible_func,
    candidato_web_parece_ficha_de_autor_func,
    puntuar_candidato_func,
):
    puntuados = []
    for c in candidatos:
        cc = dict(c)
        if cc.get("titulo") and cc.get("autor"):
            titulo_limpio = limpiar_titulo_legible_func(cc.get("titulo", ""), cc.get("autor", ""))
            if titulo_limpio:
                cc["titulo"] = titulo_limpio
        if candidato_web_parece_ficha_de_autor_func(cc.get("titulo", ""), cc.get("autor", ""), datos):
            continue
        score, motivo = puntuar_candidato_func(libro, cc, datos)
        cc["score"] = score
        cc["motivo"] = motivo
        puntuados.append(cc)
    return puntuados


def agrupar_candidatos_por_titulo(puntuados, *, similitud_func, umbral=0.82):
    grupos = []
    usados = set()
    for i, c in enumerate(puntuados):
        if i in usados:
            continue
        grupo = [c]
        usados.add(i)
        for j, d in enumerate(puntuados):
            if j in usados:
                continue
            if similitud_func(c.get("titulo", ""), d.get("titulo", "")) >= umbral:
                grupo.append(d)
                usados.add(j)
        grupos.append(grupo)
    return grupos


def autores_distintos_en_grupo(grupo):
    autores = []
    for candidato in grupo:
        autor = normalizar_texto(candidato.get("autor", ""))
        if len(autor.split()) < 2:
            continue
        if autor not in autores:
            autores.append(autor)
    return autores


def grupo_tiene_consenso_autor(grupo):
    autores = autores_distintos_en_grupo(grupo)
    if len(autores) <= 1:
        return True
    fuentes_por_autor = {autor: set() for autor in autores}
    for candidato in grupo:
        autor = normalizar_texto(candidato.get("autor", ""))
        fuente = candidato.get("fuente", "")
        for autor_ref in autores:
            if autor and (autor == autor_ref or autor in autor_ref or autor_ref in autor):
                fuentes_por_autor[autor_ref].add(fuente or "fuente_desconocida")
    return any(len(fuentes) >= 2 for fuentes in fuentes_por_autor.values())


def seleccionar_mejor_candidato_por_grupos(grupos, isbns_locales):
    mejor = None
    mejor_confianza = 0
    mejor_motivo = ""

    for grupo in grupos:
        fuentes = sorted(set(g.get("fuente", "") for g in grupo if g.get("fuente")))
        avg_top = sum(sorted([g["score"] for g in grupo], reverse=True)[:3]) / min(3, len(grupo))
        isbn_match = [g for g in grupo if g.get("isbn") and g.get("isbn") in isbns_locales]
        doi_match = [g for g in grupo if g.get("metodo") == "DOI"]

        if len(isbn_match) >= 2:
            confianza = 99
            motivo = f"ISBN confirmado por varias bases: {', '.join(fuentes)}"
        elif len(isbn_match) == 1:
            confianza = 95
            motivo = f"ISBN confirmado por {isbn_match[0].get('fuente')}"
        elif doi_match:
            confianza = 96
            motivo = f"DOI confirmado por {doi_match[0].get('fuente')}"
        else:
            bonus_fuentes = min(12, max(0, len(fuentes) - 1) * 4)
            confianza = min(96, round(avg_top + bonus_fuentes, 1))
            motivo = f"Consenso textual de {len(fuentes)} fuente(s): {', '.join(fuentes)}"
            autores_distintos = autores_distintos_en_grupo(grupo)
            if len(fuentes) >= 2 and len(autores_distintos) >= 2 and not grupo_tiene_consenso_autor(grupo):
                confianza = min(confianza, 88)
                motivo += "; autores contradictorios sin consenso"
            elif len(fuentes) >= 2 and grupo_tiene_consenso_autor(grupo):
                confianza = min(96, confianza + 2)

        candidato_top = sorted(grupo, key=lambda x: x["score"], reverse=True)[0]
        if confianza > mejor_confianza:
            mejor = candidato_top
            mejor_confianza = confianza
            mejor_motivo = motivo

    return mejor, mejor_confianza, mejor_motivo


def resultado_baja_confianza(nombre_archivo, mejor, mejor_confianza, mejor_motivo, *, limpiar_titulo_legible_func):
    titulo_mejor = limpiar_titulo_legible_func(mejor.get("titulo", ""), mejor.get("autor", "")) if mejor else ""
    return {
        "encontrado": False,
        "confianza": mejor_confianza,
        "nombre_sugerido": nombre_archivo,
        "fuente": mejor.get("fuente", "") if mejor else "",
        "titulo": titulo_mejor,
        "autor": mejor.get("autor", "") if mejor else "",
        "anio": mejor.get("anio", "") if mejor else "",
        "isbn": mejor.get("isbn", "") if mejor else "",
        "motivo": mejor_motivo or "Sin coincidencia suficientemente fiable",
    }


def resolver_anio_isbn_final(mejor, datos, isbns_locales):
    anio_local_final = datos.get("anio_local", "") or datos.get("anio_texto", "")
    anio_final = anio_local_final or mejor.get("anio", "")

    isbn_final = mejor.get("isbn", "")
    if isbn_final and isbn_final not in isbns_locales and mejor.get("metodo") != "ISBN":
        isbn_final = ""
    if not isbn_final and datos.get("isbns"):
        isbn_final = datos["isbns"][0]
    if not anio_local_final and not (isbn_final and isbn_final in isbns_locales) and mejor.get("metodo") != "DOI":
        anio_final = ""
    return anio_final, isbn_final


def autor_web_confirmado_por_local(autor_web: str, datos, *, limpiar_nombre_archivo_func, similitud_func) -> bool:
    autor_web = limpiar_nombre_archivo_func(autor_web, 90) if autor_web else ""
    if not autor_web:
        return False
    locales = [datos.get("autor_texto", ""), datos.get("autor_local", ""), datos.get("autor_nombre", "")]
    for autor_local in locales:
        if autor_local and similitud_func(autor_web, autor_local) >= 0.72:
            return True
    return False


def autor_anonimo_confirmado_por_web(autor_web: str, datos, confianza: float = 0, *, autor_es_anonimo_generico_func, umbral_renombrar=90) -> bool:
    if not autor_es_anonimo_generico_func(autor_web):
        return False
    if confianza < umbral_renombrar:
        return False
    if datos.get("isbns") or datos.get("titulo_local") or datos.get("titulo_texto"):
        return True
    return False


def elegir_titulo_final(
    datos,
    titulo_web: str = "",
    *,
    limpiar_titulo_legible_func,
    tokens_distintivos_titulo_func,
    similitud_titulo_compacto_func,
    similitud_titulo_compacto_datos_func,
    similitud_func,
    limpiar_nombre_archivo_func,
    normalizar_texto_func=normalizar_texto,
):
    titulo_web = limpiar_titulo_legible_func(titulo_web) if titulo_web else ""
    titulo_local = limpiar_titulo_legible_func(
        datos.get("titulo_local", "") or datos.get("titulo_texto", "") or datos.get("titulo_nombre", ""),
    )
    if not titulo_web:
        return titulo_local
    if not titulo_local:
        return titulo_web

    web_norm = normalizar_texto_func(titulo_web)
    local_norm = normalizar_texto_func(titulo_local)
    if web_norm and local_norm:
        local_tokens = set(tokens_distintivos_titulo_func(titulo_local))
        web_tokens = set(tokens_distintivos_titulo_func(titulo_web))
        if local_tokens and local_tokens <= web_tokens and len(web_tokens - local_tokens) >= 3:
            return titulo_local
        if datos.get("titulo_nombre_compacto") and max(
            similitud_titulo_compacto_func(titulo_web, titulo_local),
            similitud_titulo_compacto_datos_func(titulo_web, datos),
        ) >= 0.94:
            return titulo_web
        local_mas_especifico = len(local_norm.split()) >= len(web_norm.split())
        if local_mas_especifico and (web_norm in local_norm or similitud_func(titulo_web, titulo_local) >= 0.82):
            return titulo_local

    import re

    segmentos = [
        limpiar_nombre_archivo_func(p, 140)
        for p in re.split(r"\s*(?:;|\||/)\s*", titulo_web)
        if p.strip()
    ]
    if len(segmentos) > 1:
        for segmento in segmentos:
            if similitud_func(segmento, titulo_local) >= 0.88:
                return titulo_local

    return titulo_web
