import json
import re
import unicodedata
from dataclasses import dataclass


AI_DECISIONS = {"choose_candidate", "needs_review"}
AI_SCHEMA_KEYS = {
    "decision",
    "candidate_id",
    "confidence",
    "normalized_author",
    "normalized_title",
    "detected_series",
    "detected_volume",
    "language",
    "suggested_filename",
    "problem_flags",
    "review_reasons",
    "reason_codes",
    "needs_human_review",
}
ALLOWED_PROBLEM_FLAGS = {
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
}
MAX_REVIEW_REASON_CHARS = 180


@dataclass(frozen=True)
class AIValidationResult:
    ok: bool
    data: dict
    errors: tuple[str, ...] = ()


def _parse_json(value):
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        raise ValueError("AI response is not JSON text")
    return json.loads(value)


def _is_optional_string(value):
    return value is None or isinstance(value, str)


def _candidate_by_id(candidates):
    return {str(c.get("candidate_id", "")): c for c in candidates or [] if c.get("candidate_id")}


def _normalize_supported_text(value):
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _contains_unconfirmed_value(value, allowed_values):
    if not value:
        return False
    value_norm = _normalize_supported_text(value)
    allowed_norms = [_normalize_supported_text(allowed) for allowed in allowed_values if allowed]
    if not allowed_norms:
        return True
    return all(value_norm != allowed_norm for allowed_norm in allowed_norms)


def validate_ai_metadata_response(response, candidates):
    errors = []
    try:
        data = _parse_json(response)
    except Exception as exc:
        return AIValidationResult(False, {}, (f"invalid_json: {exc}",))

    extra = set(data) - AI_SCHEMA_KEYS
    missing = AI_SCHEMA_KEYS - set(data)
    if extra:
        errors.append("unexpected_keys")
    if missing:
        errors.append("missing_keys")

    decision = data.get("decision")
    if decision not in AI_DECISIONS:
        errors.append("invalid_decision")

    candidate_map = _candidate_by_id(candidates)
    candidate_id = data.get("candidate_id")
    chosen = candidate_map.get(str(candidate_id or ""))
    if decision == "choose_candidate" and not chosen:
        errors.append("candidate_id_not_found")
    if decision == "needs_review" and candidate_id not in ("", None):
        errors.append("candidate_id_must_be_null_for_review")

    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append("invalid_confidence")

    for key in ("normalized_author", "normalized_title", "detected_series", "detected_volume", "language", "suggested_filename"):
        if not _is_optional_string(data.get(key)):
            errors.append(f"invalid_{key}")

    for key in ("problem_flags", "review_reasons", "reason_codes"):
        if not isinstance(data.get(key), list) or not all(isinstance(item, str) for item in data.get(key, [])):
            errors.append(f"invalid_{key}")

    if not isinstance(data.get("needs_human_review"), bool):
        errors.append("invalid_needs_human_review")

    unknown_flags = set(data.get("problem_flags") or []) - ALLOWED_PROBLEM_FLAGS
    if unknown_flags:
        errors.append("invalid_problem_flags")

    if any(len(reason) > MAX_REVIEW_REASON_CHARS for reason in data.get("review_reasons") or []):
        errors.append("review_reason_too_long")

    if chosen:
        allowed_authors = [chosen.get("autor", ""), chosen.get("author", "")]
        allowed_titles = [chosen.get("titulo", ""), chosen.get("title", "")]
        if _contains_unconfirmed_value(data.get("normalized_author"), allowed_authors):
            errors.append("normalized_author_not_supported")
        if _contains_unconfirmed_value(data.get("normalized_title"), allowed_titles):
            errors.append("normalized_title_not_supported")
        suggested = data.get("suggested_filename") or ""
        if suggested:
            allowed_text = _normalize_supported_text(
                " ".join(str(v or "") for v in allowed_authors + allowed_titles + [chosen.get("anio", ""), chosen.get("isbn", "")])
            )
            for token in str(suggested).replace(".", " ").replace("-", " ").split():
                clean = _normalize_supported_text(token.strip("()[]_ "))
                if len(clean) >= 5 and clean not in allowed_text:
                    errors.append("suggested_filename_contains_unconfirmed_data")
                    break

    if decision == "needs_review" and data.get("confidence", 0) > 0.85:
        errors.append("needs_review_confidence_too_high")

    return AIValidationResult(not errors, data if not errors else {}, tuple(dict.fromkeys(errors)))
