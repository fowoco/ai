"""Lazy runtime composition for the Language Assistant."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.agents.language.contracts import (
    LanguageExecutionPolicy,
    SupportedLanguage,
    WarningCode,
    WarningItem,
)
from app.agents.language.generation.models import StructuredGenerator
from app.agents.language.generation.ollama import OllamaGenerationPort
from app.agents.language.generation.openai_compatible import (
    OpenAICompatibleGenerationPort,
)
from app.agents.language.graph import build_language_assistant_graph
from app.agents.language.ports import (
    EpsRetriever,
    NoopTraceSink,
    SemanticValidationPort,
    TraceSink,
)
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.models import RetrievalResult
from app.agents.language.service import LanguageAssistantService
from app.agents.language.validation import GeneratedSemanticValidator
from app.core.config import Settings

_SUPPORTED_LLM_PROVIDERS = frozenset({"openai-compatible", "ollama"})


@dataclass(frozen=True)
class LanguageAssistantCompositionOverrides:
    """Complete port set for deterministic tests or alternate runtimes."""

    generator: StructuredGenerator
    retriever: EpsRetriever
    semantic_validator: SemanticValidationPort
    trace_sink: TraceSink
    execution_policy: LanguageExecutionPolicy


class LanguageAssistantCompositionUnavailable(RuntimeError):
    code = "LANGUAGE_ASSISTANT_COMPOSITION_UNAVAILABLE"


class _UnavailableRetriever(EpsRetriever):
    """Keep generation usable while optional EPS retrieval is unavailable."""

    def __init__(self, message: str) -> None:
        self._message = message

    def retrieve(
        self,
        *,
        queries: Sequence[SearchQuery],
        standard_korean_text: str,
        target_language: SupportedLanguage,
    ) -> RetrievalResult:
        del standard_korean_text, target_language
        return RetrievalResult(
            dataset_version=None,
            query_strategies=tuple(query.kind for query in queries),
            contexts=(),
            warnings=(
                WarningItem(
                    component="retrieval",
                    code=WarningCode.RETRIEVAL_UNAVAILABLE,
                    message=self._message,
                ),
            ),
            fallback_used=True,
            degraded_components=("retrieval",),
        )


def _required_generation_settings(settings: Settings) -> tuple[str, str, str]:
    provider = (settings.llm_provider or "").strip().lower()
    base_url = (settings.llm_base_url or "").strip()
    model = (settings.llm_model or "").strip()

    if provider not in _SUPPORTED_LLM_PROVIDERS:
        raise LanguageAssistantCompositionUnavailable("unsupported LLM provider")
    if not base_url:
        raise LanguageAssistantCompositionUnavailable("LLM base URL is not configured")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LanguageAssistantCompositionUnavailable("invalid LLM base URL")
    if not model:
        raise LanguageAssistantCompositionUnavailable("LLM model is not configured")
    return provider, base_url, model


def _build_production_ports(
    settings: Settings,
) -> tuple[
    StructuredGenerator,
    EpsRetriever,
    SemanticValidationPort,
    TraceSink,
    LanguageExecutionPolicy,
]:
    provider, base_url, model = _required_generation_settings(settings)
    generator_type = (
        OllamaGenerationPort if provider == "ollama" else OpenAICompatibleGenerationPort
    )
    generator = generator_type(
        base_url=base_url,
        api_key=settings.llm_api_key,
        model=model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    retrieval_message = (
        "Qdrant is not configured"
        if not settings.qdrant_url
        else "Qdrant/BGE retrieval adapter is unavailable"
    )
    retriever = _UnavailableRetriever(retrieval_message)
    return (
        generator,
        retriever,
        GeneratedSemanticValidator(generator),
        NoopTraceSink(),
        LanguageExecutionPolicy(),
    )


def build_language_assistant_service(
    settings: Settings,
    *,
    overrides: LanguageAssistantCompositionOverrides | None = None,
) -> LanguageAssistantService:
    """Build service without network or model work during module import."""
    if overrides is None:
        ports = _build_production_ports(settings)
    else:
        ports = (
            overrides.generator,
            overrides.retriever,
            overrides.semantic_validator,
            overrides.trace_sink,
            overrides.execution_policy,
        )

    generator, retriever, validator, trace_sink, policy = ports
    graph = build_language_assistant_graph(
        retriever=retriever,
        generator=generator,
        semantic_validator=validator,
        trace_sink=trace_sink,
        execution_policy=policy,
    )
    return LanguageAssistantService(graph)


__all__ = [
    "LanguageAssistantCompositionOverrides",
    "LanguageAssistantCompositionUnavailable",
    "build_language_assistant_service",
]
