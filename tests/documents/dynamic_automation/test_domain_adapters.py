from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.domain_adapters import (
    adapter_file_sha256,
    load_domain_embedding_retriever,
    load_domain_reranker,
)
from app.documents.dynamic_automation.feedback import MappingFeedbackRecord
from app.documents.dynamic_automation.models import DocumentFieldContext, ScoredCandidate
from app.documents.dynamic_automation.qwen import (
    QWEN3_EMBEDDING_REPO,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_REPO,
    QWEN3_RERANKER_REVISION,
)
from app.documents.dynamic_automation.training import TrainingExample, TrainingSplit
from scripts import compare_dynamic_mapping_models as comparison_cli
from scripts import train_dynamic_mapping_models as training_cli

ROOT = Path(__file__).parents[3]
CATALOG_PATH = (
    ROOT / "app/documents/dynamic_automation/resources/canonical_fields.v1.yaml"
)


class ProjectionBaseBackend:
    """Complete fixed embedding backend with deliberately wrong raw worker-name queries."""

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        del max_length, batch_size
        return tuple(
            (-1.0, 2.0) if "nationality" in text.casefold() else (0.0, 1.0)
            for text in texts
        )

    def encode_documents(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        del max_length, batch_size
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            if "worker.legal_name" in text:
                vectors.append((1.0, 0.0))
            elif "worker.nationality" in text:
                vectors.append((0.0, 1.0))
            else:
                vectors.append((-1.0, 0.0))
        return tuple(vectors)


class CalibrationBaseBackend:
    def score_pairs(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[float, ...]:
        del max_length, batch_size
        return tuple(0.8 if "company.phone" in definition else 0.2 for _, definition in pairs)


class ReversedCalibrationBackend:
    """Complete backend whose raw ranking is the opposite of its training labels."""

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[float, ...]:
        del max_length, batch_size
        return tuple(
            0.1 if "worker.phone" in definition else 0.9
            for _, definition in pairs
        )


def context(*, label: str = "Worker name", field_type: str = "text") -> DocumentFieldContext:
    return DocumentFieldContext(
        field_id="field-1",
        container_id="section0.table0",
        label=label,
        normalized_label=label.casefold().replace(" ", ""),
        field_type=field_type,
        document_title="Application",
        section="Worker",
        row_labels=("Worker", label),
        nearby_labels=(),
        options=(),
        repeat_index=0,
        required=True,
        kind="text_field",
    )


def write_artifact(path: Path, payload: dict[str, object]) -> str:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_embedding_projection_artifact_is_loaded_and_changes_retrieval(
    tmp_path: Path,
) -> None:
    catalog = CanonicalCatalog.load(CATALOG_PATH)
    artifact_path = tmp_path / "embedding-adapter.json"
    expected_hash = write_artifact(
        artifact_path,
        {
            "format_version": "dynamic-mapping-adapter-v2",
            "model_kind": "bi-encoder",
            "base_model_repo": QWEN3_EMBEDDING_REPO,
            "base_model_revision": QWEN3_EMBEDDING_REVISION,
            "seed": 42,
            "weights": {
                "adapter_kind": "query_bias_projection",
                "embedding_dimension": 2,
                "positive_pair_count": 1,
                "query_bias": [1.0, -1.0],
            },
        },
    )

    retriever = load_domain_embedding_retriever(
        artifact_path,
        backend=ProjectionBaseBackend(),
        expected_sha256=expected_hash,
    )
    ranked = retriever.retrieve(context(), catalog.compatible(context()), top_k=3)

    assert ranked[0].canonical_field_id == "worker.legal_name"
    assert retriever.model_version.endswith(f"@{expected_hash}")
    assert adapter_file_sha256(artifact_path) == expected_hash

    with pytest.raises(ValueError, match="SHA-256"):
        load_domain_embedding_retriever(
            artifact_path,
            backend=ProjectionBaseBackend(),
            expected_sha256="f" * 64,
        )


def test_reranker_calibration_artifact_is_loaded_through_reranker_port(
    tmp_path: Path,
) -> None:
    catalog = CanonicalCatalog.load(CATALOG_PATH)
    artifact_path = tmp_path / "reranker-adapter.json"
    expected_hash = write_artifact(
        artifact_path,
        {
            "format_version": "dynamic-mapping-adapter-v2",
            "model_kind": "pair-reranker",
            "base_model_repo": QWEN3_RERANKER_REPO,
            "base_model_revision": QWEN3_RERANKER_REVISION,
            "seed": 42,
            "weights": {
                "adapter_kind": "score_calibration",
                "positive_pair_count": 1,
                "negative_pair_count": 1,
                "scale": 2.0,
                "bias": -1.0,
            },
        },
    )
    reranker = load_domain_reranker(
        artifact_path,
        backend=CalibrationBaseBackend(),
        definition_resolver=catalog.get,
        expected_sha256=expected_hash,
    )
    candidates = (
        ScoredCandidate(canonical_field_id="worker.phone", score=0.5, rank=1),
        ScoredCandidate(canonical_field_id="company.phone", score=0.5, rank=2),
    )

    ranked = reranker.rerank(context(label="Company contact", field_type="phone"), candidates)

    assert ranked[0].canonical_field_id == "company.phone"
    assert 0 <= ranked[0].score <= 1
    assert reranker.model_version.endswith(f"@{expected_hash}")


def test_trained_reranker_calibration_can_reverse_a_wrong_base_ranking(
    tmp_path: Path,
) -> None:
    catalog = CanonicalCatalog.load(CATALOG_PATH)
    split = TrainingSplit(
        train=(
            TrainingExample(
                document_layout_hash="a" * 64,
                document_kind="application",
                document_version="v1",
                source_institution="institution-a",
                field_context_hash="b" * 64,
                field_id="worker-phone",
                repeat_index=0,
                query_text="Worker contact number",
                canonical_field_id="worker.phone",
                catalog_version="v1",
            ),
        ),
        test=(),
    )
    weights = training_cli._fit_pair_reranker(
        split,
        catalog,
        model_path=tmp_path / "unused-model",
        backend=ReversedCalibrationBackend(),
    )
    artifact_path = tmp_path / "trained-reranker-adapter.json"
    expected_hash = write_artifact(
        artifact_path,
        {
            "format_version": "dynamic-mapping-adapter-v2",
            "model_kind": "pair-reranker",
            "base_model_repo": QWEN3_RERANKER_REPO,
            "base_model_revision": QWEN3_RERANKER_REVISION,
            "seed": 42,
            "weights": weights,
        },
    )
    reranker = load_domain_reranker(
        artifact_path,
        backend=ReversedCalibrationBackend(),
        definition_resolver=catalog.get,
        expected_sha256=expected_hash,
    )

    ranked = reranker.rerank(
        context(label="Worker contact number", field_type="phone"),
        (
            ScoredCandidate(canonical_field_id="company.phone", score=0.9, rank=1),
            ScoredCandidate(canonical_field_id="worker.phone", score=0.1, rank=2),
        ),
    )

    assert weights["scale"] < 0
    assert ranked[0].canonical_field_id == "worker.phone"


def feedback_payload(*, layout_hash: str, field_id: str) -> dict[str, object]:
    return {
        "schema_version": "v2",
        "layout_hash": layout_hash,
        "document_kind": f"kind-{field_id}",
        "document_version": f"version-{field_id}",
        "source_institution": f"institution-{field_id}",
        "field_context_hash": hashlib.sha256(field_id.encode("utf-8")).hexdigest(),
        "field_id": field_id,
        "repeat_index": 0,
        "label": "Worker name",
        "section": "Worker",
        "row_labels": ["Worker", "Worker name"],
        "nearby_labels": [],
        "predicted_status": "MATCHED",
        "predicted_canonical_field_id": "worker.legal_name",
        "final_canonical_field_id": "worker.legal_name",
        "decision": "accepted",
        "candidate_scores": [
            {"canonical_field_id": "worker.legal_name", "score": 0.99, "rank": 1}
        ],
        "catalog_version": "v1",
        "model_version": "fake-base-v1",
    }


def test_fake_backend_train_export_load_evaluate_and_compare_cli(
    tmp_path: Path,
) -> None:
    feedback_path = tmp_path / "feedback.jsonl"
    records = (
        MappingFeedbackRecord.model_validate(
            feedback_payload(layout_hash="a" * 64, field_id="worker-name-a")
        ),
        MappingFeedbackRecord.model_validate(
            feedback_payload(layout_hash="b" * 64, field_id="worker-name-b")
        ),
    )
    feedback_path.write_text(
        "".join(record.model_dump_json() + "\n" for record in records),
        encoding="utf-8",
    )
    candidate_dir = tmp_path / "candidate"

    exit_code = training_cli.main(
        [
            "--feedback",
            str(feedback_path),
            "--catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(candidate_dir),
            "--seed",
            "42",
            "--model-kind",
            "bi-encoder",
        ],
        embedding_backend=ProjectionBaseBackend(),
    )

    assert exit_code == 0
    artifact_path = candidate_dir / "adapter-weights.json"
    report_path = candidate_dir / "held-out-evaluation.json"
    candidate_manifest_path = candidate_dir / "model-manifest.json"
    candidate_manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert candidate_manifest["model_artifact_sha256"] == adapter_file_sha256(
        artifact_path
    )
    assert candidate_manifest["evaluation_report_sha256"] == hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    assert report["unseen_field_evidence"]["retrieved_rank"] is not None
    assert "unseen_catalog_retrieved" not in candidate_manifest

    catalog = CanonicalCatalog.load(CATALOG_PATH)
    loaded = load_domain_embedding_retriever(
        artifact_path,
        backend=ProjectionBaseBackend(),
        expected_sha256=candidate_manifest["model_artifact_sha256"],
    )
    assert loaded.retrieve(context(), catalog.compatible(context()), top_k=3)[
        0
    ].canonical_field_id == "worker.legal_name"

    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    baseline_artifact = baseline_dir / "adapter-weights.json"
    baseline_artifact.write_bytes(artifact_path.read_bytes())
    baseline_report = json.loads(report_path.read_text(encoding="utf-8"))
    baseline_report["metrics"]["p95_latency_ms"] += 100.0
    baseline_report_path = baseline_dir / "held-out-evaluation.json"
    baseline_report_path.write_text(
        json.dumps(baseline_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    baseline_manifest = {**candidate_manifest, "model_kind": "qwen_baseline"}
    baseline_manifest["p95_latency_ms"] = baseline_report["metrics"]["p95_latency_ms"]
    baseline_manifest["evaluation_report_sha256"] = hashlib.sha256(
        baseline_report_path.read_bytes()
    ).hexdigest()
    baseline_manifest_path = baseline_dir / "model-manifest.json"
    baseline_manifest_path.write_text(
        json.dumps(baseline_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    decision_path = tmp_path / "decision.json"

    compare_exit = comparison_cli.main(
        [
            "--baseline",
            str(baseline_manifest_path),
            "--baseline-artifact",
            str(baseline_artifact),
            "--baseline-report",
            str(baseline_report_path),
            "--candidate",
            str(candidate_manifest_path),
            "--candidate-artifact",
            str(artifact_path),
            "--candidate-report",
            str(report_path),
            "--output",
            str(decision_path),
        ]
    )

    assert compare_exit == 0
    assert json.loads(decision_path.read_text(encoding="utf-8"))["promote"] is True

    report_path.write_text(report_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert comparison_cli.main(
        [
            "--baseline",
            str(baseline_manifest_path),
            "--baseline-artifact",
            str(baseline_artifact),
            "--baseline-report",
            str(baseline_report_path),
            "--candidate",
            str(candidate_manifest_path),
            "--candidate-artifact",
            str(artifact_path),
            "--candidate-report",
            str(report_path),
            "--output",
            str(decision_path),
        ]
    ) == 2
