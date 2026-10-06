"""Conservative front-matter analysis for book identity signals."""

from __future__ import annotations

import re

from book_identity_evidence import IdentityEvidence, extract_isbns, make_evidence, normalize_comparison_text


FALSE_POSITIVE_PATTERNS = [
    r"^\s*(indice|índice|table of contents|contents|contenido|sommaire|index)\s*$",
    r"^\s*(prologo|pr[oó]logo|preface|prefacio|foreword|introducci[oó]n|introduction)\s*$",
    r"^\s*(chapter|cap[ií]tulo|capitulo|parte|part|livre|book)\s+([ivxlcdm]+|\d+)\b",
    r"^\s*(copyright|all rights reserved|derechos reservados|legal notice)\b",
    r"^\s*(editorial|publisher|published by|ediciones|collection|colecci[oó]n)\b",
    r"https?://|www\.",
]


ROLE_AUTHOR_PATTERNS = [
    r"\b(?:by|author|autor|autora|por|de|auteur|written by)\s+(.{3,90})$",
    r"^(.{3,90})\s+(?:author|autor|autora|auteur)$",
]


def _short_lines(text: str, max_lines: int = 120, max_chars: int = 16000) -> list[str]:
    text = str(text or "")[:max_chars]
    lines = []
    for raw in text.splitlines()[:max_lines]:
        line = re.sub(r"\s+", " ", raw).strip(" \t-|")
        if line:
            lines.append(line[:180])
    return lines


def is_false_positive_heading(line: str) -> bool:
    line = re.sub(r"\s+", " ", str(line or "")).strip()
    if not line:
        return True
    if len(line) > 130:
        return True
    if re.fullmatch(r"\d+", line):
        return True
    if len(re.findall(r"[^\w\sÀ-ÿ\u4e00-\u9fff.,:;!?¡¿'’\"()&/\-]", line)) > max(2, len(line) // 12):
        return True
    return any(re.search(pattern, line, re.I) for pattern in FALSE_POSITIVE_PATTERNS)


def _looks_like_title(line: str) -> bool:
    if is_false_positive_heading(line):
        return False
    normalized = normalize_comparison_text(line)
    tokens = normalized.split()
    if not tokens:
        return False
    if len(tokens) > 14 and not re.search(r"[:;]", line):
        return False
    weak = {"volumen", "volume", "edition", "edicion", "serie", "series"}
    if set(tokens) <= weak:
        return False
    return True


def _looks_like_author(line: str) -> bool:
    if is_false_positive_heading(line):
        return False
    if re.search(r"\b(editorial|publisher|collection|colecci[oó]n|isbn|copyright)\b", line, re.I):
        return False
    words = [w for w in re.split(r"\s+", line.strip()) if w]
    if not (1 <= len(words) <= 7):
        return False
    letters = re.findall(r"[A-Za-zÀ-ÿ]", line)
    cjk = re.findall(r"[\u4e00-\u9fff]", line)
    return len(letters) >= 3 or len(cjk) >= 2


def analyze_front_matter(text: str, source: str = "front_matter") -> list[IdentityEvidence]:
    lines = _short_lines(text)
    evidence: list[IdentityEvidence] = []
    for isbn in extract_isbns(text):
        ev = make_evidence("isbn", isbn, source, 88, location="front matter", notes=("valid ISBN",))
        if ev:
            evidence.append(ev)

    title_index = -1
    for index, line in enumerate(lines[:50]):
        if _looks_like_title(line):
            ev = make_evidence("title", line, source, 70, location=f"line {index + 1}")
            if ev:
                evidence.append(ev)
                title_index = index
                break

    author_candidates = []
    if title_index >= 0:
        window = lines[max(0, title_index - 4): title_index] + lines[title_index + 1: title_index + 6]
    else:
        window = lines[:12]
    for line in window:
        author = ""
        for pattern in ROLE_AUTHOR_PATTERNS:
            match = re.search(pattern, line, re.I)
            if match:
                author = match.group(1).strip()
                break
        if not author and _looks_like_author(line):
            author = line
        if author and _looks_like_author(author):
            author_candidates.append(author)
    if author_candidates:
        ev = make_evidence("author", author_candidates[0], source, 66, location="near title")
        if ev:
            evidence.append(ev)

    for line in lines[:80]:
        match = re.search(r"\b(?:copyright|©|published|publicado|edition|edici[oó]n)?\s*(1[4-9]\d{2}|20\d{2})\b", line, re.I)
        if match:
            ev = make_evidence("year", match.group(1), source, 42, location="front matter")
            if ev:
                evidence.append(ev)
            break
    return evidence


def extract_front_matter_candidates(text: str, source: str = "front_matter") -> list[IdentityEvidence]:
    return analyze_front_matter(text, source=source)
