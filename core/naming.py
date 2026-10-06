"""Filename and human-readable title cleanup without UI or storage dependencies."""

from __future__ import annotations

import re
from collections.abc import Callable

from .normalizer import normalizar_texto


def sanitize_filename(text: str, max_length: int = 170) -> str:
    text = str(text or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text)
    text = re.sub(r"\s+", " ", text).strip().rstrip(". ")
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    return text or "SIN_TITULO"


def repair_mojibake(text: str) -> str:
    text = str(text or "")
    if not text:
        return ""
    legacy_replacements = {
        "\x82": "é",
        "\x85": "à",
        "\x8a": "è",
        "\x8d": "ì",
        "\x95": "ò",
        "\x97": "ù",
        "\xa4": "ñ",
        "¨": "¿",
    }
    for invalid, replacement in legacy_replacements.items():
        text = text.replace(invalid, replacement)

    try:
        from ftfy import fix_text
    except ImportError:
        fix_text = None
    if fix_text is not None:
        try:
            repaired = fix_text(text)
        except (TypeError, UnicodeError, ValueError):
            repaired = ""
        if repaired and len(re.findall(r"[ÃÂ�]", repaired)) <= len(re.findall(r"[ÃÂ�]", text)):
            text = repaired

    replacements = {
        "Ã¡": "á",
        "Ã©": "é",
        "Ã­": "í",
        "Ã³": "ó",
        "Ãº": "ú",
        "Ã±": "ñ",
        "Ã\x81": "Á",
        "Ã\x89": "É",
        "Ã\x8d": "Í",
        "Ã\x93": "Ó",
        "Ã\x9a": "Ú",
        "Ã\x91": "Ñ",
        "Ã ": "à",
        "Ã¨": "è",
        "Ã¢": "â",
        "Ãª": "ê",
        "Ã´": "ô",
        "Ã¼": "ü",
        "Â¿": "¿",
        "Â¡": "¡",
        "Â«": "«",
        "Â»": "»",
        "CÃLCULO": "CÁLCULO",
        "cÃlculo": "cálculo",
        "CÃlculo": "Cálculo",
    }
    for invalid, replacement in replacements.items():
        text = text.replace(invalid, replacement)

    if any(marker in text for marker in ("Ã", "Â", "â€")):
        try:
            candidate = text.encode("cp1252", errors="ignore").decode("utf-8", errors="ignore")
        except UnicodeError:
            candidate = ""
        current_noise = len(re.findall(r"[ÃÂ�]", text))
        candidate_noise = len(re.findall(r"[ÃÂ�]", candidate))
        if candidate.strip() and candidate_noise <= current_noise:
            text = candidate
    return text


def author_cleanup_variants(author: str) -> list[list[str]]:
    tokens = [token for token in normalizar_texto(author).split() if token]
    if len(tokens) < 2:
        return []
    variants = [tokens, tokens[1:] + tokens[:1], tokens[-1:] + tokens[:-1]]
    unique = []
    seen = set()
    for variant in variants:
        key = tuple(variant)
        if key and key not in seen:
            seen.add(key)
            unique.append(variant)
    return sorted(unique, key=len, reverse=True)


def _remove_initial_author_fragment(title: str, author: str) -> str:
    words = str(title or "").split()
    if len(words) < 3:
        return title
    first_token = normalizar_texto(words[0]).replace(" ", "")
    if len(first_token) < 4:
        return title
    author_tokens = {
        normalizar_texto(token).replace(" ", "")
        for token in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'.-]*", str(author or ""))
    }
    author_tokens.update(token for token in normalizar_texto(author).split() if token)
    if not any(token and token != first_token and token.endswith(first_token) for token in author_tokens):
        return title
    remaining = " ".join(words[1:]).strip(" -_.,;")
    if len(normalizar_texto(remaining).split()) < 2:
        return title
    return remaining


def remove_attached_author(title: str, author: str = "") -> str:
    if not title or not author:
        return title
    words = title.split()
    if len(words) < 3:
        return title
    title = _remove_initial_author_fragment(title, author)
    words = title.split()
    if len(words) < 3:
        return title
    normalized_words = [normalizar_texto(word) for word in words]
    incomplete_endings = {"de", "del", "la", "las", "los", "el", "y", "and", "of", "the"}

    for variant in author_cleanup_variants(author):
        count = len(variant)
        if len(normalized_words) <= count or normalized_words[-count:] != variant:
            continue
        remaining = " ".join(words[:-count]).strip(" -_.,;")
        normalized_remaining = normalizar_texto(remaining)
        if not normalized_remaining or normalized_remaining.split()[-1] in incomplete_endings:
            continue
        if len(normalized_remaining.replace(" ", "")) < 4:
            continue
        return remaining
    return title


def remove_ocr_title_noise(title: str) -> str:
    tokens = str(title or "").split()
    if len(tokens) < 4:
        return title
    protected = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}
    noise = []
    for token in tokens:
        clean = token.strip(".,;:!?¡¿()[]{}")
        if 2 <= len(clean) <= 4 and clean.isupper() and clean not in protected:
            noise.append(token)
    if len(noise) < 2:
        return title
    filtered = [
        token
        for token in tokens
        if not (token in noise and token.strip(".,;:!?¡¿()[]{}") not in protected)
    ]
    return " ".join(filtered) or title


def clean_readable_title(
    title: str,
    author: str = "",
    *,
    extract_filename_metadata: Callable[[str], dict],
    similarity: Callable[[str, str], float],
    clean_distribution_noise: Callable[[str], str],
    correct_compact_title: Callable[[str], str],
) -> str:
    title = repair_mojibake(title).replace("_", " ")
    title = re.sub(r"\s*\((?:15|16|17|18|19|20)\d{2}\)\s*$", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -_.,;")
    if not title:
        return ""
    repeated_parts = [part.strip(" -_.,;") for part in re.split(r"\s+-\s+", title) if part.strip(" -_.,;")]
    if len(repeated_parts) == 2 and normalizar_texto(repeated_parts[0]) == normalizar_texto(repeated_parts[1]):
        title = repeated_parts[0]
    if author:
        metadata = extract_filename_metadata(title)
        if metadata.get("titulo") and metadata.get("autor") and similarity(metadata.get("autor", ""), author) >= 0.70:
            title = metadata["titulo"]
        normalized_author = normalizar_texto(author)
        title_without_year = re.sub(r"\b(?:1[5-9]\d{2}|20\d{2})\b", " ", title)
        normalized_title = normalizar_texto(title_without_year)
        if normalized_author and normalized_title and (
            normalized_title == normalized_author
            or set(normalized_title.split()) <= set(normalized_author.split())
        ):
            return ""
    title = clean_distribution_noise(correct_compact_title(title))
    title = re.sub(r"(?i)\b(y|and|et)\s+\1\b", r"\1", title)
    title = re.sub(r"(?<!^)\bY\b", "y", title)
    title = remove_ocr_title_noise(title)
    title = remove_attached_author(title, author)
    title = re.sub(r"\s+", " ", title).strip(" -_.,;")
    return sanitize_filename(title, 140) if title else ""


def prefer_latin_author_alias(author: str) -> str:
    author = repair_mojibake(author)
    if not author:
        return ""
    match = re.search(r"[\[\(]([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .,'’\-]{3,90})[\]\)]", author)
    if not match:
        return author
    outside = re.sub(r"[\[\(][^\]\)]*[\]\)]", " ", author).strip()
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\u0400-\u04ff\u0600-\u06ff]", outside):
        return match.group(1).strip()
    return author


def suggested_filename(
    author,
    title,
    year,
    isbn,
    extension,
    *,
    clean_title: Callable[[str, str], str],
) -> str:
    author = sanitize_filename(prefer_latin_author_alias(author) or "Autor desconocido", 80)
    title = clean_title(title, author) or sanitize_filename(repair_mojibake(title) or "Título desconocido", 120)
    parts = [f"{author} - {title}"]
    if year:
        parts.append(f"({year})")
    if isbn:
        parts.append(f"[{isbn}]")
    return sanitize_filename(" ".join(parts), 210) + extension.lower()
