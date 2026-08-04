from unittest.mock import MagicMock

import pytest

from app.agents.language.queries import SearchQuery
from app.agents.language.retrieval.models import ExpectedIndexContract, HybridVector
from app.agents.language.retrieval.qdrant_store import QdrantStore


@pytest.fixture
def expected_contract() -> ExpectedIndexContract:
    return ExpectedIndexContract(
        dataset_revision="sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d",
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=100,
    )


def test_real_store_mock_create_and_verify(
    expected_contract: ExpectedIndexContract,
) -> None:
    mock_client = MagicMock()
    mock_client.get_aliases.return_value.aliases = [
        MagicMock(
            alias_name="eps_language_phrases",
            collection_name="eps_language_phrases_29106c33d43c_5617a9f61b02",
        )
    ]
    mock_client.get_collection.return_value.points_count = 100
    dense_param = MagicMock()
    dense_param.size = 1024
    try:
        from qdrant_client import models as qmodels
        cosine_dist = qmodels.Distance.COSINE
    except ImportError:
        cosine_dist = "COSINE"

    dense_param.distance = cosine_dist

    mock_client.get_collection.return_value.config.params.vectors = {
        "korean_dense": dense_param
    }
    mock_client.get_collection.return_value.config.params.sparse_vectors = {
        "korean_sparse": MagicMock()
    }

    mock_client.count.return_value.count = 100

    store = QdrantStore(client=mock_client)
    handle = store.verify_contract(expected=expected_contract)
    assert handle.collection_name == "eps_language_phrases_29106c33d43c_5617a9f61b02"


def test_real_store_mock_search_many(
    expected_contract: ExpectedIndexContract,
) -> None:
    mock_client = MagicMock()
    mock_pt = MagicMock()
    mock_pt.id = "p1"
    mock_pt.score = 0.95
    mock_pt.payload = {
        "source_record_id": "p1",
        "korean_text": "고맙습니다.",
        "translated_text": "Thank you",
        "target_language": "en",
        "eps_language_code": "01",
        "source_page": 1,
        "dataset_revision": expected_contract.dataset_revision,
        "content_hash": "ch1",
        "quality_status": "verified",
        "source": "EPS",
        "source_url": "https://eps.go.kr",
    }
    mock_batch_res = MagicMock()
    mock_batch_res.points = [mock_pt]
    mock_client.query_batch_points.return_value = [mock_batch_res]

    store = QdrantStore(client=mock_client)

    from app.agents.language.retrieval.models import VerifiedCollectionHandle

    handle = VerifiedCollectionHandle(
        collection_name="eps_language_phrases_29106c33d43c_5617a9f61b02",
        dataset_version=expected_contract.dataset_revision,
        embedding_model_repo="BAAI/bge-m3",
        embedding_model_revision="5617a9f61b028005a4858fdac845db406aefb181",
        index_contract_version="eps-language-index-v1",
        point_count=100,
    )

    vec = HybridVector(
        dense=tuple(0.1 for _ in range(1024)),
        sparse_indices=(1, 2),
        sparse_values=(0.5, 0.8),
    )
    query = SearchQuery(kind="canonical", text="고맙습니다.")

    rankings = store.search_many([(query, vec)], target_language="en", collection=handle)
    assert len(rankings) == 1
    assert len(rankings[0].candidates) == 1
    assert rankings[0].candidates[0].reference.korean_text == "고맙습니다."
