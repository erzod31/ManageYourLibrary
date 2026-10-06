"""Shared Deep Identity Scan scorer.

The scorer combines short evidence signals into a conservative bibliographic
identity decision. It deliberately avoids using long document text.
"""

from __future__ import annotations

from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path

from bibliographic_validator import candidates_to_evidence
from book_identity_evidence import (
    IdentityEvidence,
    evidence_from_existing_data,
    normalize_comparison_text,
)
from kindle_identity_reader import KINDLE_FORMATS, build_kindle_identity_evidence
from pdf_identity_reader import build_pdf_identity_evidence, classify_pdf_from_signals


AUTO_RENAME = "AUTO_RENAME"
QUICK_REVIEW = "QUICK_REVIEW"
REVIEW_AGAIN = "REVIEW_AGAIN"
UNIDENTIFIED = "UNIDENTIFIED"


def similarity(a: str, b: str) -> float:
    a = normalize_comparison_text(a)
    b = normalize_comparison_text(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    compact_a = a.replace(" ", "")
    compact_b = b.replace(" ", "")
    if compact_a and compact_a == compact_b:
        return 0.98
    return SequenceMatcher(None, a, b).ratio()


def decision_for_confidence(confidence_percent: float) -> str:
    if confidence_percent >= 90:
        return AUTO_RENAME
    if confidence_percent >= 75:
        return QUICK_REVIEW
    if confidence_percent >= 50:
        return REVIEW_AGAIN
    return UNIDENTIFIED


def _same_group(field_name: str, a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if field_name in {"isbn", "year"}:
        return False
    threshold = 0.88 if field_name == "title" else 0.84
    return similarity(a, b) >= threshold


def group_equivalent_evidence(evidences: list[IdentityEvidence], field_name: str) -> list[dict]:
    groups: list[dict] = []
    for evidence in [ev for ev in evidences if ev.field == field_name and ev.normalized]:
        placed = False
        for group in groups:
            if _same_group(field_name, group["normalized"], evidence.normalized):
                group["items"].append(evidence)
                placed = True
                break
        if not placed:
            groups.append({"normalized": evidence.normalized, "items": [evidence]})

    for group in groups:
        sources = {ev.source for ev in group["items"] if ev.source}
        weighted = sum(max(0.0, ev.weight) * ev.quality for ev in group["items"])
        source_bonus = min(14.0, max(0, len(sources) - 1) * 5.0)
        best_item = sorted(group["items"], key=lambda ev: (ev.weight * ev.quality, len(ev.value)), reverse=True)[0]
        group["score"] = min(100.0, weighted + source_bonus)
        group["sources"] = sources
        group["best"] = best_item
    return sorted(groups, key=lambda g: g["score"], reverse=True)


def _field_confidence(groups: list[dict], cap: float) -> float:
    if not groups:
        return 0.0
    return min(cap, groups[0]["score"])


def _detect_conflicts(groups: list[dict], field_name: str) -> list[str]:
    if len(groups) < 2:
        return []
    top, second = groups[0], groups[1]
    if second["score"] < 45 or second["score"] < top["score"] * 0.58:
        return []
    if field_name == "year":
        try:
            if abs(int(top["normalized"]) - int(second["normalized"])) <= 1:
                return []
        except Exception:
            pass
    if field_name in {"title", "author"} and similarity(top["normalized"], second["normalized"]) >= 0.62:
        return []
    label = "título" if field_name == "title" else "autor" if field_name == "author" else field_name
    return [f"Conflicto fuerte de {label}: {top['best'].value} / {second['best'].value}"]


def _is_filename_only(evidences: list[IdentityEvidence]) -> bool:
    meaningful = [ev for ev in evidences if ev.field in {"title", "author", "isbn", "year"}]
    return bool(meaningful) and all(ev.source == "filename" for ev in meaningful)


def _ocr_quality_warnings(evidences: list[IdentityEvidence]) -> tuple[list[str], float]:
    warnings = []
    penalty = 0.0
    for ev in evidences:
        if "ocr" in ev.source and ev.quality < 0.55:
            warnings.append("OCR de baja calidad usado solo como pista débil")
            penalty += 8.0
            break
    return warnings, penalty


def _summary_for_group(label: str, group: dict | None) -> str:
    if not group:
        return ""
    sources = ", ".join(sorted(group["sources"])) or "fuente local"
    return f"{label} apoyado por {sources}"


def score_identity(evidences: list[IdentityEvidence], external_evidences: list[IdentityEvidence] | None = None) -> dict:
    all_evidence = list(evidences or []) + list(external_evidences or [])
    title_groups = group_equivalent_evidence(all_evidence, "title")
    author_groups = group_equivalent_evidence(all_evidence, "author")
    isbn_groups = group_equivalent_evidence(all_evidence, "isbn")
    year_groups = group_equivalent_evidence(all_evidence, "year")

    best_title = title_groups[0] if title_groups else None
    best_author = author_groups[0] if author_groups else None
    best_isbn = isbn_groups[0] if isbn_groups else None
    best_year = year_groups[0] if year_groups else None

    title_conf = _field_confidence(title_groups, 94.0)
    author_conf = _field_confidence(author_groups, 92.0)
    isbn_conf = _field_confidence(isbn_groups, 98.0)
    year_conf = _field_confidence(year_groups, 76.0)

    confidence = 0.0
    if best_isbn:
        confidence += isbn_conf * 0.36
        confidence += title_conf * 0.32
        confidence += author_conf * 0.22
        confidence += year_conf * 0.06
    else:
        confidence += title_conf * 0.48
        confidence += author_conf * 0.35
        confidence += year_conf * 0.08

    independent_sources = {
        ev.source
        for ev in all_evidence
        if ev.field in {"title", "author", "isbn"} and ev.source and ev.normalized
    }
    if len(independent_sources) >= 3 and best_title and (best_author or best_isbn):
        confidence += 8
    elif len(independent_sources) >= 2 and best_title and (best_author or best_isbn):
        confidence += 4

    conflicts = []
    conflicts.extend(_detect_conflicts(title_groups, "title"))
    conflicts.extend(_detect_conflicts(author_groups, "author"))
    conflicts.extend(_detect_conflicts(year_groups, "year"))
    if conflicts:
        confidence -= min(28, 12 + len(conflicts) * 6)

    warnings, ocr_penalty = _ocr_quality_warnings(all_evidence)
    confidence -= ocr_penalty

    if not best_title:
        confidence = min(confidence, 49)
        warnings.append("No hay título fiable")
    if best_title and not (best_author or best_isbn):
        confidence = min(confidence, 74)
        warnings.append("Título sin autor o ISBN confirmable")
    if best_author and not best_title:
        confidence = min(confidence, 45)
    if _is_filename_only(all_evidence):
        if best_title and best_author:
            confidence = max(confidence, 50)
        confidence = min(confidence, 64)
        warnings.append("Solo hay pistas del nombre de archivo")

    confidence = max(0.0, min(99.0, round(confidence, 1)))
    decision = decision_for_confidence(confidence)
    title_value = best_title["best"].value if best_title else ""
    author_value = best_author["best"].value if best_author else ""
    isbn_value = best_isbn["best"].value if best_isbn else ""
    year_value = best_year["best"].value if best_year else ""

    summary = [
        item
        for item in [
            _summary_for_group("Título", best_title),
            _summary_for_group("Autor", best_author),
            _summary_for_group("ISBN", best_isbn),
            _summary_for_group("Año", best_year),
        ]
        if item
    ]
    if conflicts:
        summary.append("Contradicciones detectadas; decisión conservadora")

    return {
        "title": title_value,
        "author": author_value,
        "year": year_value,
        "isbn": isbn_value,
        "confidence": round(confidence / 100.0, 3),
        "confidence_percent": confidence,
        "decision": decision,
        "evidence_summary": summary[:8],
        "warnings": list(dict.fromkeys(warnings))[:8],
        "conflicts": conflicts[:8],
        "evidence_count": len(all_evidence),
        "field_confidence": {
            "title": round(title_conf, 1),
            "author": round(author_conf, 1),
            "isbn": round(isbn_conf, 1),
            "year": round(year_conf, 1),
        },
    }


def scan_identity_from_data(path: Path, datos: dict, candidates=None) -> dict:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        page_texts = [datos.get("titulo_texto", ""), datos.get("autor_texto", "")]
        ocr_texts = [datos.get("ocr_texto", "")] if datos.get("ocr_texto") else []
        evidences = build_pdf_identity_evidence(path, datos, page_texts=page_texts, ocr_texts=ocr_texts)
        pdf_type = classify_pdf_from_signals(page_texts, ocr_texts=ocr_texts)
    elif suffix in KINDLE_FORMATS:
        evidences = build_kindle_identity_evidence(path, datos)
        pdf_type = ""
    else:
        evidences = evidence_from_existing_data(datos or {}, filename=Path(path).name)
        pdf_type = ""
    external = candidates_to_evidence(candidates or [])
    result = score_identity(evidences, external)
    result["format"] = suffix.lstrip(".") or "unknown"
    if pdf_type:
        result["pdf_type"] = pdf_type
    result["evidence"] = [asdict(ev) for ev in evidences[:20]]
    return result
