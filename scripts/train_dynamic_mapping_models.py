"""Build deterministic domain mapping adapters from sanitized reviewer feedback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.documents.dynamic_automation.catalog import CanonicalCatalog  # noqa: E402
from app.documents.dynamic_automation.feedback import MappingFeedbackRecord  # noqa: E402
from app.documents.dynamic_automation.qwen import (  # noqa: E402
    QWEN3_EMBEDDING_CACHE_NAME,
    QWEN3_EMBEDDING_REPO,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_CACHE_NAME,
    QWEN3_RERANKER_REPO,
    QWEN3_RERANKER_REVISION,
    LocalQwen3RerankerBackend,
    LocalSentenceTransformerBackend,
)
from app.documents.dynamic_automation.training import (  # noqa: E402
    ModelManifest,
    TrainingSplit,
    build_hard_negatives,
    build_training_split,
    training_dataset_sha256,
)


def main(argv: Sequence[str] | None = None) -> int:
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
        _require_local_model(model_spec[3], revision=model_spec[2], cache_name=model_spec[1])
        weights = _fit_adapter(
            split,
            catalog,
            model_path=model_spec[3],
            seed=args.seed,
            model_kind=args.model_kind,
            base_model_repo=model_spec[0],
            base_model_revision=model_spec[2],
        )
        manifest = ModelManifest(
            model_kind=(
                "domain_bi_encoder"
                if args.model_kind == "bi-encoder"
                else "domain_pair_reranker"
            ),
            base_model_repo=model_spec[0],
            base_model_revision=model_spec[2],
            dataset_sha256=training_dataset_sha256(split),
            catalog_sha256=_file_sha256(args.catalog),
            catalog_version=catalog.version,
            auto_precision=0.0,
            sensitive_precision=0.0,
            coverage=0.0,
            expected_calibration_error=1.0,
            p95_latency_ms=1_000_000_000.0,
            seed=args.seed,
            training_canonical_field_ids=tuple(
                sorted({example.canonical_field_id for example in split.train})
            ),
            catalog_field_ids=tuple(sorted(catalog._fields_by_id)),
            unseen_catalog_field_id=None,
            unseen_catalog_retrieved=False,
        )
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
    _write_json(args.output_dir / "adapter-weights.json", weights)
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
) -> dict[str, Any]:
    common = {
        "format_version": "dynamic-mapping-adapter-v1",
        "model_kind": model_kind,
        "base_model_repo": base_model_repo,
        "base_model_revision": base_model_revision,
        "seed": seed,
    }
    if model_kind == "bi-encoder":
        common["weights"] = _fit_bi_encoder(split, catalog, model_path=model_path)
    else:
        common["weights"] = _fit_pair_reranker(
            split, catalog, model_path=model_path
        )
    return common


def _fit_bi_encoder(
    split: TrainingSplit, catalog: CanonicalCatalog, *, model_path: Path
) -> dict[str, Any]:
    backend = LocalSentenceTransformerBackend(model_path)
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
        "adapter_kind": "mean_query_bias",
        "embedding_dimension": len(query_bias),
        "positive_pair_count": pair_count,
        "query_bias": query_bias,
    }


def _fit_pair_reranker(
    split: TrainingSplit, catalog: CanonicalCatalog, *, model_path: Path
) -> dict[str, Any]:
    backend = LocalQwen3RerankerBackend(model_path)
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
    scale = 1 / max(abs(positive_mean - negative_mean), 1e-6)
    return {
        "adapter_kind": "score_calibration",
        "positive_pair_count": len(positive_pairs),
        "negative_pair_count": len(negative_pairs),
        "scale": scale,
        "bias": -threshold * scale,
    }


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
