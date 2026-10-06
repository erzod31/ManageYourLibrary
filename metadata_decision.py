AI_ACCEPT_WITHOUT_CALL = 92.0
AI_REVIEW_BELOW = 75.0


def confidence_to_percent(value) -> float:
    try:
        numeric = float(value or 0)
    except Exception:
        return 0.0
    if numeric <= 1:
        return numeric * 100
    return numeric


def should_call_ai_for_confidence(local_confidence) -> bool:
    confidence = confidence_to_percent(local_confidence)
    return AI_REVIEW_BELOW <= confidence < AI_ACCEPT_WITHOUT_CALL


def _candidate_map(prompt_candidates):
    return {
        str(candidate.get("candidate_id", "")): candidate
        for candidate in prompt_candidates or []
        if candidate.get("candidate_id")
    }


def _top_candidate_id(prompt_candidates):
    return str((prompt_candidates or [{}])[0].get("candidate_id", ""))


def _contradicts_exact_identifier(chosen, datos):
    chosen = chosen or {}
    datos = datos or {}
    chosen_isbn = chosen.get("isbn", "") or chosen.get("_original", {}).get("isbn", "")
    local_isbns = set(datos.get("isbns", []) or [])
    if chosen_isbn and local_isbns and chosen_isbn not in local_isbns:
        return True
    return False


def evaluate_ai_decision(ai_result, datos):
    if not ai_result or not ai_result.get("ok"):
        return {
            "action": "needs_review",
            "reason": "La IA local no devolvió una respuesta válida",
            "errors": tuple(ai_result.get("errors", ())) if ai_result else (),
        }

    decision = ai_result["decision"]
    prompt_candidates = ai_result.get("prompt", {}).get("candidates", [])
    candidates_by_id = _candidate_map(prompt_candidates)
    if decision.get("decision") == "needs_review" or decision.get("needs_human_review"):
        return {
            "action": "needs_review",
            "reason": "; ".join(decision.get("review_reasons") or ["La IA local pidió revisión humana"]),
            "ai_decision": decision,
        }

    chosen_id = str(decision.get("candidate_id") or "")
    chosen = candidates_by_id.get(chosen_id)
    if not chosen:
        return {"action": "needs_review", "reason": "La IA eligió un candidato inexistente", "ai_decision": decision}

    if chosen_id != _top_candidate_id(prompt_candidates):
        return {"action": "needs_review", "reason": "La IA no coincidió con el candidato mejor puntuado", "ai_decision": decision}

    if _contradicts_exact_identifier(chosen, datos):
        return {"action": "needs_review", "reason": "La IA contradijo un ISBN/DOI exacto", "ai_decision": decision}

    if confidence_to_percent(decision.get("confidence", 0)) < AI_REVIEW_BELOW:
        return {"action": "needs_review", "reason": "La IA local no tuvo confianza suficiente", "ai_decision": decision}

    return {
        "action": "choose_candidate",
        "candidate": chosen.get("_original", chosen),
        "candidate_id": chosen_id,
        "ai_decision": decision,
        "ai_confidence": confidence_to_percent(decision.get("confidence", 0)),
    }


def merge_ai_review_reason(resultado, evaluation):
    out = dict(resultado or {})
    reason = evaluation.get("reason", "La IA local pidió revisión humana")
    out["encontrado"] = False
    out["accion_recomendada"] = "dejar_igual"
    out["metodo"] = "ia_local_revision"
    out["motivo"] = f"{out.get('motivo', '')}; IA local: {reason}"
    out.setdefault("motivos_revision", [])
    if "ia_local_revision" not in out["motivos_revision"]:
        out["motivos_revision"].append("ia_local_revision")
    out.setdefault("advertencias", [])
    if reason and reason not in out["advertencias"]:
        out["advertencias"].append(reason)
    return out
