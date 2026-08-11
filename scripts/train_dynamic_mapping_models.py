"""Build deterministic domain mapping adapters from sanitized reviewer feedback."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.documents.dynamic_automation.catalog import CanonicalCatalog  # noqa: E402
from app.documents.dynamic_automation.domain_adapters import (  # noqa: E402
    adapter_file_sha256,
    load_domain_embedding_retriever,
    load_domain_reranker,
)
from app.documents.dynamic_automation.feedback import MappingFeedbackRecord  # noqa: E402
from app.documents.dynamic_automation.models import (  # noqa: E402
    DocumentFieldContext,
    ScoredCandidate,
)
from app.documents.dynamic_automation.qwen import (  # noqa: E402
    QWEN3_EMBEDDING_CACHE_NAME,
    QWEN3_EMBEDDING_REPO,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_CACHE_NAME,
    QWEN3_RERANKER_REPO,
    QWEN3_RERANKER_REVISION,
    EmbeddingBackend,
    LocalQwen3RerankerBackend,
    LocalSentenceTransformerBackend,
    RerankerBackend,
)
from app.documents.dynamic_automation.training import (  # noqa: E402
    EVALUATION_CODE_VERSION,
    TRAINING_CODE_VERSION,
    EvaluationMetricsEvidence,
    HeldOutEvaluationReport,
    ModelManifest,
    TrainingSplit,
    UnseenFieldEvidence,
    build_hard_negatives,
    build_training_split,
    training_dataset_sha256,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    embedding_backend: EmbeddingBackend | None = None,
    reranker_backend: RerankerBackend | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feedback", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument(
        "--model-kind", required=True, choices=("bi-encoder", "pair-reranker")
    )
    args = parser.parse_args(argv)

    try:
        if args.seed < 0:
            raise ValueError("seed must be non-negative")
        records = _load_feedback(args.feedback)
        catalog = CanonicalCatalog.load(args.catalog)
        mismatched_versions = sorted(
            {
                record.catalog_version
                for record in records
                if record.catalog_version != catalog.version
            }
        )
        if mismatched_versions:
            raise ValueError(
                f"feedback catalog_version {', '.join(mismatched_versions)} "
                f"does not match loaded catalog {catalog.version}"
            )
        split = build_training_split(records)
        if not split.train:
            raise ValueError("feedback contains no reviewer-approved training labels")
        model_spec = _base_model_spec(args.model_kind)
        injected_backend = (
            embedding_backend if args.model_kind == "bi-encoder" else reranker_backend
        )
        if injected_backend is None:
            _require_local_model(
                model_spec[3], revision=model_spec[2], cache_name=model_spec[1]
            )
        weights = _fit_adapter(
            split,
            catalog,
            model_path=model_spec[3],
            seed=args.seed,
            model_kind=args.model_kind,
            base_model_repo=model_spec[0],
            base_model_revision=model_spec[2],
            embedding_backend=embedding_backend,
            reranker_backend=reranker_backend,
        )
        dataset_sha256 = training_dataset_sha256(split)
        catalog_sha256 = _file_sha256(args.catalog)
        with tempfile.TemporaryDirectory(prefix="dynamic-mapping-training-") as temp_dir:
            temp_root = Path(temp_dir)
            artifact_path = temp_root / "adapter-weights.json"
            _write_json(artifact_path, weights)
            artifact_sha256 = adapter_file_sha256(artifact_path)
            report = _evaluate_exported_adapter(
                split,
                catalog,
                artifact_path=artifact_path,
                artifact_sha256=artifact_sha256,
                dataset_sha256=dataset_sha256,
                catalog_sha256=catalog_sha256,
                model_kind=args.model_kind,
                embedding_backend=embedding_backend,
                reranker_backend=reranker_backend,
                model_path=model_spec[3],
            )
            report_path = temp_root / "held-out-evaluation.json"
            _write_json(report_path, report.model_dump(mode="json"))
            report_sha256 = _file_sha256(report_path)
            metrics = report.metrics
            manifest = ModelManifest(
                schema_version="dynamic-mapping-model-manifest-v2",
                model_kind=(
                    "domain_bi_encoder"
                    if args.model_kind == "bi-encoder"
                    else "domain_pair_reranker"
                ),
                base_model_repo=model_spec[0],
                base_model_revision=model_spec[2],
                dataset_sha256=dataset_sha256,
                catalog_sha256=catalog_sha256,
                model_artifact_sha256=artifact_sha256,
                evaluation_report_sha256=report_sha256,
                catalog_version=catalog.version,
                training_code_version=TRAINING_CODE_VERSION,
                evaluation_code_version=EVALUATION_CODE_VERSION,
                training_sample_count=len(split.train),
                evaluation_sample_count=len(split.test),
                training_cohort_count=len(
                    {example.document_layout_hash for example in split.train}
                ),
                evaluation_cohort_count=report.cohort_count,
                auto_precision=metrics.auto_precision,
                sensitive_precision=metrics.sensitive_precision,
                coverage=metrics.coverage,
                expected_calibration_error=metrics.expected_calibration_error,
                p95_latency_ms=metrics.p95_latency_ms,
                seed=args.seed,
                training_canonical_field_ids=tuple(
                    sorted({example.canonical_field_id for example in split.train})
                ),
                catalog_field_ids=tuple(
                    definition.field_id for definition in catalog.definitions
                ),
            )
            artifact_bytes = artifact_path.read_bytes()
            report_bytes = report_path.read_bytes()
    except (
        OSError,
        RuntimeError,
        ValidationError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"training failed: {error}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "adapter-weights.json").write_bytes(artifact_bytes)
    (args.output_dir / "held-out-evaluation.json").write_bytes(report_bytes)
    _write_json(
        args.output_dir / "model-manifest.json", manifest.model_dump(mode="json")
    )
    print(
        f"trained={manifest.model_kind} dataset_sha256={manifest.dataset_sha256} "
        f"catalog_sha256={manifest.catalog_sha256}"
    )
    return 0


def _load_feedback(path: Path) -> tuple[MappingFeedbackRecord, ...]:
    records: list[MappingFeedbackRecord] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(MappingFeedbackRecord.model_validate_json(line))
        except ValidationError as error:
            raise ValueError(f"invalid feedback on line {line_number}: {error}") from error
    return tuple(records)


def _base_model_spec(model_kind: str) -> tuple[str, str, str, Path]:
    if model_kind == "bi-encoder":
        repo = QWEN3_EMBEDDING_REPO
        cache_name = QWEN3_EMBEDDING_CACHE_NAME
        revision = QWEN3_EMBEDDING_REVISION
        explicit_path = os.environ.get("FOWOCO_DYNAMIC_AUTOMATION_EMBEDDING_MODEL_PATH")
    else:
        repo = QWEN3_RERANKER_REPO
        cache_name = QWEN3_RERANKER_CACHE_NAME
        revision = QWEN3_RERANKER_REVISION
        explicit_path = os.environ.get("FOWOCO_DYNAMIC_AUTOMATION_RERANKER_MODEL_PATH")
    if explicit_path:
        path = Path(explicit_path)
    else:
        cache_root = Path(
            os.environ.get(
                "FOWOCO_MODEL_CACHE_DIR",
                str(Path(tempfile.gettempdir()) / "fowoco-model-cache"),
            )
        )
        path = cache_root / cache_name / revision
    return repo, cache_name, revision, path


def _require_local_model(path: Path, *, revision: str, cache_name: str) -> None:
    if tuple(path.parts[-2:]) != (cache_name, revision):
        raise ValueError(
            f"base model path must end with pinned cache path {cache_name}/{revision}"
        )
    if not path.is_dir() or not (path / "config.json").is_file():
        raise ValueError(
            f"pinned local base model cache is unavailable at {path}; "
            "provision it explicitly before training"
        )
    has_weights = any(path.glob("*.safetensors")) or any(path.glob("*.bin"))
    if not has_weights:
        raise ValueError(f"pinned local base model cache has no model weights at {path}")


def _fit_adapter(
    split: TrainingSplit,
    catalog: CanonicalCatalog,
    *,
    model_path: Path,
    seed: int,
    model_kind: str,
    base_model_repo: str,
    base_model_revision: str,
    embedding_backend: EmbeddingBackend | None = None,
    reranker_backend: RerankerBackend | None = None,
) -> dict[str, Any]:
    common = {
        "format_version": "dynamic-mapping-adapter-v2",
        "model_kind": model_kind,
        "base_model_repo": base_model_repo,
        "base_model_revision": base_model_revision,
        "seed": seed,
    }
    if model_kind == "bi-encoder":
        common["weights"] = _fit_bi_encoder(
            split,
            catalog,
            model_path=model_path,
            backend=embedding_backend,
        )
    else:
        common["weights"] = _fit_pair_reranker(
            split,
            catalog,
            model_path=model_path,
            backend=reranker_backend,
        )
    return common


def _fit_bi_encoder(
    split: TrainingSplit,
    catalog: CanonicalCatalog,
    *,
    model_path: Path,
    backend: EmbeddingBackend | None = None,
) -> dict[str, Any]:
    backend = backend or LocalSentenceTransformerBackend(model_path)
    queries = tuple(example.query_text for example in split.train)
    documents = tuple(
        _definition_text(catalog, example.canonical_field_id)
        for example in split.train
    )
    query_vectors = backend.encode_queries(queries, max_length=512, batch_size=8)
    document_vectors = backend.encode_documents(
        documents, max_length=512, batch_size=8
    )
    if len(query_vectors) != len(split.train) or len(document_vectors) != len(
        split.train
    ):
        raise RuntimeError("invalid embedding batch size during adapter training")
    if not query_vectors or not query_vectors[0]:
        raise RuntimeError("base embedding model returned empty vectors")
    dimensions = {len(vector) for vector in (*query_vectors, *document_vectors)}
    if len(dimensions) != 1:
        raise RuntimeError("base embedding model returned inconsistent dimensions")
    pair_count = len(query_vectors)
    query_bias = tuple(
        sum(document[index] - query[index] for query, document in zip(
            query_vectors, document_vectors, strict=True
        ))
        / pair_count
        for index in range(len(query_vectors[0]))
    )
    return {
        "adapter_kind": "query_bias_projection",
        "embedding_dimension": len(query_bias),
        "positive_pair_count": pair_count,
        "query_bias": query_bias,
    }


def _fit_pair_reranker(
    split: TrainingSplit,
    catalog: CanonicalCatalog,
    *,
    model_path: Path,
    backend: RerankerBackend | None = None,
) -> dict[str, Any]:
    backend = backend or LocalQwen3RerankerBackend(model_path)
    positive_pairs = tuple(
        (example.query_text, _definition_text(catalog, example.canonical_field_id))
        for example in split.train
    )
    negatives = build_hard_negatives(split, catalog)
    negative_pairs = tuple(
        (pair.query_text, _definition_text(catalog, pair.negative_canonical_field_id))
        for pair in negatives
    )
    if not negative_pairs:
        raise ValueError("pair-reranker training requires type-compatible negatives")
    positive_scores = backend.score_pairs(
        positive_pairs, max_length=512, batch_size=2
    )
    negative_scores = backend.score_pairs(
        negative_pairs, max_length=512, batch_size=2
    )
    if len(positive_scores) != len(positive_pairs) or len(negative_scores) != len(
        negative_pairs
    ):
        raise RuntimeError("invalid reranker batch size during adapter training")
    positive_mean = sum(positive_scores) / len(positive_scores)
    negative_mean = sum(negative_scores) / len(negative_scores)
    threshold = (positive_mean + negative_mean) / 2
    separation = positive_mean - negative_mean
    scale = 1 / (separation if abs(separation) >= 1e-6 else 1e-6)
    return {
        "adapter_kind": "score_calibration",
        "positive_pair_count": len(positive_pairs),
        "negative_pair_count": len(negative_pairs),
        "scale": scale,
        "bias": -threshold * scale,
    }


def _evaluate_exported_adapter(
    split: TrainingSplit,
    catalog: CanonicalCatalog,
    *,
    artifact_path: Path,
    artifact_sha256: str,
    dataset_sha256: str,
    catalog_sha256: str,
    model_kind: str,
    embedding_backend: EmbeddingBackend | None,
    reranker_backend: RerankerBackend | None,
    model_path: Path,
) -> HeldOutEvaluationReport:
    if not split.test:
        raise ValueError("training requires at least one held-out evaluation cohort")
    if model_kind == "bi-encoder":
        adapter: Any = load_domain_embedding_retriever(
            artifact_path,
            backend=embedding_backend,
            model_path=model_path,
            expected_sha256=artifact_sha256,
        )
    else:
        adapter = load_domain_reranker(
            artifact_path,
            backend=reranker_backend,
            model_path=model_path,
            definition_resolver=catalog.get,
            expected_sha256=artifact_sha256,
        )

    correct = 0
    predictions = 0
    sensitive_correct = 0
    sensitive_predictions = 0
    calibration_errors: list[float] = []
    latencies_ms: list[float] = []
    for example in split.test:
        definition = catalog.get(example.canonical_field_id)
        context = _context_for_training_example(example, definition.compatible_field_types[0])
        candidates = catalog.compatible(context)
        started = time.perf_counter()
        ranked = _rank_with_adapter(
            adapter,
            model_kind=model_kind,
            context=context,
            candidates=candidates,
        )
        latencies_ms.append((time.perf_counter() - started) * 1_000)
        if not ranked:
            continue
        predictions += 1
        is_correct = ranked[0].canonical_field_id == example.canonical_field_id
        correct += int(is_correct)
        calibration_errors.append(abs(ranked[0].score - float(is_correct)))
        if definition.sensitivity == "sensitive":
            sensitive_predictions += 1
            sensitive_correct += int(is_correct)

    training_ids = {example.canonical_field_id for example in split.train}
    unseen_definition = next(
        definition
        for definition in catalog.definitions
        if definition.field_id not in training_ids
    )
    unseen_context = _generated_unseen_context(unseen_definition)
    unseen_ranked = _rank_with_adapter(
        adapter,
        model_kind=model_kind,
        context=unseen_context,
        candidates=catalog.compatible(unseen_context),
    )
    unseen_ids = tuple(item.canonical_field_id for item in unseen_ranked[:20])
    try:
        unseen_rank: int | None = unseen_ids.index(unseen_definition.field_id) + 1
    except ValueError:
        unseen_rank = None
    query_payload = json.dumps(
        unseen_context.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    sample_count = len(split.test)
    metrics = EvaluationMetricsEvidence(
        auto_precision=_ratio(correct, predictions),
        sensitive_precision=(
            _ratio(sensitive_correct, sensitive_predictions)
            if sensitive_predictions
            else 1.0
        ),
        coverage=_ratio(predictions, sample_count),
        expected_calibration_error=(
            sum(calibration_errors) / len(calibration_errors)
            if calibration_errors
            else 1.0
        ),
        p95_latency_ms=_percentile_95(latencies_ms),
    )
    return HeldOutEvaluationReport(
        schema_version="dynamic-mapping-held-out-v2",
        evaluation_code_version=EVALUATION_CODE_VERSION,
        model_artifact_sha256=artifact_sha256,
        dataset_sha256=dataset_sha256,
        catalog_sha256=catalog_sha256,
        catalog_version=catalog.version,
        sample_count=sample_count,
        cohort_count=len({example.document_layout_hash for example in split.test}),
        model_execution_count=sample_count + 1,
        metrics=metrics,
        unseen_field_evidence=UnseenFieldEvidence(
            case_id=f"generated-unseen:{unseen_definition.field_id}",
            canonical_field_id=unseen_definition.field_id,
            query_sha256=hashlib.sha256(query_payload).hexdigest(),
            candidate_ids=unseen_ids,
            retrieved_rank=unseen_rank,
        ),
    )


def _rank_with_adapter(
    adapter: Any,
    *,
    model_kind: str,
    context: DocumentFieldContext,
    candidates: Sequence[Any],
) -> tuple[ScoredCandidate, ...]:
    if model_kind == "bi-encoder":
        return adapter.retrieve(context, candidates, min(20, len(candidates)))
    initial = tuple(
        ScoredCandidate(canonical_field_id=item.field_id, score=0.5, rank=index)
        for index, item in enumerate(candidates[:20], start=1)
    )
    return adapter.rerank(context, initial)


def _context_for_training_example(example: Any, field_type: str) -> DocumentFieldContext:
    lines = example.query_text.splitlines()
    label = lines[0].removeprefix("label: ") if lines else example.field_id
    section = lines[1].removeprefix("section: ") if len(lines) > 1 else ""
    return DocumentFieldContext(
        field_id=example.field_id,
        container_id="held-out-evaluation",
        label=label[:200],
        normalized_label=label.casefold().replace(" ", "")[:200],
        field_type=field_type,
        document_title="Held-out mapping evaluation",
        section=section[:200],
        row_labels=(section[:200], label[:200]) if section else (label[:200],),
        nearby_labels=(),
        options=(),
        repeat_index=example.repeat_index,
        required=True,
        kind="text_field",
    )


def _generated_unseen_context(definition: Any) -> DocumentFieldContext:
    label = definition.description[:200]
    return DocumentFieldContext(
        field_id=f"generated-{definition.field_id}"[:200],
        container_id="generated-unseen-evaluation",
        label=label,
        normalized_label=label.casefold().replace(" ", "")[:200],
        field_type=definition.compatible_field_types[0],
        document_title="Generated unseen catalog evaluation",
        section=definition.entity[:200],
        row_labels=(definition.entity[:200], label),
        nearby_labels=tuple(alias[:200] for alias in definition.aliases[:4]),
        options=(),
        repeat_index=0,
        required=True,
        kind="text_field",
    )


def _percentile_95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _definition_text(catalog: CanonicalCatalog, field_id: str) -> str:
    definition = catalog.get(field_id)
    return "\n".join(
        (
            f"field id: {definition.field_id}",
            f"entity: {definition.entity}",
            f"value type: {definition.value_type}",
            f"aliases: {' | '.join(definition.aliases)}",
            f"description: {definition.description}",
        )
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
