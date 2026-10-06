import hashlib
import json
import re
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime


WEB_CACHE = {}
WEB_CACHE_LOCK = threading.RLock()
PROVIDER_HEALTH = {}
MAX_WEB_CACHE_ENTRIES = 2500
PAUSA_WEB = 0.20
HTTP_TIMEOUT_SECONDS = 18
USER_AGENT = "ManageYourLibrary/0.5 (desktop metadata lookup; +https://github.com/erzod31/ManageYourLibrary)"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
CIRCUIT_FAILURE_LIMIT = 3
CIRCUIT_COOLDOWN_SECONDS = 60
OPENLIBRARY_SEARCH_FIELDS = (
    "title,author_name,author_key,first_publish_year,isbn,key,language,edition_count,cover_i,"
    "editions,editions.key,editions.title,editions.publish_date,editions.publisher,"
    "editions.language,editions.isbn"
)
WIKIDATA_DEFAULT_LANGUAGES = ("es", "en", "fr")


def limpiar_isbn_default(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def limpiar_nombre_archivo_default(texto: str, max_len=170) -> str:
    texto = str(texto or "").strip()
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = texto.rstrip(". ")
    if len(texto) > max_len:
        texto = texto[:max_len].rstrip()
    return texto or "SIN_TITULO"


def autor_desde_nombre_es_usable_default(autor: str, permitir_mononimo: bool = True) -> bool:
    autor = limpiar_nombre_archivo_default(autor, 90) if autor else ""
    if not autor:
        return False
    tokens = autor.split()
    return len(tokens) >= 2 or (permitir_mononimo and len(tokens) == 1 and len(tokens[0]) >= 4)


def cache_key_web(url: str) -> str:
    return hashlib.sha256(str(url or "").encode("utf-8", errors="ignore")).hexdigest()


def prune_web_cache(max_entries=MAX_WEB_CACHE_ENTRIES):
    with WEB_CACHE_LOCK:
        if len(WEB_CACHE) <= max_entries:
            return
        keep_from = max(0, len(WEB_CACHE) - max_entries)
        for key in list(WEB_CACHE.keys())[:keep_from]:
            WEB_CACHE.pop(key, None)


def provider_health():
    with WEB_CACHE_LOCK:
        return {key: dict(value) for key, value in PROVIDER_HEALTH.items()}


def _record_health(provider, status, error=""):
    with WEB_CACHE_LOCK:
        current = PROVIDER_HEALTH.setdefault(provider, {"failures": 0})
        if status == "ok":
            current["failures"] = 0
        elif status not in {"no_result", "offline", "circuit_open"}:
            current["failures"] = int(current.get("failures", 0)) + 1
        current.update({"status": status, "error": str(error or "")[:500], "updated_at": time.time()})


def _circuit_is_open(provider):
    with WEB_CACHE_LOCK:
        state = PROVIDER_HEALTH.get(provider, {})
        return (
            int(state.get("failures", 0)) >= CIRCUIT_FAILURE_LIMIT
            and time.time() - float(state.get("updated_at", 0)) < CIRCUIT_COOLDOWN_SECONDS
        )


def http_get(url, accept="application/json", *, timeout=HTTP_TIMEOUT_SECONDS, pause=PAUSA_WEB, max_cache_entries=MAX_WEB_CACHE_ENTRIES, retries=2):
    provider = urllib.parse.urlparse(url).netloc or "unknown"
    if os.environ.get("MANAGE_YOUR_LIBRARY_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}:
        _record_health(provider, "offline", "Modo sin conexión activado")
        return None
    if _circuit_is_open(provider):
        _record_health(provider, "circuit_open", "Proveedor pausado tras fallos consecutivos")
        return None
    with WEB_CACHE_LOCK:
        if url in WEB_CACHE:
            return WEB_CACHE[url]

    try:
        from cache_engine import get_cached_api_response

        cached = get_cached_api_response(cache_key_web(url))
        if cached is not None:
            with WEB_CACHE_LOCK:
                WEB_CACHE[url] = cached
            prune_web_cache(max_cache_entries)
            return cached
    except Exception:
        pass

    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    req = urllib.request.Request(url, headers=headers)
    last_error = ""
    for attempt in range(max(0, int(retries)) + 1):
        if pause:
            time.sleep(float(pause) * (attempt + 1))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 404:
                    _record_health(provider, "no_result")
                    return None
                if resp.status != 200:
                    last_error = f"HTTP {resp.status}"
                    continue
                data = resp.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise ValueError(f"Respuesta mayor de {MAX_RESPONSE_BYTES} bytes")
                obj = json.loads(data.decode("utf-8", errors="replace")) if "json" in accept else data.decode("utf-8", errors="replace")
                with WEB_CACHE_LOCK:
                    WEB_CACHE[url] = obj
                try:
                    from cache_engine import cache_api_response

                    parsed = urllib.parse.urlsplit(url)
                    redacted_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
                    cache_api_response(cache_key_web(url), provider, redacted_url, obj)
                except Exception:
                    pass
                prune_web_cache(max_cache_entries)
                _record_health(provider, "ok")
                return obj
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                _record_health(provider, "no_result")
                return None
            last_error = f"HTTP {exc.code}"
            if exc.code not in {408, 429, 500, 502, 503, 504}:
                break
        except urllib.error.URLError as exc:
            last_error = f"network: {exc.reason}"
        except TimeoutError:
            last_error = "timeout"
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = f"invalid_response: {exc}"
            break
        except Exception as exc:
            last_error = f"unexpected: {exc}"
            break
    status = "timeout" if "timeout" in last_error.lower() else "error"
    _record_health(provider, status, last_error)
    return None


def extraer_anio(texto):
    if not texto:
        return ""
    m = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", str(texto))
    if not m:
        return ""
    anio = int(m.group(1))
    if anio > datetime.now().year + 1:
        return ""
    return str(anio)


def candidato(fuente, titulo="", autor="", anio="", isbn="", metodo="", identificador="", *, limpiar_isbn_func=limpiar_isbn_default, **extras):
    out = {
        "fuente": fuente,
        "titulo": str(titulo or "").strip(),
        "autor": str(autor or "").strip(),
        "anio": str(anio or "").strip()[:4] if anio else "",
        "isbn": limpiar_isbn_func(isbn),
        "metodo": metodo,
        "identificador": str(identificador or "").strip(),
    }
    for key, value in extras.items():
        if value not in ("", None, [], {}):
            out[key] = value
    return out


def _first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _openlibrary_language_code(value):
    value = _first(value)
    if isinstance(value, dict):
        value = value.get("key", "")
    value = str(value or "").strip()
    if value.startswith("/languages/"):
        return value.rsplit("/", 1)[-1]
    return value


def _openlibrary_editions(doc):
    editions = doc.get("editions") or {}
    if isinstance(editions, dict):
        editions = editions.get("docs") or []
    return editions if isinstance(editions, list) else []


def _best_openlibrary_edition(doc):
    for edition in _openlibrary_editions(doc):
        if not isinstance(edition, dict):
            continue
        if edition.get("title") or edition.get("isbn") or edition.get("publish_date"):
            return edition
    return {}


def _openlibrary_cover_url(isbn="", cover_id=""):
    try:
        cover_id = int(cover_id)
    except (TypeError, ValueError):
        cover_id = 0
    if cover_id:
        return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg?default=false"
    isbn = limpiar_isbn_default(isbn)
    if isbn:
        return f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"
    return ""


def _openlibrary_candidate_from_doc(doc, metodo, *, limpiar_isbn_func=limpiar_isbn_default):
    edition = _best_openlibrary_edition(doc)
    autores = doc.get("author_name") or []
    author_keys = doc.get("author_key") or []
    doc_isbns = doc.get("isbn") or []
    edition_isbns = edition.get("isbn") or []
    publish_date = edition.get("publish_date", "")
    language = _openlibrary_language_code(edition.get("language") or doc.get("language"))
    publisher = _first(edition.get("publisher"))
    edition_title = edition.get("title", "")
    title = edition_title or doc.get("title", "")
    year = extraer_anio(publish_date) or str(doc.get("first_publish_year", "") or "")
    isbn = _first(edition_isbns) or _first(doc_isbns)
    edition_id = edition.get("key", "")
    work_id = doc.get("key", "")

    return candidato(
        "Open Library",
        title,
        _first(autores),
        year,
        isbn,
        metodo,
        edition_id or work_id,
        limpiar_isbn_func=limpiar_isbn_func,
        work_id=work_id,
        edition_id=edition_id,
        edition_title=edition_title,
        edition_publish_date=publish_date,
        publisher=publisher,
        language=language,
        edition_count=doc.get("edition_count", ""),
        author_key=_first(author_keys),
        cover_url=_openlibrary_cover_url(isbn, doc.get("cover_i")),
        source_scope="work_edition",
    )


def openlibrary_isbn(isbn, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    url = f"https://openlibrary.org/isbn/{urllib.parse.quote(isbn)}.json"
    data = http_get_func(url)
    if not data:
        return []
    autor = ""
    try:
        authors = data.get("authors") or []
        if authors:
            key = authors[0].get("key")
            if key:
                adata = http_get_func("https://openlibrary.org" + key + ".json")
                if adata and adata.get("name"):
                    autor = adata["name"]
    except Exception:
        pass
    work_id = ""
    try:
        works = data.get("works") or []
        if works:
            work_id = works[0].get("key", "")
    except Exception:
        work_id = ""
    return [
        candidato(
            "Open Library",
            data.get("title", ""),
            autor,
            extraer_anio(data.get("publish_date", "")),
            isbn,
            "ISBN",
            data.get("key", ""),
            limpiar_isbn_func=limpiar_isbn_func,
            work_id=work_id,
            edition_id=data.get("key", ""),
            publisher=_first(data.get("publishers")),
            language=_openlibrary_language_code(data.get("languages")),
            cover_url=_openlibrary_cover_url(isbn, data.get("covers", [""])[0] if data.get("covers") else ""),
            source_scope="edition_isbn",
        )
    ]


def openlibrary_busqueda(query, language="", *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    params = {"q": query, "limit": 5, "fields": OPENLIBRARY_SEARCH_FIELDS}
    language = _openlibrary_language_code(language)
    if language:
        params["language"] = language
    q = urllib.parse.urlencode(params)
    data = http_get_func(f"https://openlibrary.org/search.json?{q}")
    if not data or not data.get("docs"):
        return []
    out = []
    for doc in data["docs"][:5]:
        out.append(_openlibrary_candidate_from_doc(doc, "Búsqueda", limpiar_isbn_func=limpiar_isbn_func))
    return out


def openlibrary_busqueda_autor(
    autor,
    limit=25,
    *,
    http_get_func=http_get,
    limpiar_nombre_archivo_func=limpiar_nombre_archivo_default,
    autor_desde_nombre_es_usable_func=autor_desde_nombre_es_usable_default,
    limpiar_isbn_func=limpiar_isbn_default,
):
    autor = limpiar_nombre_archivo_func(autor, 90) if autor else ""
    if not autor or not autor_desde_nombre_es_usable_func(autor, permitir_mononimo=True):
        return []
    limite = max(5, min(int(limit or 25), 30))
    q = urllib.parse.urlencode({
        "author": autor,
        "limit": limite,
        "fields": OPENLIBRARY_SEARCH_FIELDS,
    })
    data = http_get_func(f"https://openlibrary.org/search.json?{q}")
    if not data or not data.get("docs"):
        return []
    out = []
    for doc in data["docs"][:limite]:
        c = _openlibrary_candidate_from_doc(doc, "Búsqueda por autor", limpiar_isbn_func=limpiar_isbn_func)
        if not c.get("autor"):
            c["autor"] = autor
        out.append(c)
    return out


def internetarchive_busqueda(query, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    limpio = query.replace('"', " ")
    params = [
        ("q", f'(title:("{limpio}") OR creator:("{limpio}"))'),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "creator"),
        ("fl[]", "date"),
        ("fl[]", "isbn"),
        ("rows", "5"),
        ("output", "json"),
    ]
    data = http_get_func("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params))
    if not data:
        return []
    docs = data.get("response", {}).get("docs", []) or []
    out = []
    for d in docs[:5]:
        creator = d.get("creator", "")
        if isinstance(creator, list):
            creator = creator[0] if creator else ""
        isbn = d.get("isbn", "")
        if isinstance(isbn, list):
            isbn = isbn[0] if isbn else ""
        out.append(
            candidato(
                "Internet Archive",
                d.get("title", ""),
                creator,
                extraer_anio(d.get("date", "")),
                isbn,
                "Recuperación",
                d.get("identifier", ""),
                limpiar_isbn_func=limpiar_isbn_func,
            )
        )
    return out


def gutendex_busqueda(query, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    data = http_get_func("https://gutendex.com/books/?" + urllib.parse.urlencode({"search": query}))
    if not data:
        return []
    out = []
    for item in data.get("results", [])[:5]:
        authors = item.get("authors") or []
        autor = authors[0].get("name", "") if authors else ""
        out.append(
            candidato(
                "Gutendex / Project Gutenberg",
                item.get("title", ""),
                autor,
                "",
                "",
                "Recuperación",
                str(item.get("id", "")),
                limpiar_isbn_func=limpiar_isbn_func,
            )
        )
    return out


def crossref_doi(doi, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    data = http_get_func(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")
    if not data:
        return []
    return [parse_crossref_item(data.get("message", {}), "DOI", limpiar_isbn_func=limpiar_isbn_func)]


def crossref_busqueda(query, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query.bibliographic": query, "rows": 5})
    data = http_get_func(url)
    if not data:
        return []
    items = data.get("message", {}).get("items", []) or []
    return [parse_crossref_item(item, "Búsqueda", limpiar_isbn_func=limpiar_isbn_func) for item in items[:5]]


def parse_crossref_item(item, metodo, *, limpiar_isbn_func=limpiar_isbn_default):
    titulos = item.get("title") or []
    titulo = titulos[0] if titulos else ""
    autores = item.get("author") or []
    autor = ""
    if autores:
        a = autores[0]
        autor = " ".join([a.get("given", ""), a.get("family", "")]).strip()
    anio = ""
    for k in ["published-print", "published-online", "issued"]:
        parts = item.get(k, {}).get("date-parts")
        if parts and parts[0]:
            anio = str(parts[0][0])
            break
    isbns = item.get("ISBN") or []
    return candidato(
        "Crossref",
        titulo,
        autor,
        anio,
        isbns[0] if isbns else "",
        metodo,
        item.get("DOI", ""),
        limpiar_isbn_func=limpiar_isbn_func,
    )


def openalex_doi(doi, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    url = "https://api.openalex.org/works/" + urllib.parse.quote("https://doi.org/" + doi, safe="")
    data = http_get_func(url)
    if not data:
        return []
    return [parse_openalex_work(data, "DOI", limpiar_isbn_func=limpiar_isbn_func)]


def openalex_busqueda(query, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": query, "per-page": 5})
    data = http_get_func(url)
    if not data:
        return []
    results = data.get("results", []) or []
    return [parse_openalex_work(w, "Búsqueda", limpiar_isbn_func=limpiar_isbn_func) for w in results[:5]]


def parse_openalex_work(w, metodo, *, limpiar_isbn_func=limpiar_isbn_default):
    titulo = w.get("title", "")
    anio = str(w.get("publication_year", "")) if w.get("publication_year") else ""
    autor = ""
    auths = w.get("authorships") or []
    if auths:
        autor = auths[0].get("author", {}).get("display_name", "")
    ids = w.get("ids", {}) or {}
    identificador = ids.get("doi", "") or w.get("id", "")
    return candidato("OpenAlex", titulo, autor, anio, "", metodo, identificador, limpiar_isbn_func=limpiar_isbn_func)


def _query_has_cjk(query: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(query or "")))


def wikidata_search_languages(query, preferred=None):
    ordered = []

    def add(lang):
        lang = str(lang or "").strip().lower().replace("_", "-")
        if not lang:
            return
        lang = lang.split("-", 1)[0]
        if lang and lang not in ordered:
            ordered.append(lang)

    for lang in _as_list(preferred):
        add(lang)
    if _query_has_cjk(query):
        add("zh")
    for lang in WIKIDATA_DEFAULT_LANGUAGES:
        add(lang)
    return tuple(ordered[:4])


def _wikidata_label(entity, languages=WIKIDATA_DEFAULT_LANGUAGES):
    labels = entity.get("labels") or {}
    for lang in wikidata_search_languages("", languages):
        if lang in labels and labels[lang].get("value"):
            return labels[lang]["value"]
    for label in labels.values():
        if isinstance(label, dict) and label.get("value"):
            return label["value"]
    return ""


def _wikidata_claim_values(entity, prop):
    out = []
    claims = (entity.get("claims") or {}).get(prop) or []
    for claim in claims:
        mainsnak = claim.get("mainsnak") or {}
        datavalue = mainsnak.get("datavalue") or {}
        value = datavalue.get("value")
        if value not in ("", None):
            out.append(value)
    return out


def _wikidata_claim_entity_id(entity, prop):
    for value in _wikidata_claim_values(entity, prop):
        if isinstance(value, dict):
            entity_id = value.get("id")
            if entity_id:
                return entity_id
            numeric_id = value.get("numeric-id")
            if numeric_id:
                return f"Q{numeric_id}"
    return ""


def _wikidata_title_claim(entity):
    for value in _wikidata_claim_values(entity, "P1476"):
        if isinstance(value, dict) and value.get("text"):
            return value["text"]
        if isinstance(value, str):
            return value
    return ""


def _wikidata_year_claim(entity):
    for value in _wikidata_claim_values(entity, "P577"):
        if isinstance(value, dict):
            year = extraer_anio(value.get("time", ""))
            if year:
                return year
        else:
            year = extraer_anio(value)
            if year:
                return year
    return ""


def _wikidata_isbn_claim(entity):
    for prop in ("P212", "P957"):
        for value in _wikidata_claim_values(entity, prop):
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _wikidata_entity(qid, *, http_get_func=http_get):
    if not qid:
        return {}
    data = http_get_func(f"https://www.wikidata.org/wiki/Special:EntityData/{urllib.parse.quote(qid)}.json")
    if not data:
        return {}
    return ((data.get("entities") or {}).get(qid) or {}) if isinstance(data, dict) else {}


def _wikidata_structured_candidate(qid, fallback_label, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default, languages=WIKIDATA_DEFAULT_LANGUAGES):
    entity = _wikidata_entity(qid, http_get_func=http_get_func)
    if not entity:
        return candidato(
            "Wikidata",
            fallback_label,
            "",
            "",
            "",
            "Búsqueda",
            qid,
            limpiar_isbn_func=limpiar_isbn_func,
            wikidata_id=qid,
            source_scope="authority_label",
        )

    author_qid = _wikidata_claim_entity_id(entity, "P50")
    author = ""
    if author_qid:
        author_entity = _wikidata_entity(author_qid, http_get_func=http_get_func)
        author = _wikidata_label(author_entity, languages) if author_entity else ""

    language_qid = _wikidata_claim_entity_id(entity, "P407")
    publisher_qid = _wikidata_claim_entity_id(entity, "P123")
    language_label = ""
    publisher = ""
    if language_qid:
        language_entity = _wikidata_entity(language_qid, http_get_func=http_get_func)
        language_label = _wikidata_label(language_entity, languages) if language_entity else ""
    if publisher_qid:
        publisher_entity = _wikidata_entity(publisher_qid, http_get_func=http_get_func)
        publisher = _wikidata_label(publisher_entity, languages) if publisher_entity else ""

    title = _wikidata_title_claim(entity) or _wikidata_label(entity, languages) or fallback_label
    method = "Búsqueda estructurada" if (author or _wikidata_isbn_claim(entity) or _wikidata_year_claim(entity)) else "Búsqueda"
    source_scope = "structured_work" if method == "Búsqueda estructurada" else "authority_label"
    return candidato(
        "Wikidata",
        title,
        author,
        _wikidata_year_claim(entity),
        _wikidata_isbn_claim(entity),
        method,
        qid,
        limpiar_isbn_func=limpiar_isbn_func,
        wikidata_id=qid,
        author_qid=author_qid,
        language=language_label,
        language_qid=language_qid,
        publisher=publisher,
        publisher_qid=publisher_qid,
        source_scope=source_scope,
    )


def wikidata_busqueda(query, languages=None, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    out = []
    vistos = set()
    for lang in wikidata_search_languages(query, languages):
        url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({
            "action": "wbsearchentities",
            "search": query,
            "language": lang,
            "type": "item",
            "limit": "5",
            "format": "json",
        })
        data = http_get_func(url)
        if not data:
            continue
        for item in data.get("search", [])[:5]:
            qid = item.get("id", "")
            if not qid or qid in vistos:
                continue
            vistos.add(qid)
            out.append(
                _wikidata_structured_candidate(
                    qid,
                    item.get("label", ""),
                    http_get_func=http_get_func,
                    limpiar_isbn_func=limpiar_isbn_func,
                    languages=(lang,) + tuple(wikidata_search_languages(query, languages)),
                )
            )
            if len(out) >= 5:
                return out
    return out


def loc_busqueda(query, *, http_get_func=http_get, limpiar_isbn_func=limpiar_isbn_default):
    url = "https://www.loc.gov/books/?" + urllib.parse.urlencode({"fo": "json", "q": query, "c": "5"})
    data = http_get_func(url)
    if not data:
        return []
    out = []
    for item in data.get("results", [])[:5]:
        titulo = item.get("title", "")
        autores = item.get("contributor") or item.get("creator") or []
        autor = ""
        if isinstance(autores, list) and autores:
            autor = autores[0]
        elif isinstance(autores, str):
            autor = autores
        fecha = item.get("date", "")
        out.append(
            candidato(
                "Library of Congress",
                titulo,
                autor,
                extraer_anio(fecha),
                "",
                "Búsqueda",
                item.get("id", ""),
                limpiar_isbn_func=limpiar_isbn_func,
                source_scope="catalog_auxiliary",
            )
        )
    return out
