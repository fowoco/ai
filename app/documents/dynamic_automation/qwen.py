"""Lazy, local-only Qwen3 adapters for canonical field mapping."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from .models import CanonicalFieldDefinition, DocumentFieldContext, ScoredCandidate

QWEN3_EMBEDDING_REPO = "Qwen/Qwen3-Embedding-0.6B"
QWEN3_EMBEDDING_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QWEN3_RERANKER_REPO = "Qwen/Qwen3-Reranker-0.6B"
QWEN3_RERANKER_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"

QWEN3_EMBEDDING_CACHE_NAME = "qwen3-embedding-0.6b"
QWEN3_RERANKER_CACHE_NAME = "qwen3-reranker-0.6b"

_RERANKER_SYSTEM_PREFIX = (
    '<|im_start|>system\nJudge whether the Document meets the requirements based on '
    'the Query and the Instruct provided. Note that the answer can only be "yes" or '
    '"no".<|im_end|>\n<|im_start|>user\n'
)
_RERANKER_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_MAPPING_INSTRUCTION = (
    "주어진 문서 필드의 구조적 문맥에 가장 적합한 canonical field를 찾으세요."
)


class EmbeddingBackend(Protocol):
    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]: ...

    def encode_documents(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]: ...


class RerankerBackend(Protocol):
    def score_pairs(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[float, ...]: ...


class LocalSentenceTransformerBackend:
    """Load SentenceTransformer only on first use and never access the network."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path)
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as err:
                raise RuntimeError("sentence-transformers is not installed") from err
            self._model = SentenceTransformer(
                str(self.model_path),
                local_files_only=True,
            )
        return self._model

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        return self._encode(texts, max_length=max_length, batch_size=batch_size)

    def encode_documents(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        return self._encode(texts, max_length=max_length, batch_size=batch_size)

    def _encode(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        model = self._get_model()
        model.max_seq_length = max_length
        vectors = model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return tuple(tuple(float(value) for value in vector) for vector in vectors)


class LocalQwen3RerankerBackend:
    """Lazy local Transformers backend using Qwen's official yes/no scoring."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path)
        self._tokenizer: Any = None
        self._model: Any = None

    def _get_components(self) -> tuple[Any, Any]:
        if self._tokenizer is None or self._model is None:
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer
            except ImportError as err:
                raise RuntimeError("transformers is not installed") from err
            tokenizer = AutoTokenizer.from_pretrained(
                str(self.model_path),
                local_files_only=True,
            )
            tokenizer.padding_side = "left"
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(
                str(self.model_path),
                local_files_only=True,
            ).eval()
            self._tokenizer = tokenizer
            self._model = model
        return self._tokenizer, self._model

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[float, ...]:
        if not pairs:
            return ()
        try:
            import torch
        except ImportError as err:
            raise RuntimeError("torch is not installed") from err
        tokenizer, model = self._get_components()
        yes_token_id = int(tokenizer.convert_tokens_to_ids("yes"))
        no_token_id = int(tokenizer.convert_tokens_to_ids("no"))
        prefix_tokens = tokenizer.encode(
            _RERANKER_SYSTEM_PREFIX,
            add_special_tokens=False,
        )
        suffix_tokens = tokenizer.encode(
            _RERANKER_SUFFIX,
            add_special_tokens=False,
        )
        content_max_length = max_length - len(prefix_tokens) - len(suffix_tokens)
        if content_max_length < 1:
            raise ValueError("max_length is too small for the Qwen3 reranker prompt")
        scores: list[float] = []
        for offset in range(0, len(pairs), batch_size):
            batch = pairs[offset : offset + batch_size]
            contents = [_format_reranker_content(query, document) for query, document in batch]
            encoded = tokenizer(
                contents,
                add_special_tokens=False,
                padding=False,
                truncation=True,
                max_length=content_max_length,
                return_attention_mask=False,
            )
            input_ids = [
                [*prefix_tokens, *content_tokens, *suffix_tokens]
                for content_tokens in encoded["input_ids"]
            ]
            inputs = tokenizer.pad(
                {"input_ids": input_ids},
                padding=True,
                max_length=max_length,
                return_tensors="pt",
            )
            with torch.inference_mode():
                output = model(**inputs)
            logits = output.logits[:, -1, :].detach().cpu().tolist()
            scores.extend(
                _yes_probability(row[yes_token_id], row[no_token_id]) for row in logits
            )
        return tuple(scores)


class Qwen3EmbeddingRetriever:
    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        backend: EmbeddingBackend | None = None,
        max_length: int = 512,
        batch_size: int = 8,
    ) -> None:
        if max_length < 1 or max_length > 512:
            raise ValueError("max_length must be between 1 and 512")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if backend is None:
            backend = LocalSentenceTransformerBackend(model_path or QWEN3_EMBEDDING_REPO)
        self.backend = backend
        self.max_length = max_length
        self.batch_size = batch_size

    @property
    def model_version(self) -> str:
        return f"{QWEN3_EMBEDDING_REPO}@{QWEN3_EMBEDDING_REVISION}"

    def retrieve(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[CanonicalFieldDefinition],
        top_k: int,
    ) -> tuple[ScoredCandidate, ...]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if not candidates:
            return ()
        query_vectors = self.backend.encode_queries(
            (_format_context(context),),
            max_length=self.max_length,
            batch_size=self.batch_size,
        )
        document_vectors = self.backend.encode_documents(
            tuple(_format_definition(candidate) for candidate in candidates),
            max_length=self.max_length,
            batch_size=self.batch_size,
        )
        if len(query_vectors) != 1 or len(document_vectors) != len(candidates):
            raise RuntimeError("invalid Qwen3 embedding batch size")
        query_vector = query_vectors[0]
        scored = [
            (
                _normalized_cosine(query_vector, vector),
                candidate.field_id,
            )
            for candidate, vector in zip(candidates, document_vectors, strict=True)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(
            ScoredCandidate(canonical_field_id=field_id, score=score, rank=rank)
            for rank, (score, field_id) in enumerate(scored[:top_k], start=1)
        )


class Qwen3CandidateReranker:
    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        backend: RerankerBackend | None = None,
        max_length: int = 512,
        batch_size: int = 8,
    ) -> None:
        if max_length < 1 or max_length > 512:
            raise ValueError("max_length must be between 1 and 512")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if backend is None:
            backend = LocalQwen3RerankerBackend(model_path or QWEN3_RERANKER_REPO)
        self.backend = backend
        self.max_length = max_length
        self.batch_size = batch_size

    @property
    def model_version(self) -> str:
        return f"{QWEN3_RERANKER_REPO}@{QWEN3_RERANKER_REVISION}"

    def rerank(
        self,
        context: DocumentFieldContext,
        candidates: Sequence[ScoredCandidate],
    ) -> tuple[ScoredCandidate, ...]:
        if not candidates:
            return ()
        query = _format_context(context)
        scores = self.backend.score_pairs(
            tuple((query, candidate.canonical_field_id) for candidate in candidates),
            max_length=self.max_length,
            batch_size=self.batch_size,
        )
        if len(scores) != len(candidates):
            raise RuntimeError("invalid Qwen3 reranker batch size")
        reranked: list[tuple[float, int, str]] = []
        for candidate, raw_score in zip(candidates, scores, strict=True):
            score = float(raw_score)
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise RuntimeError("invalid Qwen3 reranker probability")
            reranked.append((score, candidate.rank, candidate.canonical_field_id))
        reranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        return tuple(
            ScoredCandidate(canonical_field_id=field_id, score=score, rank=rank)
            for rank, (score, _, field_id) in enumerate(reranked, start=1)
        )


def _format_context(context: DocumentFieldContext) -> str:
    return "\n".join(
        (
            f"{context.label} canonical field를 찾으세요.",
            f"문서 제목: {context.document_title}",
            f"섹션: {context.section}",
            f"행 라벨: {', '.join(context.row_labels)}",
            f"주변 라벨: {', '.join(context.nearby_labels)}",
            f"필드 유형: {context.field_type}",
            f"요소 종류: {context.kind}",
        )
    )


def _format_definition(candidate: CanonicalFieldDefinition) -> str:
    return "\n".join(
        (
            f"canonical field: {candidate.field_id}",
            f"entity: {candidate.entity}",
            f"value type: {candidate.value_type}",
            f"aliases: {', '.join(candidate.aliases)}",
            f"description: {candidate.description}",
        )
    )


def _format_reranker_content(query: str, document: str) -> str:
    return (
        f"<Instruct>: {_MAPPING_INSTRUCTION}\n\n"
        f"<Query>: {query}\n\n"
        f"<Document>: {document}"
    )


def _normalized_cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise RuntimeError("Qwen3 embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.5
    cosine = sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
    return min(1.0, max(0.0, (cosine + 1.0) / 2.0))


def _yes_probability(yes_logit: float, no_logit: float) -> float:
    maximum = max(yes_logit, no_logit)
    yes = math.exp(yes_logit - maximum)
    no = math.exp(no_logit - maximum)
    return yes / (yes + no)


__all__ = [
    "LocalQwen3RerankerBackend",
    "LocalSentenceTransformerBackend",
    "QWEN3_EMBEDDING_REPO",
    "QWEN3_EMBEDDING_REVISION",
    "QWEN3_RERANKER_REPO",
    "QWEN3_RERANKER_REVISION",
    "Qwen3CandidateReranker",
    "Qwen3EmbeddingRetriever",
]
