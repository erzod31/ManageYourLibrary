"""PDF identity helpers used by the Deep Identity Scan layer."""

from __future__ import annotations

from pathlib import Path

from book_identity_evidence import IdentityEvidence, evidence_from_existing_data
from front_matter_analyzer import analyze_front_matter


PDF_TEXTUAL = "PDF_TEXTUAL"
PDF_SCANNED = "PDF_SCANNED"
PDF_MIXED = "PDF_MIXED"
PDF_PROTECTED = "PDF_PROTECTED"
PDF_CORRUPT = "PDF_CORRUPT"
PDF_UNKNOWN = "PDF_UNKNOWN"


def _useful_text(text: str) -> bool:
    stripped = "".join(ch for ch in str(text or "") if ch.isalnum() or ch.isspace()).strip()
    return len(stripped) >= 80


def classify_pdf_from_signals(page_texts=None, *, encrypted=False, errors=None, ocr_texts=None) -> str:
    if encrypted:
        return PDF_PROTECTED
    if errors:
        return PDF_CORRUPT
    page_texts = list(page_texts or [])
    ocr_texts = list(ocr_texts or [])
    text_pages = sum(1 for text in page_texts if _useful_text(text))
    ocr_pages = sum(1 for text in ocr_texts if _useful_text(text))
    if text_pages and ocr_pages:
        return PDF_MIXED
    if text_pages:
        return PDF_TEXTUAL
    if ocr_pages:
        return PDF_SCANNED
    return PDF_UNKNOWN


def build_pdf_identity_evidence(path: Path, datos=None, page_texts=None, ocr_texts=None) -> list[IdentityEvidence]:
    evidence = evidence_from_existing_data(datos or {}, filename=Path(path).name)
    for text in list(page_texts or [])[:8]:
        evidence.extend(analyze_front_matter(text, source="pdf_text"))
    for text in list(ocr_texts or [])[:5]:
        evidence.extend(analyze_front_matter(text, source="pdf_ocr"))
    return evidence
