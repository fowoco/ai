from collections.abc import Sequence
from typing import Any, Protocol

from app.agents.language.ports import CandidateReranker
from app.agents.language.retrieval.models import FusedCandidate, RerankedCandidate


class RerankerBackend(Protocol):
    def compute_scores(
        self, pairs: Sequence[tuple[str, str]], max_length: int = 256
    ) -> tuple[float, ...]: ...


class LocalCandidateReranker(CandidateReranker):
    def __init__(
        self, backend: RerankerBackend, max_length: int = 256
    ) -> None:
        self.backend = backend
        self.max_length = max_length

    def rerank(
        self, query: str, candidates: Sequence[FusedCandidate]
    ) -> tuple[RerankedCandidate, ...]:
        if not candidates:
            return ()

        target_candidates = candidates[:30]
        pairs = [(query, c.reference.korean_text) for c in target_candidates]
        scores = self.backend.compute_scores(pairs, max_length=self.max_length)

        reranked = []
        for cand, score in zip(target_candidates, scores, strict=True):
            reranked.append(
                (
                    float(score),
                    cand.fusion_score,
                    cand.reference.point_id,
                    cand,
                )
            )

        # Sort: reranker_score DESC, fusion_score DESC, point_id ASC
        reranked.sort(key=lambda x: (-x[0], -x[1], x[2]))

        result = []
        for rank, (score, _, _, cand) in enumerate(reranked):
            result.append(
                RerankedCandidate(
                    reference=cand.reference,
                    fusion_score=cand.fusion_score,
                    reranker_score=score,
                    reranker_rank=rank,
                )
            )

        return tuple(result)


class FlagEmbeddingReranker(CandidateReranker):
    def __init__(
        self,
        model_path: str = "/models/bge-reranker-v2-m3",
        expected_revision: str = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        max_length: int = 256,
        use_fp16: bool = False,
    ) -> None:
        self.model_path = model_path
        self.expected_revision = expected_revision
        self.max_length = max_length
        self.use_fp16 = use_fp16
        self._reranker_model: Any = None

    def _get_model(self) -> Any:
        if self._reranker_model is None:
            try:
                from FlagEmbedding import FlagReranker
            except ImportError as err:
                raise RuntimeError("FlagEmbedding model not available") from err

            self._reranker_model = FlagReranker(
                self.model_path, use_fp16=self.use_fp16
            )
        return self._reranker_model

    def rerank(
        self, query: str, candidates: Sequence[FusedCandidate]
    ) -> tuple[RerankedCandidate, ...]:
        if not candidates:
            return ()

        model = self._get_model()
        target_candidates = candidates[:30]
        pairs = [[query, c.reference.korean_text] for c in target_candidates]
        scores = model.compute_score(pairs, max_length=self.max_length)
        if isinstance(scores, (float, int)):
            scores = [scores]

        reranked = []
        for cand, score in zip(target_candidates, scores, strict=True):
            reranked.append(
                (
                    float(score),
                    cand.fusion_score,
                    cand.reference.point_id,
                    cand,
                )
            )

        reranked.sort(key=lambda x: (-x[0], -x[1], x[2]))

        result = []
        for rank, (score, _, _, cand) in enumerate(reranked):
            result.append(
                RerankedCandidate(
                    reference=cand.reference,
                    fusion_score=cand.fusion_score,
                    reranker_score=score,
                    reranker_rank=rank,
                )
            )

        return tuple(result)
