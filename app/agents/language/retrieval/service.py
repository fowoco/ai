from collections.abc import Sequence

from app.agents.language.contracts import (
    SupportedLanguage,
    WarningCode,
    WarningItem,
)
from app.agents.language.ports import (
    CandidateReranker,
    DenseSparseEncoder,
    EpsRetriever,
    HybridSearchStore,
)
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.fusion import fuse_query_rankings
from app.agents.language.retrieval.models import (
    ExpectedIndexContract,
    FusionSelectedContext,
    RerankerSelectedContext,
    RetrievalResult,
    SelectedContext,
)


class HybridEpsRetriever(EpsRetriever):
    def __init__(
        self,
        *,
        encoder: DenseSparseEncoder,
        store: HybridSearchStore,
        reranker: CandidateReranker | None = None,
        expected_index_contract: ExpectedIndexContract,
    ) -> None:
        self.encoder = encoder
        self.store = store
        self.reranker = reranker
        self.expected_index_contract = expected_index_contract

    def retrieve(
        self,
        *,
        queries: Sequence[SearchQuery],
        standard_korean_text: str,
        target_language: SupportedLanguage,
    ) -> RetrievalResult:
        query_kinds = tuple(q.kind for q in queries)
        warnings: list[WarningItem] = []
        degraded: list[str] = []

        # 1. Verify store contract
        try:
            handle = self.store.verify_contract(
                expected=self.expected_index_contract
            )
        except ValueError as err:
            err_msg = str(err)
            if "RETRIEVAL_DATASET_MISMATCH" in err_msg:
                code = WarningCode.RETRIEVAL_DATASET_MISMATCH
            elif "RETRIEVAL_INDEX_PROVENANCE_MISMATCH" in err_msg:
                code = WarningCode.RETRIEVAL_INDEX_PROVENANCE_MISMATCH
            elif "RETRIEVAL_SCHEMA_MISMATCH" in err_msg:
                code = WarningCode.RETRIEVAL_SCHEMA_MISMATCH
            else:
                code = WarningCode.RETRIEVAL_UNAVAILABLE

            warnings.append(
                WarningItem(
                    component="retrieval",
                    code=code,
                    message=f"Contract verification failed: {err}",
                )
            )
            degraded.append("retrieval_store")
            return RetrievalResult(
                dataset_version=None,
                query_strategies=query_kinds,
                contexts=(),
                warnings=tuple(warnings),
                fallback_used=True,
                degraded_components=tuple(degraded),
            )
        except Exception as err:
            warnings.append(
                WarningItem(
                    component="retrieval",
                    code=WarningCode.RETRIEVAL_UNAVAILABLE,
                    message=f"Qdrant connection failed: {err}",
                )
            )
            degraded.append("retrieval_store")
            return RetrievalResult(
                dataset_version=None,
                query_strategies=query_kinds,
                contexts=(),
                warnings=tuple(warnings),
                fallback_used=True,
                degraded_components=tuple(degraded),
            )

        # 2. Encode queries
        try:
            vectors = self.encoder.encode_queries(
                tuple(q.text for q in queries)
            )
        except ValueError as err:
            if "RETRIEVAL_QUERY_TOO_LONG" in str(err):
                code = WarningCode.RETRIEVAL_QUERY_TOO_LONG
            else:
                code = WarningCode.RETRIEVAL_ENCODER_UNAVAILABLE
            warnings.append(
                WarningItem(
                    component="retrieval",
                    code=code,
                    message=f"Encoder failed: {err}",
                )
            )
            degraded.append("encoder")
            return RetrievalResult(
                dataset_version=handle.dataset_version,
                query_strategies=query_kinds,
                contexts=(),
                warnings=tuple(warnings),
                fallback_used=True,
                degraded_components=tuple(degraded),
            )
        except Exception as err:
            warnings.append(
                WarningItem(
                    component="retrieval",
                    code=WarningCode.RETRIEVAL_ENCODER_UNAVAILABLE,
                    message=f"Encoder failed: {err}",
                )
            )
            degraded.append("encoder")
            return RetrievalResult(
                dataset_version=handle.dataset_version,
                query_strategies=query_kinds,
                contexts=(),
                warnings=tuple(warnings),
                fallback_used=True,
                degraded_components=tuple(degraded),
            )

        # 3. Search store
        try:
            query_pairs = tuple(
                (q, vec) for q, vec in zip(queries, vectors, strict=True)
            )
            rankings = self.store.search_many(
                query_pairs,
                target_language=target_language,
                collection=handle,
            )
        except Exception as err:
            warnings.append(
                WarningItem(
                    component="retrieval",
                    code=WarningCode.RETRIEVAL_UNAVAILABLE,
                    message=f"Search failed: {err}",
                )
            )
            degraded.append("retrieval_store")
            return RetrievalResult(
                dataset_version=handle.dataset_version,
                query_strategies=query_kinds,
                contexts=(),
                warnings=tuple(warnings),
                fallback_used=True,
                degraded_components=tuple(degraded),
            )

        # 4. Fuse rankings
        fused = fuse_query_rankings(rankings)
        if not fused:
            warnings.append(
                WarningItem(
                    component="retrieval",
                    code=WarningCode.RETRIEVAL_NO_MATCH,
                    message="No matching candidates found",
                )
            )
            return RetrievalResult(
                dataset_version=handle.dataset_version,
                query_strategies=query_kinds,
                contexts=(),
                warnings=tuple(warnings),
                fallback_used=True,
                degraded_components=(),
            )

        # 5. Rerank or cross-query fallback
        selected_contexts: list[SelectedContext] = []
        if self.reranker is not None:
            try:
                reranked = self.reranker.rerank(
                    standard_korean_text, fused[:30]
                )
                for rank, rc in enumerate(reranked[:5]):
                    selected_contexts.append(
                        RerankerSelectedContext(
                            reference=rc.reference,
                            fusion_score=rc.fusion_score,
                            reranker_score=rc.reranker_score,
                            selection_rank=rank,
                            selected_by="reranker",
                        )
                    )
            except Exception as err:
                warnings.append(
                    WarningItem(
                        component="retrieval",
                        code=WarningCode.RERANKER_UNAVAILABLE,
                        message=f"Reranker failed: {err}",
                    )
                )
                degraded.append("reranker")
                for rank, fc in enumerate(fused[:5]):
                    selected_contexts.append(
                        FusionSelectedContext(
                            reference=fc.reference,
                            fusion_score=fc.fusion_score,
                            reranker_score=None,
                            selection_rank=rank,
                            selected_by="cross_query_rrf",
                        )
                    )
        else:
            for rank, fc in enumerate(fused[:5]):
                selected_contexts.append(
                    FusionSelectedContext(
                        reference=fc.reference,
                        fusion_score=fc.fusion_score,
                        reranker_score=None,
                        selection_rank=rank,
                        selected_by="cross_query_rrf",
                    )
                )

        return RetrievalResult(
            dataset_version=handle.dataset_version,
            query_strategies=query_kinds,
            contexts=tuple(selected_contexts),
            warnings=tuple(warnings),
            fallback_used=len(degraded) > 0,
            degraded_components=tuple(degraded),
        )
