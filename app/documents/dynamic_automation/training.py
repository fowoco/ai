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
TRAINING_CODE_VERSION = "dynamic-mapping-training-v2"
EVALUATION_CODE_VERSION = "dynamic-mapping-evaluation-v2"

_CANONICAL_ID_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_BoundedCanonicalId = Annotated[
    str, Field(max_length=200, pattern=_CANONICAL_ID_PATTERN)
]


class TrainingExample(BaseModel):
    """One reviewer-approved, value-free retrieval query and label."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_layout_hash: str = Field(pattern=_SHA256_PATTERN)
    document_kind: str = Field(min_length=1, max_length=100)
    document_version: str = Field(min_length=1, max_length=100)
    source_institution: str = Field(min_length=1, max_length=100)
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


class EvaluationMetricsEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    auto_precision: float = Field(ge=0, le=1)
    sensitive_precision: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    expected_calibration_error: float = Field(ge=0, le=1)
    p95_latency_ms: float = Field(ge=0)


class UnseenFieldEvidence(BaseModel):
    """Generated catalog-field retrieval evidence, never a self-asserted boolean."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=200)
    canonical_field_id: _BoundedCanonicalId
    query_sha256: str = Field(pattern=_SHA256_PATTERN)
    candidate_ids: tuple[_BoundedCanonicalId, ...] = Field(max_length=20)
    retrieved_rank: int | None = Field(default=None, ge=1, le=20)


class HeldOutEvaluationReport(BaseModel):
    """Hashed evidence produced by loading and executing an exported artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["dynamic-mapping-held-out-v2"]
    evaluation_code_version: Literal["dynamic-mapping-evaluation-v2"]
    model_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    dataset_sha256: str = Field(pattern=_SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=_SHA256_PATTERN)
    catalog_version: str = Field(max_length=20, pattern=r"^v[1-9][0-9]*$")
    sample_count: int = Field(ge=1)
    cohort_count: int = Field(ge=1)
    model_execution_count: int = Field(ge=1)
    metrics: EvaluationMetricsEvidence
    unseen_field_evidence: UnseenFieldEvidence


class ModelManifest(BaseModel):
    """Immutable evidence used to compare a candidate with the pinned baseline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["dynamic-mapping-model-manifest-v2"]
    model_kind: Literal[
        "qwen_baseline", "domain_bi_encoder", "domain_pair_reranker"
    ]
    base_model_repo: str = Field(min_length=1, max_length=300)
    base_model_revision: str = Field(min_length=1, max_length=200)
    dataset_sha256: str = Field(pattern=_SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=_SHA256_PATTERN)
    model_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    evaluation_report_sha256: str = Field(pattern=_SHA256_PATTERN)
    catalog_version: str = Field(max_length=20, pattern=r"^v[1-9][0-9]*$")
    training_code_version: Literal["dynamic-mapping-training-v2"]
    evaluation_code_version: Literal["dynamic-mapping-evaluation-v2"]
    training_sample_count: int = Field(ge=1)
    evaluation_sample_count: int = Field(ge=1)
    training_cohort_count: int = Field(ge=1)
    evaluation_cohort_count: int = Field(ge=1)
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

    @field_validator(
        "dataset_sha256",
        "catalog_sha256",
        "model_artifact_sha256",
        "evaluation_report_sha256",
    )
    @classmethod
    def _hash_is_not_a_placeholder(cls, value: str) -> str:
        if value == "0" * 64:
            raise ValueError("evidence SHA-256 must not be the zero placeholder")
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
    components = _group_components(examples)
    if len(components) < 2:
        test_indices: set[int] = set()
    else:
        test_count = max(1, len(components) // 5)
        ranked_components = sorted(
            components,
            key=lambda component: (
                hashlib.sha256(
                    "\n".join(
                        _example_group_fingerprint(examples[index])
                        for index in component
                    ).encode("utf-8")
                ).hexdigest(),
                tuple(_example_sort_key(examples[index]) for index in component),
            ),
        )
        test_indices = {
            index
            for component in ranked_components[:test_count]
            for index in component
        }
    return TrainingSplit(
        train=tuple(
            example
            for index, example in enumerate(examples)
            if index not in test_indices
        ),
        test=tuple(
            example
            for index, example in enumerate(examples)
            if index in test_indices
        ),
    )


def build_hard_negatives(
    split: TrainingSplit, catalog: CanonicalCatalog
) -> tuple[TrainingPair, ...]:
    """Return deterministic catalog negatives, with known entity confusions first."""
    definitions = catalog.definitions
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
    *,
    baseline: ModelManifest,
    candidate: ModelManifest,
    baseline_report: HeldOutEvaluationReport,
    candidate_report: HeldOutEvaluationReport,
    baseline_artifact_sha256: str | None = None,
    candidate_artifact_sha256: str | None = None,
    baseline_report_sha256: str | None = None,
    candidate_report_sha256: str | None = None,
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
    baseline_evidence_valid = _manifest_matches_evidence(
        baseline,
        baseline_report,
        artifact_sha256=baseline_artifact_sha256,
        report_sha256=baseline_report_sha256,
    )
    candidate_evidence_valid = _manifest_matches_evidence(
        candidate,
        candidate_report,
        artifact_sha256=candidate_artifact_sha256,
        report_sha256=candidate_report_sha256,
    )
    if not baseline_evidence_valid:
        reasons.append("baseline_evaluation_evidence")
    if not candidate_evidence_valid:
        reasons.append("candidate_evaluation_evidence")

    baseline_metrics = baseline_report.metrics
    candidate_metrics = candidate_report.metrics
    if (
        candidate_metrics.auto_precision < AUTO_PRECISION_FLOOR
        or candidate_metrics.auto_precision < baseline_metrics.auto_precision
    ):
        reasons.append("auto_precision")
    if (
        candidate_metrics.sensitive_precision < SENSITIVE_PRECISION_FLOOR
        or candidate_metrics.sensitive_precision < baseline_metrics.sensitive_precision
    ):
        reasons.append("sensitive_precision")
    if (
        candidate_metrics.expected_calibration_error
        > baseline_metrics.expected_calibration_error
    ):
        reasons.append("expected_calibration_error")
    if candidate_metrics.coverage < baseline_metrics.coverage:
        reasons.append("coverage")
    if candidate_metrics.p95_latency_ms > baseline_metrics.p95_latency_ms:
        reasons.append("p95_latency_ms")
    if (
        candidate_metrics.coverage == baseline_metrics.coverage
        and candidate_metrics.p95_latency_ms == baseline_metrics.p95_latency_ms
    ):
        reasons.append("coverage_or_p95_latency_ms")
    if candidate.catalog_version != baseline.catalog_version:
        reasons.append("catalog_version")
    if candidate.dataset_sha256 != baseline.dataset_sha256:
        reasons.append("dataset_sha256")
    if candidate.catalog_sha256 != baseline.catalog_sha256:
        reasons.append("catalog_sha256")
    if candidate.catalog_field_ids != baseline.catalog_field_ids:
        reasons.append("catalog_field_ids")
    unseen = candidate_report.unseen_field_evidence
    unseen_rank_valid = (
        unseen.retrieved_rank is not None
        and unseen.retrieved_rank <= len(unseen.candidate_ids)
        and unseen.candidate_ids[unseen.retrieved_rank - 1] == unseen.canonical_field_id
    )
    if (
        not unseen_rank_valid
        or unseen.canonical_field_id not in candidate.catalog_field_ids
        or unseen.canonical_field_id not in baseline.catalog_field_ids
        or unseen.canonical_field_id in candidate.training_canonical_field_ids
    ):
        reasons.append("unseen_catalog_retrieval")
    return PromotionDecision(promote=not reasons, reasons=tuple(reasons))


def held_out_evaluation_report_bytes(report: HeldOutEvaluationReport) -> bytes:
    serialized = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (serialized + "\n").encode("utf-8")


def held_out_evaluation_report_sha256(report: HeldOutEvaluationReport) -> str:
    return hashlib.sha256(held_out_evaluation_report_bytes(report)).hexdigest()


def _manifest_matches_evidence(
    manifest: ModelManifest,
    report: HeldOutEvaluationReport,
    *,
    artifact_sha256: str | None,
    report_sha256: str | None,
) -> bool:
    metrics = report.metrics
    return (
        artifact_sha256 == manifest.model_artifact_sha256
        and report_sha256 == manifest.evaluation_report_sha256
        and report.model_artifact_sha256 == manifest.model_artifact_sha256
        and report.dataset_sha256 == manifest.dataset_sha256
        and report.catalog_sha256 == manifest.catalog_sha256
        and report.catalog_version == manifest.catalog_version
        and report.evaluation_code_version == manifest.evaluation_code_version
        and report.sample_count == manifest.evaluation_sample_count
        and report.cohort_count == manifest.evaluation_cohort_count
        and metrics.auto_precision == manifest.auto_precision
        and metrics.sensitive_precision == manifest.sensitive_precision
        and metrics.coverage == manifest.coverage
        and metrics.expected_calibration_error
        == manifest.expected_calibration_error
        and metrics.p95_latency_ms == manifest.p95_latency_ms
    )


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
        document_kind=record.document_kind,
        document_version=record.document_version,
        source_institution=record.source_institution,
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


def _group_components(examples: Sequence[TrainingExample]) -> tuple[tuple[int, ...], ...]:
    """Return connected components sharing any required group identity."""
    parents = list(range(len(examples)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    seen: dict[tuple[str, str], int] = {}
    for index, example in enumerate(examples):
        identities = (
            ("layout_hash", example.document_layout_hash),
            ("document_kind", example.document_kind),
            ("document_version", example.document_version),
            ("source_institution", example.source_institution),
        )
        for identity in identities:
            previous = seen.setdefault(identity, index)
            union(index, previous)

    components: dict[int, list[int]] = {}
    for index in range(len(examples)):
        components.setdefault(find(index), []).append(index)
    return tuple(tuple(indices) for _, indices in sorted(components.items()))


def _example_group_fingerprint(example: TrainingExample) -> str:
    return "|".join(
        (
            example.document_layout_hash,
            example.document_kind,
            example.document_version,
            example.source_institution,
            example.field_context_hash,
            example.field_id,
            str(example.repeat_index),
        )
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
