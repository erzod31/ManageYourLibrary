"""Common evidence primitives for local book identity resolution.

The helpers in this module intentionally work with short metadata signals only.
They do not store full extracted text, OCR pages, or document contents.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
import re
import unicodedata


NOISE_WORDS = {
    "azw",
    "azw3",
    "book",
    "books",
    "calibre",
    "converted",
    "copy",
    "copia",
    "digital",
    "doc",
    "documento",
    "duplicate",
    "duplicado",
    "ebook",
    "edicion",
    "edition",
    "epub",
    "final",
    "libro",
    "microsoft",
    "mobi",
    "pdf",
    "scan",
    "sin",
    "titulo",
    "unknown",
    "version",
    "word",
}


ROLE_PREFIXES = (
    r"translated by",
    r"translation by",
    r"traducido por",
    r"traduccion de",
    r"traductor",
    r"traductora",
    r"edited by",
    r"editado por",
    r"edicion de",
    r"illustrated by",
    r"ilustrado por",
    r"prologo de",
    r"foreword by",
    r"introduction by",
    r"introduccion de",
)


CORPORATE_AUTHOR_HINTS = {
    "academy",
    "agencia",
    "association",
    "biblioteca",
    "committee",
    "editorial",
    "foundation",
    "fundacion",
    "institute",
    "instituto",
    "ministerio",
    "press",
    "society",
    "universidad",
    "university",
}


TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "de",
    "del",
    "der",
    "des",
    "el",
    "en",
    "et",
    "la",
    "las",
    "le",
    "les",
    "los",
    "of",
    "the",
    "und",
    "y",
}


@dataclass(frozen=True)
class IdentityEvidence:
    field: str
    value: str
    source: str
    weight: float
    quality: float = 1.0
    location: str = ""
    notes: tuple[str, ...] = dataclass_field(default_factory=tuple)
    normalized: str = ""

    def __post_init__(self):
        value = clean_display_value(self.value)
        quality = max(0.0, min(1.0, float(self.quality or 0.0)))
        normalized = self.normalized or normalize_for_field(self.field, value)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "quality", quality)
        object.__setattr__(self, "weight", float(self.weight or 0.0))
        object.__setattr__(self, "normalized", normalized)
        if isinstance(self.notes, list):
            object.__setattr__(self, "notes", tuple(str(n) for n in self.notes if n))


def remove_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text or ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def clean_display_value(value: str, max_len: int = 180) -> str:
    value = str(value or "").replace("\r", " ").replace("\n", " ")
    value = re.sub(r"\s+", " ", value).strip(" \t-_|:;,.")
    return value[:max_len].strip()


def normalize_comparison_text(text: str) -> str:
    text = remove_accents(str(text or "").casefold())
    text = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", text)
    text = re.sub(r"[_./\\\-]+", " ", text)
    text = "".join(ch if ch.isalnum() else " " for ch in text)
    tokens = [token for token in text.split() if token not in NOISE_WORDS]
    return " ".join(tokens)


def normalize_title(title: str) -> str:
    title = clean_filename_noise(title)
    tokens = normalize_comparison_text(title).split()
    if len(tokens) > 1:
        filtered = [token for token in tokens if token not in TITLE_STOPWORDS]
        if filtered:
            tokens = filtered
    return " ".join(tokens)


def _looks_corporate_author(author: str) -> bool:
    tokens = set(normalize_comparison_text(author).split())
    return bool(tokens & CORPORATE_AUTHOR_HINTS)


def normalize_author(author: str) -> str:
    author = clean_display_value(author, 160)
    if not author:
        return ""
    author = re.sub(r"(?i)^(?:%s)\s*[:\-]?\s+" % "|".join(ROLE_PREFIXES), " ", author).strip()
    if "," in author and not _looks_corporate_author(author):
        parts = [p.strip() for p in author.split(",") if p.strip()]
        if len(parts) == 2 and all(len(p.split()) <= 4 for p in parts):
            author = f"{parts[1]} {parts[0]}"
    return normalize_comparison_text(author)


def normalize_for_field(field_name: str, value: str) -> str:
    field_name = str(field_name or "").lower()
    if field_name == "title":
        return normalize_title(value)
    if field_name == "author":
        return normalize_author(value)
    if field_name == "isbn":
        return canonical_isbn(value)
    if field_name == "year":
        match = re.search(r"\b(1[4-9]\d{2}|20\d{2})\b", str(value or ""))
        return match.group(1) if match else ""
    return normalize_comparison_text(value)


def clean_filename_noise(name: str) -> str:
    stem = Path(str(name or "")).stem
    stem = re.sub(r"\[[^\]]*\]", " ", stem)
    stem = re.sub(r"\((?:19|20)\d{2}\)", " ", stem)
    stem = re.sub(r"\b(?:19|20)\d{2}\b", " ", stem)
    stem = re.sub(r"(?i)\b(?:microsoft\s+word|converted|unknown|ebook|scan|final|libro|book|calibre)\b", " ", stem)
    stem = re.sub(r"[_./\\]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem)
    return clean_display_value(stem, 180)


def clean_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", str(value or "")).upper()


def is_valid_isbn10(value: str) -> bool:
    isbn = clean_isbn(value)
    if len(isbn) != 10 or len(set(isbn)) == 1:
        return False
    total = 0
    for index, char in enumerate(isbn):
        if char == "X" and index == 9:
            digit = 10
        elif char.isdigit():
            digit = int(char)
        else:
            return False
        total += digit * (10 - index)
    return total % 11 == 0


def is_valid_isbn13(value: str) -> bool:
    isbn = clean_isbn(value)
    if len(isbn) != 13 or len(set(isbn)) == 1 or not isbn.startswith(("978", "979")):
        return False
    total = sum(int(ch) * (1 if index % 2 == 0 else 3) for index, ch in enumerate(isbn[:12]))
    return (10 - (total % 10)) % 10 == int(isbn[-1])


def isbn10_to_isbn13(value: str) -> str:
    isbn10 = clean_isbn(value)
    if not is_valid_isbn10(isbn10):
        return ""
    base = "978" + isbn10[:9]
    total = sum(int(ch) * (1 if index % 2 == 0 else 3) for index, ch in enumerate(base))
    return base + str((10 - (total % 10)) % 10)


def canonical_isbn(value: str) -> str:
    isbn = clean_isbn(value)
    if is_valid_isbn13(isbn):
        return isbn
    if is_valid_isbn10(isbn):
        return isbn10_to_isbn13(isbn)
    return ""


def extract_isbns(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    patterns = [
        r"ISBN(?:-1[03])?\s*[: ]?\s*([0-9Xx][0-9Xx\-\s]{8,25}[0-9Xx])",
        r"\b(97[89][0-9\-\s]{10,20}[0-9])\b",
        r"\b([0-9Xx][0-9Xx\-\s]{8,18}[0-9Xx])\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, str(text), re.I):
            isbn = canonical_isbn(match.group(1))
            if isbn and isbn not in found:
                found.append(isbn)
    return found


def make_evidence(
    field_name: str,
    value: str,
    source: str,
    weight: float,
    *,
    quality: float = 1.0,
    location: str = "",
    notes: list[str] | tuple[str, ...] | None = None,
) -> IdentityEvidence | None:
    evidence = IdentityEvidence(field_name, value, source, weight, quality, location, tuple(notes or ()))
    if not evidence.value or not evidence.normalized:
        return None
    return evidence


def evidence_from_existing_data(datos: dict, filename: str = "") -> list[IdentityEvidence]:
    datos = datos or {}
    evidence: list[IdentityEvidence] = []
    title_norms = {
        normalize_comparison_text(datos.get(key, ""))
        for key in ("titulo_local", "titulo_texto", "titulo_nombre")
        if datos.get(key)
    }

    def add(field_name, key, source, weight, quality=1.0, location="", notes=None):
        if field_name == "author" and key in {"autor_local", "autor_nombre"}:
            author_norm = normalize_comparison_text(datos.get(key, ""))
            if author_norm and author_norm in title_norms:
                return
        ev = make_evidence(field_name, datos.get(key, ""), source, weight, quality=quality, location=location, notes=notes)
        if ev:
            evidence.append(ev)

    add("title", "titulo_local", "metadata", 82, location="structured metadata")
    add("author", "autor_local", "metadata", 82, location="structured metadata")
    add("publisher", "editorial_local", "metadata", 50)
    add("year", "anio_local", "metadata", 55)
    add("title", "titulo_texto", "front_matter", 70, location="first blocks")
    add("author", "autor_texto", "front_matter", 68, location="near title")
    add("publisher", "editorial_texto", "front_matter", 42)
    add("year", "anio_texto", "front_matter", 45)
    add("title", "titulo_nombre", "filename", 48)
    add("author", "autor_nombre", "filename", 48)

    for isbn in list(datos.get("isbns") or [])[:4]:
        ev = make_evidence("isbn", isbn, "local_isbn", 90, location="metadata/text")
        if ev:
            evidence.append(ev)
    ev = make_evidence("isbn", datos.get("ocr_isbn", ""), "ocr", 72, quality=0.72, location="selective OCR")
    if ev:
        evidence.append(ev)

    if filename and not any(ev.field == "title" and ev.source == "filename" for ev in evidence):
        ev = make_evidence("title", clean_filename_noise(filename), "filename", 36, notes=("fallback filename hint",))
        if ev:
            evidence.append(ev)
    return evidence
