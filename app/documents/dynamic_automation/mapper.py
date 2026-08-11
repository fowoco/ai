"""Fail-closed hybrid canonical field mapping orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from .catalog import CanonicalCatalog
from .field_context import normalize_text
from .global_validation import validate_global_mapping
from .models import (
    CanonicalFieldDefinition,
    CanonicalMappingPlan,
    DocumentFieldContext,
    FieldMapping,
    MappingEvidence,
    MappingStatus,
    ScoredCandidate,
)
from .ports import CandidateReranker, CandidateRetriever
from .rules import classify_non_data, exact_alias_matches

_RULE_MODEL_VERSION = "deterministic-rules-v1"
_ENTITY_TERMS = {
    "worker": ("근로자", "신청인", "worker", "employee", "applicant"),
    "company": ("회사", "사업장", "근무처", "고용주", "company", "employer", "workplace"),
    "identity": ("신원", "여권", "외국인등록", "identity", "passport"),
    "contract": ("계약", "근로조건", "contract"),
    "application": ("신청일", "application date"),
}


class MappingThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_reranker_score: float = Field(ge=0, le=1)
    min_margin: float = Field(ge=0, le=1)
    exact_alias_requires_unique_entity: bool = True


@dataclass(frozen=True)
class HybridFieldMapper:
    catalog: CanonicalCatalog
    retriever: CandidateRetriever
    reranker: CandidateReranker
    thresholds: MappingThresholds
    top_k: int = 10

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be positive")

    def map(self, contexts: Sequence[DocumentFieldContext]) -> CanonicalMappingPlan:
        mappings = tuple(self._map_one(context) for context in contexts)
        return validate_global_mapping(
            CanonicalMappingPlan(catalog_version=self.catalog.version, mappings=mappings),
            self.catalog,
        )

    def _map_one(self, context: DocumentFieldContext) -> FieldMapping:
        entity_hint = _entity_hint(context)
        non_data = classify_non_data(context)
        if non_data.is_non_data:
            return self._mapping(
                context,
                status=MappingStatus.NON_DATA,
                reason=non_data.reason or "non_data",
                rule="non_data_rule",
                entity_hint=entity_hint,
                model_version=_RULE_MODEL_VERSION,
            )

        compatible = self.catalog.compatible(context)
        if not compatible:
            return self._mapping(
                context,
                status=MappingStatus.UNMAPPED,
                reason="no_compatible_candidates",
                rule="candidate_filter",
                type_compatible=False,
                entity_hint=entity_hint,
                model_version=_RULE_MODEL_VERSION,
            )

        exact = exact_alias_matches(context, self.catalog)
        if _is_unique_exact_match(
            exact,
            entity_hint=entity_hint,
            require_unique_entity=self.thresholds.exact_alias_requires_unique_entity,
        ):
            definition = exact[0]
            candidate = ScoredCandidate(
                canonical_field_id=definition.field_id,
                score=1.0,
                rank=1,
            )
            return self._mapping(
                context,
                status=MappingStatus.MATCHED,
                canonical_field_id=definition.field_id,
                candidates=(candidate,),
                reason="exact_alias",
                rule="exact_alias",
                type_compatible=True,
                entity_hint=entity_hint or definition.entity,
                model_version=_RULE_MODEL_VERSION,
            )

        try:
            retrieved = self.retriever.retrieve(context, compatible, self.top_k)
        except Exception:
            return self._mapping(
                context,
                status=MappingStatus.AMBIGUOUS,
                reason="retriever_unavailable",
                rule="semantic_decision_gate",
                type_compatible=True,
                entity_hint=entity_hint,
                model_version=self.retriever.model_version,
            )

        if not isinstance(retrieved, tuple):
            return self._mapping(
                context,
                status=MappingStatus.AMBIGUOUS,
                reason="invalid_retrieval_evidence",
                rule="semantic_decision_gate",
                entity_hint=entity_hint,
                model_version=self.retriever.model_version,
            )

        allowed_ids = {candidate.field_id for candidate in compatible}
        if len(retrieved) > self.top_k or not _valid_ranking(
            retrieved, allowed_ids=allowed_ids, require_all_ids=False
        ):
            return self._mapping(
                context,
                status=MappingStatus.AMBIGUOUS,
                candidates=retrieved,
                reason="invalid_retrieval_evidence",
                rule="semantic_decision_gate",
                type_compatible=all(
                    candidate.canonical_field_id in allowed_ids for candidate in retrieved
                ),
                entity_hint=entity_hint,
                model_version=self.retriever.model_version,
            )
        if not retrieved:
            return self._mapping(
                context,
                status=MappingStatus.UNMAPPED,
                reason="no_retrieval_candidates",
                rule="semantic_decision_gate",
                type_compatible=True,
                entity_hint=entity_hint,
                model_version=self.retriever.model_version,
            )

        try:
            reranked = self.reranker.rerank(context, retrieved)
        except Exception:
            return self._mapping(
                context,
                status=MappingStatus.AMBIGUOUS,
                candidates=retrieved,
                reason="reranker_unavailable",
                rule="semantic_decision_gate",
                embedding_rank=retrieved[0].rank,
                type_compatible=True,
                entity_hint=entity_hint,
                model_version=self.reranker.model_version,
            )

        if not isinstance(reranked, tuple):
            return self._mapping(
                context,
                status=MappingStatus.AMBIGUOUS,
                reason="invalid_reranker_evidence",
                rule="semantic_decision_gate",
                entity_hint=entity_hint,
                model_version=self.reranker.model_version,
            )

        retrieved_ids = {candidate.canonical_field_id for candidate in retrieved}
        if not _valid_ranking(reranked, allowed_ids=retrieved_ids, require_all_ids=True):
            return self._mapping(
                context,
                status=MappingStatus.AMBIGUOUS,
                candidates=reranked,
                reason="invalid_reranker_evidence",
                rule="semantic_decision_gate",
                type_compatible=all(
                    candidate.canonical_field_id in retrieved_ids for candidate in reranked
                ),
                entity_hint=entity_hint,
                model_version=self.reranker.model_version,
            )

        top = reranked[0]
        embedding_rank = next(
            candidate.rank
            for candidate in retrieved
            if candidate.canonical_field_id == top.canonical_field_id
        )
        if len(reranked) < 2:
            return self._mapping(
                context,
                status=MappingStatus.AMBIGUOUS,
                candidates=reranked,
                reason="insufficient_margin_evidence",
                rule="semantic_decision_gate",
                embedding_rank=embedding_rank,
                reranker_score=top.score,
                type_compatible=True,
                entity_hint=entity_hint,
                model_version=self.reranker.model_version,
            )

        score_margin = top.score - reranked[1].score
        reason = "decision_gate_passed"
        status = MappingStatus.MATCHED
        canonical_field_id: str | None = top.canonical_field_id
        if top.score < self.thresholds.min_reranker_score:
            reason = "insufficient_score"
            status = MappingStatus.AMBIGUOUS
            canonical_field_id = None
        elif score_margin < self.thresholds.min_margin:
            reason = "insufficient_margin"
            status = MappingStatus.AMBIGUOUS
            canonical_field_id = None

        return self._mapping(
            context,
            status=status,
            canonical_field_id=canonical_field_id,
            candidates=reranked,
            reason=reason,
            rule="semantic_decision_gate",
            embedding_rank=embedding_rank,
            reranker_score=top.score,
            score_margin=score_margin,
            type_compatible=True,
            entity_hint=entity_hint,
            model_version=self.reranker.model_version,
        )

    def _mapping(
        self,
        context: DocumentFieldContext,
        *,
        status: MappingStatus,
        reason: str,
        rule: str,
        candidates: tuple[ScoredCandidate, ...] = (),
        canonical_field_id: str | None = None,
        embedding_rank: int | None = None,
        reranker_score: float | None = None,
        score_margin: float | None = None,
        type_compatible: bool | None = None,
        entity_hint: str | None = None,
        model_version: str | None = None,
    ) -> FieldMapping:
        return FieldMapping(
            field_id=context.field_id,
            repeat_index=context.repeat_index,
            status=status,
            canonical_field_id=canonical_field_id,
            candidates=candidates,
            evidence=MappingEvidence(
                reason=reason,
                rule=rule,
                embedding_rank=embedding_rank,
                reranker_score=reranker_score,
                score_margin=score_margin,
                type_compatible=type_compatible,
                entity_hint=entity_hint,
                catalog_version=self.catalog.version,
                model_version=model_version,
            ),
        )


def _is_unique_exact_match(
    matches: Sequence[CanonicalFieldDefinition],
    *,
    entity_hint: str | None,
    require_unique_entity: bool,
) -> bool:
    if len(matches) != 1:
        return False
    if entity_hint is not None and matches[0].entity != entity_hint:
        return False
    if require_unique_entity and entity_hint is None:
        return False
    return True


def _valid_ranking(
    candidates: Sequence[ScoredCandidate],
    *,
    allowed_ids: set[str],
    require_all_ids: bool,
) -> bool:
    candidate_ids = [candidate.canonical_field_id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        return False
    if not set(candidate_ids).issubset(allowed_ids):
        return False
    if require_all_ids and set(candidate_ids) != allowed_ids:
        return False
    if [candidate.rank for candidate in candidates] != list(range(1, len(candidates) + 1)):
        return False
    return all(
        left.score >= right.score for left, right in zip(candidates, candidates[1:], strict=False)
    )


def _entity_hint(context: DocumentFieldContext) -> str | None:
    structural_text = " ".join(
        (
            context.section,
            *context.row_labels,
            *context.nearby_labels,
        )
    )
    normalized = normalize_text(structural_text)
    matches = {
        entity
        for entity, terms in _ENTITY_TERMS.items()
        if any(normalize_text(term) in normalized for term in terms)
    }
    return next(iter(matches)) if len(matches) == 1 else None
