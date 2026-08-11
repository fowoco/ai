from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import scripts.evaluate_dynamic_mapping as evaluation
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


class SemanticEmbeddingBackend:
    """Complete deterministic stand-in for the unavailable local Qwen encoder."""

    def __init__(self) -> None:
        self.query_batches = 0
        self.document_batches = 0

    def encode_queries(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        assert max_length == 512
        assert batch_size == 8
        self.query_batches += 1
        return tuple((1.0, 0.0) for _ in texts)

    def encode_documents(
        self,
        texts: Sequence[str],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]:
        assert max_length == 512
        assert batch_size == 8
        self.document_batches += 1
        return tuple(
            (1.0, 0.0) if "canonical field: company.phone" in text else (0.0, 1.0)
            for text in texts
        )


class SemanticRerankerBackend:
    """Complete deterministic stand-in for the unavailable local Qwen reranker."""

    def __init__(self) -> None:
        self.pair_batches = 0

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        max_length: int,
        batch_size: int,
    ) -> tuple[float, ...]:
        assert max_length == 512
        assert batch_size == 8
        self.pair_batches += 1
        scores: list[float] = []
        for query, definition in pairs:
            if "Employer contact line" in query:
                scores.append(0.99 if "company.phone" in definition else 0.20)
            else:
                scores.append(0.75 if "company.phone" in definition else 0.74)
        return tuple(scores)


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


def test_auto_precision_counts_false_match_on_expected_non_data() -> None:
    correct_sensitive = EvaluationCase(
        case_id="correct-sensitive",
        document_id="document-1",
        expected_status="MATCHED",
        expected_canonical_field_id="identity.passport_number",
        expected_sensitive=True,
        predicted_status="MATCHED",
        predicted_canonical_field_id="identity.passport_number",
        candidate_ids=("identity.passport_number",),
    )
    false_non_data = EvaluationCase(
        case_id="false-non-data",
        document_id="document-2",
        expected_status="NON_DATA",
        expected_canonical_field_id=None,
        expected_sensitive=False,
        predicted_status="MATCHED",
        predicted_canonical_field_id="company.phone",
        candidate_ids=("company.phone",),
    )

    metrics = evaluate_cases([correct_sensitive, false_non_data])

    assert metrics.auto_precision == 0.5
    assert metrics.coverage == 1.0


def test_cli_exits_two_when_auto_precision_is_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = (
        EvaluationCase(
            case_id="correct-sensitive",
            document_id="document-1",
            expected_status="MATCHED",
            expected_canonical_field_id="identity.passport_number",
            expected_sensitive=True,
            predicted_status="MATCHED",
            predicted_canonical_field_id="identity.passport_number",
            candidate_ids=("identity.passport_number",),
        ),
        EvaluationCase(
            case_id="false-non-data",
            document_id="document-2",
            expected_status="NON_DATA",
            expected_canonical_field_id=None,
            expected_sensitive=False,
            predicted_status="MATCHED",
            predicted_canonical_field_id="company.phone",
            candidate_ids=("company.phone",),
        ),
    )
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("", encoding="utf-8")
    output_path = tmp_path / "report.json"
    monkeypatch.setattr(
        evaluation,
        "_run_cases",
        lambda *_args, **_kwargs: (SimpleNamespace(version="v1"), cases),
    )

    exit_code = evaluation.main(
        [
            "--cases",
            str(cases_path),
            "--catalog",
            "unused.yaml",
            "--mode",
            "rule",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert json.loads(output_path.read_text(encoding="utf-8"))["gate"]["passed"] is False


def test_sensitive_precision_counts_false_assignment_into_sensitive_target() -> None:
    correct_non_sensitive = EvaluationCase(
        case_id="correct-company-phone",
        document_id="document-1",
        expected_status="MATCHED",
        expected_canonical_field_id="company.phone",
        expected_sensitive=False,
        predicted_status="MATCHED",
        predicted_canonical_field_id="company.phone",
        predicted_sensitive=False,
        candidate_ids=("company.phone",),
    )
    false_sensitive_target = EvaluationCase(
        case_id="wrong-passport-target",
        document_id="document-2",
        expected_status="MATCHED",
        expected_canonical_field_id="company.phone",
        expected_sensitive=False,
        predicted_status="MATCHED",
        predicted_canonical_field_id="identity.passport_number",
        predicted_sensitive=True,
        candidate_ids=("identity.passport_number", "company.phone"),
    )

    metrics = evaluate_cases([correct_non_sensitive, false_sensitive_target])

    assert metrics.auto_precision == 0.5
    assert metrics.sensitive_field_precision == 0.0


def test_cli_exits_two_when_sensitive_precision_is_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    correct = tuple(
        EvaluationCase(
            case_id=f"correct-{index}",
            document_id=f"document-{index}",
            expected_status="MATCHED",
            expected_canonical_field_id="company.phone",
            expected_sensitive=False,
            predicted_status="MATCHED",
            predicted_canonical_field_id="company.phone",
            predicted_sensitive=False,
            candidate_ids=("company.phone",),
        )
        for index in range(100)
    )
    false_sensitive_target = EvaluationCase(
        case_id="wrong-passport-target",
        document_id="document-sensitive-error",
        expected_status="MATCHED",
        expected_canonical_field_id="company.phone",
        expected_sensitive=False,
        predicted_status="MATCHED",
        predicted_canonical_field_id="identity.passport_number",
        predicted_sensitive=True,
        candidate_ids=("identity.passport_number", "company.phone"),
    )
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text("", encoding="utf-8")
    output_path = tmp_path / "report.json"
    monkeypatch.setattr(
        evaluation,
        "_run_cases",
        lambda *_args, **_kwargs: (
            SimpleNamespace(version="v1"),
            (*correct, false_sensitive_target),
        ),
    )

    exit_code = evaluation.main(
        [
            "--cases",
            str(cases_path),
            "--catalog",
            "unused.yaml",
            "--mode",
            "rule",
            "--output",
            str(output_path),
        ]
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert report["metrics"]["auto_precision"] == 0.9900990099009901
    assert report["metrics"]["sensitive_field_precision"] == 0.0
    assert report["gate"]["passed"] is False


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


@pytest.mark.parametrize(
    "updates",
    (
        {"expected_canonical_field_id": "identity." + "x" * 200},
        {"predicted_canonical_field_id": "identity." + "x" * 200},
        {"candidate_ids": ("identity." + "x" * 200,)},
    ),
)
def test_evaluation_bounds_canonical_and_candidate_ids(
    updates: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "case_id": "bounded-case",
        "document_id": "bounded-document",
        "expected_status": "MATCHED",
        "expected_canonical_field_id": "company.phone",
        "expected_sensitive": False,
        "predicted_status": "MATCHED",
        "predicted_canonical_field_id": "company.phone",
        "candidate_ids": ("company.phone",),
    }
    payload.update(updates)

    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(payload)


def test_cli_rejects_unbounded_fixture_context_before_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "case_id": "oversized-context",
                "document_id": "document-1",
                "context": {
                    "field_id": "field-1",
                    "label": "x" * 201,
                    "normalized_label": "x" * 200,
                    "field_type": "text",
                    "document_title": "Application",
                    "section": "Company",
                    "row_labels": ["Company"],
                    "nearby_labels": [],
                    "options": [],
                    "repeat_index": 0,
                    "required": True,
                    "kind": "text_field",
                },
                "expected_status": "MATCHED",
                "expected_canonical_field_id": "company.name",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "report.json"
    monkeypatch.setattr(
        evaluation,
        "_run_cases",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unbounded fixture reached mapping")
        ),
    )

    exit_code = evaluation.main(
        [
            "--cases",
            str(cases_path),
            "--catalog",
            "unused.yaml",
            "--mode",
            "rule",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assert not output_path.exists()


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
    assert report["metrics"]["coverage"] == 0.4
    assert report["gate"]["passed"] is True
    assert "precision=1.000000" in result.stdout
    assert "coverage=0.400000" in result.stdout


def test_qwen_cli_fails_closed_when_lazy_model_inference_never_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UnavailableSentenceTransformer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("model cache is unavailable")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=UnavailableSentenceTransformer),
    )
    model_cache = tmp_path / "missing-model-cache"
    embedding_path = (
        model_cache
        / "qwen3-embedding-0.6b"
        / "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    )
    reranker_path = (
        model_cache
        / "qwen3-reranker-0.6b"
        / "e61197ed45024b0ed8a2d74b80b4d909f1255473"
    )
    monkeypatch.setenv("FOWOCO_QWEN3_EMBEDDING_PATH", str(embedding_path))
    monkeypatch.setenv("FOWOCO_QWEN3_RERANKER_PATH", str(reranker_path))
    monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(model_cache))
    monkeypatch.setenv("FOWOCO_DYNAMIC_AUTOMATION_MAPPING_ENABLED", "true")
    output_path = tmp_path / "false-green-report.json"

    exit_code = evaluation.main(
        [
            "--cases",
            str(CASES_PATH),
            "--catalog",
            str(CATALOG_PATH),
            "--mode",
            "qwen",
            "--output",
            str(output_path),
        ]
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert report["model_execution"] == {
        "embedding_success_count": 0,
        "reranker_success_count": 0,
        "required": True,
        "semantic_case_count": 1,
        "semantic_case_pass_count": 0,
    }
    assert report["gate"]["passed"] is False


def test_qwen_cli_uses_documented_settings_and_records_fake_backend_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_cache = tmp_path / "model-cache"
    monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(model_cache))
    monkeypatch.setenv("FOWOCO_DYNAMIC_AUTOMATION_MAPPING_ENABLED", "true")
    monkeypatch.delenv("FOWOCO_QWEN3_EMBEDDING_PATH", raising=False)
    monkeypatch.delenv("FOWOCO_QWEN3_RERANKER_PATH", raising=False)
    embedding = SemanticEmbeddingBackend()
    reranker = SemanticRerankerBackend()
    output_path = tmp_path / "qwen-report.json"

    exit_code = evaluation.main(
        [
            "--cases",
            str(CASES_PATH),
            "--catalog",
            str(CATALOG_PATH),
            "--mode",
            "qwen",
            "--output",
            str(output_path),
        ],
        embedding_backend=embedding,
        reranker_backend=reranker,
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert embedding.query_batches > 0
    assert embedding.document_batches > 0
    assert reranker.pair_batches > 0
    assert report["model_execution"] == {
        "embedding_success_count": 2,
        "reranker_success_count": 2,
        "required": True,
        "semantic_case_count": 1,
        "semantic_case_pass_count": 1,
    }
    assert report["gate"]["passed"] is True
