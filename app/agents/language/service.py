from collections.abc import Callable, Mapping

from app.agents.language.contracts import (
    LanguageAssistantInput,
    LanguageAssistantOutput,
)
from app.agents.language.graph import LanguageAssistantGraph
from app.agents.language.projection import project_language_input


class LanguageAssistantService:
    def __init__(self, graph: LanguageAssistantGraph) -> None:
        self._graph = graph

    def invoke(self, request: LanguageAssistantInput) -> LanguageAssistantOutput:
        """Invoke graph with validated Pydantic input and return output."""
        return self._graph.invoke(request)


def build_language_assistant_node(
    service: LanguageAssistantService,
) -> Callable[[Mapping[str, object]], dict[str, object]]:
    """Build a node function adapting parent graph state dict to LanguageAssistantService."""

    def language_assistant_node(parent_state: Mapping[str, object]) -> dict[str, object]:
        child_input = project_language_input(parent_state)
        output = service.invoke(child_input)
        return {"language_assistant": output.model_dump(mode="json")}

    return language_assistant_node


__all__ = [
    "LanguageAssistantService",
    "build_language_assistant_node",
]
