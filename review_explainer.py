DEFAULT_REASON_LABELS = {
    "sin_identificador_fuerte": "No se encontró ISBN/DOI fiable",
    "sin_candidatos_externos": "No se encontraron candidatos bibliográficos externos",
    "candidatos_externos_incompletos": "Los candidatos externos estaban incompletos",
    "conflicto_autor_local_web": "El autor local contradice la fuente externa",
    "conflicto_titulo_local_web": "El título local contradice la fuente externa",
    "titulo_compacto_no_confirmado": "El título compactado no pudo confirmarse",
    "autor_no_fiable": "El autor detectado es incompleto o poco fiable",
    "ia_local_revision": "La IA local pidió revisión humana",
}


def explain_review_reasons(reason_codes=None, ai_review_reasons=None, max_items=5):
    out = []
    for code in reason_codes or []:
        label = DEFAULT_REASON_LABELS.get(code, str(code or "").replace("_", " ").strip())
        if label and label not in out:
            out.append(label[:180])
        if len(out) >= max_items:
            return out
    for reason in ai_review_reasons or []:
        text = " ".join(str(reason or "").replace("\r", " ").replace("\n", " ").split())
        if text and text not in out:
            out.append(text[:180])
        if len(out) >= max_items:
            break
    return out
