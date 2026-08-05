import os

import pytest


@pytest.mark.language_models
def test_offline_model_revision_smoke():
    """Verify model offline contract configuration and environment flags."""
    embedding_path = os.environ.get("FOWOCO_LANGUAGE_EMBEDDING_MODEL_PATH")
    reranker_path = os.environ.get("FOWOCO_LANGUAGE_RERANKER_MODEL_PATH")

    if embedding_path:
        assert os.path.exists(embedding_path), f"Embedding path {embedding_path} missing"
    if reranker_path:
        assert os.path.exists(reranker_path), f"Reranker path {reranker_path} missing"


@pytest.mark.qdrant_integration
def test_offline_qdrant_contract_smoke():
    """Verify Qdrant integration test contract markers."""
    qdrant_url = os.environ.get("FOWOCO_QDRANT_URL", "http://127.0.0.1:16333")
    assert qdrant_url.startswith("http://") or qdrant_url.startswith("https://")
