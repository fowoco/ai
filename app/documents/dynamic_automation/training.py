"""Privacy-safe training datasets and fail-closed model promotion gates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .catalog import CanonicalCatalog
from .feedback import MappingFeedbackRecord, ReviewerDecision
from .qwen import (
    QWEN3_EMBEDDING_REPO,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_REPO,
    QWEN3_RERANKER_REVISION,
)

AUTO_PRECISION_FLOOR = 0.99
SENSITIVE_PRECISION_FLOOR = 0.995

_CANONICAL_ID_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_BoundedCanonicalId = Annotated[
    str, Field(max_length=200, pattern=_CANONICAL_ID_PATTERN)
]


class TrainingExample(BaseModel):
    """One reviewer-approved, value-free retrieval query and label."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_layout_hash: str = Field(pattern=_SHA256_PATTERN)
    field_context_hash: str = Field(pattern=_SHA256_PATTERN)
    field_id: str = Field(min_length=1, max_length=200)
    repeat_index: int = Field(ge=0)
    query_text: str = Field(min_length=1, max_length=1800)
    canonical_field_id: _BoundedCanonicalId
    catalog_version: str = Field(max_length=20, pattern=r"^v[1-9][0-9]*$")


class TrainingSplit(BaseModel):
    """Deterministic split whose layout groups never cross partitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    train: tuple[TrainingExample, ...]
    test: tuple[TrainingExample, ...]


class TrainingPair(BaseModel):
    """Type-compatible negative pair for retrieval or pairwise ranking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_layout_hash: str = Field(pattern=_SHA256_PATTERN)
    query_text: str = Field(min_length=1, max_length=1800)
    positive_canonical_field_id: _BoundedCanonicalId
    negative_canonical_field_id: _BoundedCanonicalId


class ModelManifest(BaseModel):
    """Immutable evidence used to compare a candidate with the pinned baseline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_kind: Literal[
        "qwen_baseline", "domain_bi_encoder", "domain_pair_reranker"
    ]
    base_model_repo: str = Field(min_length=1, max_length=300)
    base_model_revision: str = Field(min_length=1, max_length=200)
    dataset_sha256: str = Field(pattern=_SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=_SHA256_PATTERN)
    catalog_version: str = Field(max_length=20, pattern=r"^v[1-9][0-9]*$")
    auto_precision: float = Field(ge=0, le=1)
    sensitive_precision: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    expected_calibration_error: float = Field(ge=0, le=1)
    p95_latency_ms: float = Field(ge=0)
    seed: int = Field(default=42, ge=0)
    training_canonical_field_ids: tuple[_BoundedCanonicalId, ...] = Field(
        default=(), max_length=10_000
    )
    catalog_field_ids: tuple[_BoundedCanonicalId, ...] = Field(
        min_length=1, max_length=10_000
    )
    unseen_catalog_field_id: _BoundedCanonicalId | None = None
    unseen_catalog_retrieved: bool

    @field_validator("catalog_sha256")
    @classmethod
    def _catalog_hash_is_not_a_placeholder(cls, value: str) -> str:
        if value == "0" * 64:
            raise ValueError("catalog_sha256 must not be the zero placeholder")
        return value

    @field_validator("catalog_field_ids")
    @classmethod
    def _catalog_membership_is_unique_and_stable(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("catalog_field_ids must not contain duplicates")
        return tuple(sorted(value))


class PromotionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    promote: bool
    reasons: tuple[str, ...]


def build_training_split(
    records: Sequence[MappingFeedbackRecord | Mapping[str, Any]],
) -> TrainingSplit:
    """Build a stable split after revalidating every sanitized feedback record."""
    validated = tuple(_validate_feedback(record) for record in records)
    examples = tuple(
        sorted(
            (
                _to_example(record)
                for record in validated
                if record.final_canonical_field_id is not None
                and record.decision
                in (ReviewerDecision.ACCEPTED, ReviewerDecision.CORRECTED)
            ),
            key=_example_sort_key,
        )
    )
    layouts = sorted({example.document_layout_hash for example in examples})
    if len(layouts) < 2:
        test_layouts: set[str] = set()
    else:
        test_count = max(1, len(layouts) // 5)
        ranked_layouts = sorted(
            layouts,
            key=lambda layout: (hashlib.sha256(layout.encode("ascii")).hexdigest(), layout),
        )
        test_layouts = set(ranked_layouts[:test_count])
    return TrainingSplit(
        train=tuple(
            example
            for example in examples
            if example.document_layout_hash not in test_layouts
        ),
        test=tuple(
            example
            for example in examples
            if example.document_layout_hash in test_layouts
        ),
    )


def build_hard_negatives(
    split: TrainingSplit, catalog: CanonicalCatalog
) -> tuple[TrainingPair, ...]:
    """Return deterministic catalog negatives, with known entity confusions first."""
    definitions = tuple(catalog._fields_by_id.values())
    pairs: list[TrainingPair] = []
    for example in split.train:
        positive = catalog.get(example.canonical_field_id)
        compatible = [
            candidate
            for candidate in definitions
            if candidate.field_id != positive.field_id
            and set(candidate.compatible_field_types)
            & set(positive.compatible_field_types)
        ]
        priority = _CONFUSION_PRIORITY.get(positive.field_id, ())
        compatible.sort(
            key=lambda candidate: (
                priority.index(candidate.field_id)
                if candidate.field_id in priority
                else len(priority),
                candidate.field_id,
            )
        )
        pairs.extend(
            TrainingPair(
                document_layout_hash=example.document_layout_hash,
                query_text=example.query_text,
                positive_canonical_field_id=positive.field_id,
                negative_canonical_field_id=candidate.field_id,
            )
            for candidate in compatible
        )
    return tuple(pairs)


def compare_manifests(
    *, baseline: ModelManifest, candidate: ModelManifest
) -> PromotionDecision:
    """Require every safety, quality, efficiency, and generalization gate."""
    reasons: list[str] = []
    expected_base: tuple[str, str] | None
    if candidate.model_kind == "domain_bi_encoder":
        expected_base = (QWEN3_EMBEDDING_REPO, QWEN3_EMBEDDING_REVISION)
    elif candidate.model_kind == "domain_pair_reranker":
        expected_base = (QWEN3_RERANKER_REPO, QWEN3_RERANKER_REVISION)
    else:
        expected_base = None
        reasons.append("candidate_model_kind")
    if baseline.model_kind != "qwen_baseline":
        reasons.append("baseline_model_kind")
    if expected_base is not None and (
        (baseline.base_model_repo, baseline.base_model_revision) != expected_base
        or (candidate.base_model_repo, candidate.base_model_revision) != expected_base
    ):
        reasons.append("base_model_manifest")
    if (
        candidate.auto_precision < AUTO_PRECISION_FLOOR
        or candidate.auto_precision < baseline.auto_precision
    ):
        reasons.append("auto_precision")
    if (
        candidate.sensitive_precision < SENSITIVE_PRECISION_FLOOR
        or candidate.sensitive_precision < baseline.sensitive_precision
    ):
        reasons.append("sensitive_precision")
    if candidate.expected_calibration_error > baseline.expected_calibration_error:
        reasons.append("expected_calibration_error")
    if not (
        candidate.coverage > baseline.coverage
        or candidate.p95_latency_ms < baseline.p95_latency_ms
    ):
        reasons.append("coverage_or_p95_latency_ms")
    if candidate.catalog_version != baseline.catalog_version:
        reasons.append("catalog_version")
    if candidate.catalog_sha256 != baseline.catalog_sha256:
        reasons.append("catalog_sha256")
    if candidate.catalog_field_ids != baseline.catalog_field_ids:
        reasons.append("catalog_field_ids")
    if (
        candidate.unseen_catalog_field_id is None
        or not candidate.unseen_catalog_retrieved
        or candidate.unseen_catalog_field_id not in candidate.catalog_field_ids
        or candidate.unseen_catalog_field_id not in baseline.catalog_field_ids
        or candidate.unseen_catalog_field_id
        in candidate.training_canonical_field_ids
    ):
        reasons.append("unseen_catalog_retrieval")
    return PromotionDecision(promote=not reasons, reasons=tuple(reasons))


def training_dataset_sha256(split: TrainingSplit) -> str:
    """Hash canonical JSON so record ordering and JSONL whitespace cannot affect identity."""
    payload = split.model_dump(mode="json")
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _validate_feedback(
    record: MappingFeedbackRecord | Mapping[str, Any],
) -> MappingFeedbackRecord:
    payload: Any
    if isinstance(record, MappingFeedbackRecord):
        payload = record.model_dump(mode="json", warnings="none")
    else:
        payload = record
    return MappingFeedbackRecord.model_validate(payload)


def _to_example(record: MappingFeedbackRecord) -> TrainingExample:
    assert record.final_canonical_field_id is not None
    parts = (
        f"label: {record.label}",
        f"section: {record.section}",
        f"row labels: {' | '.join(record.row_labels)}",
        f"nearby labels: {' | '.join(record.nearby_labels)}",
    )
    return TrainingExample(
        document_layout_hash=record.layout_hash,
        field_context_hash=record.field_context_hash,
        field_id=record.field_id,
        repeat_index=record.repeat_index,
        query_text="\n".join(parts),
        canonical_field_id=record.final_canonical_field_id,
        catalog_version=record.catalog_version,
    )


def _example_sort_key(example: TrainingExample) -> tuple[str, str, str, int]:
    return (
        example.document_layout_hash,
        example.field_context_hash,
        example.field_id,
        example.repeat_index,
    )


_CONFUSION_PRIORITY: dict[str, tuple[str, ...]] = {
    "worker.phone": ("company.phone", "guarantor.phone"),
    "company.phone": ("worker.phone", "guarantor.phone"),
    "guarantor.phone": ("worker.phone", "company.phone"),
    "worker.legal_name": ("company.representative_name",),
    "company.representative_name": ("worker.legal_name",),
    "identity.passport_number": ("identity.alien_registration_number",),
    "identity.alien_registration_number": ("identity.passport_number",),
    "contract.start_date": ("application.date", "contract.end_date", "contract.expiry_date"),
    "contract.end_date": ("contract.start_date", "application.date", "contract.expiry_date"),
    "contract.expiry_date": ("contract.end_date", "application.date", "contract.start_date"),
    "application.date": ("contract.start_date", "contract.end_date", "contract.expiry_date"),
}
