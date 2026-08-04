import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..contracts import QueryStrategy
from .models import FusedCandidate, PerQueryRanking, RankedCandidate

DEFAULT_RRF_K = 60
DEFAULT_RRF_WEIGHTS = (1.0, 1.0, 1.0)
DEFAULT_CANDIDATE_LIMIT = 30


@dataclass
class _Aggregate:
    candidate: RankedCandidate
    fusion_score: float = 0.0
    best_rank: int = field(init=False)
    contributing_queries: list[QueryStrategy] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.best_rank = self.candidate.rank


def _reference_key(candidate: RankedCandidate) -> tuple[object, ...]:
    reference = candidate.reference
    return (
        reference.source_record_id,
        reference.korean_text,
        reference.translated_text,
        reference.target_language,
        reference.eps_language_code,
        reference.source_page,
        reference.dataset_revision,
        reference.content_hash,
        reference.quality_status,
        reference.source,
        reference.source_url,
    )


def _effective_weights(
    ranking_count: int,
    weights: Sequence[float],
) -> tuple[float, ...]:
    supplied = tuple(weights)
    if ranking_count == 0:
        return ()
    if len(supplied) == ranking_count:
        return supplied
    if supplied == DEFAULT_RRF_WEIGHTS and ranking_count < len(DEFAULT_RRF_WEIGHTS):
        return DEFAULT_RRF_WEIGHTS[:ranking_count]
    raise ValueError("weights must contain one value per query ranking")


def fuse_query_rankings(
    rankings: Sequence[PerQueryRanking],
    *,
    rrf_k: int = DEFAULT_RRF_K,
    weights: Sequence[float] = DEFAULT_RRF_WEIGHTS,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> tuple[FusedCandidate, ...]:
    """Fuse query rankings with deterministic, point-ID keyed reciprocal rank fusion."""

    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int) or rrf_k <= 0:
        raise ValueError("rrf_k must be a positive integer")
    if (
        isinstance(candidate_limit, bool)
        or not isinstance(candidate_limit, int)
        or candidate_limit < 0
    ):
        raise ValueError("candidate_limit must be a non-negative integer")

    effective_weights = _effective_weights(len(rankings), weights)
    if any(not math.isfinite(weight) or weight < 0 for weight in effective_weights):
        raise ValueError("weights must be finite and non-negative")

    aggregates: dict[str, _Aggregate] = {}
    for ranking, weight in zip(rankings, effective_weights, strict=True):
        best_by_point: dict[str, RankedCandidate] = {}
        for candidate in ranking.candidates:
            point_id = candidate.reference.point_id
            previous = best_by_point.get(point_id)
            if previous is None or (candidate.rank, _reference_key(candidate)) < (
                previous.rank,
                _reference_key(previous),
            ):
                best_by_point[point_id] = candidate

        for candidate in best_by_point.values():
            point_id = candidate.reference.point_id
            aggregate = aggregates.get(point_id)
            if aggregate is None:
                aggregate = _Aggregate(candidate=candidate)
                aggregates[point_id] = aggregate
            contribution = weight / (rrf_k + candidate.rank)
            aggregate.fusion_score += contribution
            if ranking.query_kind not in aggregate.contributing_queries:
                aggregate.contributing_queries.append(ranking.query_kind)
            if (candidate.rank, _reference_key(candidate)) < (
                aggregate.best_rank,
                _reference_key(aggregate.candidate),
            ):
                aggregate.best_rank = candidate.rank
                aggregate.candidate = candidate

    ordered = sorted(
        aggregates.items(),
        key=lambda item: (-item[1].fusion_score, item[1].best_rank, item[0]),
    )
    return tuple(
        FusedCandidate(
            reference=aggregate.candidate.reference,
            fusion_score=aggregate.fusion_score,
            best_rank=aggregate.best_rank,
            contributing_queries=tuple(aggregate.contributing_queries),
        )
        for _, aggregate in ordered[:candidate_limit]
    )


cross_query_rrf = fuse_query_rankings
fuse_rankings = fuse_query_rankings


__all__ = [
    "DEFAULT_CANDIDATE_LIMIT",
    "DEFAULT_RRF_K",
    "DEFAULT_RRF_WEIGHTS",
    "cross_query_rrf",
    "fuse_query_rankings",
    "fuse_rankings",
]
