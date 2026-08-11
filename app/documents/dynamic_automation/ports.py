"""Model-independent ports for canonical field retrieval and reranking."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import CanonicalFieldDefinition, DocumentFieldContext, ScoredCandidate


class CandidateRetriever(Protocol):
    @property
    def model_version(self) -> str: ...

    def retrieve(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[CanonicalFieldDefinition],
        top_k: int,
    ) -> tuple[ScoredCandidate, ...]: ...


class CandidateReranker(Protocol):
    @property
    def model_version(self) -> str: ...

    def rerank(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[ScoredCandidate],
    ) -> tuple[ScoredCandidate, ...]: ...
