from collections.abc import Mapping, Sequence
from threading import Barrier, Event
from typing import Any, TypeVar

from pydantic import BaseModel

from app.agents.language.contracts import RequestContext, SupportedLanguage
from app.agents.language.ports import (
    GenerationOperation,
    SemanticValidationDecision,
    TraceEvent,
)
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.models import (
    ExpectedIndexContract,
    FusedCandidate,
    HybridVector,
    PerQueryRanking,
    RerankedCandidate,
    RetrievalResult,
    VerifiedCollectionHandle,
)


class FakePortError(RuntimeError):
    """Typed failure used by deterministic port fakes."""


class FakeContractMismatchError(FakePortError):
    """Configured fake failure for a provenance mismatch."""


class FakeSchemaMismatchError(FakePortError):
    """Configured fake failure for a collection schema mismatch."""


FakeContractSchemaMismatchError = FakeSchemaMismatchError


def _coordinate(
    *,
    barrier: Barrier | None,
    entered: Event | None,
    release: Event | None,
) -> None:
    if entered is not None:
        entered.set()
    if barrier is not None:
        barrier.wait()
    if release is not None:
        release.wait()


OutcomeT = TypeVar("OutcomeT")


def _resolve_outcome(
    *,
    scripted_results: list[OutcomeT | BaseException],
    result: OutcomeT | None,
    failure: BaseException | None,
    missing_result_message: str,
) -> OutcomeT:
    if scripted_results:
        outcome = scripted_results.pop(0)
    elif failure is not None:
        outcome = failure
    elif result is not None:
        outcome = result
    else:
        raise FakePortError(missing_result_message)
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


class FakeDenseSparseEncoder:
    def __init__(
        self,
        result: tuple[HybridVector, ...] | None = None,
        *,
        failure: BaseException | None = None,
        error: BaseException | None = None,
        scripted_results: Sequence[tuple[HybridVector, ...] | BaseException] = (),
        barrier: Barrier | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.result = result
        self.failure = failure or error
        self.scripted_results = list(scripted_results)
        self.barrier = barrier
        self.entered = entered
        self.release = release
        self.calls: list[tuple[str, ...]] = []

    def encode_queries(self, texts: Sequence[str]) -> tuple[HybridVector, ...]:
        captured = tuple(texts)
        self.calls.append(captured)
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        return _resolve_outcome(
            scripted_results=self.scripted_results,
            result=self.result,
            failure=self.failure,
            missing_result_message="no encoder result configured",
        )


class FakeHybridSearchStore:
    def __init__(
        self,
        rankings: tuple[PerQueryRanking, ...] | None = None,
        *,
        failure: BaseException | None = None,
        error: BaseException | None = None,
        scripted_results: Sequence[tuple[PerQueryRanking, ...] | BaseException] = (),
        verified_handle: VerifiedCollectionHandle | None = None,
        contract_outcome: str = "verified",
        contract_failure: BaseException | None = None,
        barrier: Barrier | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.rankings = rankings
        self.failure = failure or error
        self.scripted_results = list(scripted_results)
        self.verified_handle = verified_handle
        self.contract_outcome = contract_outcome
        self.contract_failure = contract_failure
        self.barrier = barrier
        self.entered = entered
        self.release = release
        self.verify_calls: list[ExpectedIndexContract] = []
        self.search_calls: list[dict[str, Any]] = []
        self.calls = self.search_calls
        self.alias_target = (
            verified_handle.collection_name if verified_handle is not None else None
        )

    def verify_contract(
        self,
        *,
        expected: ExpectedIndexContract,
    ) -> VerifiedCollectionHandle:
        self.verify_calls.append(expected)
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        if self.contract_failure is not None:
            raise self.contract_failure
        if self.contract_outcome == "mismatched":
            raise FakeContractMismatchError("index contract mismatch")
        if self.contract_outcome == "schema-invalid":
            raise FakeSchemaMismatchError("collection schema mismatch")
        if self.contract_outcome != "verified":
            raise ValueError(f"unknown fake contract outcome: {self.contract_outcome}")
        if self.verified_handle is None:
            self.verified_handle = VerifiedCollectionHandle(
                collection_name="eps-language-verified",
                dataset_version=expected.dataset_revision,
                embedding_model_repo=expected.embedding_model_repo,
                embedding_model_revision=expected.embedding_model_revision,
                index_contract_version=expected.index_contract_version,
                point_count=1,
            )
        if self.alias_target is None:
            self.alias_target = self.verified_handle.collection_name
        return self.verified_handle

    def search_many(
        self,
        queries: Sequence[tuple[SearchQuery, HybridVector]],
        *,
        target_language: SupportedLanguage,
        collection: VerifiedCollectionHandle,
    ) -> tuple[PerQueryRanking, ...]:
        self.search_calls.append(
            {
                "queries": tuple(queries),
                "target_language": target_language,
                "collection": collection,
            }
        )
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        return _resolve_outcome(
            scripted_results=self.scripted_results,
            result=self.rankings,
            failure=self.failure,
            missing_result_message="no store result configured",
        )

    def switch_alias(self, collection_name: str) -> None:
        self.alias_target = collection_name


class FakeCandidateReranker:
    def __init__(
        self,
        reranked: tuple[RerankedCandidate, ...] | None = None,
        *,
        failure: BaseException | None = None,
        error: BaseException | None = None,
        scripted_results: Sequence[tuple[RerankedCandidate, ...] | BaseException] = (),
        barrier: Barrier | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.reranked = reranked
        self.failure = failure or error
        self.scripted_results = list(scripted_results)
        self.barrier = barrier
        self.entered = entered
        self.release = release
        self.calls: list[dict[str, Any]] = []

    def rerank(
        self,
        query: str,
        candidates: Sequence[FusedCandidate],
    ) -> tuple[RerankedCandidate, ...]:
        self.calls.append({"query": query, "candidates": tuple(candidates)})
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        return _resolve_outcome(
            scripted_results=self.scripted_results,
            result=self.reranked,
            failure=self.failure,
            missing_result_message="no reranker result configured",
        )


DraftT = TypeVar("DraftT", bound=BaseModel)


class FakeStructuredGenerationPort:
    def __init__(
        self,
        result: BaseModel | None = None,
        *,
        failure: BaseException | None = None,
        error: BaseException | None = None,
        scripted_results: Sequence[BaseModel | BaseException] = (),
        barrier: Barrier | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.result = result
        self.failure = failure or error
        self.scripted_results = list(scripted_results)
        self.barrier = barrier
        self.entered = entered
        self.release = release
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        operation: GenerationOperation,
        payload: Mapping[str, object],
        response_model: type[DraftT],
    ) -> DraftT:
        self.calls.append(
            {
                "operation": operation,
                "payload": dict(payload),
                "response_model": response_model,
            }
        )
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        result = _resolve_outcome(
            scripted_results=self.scripted_results,
            result=self.result,
            failure=self.failure,
            missing_result_message="no generation result configured",
        )
        return result  # type: ignore[return-value]


class FakeSemanticValidationPort:
    def __init__(
        self,
        result: SemanticValidationDecision | None = None,
        *,
        failure: BaseException | None = None,
        error: BaseException | None = None,
        scripted_results: Sequence[SemanticValidationDecision | BaseException] = (),
        barrier: Barrier | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.result = result
        self.failure = failure or error
        self.scripted_results = list(scripted_results)
        self.barrier = barrier
        self.entered = entered
        self.release = release
        self.calls: list[dict[str, Any]] = []

    def validate(
        self,
        *,
        component: str,
        request_context: RequestContext,
        target_language: SupportedLanguage | None,
        candidate: str,
    ) -> SemanticValidationDecision:
        self.calls.append(
            {
                "component": component,
                "request_context": request_context,
                "target_language": target_language,
                "candidate": candidate,
            }
        )
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        return _resolve_outcome(
            scripted_results=self.scripted_results,
            result=self.result,
            failure=self.failure,
            missing_result_message="no semantic validation result configured",
        )


class FakeEpsRetriever:
    def __init__(
        self,
        result: RetrievalResult | None = None,
        *,
        failure: BaseException | None = None,
        error: BaseException | None = None,
        scripted_results: Sequence[RetrievalResult | BaseException] = (),
        barrier: Barrier | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.result = result
        self.failure = failure or error
        self.scripted_results = list(scripted_results)
        self.barrier = barrier
        self.entered = entered
        self.release = release
        self.calls: list[dict[str, Any]] = []

    def retrieve(
        self,
        *,
        queries: Sequence[SearchQuery],
        standard_korean_text: str,
        target_language: SupportedLanguage,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "queries": tuple(queries),
                "standard_korean_text": standard_korean_text,
                "target_language": target_language,
            }
        )
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        return _resolve_outcome(
            scripted_results=self.scripted_results,
            result=self.result,
            failure=self.failure,
            missing_result_message="no retrieval result configured",
        )


class FakeTraceSink:
    def __init__(
        self,
        *,
        failure: BaseException | None = None,
        barrier: Barrier | None = None,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.failure = failure
        self.barrier = barrier
        self.entered = entered
        self.release = release
        self.events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)
        _coordinate(barrier=self.barrier, entered=self.entered, release=self.release)
        if self.failure is not None:
            raise self.failure


__all__ = [
    "FakeCandidateReranker",
    "FakeContractMismatchError",
    "FakeContractSchemaMismatchError",
    "FakeDenseSparseEncoder",
    "FakeEpsRetriever",
    "FakeHybridSearchStore",
    "FakePortError",
    "FakeSchemaMismatchError",
    "FakeSemanticValidationPort",
    "FakeStructuredGenerationPort",
    "FakeTraceSink",
]
