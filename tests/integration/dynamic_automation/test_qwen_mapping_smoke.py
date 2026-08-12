from __future__ import annotations

import socket
from pathlib import Path

import pytest

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.config import DynamicAutomationSettings
from app.documents.dynamic_automation.models import DocumentFieldContext
from app.documents.dynamic_automation.qwen import (
    Qwen3CandidateReranker,
    Qwen3EmbeddingRetriever,
)


@pytest.mark.language_models
def test_qwen_mapping_models_run_from_pinned_local_cache_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = DynamicAutomationSettings(_env_file=None)
    embedding_path = settings.dynamic_automation_embedding_model_path
    reranker_path = settings.dynamic_automation_reranker_model_path
    assert embedding_path is not None
    assert reranker_path is not None
    if not embedding_path.is_dir() or not reranker_path.is_dir():
        pytest.skip("pinned Qwen3 mapping model cache is not provisioned")

    def reject_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Qwen3 mapping smoke attempted outbound network access")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    catalog_path = (
        Path(__file__).parents[3]
        / "app"
        / "documents"
        / "dynamic_automation"
        / "resources"
        / "canonical_fields.v1.yaml"
    )
    catalog = CanonicalCatalog.load(catalog_path)
    context = DocumentFieldContext(
        field_id="field-1",
        label="회사 연락처",
        normalized_label="회사 연락처",
        field_type="phone",
        document_title="통합신청서",
        section="현재 근무처",
        row_labels=("현재 근무처", "연락처"),
        nearby_labels=("회사명",),
        options=(),
        repeat_index=0,
        required=True,
        kind="text_field",
    )
    candidates = catalog.compatible(context)

    retrieved = Qwen3EmbeddingRetriever(embedding_path).retrieve(
        context,
        candidates,
        top_k=2,
    )
    definitions_by_id = {definition.field_id: definition for definition in candidates}
    reranked = Qwen3CandidateReranker(
        reranker_path,
        definition_resolver=definitions_by_id.__getitem__,
    ).rerank(context, retrieved)

    assert len(retrieved) == 2
    assert len(reranked) == 2
    assert all(0 <= candidate.score <= 1 for candidate in reranked)
