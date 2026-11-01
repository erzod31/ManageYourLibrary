"""Local Indra OCR and conservative bibliographic evidence extraction."""
from __future__ import annotations

import copy
import re
import threading
import unicodedata
from collections import OrderedDict
from io import BytesIO
from itertools import islice
from pathlib import Path

from core import ocr_runtime
from core.cancellation import OperationCancelled
from core.document_context import DocumentContext

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS
DEFAULT_DPI = 200
FALLBACK_DPI = 300
_SESSION_OCR_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
MAX_DOCUMENT_CACHE = 16


def limpiar_cache_ocr():
    with _CACHE_LOCK:
        _SESSION_OCR_CACHE.clear()
    ocr_runtime.close()


def _resource_path(relative_path):
    return ocr_runtime.resource_root() / relative_path


def _validar_isbn10(isbn: str) -> bool:
    isbn = re.sub(r"[^0-9Xx]", "", isbn)
    if len(isbn) != 10:
        return False
    total = 0
    for i, ch in enumerate(isbn):
        if i == 9 and ch.upper() == "X":
            val = 10
        elif ch.isdigit():
            val = int(ch)
        else:
            return False
        total += val * (10 - i)
    return total % 11 == 0


def _validar_isbn13(isbn: str) -> bool:
    isbn = re.sub(r"[^0-9]", "", isbn)
    if len(isbn) != 13 or not isbn.startswith(("978", "979")):
        return False
    total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(isbn[:12]))
    check = (10 - (total % 10)) % 10
    return check == int(isbn[-1])


def _limpiar_isbn(isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", isbn or "").upper()


def _normalizar_fragmento_isbn_ocr(fragmento: str) -> str:
    """Corrige confusiones OCR solo dentro de fragmentos con aspecto de ISBN."""
    table = str.maketrans({
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "!": "1",
        "S": "5",
        "s": "5",
        "B": "8",
    })
    return str(fragmento or "").translate(table)


def _extraer_isbns(texto: str):
    if not texto:
        return []
    found = set()
    patterns = [
        re.compile(r"ISBN(?:-1[03])?\s*[: ]?\s*([0-9Xx][0-9Xx\-\s]{8,25}[0-9Xx])", re.I),
        re.compile(r"ISBN(?:-1[03])?\s*[:.\- ]?\s*([0-9XxOoIl|!SsB][0-9XxOoIl|!SsB\-\s]{8,25}[0-9XxOoIl|!SsB])", re.I),
        re.compile(r"(97[89][0-9\-\s]{10,20}[0-9])", re.I),
        re.compile(r"\b([97Oo][789Oo][0-9OoIl|!SsB\-\s]{10,22}[0-9XxOoIl|!SsB])\b", re.I),
    ]
    for pattern in patterns:
        for match in pattern.finditer(texto):
            raw = match.group(1)
            clean = _limpiar_isbn(raw)
            if not (_validar_isbn13(clean) or _validar_isbn10(clean)):
                clean = _limpiar_isbn(_normalizar_fragmento_isbn_ocr(raw))
            if _validar_isbn13(clean) or _validar_isbn10(clean):
                found.add(clean)
    for match in re.finditer(r"\b(97[89]\d{10})\b", texto):
        clean = _limpiar_isbn(match.group(1))
        if _validar_isbn13(clean):
            found.add(clean)
    return sorted(found)


def _normalizar_texto(texto: str) -> str:
    texto = str(texto or "")
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _sin_acentos(texto: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(ch)
    )


def detectar_idioma_ocr_rapido(texto_muestra) -> str:
    texto = str(texto_muestra or "")
    lower = texto.lower()
    plain = _sin_acentos(lower)
    padded = f" {lower} "
    plain_padded = f" {plain} "

    if re.search(r"[\u4e00-\u9fff]", texto):
        if re.search(r"[A-Za-zÀ-ÿ]", texto):
            return "chi_sim+eng"
        return "chi_sim"

    spanish_hits = sum(1 for w in [
        " el ", " la ", " los ", " las ", " de ", " que ", " para ", " capítulo ",
        " autor ", " edición ", " prólogo ", " índice ", " español ",
        " capitulo ", " edicion ", " prologo ", " indice ", " espanol ", " libro ",
    ] if w in padded or w in plain_padded)
    french_hits = sum(1 for w in [
        " le ", " la ", " les ", " des ", " pour ", " avec ", " chapitre ",
        " auteur ", " édition ", " préface ", " français ",
        " editeur ", " preface ", " francais ", " livre ",
    ] if w in padded or w in plain_padded)
    english_hits = sum(1 for w in [
        " the ", " and ", " author ", " edition ", " chapter ", " contents ",
        " introduction ", " publisher ", " copyright ",
    ] if w in padded)
    dutch_hits = sum(1 for w in [
        " het ", " een ", " van ", " voor ", " met ", " hoofdstuk ",
        " auteur ", " uitgave ", " inhoud ", " uitgever ", " nederlands ",
    ] if w in plain_padded)

    spanish_unique = sum(1 for w in [
        " el ", " los ", " las ", " que ", " para ", " capitulo ", " autor ",
        " prologo ", " indice ", " espanol ", " libro ",
    ] if w in plain_padded)
    french_unique = sum(1 for w in [
        " le ", " les ", " des ", " pour ", " avec ", " chapitre ", " auteur ",
        " preface ", " francais ", " livre ",
    ] if w in plain_padded)

    if re.search(r"[áéíóúñ¿¡]", lower):
        spanish_hits += 2
    if re.search(r"[àâçèéêëîïôûùüÿœ]", lower):
        french_hits += 2

    if dutch_hits >= 3 and dutch_hits > max(spanish_hits, french_hits, english_hits):
        return "nld+eng"

    if french_hits == spanish_hits and french_unique > spanish_unique:
        return "fra"
    if spanish_hits == french_hits and spanish_unique > french_unique:
        return "spa"
    if spanish_hits >= french_hits + 2 and spanish_hits >= english_hits:
        return "spa+eng"
    if french_hits >= spanish_hits + 2 and french_hits >= english_hits:
        return "fra+eng"
    if spanish_hits and english_hits and abs(spanish_hits - english_hits) <= 1:
        return "eng+spa"
    if spanish_hits > english_hits:
        return "spa+eng"
    if french_hits > english_hits:
        return "fra+eng"
    return "eng"


def classify_page_type(texto: str, page_number=1):
    norm = _sin_acentos(str(texto or "").lower())
    if page_number == 1 and len(norm.strip()) < 400:
        return "cover"
    if re.search(r"\b(isbn|copyright|derechos reservados|all rights reserved|publisher|editorial)\b", norm):
        return "copyright_page"
    if re.search(r"\b(indice|contents|table of contents)\b", norm):
        return "table_of_contents"
    if re.search(r"\b(prologo|preface|introduction|introduccion)\b", norm):
        return "preface"
    if re.search(r"\b(capitulo|chapter)\s+\d+\b", norm):
        return "chapter"
    if page_number <= 3:
        return "title_page"
    return "unknown"


def detect_title_author_candidates(texto: str = "", layout=None):
    layout = layout or {}
    layout_lines = list(layout.get("lines", []) or [])
    max_height = max([int(item.get("height", 0) or 0) for item in layout_lines] or [0])
    lines = []
    for item in layout.get("lines", []):
        line = dict(item)
        line["text"] = str(item.get("text", "")).strip()
        lines.append(line)
    if not lines:
        lines = [
            {"text": l.strip(), "confidence": 55, "height": 0, "relative_position": "", "y": 0}
            for l in str(texto or "").splitlines()
            if 3 <= len(l.strip()) <= 140
        ]
    clean = []
    for item in lines[:80]:
        line = item.get("text", "")
        if re.search(r"(?i)\b(isbn|copyright|editorial|publisher|chapter|capitulo|indice|contents|colecci[oó]n|collection|serie|series|saga)\b", line):
            continue
        item = dict(item)
        item["text"] = line
        clean.append(item)

    title_candidates = []
    author_candidates = []
    for i, item in enumerate(clean[:30]):
        line = item.get("text", "")
        words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", line)
        cjk_chars = re.findall(r"[\u4e00-\u9fff]", line)
        confidence = float(item.get("confidence", 55) or 0)
        height = int(item.get("height", 0) or 0)
        position = item.get("relative_position", "")
        centered = bool(item.get("centered"))
        top_half = position in {"top", "center"} or int(item.get("y", 0) or 0) < 1300
        if 1 <= len(words) <= 12:
            title_score = 45
            if i <= 5:
                title_score += 15
            if max_height and height >= max_height * 0.82:
                title_score += 18
            elif max_height and height >= max_height * 0.62:
                title_score += 8
            if top_half:
                title_score += 5
            if centered:
                title_score += 7
            if confidence >= 75:
                title_score += 6
            elif confidence < 45:
                title_score -= 8
            if any(ch in line for ch in "¿?¡!:"):
                title_score += 5
            title_candidates.append({"text": line, "score": min(95, title_score), "source": "ocr_layout"})
        elif cjk_chars and 2 <= len(cjk_chars) <= 24:
            title_score = 62
            if i <= 5:
                title_score += 12
            if max_height and height >= max_height * 0.62:
                title_score += 10
            title_candidates.append({"text": line, "score": min(95, title_score), "source": "ocr_layout"})
        if re.match(r"(?i)^(por|by|author|written by|obra de)\s+(.+)$", line):
            value = re.sub(r"(?i)^(por|by|author|written by|obra de)\s+", "", line).strip()
            author_candidates.append({"text": value, "role": "author", "score": 88, "source": "ocr_layout"})
        elif 2 <= len(words) <= 5 and all(w[:1].isupper() for w in words[:3]):
            score = 58
            if i <= 8:
                score += 6
            if max_height and height < max_height * 0.80:
                score += 5
            if centered and position in {"top", "center"}:
                score += 3
            if confidence >= 70:
                score += 4
            author_candidates.append({"text": line, "role": "unknown_name", "score": min(82, score), "source": "ocr_layout"})
    return {
        "ocr_title_candidates": title_candidates[:8],
        "ocr_author_candidates": author_candidates[:8],
        "ocr_isbn_candidates": _extraer_isbns(texto),
        "ocr_year_candidates": sorted(set(re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", str(texto or ""))))[:4],
        "ocr_publisher_candidates": [],
        "ocr_translator_candidates": [],
        "ocr_original_title_candidates": [],
        "ocr_page_source": [],
        "ocr_confidence": max([c["score"] for c in title_candidates + author_candidates] or [0]),
        "ocr_warnings": [],
    }


def _texto_util(texto: str) -> bool:
    if not texto:
        return False
    if _extraer_isbns(texto):
        return True
    words = re.findall(r"[A-Za-zÀ-ÿ\u4e00-\u9fff]{3,}", texto)
    meaningful = len("".join(words))
    alpha_ratio = meaningful / max(1, len(str(texto).strip()))
    return len(words) >= 18 or (len(words) >= 8 and len(texto.strip()) >= 180 and alpha_ratio >= 0.35)


def _datos_suficientes(texto: str) -> bool:
    lines = [l.strip() for l in texto.splitlines() if 4 <= len(l.strip()) <= 140]
    if _extraer_isbns(texto):
        bibliographic = [line for line in lines if not re.search(r"(?i)\bisbn\b", line)
                         and len(re.findall(r"[A-Za-zÀ-ÿ\u4e00-\u9fff]", line)) >= 4]
        words = re.findall(r"[A-Za-zÀ-ÿ]{2,}|[\u4e00-\u9fff]", " ".join(bibliographic))
        return len(set(bibliographic)) >= 2 and len(words) >= 5
    return len(lines) >= 3 and len(re.findall(r"[A-Za-zÀ-ÿ\u4e00-\u9fff]{3,}", texto)) >= 25


def _ocr_text_score(texto: str) -> float:
    texto = _normalizar_texto(texto)
    if not texto:
        return 0.0
    words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", texto)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", texto)
    lines = [line.strip() for line in texto.splitlines() if 2 <= len(line.strip()) <= 140]
    useful_lines = [
        line for line in lines
        if re.search(r"[A-Za-zÀ-ÿ\u4e00-\u9fff]{2,}", line)
        and not re.search(r"(?i)\b(copyright|editorial|publisher|contents|indice)\b", line)
    ]
    alpha_num = re.findall(r"[A-Za-zÀ-ÿ0-9\u4e00-\u9fff]", texto)
    odd_chars = re.findall(r"[^A-Za-zÀ-ÿ0-9\u4e00-\u9fff\s.,:;¿?¡!()'\"\-/]", texto)
    odd_ratio = len(odd_chars) / max(1, len(alpha_num) + len(odd_chars))
    score = 0.0
    if _extraer_isbns(texto):
        score += 120
    score += min(len(words) * 2.8, 80)
    score += min(len(cjk_chars) * 3.0, 60)
    score += min(len(useful_lines) * 9, 55)
    if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", texto):
        score += 10
    if 2 <= len(useful_lines) <= 8 and len(words) <= 80:
        score += 14
    if odd_ratio > 0.18:
        score -= min(35, odd_ratio * 100)
    return max(0.0, round(score, 2))

def is_pdf_scanned(archivo, max_paginas=3, min_chars=50):
    path = Path(archivo)
    if path.suffix.lower() != ".pdf" or not path.exists():
        return False
    try:
        from pypdf import PdfReader
        with path.open("rb") as stream:
            reader = PdfReader(stream)
            checked = useful_pages = 0
            for page in islice(reader.pages, max(1, int(max_paginas or 3))):
                checked += 1
                text = page.extract_text() or ""
                if len(text.strip()) >= min_chars and len(re.findall(r"[A-Za-zÀ-ÿ0-9]{2,}", text)) >= 8:
                    useful_pages += 1
            return checked > 0 and useful_pages == 0
    except Exception:
        return True


def _pdf_images(path, max_pages, dpi):
    """Open a PDF once; retain only the current page and its rendered bitmap."""
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(str(path)) as document:
        for index in range(min(len(document), max_pages)):
            page = document[index]
            bitmap = image = None
            try:
                bitmap = page.render(scale=dpi / 72)
                image = bitmap.to_pil()
                with BytesIO() as output:
                    image.save(output, format="PNG")
                    raw = output.getvalue()
            finally:
                if image is not None:
                    image.close()
                if bitmap is not None:
                    bitmap.close()
                page.close()
            yield index, raw


def render_first_pages(archivo, max_paginas=3, dpi=DEFAULT_DPI):
    path = Path(archivo)
    if path.suffix.lower() != ".pdf" or not path.is_file():
        return []
    pages = []
    try:
        for index, raw in _pdf_images(path, max(1, min(int(max_paginas or 3), 6)), int(dpi or DEFAULT_DPI)):
            pages.append({"page_number": index + 1, "dpi": int(dpi or DEFAULT_DPI), "image_bytes": raw})
    except Exception:
        pass
    return pages


def _layout_from_page(page):
    if page.get("error"):
        return {"tokens": [], "lines": [], "error": page["error"]}
    tokens = page.get("lines", [])
    lines = []
    page_width = max(1, page.get("width") or max((v["x"] + v["width"] for v in tokens), default=1))
    page_height = max(1, page.get("height") or max((v["y"] + v["height"] for v in tokens), default=1))
    grouped = OrderedDict()
    for token in tokens:
        grouped.setdefault((token["page"], token["block"], token["line"]), []).append(token)
    for key, values in grouped.items():
        # Indra already supplies reading order, including RTL and CJK lines.
        x = min(v["x"] for v in values)
        y = min(v["y"] for v in values)
        right = max(v["x"] + v["width"] for v in values)
        bottom = max(v["y"] + v["height"] for v in values)
        ratio = y / page_height
        lines.append({"text": " ".join(v["text"] for v in values), "page": key[0],
                      "x": x, "y": y, "width": right - x, "height": bottom - y,
                      "confidence": sum(v["confidence"] for v in values) / len(values),
                      "relative_position": "top" if ratio < 0.28 else "center" if ratio < 0.72 else "bottom",
                      "centered": abs(x + (right - x) / 2 - page_width / 2) / page_width <= 0.24,
                      "page_width": page_width, "page_height": page_height})
    return {"tokens": tokens, "lines": lines, "error": None}


def extract_layout_tokens(image_bytes, lang=None, psm=None, cancellation=None):
    # Legacy language/PSM arguments remain accepted; Indra selects scripts and
    # orientation automatically, with no second language or layout OCR pass.
    return _layout_from_page(ocr_runtime.recognize(image_bytes, cancellation=cancellation))


def _provenance():
    info = ocr_runtime.model_manifest()
    return {"ocr_engine": info["engine"], "ocr_engine_version": info["engineVersion"],
            "ocr_model_revision": info["modelRevision"], "ocr_model_license": info["modelLicense"],
            "ocr_attribution": "Indra OCR by Datalab: https://huggingface.co/datalab-to/indra-ocr"}


def _empty_result(method, error=None):
    return _finish_result("", method, "eng", 0, DEFAULT_DPI, error=error)


def _finish_result(texto, metodo, idioma, paginas, dpi, desde_cache=False, error=None, candidates=None):
    texto = _normalizar_texto(texto)
    isbns = _extraer_isbns(texto)
    result = {"texto": texto, "metodo": metodo, "idioma_detectado": idioma,
              "paginas_analizadas": paginas, "dpi": dpi, "desde_cache": desde_cache,
              "isbn_detectado": isbns[0] if isbns else "", "error": error, **_provenance()}
    if candidates:
        result.update({k: v for k, v in candidates.items() if k.startswith("ocr_")})
    return result


def _candidates(page):
    text = _normalizar_texto(page.get("text", ""))
    candidates = detect_title_author_candidates(text, layout=_layout_from_page(page))
    candidates.update(ocr_rotation=page.get("rotation", 0), ocr_text_score=_ocr_text_score(text),
                      ocr_timings=page.get("timings", {}))
    if page.get("unreadable_lines"):
        candidates["ocr_warnings"].append("Indra could not read some detected lines; verify bibliographic evidence")
    return text, candidates


def extraer_texto_imagen_bytes_ocr(image_bytes, callback=None, cancellation=None):
    if cancellation:
        cancellation.raise_if_cancelled()
    if not image_bytes:
        return _empty_result("image_ocr", "Empty image")
    if callback:
        callback("OCR: Indra (local)")
    page = ocr_runtime.recognize(image_bytes, cancellation=cancellation)
    text, candidates = _candidates(page)
    return _finish_result(text, "image_ocr", detectar_idioma_ocr_rapido(text), 1,
                          DEFAULT_DPI, error=page.get("error"), candidates=candidates)


def extraer_texto_documento_ocr(archivo, max_paginas=12, callback=None, cancellation=None, *, dpi=DEFAULT_DPI):
    path = Path(archivo)
    method = "pdf_ocr" if path.suffix.lower() == ".pdf" else "image_ocr"
    if cancellation:
        cancellation.raise_if_cancelled()
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return _empty_result("", "Unsupported file type")
    if not path.is_file():
        return _empty_result(method, "File not found")
    max_pages = max(1, min(int(max_paginas or 12), 200))
    try:
        context = DocumentContext(path)
        key = (context.sha256, max_pages, dpi, ocr_runtime.model_manifest()["modelRevision"])
        with _CACHE_LOCK:
            if key in _SESSION_OCR_CACHE:
                result = copy.deepcopy(_SESSION_OCR_CACHE.pop(key))
                _SESSION_OCR_CACHE[key] = copy.deepcopy(result)
                result["desde_cache"] = True
                return result
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            if context.size > ocr_runtime.MAX_IMAGE_BYTES:
                return _empty_result(method, "OCR image exceeds the 32 MB input limit")
            result = extraer_texto_imagen_bytes_ocr(path.read_bytes(), callback=callback, cancellation=cancellation)
        else:
            texts, candidates, last_error, count = [], {}, None, 0
            images = _pdf_images(path, max_pages, dpi)
            try:
                for index, raw in images:
                    if cancellation:
                        cancellation.raise_if_cancelled()
                    context.assert_unchanged()
                    if callback:
                        callback(f"OCR: Indra, página {index + 1}/{max_pages} (local)")
                    page = ocr_runtime.recognize(raw, cancellation=cancellation)
                    count += 1
                    if page.get("error"):
                        last_error = page["error"]
                        break
                    text, page_candidates = _candidates(page)
                    if text:
                        if sum(map(len, texts)) + len(text) > 64_000:
                            last_error = "OCR evidence exceeds the 64,000 character limit"
                            break
                        texts.append(text)
                        if not candidates:
                            candidates = page_candidates
                        # An ISBN on its own is not enough bibliographic evidence.
                        if _datos_suficientes("\n".join(texts)):
                            break
            finally:
                images.close()
            joined = "\n".join(texts)
            result = _finish_result(joined, method, detectar_idioma_ocr_rapido(joined), count,
                                    dpi, error=last_error, candidates=candidates)
        context.assert_unchanged()
        if not result.get("error"):
            with _CACHE_LOCK:
                _SESSION_OCR_CACHE[key] = copy.deepcopy(result)
                while len(_SESSION_OCR_CACHE) > MAX_DOCUMENT_CACHE:
                    _SESSION_OCR_CACHE.popitem(last=False)
        return result
    except OperationCancelled:
        raise
    except Exception as exc:
        return _empty_result(method, str(exc))


def run_fast_ocr(archivo, max_paginas=3, callback=None, cancellation=None):
    return extraer_texto_documento_ocr(archivo, max_paginas=min(max_paginas or 3, 3),
                                      callback=callback, cancellation=cancellation)


def run_deep_ocr(archivo, max_paginas=6, callback=None, cancellation=None):
    return extraer_texto_documento_ocr(archivo, max_paginas=min(max_paginas or 6, 6),
                                      callback=callback, cancellation=cancellation, dpi=FALLBACK_DPI)
