from collections.abc import Sequence
from typing import Any

import pytest

from app.agents.language.contracts import WarningCode
from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.encoder import (
    BGEM3Backend,
    BgeM3Encoder,
    FlagEmbeddingBgeM3Backend,
    RawBgeBatch,
)
from app.agents.language.retrieval.models import (
    EpsReference,
    ExpectedIndexContract,
    HybridVector,
    PerQueryRanking,
    RankedCandidate,
    VerifiedCollectionHandle,
)
from app.agents.language.retrieval.reranker import LocalCandidateReranker, RerankerBackend
from app.agents.language.retrieval.service import HybridEpsRetriever


class FakeBGEM3Backend(BGEM3Backend):
    def __init__(self, fail: bool = False, max_token_limit: int = 128) -> None:
        self.fail = fail
        self.max_token_limit = max_token_limit
        self.call_count = 0

    def token_count(self, text: str) -> int:
        if "too_long" in text:
            return 200
        return len(text.split())

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int = 128,
        return_dense: bool = True,
        return_sparse: bool = True,
        return_colbert_vecs: bool = False,
    ) -> RawBgeBatch:
        self.call_count += 1
        if self.fail:
            raise RuntimeError("Fake BGE-M3 backend failure")
        dense = tuple(tuple(0.1 for _ in range(1024)) for _ in texts)
        sparse = tuple({1: 0.5, 10: 0.8} for _ in texts)
        return RawBgeBatch(dense_vectors=dense, lexical_weights=sparse)


class FakeSearchStore:
    def __init__(
        self,
        fail: bool = False,
        mismatch_dataset: bool = False,
        mismatch_provenance: bool = False,
        mismatch_schema: bool = False,
        empty_result: bool = False,
    ) -> None:
        self.fail = fail
        self.mismatch_dataset = mismatch_dataset
        self.mismatch_provenance = mismatch_provenance
        self.mismatch_schema = mismatch_schema
        self.empty_result = empty_result

    def verify_contract(
        self, *, expected: ExpectedIndexContract
    ) -> VerifiedCollectionHandle:
        if self.fail:
            raise RuntimeError("Qdrant store connection failed")
        if self.mismatch_dataset:
            raise ValueError("RETRIEVAL_DATASET_MISMATCH")
        if self.mismatch_provenance:
            raise ValueError("RETRIEVAL_INDEX_PROVENANCE_MISMATCH")
        if self.mismatch_schema:
            raise ValueError("RETRIEVAL_SCHEMA_MISMATCH")

        return VerifiedCollectionHandle(
            collection_name="eps_language_phrases_29106c33d43c_5617a9f61b02",
            dataset_version=expected.dataset_revision,
            embedding_model_repo="BAAI/bge-m3",
            embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
            index_contract_version="eps-language-index-v1",
            point_count=100,
        )

    def search_many(
        self,
        queries: Sequence[tuple[SearchQuery, HybridVector]],
        *,
        target_language: str,
        collection: VerifiedCollectionHandle,
    ) -> tuple[PerQueryRanking, ...]:
        if self.fail:
            raise RuntimeError("Qdrant search failed")
        if self.empty_result:
            return tuple(
                PerQueryRanking(query_kind=q[0].kind, candidates=()) for q in queries
            )

        rankings = []
        for q, _ in queries:
            ref = EpsReference(
                point_id="p1",
                source_record_id="p1",
                korean_text="고맙습니다.",
                translated_text="Thank you",
                target_language="en",
                eps_language_code="01",
                source_page=1,
                dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
                content_hash="ch1",
                quality_status="verified",
                source="EPS",
                source_url="https://eps.go.kr",
            )
            candidate = RankedCandidate(reference=ref, rank=0, score=0.9)
            rankings.append(
                PerQueryRanking(query_kind=q.kind, candidates=(candidate,))
            )
        return tuple(rankings)


class FakeRerankerBackend(RerankerBackend):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, Sequence[str]]] = []

    def compute_scores(
        self, pairs: Sequence[tuple[str, str]], max_length: int = 256
    ) -> tuple[float, ...]:
        if self.fail:
            raise RuntimeError("Fake reranker failure")
        self.calls.append(("rerank", [p[1] for p in pairs]))
        return tuple(0.85 - 0.01 * i for i in range(len(pairs)))


@pytest.fixture
def expected_contract() -> ExpectedIndexContract:
    return ExpectedIndexContract(
        dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=100,
    )


def test_encoder_batches_all_three_queries_once() -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend)
    res = encoder.encode_queries(["q1", "q2", "q3"])
    assert len(res) == 3
    assert backend.call_count == 1


def test_flag_embedding_backend_converts_dense_and_lexical_weights() -> None:
    class FakeTokenizer:
        def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
            assert text == "고맙습니다"
            assert add_special_tokens is True
            return [1, 2, 3]

    class FakeFlagModel:
        tokenizer = FakeTokenizer()

        def encode(self, texts: Sequence[str], **kwargs: object) -> dict[str, object]:
            assert tuple(texts) == ("고맙습니다",)
            assert kwargs == {
                "max_length": 128,
                "return_dense": True,
                "return_sparse": True,
                "return_colbert_vecs": False,
            }
            return {
                "dense_vecs": [[0.1] * 1024],
                "lexical_weights": [{"9": 0.2, "1": 0.5}],
            }

    backend = FlagEmbeddingBgeM3Backend("/models/bge-m3")
    backend._model = FakeFlagModel()

    assert backend.token_count("고맙습니다") == 3
    result = backend.encode_queries(("고맙습니다",))

    assert len(result.dense_vectors[0]) == 1024
    assert result.lexical_weights[0] == {9: 0.2, 1: 0.5}


def test_encoder_requests_dense_and_sparse_only() -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend)
    res = encoder.encode_queries(["test"])
    assert len(res[0].dense) == 1024
    assert len(res[0].sparse_indices) > 0


def test_encoder_uses_max_length_128() -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend, max_length=128)
    assert encoder.max_length == 128


def test_encoder_rejects_over_128_tokens_without_truncating() -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend, max_length=128)
    with pytest.raises(ValueError, match="RETRIEVAL_QUERY_TOO_LONG"):
        encoder.encode_queries(["too_long query sentence"])


def test_encoder_returns_1024_dense_dimensions() -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend)
    vecs = encoder.encode_queries(["query"])
    assert len(vecs[0].dense) == 1024


def test_encoder_sorts_sparse_token_ids() -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend)
    vecs = encoder.encode_queries(["query"])
    assert list(vecs[0].sparse_indices) == sorted(vecs[0].sparse_indices)


def test_encoder_rejects_nan_or_infinite_values() -> None:
    class BadBackend(FakeBGEM3Backend):
        def encode_queries(self, *args: Any, **kwargs: Any) -> RawBgeBatch:
            return RawBgeBatch(
                dense_vectors=((float("nan"),) * 1024,),
                lexical_weights=({1: 1.0},),
            )

    encoder = BgeM3Encoder(backend=BadBackend())
    with pytest.raises(ValueError):
        encoder.encode_queries(["q"])


def test_success_returns_five_contexts(expected_contract: ExpectedIndexContract) -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend)
    store = FakeSearchStore()
    reranker_backend = FakeRerankerBackend()
    reranker = LocalCandidateReranker(backend=reranker_backend)

    retriever = HybridEpsRetriever(
        encoder=encoder,
        store=store,
        reranker=reranker,
        expected_index_contract=expected_contract,
    )

    queries = [
        SearchQuery(kind="canonical", text="고맙습니다."),
        SearchQuery(kind="reason_items", text="감사 표명"),
        SearchQuery(kind="action_deadline", text="감사 2026-08-04"),
    ]

    res = retriever.retrieve(
        queries=queries,
        standard_korean_text="고맙습니다.",
        target_language="en",
    )

    assert res.fallback_used is False
    assert len(res.contexts) > 0
    assert res.contexts[0].selected_by == "reranker"


def test_no_match_returns_empty_context_and_no_match_warning(
    expected_contract: ExpectedIndexContract,
) -> None:
    backend = FakeBGEM3Backend()
    encoder = BgeM3Encoder(backend=backend)
    store = FakeSearchStore(empty_result=True)
    reranker = LocalCandidateReranker(backend=FakeRerankerBackend())

    retriever = HybridEpsRetriever(
        encoder=encoder,
        store=store,
        reranker=reranker,
        expected_index_contract=expected_contract,
    )

    queries = [SearchQuery(kind="canonical", text="고맙습니다.")]
    res = retriever.retrieve(
        queries=queries, standard_korean_text="고맙습니다.", target_language="en"
    )

    assert len(res.contexts) == 0
    assert any(w.code == WarningCode.RETRIEVAL_NO_MATCH for w in res.warnings)


def test_qdrant_failure_returns_empty_context_and_unavailable_warning(
    expected_contract: ExpectedIndexContract,
) -> None:
    encoder = BgeM3Encoder(backend=FakeBGEM3Backend())
    store = FakeSearchStore(fail=True)
    reranker = LocalCandidateReranker(backend=FakeRerankerBackend())

    retriever = HybridEpsRetriever(
        encoder=encoder,
        store=store,
        reranker=reranker,
        expected_index_contract=expected_contract,
    )

    queries = [SearchQuery(kind="canonical", text="고맙습니다.")]
    res = retriever.retrieve(
        queries=queries, standard_korean_text="고맙습니다.", target_language="en"
    )

    assert len(res.contexts) == 0
    assert res.fallback_used is True
    assert any(w.code == WarningCode.RETRIEVAL_UNAVAILABLE for w in res.warnings)


def test_encoder_failure_returns_empty_context_and_encoder_warning(
    expected_contract: ExpectedIndexContract,
) -> None:
    encoder = BgeM3Encoder(backend=FakeBGEM3Backend(fail=True))
    store = FakeSearchStore()
    reranker = LocalCandidateReranker(backend=FakeRerankerBackend())

    retriever = HybridEpsRetriever(
        encoder=encoder,
        store=store,
        reranker=reranker,
        expected_index_contract=expected_contract,
    )

    queries = [SearchQuery(kind="canonical", text="고맙습니다.")]
    res = retriever.retrieve(
        queries=queries, standard_korean_text="고맙습니다.", target_language="en"
    )

    assert len(res.contexts) == 0
    assert any(
        w.code == WarningCode.RETRIEVAL_ENCODER_UNAVAILABLE for w in res.warnings
    )


def test_query_too_long_returns_empty_context_without_truncation(
    expected_contract: ExpectedIndexContract,
) -> None:
    encoder = BgeM3Encoder(backend=FakeBGEM3Backend())
    store = FakeSearchStore()
    reranker = LocalCandidateReranker(backend=FakeRerankerBackend())

    retriever = HybridEpsRetriever(
        encoder=encoder,
        store=store,
        reranker=reranker,
        expected_index_contract=expected_contract,
    )

    queries = [SearchQuery(kind="canonical", text="too_long text query")]
    res = retriever.retrieve(
        queries=queries, standard_korean_text="고맙습니다.", target_language="en"
    )

    assert len(res.contexts) == 0
    assert any(
        w.code == WarningCode.RETRIEVAL_QUERY_TOO_LONG for w in res.warnings
    )


def test_reranker_failure_uses_cross_query_order(
    expected_contract: ExpectedIndexContract,
) -> None:
    encoder = BgeM3Encoder(backend=FakeBGEM3Backend())
    store = FakeSearchStore()
    reranker = LocalCandidateReranker(backend=FakeRerankerBackend(fail=True))

    retriever = HybridEpsRetriever(
        encoder=encoder,
        store=store,
        reranker=reranker,
        expected_index_contract=expected_contract,
    )

    queries = [SearchQuery(kind="canonical", text="고맙습니다.")]
    res = retriever.retrieve(
        queries=queries, standard_korean_text="고맙습니다.", target_language="en"
    )

    assert len(res.contexts) > 0
    assert res.contexts[0].selected_by == "cross_query_rrf"
    assert any(w.code == WarningCode.RERANKER_UNAVAILABLE for w in res.warnings)
