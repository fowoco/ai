from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.documents.dynamic_automation.models import (
    CanonicalFieldDefinition,
    CanonicalSource,
    DocumentFieldContext,
    ScoredCandidate,
)
from app.documents.dynamic_automation.qwen import (
    QWEN3_EMBEDDING_REPO,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_REPO,
    QWEN3_RERANKER_REVISION,
    LocalQwen3RerankerBackend,
    LocalSentenceTransformerBackend,
    Qwen3CandidateReranker,
    Qwen3EmbeddingRetriever,
)

COMPANY_PHONE_CONTEXT = DocumentFieldContext(
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


def definition(
    field_id: str,
    *,
    entity: str,
    description: str,
) -> CanonicalFieldDefinition:
    return CanonicalFieldDefinition(
        field_id=field_id,
        entity=entity,
        value_type="phone",
        aliases=(field_id.replace(".", " "),),
        description=description,
        compatible_field_types=("phone", "text"),
        source=CanonicalSource(
            view=f"document_{entity}_view",
            column="phone",
            scope_keys=("tenant_id", "company_id")
            if entity == "company"
            else ("tenant_id", "worker_id"),
        ),
        sensitivity="business" if entity == "company" else "personal",
        formatter="phone",
    )


CANDIDATE_DEFINITIONS = (
    definition(
        "worker.phone",
        entity="worker",
        description="Worker's phone number.",
    ),
    definition(
        "company.phone",
        entity="company",
        description="Company's contact telephone number.",
    ),
)
CANDIDATES = (
    ScoredCandidate(canonical_field_id="worker.phone", score=0.8, rank=1),
    ScoredCandidate(canonical_field_id="company.phone", score=0.7, rank=2),
)


class RecordingEmbeddingBackend:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.documents: list[str] = []
        self.calls: list[tuple[int, int]] = []

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        self.queries.extend(texts)
        self.calls.append((max_length, batch_size))
        return ((1.0, 0.0),)

    def encode_documents(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        self.documents.extend(texts)
        self.calls.append((max_length, batch_size))
        return ((0.0, 1.0), (1.0, 0.0))


class FakeLogitBackend:
    def __init__(self, scores: tuple[float, ...]) -> None:
        self.scores = scores
        self.pairs: list[tuple[str, str]] = []
        self.calls: list[tuple[int, int]] = []

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[float, ...]:
        self.pairs.extend(pairs)
        self.calls.append((max_length, batch_size))
        return self.scores


def test_embedding_query_includes_instruction_and_structural_context() -> None:
    backend = RecordingEmbeddingBackend()
    retriever = Qwen3EmbeddingRetriever(backend=backend)

    retriever.retrieve(COMPANY_PHONE_CONTEXT, CANDIDATE_DEFINITIONS, top_k=2)

    assert "회사 연락처 canonical field를 찾으세요" in backend.queries[0]
    assert "현재 근무처" in backend.queries[0]
    assert "통합신청서" in backend.queries[0]


def test_embedding_batches_candidates_and_returns_bounded_ranked_scores() -> None:
    backend = RecordingEmbeddingBackend()
    retriever = Qwen3EmbeddingRetriever(backend=backend, max_length=512, batch_size=8)

    ranked = retriever.retrieve(COMPANY_PHONE_CONTEXT, CANDIDATE_DEFINITIONS, top_k=1)

    assert len(backend.documents) == 2
    assert "company.phone" in backend.documents[1]
    assert backend.calls == [(512, 8), (512, 8)]
    assert [(item.canonical_field_id, item.rank) for item in ranked] == [
        ("company.phone", 1)
    ]
    assert ranked[0].score == pytest.approx(1.0)


def test_reranker_uses_yes_no_probability_and_returns_zero_to_one() -> None:
    backend = FakeLogitBackend(scores=(0.8, 0.2))
    reranker = Qwen3CandidateReranker(backend=backend)

    ranked = reranker.rerank(COMPANY_PHONE_CONTEXT, CANDIDATES)

    assert ranked[0].canonical_field_id == "worker.phone"
    assert ranked[0].score == pytest.approx(0.8)
    assert ranked[1].score == pytest.approx(0.2)
    assert all(0 <= item.score <= 1 for item in ranked)


def test_reranker_batches_structural_query_and_canonical_ids_at_512_tokens() -> None:
    backend = FakeLogitBackend(scores=(0.2, 0.9))
    reranker = Qwen3CandidateReranker(backend=backend, max_length=512, batch_size=4)

    ranked = reranker.rerank(COMPANY_PHONE_CONTEXT, CANDIDATES)

    assert len(backend.pairs) == 2
    assert "현재 근무처" in backend.pairs[0][0]
    assert backend.pairs[1][1] == "company.phone"
    assert backend.calls == [(512, 4)]
    assert [item.canonical_field_id for item in ranked] == [
        "company.phone",
        "worker.phone",
    ]
    assert [item.rank for item in ranked] == [1, 2]


def test_adapters_report_pinned_model_versions() -> None:
    assert Qwen3EmbeddingRetriever(backend=RecordingEmbeddingBackend()).model_version == (
        f"{QWEN3_EMBEDDING_REPO}@{QWEN3_EMBEDDING_REVISION}"
    )
    assert Qwen3CandidateReranker(backend=FakeLogitBackend(())).model_version == (
        f"{QWEN3_RERANKER_REPO}@{QWEN3_RERANKER_REVISION}"
    )


@pytest.mark.parametrize(
    ("adapter_type", "cache_name", "revision"),
    [
        (
            Qwen3EmbeddingRetriever,
            "qwen3-embedding-0.6b",
            QWEN3_EMBEDDING_REVISION,
        ),
        (
            Qwen3CandidateReranker,
            "qwen3-reranker-0.6b",
            QWEN3_RERANKER_REVISION,
        ),
    ],
)
def test_real_adapters_require_an_explicit_pinned_cache_path(
    adapter_type: type[Qwen3EmbeddingRetriever] | type[Qwen3CandidateReranker],
    cache_name: str,
    revision: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="pinned model cache path is required"):
        adapter_type()

    with pytest.raises(ValueError, match="absolute local path"):
        adapter_type("Qwen/repository-id")

    with pytest.raises(ValueError, match="pinned revision directory"):
        adapter_type(tmp_path / "wrong-model" / "unversioned")

    adapter_type(tmp_path / cache_name / revision)


def test_fake_backends_do_not_require_a_model_path() -> None:
    Qwen3EmbeddingRetriever(backend=RecordingEmbeddingBackend())
    Qwen3CandidateReranker(backend=FakeLogitBackend(()))


def test_sentence_transformer_backend_is_lazy_and_local_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    constructor_calls: list[tuple[str, dict[str, Any]]] = []

    class FakeSentenceTransformer:
        max_seq_length = 0

        def __init__(self, model_path: str, **kwargs: Any) -> None:
            constructor_calls.append((model_path, kwargs))

        def encode(self, texts: Sequence[str], **kwargs: Any) -> list[list[float]]:
            assert list(texts) == ["query"]
            assert kwargs["batch_size"] == 3
            assert kwargs["normalize_embeddings"] is True
            return [[1.0, 0.0]]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    model_path = tmp_path / "embedding"
    backend = LocalSentenceTransformerBackend(model_path)
    assert constructor_calls == []

    vectors = backend.encode_queries(("query",), max_length=512, batch_size=3)

    assert vectors == ((1.0, 0.0),)
    assert constructor_calls == [(str(model_path), {"local_files_only": True})]


def test_reranker_backend_loads_local_only_and_normalizes_yes_no_logits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    load_calls: list[tuple[str, str, dict[str, Any]]] = []
    model_calls = 0
    inference_mode_active = False

    class FakeInferenceMode:
        def __enter__(self) -> None:
            nonlocal inference_mode_active
            inference_mode_active = True

        def __exit__(self, *args: object) -> None:
            nonlocal inference_mode_active
            inference_mode_active = False

    class FakeLastTokenLogits:
        def __getitem__(self, key: Any) -> FakeLastTokenLogits:
            assert key == (slice(None), -1, slice(None))
            return self

        def detach(self) -> FakeLastTokenLogits:
            return self

        def cpu(self) -> FakeLastTokenLogits:
            return self

        def tolist(self) -> list[list[float]]:
            row = [0.0] * 8
            row[5] = 2.0
            row[7] = 0.0
            return [row]

    class FakeTokenizer:
        padding_side = "right"
        pad_token = None
        eos_token = "<eos>"

        def convert_tokens_to_ids(self, token: str) -> int:
            return {"yes": 5, "no": 7}[token]

        def encode(self, text: str, **kwargs: Any) -> list[int]:
            assert kwargs == {"add_special_tokens": False}
            if text.startswith("<|im_start|>system"):
                return [1, 2]
            assert text.startswith("<|im_end|>")
            return [6]

        def __call__(self, texts: Sequence[str], **kwargs: Any) -> dict[str, str]:
            assert len(texts) == 1
            assert kwargs["max_length"] == 509
            assert kwargs["truncation"] is True
            assert kwargs["padding"] is False
            return {"input_ids": [[3, 4]]}  # type: ignore[dict-item]

        def pad(self, inputs: dict[str, Any], **kwargs: Any) -> dict[str, str]:
            assert inputs == {"input_ids": [[1, 2, 3, 4, 6]]}
            assert kwargs["padding"] is True
            assert kwargs["max_length"] == 512
            return {"input_ids": "fake-inputs"}

    tokenizer = FakeTokenizer()

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(model_path: str, **kwargs: Any) -> FakeTokenizer:
            load_calls.append(("tokenizer", model_path, kwargs))
            return tokenizer

    class FakeModel:
        def eval(self) -> FakeModel:
            return self

        def __call__(self, **inputs: Any) -> SimpleNamespace:
            nonlocal model_calls
            assert inference_mode_active is True
            assert inputs == {"input_ids": "fake-inputs"}
            model_calls += 1
            return SimpleNamespace(logits=FakeLastTokenLogits())

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(model_path: str, **kwargs: Any) -> FakeModel:
            load_calls.append(("model", model_path, kwargs))
            return FakeModel()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModelForCausalLM=FakeAutoModel,
            AutoTokenizer=FakeAutoTokenizer,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(inference_mode=FakeInferenceMode),
    )
    model_path = tmp_path / "reranker"
    backend = LocalQwen3RerankerBackend(model_path)
    assert load_calls == []

    scores = backend.score_pairs(
        (
            ("회사 연락처", "company.phone"),
            ("근로자 연락처", "worker.phone"),
        ),
        max_length=512,
        batch_size=1,
    )

    assert scores == pytest.approx((0.8807970779, 0.8807970779))
    assert model_calls == 2
    assert load_calls == [
        ("tokenizer", str(model_path), {"local_files_only": True}),
        ("model", str(model_path), {"local_files_only": True}),
    ]
    assert tokenizer.padding_side == "left"
    assert tokenizer.pad_token == tokenizer.eos_token
