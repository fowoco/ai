from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeCandidateReranker, FakeCandidateRetriever, scored
from pydantic import ValidationError

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.mapper import HybridFieldMapper, MappingThresholds
from app.documents.dynamic_automation.models import (
    DocumentFieldContext,
    FieldMapping,
    MappingEvidence,
    MappingStatus,
    ScoredCandidate,
)

CATALOG_PATH = (
    Path(__file__).parents[3]
    / "app"
    / "documents"
    / "dynamic_automation"
    / "resources"
    / "canonical_fields.v1.yaml"
)


@pytest.fixture
def catalog() -> CanonicalCatalog:
    return CanonicalCatalog.load(CATALOG_PATH)


def make_context(
    *,
    field_id: str = "field-1",
    label: str = "연락처",
    field_type: str = "phone",
    section: str = "현재 근무처",
    row_labels: tuple[str, ...] = ("현재 근무처", "연락처"),
    repeat_index: int = 0,
    kind: str = "text_field",
) -> DocumentFieldContext:
    return DocumentFieldContext(
        field_id=field_id,
        label=label,
        normalized_label=label,
        field_type=field_type,
        document_title="통합신청서",
        section=section,
        row_labels=row_labels,
        nearby_labels=(),
        options=(),
        repeat_index=repeat_index,
        required=True,
        kind=kind,
    )


def make_mapper(
    catalog: CanonicalCatalog,
    *,
    retrieved: tuple[ScoredCandidate, ...] | None = (),
    reranked: tuple[ScoredCandidate, ...] | None = (),
    retriever_error: Exception | None = None,
    reranker_error: Exception | None = None,
    min_score: float = 0.90,
    min_margin: float = 0.10,
) -> HybridFieldMapper:
    return HybridFieldMapper(
        catalog=catalog,
        retriever=FakeCandidateRetriever(results=retrieved, error=retriever_error),
        reranker=FakeCandidateReranker(results=reranked, error=reranker_error),
        thresholds=MappingThresholds(
            min_reranker_score=min_score,
            min_margin=min_margin,
        ),
        top_k=5,
    )


def test_field_mapping_records_repeat_index() -> None:
    mapping = FieldMapping(
        field_id="worker-name-1",
        repeat_index=1,
        status=MappingStatus.UNMAPPED,
        evidence=MappingEvidence(reason="no_match", catalog_version="v1"),
    )

    assert mapping.repeat_index == 1


def test_field_mapping_rejects_negative_repeat_index() -> None:
    with pytest.raises(ValidationError):
        FieldMapping(
            field_id="worker-name-1",
            repeat_index=-1,
            status=MappingStatus.UNMAPPED,
            evidence=MappingEvidence(reason="no_match", catalog_version="v1"),
        )


def test_mapper_requires_absolute_score_and_margin(catalog: CanonicalCatalog) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("company.phone", 0.94), ("worker.phone", 0.92)),
        reranked=scored(("company.phone", 0.91), ("worker.phone", 0.88)),
        min_score=0.90,
        min_margin=0.10,
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "insufficient_margin"
    assert result.evidence.score_margin == pytest.approx(0.03)


def test_mapper_rejects_top_candidate_below_absolute_threshold(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("company.phone", 0.95), ("worker.phone", 0.80)),
        reranked=scored(("company.phone", 0.89), ("worker.phone", 0.60)),
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "insufficient_score"


def test_mapper_requires_a_runner_up_for_margin_evidence(catalog: CanonicalCatalog) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("company.phone", 0.98)),
        reranked=scored(("company.phone", 0.96)),
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "insufficient_margin_evidence"
    assert result.evidence.score_margin is None


def test_reranker_failure_does_not_accept_embedding_top_one(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("company.phone", 0.99), ("worker.phone", 0.70)),
        reranker_error=RuntimeError("offline"),
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "reranker_unavailable"
    assert result.candidates[0].canonical_field_id == "company.phone"


def test_none_reranker_result_is_ambiguous(catalog: CanonicalCatalog) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("company.phone", 0.95), ("worker.phone", 0.80)),
        reranked=None,
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "invalid_reranker_evidence"
    assert result.candidates == ()


def test_retriever_failure_reduces_coverage_without_lowering_thresholds(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(catalog, retriever_error=RuntimeError("offline"))

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "retriever_unavailable"


def test_none_retriever_result_is_ambiguous(catalog: CanonicalCatalog) -> None:
    mapper = make_mapper(catalog, retrieved=None)

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "invalid_retrieval_evidence"
    assert result.candidates == ()


def test_unique_exact_alias_is_safe_without_model_services(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(
        catalog,
        retriever_error=RuntimeError("offline"),
        reranker_error=RuntimeError("offline"),
    )

    result = mapper.map(
        (make_context(label="사업장 전화번호", row_labels=("사업장", "전화번호")),)
    ).mappings[0]

    assert result.status is MappingStatus.MATCHED
    assert result.canonical_field_id == "company.phone"
    assert result.evidence.rule == "exact_alias"
    assert result.evidence.type_compatible is True
    assert result.evidence.catalog_version == "v1"


def test_exact_alias_requires_a_compatible_structural_entity_hint(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(
        catalog,
        retriever_error=RuntimeError("offline"),
        reranker_error=RuntimeError("offline"),
    )

    result = mapper.map(
        (make_context(label="사업장 전화번호", section="", row_labels=()),)
    ).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "retriever_unavailable"
    assert result.evidence.entity_hint is None


def test_mapper_records_complete_semantic_decision_evidence(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("company.phone", 0.95), ("worker.phone", 0.82)),
        reranked=scored(("company.phone", 0.96), ("worker.phone", 0.61)),
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.MATCHED
    assert result.canonical_field_id == "company.phone"
    assert result.repeat_index == 0
    assert result.evidence.rule == "semantic_decision_gate"
    assert result.evidence.embedding_rank == 1
    assert result.evidence.reranker_score == 0.96
    assert result.evidence.score_margin == pytest.approx(0.35)
    assert result.evidence.type_compatible is True
    assert result.evidence.entity_hint == "company"
    assert result.evidence.catalog_version == "v1"
    assert result.evidence.model_version == "fake-reranker-v1"


def test_mapper_rejects_candidates_outside_the_compatible_allowlist(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("worker.date_of_birth", 0.99), ("company.phone", 0.95)),
        reranked=scored(("worker.date_of_birth", 0.99), ("company.phone", 0.95)),
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "invalid_retrieval_evidence"
    assert result.evidence.type_compatible is False


def test_retriever_result_exceeding_top_k_is_ambiguous(catalog: CanonicalCatalog) -> None:
    retrieved = scored(("company.phone", 0.95), ("worker.phone", 0.80))
    mapper = HybridFieldMapper(
        catalog=catalog,
        retriever=FakeCandidateRetriever(results=retrieved, enforce_top_k=False),
        reranker=FakeCandidateReranker(results=retrieved),
        thresholds=MappingThresholds(min_reranker_score=0.90, min_margin=0.10),
        top_k=1,
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "invalid_retrieval_evidence"


def test_malformed_ranking_preserves_truthful_type_compatibility(
    catalog: CanonicalCatalog,
) -> None:
    mapper = make_mapper(
        catalog,
        retrieved=scored(("company.phone", 0.95), ("company.phone", 0.80)),
    )

    result = mapper.map((make_context(),)).mappings[0]

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.evidence.reason == "invalid_retrieval_evidence"
    assert result.evidence.type_compatible is True


def test_non_data_fields_bypass_models(catalog: CanonicalCatalog) -> None:
    mapper = make_mapper(
        catalog,
        retriever_error=AssertionError("retriever must not run"),
        reranker_error=AssertionError("reranker must not run"),
    )

    result = mapper.map((make_context(label="확인검토", field_type="text"),)).mappings[0]

    assert result.status is MappingStatus.NON_DATA
    assert result.evidence.reason == "process_flow_label"


def test_no_compatible_candidates_is_unmapped(catalog: CanonicalCatalog) -> None:
    mapper = make_mapper(catalog)

    result = mapper.map((make_context(field_type="unsupported"),)).mappings[0]

    assert result.status is MappingStatus.UNMAPPED
    assert result.evidence.reason == "no_compatible_candidates"
