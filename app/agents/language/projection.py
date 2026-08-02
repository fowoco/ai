from collections.abc import Mapping

from .contracts import LanguageAssistantInput

LANGUAGE_INPUT_KEYS = (
    "worker_id",
    "preferred_language",
    "nationality_code",
    "request_context",
)


def project_language_input(
    parent_state: Mapping[str, object],
) -> LanguageAssistantInput:
    projected = {key: parent_state.get(key) for key in LANGUAGE_INPUT_KEYS}
    return LanguageAssistantInput.model_validate(projected)
