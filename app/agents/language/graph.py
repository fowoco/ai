from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.language.contracts import (
    LanguageAssistantInput,
    LanguageAssistantOutput,
    LanguageExecutionPolicy,
)
from app.agents.language.generation.models import StructuredGenerator
from app.agents.language.nodes import build_language_nodes
from app.agents.language.ports import EpsRetriever, SemanticValidationPort, TraceSink
from app.agents.language.state import LanguageAssistantState


class LanguageAssistantGraph:
    def __init__(self, compiled: CompiledStateGraph) -> None:
        self._compiled = compiled

    def invoke(self, request: LanguageAssistantInput) -> LanguageAssistantOutput:
        """Validate Pydantic input before entry and Pydantic output after exit."""
        validated_input = LanguageAssistantInput.model_validate(request)
        initial_state: LanguageAssistantState = {"input": validated_input}
        result = self._compiled.invoke(initial_state)
        return LanguageAssistantOutput.model_validate(result["output"])


def build_private_compiled_graph(
    *,
    retriever: EpsRetriever,
    generator: StructuredGenerator,
    semantic_validator: SemanticValidationPort,
    trace_sink: TraceSink,
    execution_policy: LanguageExecutionPolicy,
    allow_draft_context_pack: bool = False,
) -> CompiledStateGraph:
    """Build and compile the parent parallel LangGraph."""
    node_set = build_language_nodes(
        retriever=retriever,
        generator=generator,
        semantic_validator=semantic_validator,
        trace_sink=trace_sink,
        execution_policy=execution_policy,
        allow_draft_context_pack=allow_draft_context_pack,
    )
    builder = StateGraph(LanguageAssistantState)
    builder.add_node("validate_and_normalize", node_set.validate_and_normalize)
    builder.add_node("resolve_target_language", node_set.resolve_target_language)
    builder.add_node("build_protected_facts", node_set.build_protected_facts)
    builder.add_node("compose_standard_korean", node_set.compose_standard_korean)
    builder.add_node("easy_korean", node_set.run_easy_branch)
    builder.add_node("native_translation", node_set.run_translation_branch)
    builder.add_node("assemble_output", node_set.assemble_output)

    builder.add_edge(START, "validate_and_normalize")
    builder.add_edge("validate_and_normalize", "resolve_target_language")
    builder.add_edge("resolve_target_language", "build_protected_facts")
    builder.add_edge("build_protected_facts", "compose_standard_korean")
    builder.add_edge("compose_standard_korean", "easy_korean")
    builder.add_edge("compose_standard_korean", "native_translation")
    builder.add_edge(["easy_korean", "native_translation"], "assemble_output")
    builder.add_edge("assemble_output", END)

    return builder.compile()


def build_language_assistant_graph(
    *,
    retriever: EpsRetriever,
    generator: StructuredGenerator,
    semantic_validator: SemanticValidationPort,
    trace_sink: TraceSink,
    execution_policy: LanguageExecutionPolicy,
    allow_draft_context_pack: bool = False,
) -> LanguageAssistantGraph:
    """Build facade graph encapsulating compiled LangGraph."""
    compiled = build_private_compiled_graph(
        retriever=retriever,
        generator=generator,
        semantic_validator=semantic_validator,
        trace_sink=trace_sink,
        execution_policy=execution_policy,
        allow_draft_context_pack=allow_draft_context_pack,
    )
    return LanguageAssistantGraph(compiled)


__all__ = [
    "LanguageAssistantGraph",
    "build_language_assistant_graph",
    "build_private_compiled_graph",
]
