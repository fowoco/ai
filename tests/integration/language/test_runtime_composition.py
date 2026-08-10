import pytest

from app.agents.language.contracts import LanguageExecutionPolicy
from app.agents.language.generation.models import EasyKoreanDraft
from app.agents.language.generation.ollama import OllamaGenerationPort
from app.agents.language.ports import NoopTraceSink, SemanticValidationDecision
from app.agents.language.retrieval.models import RetrievalResult
from app.agents.language.service import LanguageAssistantService
from app.core.config import Settings
from tests.agents.language.fakes import (
    FakeEpsRetriever,
    FakeSemanticValidationPort,
    FakeStructuredGenerationPort,
)


def _composition_types():
    try:
        from app.agents.language.composition import (
            LanguageAssistantCompositionOverrides,
            LanguageAssistantCompositionUnavailable,
            build_language_assistant_service,
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"composition module missing: {exc}")
    return (
        LanguageAssistantCompositionOverrides,
        LanguageAssistantCompositionUnavailable,
        build_language_assistant_service,
    )


def _test_overrides():
    overrides_type, _, _ = _composition_types()
    return overrides_type(
        generator=FakeStructuredGenerationPort(
            result=EasyKoreanDraft(
                request_reason="신청",
                requested_items=("체류기간",),
                submission_method="방문",
            )
        ),
        retriever=FakeEpsRetriever(
            result=RetrievalResult(
                dataset_version=None,
                query_strategies=(),
                contexts=(),
                warnings=(),
                fallback_used=True,
                degraded_components=("retrieval",),
            )
        ),
        semantic_validator=FakeSemanticValidationPort(
            result=SemanticValidationDecision(status="passed")
        ),
        trace_sink=NoopTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
    )


def test_factory_builds_service_from_explicit_test_ports() -> None:
    _, _, build_service = _composition_types()

    service = build_service(Settings(), overrides=_test_overrides())

    assert isinstance(service, LanguageAssistantService)


def test_factory_builds_service_from_valid_generation_settings() -> None:
    _, _, build_service = _composition_types()

    service = build_service(
        Settings(
            llm_provider="openai-compatible",
            llm_base_url="http://example.test/v1",
            llm_model="test-model",
        )
    )

    assert isinstance(service, LanguageAssistantService)


def test_factory_selects_native_adapter_for_ollama_provider() -> None:
    from app.agents.language.composition import _build_production_ports

    generator, _, _, _, _ = _build_production_ports(
        Settings(
            llm_provider="ollama",
            llm_base_url="http://localhost:11434/v1",
            llm_model="gemma4:26b-mlx",
        )
    )

    assert isinstance(generator, OllamaGenerationPort)


def test_factory_rejects_missing_generation_settings() -> None:
    _, unavailable, build_service = _composition_types()

    with pytest.raises(unavailable):
        build_service(Settings())


@pytest.mark.parametrize(
    "settings",
    (
        Settings(
            llm_provider="unsupported",
            llm_base_url="http://example.test/v1",
            llm_model="test-model",
        ),
        Settings(
            llm_provider="openai-compatible",
            llm_base_url="not-a-url",
            llm_model="test-model",
        ),
        Settings(
            llm_provider="openai-compatible",
            llm_base_url="http://example.test/v1",
            llm_model="",
        ),
    ),
)
def test_factory_rejects_invalid_generation_settings(settings: Settings) -> None:
    _, unavailable, build_service = _composition_types()

    with pytest.raises(unavailable):
        build_service(settings)
