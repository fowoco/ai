import math
from typing import Annotated, Literal

from pydantic import (
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from ..contracts import (
    EpsLanguageCode,
    FrozenContract,
    QueryStrategy,
    SupportedLanguage,
    WarningItem,
)

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
Revision = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{40}$")]


def _require_finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("scores and vector values must be finite")
    return value


class HybridVector(FrozenContract):
    dense: tuple[float, ...] = Field(min_length=1024, max_length=1024)
    sparse_indices: tuple[StrictInt, ...]
    sparse_values: tuple[float, ...]

    @field_validator("dense", "sparse_values")
    @classmethod
    def validate_finite_values(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(_require_finite(value) for value in values)

    @model_validator(mode="after")
    def validate_sparse_structure(self) -> "HybridVector":
        if len(self.sparse_indices) != len(self.sparse_values):
            raise ValueError("sparse indices and values must have equal length")
        if any(index < 0 for index in self.sparse_indices):
            raise ValueError("sparse indices must be non-negative")
        if tuple(sorted(self.sparse_indices)) != self.sparse_indices:
            raise ValueError("sparse indices must be sorted")
        if len(set(self.sparse_indices)) != len(self.sparse_indices):
            raise ValueError("sparse indices must be unique")
        return self


class EpsReference(FrozenContract):
    point_id: NonEmptyText
    source_record_id: NonEmptyText
    korean_text: NonEmptyText
    translated_text: NonEmptyText
    target_language: SupportedLanguage
    eps_language_code: EpsLanguageCode
    source_page: StrictInt
    dataset_revision: NonEmptyText
    content_hash: NonEmptyText
    quality_status: NonEmptyText
    source: Literal["EPS"]
    source_url: NonEmptyText


class RankedCandidate(FrozenContract):
    reference: EpsReference
    rank: Annotated[StrictInt, Field(ge=0)]
    score: float

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        return _require_finite(value)


class PerQueryRanking(FrozenContract):
    query_kind: QueryStrategy
    candidates: tuple[RankedCandidate, ...]


class FusedCandidate(FrozenContract):
    reference: EpsReference
    fusion_score: float
    best_rank: Annotated[StrictInt, Field(ge=0)]
    contributing_queries: tuple[QueryStrategy, ...]

    @field_validator("fusion_score")
    @classmethod
    def validate_fusion_score(cls, value: float) -> float:
        return _require_finite(value)


class RerankedCandidate(FrozenContract):
    reference: EpsReference
    fusion_score: float
    reranker_score: float
    reranker_rank: Annotated[StrictInt, Field(ge=0)]

    @field_validator("fusion_score", "reranker_score")
    @classmethod
    def validate_scores(cls, value: float) -> float:
        return _require_finite(value)


class RerankerSelectedContext(FrozenContract):
    reference: EpsReference
    fusion_score: float
    reranker_score: float
    selection_rank: Annotated[StrictInt, Field(ge=0)]
    selected_by: Literal["reranker"]

    @field_validator("fusion_score", "reranker_score")
    @classmethod
    def validate_scores(cls, value: float) -> float:
        return _require_finite(value)


class FusionSelectedContext(FrozenContract):
    reference: EpsReference
    fusion_score: float
    reranker_score: None = None
    selection_rank: Annotated[StrictInt, Field(ge=0)]
    selected_by: Literal["cross_query_rrf"]

    @field_validator("fusion_score")
    @classmethod
    def validate_fusion_score(cls, value: float) -> float:
        return _require_finite(value)


SelectedContext = Annotated[
    RerankerSelectedContext | FusionSelectedContext,
    Field(discriminator="selected_by"),
]


class ExpectedIndexContract(FrozenContract):
    dataset_revision: NonEmptyText
    embedding_model_repo: Literal["BAAI/bge-m3"]
    embedding_model_revision: Revision
    index_contract_version: Literal["eps-language-index-v1"]
    point_count: StrictInt | None = None



class VerifiedCollectionHandle(FrozenContract):
    collection_name: NonEmptyText
    dataset_version: NonEmptyText
    embedding_model_repo: Literal["BAAI/bge-m3"]
    embedding_model_revision: Revision
    index_contract_version: Literal["eps-language-index-v1"]
    point_count: Annotated[StrictInt, Field(gt=0)]


class RetrievalResult(FrozenContract):
    dataset_version: NonEmptyText | None
    query_strategies: tuple[QueryStrategy, ...]
    contexts: tuple[SelectedContext, ...]
    warnings: tuple[WarningItem, ...]
    fallback_used: bool
    degraded_components: tuple[str, ...]


__all__ = [
    "EpsReference",
    "ExpectedIndexContract",
    "FusedCandidate",
    "FusionSelectedContext",
    "HybridVector",
    "PerQueryRanking",
    "RankedCandidate",
    "RerankedCandidate",
    "RerankerSelectedContext",
    "RetrievalResult",
    "SelectedContext",
    "VerifiedCollectionHandle",
]
