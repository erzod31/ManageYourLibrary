from ai_decision_cache import GLOBAL_AI_DECISION_CACHE
from ai_metadata_schema import validate_ai_metadata_response
from ai_prompt_builder import build_prompt
from ai_runtime_manager import LlamaCppServer, llama_completion


class FakeAIJudge:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = 0

    def judge(self, prompt):
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return {
            "decision": "needs_review",
            "candidate_id": None,
            "confidence": 0.0,
            "normalized_author": None,
            "normalized_title": None,
            "detected_series": None,
            "detected_volume": None,
            "language": None,
            "suggested_filename": None,
            "problem_flags": [],
            "review_reasons": ["La IA local no tuvo confianza suficiente"],
            "reason_codes": ["ai_low_confidence"],
            "needs_human_review": True,
        }


class LlamaCppAIJudge:
    def __init__(self, config=None, runtime=None):
        self.config = config or {}
        self.runtime = runtime or LlamaCppServer(self.config)

    def judge(self, prompt):
        ok, state = self.runtime.start()
        if not ok:
            raise RuntimeError(state)
        return llama_completion(self.runtime.endpoint, prompt["system"], prompt["user"])


def request_ai_judgement(
    file_path_or_name,
    datos,
    candidates,
    *,
    local_confidence=0,
    model_id="",
    judge=None,
    cache=GLOBAL_AI_DECISION_CACHE,
):
    prompt = build_prompt(file_path_or_name, datos, candidates, local_confidence=local_confidence)
    model_key = model_id or "qwen3-1.7b-q4"
    cached = cache.get(model_key, prompt["payload"]) if cache else None
    if cached is not None:
        return cached

    judge = judge or LlamaCppAIJudge({"model_id": model_key, "enabled": True})
    last_errors = ()
    for _attempt in range(2):
        raw = judge.judge(prompt)
        validation = validate_ai_metadata_response(raw, prompt["candidates"])
        if validation.ok:
            result = {
                "ok": True,
                "decision": validation.data,
                "prompt": prompt,
                "errors": (),
            }
            if cache:
                cache.set(model_key, prompt["payload"], result)
            return result
        last_errors = validation.errors

    result = {
        "ok": False,
        "decision": {
            "decision": "needs_review",
            "candidate_id": None,
            "confidence": 0.0,
            "normalized_author": None,
            "normalized_title": None,
            "detected_series": None,
            "detected_volume": None,
            "language": None,
            "suggested_filename": None,
            "problem_flags": ["contradictory_metadata"] if "candidate_id_not_found" in last_errors else [],
            "review_reasons": ["La IA local devolvió una respuesta no válida"],
            "reason_codes": ["ai_invalid_response"],
            "needs_human_review": True,
        },
        "prompt": prompt,
        "errors": last_errors,
    }
    if cache:
        cache.set(model_key, prompt["payload"], result)
    return result
