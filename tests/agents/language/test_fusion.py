import math
import threading
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.agents.language.contracts import RequestContext
from app.agents.language.ports import (
    NoopTraceSink,
    SemanticValidationDecision,
    TraceEvent,
)
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.fusion import fuse_query_rankings
from app.agents.language.retrieval.models import (
    EpsReference,
    ExpectedIndexContract,
    FusionSelectedContext,
    HybridVector,
    PerQueryRanking,
    RankedCandidate,
    RerankerSelectedContext,
    RetrievalResult,
    SelectedContext,
    VerifiedCollectionHandle,
)
from tests.agents.language.fakes import (
    FakeCandidateReranker,
    FakeDenseSparseEncoder,
    FakeEpsRetriever,
    FakeHybridSearchStore,
    FakePortError,
    FakeSchemaMismatchError,
    FakeSemanticValidationPort,
    FakeStructuredGenerationPort,
    FakeTraceSink,
)


def make_reference(point_id: str) -> EpsReference:
    return EpsReference(
        point_id=point_id,
        source_record_id=f"record-{point_id}",
        korean_text=f"한국어 {point_id}",
        translated_text=f"translated {point_id}",
        target_language="vi",
        eps_language_code="03",
        source_page=1,
        dataset_revision="sha256:dataset",
        content_hash=f"sha256:{point_id}",
        quality_status="raw",
        source="EPS",
        source_url="https://eps.hrdkorea.or.kr/e9/user/language/language.do",
    )


def ranked(point_id: str, rank: int) -> RankedCandidate:
    return RankedCandidate(reference=make_reference(point_id), rank=rank, score=1.0)


def ranking(kind: str, *point_ids: str) -> PerQueryRanking:
    return PerQueryRanking(
        query_kind=kind,
        candidates=tuple(ranked(point_id, rank) for rank, point_id in enumerate(point_ids)),
    )


def vector() -> HybridVector:
    return HybridVector(
        dense=(0.0,) * 1024,
        sparse_indices=(1, 3),
        sparse_values=(0.25, 0.75),
    )


def expected_contract() -> ExpectedIndexContract:
    return ExpectedIndexContract(
        dataset_revision="sha256:dataset",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="a" * 40,
        index_contract_version="eps-language-index-v1",
    )


def verified_handle(collection_name: str = "eps-language-verified") -> VerifiedCollectionHandle:
    contract = expected_contract()
    return VerifiedCollectionHandle(
        collection_name=collection_name,
        dataset_version=contract.dataset_revision,
        embedding_model_repo=contract.embedding_model_repo,
        embedding_model_revision=contract.embedding_model_revision,
        index_contract_version=contract.index_contract_version,
        point_count=1,
    )


def test_hybrid_vector_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValidationError):
        HybridVector(dense=(0.0,) * 1023, sparse_indices=(), sparse_values=())


@pytest.mark.parametrize("indices", [(2, 1), (1, 1), (-1, 2)])
def test_sparse_indices_are_sorted_unique_and_non_negative(indices: tuple[int, ...]) -> None:
    with pytest.raises(ValidationError):
        HybridVector(
            dense=(0.0,) * 1024,
            sparse_indices=indices,
            sparse_values=(0.5,) * len(indices),
        )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_sparse_values_are_finite(value: float) -> None:
    with pytest.raises(ValidationError):
        HybridVector(dense=(0.0,) * 1024, sparse_indices=(1,), sparse_values=(value,))


def test_rrf_deduplicates_by_point_id() -> None:
    result = fuse_query_rankings(
        (
            ranking("canonical", "p1", "p2"),
            ranking("reason_items", "p1", "p3"),
            ranking("action_deadline", "p2"),
        )
    )

    assert [candidate.reference.point_id for candidate in result].count("p1") == 1
    p1 = next(candidate for candidate in result if candidate.reference.point_id == "p1")
    assert p1.contributing_queries == ("canonical", "reason_items")
    assert p1.fusion_score == pytest.approx(2 / 60)


def test_rrf_uses_all_query_rankings() -> None:
    result = fuse_query_rankings(
        (
            ranking("canonical", "p1"),
            ranking("reason_items", "p2"),
            ranking("action_deadline", "p3"),
        )
    )

    assert {candidate.reference.point_id for candidate in result} == {"p1", "p2", "p3"}


def test_rrf_stable_tie_break() -> None:
    result = fuse_query_rankings(
        (
            ranking("canonical", "point-b"),
            ranking("reason_items", "point-a"),
            ranking("action_deadline"),
        )
    )

    assert [candidate.reference.point_id for candidate in result] == ["point-a", "point-b"]


def test_empty_rankings_return_empty_candidates() -> None:
    assert fuse_query_rankings(()) == ()
    assert fuse_query_rankings(
        (ranking("canonical"), ranking("reason_items"), ranking("action_deadline"))
    ) == ()


def test_fusion_preserves_reference_payload_without_vectors() -> None:
    result = fuse_query_rankings((ranking("canonical", "p1"),))

    dumped = result[0].model_dump()
    assert result[0].reference == make_reference("p1")
    assert "dense" not in dumped
    assert "sparse_indices" not in dumped
    assert "sparse_values" not in dumped


def selected_context_payload(*, selected_by: str, reranker_score: Any) -> dict[str, Any]:
    return {
        "reference": make_reference("p1").model_dump(),
        "fusion_score": 0.25,
        "reranker_score": reranker_score,
        "selection_rank": 0,
        "selected_by": selected_by,
    }


def test_selected_context_accepts_only_reranker_with_score() -> None:
    value = TypeAdapter(SelectedContext).validate_python(
        selected_context_payload(selected_by="reranker", reranker_score=0.9)
    )

    assert isinstance(value, RerankerSelectedContext)
    assert value.model_dump()["selected_by"] == "reranker"


def test_selected_context_accepts_only_fusion_fallback_without_score() -> None:
    value = TypeAdapter(SelectedContext).validate_python(
        selected_context_payload(selected_by="cross_query_rrf", reranker_score=None)
    )

    assert isinstance(value, FusionSelectedContext)
    assert value.model_dump()["reranker_score"] is None


def test_selected_context_rejects_reranker_without_score() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SelectedContext).validate_python(
            selected_context_payload(
                selected_by="reranker",
                reranker_score=None,
            )
        )


def test_selected_context_rejects_fusion_fallback_with_score() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SelectedContext).validate_python(
            selected_context_payload(
                selected_by="cross_query_rrf",
                reranker_score=0.9,
            )
        )


def test_retrieval_result_serializes_verified_or_missing_dataset_version() -> None:
    result = RetrievalResult(
        dataset_version=None,
        query_strategies=("canonical", "reason_items", "action_deadline"),
        contexts=(),
        warnings=(),
        fallback_used=True,
        degraded_components=("retrieval",),
    )

    assert result.model_dump()["dataset_version"] is None


def test_semantic_validation_unavailable_is_inconclusive() -> None:
    with pytest.raises(ValidationError):
        SemanticValidationDecision(status="passed", unavailable=True)

    value = SemanticValidationDecision(
        status="inconclusive",
        unavailable=True,
        inconclusive_checks=("facts.no_semantic_addition",),
    )
    assert value.unavailable is True


def test_noop_trace_sink_is_safe_default() -> None:
    event = TraceEvent(
        run_id="run-1",
        node_name="retrieval",
        status="succeeded",
        latency_ms=1.0,
        retry_count=0,
    )

    assert NoopTraceSink().emit(event) is None


class Draft(BaseModel):
    text: str


def test_deterministic_fakes_capture_calls_and_scripted_failures() -> None:
    encoded = vector()
    encoder = FakeDenseSparseEncoder(
        scripted_results=[(encoded,), FakePortError("encoder unavailable")]
    )

    assert encoder.encode_queries(["first"]) == (encoded,)
    with pytest.raises(FakePortError, match="encoder unavailable"):
        encoder.encode_queries(["second"])
    assert encoder.calls == [("first",), ("second",)]

    reranker = FakeCandidateReranker(reranked=())
    candidates = fuse_query_rankings((ranking("canonical", "p1"),))
    assert reranker.rerank("query", candidates) == ()
    assert reranker.calls[-1]["query"] == "query"
    assert reranker.calls[-1]["candidates"] == candidates

    generation = FakeStructuredGenerationPort(result=Draft(text="draft"))
    assert generation.generate(operation="translation", payload={}, response_model=Draft) == Draft(
        text="draft"
    )
    assert generation.calls[-1]["operation"] == "translation"


def test_deterministic_fakes_support_event_and_barrier_hooks() -> None:
    entered = threading.Event()
    encoder = FakeDenseSparseEncoder(
        result=(vector(),),
        entered=entered,
        barrier=threading.Barrier(1),
    )

    encoder.encode_queries(["query"])

    assert entered.is_set()


def test_store_fake_distinguishes_verified_mismatched_and_schema_invalid_outcomes() -> None:
    contract = expected_contract()
    handle = verified_handle()
    store = FakeHybridSearchStore(
        rankings=(),
        verified_handle=handle,
        contract_outcome="verified",
    )

    assert store.verify_contract(expected=contract) == handle
    store.switch_alias("eps-language-new")
    store.search_many(
        ((SearchQuery(kind="canonical", text="query"), vector()),),
        target_language="vi",
        collection=handle,
    )
    assert store.search_calls[-1]["collection"].collection_name == "eps-language-verified"
    assert store.alias_target == "eps-language-new"

    mismatched = FakeHybridSearchStore(contract_outcome="mismatched")
    with pytest.raises(FakePortError):
        mismatched.verify_contract(expected=contract)

    schema_invalid = FakeHybridSearchStore(contract_outcome="schema-invalid")
    with pytest.raises(FakeSchemaMismatchError):
        schema_invalid.verify_contract(expected=contract)


def test_remaining_port_fakes_capture_typed_results() -> None:
    context = RequestContext(
        request_reason="연장",
        requested_items=("여권",),
        deadline="2026-08-10",
        submission_method="이메일",
    )
    decision = SemanticValidationDecision(status="passed")
    validation = FakeSemanticValidationPort(result=decision)
    assert (
        validation.validate(
            component="translation",
            request_context=context,
            target_language="vi",
            candidate="번역",
        )
        == decision
    )

    retrieval_result = RetrievalResult(
        dataset_version=None,
        query_strategies=(),
        contexts=(),
        warnings=(),
        fallback_used=True,
        degraded_components=("retrieval",),
    )
    retriever = FakeEpsRetriever(result=retrieval_result)
    query = SearchQuery(kind="canonical", text="검색")
    assert (
        retriever.retrieve(
            queries=(query,),
            standard_korean_text="표준",
            target_language="vi",
        )
        == retrieval_result
    )

    trace = FakeTraceSink()
    event = TraceEvent(
        run_id="run-1",
        node_name="retrieval",
        status="degraded",
        latency_ms=2.0,
        retry_count=1,
    )
    trace.emit(event)
    assert trace.events == [event]
