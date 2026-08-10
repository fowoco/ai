from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

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
