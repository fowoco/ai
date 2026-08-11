"""Deterministic offline evaluation for dynamic canonical field mapping."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

AUTO_PRECISION_THRESHOLD = 0.99
SENSITIVE_PRECISION_THRESHOLD = 0.995
_CANONICAL_ID_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_BoundedCanonicalId = Annotated[
    str, Field(max_length=200, pattern=_CANONICAL_ID_PATTERN)
]
_BoundedText = Annotated[str, Field(max_length=200)]


class EvaluationStatus(StrEnum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMAPPED = "UNMAPPED"
    NON_DATA = "NON_DATA"


class EvaluationCase(BaseModel):
    """Literal expected and observed outcomes for one document field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=200)
    expected_status: EvaluationStatus
    expected_canonical_field_id: _BoundedCanonicalId | None = None
    expected_sensitive: bool
    predicted_status: EvaluationStatus
    predicted_canonical_field_id: _BoundedCanonicalId | None = None
    predicted_sensitive: bool = False
    candidate_ids: tuple[_BoundedCanonicalId, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def _matched_prediction_has_id(self) -> EvaluationCase:
        has_id = self.predicted_canonical_field_id is not None
        if (self.predicted_status is EvaluationStatus.MATCHED) != has_id:
            raise ValueError("only matched predictions may include a canonical field ID")
        return self


class EvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    extraction_precision: float
    extraction_recall: float
    top_1_accuracy: float
    top_k_recall: float
    auto_precision: float
    coverage: float
    ambiguous_accuracy: float
    sensitive_field_precision: float
    document_zero_error_rate: float


class _FixtureContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_id: str = Field(min_length=1, max_length=200)
    label: str = Field(max_length=200)
    normalized_label: str = Field(max_length=200)
    field_type: str = Field(min_length=1, max_length=100)
    document_title: str = Field(max_length=200)
    section: str = Field(max_length=200)
    row_labels: tuple[_BoundedText, ...] = Field(max_length=3)
    nearby_labels: tuple[_BoundedText, ...] = Field(max_length=4)
    options: tuple[_BoundedText, ...] = Field(max_length=50)
    repeat_index: int = Field(ge=0)
    required: bool
    kind: str = Field(min_length=1, max_length=100)


class _FixtureCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=200)
    context: _FixtureContext
    expected_status: EvaluationStatus
    expected_canonical_field_id: _BoundedCanonicalId | None = None


def evaluate_cases(
    cases: Sequence[EvaluationCase | Mapping[str, Any]], *, top_k: int = 5
) -> EvaluationMetrics:
    """Compute mapping metrics solely from literal expected and predicted outcomes."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    validated = tuple(
        case if isinstance(case, EvaluationCase) else EvaluationCase.model_validate(case)
        for case in cases
    )

    actual_data = [
        case for case in validated if case.expected_status is not EvaluationStatus.NON_DATA
    ]
    predicted_data = [
        case for case in validated if case.predicted_status is not EvaluationStatus.NON_DATA
    ]
    extraction_hits = sum(
        case.expected_status is not EvaluationStatus.NON_DATA for case in predicted_data
    )

    ranked = [case for case in validated if case.expected_canonical_field_id is not None]
    top_1_hits = sum(
        bool(case.candidate_ids)
        and case.candidate_ids[0] == case.expected_canonical_field_id
        for case in ranked
    )
    top_k_hits = sum(
        case.expected_canonical_field_id in case.candidate_ids[:top_k] for case in ranked
    )

    automatic = [
        case for case in validated if case.predicted_status is EvaluationStatus.MATCHED
    ]
    automatic_on_expected_data = [
        case for case in actual_data if case.predicted_status is EvaluationStatus.MATCHED
    ]
    correct_automatic = sum(_is_correct(case) for case in automatic)
    expected_ambiguous = [
        case for case in validated if case.expected_status is EvaluationStatus.AMBIGUOUS
    ]
    correct_ambiguous = sum(
        case.predicted_status is EvaluationStatus.AMBIGUOUS for case in expected_ambiguous
    )
    sensitive_automatic = [
        case for case in automatic if case.expected_sensitive or case.predicted_sensitive
    ]
    correct_sensitive = sum(_is_correct(case) for case in sensitive_automatic)

    documents: dict[str, list[EvaluationCase]] = defaultdict(list)
    for case in validated:
        documents[case.document_id].append(case)
    zero_error_documents = sum(
        all(_is_correct(case) for case in document_cases)
        for document_cases in documents.values()
    )

    return EvaluationMetrics(
        extraction_precision=_ratio(extraction_hits, len(predicted_data)),
        extraction_recall=_ratio(extraction_hits, len(actual_data)),
        top_1_accuracy=_ratio(top_1_hits, len(ranked)),
        top_k_recall=_ratio(top_k_hits, len(ranked)),
        auto_precision=_ratio(correct_automatic, len(automatic)),
        coverage=_ratio(len(automatic_on_expected_data), len(actual_data)),
        ambiguous_accuracy=_ratio(correct_ambiguous, len(expected_ambiguous)),
        sensitive_field_precision=_ratio(correct_sensitive, len(sensitive_automatic)),
        document_zero_error_rate=_ratio(zero_error_documents, len(documents)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("rule", "qwen"))
    args = parser.parse_args(argv)

    try:
        fixture_cases = _load_cases(args.cases)
        catalog, evaluated = _run_cases(fixture_cases, args.catalog, mode=args.mode)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"evaluation failed: {error}", file=sys.stderr)
        return 1

    metrics = evaluate_cases(evaluated)
    passed = (
        metrics.auto_precision >= AUTO_PRECISION_THRESHOLD
        and metrics.sensitive_field_precision >= SENSITIVE_PRECISION_THRESHOLD
    )
    report = {
        "mode": args.mode,
        "catalog_version": catalog.version,
        "case_count": len(evaluated),
        "metrics": metrics.model_dump(mode="json"),
        "gate": {
            "auto_precision_threshold": AUTO_PRECISION_THRESHOLD,
            "sensitive_field_precision_threshold": SENSITIVE_PRECISION_THRESHOLD,
            "passed": passed,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"precision={metrics.auto_precision:.6f} "
        f"coverage={metrics.coverage:.6f} "
        f"sensitive_precision={metrics.sensitive_field_precision:.6f}"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 2


def _load_cases(path: Path) -> tuple[_FixtureCase, ...]:
    cases: list[_FixtureCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(_FixtureCase.model_validate_json(line))
        except ValueError as error:
            raise ValueError(f"invalid case on line {line_number}: {error}") from error
    return tuple(cases)


def _run_cases(
    fixture_cases: Sequence[_FixtureCase], catalog_path: Path, *, mode: str
) -> tuple[Any, tuple[EvaluationCase, ...]]:
    _ensure_project_root_on_path()
    from app.documents.dynamic_automation.catalog import CanonicalCatalog
    from app.documents.dynamic_automation.models import DocumentFieldContext

    catalog = CanonicalCatalog.load(catalog_path)
    contexts = tuple(
        DocumentFieldContext.model_validate(case.context.model_dump(mode="json"))
        for case in fixture_cases
    )
    mapper = _make_mapper(catalog, mode=mode)
    plan = mapper.map(contexts)
    evaluated: list[EvaluationCase] = []
    for fixture, mapping in zip(fixture_cases, plan.mappings, strict=True):
        expected_sensitive = False
        if fixture.expected_canonical_field_id is not None:
            definition = catalog.get(fixture.expected_canonical_field_id)
            expected_sensitive = definition.sensitivity == "sensitive"
        predicted_sensitive = False
        if mapping.canonical_field_id is not None:
            predicted_definition = catalog.get(mapping.canonical_field_id)
            predicted_sensitive = predicted_definition.sensitivity == "sensitive"
        evaluated.append(
            EvaluationCase(
                case_id=fixture.case_id,
                document_id=fixture.document_id,
                expected_status=fixture.expected_status,
                expected_canonical_field_id=fixture.expected_canonical_field_id,
                expected_sensitive=expected_sensitive,
                predicted_status=mapping.status.value,
                predicted_canonical_field_id=mapping.canonical_field_id,
                predicted_sensitive=predicted_sensitive,
                candidate_ids=tuple(
                    candidate.canonical_field_id for candidate in mapping.candidates
                ),
            )
        )
    return catalog, tuple(evaluated)


def _make_mapper(catalog: Any, *, mode: str) -> Any:
    from app.documents.dynamic_automation.mapper import HybridFieldMapper, MappingThresholds

    if mode == "rule":
        retriever: Any = _UnavailableRetriever()
        reranker: Any = _UnavailableReranker()
    else:
        from app.documents.dynamic_automation.qwen import (
            Qwen3CandidateReranker,
            Qwen3EmbeddingRetriever,
        )

        embedding_path = os.environ.get("FOWOCO_QWEN3_EMBEDDING_PATH")
        reranker_path = os.environ.get("FOWOCO_QWEN3_RERANKER_PATH")
        if embedding_path is None or reranker_path is None:
            raise ValueError(
                "qwen mode requires FOWOCO_QWEN3_EMBEDDING_PATH and "
                "FOWOCO_QWEN3_RERANKER_PATH"
            )
        retriever = Qwen3EmbeddingRetriever(embedding_path)
        reranker = Qwen3CandidateReranker(reranker_path)
    return HybridFieldMapper(
        catalog=catalog,
        retriever=retriever,
        reranker=reranker,
        thresholds=MappingThresholds(
            min_reranker_score=0.90,
            min_margin=0.10,
        ),
        top_k=5,
    )


class _UnavailableRetriever:
    model_version = "rule-mode-no-retriever-v1"

    def retrieve(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("semantic retrieval is disabled in rule mode")


class _UnavailableReranker:
    model_version = "rule-mode-no-reranker-v1"

    def rerank(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("semantic reranking is disabled in rule mode")


def _is_correct(case: EvaluationCase) -> bool:
    if case.predicted_status is not case.expected_status:
        return False
    if case.expected_status is EvaluationStatus.MATCHED:
        return case.predicted_canonical_field_id == case.expected_canonical_field_id
    return case.predicted_canonical_field_id is None


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _ensure_project_root_on_path() -> None:
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


if __name__ == "__main__":
    raise SystemExit(main())
