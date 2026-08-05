import math
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from .contracts import (
    FrozenContract,
    RequestContext,
    SupportedLanguage,
    ValidationCheckId,
    WarningCode,
)
from .queries import SearchQuery
from .retrieval.models import (
    ExpectedIndexContract,
    FusedCandidate,
    HybridVector,
    PerQueryRanking,
    RerankedCandidate,
    RetrievalResult,
    VerifiedCollectionHandle,
)

DraftT = TypeVar("DraftT", bound=BaseModel)

GenerationOperation = Literal[
    "easy_korean",
    "translation",
    "correction",
    "semantic_validation",
]


class SemanticValidationDecision(FrozenContract):
    status: Literal["passed", "failed", "inconclusive"]
    unavailable: bool = False
    failed_checks: tuple[ValidationCheckId, ...] = ()
    inconclusive_checks: tuple[ValidationCheckId, ...] = ()

    @model_validator(mode="after")
    def validate_status_contract(self) -> "SemanticValidationDecision":
        if self.status == "passed" and (self.failed_checks or self.inconclusive_checks):
            raise ValueError("passed validation cannot contain failed or inconclusive checks")
        if self.status == "failed" and (
            not self.failed_checks or self.inconclusive_checks
        ):
            raise ValueError("failed validation requires only failed checks")
        if self.status == "inconclusive" and (
            self.failed_checks or not self.inconclusive_checks
        ):
            raise ValueError("inconclusive validation requires only inconclusive checks")
        if self.unavailable and self.status != "inconclusive":
            raise ValueError("unavailable validation must be inconclusive")
        return self


class TraceEvent(FrozenContract):
    run_id: str
    node_name: str
    status: Literal["started", "succeeded", "degraded", "failed"]
    latency_ms: float = Field(ge=0)
    retry_count: int = Field(ge=0, le=2)
    target_language: SupportedLanguage | None = None
    model_revision: str | None = None
    prompt_version: str | None = None
    context_pack_version: str | None = None
    dataset_revision: str | None = None
    reference_ids: tuple[str, ...] = ()
    warning_codes: tuple[WarningCode, ...] = ()

    @field_validator("latency_ms")
    @classmethod
    def validate_latency(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("latency_ms must be finite")
        return value


class DenseSparseEncoder(Protocol):
    def encode_queries(self, texts: Sequence[str]) -> tuple[HybridVector, ...]: ...


class HybridSearchStore(Protocol):
    def search_many(
        self,
        queries: Sequence[tuple[SearchQuery, HybridVector]],
        *,
        target_language: SupportedLanguage,
        collection: VerifiedCollectionHandle,
    ) -> tuple[PerQueryRanking, ...]: ...

    def verify_contract(
        self,
        *,
        expected: ExpectedIndexContract,
    ) -> VerifiedCollectionHandle: ...


class CandidateReranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: Sequence[FusedCandidate],
    ) -> tuple[RerankedCandidate, ...]: ...


class StructuredGenerationPort(Protocol):
    def generate(
        self,
        *,
        operation: GenerationOperation,
        payload: Mapping[str, object],
        response_model: type[DraftT],
    ) -> DraftT: ...


class SemanticValidationPort(Protocol):
    def validate(
        self,
        *,
        component: Literal["easy_korean", "translation"],
        request_context: RequestContext,
        target_language: SupportedLanguage | None,
        candidate: str,
    ) -> SemanticValidationDecision: ...


class EpsRetriever(Protocol):
    def retrieve(
        self,
        *,
        queries: Sequence[SearchQuery],
        standard_korean_text: str,
        target_language: SupportedLanguage,
    ) -> RetrievalResult: ...


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...


class NoopTraceSink:
    def emit(self, event: TraceEvent) -> None:
        return None


class EpsIndexStore(Protocol):
    def create_collection(
        self, collection_name: str, spec: object
    ) -> None: ...

    def ensure_payload_indexes(
        self, collection_name: str, fields: tuple[str, ...]
    ) -> None: ...

    def upsert_batch(
        self, collection_name: str, points: tuple[dict[str, object], ...]
    ) -> None: ...

    def verify_collection(
        self,
        collection_name: str,
        expected_count: int,
        spec: object,
        expected_languages: tuple[str, ...],
        expected_contract: ExpectedIndexContract,
    ) -> None: ...

    def swap_alias(
        self, alias_name: str, collection_name: str
    ) -> None: ...


__all__ = [
    "CandidateReranker",
    "DenseSparseEncoder",
    "DraftT",
    "EpsIndexStore",
    "EpsRetriever",
    "GenerationOperation",
    "HybridSearchStore",
    "NoopTraceSink",
    "SemanticValidationDecision",
    "SemanticValidationPort",
    "StructuredGenerationPort",
    "TraceEvent",
    "TraceSink",
]
