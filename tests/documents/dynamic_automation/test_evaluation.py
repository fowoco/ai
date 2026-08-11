from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.evaluate_dynamic_mapping import EvaluationCase, evaluate_cases

ROOT = Path(__file__).parents[3]
CASES_PATH = ROOT / "tests" / "fixtures" / "dynamic_automation" / "mapping_cases.jsonl"
CATALOG_PATH = (
    ROOT
    / "app"
    / "documents"
    / "dynamic_automation"
    / "resources"
    / "canonical_fields.v1.yaml"
)


def matched_case(*, correct: bool) -> EvaluationCase:
    return EvaluationCase(
        case_id="matched",
        document_id="document-1",
        expected_status="MATCHED",
        expected_canonical_field_id="worker.phone",
        expected_sensitive=False,
        predicted_status="MATCHED",
        predicted_canonical_field_id=("worker.phone" if correct else "company.phone"),
        candidate_ids=("company.phone", "worker.phone"),
    )


def ambiguous_case(*, correct: bool) -> EvaluationCase:
    return EvaluationCase(
        case_id="ambiguous",
        document_id="document-2",
        expected_status="AMBIGUOUS",
        expected_canonical_field_id=None,
        expected_sensitive=False,
        predicted_status="AMBIGUOUS" if correct else "MATCHED",
        predicted_canonical_field_id=None if correct else "worker.phone",
        candidate_ids=(),
    )


def test_selective_metrics_count_wrong_auto_match() -> None:
    metrics = evaluate_cases([matched_case(correct=False), ambiguous_case(correct=True)])

    assert metrics.auto_precision == 0.0
    assert metrics.coverage == 0.5


def test_metrics_are_derived_from_literal_case_outcomes() -> None:
    cases = [
        EvaluationCase(
            case_id="correct-auto",
            document_id="document-1",
            expected_status="MATCHED",
            expected_canonical_field_id="identity.passport_number",
            expected_sensitive=True,
            predicted_status="MATCHED",
            predicted_canonical_field_id="identity.passport_number",
            candidate_ids=("identity.passport_number",),
        ),
        EvaluationCase(
            case_id="wrong-auto",
            document_id="document-1",
            expected_status="MATCHED",
            expected_canonical_field_id="worker.phone",
            expected_sensitive=False,
            predicted_status="MATCHED",
            predicted_canonical_field_id="company.phone",
            candidate_ids=("company.phone", "worker.phone"),
        ),
        ambiguous_case(correct=True),
        EvaluationCase(
            case_id="non-data",
            document_id="document-2",
            expected_status="NON_DATA",
            expected_canonical_field_id=None,
            expected_sensitive=False,
            predicted_status="NON_DATA",
            predicted_canonical_field_id=None,
            candidate_ids=(),
        ),
        EvaluationCase(
            case_id="deferred-sensitive",
            document_id="document-3",
            expected_status="MATCHED",
            expected_canonical_field_id="identity.alien_registration_number",
            expected_sensitive=True,
            predicted_status="AMBIGUOUS",
            predicted_canonical_field_id=None,
            candidate_ids=("identity.alien_registration_number",),
        ),
    ]

    metrics = evaluate_cases(cases, top_k=2)

    assert metrics.extraction_precision == 1.0
    assert metrics.extraction_recall == 1.0
    assert metrics.top_1_accuracy == pytest.approx(2 / 3)
    assert metrics.top_k_recall == 1.0
    assert metrics.auto_precision == 0.5
    assert metrics.coverage == 0.5
    assert metrics.ambiguous_accuracy == 1.0
    assert metrics.sensitive_field_precision == 1.0
    assert metrics.document_zero_error_rate == pytest.approx(1 / 3)


def test_empty_evaluation_is_deterministic() -> None:
    assert evaluate_cases([]).model_dump() == {
        "extraction_precision": 0.0,
        "extraction_recall": 0.0,
        "top_1_accuracy": 0.0,
        "top_k_recall": 0.0,
        "auto_precision": 0.0,
        "coverage": 0.0,
        "ambiguous_accuracy": 0.0,
        "sensitive_field_precision": 0.0,
        "document_zero_error_rate": 0.0,
    }


def test_rule_mode_cli_writes_json_without_model_packages(tmp_path: Path) -> None:
    output_path = tmp_path / "baseline.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_dynamic_mapping.py",
            "--cases",
            str(CASES_PATH),
            "--catalog",
            str(CATALOG_PATH),
            "--mode",
            "rule",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["mode"] == "rule"
    assert report["catalog_version"] == "v1"
    assert report["metrics"]["auto_precision"] == 1.0
    assert report["metrics"]["coverage"] == 0.5
    assert report["gate"]["passed"] is True
    assert "precision=1.000000" in result.stdout
    assert "coverage=0.500000" in result.stdout
