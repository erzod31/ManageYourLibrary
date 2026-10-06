import json
import re
from pathlib import PureWindowsPath


SYSTEM_PROMPT = (
    "You are a strict bibliographic metadata judge for a local ebook library manager. "
    "Choose only from the provided bibliographic candidates or return needs_review. "
    "Do not invent metadata. Do not use external knowledge as a source of truth. "
    "Prefer exact ISBN or DOI matches. Prefer strong title and author matches. "
    "Prefer language consistency. Normalize only spelling, accents, punctuation and obvious "
    "author-name order when supported by the selected candidate. Detect possible series, "
    "volume, duplicate-equivalence and problematic edition flags only when evidence is present. "
    "If uncertain, return needs_review. Return only valid JSON matching the required schema."
)

MAX_SIGNAL_CHARS = 140
MAX_SHORT_TEXT_CHARS = 220
MAX_CANDIDATES = 6


def _safe_basename(path_or_name) -> str:
    # Parse both slash styles lexically, independent of the host OS. A Windows
    # path imported on POSIX must not become a filename containing private dirs.
    name = PureWindowsPath(str(path_or_name or "")).name
    return re.sub(r"\s+", " ", name).strip()[:MAX_SIGNAL_CHARS]


def _short(value, limit=MAX_SIGNAL_CHARS) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _short_list(values, limit_items=4):
    out = []
    for value in values or []:
        text = _short(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit_items:
            break
    return out


def _minimal_candidate(candidate, candidate_id):
    return {
        "candidate_id": candidate_id,
        "source": _short(candidate.get("fuente", "")),
        "title": _short(candidate.get("titulo", "")),
        "author": _short(candidate.get("autor", "")),
        "year": _short(candidate.get("anio", ""), 12),
        "isbn": _short(candidate.get("isbn", ""), 32),
        "doi": _short(candidate.get("doi", "") or candidate.get("identificador", ""), 80) if candidate.get("metodo") == "DOI" else "",
        "method": _short(candidate.get("metodo", "")),
        "score": candidate.get("score", ""),
        "language": _short(candidate.get("language", "") or candidate.get("idioma", ""), 24),
        "source_scope": _short(candidate.get("source_scope", ""), 40),
    }


def candidates_with_ids(candidates, max_candidates=MAX_CANDIDATES):
    out = []
    for index, candidate in enumerate((candidates or [])[:max_candidates]):
        candidate_id = chr(ord("A") + index)
        entry = _minimal_candidate(candidate, candidate_id)
        entry["_original"] = candidate
        out.append(entry)
    return out


def public_candidates(candidates_with_private):
    return [{k: v for k, v in c.items() if k != "_original"} for c in candidates_with_private]


def build_minimal_metadata_payload(file_path_or_name, datos, candidates, local_confidence=0):
    datos = datos or {}
    safe_candidates = candidates_with_ids(candidates)
    payload = {
        "file": {
            "base_name": _safe_basename(file_path_or_name),
            "extension": PureWindowsPath(str(file_path_or_name or "")).suffix.lower()[:12],
            "approx_size": datos.get("tamano_aproximado", "") or datos.get("size_bucket", ""),
        },
        "local_signals": {
            "title": _short(datos.get("titulo_local") or datos.get("titulo_texto") or datos.get("titulo_nombre")),
            "author": _short(datos.get("autor_local") or datos.get("autor_texto") or datos.get("autor_nombre") or datos.get("autor_ambiguo")),
            "year": _short(datos.get("anio_local") or datos.get("anio_texto"), 12),
            "isbns": _short_list(datos.get("isbns", []), limit_items=3),
            "dois": _short_list(datos.get("dois", []), limit_items=2),
            "language": _short(datos.get("idioma") or datos.get("idioma_probable"), 24),
            "short_evidence": _short_list(datos.get("senales_cortas", []) or datos.get("motivos_revision", []), limit_items=4),
            "local_confidence": local_confidence,
        },
        "candidates": public_candidates(safe_candidates),
        "allowed_problem_flags": [
            "anthology",
            "incomplete_book",
            "free_sample",
            "preview",
            "problematic_scan",
            "contradictory_metadata",
            "multiple_authors",
            "translation",
            "commented_edition",
            "series_volume",
            "language_conflict",
            "duplicate_equivalence_suggested",
            "bad_filename",
        ],
        "required_schema": {
            "decision": "choose_candidate | needs_review",
            "candidate_id": "string|null",
            "confidence": "0..1",
            "normalized_author": "string|null",
            "normalized_title": "string|null",
            "detected_series": "string|null",
            "detected_volume": "string|null",
            "language": "string|null",
            "suggested_filename": "string|null",
            "problem_flags": "array[string]",
            "review_reasons": "array[string]",
            "reason_codes": "array[string]",
            "needs_human_review": "boolean",
        },
    }
    return payload, safe_candidates


def build_prompt(file_path_or_name, datos, candidates, local_confidence=0):
    payload, safe_candidates = build_minimal_metadata_payload(file_path_or_name, datos, candidates, local_confidence)
    user_prompt = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(user_prompt) > 8000:
        payload["local_signals"]["short_evidence"] = []
        payload["candidates"] = payload["candidates"][:4]
        user_prompt = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return {
        "system": SYSTEM_PROMPT,
        "user": user_prompt[:9000],
        "payload": payload,
        "candidates": safe_candidates,
    }


def prompt_contains_private_path(prompt_text: str) -> bool:
    return bool(re.search(r"[A-Za-z]:\\|\\\\[^\\]+\\|/Users/|/home/", str(prompt_text or "")))
