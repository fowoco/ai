from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.documents.dynamic_automation.models import (
    CanonicalFieldDefinition,
    DocumentFieldContext,
    ScoredCandidate,
)


@dataclass
class FakeCandidateRetriever:
    results: tuple[ScoredCandidate, ...] | None = ()
    model_version: str = "fake-embedding-v1"
    error: Exception | None = None
    enforce_top_k: bool = True

    def retrieve(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[CanonicalFieldDefinition],
        top_k: int,
    ) -> tuple[ScoredCandidate, ...] | None:
        del context, candidates
        if self.error is not None:
            raise self.error
        if self.results is None:
            return None
        return self.results[:top_k] if self.enforce_top_k else self.results


@dataclass
class FakeCandidateReranker:
    results: tuple[ScoredCandidate, ...] | None = ()
    model_version: str = "fake-reranker-v1"
    error: Exception | None = None

    def rerank(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[ScoredCandidate],
    ) -> tuple[ScoredCandidate, ...] | None:
        del context, candidates
        if self.error is not None:
            raise self.error
        return self.results


def scored(*items: tuple[str, float]) -> tuple[ScoredCandidate, ...]:
    return tuple(
        ScoredCandidate(canonical_field_id=field_id, score=score, rank=rank)
        for rank, (field_id, score) in enumerate(items, start=1)
    )
