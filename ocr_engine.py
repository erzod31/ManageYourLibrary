import hashlib
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from io import BytesIO
from pathlib import Path

from core.cancellation import OperationCancelled

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS

DEFAULT_DPI = 200
QUICK_DPI = 120
FALLBACK_DPI = 300
MAX_IMAGE_SIDE = 2800
MIN_IMAGE_SIDE = 900
OCR_FAST_PSMS = ("6", "11")
OCR_COVER_PSMS = ("6", "11", "4", "7", "12")
OCR_MAX_VARIANT_ATTEMPTS = 8
_SESSION_OCR_CACHE = {}


def _resource_path(relative_path: str) -> Path:
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return Path(base_path) / relative_path


def _tesseract_path() -> Path | None:
    candidates = [
        _resource_path("tesseract/tesseract.exe"),
        _resource_path("tesseract/tesseract"),
        _resource_path("tesseract/bin/tesseract"),
        Path(__file__).resolve().parent / "tesseract" / "tesseract.exe",
        Path(__file__).resolve().parent / "tesseract" / "tesseract",
        Path(__file__).resolve().parent / "tesseract" / "bin" / "tesseract",
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and (os.name == "nt" or os.access(candidate, os.X_OK)):
            return candidate
    system_tesseract = shutil.which("tesseract")
    if system_tesseract:
        return Path(system_tesseract)
    return None


def _tesseract_env(tesseract: Path):
    env = os.environ.copy()
    for tessdata in (
        tesseract.parent / "tessdata",
        tesseract.parent.parent / "tessdata",
        tesseract.parent.parent / "share" / "tessdata",
        _resource_path("tesseract/tessdata"),
        _resource_path("tesseract/share/tessdata"),
    ):
        if tessdata.exists():
            env["TESSDATA_PREFIX"] = str(tessdata)
            break
    return env


def limpiar_cache_ocr():
    _SESSION_OCR_CACHE.clear()


def _file_hash(path: Path, block_size=1024 * 1024) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def _cache_key(path: Path) -> str:
    stat = path.stat()
    return "|".join([
        str(path.resolve()),
        str(stat.st_size),
        str(int(stat.st_mtime)),
        _file_hash(path),
    ])


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


def _run_tesseract_bytes(image_bytes: bytes, lang: str, psm="6", timeout=40, cancellation=None):
    tesseract = _tesseract_path()
    if not tesseract:
        return "", "Tesseract not found"

    cmd = [str(tesseract), "stdin", "stdout", "-l", lang, "--psm", str(psm)]
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=_tesseract_env(tesseract), creationflags=flags,
        )
        if cancellation:
            with cancellation.track_process(process):
                stdout, stderr = process.communicate(input=image_bytes, timeout=timeout)
        else:
            stdout, stderr = process.communicate(input=image_bytes, timeout=timeout)
        text = stdout.decode("utf-8", errors="ignore")
        err = stderr.decode("utf-8", errors="ignore").strip()
        if process.returncode != 0 and not text.strip():
            return "", err or f"Tesseract exited with code {process.returncode}"
        return _normalizar_texto(text), None
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.communicate()
        except Exception:
            pass
        return "", f"Tesseract superó {timeout} segundos"
    except OperationCancelled:
        raise
    except Exception as exc:
        return "", str(exc)


def _run_tesseract_file(path: Path, lang: str, psm="6", timeout=40):
    tesseract = _tesseract_path()
    if not tesseract:
        return "", "Tesseract not found"

    cmd = [str(tesseract), str(path), "stdout", "-l", lang, "--psm", str(psm)]
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        run = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_tesseract_env(tesseract),
            creationflags=flags,
        )
        if run.returncode != 0 and not run.stdout.strip():
            return "", run.stderr.strip() or f"Tesseract exited with code {run.returncode}"
        return _normalizar_texto(run.stdout), None
    except Exception as exc:
        return "", str(exc)


def _run_tesseract_tsv_bytes(image_bytes: bytes, lang: str, psm="6", timeout=45, cancellation=None):
    tesseract = _tesseract_path()
    if not tesseract:
        return [], "Tesseract not found"
    cmd = [str(tesseract), "stdin", "stdout", "-l", lang, "--psm", str(psm), "tsv"]
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=_tesseract_env(tesseract), creationflags=flags,
        )
        if cancellation:
            with cancellation.track_process(process):
                stdout, stderr = process.communicate(input=image_bytes, timeout=timeout)
        else:
            stdout, stderr = process.communicate(input=image_bytes, timeout=timeout)
        text = stdout.decode("utf-8", errors="ignore")
        err = stderr.decode("utf-8", errors="ignore").strip()
        if process.returncode != 0 and not text.strip():
            return [], err or f"Tesseract exited with code {process.returncode}"
        lines = text.splitlines()
        if not lines:
            return [], None
        header = lines[0].split("\t")
        tokens = []
        for row in lines[1:]:
            parts = row.split("\t")
            if len(parts) != len(header):
                continue
            item = dict(zip(header, parts))
            value = item.get("text", "").strip()
            if not value:
                continue
            try:
                conf = float(item.get("conf", "-1"))
            except Exception:
                conf = -1.0
            if conf < 0:
                continue
            tokens.append({
                "text": value,
                "page": int(item.get("page_num", "1") or 1),
                "block": int(item.get("block_num", "0") or 0),
                "line": int(item.get("line_num", "0") or 0),
                "x": int(item.get("left", "0") or 0),
                "y": int(item.get("top", "0") or 0),
                "width": int(item.get("width", "0") or 0),
                "height": int(item.get("height", "0") or 0),
                "confidence": conf,
            })
        return tokens, None
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.communicate()
        except Exception:
            pass
        return [], f"Tesseract superó {timeout} segundos"
    except OperationCancelled:
        raise
    except Exception as exc:
        return [], str(exc)


def _render_pdf_page(path: Path, page_index: int, dpi: int):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        if page_index >= len(doc):
            return None
        page = doc[page_index]
        bitmap = page.render(scale=dpi / 72)
        image = bitmap.to_pil()
        out = BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
    finally:
        try:
            doc.close()
        except Exception:
            pass


def is_pdf_scanned(archivo, max_paginas=3, min_chars=50):
    path = Path(archivo)
    if path.suffix.lower() != ".pdf" or not path.exists():
        return False
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        checked = 0
        useful_pages = 0
        for page in list(reader.pages)[:max(1, int(max_paginas or 3))]:
            checked += 1
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            useful = len(re.findall(r"[A-Za-zÀ-ÿ0-9]{2,}", text))
            if len(text.strip()) >= min_chars and useful >= 8:
                useful_pages += 1
        return checked > 0 and useful_pages == 0
    except Exception:
        return True


def render_first_pages(archivo, max_paginas=3, dpi=DEFAULT_DPI):
    path = Path(archivo)
    pages = []
    if path.suffix.lower() != ".pdf" or not path.exists():
        return pages
    max_paginas = max(1, min(int(max_paginas or 3), 6))
    for page_index in range(max_paginas):
        try:
            image_bytes = _render_pdf_page(path, page_index, int(dpi or DEFAULT_DPI))
        except Exception:
            break
        if not image_bytes:
            break
        pages.append({
            "page_number": page_index + 1,
            "dpi": int(dpi or DEFAULT_DPI),
            "image_bytes": image_bytes,
        })
    return pages


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


def extract_layout_tokens(image_bytes: bytes, lang="eng+spa", psm="6", cancellation=None):
    kwargs = {"psm": psm}
    if cancellation is not None:
        kwargs["cancellation"] = cancellation
    tokens, error = _run_tesseract_tsv_bytes(image_bytes, lang, **kwargs)
    if error:
        return {"tokens": [], "lines": [], "error": error}
    grouped = {}
    for token in tokens:
        key = (token["page"], token["block"], token["line"])
        grouped.setdefault(key, []).append(token)
    lines = []
    for key, values in grouped.items():
        values = sorted(values, key=lambda item: item["x"])
        text = " ".join(v["text"] for v in values).strip()
        if not text:
            continue
        x = min(v["x"] for v in values)
        y = min(v["y"] for v in values)
        right = max(v["x"] + v["width"] for v in values)
        bottom = max(v["y"] + v["height"] for v in values)
        confs = [v["confidence"] for v in values if v["confidence"] >= 0]
        lines.append({
            "text": text,
            "page": key[0],
            "x": x,
            "y": y,
            "width": right - x,
            "height": bottom - y,
            "confidence": round(sum(confs) / len(confs), 1) if confs else 0,
        })
    page_width = max([item["x"] + item["width"] for item in lines] or [1])
    page_height = max([item["y"] + item["height"] for item in lines] or [1])
    for line in lines:
        y_ratio = line["y"] / max(1, page_height)
        center_x = line["x"] + line["width"] / 2
        line["relative_position"] = "top" if y_ratio < 0.28 else "center" if y_ratio < 0.72 else "bottom"
        line["centered"] = abs(center_x - page_width / 2) / max(1, page_width) <= 0.24
        line["page_width"] = page_width
        line["page_height"] = page_height
    return {"tokens": tokens, "lines": lines, "error": None}


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


def run_fast_ocr(archivo, max_paginas=3, callback=None):
    return extraer_texto_documento_ocr(archivo, max_paginas=min(max_paginas or 3, 3), callback=callback)


def run_deep_ocr(archivo, max_paginas=6, callback=None):
    path = Path(archivo)
    if not path.exists() or not _tesseract_path():
        return _empty_result("pdf_ocr" if path.suffix.lower() == ".pdf" else "image_ocr", "Tesseract not found")
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return extraer_texto_documento_ocr(path, max_paginas=1, callback=callback)
    if path.suffix.lower() != ".pdf":
        return _empty_result("", "Unsupported file type")

    pages = render_first_pages(path, max_paginas=min(max_paginas or 6, 6), dpi=FALLBACK_DPI)
    sample_text = ""
    texts = []
    lang = "eng+spa"
    last_error = None
    candidates = {}
    for idx, page in enumerate(pages):
        if idx == 0:
            sample_text, _ = _run_tesseract_bytes(page["image_bytes"], "eng+spa", psm="6", timeout=30)
            lang = detectar_idioma_ocr_rapido(sample_text)
            if callback:
                callback(f"OCR: idioma detectado: {lang}")
        attempt = _run_best_ocr_image(
            page["image_bytes"],
            lang,
            psms=("3", "6", "11", "4") if idx == 0 else ("3", "6", "11"),
            timeout=60,
            allow_variants=idx == 0,
            allow_rotations=idx == 0,
        )
        last_error = attempt.get("error")
        if attempt.get("text"):
            texts.append(attempt["text"])
            if not candidates:
                candidates = _layout_candidates_for_image(
                    attempt.get("image_bytes", page["image_bytes"]),
                    attempt["text"],
                    lang,
                    psm=attempt.get("psm", "6"),
                )
                candidates.update(_candidate_metadata_from_attempt(attempt))
        if _extraer_isbns("\n".join(texts)) or _datos_suficientes("\n".join(texts)):
            break
    result = _finish_result(
        "\n".join(texts),
        "pdf_ocr_deep",
        lang,
        len(texts),
        FALLBACK_DPI,
        error=last_error,
        candidates=candidates,
    )
    return result


def _quick_pdf_sample(path: Path):
    try:
        return _render_pdf_page(path, 0, QUICK_DPI)
    except Exception:
        return None


def _prepare_image_bytes(path: Path):
    raw = path.read_bytes()
    return _prepare_image_bytes_raw(raw)


def _image_to_png_bytes(img):
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _resize_image_for_ocr(img):
    from PIL import Image

    width, height = img.size
    max_side = max(width, height)
    min_side = min(width, height)
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "LANCZOS", 1))

    if max_side > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / max_side
        return img.resize((max(1, int(width * scale)), max(1, int(height * scale))), resampling)
    if min_side and min_side < MIN_IMAGE_SIDE:
        scale = min(2.0, MIN_IMAGE_SIDE / min_side)
        return img.resize((max(1, int(width * scale)), max(1, int(height * scale))), resampling)
    return img


def _otsu_threshold(gray_img) -> int:
    hist = gray_img.histogram()
    total = sum(hist)
    if not total:
        return 128
    sum_total = sum(i * count for i, count in enumerate(hist))
    sum_bg = 0.0
    weight_bg = 0
    best_score = -1.0
    threshold = 128
    for i, count in enumerate(hist):
        weight_bg += count
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += i * count
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        score = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if score > best_score:
            best_score = score
            threshold = i
    return max(48, min(210, int(threshold)))


def _prepare_image_variants_raw(raw: bytes, include_rotations=False):
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        variants = []
        with Image.open(BytesIO(raw)) as img:
            base = ImageOps.exif_transpose(img).convert("L")
            base = _resize_image_for_ocr(base)
            normalized = ImageEnhance.Contrast(ImageOps.autocontrast(base)).enhance(1.35)
            variants.append({"name": "normalized", "image_bytes": _image_to_png_bytes(normalized), "rotation": 0})

            sharp = normalized.filter(ImageFilter.SHARPEN)
            variants.append({"name": "sharpened", "image_bytes": _image_to_png_bytes(sharp), "rotation": 0})

            threshold = _otsu_threshold(normalized)
            binary = normalized.point(lambda p: 255 if p > threshold else 0).convert("L")
            variants.append({"name": "binary", "image_bytes": _image_to_png_bytes(binary), "rotation": 0})

            mean_light = sum(normalized.histogram()[129:]) / max(1, sum(normalized.histogram()))
            if mean_light < 0.45:
                inverted = ImageOps.invert(normalized)
                variants.append({"name": "inverted", "image_bytes": _image_to_png_bytes(inverted), "rotation": 0})

            high_contrast = ImageEnhance.Contrast(normalized).enhance(1.8)
            variants.append({"name": "high_contrast", "image_bytes": _image_to_png_bytes(high_contrast), "rotation": 0})

            if include_rotations:
                for angle in (90, 270, 180):
                    rotated = normalized.rotate(angle, expand=True)
                    variants.append({
                        "name": f"rotated_{angle}",
                        "image_bytes": _image_to_png_bytes(rotated),
                        "rotation": angle,
                    })

        unique = []
        seen = set()
        for variant in variants:
            digest = hashlib.sha1(variant["image_bytes"]).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            unique.append(variant)
        return unique
    except Exception:
        return [{"name": "raw", "image_bytes": raw, "rotation": 0}]


def _prepare_image_bytes_raw(raw: bytes):
    variants = _prepare_image_variants_raw(raw, include_rotations=False)
    return variants[0]["image_bytes"] if variants else raw


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
    if _extraer_isbns(texto):
        return True
    lines = [l.strip() for l in texto.splitlines() if 4 <= len(l.strip()) <= 140]
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


def _ocr_attempt_is_good(texto: str, score: float) -> bool:
    return bool(_extraer_isbns(texto)) or _texto_util(texto) or score >= 70


def _run_best_ocr_image(
    raw_image_bytes: bytes,
    lang: str,
    psms=OCR_FAST_PSMS,
    timeout=45,
    allow_variants=True,
    allow_rotations=False,
    cancellation=None,
):
    variants = _prepare_image_variants_raw(raw_image_bytes, include_rotations=False) if allow_variants else [{
        "name": "prepared",
        "image_bytes": _prepare_image_bytes_raw(raw_image_bytes),
        "rotation": 0,
    }]
    attempts = []
    attempt_count = 0

    def run_variant(variant, psm_values):
        nonlocal attempt_count
        for psm in psm_values:
            if cancellation:
                cancellation.raise_if_cancelled()
            if attempt_count >= OCR_MAX_VARIANT_ATTEMPTS:
                return
            attempt_count += 1
            ocr_kwargs = {"psm": psm, "timeout": timeout}
            if cancellation is not None:
                ocr_kwargs["cancellation"] = cancellation
            text, error = _run_tesseract_bytes(variant["image_bytes"], lang, **ocr_kwargs)
            score = _ocr_text_score(text)
            attempts.append({
                "text": text,
                "error": error,
                "lang": lang,
                "psm": str(psm),
                "variant": variant.get("name", ""),
                "rotation": int(variant.get("rotation", 0) or 0),
                "image_bytes": variant["image_bytes"],
                "score": score,
            })

    for index, variant in enumerate(variants):
        psm_values = tuple(psms) if index == 0 else tuple(p for p in psms if str(p) in {"6", "11", "4"})[:2]
        run_variant(variant, psm_values or OCR_FAST_PSMS)
        best_so_far = max(attempts, key=lambda item: (item["score"], len(item["text"] or "")), default=None)
        if best_so_far and _ocr_attempt_is_good(best_so_far["text"], best_so_far["score"]):
            break

    best = max(attempts, key=lambda item: (item["score"], len(item["text"] or "")), default=None)
    if allow_rotations and (not best or best["score"] < 35):
        rotated_variants = [
            item for item in _prepare_image_variants_raw(raw_image_bytes, include_rotations=True)
            if int(item.get("rotation", 0) or 0)
        ]
        for variant in rotated_variants:
            if attempt_count >= OCR_MAX_VARIANT_ATTEMPTS + 4:
                break
            run_variant(variant, ("6", "11"))
        best = max(attempts, key=lambda item: (item["score"], len(item["text"] or "")), default=best)

    if best:
        best["attempts"] = [
            {
                "variant": item["variant"],
                "psm": item["psm"],
                "rotation": item["rotation"],
                "score": item["score"],
                "chars": len(item["text"] or ""),
            }
            for item in attempts[:12]
        ]
        return best
    prepared = _prepare_image_bytes_raw(raw_image_bytes)
    return {
        "text": "",
        "error": "OCR produced no attempts",
        "lang": lang,
        "psm": str(next(iter(psms), "6")),
        "variant": "prepared",
        "rotation": 0,
        "image_bytes": prepared,
        "score": 0.0,
        "attempts": [],
    }


def _empty_result(method, error=None):
    return {
        "texto": "",
        "metodo": method,
        "idioma_detectado": "eng",
        "paginas_analizadas": 0,
        "dpi": DEFAULT_DPI,
        "desde_cache": False,
        "isbn_detectado": "",
        "error": error,
    }


def _finish_result(texto, metodo, idioma, paginas, dpi, desde_cache=False, error=None, candidates=None):
    texto = _normalizar_texto(texto)
    isbns = _extraer_isbns(texto)
    result = {
        "texto": texto,
        "metodo": metodo,
        "idioma_detectado": idioma,
        "paginas_analizadas": paginas,
        "dpi": dpi,
        "desde_cache": desde_cache,
        "isbn_detectado": isbns[0] if isbns else "",
        "error": error,
    }
    if candidates:
        for key, value in candidates.items():
            if key.startswith("ocr_"):
                result[key] = value
    return result


def _layout_candidates_for_image(image_bytes: bytes, text: str, lang: str, psm="6", cancellation=None):
    try:
        layout = extract_layout_tokens(
            image_bytes, lang=lang, psm=psm, cancellation=cancellation,
        )
        candidates = detect_title_author_candidates(text, layout=layout)
        if layout.get("error"):
            candidates.setdefault("ocr_warnings", []).append(f"layout: {layout['error'][:80]}")
        return candidates
    except OperationCancelled:
        raise
    except Exception as exc:
        return {"ocr_warnings": [f"layout: {str(exc)[:80]}"]}


def _candidate_metadata_from_attempt(attempt):
    return {
        "ocr_preprocess_variant": attempt.get("variant", ""),
        "ocr_psm": str(attempt.get("psm", "")),
        "ocr_rotation": int(attempt.get("rotation", 0) or 0),
        "ocr_text_score": attempt.get("score", 0),
        "ocr_attempts": attempt.get("attempts", []),
    }


def extraer_texto_imagen_bytes_ocr(image_bytes: bytes, callback=None, cancellation=None):
    if not image_bytes:
        return _empty_result("image_ocr", "Empty image")
    if not _tesseract_path():
        return _empty_result("image_ocr", "Tesseract not found")

    prepared = _prepare_image_bytes_raw(image_bytes)
    sample_kwargs = {"psm": "6", "timeout": 25}
    if cancellation is not None:
        sample_kwargs["cancellation"] = cancellation
    sample, _ = _run_tesseract_bytes(prepared, "eng+spa", **sample_kwargs)
    lang = detectar_idioma_ocr_rapido(sample)
    if callback:
        callback(f"OCR: idioma detectado: {lang}")

    attempt = _run_best_ocr_image(
        image_bytes,
        lang,
        psms=OCR_COVER_PSMS,
        timeout=45,
        allow_variants=True,
        allow_rotations=True,
        cancellation=cancellation,
    )
    text = attempt.get("text", "")
    error = attempt.get("error")
    if not _ocr_attempt_is_good(text, attempt.get("score", 0)) and lang not in {"eng+spa", "spa+eng", "chi_sim", "chi_sim+eng"}:
        fallback = _run_best_ocr_image(
            image_bytes,
            "eng+spa",
            psms=OCR_FAST_PSMS,
            timeout=45,
            allow_variants=True,
            allow_rotations=False,
            cancellation=cancellation,
        )
        if fallback.get("score", 0) > attempt.get("score", 0) or len(fallback.get("text", "")) > len(text):
            attempt = fallback
            text = attempt.get("text", "")
            error = attempt.get("error")
            lang = "eng+spa"
    candidates = _layout_candidates_for_image(
        attempt.get("image_bytes", prepared),
        text,
        lang,
        psm=attempt.get("psm", "6"),
        cancellation=cancellation,
    )
    candidates.update(_candidate_metadata_from_attempt(attempt))
    return _finish_result(text, "image_ocr", lang, 1, DEFAULT_DPI, error=error, candidates=candidates)


def extraer_texto_documento_ocr(archivo, max_paginas=12, callback=None, cancellation=None):
    path = Path(archivo)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return _empty_result("", "Unsupported file type")
    if not path.exists():
        return _empty_result("", "File not found")
    if not _tesseract_path():
        return _empty_result("pdf_ocr" if suffix == ".pdf" else "image_ocr", "Tesseract not found")

    max_paginas = max(1, min(int(max_paginas or 12), 200))
    method = "pdf_ocr" if suffix == ".pdf" else "image_ocr"

    try:
        key = _cache_key(path)
        cached = _SESSION_OCR_CACHE.get(key)
        if cached:
            cached = dict(cached)
            cached["desde_cache"] = True
            return cached
    except Exception:
        key = ""

    if suffix in IMAGE_EXTENSIONS:
        raw_image_bytes = path.read_bytes()
        image_bytes = _prepare_image_bytes_raw(raw_image_bytes)
        sample, _ = _run_tesseract_bytes(image_bytes, "eng+spa", psm="6", timeout=25, cancellation=cancellation)
        lang = detectar_idioma_ocr_rapido(sample)
        if callback:
            callback(f"OCR: idioma detectado: {lang}")
        attempt = _run_best_ocr_image(
            raw_image_bytes,
            lang,
            psms=OCR_COVER_PSMS,
            timeout=45,
            allow_variants=True,
            allow_rotations=True,
            cancellation=cancellation,
        )
        text = attempt.get("text", "")
        error = attempt.get("error")
        if not _ocr_attempt_is_good(text, attempt.get("score", 0)) and lang not in {"eng+spa", "spa+eng", "chi_sim", "chi_sim+eng"}:
            fallback = _run_best_ocr_image(
                raw_image_bytes,
                "eng+spa",
                psms=OCR_FAST_PSMS,
                timeout=45,
                allow_variants=True,
                allow_rotations=False,
                cancellation=cancellation,
            )
            if fallback.get("score", 0) > attempt.get("score", 0) or len(fallback.get("text", "")) > len(text):
                attempt = fallback
                text = fallback.get("text", "")
                error = fallback.get("error")
                lang = "eng+spa"
        candidates = _layout_candidates_for_image(
            attempt.get("image_bytes", image_bytes),
            text,
            lang,
            psm=attempt.get("psm", "6"),
        )
        candidates.update(_candidate_metadata_from_attempt(attempt))
        result = _finish_result(text, method, lang, 1, DEFAULT_DPI, error=error, candidates=candidates)
        if key:
            _SESSION_OCR_CACHE[key] = dict(result)
        return result

    sample_bytes = _quick_pdf_sample(path)
    sample_text = ""
    if sample_bytes:
        sample_text, _ = _run_tesseract_bytes(sample_bytes, "eng+spa", psm="6", timeout=25, cancellation=cancellation)
    lang = detectar_idioma_ocr_rapido(sample_text)
    if callback:
        callback(f"OCR: idioma detectado: {lang}")

    pages_to_try = max_paginas
    texts = []
    candidates = {}
    used_dpi = DEFAULT_DPI
    last_error = None
    page_index = 0

    while page_index < pages_to_try:
        if cancellation:
            cancellation.raise_if_cancelled()
        if callback:
            callback(f"OCR: analizando página {page_index + 1}/{pages_to_try}")
        try:
            image_bytes = _render_pdf_page(path, page_index, DEFAULT_DPI)
        except Exception as exc:
            last_error = str(exc)
            break
        if not image_bytes:
            break

        attempt = _run_best_ocr_image(
            image_bytes,
            lang,
            psms=OCR_COVER_PSMS if page_index == 0 else OCR_FAST_PSMS,
            timeout=45,
            allow_variants=page_index == 0,
            allow_rotations=page_index == 0,
            cancellation=cancellation,
        )
        text = attempt.get("text", "")
        last_error = attempt.get("error")
        if text:
            texts.append(text)
            if not candidates:
                candidates = _layout_candidates_for_image(
                    attempt.get("image_bytes", image_bytes),
                    text,
                    lang,
                    psm=attempt.get("psm", "6"),
                )
                candidates.update(_candidate_metadata_from_attempt(attempt))
            joined = "\n".join(texts)
            if _extraer_isbns(text):
                if callback:
                    callback("OCR: ISBN encontrado; buscando evidencia bibliográfica adicional")
            if _datos_suficientes(joined):
                break

        page_index += 1

    joined_text = "\n".join(texts)
    if not _texto_util(joined_text):
        try:
            if callback:
                callback("OCR: analizando página 1/1 a 300 DPI")
            image_bytes = _render_pdf_page(path, 0, FALLBACK_DPI)
            attempt_300 = _run_best_ocr_image(
                image_bytes,
                lang,
                psms=OCR_COVER_PSMS,
                timeout=60,
                allow_variants=True,
                allow_rotations=True,
                cancellation=cancellation,
            ) if image_bytes else {"text": "", "error": last_error, "score": 0}
            text_300, error_300 = attempt_300.get("text", ""), attempt_300.get("error")
            if len(text_300) > len(joined_text):
                joined_text = text_300
                used_dpi = FALLBACK_DPI
                last_error = error_300
                candidates = _layout_candidates_for_image(
                    attempt_300.get("image_bytes", image_bytes),
                    text_300,
                    lang,
                    psm=attempt_300.get("psm", "6"),
                )
                candidates.update(_candidate_metadata_from_attempt(attempt_300))
        except Exception as exc:
            last_error = str(exc)

    if callback and not _datos_suficientes(joined_text):
        callback("OCR: sin datos suficientes")

    result = _finish_result(
        joined_text,
        method,
        lang,
        min(max(page_index, 1), pages_to_try),
        used_dpi,
        error=last_error,
        candidates=candidates,
    )
    if key:
        _SESSION_OCR_CACHE[key] = dict(result)
    return result
