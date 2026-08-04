from datetime import date

import pytest

from app.agents.language.contracts import (
    LanguageAssistantInput,
    LanguageAssistantOutput,
    LanguageExecutionPolicy,
    RequestContext,
)
from app.agents.language.generation.models import (
    EasyKoreanDraft,
    SemanticValidationDraft,
    TranslationDraft,
)
from app.agents.language.graph import (
    build_language_assistant_graph,
)
from app.agents.language.ports import SemanticValidationDecision, TraceSink
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.models import (
    EpsReference,
    RerankerSelectedContext,
    RetrievalResult,
)
from app.agents.language.service import (
    LanguageAssistantService,
    build_language_assistant_node,
)


@pytest.fixture
def sample_context() -> RequestContext:
    return RequestContext(
        request_reason="체류기간 연장 신청 (2026-08-15까지)",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        deadline=date(2026, 8, 15),
        submission_method=(
            "출입국 관서 2층 방문 제출 (전화: 02-123-4567, email: test@example.com)"
        ),
    )


@pytest.fixture
def sample_input(sample_context: RequestContext) -> LanguageAssistantInput:
    return LanguageAssistantInput(
        worker_id="worker-123",
        preferred_language="en",
        nationality_code="VN",
        request_context=sample_context,
    )


def make_sample_eps_ref(point_id: str = "p1") -> EpsReference:
    return EpsReference(
        point_id=point_id,
        source_record_id=f"rec-{point_id}",
        korean_text="체류기간 연장",
        translated_text="Extension of stay period",
        target_language="en",
        eps_language_code="01",
        source_page=1,
        dataset_revision="a" * 40,
        content_hash="b" * 40,
        quality_status="canonical",
        source="EPS",
        source_url="https://eps.go.kr",
    )


class FakeRetriever:
    def retrieve(
        self,
        *,
        queries: list[SearchQuery],
        standard_korean_text: str,
        target_language: str,
    ) -> RetrievalResult:
        return RetrievalResult(
            dataset_version="v1.0",
            query_strategies=tuple(q.kind for q in queries),
            contexts=(
                RerankerSelectedContext(
                    reference=make_sample_eps_ref("p1"),
                    fusion_score=0.9,
                    reranker_score=0.95,
                    selection_rank=0,
                    selected_by="reranker",
                ),
            ),
            warnings=(),
            fallback_used=False,
            degraded_components=(),
        )


class FakeGenerator:
    def __init__(self, raise_translation_error: bool = False) -> None:
        self.raise_translation_error = raise_translation_error

    def generate(
        self, *, operation: str, payload: dict[str, object], response_model: type
    ) -> object:
        if operation == "translation" and self.raise_translation_error:
            raise RuntimeError("Translation provider failed")
        if response_model == EasyKoreanDraft:
            return EasyKoreanDraft(
                request_reason="체류기간 늘림 신청",
                requested_items=("여권 복사본 1부", "일터 약속 서류 복사본 1부"),
                submission_method=(
                    "출입국 관서 2층 가져오기 내기 (전화: 02-123-4567, email: test@example.com)"
                ),
            )
        if response_model == TranslationDraft:
            return TranslationDraft(
                translated_reason="Extension of stay period",
                translated_items=("Passport copy 1 copy", "Employment contract copy 1 copy"),
                translated_submission_method=(
                    "2nd floor immigration office visit "
                    "(phone: 02-123-4567, email: test@example.com)"
                ),
            )
        return SemanticValidationDraft(status="passed")


class FakeValidator:
    def validate(self, **kwargs: object) -> SemanticValidationDecision:
        return SemanticValidationDecision(status="passed")


class FakeTraceSink(TraceSink):
    def emit(self, event_name: str, payload: dict[str, object]) -> None:
        pass


def test_language_assistant_graph_happy_path(sample_input: LanguageAssistantInput) -> None:
    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=True,
    )
    output = graph.invoke(sample_input)
    assert isinstance(output, LanguageAssistantOutput)
    assert output.worker_id == "worker-123"
    assert output.target_language == "en"
    assert output.generation_status == "success"
    assert output.requires_human_review is False
    assert "체류기간 연장" in output.standard_korean_text
    assert "체류기간 늘림" in output.easy_korean_text
    assert "Extension of stay" in output.translated_text


def test_translation_failure_preserves_easy_and_standard(
    sample_input: LanguageAssistantInput,
) -> None:
    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=FakeGenerator(raise_translation_error=True),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=True,
    )
    output = graph.invoke(sample_input)
    assert isinstance(output, LanguageAssistantOutput)
    assert output.translated_text is None
    assert output.generation_status == "failed"
    assert output.requires_human_review is True
    assert output.standard_korean_text != ""
    assert output.easy_korean_text != ""


def test_parallel_execution_without_inter_branch_dependency(
    sample_input: LanguageAssistantInput,
) -> None:
    easy_entered = False
    translation_entered = False

    class ParallelTestGenerator:
        def generate(
            self, *, operation: str, payload: dict[str, object], response_model: type
        ) -> object:
            nonlocal easy_entered, translation_entered
            if operation == "easy_korean":
                easy_entered = True
            elif operation == "translation":
                translation_entered = True
            return FakeGenerator().generate(
                operation=operation, payload=payload, response_model=response_model
            )

    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=ParallelTestGenerator(),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=True,
    )
    output = graph.invoke(sample_input)
    assert output.generation_status == "success"
    assert easy_entered is True
    assert translation_entered is True


def test_language_assistant_service_node_integration(
    sample_input: LanguageAssistantInput,
) -> None:
    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=True,
    )
    service = LanguageAssistantService(graph)
    node_fn = build_language_assistant_node(service)

    parent_state = {
        "worker_id": "worker-123",
        "preferred_language": "en",
        "nationality_code": "VN",
        "request_context": sample_input.request_context.model_dump(mode="json"),
        "extra_db_field": "should_be_ignored",
    }

    result = node_fn(parent_state)
    assert "language_assistant" in result
    assert result["language_assistant"]["worker_id"] == "worker-123"
    assert result["language_assistant"]["target_language"] == "en"


def test_easy_failure_preserves_translation(
    sample_input: LanguageAssistantInput,
) -> None:
    # Unapproved context pack forces Easy Korean fallback without breaking translation
    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=False,
    )
    output = graph.invoke(sample_input)
    assert output.generation_status == "warning"
    assert output.easy_korean_text == output.standard_korean_text
    assert output.translated_text is not None
    assert "Extension of stay" in output.translated_text


def test_both_fail_preserve_standard_korean(
    sample_input: LanguageAssistantInput,
) -> None:
    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=FakeGenerator(raise_translation_error=True),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=False,
    )
    output = graph.invoke(sample_input)
    assert output.generation_status == "failed"
    assert output.translated_text is None
    assert output.standard_korean_text != ""
    assert output.easy_korean_text == output.standard_korean_text


def test_expected_provider_errors_do_not_raise_graph_exception(
    sample_input: LanguageAssistantInput,
) -> None:
    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=FakeGenerator(raise_translation_error=True),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=True,
    )
    # Should complete returning failed output instead of raising unhandled exception
    output = graph.invoke(sample_input)
    assert output.generation_status == "failed"


def test_target_language_change_keeps_standard_easy_protected_facts_equal(
    sample_context: RequestContext,
) -> None:
    input_en = LanguageAssistantInput(
        worker_id="w-1",
        preferred_language="en",
        request_context=sample_context,
    )
    input_vi = LanguageAssistantInput(
        worker_id="w-1",
        preferred_language="vi",
        request_context=sample_context,
    )

    graph = build_language_assistant_graph(
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
        semantic_validator=FakeValidator(),
        trace_sink=FakeTraceSink(),
        execution_policy=LanguageExecutionPolicy(),
        allow_draft_context_pack=True,
    )

    out_en = graph.invoke(input_en)
    out_vi = graph.invoke(input_vi)

    assert out_en.standard_korean_text == out_vi.standard_korean_text
    assert out_en.easy_korean_text == out_vi.easy_korean_text
