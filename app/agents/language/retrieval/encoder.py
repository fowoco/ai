from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.agents.language.ports import DenseSparseEncoder
from app.agents.language.retrieval.models import HybridVector


@dataclass(frozen=True)
class RawBgeBatch:
    dense_vectors: tuple[tuple[float, ...], ...]
    lexical_weights: tuple[Mapping[int, float], ...]


class BGEM3Backend(Protocol):
    def token_count(self, text: str) -> int: ...

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int = 128,
        return_dense: bool = True,
        return_sparse: bool = True,
        return_colbert_vecs: bool = False,
    ) -> RawBgeBatch: ...


class FlagEmbeddingBgeM3Backend(BGEM3Backend):
    def __init__(self, model_path: str, *, use_fp16: bool = True) -> None:
        self.model_path = model_path
        self.use_fp16 = use_fp16
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from FlagEmbedding import BGEM3FlagModel
            except ImportError as err:
                raise RuntimeError("FlagEmbedding BGE-M3 model is not available") from err
            self._model = BGEM3FlagModel(
                self.model_path,
                use_fp16=self.use_fp16,
            )
        return self._model

    def token_count(self, text: str) -> int:
        model = self._get_model()
        return len(model.tokenizer.encode(text, add_special_tokens=True))

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int = 128,
        return_dense: bool = True,
        return_sparse: bool = True,
        return_colbert_vecs: bool = False,
    ) -> RawBgeBatch:
        output = self._get_model().encode(
            texts,
            max_length=max_length,
            return_dense=return_dense,
            return_sparse=return_sparse,
            return_colbert_vecs=return_colbert_vecs,
        )
        try:
            dense_vectors = tuple(
                tuple(float(value) for value in vector)
                for vector in output["dense_vecs"]
            )
            lexical_weights = tuple(
                {int(token_id): float(weight) for token_id, weight in weights.items()}
                for weights in output["lexical_weights"]
            )
        except (KeyError, TypeError, ValueError) as err:
            raise RuntimeError("Invalid FlagEmbedding BGE-M3 output") from err
        return RawBgeBatch(
            dense_vectors=dense_vectors,
            lexical_weights=lexical_weights,
        )


class BgeM3Encoder(DenseSparseEncoder):
    def __init__(
        self, backend: BGEM3Backend, max_length: int = 128
    ) -> None:
        self.backend = backend
        self.max_length = max_length

    def encode_queries(self, texts: Sequence[str]) -> tuple[HybridVector, ...]:
        for t in texts:
            if self.backend.token_count(t) > self.max_length:
                raise ValueError("RETRIEVAL_QUERY_TOO_LONG")

        raw_batch = self.backend.encode_queries(
            texts,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        vectors = []
        for dense, sparse_map in zip(
            raw_batch.dense_vectors, raw_batch.lexical_weights, strict=True
        ):
            sorted_items = sorted(sparse_map.items(), key=lambda x: x[0])
            indices = tuple(int(k) for k, _ in sorted_items)
            values = tuple(float(v) for _, v in sorted_items)
            vectors.append(
                HybridVector(
                    dense=tuple(float(x) for x in dense),
                    sparse_indices=indices,
                    sparse_values=values,
                )
            )

        return tuple(vectors)
