from datetime import date

import pytest
from pydantic import BaseModel

from app.agents.language.contracts import (
    LanguageExecutionPolicy,
    RequestContext,
    WarningCode,
    WarningItem,
)
from app.agents.language.generation.models import SemanticValidationDraft, TranslationDraft
from app.agents.language.ports import SemanticValidationDecision
from app.agents.language.protected_facts import ProtectedFacts
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.models import (
    EpsReference,
    FusionSelectedContext,
    RerankerSelectedContext,
    RetrievalResult,
)
from app.agents.language.translation import (
    TranslationBranchInput,
    TranslationResult,
    build_translation_queries,
    build_translation_subgraph,
    render_translation_text,
)


@pytest.fixture
def sample_context() -> RequestContext:
    return RequestContext(
        request_reason="체류기간 연장 신청 (2026-08-15까지)",
        requested_items=("여권 사본 1부", "근로계약서 사본 1부"),
        deadline=date(2026, 8, 15),
        submission_method="출입국 관서 2층 방문 제출 (전화: 02-123-4567, email: test@example.com)",
    )


@pytest.fixture
def sample_protected_facts(sample_context: RequestContext) -> ProtectedFacts:
    return ProtectedFacts.from_request_context(sample_context)


@pytest.fixture
def sample_input(
    sample_context: RequestContext, sample_protected_facts: ProtectedFacts
) -> TranslationBranchInput:
    return {
        "request_context": sample_context,
        "target_language": "en",
        "protected_facts": sample_protected_facts,
        "standard_korean_text": (
            "체류기간 연장 신청서 제출 안내\n"
            "- 여권 사본 1부\n"
            "- 근로계약서 사본 1부\n"
            "기한: 2026-08-15\n"
            "제출방법: 출입국 관서 2층 방문 제출"
        ),
    }


def make_sample_eps_ref(
    point_id: str = "p1",
    korean: str = "체류기간 연장",
    translated: str = "Extension of stay period",
) -> EpsReference:
    return EpsReference(
        point_id=point_id,
        source_record_id=f"rec-{point_id}",
        korean_text=korean,
        translated_text=translated,
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
    def __init__(self, result: RetrievalResult | None = None) -> None:
        self.captured_calls: list[dict[str, object]] = []
        self.result = result
        self.call_count = 0

    def retrieve(
        self,
        *,
        queries: list[SearchQuery],
        standard_korean_text: str,
        target_language: str,
    ) -> RetrievalResult:
        self.call_count += 1
        self.captured_calls.append({
            "queries": queries,
            "standard_korean_text": standard_korean_text,
            "target_language": target_language,
        })
        if self.result is not None:
            return self.result
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
    def __init__(
        self,
        draft: BaseModel | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.captured_payloads: list[dict[str, object]] = []
        self.draft = draft
        self.raise_error = raise_error
        self.call_count = 0

    def generate(
        self, *, operation: str, payload: dict[str, object], response_model: type
    ) -> object:
        self.call_count += 1
        self.captured_payloads.append({"operation": operation, **payload})
        if self.raise_error:
            raise self.raise_error
        if self.draft is not None:
            return self.draft
        if response_model == SemanticValidationDraft:
            return SemanticValidationDraft(status="passed")
        return TranslationDraft(
            translated_reason="Extension of stay period",
            translated_items=("Passport copy 1 copy", "Employment contract copy 1 copy"),
            translated_submission_method=(
                "2nd floor immigration office visit (02-123-4567, test@example.com)"
            ),
        )


class FakeValidator:
    def __init__(self, decision: SemanticValidationDecision | None = None) -> None:
        self.decision = decision or SemanticValidationDecision(status="passed")
        self.call_count = 0

    def validate(self, **kwargs: object) -> SemanticValidationDecision:
        self.call_count += 1
        return self.decision


def test_translation_builds_three_queries_before_retrieval(
    sample_context: RequestContext,
) -> None:
    queries = build_translation_queries(sample_context, "표준 한국어 텍스트")
    assert len(queries) == 3
    kinds = [q.kind for q in queries]
    assert "canonical" in kinds
    assert "reason_items" in kinds
    assert "action_deadline" in kinds


def test_translation_retrieval_always_filters_target_language(
    sample_input: TranslationBranchInput,
) -> None:
    ret = FakeRetriever()
    gen = FakeGenerator()
    val = FakeValidator()
    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
    )
    subgraph.invoke(sample_input)
    assert ret.call_count == 1
    assert ret.captured_calls[0]["target_language"] == "en"


def test_translation_prompt_contains_only_top_five_eps_contexts(
    sample_input: TranslationBranchInput,
) -> None:
    gen = FakeGenerator()
    val = FakeValidator()

    # Create 7 contexts
    contexts = tuple(
        FusionSelectedContext(
            reference=make_sample_eps_ref(f"p{i}", f"텍스트 {i}", f"Text {i}"),
            fusion_score=0.9 - (i * 0.01),
            reranker_score=None,
            selection_rank=i,
            selected_by="cross_query_rrf",
        )
        for i in range(7)
    )
    ret_res = RetrievalResult(
        dataset_version="v1.0",
        query_strategies=("canonical", "reason_items", "action_deadline"),
        contexts=contexts,
        warnings=(),
        fallback_used=False,
        degraded_components=(),
    )
    ret = FakeRetriever(result=ret_res)

    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
    )
    res = subgraph.invoke(sample_input)["translation_result"]
    assert isinstance(res, TranslationResult)
    assert len(gen.captured_payloads[0]["eps_references"]) <= 5


def test_translation_prompt_labels_eps_as_untrusted_reference(
    sample_input: TranslationBranchInput,
) -> None:
    ret = FakeRetriever()
    gen = FakeGenerator()
    val = FakeValidator()
    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
    )
    subgraph.invoke(sample_input)
    eps_refs = gen.captured_payloads[0]["eps_references"]
    assert any("Untrusted" in str(ref) or "reference" in str(ref) for ref in eps_refs)


def test_translation_prompt_excludes_parent_context(
    sample_input: TranslationBranchInput,
) -> None:
    ret = FakeRetriever()
    gen = FakeGenerator()
    val = FakeValidator()
    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
    )
    subgraph.invoke(sample_input)
    payload = gen.captured_payloads[0]
    assert "worker_id" not in payload
    assert "nationality" not in payload
    assert "parent_context" not in payload


def test_translation_renderer_preserves_item_order_and_iso_deadline(
    sample_context: RequestContext,
) -> None:
    draft = TranslationDraft(
        translated_reason="Extension of stay period",
        translated_items=("Passport copy", "Employment contract copy"),
        translated_submission_method="Visit local office",
    )
    text = render_translation_text(draft, sample_context, "en")
    assert "2026-08-15" in text
    assert "- Passport copy" in text
    assert "- Employment contract copy" in text


def test_no_match_uses_general_llm_and_sets_fallback(
    sample_input: TranslationBranchInput,
) -> None:
    no_match_result = RetrievalResult(
        dataset_version="v1.0",
        query_strategies=("canonical", "reason_items", "action_deadline"),
        contexts=(),
        warnings=(),
        fallback_used=True,
        degraded_components=(),
    )
    ret = FakeRetriever(result=no_match_result)
    gen = FakeGenerator()
    val = FakeValidator()

    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
    )
    res = subgraph.invoke(sample_input)["translation_result"]
    assert gen.call_count >= 1
    assert res.retrieval.fallback_used is True
    assert any(w.code == WarningCode.TRANSLATION_FALLBACK_USED for w in res.warnings)


def test_qdrant_failure_uses_general_llm_and_sets_unavailable_warning(
    sample_input: TranslationBranchInput,
) -> None:
    failed_result = RetrievalResult(
        dataset_version=None,
        query_strategies=("canonical", "reason_items", "action_deadline"),
        contexts=(),
        warnings=(),
        fallback_used=True,
        degraded_components=("retrieval_store",),
    )
    ret = FakeRetriever(result=failed_result)
    gen = FakeGenerator()
    val = FakeValidator()

    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
    )
    res = subgraph.invoke(sample_input)["translation_result"]
    assert gen.call_count >= 1
    assert res.retrieval.fallback_used is True


def test_translation_retry_does_not_repeat_queries_or_retrieval(
    sample_input: TranslationBranchInput,
) -> None:
    ret = FakeRetriever()
    gen = FakeGenerator()
    val = FakeValidator(
        decision=SemanticValidationDecision(
            status="failed",
            failed_checks=("request_reason.semantic_equivalence",),
        )
    )
    policy = LanguageExecutionPolicy(max_correction_retries=1)

    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
        policy=policy,
    )
    subgraph.invoke(sample_input)
    assert ret.call_count == 1  # Retrieval invoked exactly once
    assert gen.call_count == 2  # Generator invoked twice (initial + 1 retry)


def test_translation_no_candidate_returns_null_and_failed(
    sample_input: TranslationBranchInput,
) -> None:
    ret = FakeRetriever()
    gen = FakeGenerator(raise_error=RuntimeError("LLM API error"))
    val = FakeValidator()

    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
    )
    res = subgraph.invoke(sample_input)["translation_result"]
    assert res.text is None
    assert res.status == "failed"
    assert res.validation.status == "not_run"


def test_query_too_long_uses_general_llm_without_truncation(
    sample_input: TranslationBranchInput,
) -> None:
    ret_res = RetrievalResult(
        dataset_version="v1.0",
        query_strategies=("canonical", "reason_items", "action_deadline"),
        contexts=(),
        warnings=(
            WarningItem(
                component="retrieval",
                code=WarningCode.RETRIEVAL_QUERY_TOO_LONG,
                message="Query too long",
            ),
        ),
        fallback_used=True,
        degraded_components=("encoder",),
    )
    ret = FakeRetriever(result=ret_res)
    gen = FakeGenerator()
    val = FakeValidator()

    subgraph = build_translation_subgraph(retriever=ret, generator=gen, validator=val)
    res = subgraph.invoke(sample_input)["translation_result"]
    assert gen.call_count >= 1
    assert res.retrieval.fallback_used is True
    assert any(w.code == WarningCode.RETRIEVAL_QUERY_TOO_LONG for w in res.warnings)


def test_dataset_mismatch_uses_general_llm_and_sets_mismatch_warning(
    sample_input: TranslationBranchInput,
) -> None:
    ret_res = RetrievalResult(
        dataset_version=None,
        query_strategies=("canonical", "reason_items", "action_deadline"),
        contexts=(),
        warnings=(
            WarningItem(
                component="retrieval",
                code=WarningCode.RETRIEVAL_DATASET_MISMATCH,
                message="Dataset mismatch",
            ),
        ),
        fallback_used=True,
        degraded_components=("retrieval_store",),
    )
    ret = FakeRetriever(result=ret_res)
    gen = FakeGenerator()
    val = FakeValidator()

    subgraph = build_translation_subgraph(retriever=ret, generator=gen, validator=val)
    res = subgraph.invoke(sample_input)["translation_result"]
    assert any(w.code == WarningCode.RETRIEVAL_DATASET_MISMATCH for w in res.warnings)


def test_reranker_failure_uses_fused_context_and_sets_warning(
    sample_input: TranslationBranchInput,
) -> None:
    ret_res = RetrievalResult(
        dataset_version="v1.0",
        query_strategies=("canonical", "reason_items", "action_deadline"),
        contexts=(
            FusionSelectedContext(
                reference=make_sample_eps_ref("p1"),
                fusion_score=0.8,
                reranker_score=None,
                selection_rank=0,
                selected_by="cross_query_rrf",
            ),
        ),
        warnings=(
            WarningItem(
                component="retrieval",
                code=WarningCode.RERANKER_UNAVAILABLE,
                message="Reranker failed",
            ),
        ),
        fallback_used=False,
        degraded_components=("reranker",),
    )
    ret = FakeRetriever(result=ret_res)
    gen = FakeGenerator()
    val = FakeValidator()

    subgraph = build_translation_subgraph(retriever=ret, generator=gen, validator=val)
    res = subgraph.invoke(sample_input)["translation_result"]
    assert res.text is not None
    assert any(w.code == WarningCode.RERANKER_UNAVAILABLE for w in res.warnings)


def test_translation_retry_exhaustion_returns_last_candidate(
    sample_input: TranslationBranchInput,
) -> None:
    ret = FakeRetriever()
    gen = FakeGenerator()
    val = FakeValidator(
        decision=SemanticValidationDecision(
            status="failed",
            failed_checks=("request_reason.semantic_equivalence",),
        )
    )
    policy = LanguageExecutionPolicy(max_correction_retries=2)

    subgraph = build_translation_subgraph(
        retriever=ret,
        generator=gen,
        validator=val,
        policy=policy,
    )
    res = subgraph.invoke(sample_input)["translation_result"]
    assert res.text is not None
    assert res.status == "warning"
    assert res.validation.status == "failed"
    assert any(w.code == WarningCode.VALIDATION_RETRY_EXCEEDED for w in res.warnings)
