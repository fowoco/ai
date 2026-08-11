"""Load deterministic domain heads over fixed local Qwen mapping backends."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .models import CanonicalFieldDefinition, DocumentFieldContext, ScoredCandidate
from .qwen import (
    QWEN3_EMBEDDING_REPO,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_REPO,
    QWEN3_RERANKER_REVISION,
    EmbeddingBackend,
    Qwen3CandidateReranker,
    Qwen3EmbeddingRetriever,
    RerankerBackend,
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class QueryBiasProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_kind: Literal["query_bias_projection"]
    embedding_dimension: int = Field(ge=1, le=100_000)
    positive_pair_count: int = Field(ge=1)
    query_bias: tuple[float, ...] = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def _dimension_matches_weights(self) -> QueryBiasProjection:
        if len(self.query_bias) != self.embedding_dimension:
            raise ValueError("query projection dimension does not match query_bias")
        if not all(math.isfinite(value) for value in self.query_bias):
            raise ValueError("query projection weights must be finite")
        return self


class ScoreCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_kind: Literal["score_calibration"]
    positive_pair_count: int = Field(ge=1)
    negative_pair_count: int = Field(ge=1)
    scale: float
    bias: float

    @model_validator(mode="after")
    def _weights_are_finite(self) -> ScoreCalibration:
        if not math.isfinite(self.scale) or not math.isfinite(self.bias):
            raise ValueError("reranker calibration weights must be finite")
        return self


AdapterWeights = Annotated[
    QueryBiasProjection | ScoreCalibration,
    Field(discriminator="adapter_kind"),
]


class DomainAdapterArtifact(BaseModel):
    """Strict, portable runtime artifact produced by the training command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["dynamic-mapping-adapter-v2"]
    model_kind: Literal["bi-encoder", "pair-reranker"]
    base_model_repo: str = Field(min_length=1, max_length=300)
    base_model_revision: str = Field(min_length=1, max_length=200)
    seed: int = Field(ge=0)
    weights: AdapterWeights

    @model_validator(mode="after")
    def _kind_matches_weights_and_pinned_base(self) -> DomainAdapterArtifact:
        if self.model_kind == "bi-encoder":
            if not isinstance(self.weights, QueryBiasProjection):
                raise ValueError("bi-encoder artifact requires query projection weights")
            expected = (QWEN3_EMBEDDING_REPO, QWEN3_EMBEDDING_REVISION)
        else:
            if not isinstance(self.weights, ScoreCalibration):
                raise ValueError("pair-reranker artifact requires calibration weights")
            expected = (QWEN3_RERANKER_REPO, QWEN3_RERANKER_REVISION)
        if (self.base_model_repo, self.base_model_revision) != expected:
            raise ValueError("domain adapter does not identify the pinned Qwen base")
        return self


@dataclass(frozen=True)
class DomainEmbeddingRetriever:
    delegate: Qwen3EmbeddingRetriever
    artifact_sha256: str

    @property
    def model_version(self) -> str:
        return f"domain-bi-encoder@{self.artifact_sha256}"

    def retrieve(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[CanonicalFieldDefinition],
        top_k: int,
    ) -> tuple[ScoredCandidate, ...]:
        return self.delegate.retrieve(context, candidates, top_k)


@dataclass(frozen=True)
class DomainCandidateReranker:
    delegate: Qwen3CandidateReranker
    artifact_sha256: str

    @property
    def model_version(self) -> str:
        return f"domain-pair-reranker@{self.artifact_sha256}"

    def rerank(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[ScoredCandidate],
    ) -> tuple[ScoredCandidate, ...]:
        return self.delegate.rerank(context, candidates)


def adapter_file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_domain_embedding_retriever(
    artifact_path: str | Path,
    *,
    backend: EmbeddingBackend | None = None,
    model_path: str | Path | None = None,
    expected_sha256: str | None = None,
    max_length: int = 512,
    batch_size: int = 8,
) -> DomainEmbeddingRetriever:
    artifact, digest = _load_artifact(artifact_path, expected_sha256=expected_sha256)
    if artifact.model_kind != "bi-encoder" or not isinstance(
        artifact.weights, QueryBiasProjection
    ):
        raise ValueError("artifact is not a domain bi-encoder projection")
    base = Qwen3EmbeddingRetriever(
        model_path,
        backend=backend,
        max_length=max_length,
        batch_size=batch_size,
    )
    projected = Qwen3EmbeddingRetriever(
        backend=_ProjectedEmbeddingBackend(base.backend, artifact.weights),
        max_length=max_length,
        batch_size=batch_size,
    )
    return DomainEmbeddingRetriever(projected, digest)


def load_domain_reranker(
    artifact_path: str | Path,
    *,
    definition_resolver: Callable[[str], CanonicalFieldDefinition],
    backend: RerankerBackend | None = None,
    model_path: str | Path | None = None,
    expected_sha256: str | None = None,
    max_length: int = 512,
    batch_size: int = 8,
) -> DomainCandidateReranker:
    artifact, digest = _load_artifact(artifact_path, expected_sha256=expected_sha256)
    if artifact.model_kind != "pair-reranker" or not isinstance(
        artifact.weights, ScoreCalibration
    ):
        raise ValueError("artifact is not a domain pair-reranker calibration")
    base = Qwen3CandidateReranker(
        model_path,
        backend=backend,
        definition_resolver=definition_resolver,
        max_length=max_length,
        batch_size=batch_size,
    )
    calibrated = Qwen3CandidateReranker(
        backend=_CalibratedRerankerBackend(base.backend, artifact.weights),
        definition_resolver=definition_resolver,
        max_length=max_length,
        batch_size=batch_size,
    )
    return DomainCandidateReranker(calibrated, digest)


def _load_artifact(
    path: str | Path, *, expected_sha256: str | None
) -> tuple[DomainAdapterArtifact, str]:
    artifact_path = Path(path)
    payload = artifact_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None:
        if not _is_sha256(expected_sha256) or digest != expected_sha256:
            raise ValueError("domain adapter SHA-256 does not match the manifest")
    try:
        artifact = DomainAdapterArtifact.model_validate_json(payload)
    except ValidationError as error:
        raise ValueError(f"invalid domain adapter artifact: {error}") from error
    return artifact, digest


@dataclass(frozen=True)
class _ProjectedEmbeddingBackend:
    base: EmbeddingBackend
    projection: QueryBiasProjection

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        vectors = self.base.encode_queries(
            texts, max_length=max_length, batch_size=batch_size
        )
        validated = _validate_vectors(vectors, self.projection.embedding_dimension)
        return tuple(
            _normalize(
                tuple(
                    value + bias
                    for value, bias in zip(
                        vector, self.projection.query_bias, strict=True
                    )
                )
            )
            for vector in validated
        )

    def encode_documents(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        vectors = self.base.encode_documents(
            texts, max_length=max_length, batch_size=batch_size
        )
        return _validate_vectors(vectors, self.projection.embedding_dimension)


@dataclass(frozen=True)
class _CalibratedRerankerBackend:
    base: RerankerBackend
    calibration: ScoreCalibration

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[float, ...]:
        raw_scores = self.base.score_pairs(
            pairs, max_length=max_length, batch_size=batch_size
        )
        if len(raw_scores) != len(pairs):
            raise RuntimeError("base reranker returned the wrong score count")
        calibrated: list[float] = []
        for raw_score in raw_scores:
            score = float(raw_score)
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise RuntimeError("base reranker returned an invalid probability")
            calibrated.append(
                _sigmoid(self.calibration.scale * score + self.calibration.bias)
            )
        return tuple(calibrated)


def _validate_vectors(
    vectors: Sequence[Sequence[float]], dimension: int
) -> tuple[tuple[float, ...], ...]:
    validated = tuple(tuple(float(value) for value in vector) for vector in vectors)
    if any(len(vector) != dimension for vector in validated):
        raise RuntimeError("base embedding dimension does not match the adapter")
    if any(not math.isfinite(value) for vector in validated for value in vector):
        raise RuntimeError("base embedding returned non-finite values")
    return validated


def _normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return tuple(value / norm for value in vector)


def _sigmoid(value: float) -> float:
    if value >= 0:
        exponential = math.exp(-value)
        return 1 / (1 + exponential)
    exponential = math.exp(value)
    return exponential / (1 + exponential)


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


__all__ = [
    "DomainAdapterArtifact",
    "DomainCandidateReranker",
    "DomainEmbeddingRetriever",
    "adapter_file_sha256",
    "load_domain_embedding_retriever",
    "load_domain_reranker",
]
