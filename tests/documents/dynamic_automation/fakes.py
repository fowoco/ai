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
    results: tuple[ScoredCandidate, ...] = ()
    model_version: str = "fake-embedding-v1"
    error: Exception | None = None

    def retrieve(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[CanonicalFieldDefinition],
        top_k: int,
    ) -> tuple[ScoredCandidate, ...]:
        del context, candidates
        if self.error is not None:
            raise self.error
        return self.results[:top_k]


@dataclass
class FakeCandidateReranker:
    results: tuple[ScoredCandidate, ...] = ()
    model_version: str = "fake-reranker-v1"
    error: Exception | None = None

    def rerank(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[ScoredCandidate],
    ) -> tuple[ScoredCandidate, ...]:
        del context, candidates
        if self.error is not None:
            raise self.error
        return self.results


def scored(*items: tuple[str, float]) -> tuple[ScoredCandidate, ...]:
    return tuple(
        ScoredCandidate(canonical_field_id=field_id, score=score, rank=rank)
        for rank, (field_id, score) in enumerate(items, start=1)
    )
