import hashlib
import json


class AIDecisionCache:
    def __init__(self, max_entries=256):
        self.max_entries = max_entries
        self._cache = {}

    def key_for(self, model_id, payload):
        sanitized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(f"{model_id}\0{sanitized}".encode("utf-8", errors="ignore")).hexdigest()

    def get(self, model_id, payload):
        return self._cache.get(self.key_for(model_id, payload))

    def set(self, model_id, payload, value):
        if len(self._cache) >= self.max_entries:
            for key in list(self._cache.keys())[: max(1, self.max_entries // 10)]:
                self._cache.pop(key, None)
        self._cache[self.key_for(model_id, payload)] = value

    def clear(self):
        self._cache.clear()


GLOBAL_AI_DECISION_CACHE = AIDecisionCache()
