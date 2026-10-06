from dataclasses import dataclass


@dataclass(frozen=True)
class AIModelOption:
    model_id: str
    label: str
    relative_model_path: str
    recommended: bool = False


MODEL_QWEN3_1_7B_Q4 = "qwen3-1.7b-q4"
MODEL_QWEN3_4B_Q4 = "qwen3-4b-q4"


MODEL_OPTIONS = (
    AIModelOption(
        model_id=MODEL_QWEN3_1_7B_Q4,
        label="Qwen3 1.7B Q4 — aprox. 1,4 GB — recomendado",
        relative_model_path="models/qwen3-1.7b-q4/model.gguf",
        recommended=True,
    ),
    AIModelOption(
        model_id=MODEL_QWEN3_4B_Q4,
        label="Qwen3 4B Q4 — aprox. 2,5 GB — más preciso",
        relative_model_path="models/qwen3-4b-q4/model.gguf",
        recommended=False,
    ),
)


def get_model_options():
    return MODEL_OPTIONS


def default_model_id():
    for model in MODEL_OPTIONS:
        if model.recommended:
            return model.model_id
    return MODEL_OPTIONS[0].model_id


def get_model_option(model_id):
    for model in MODEL_OPTIONS:
        if model.model_id == model_id:
            return model
    return None


def is_allowed_model(model_id):
    return get_model_option(model_id) is not None
