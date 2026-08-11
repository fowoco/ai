from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.documents.dynamic_automation.qwen import (
    QWEN3_EMBEDDING_REPO,
    QWEN3_EMBEDDING_REVISION,
)
from app.documents.dynamic_automation.training import (
    EVALUATION_CODE_VERSION,
    TRAINING_CODE_VERSION,
    EvaluationMetricsEvidence,
    HeldOutEvaluationReport,
    ModelManifest,
    UnseenFieldEvidence,
    compare_manifests,
    held_out_evaluation_report_bytes,
    held_out_evaluation_report_sha256,
)
from scripts import compare_dynamic_mapping_models as comparison

ARTIFACT_BYTES = b"deterministic test model artifact\n"
ARTIFACT_SHA256 = hashlib.sha256(ARTIFACT_BYTES).hexdigest()
_REPORTS: dict[str, HeldOutEvaluationReport] = {}


def manifest(
    *,
    auto_precision: float = 0.995,
    sensitive_precision: float = 0.996,
    coverage: float = 0.80,
    ece: float = 0.03,
    p95_ms: float = 200,
    unseen_field: str | None = "worker.email",
    unseen_retrieved: bool = True,
    catalog_field_ids: tuple[str, ...] = (
        "company.phone",
        "worker.email",
        "worker.phone",
    ),
) -> ModelManifest:
    unseen_id = unseen_field or "worker.email"
    candidate_ids = (unseen_id,) if unseen_retrieved and unseen_field is not None else ()
    report = HeldOutEvaluationReport(
        schema_version="dynamic-mapping-held-out-v2",
        evaluation_code_version=EVALUATION_CODE_VERSION,
        model_artifact_sha256=ARTIFACT_SHA256,
        dataset_sha256="b" * 64,
        catalog_sha256="c" * 64,
        catalog_version="v1",
        sample_count=10,
        cohort_count=5,
        model_execution_count=11,
        metrics=EvaluationMetricsEvidence(
            auto_precision=auto_precision,
            sensitive_precision=sensitive_precision,
            coverage=coverage,
            expected_calibration_error=ece,
            p95_latency_ms=p95_ms,
        ),
        unseen_field_evidence=UnseenFieldEvidence(
            case_id=f"generated-unseen:{unseen_id}",
            canonical_field_id=unseen_id,
            query_sha256="d" * 64,
            candidate_ids=candidate_ids,
            retrieved_rank=1 if candidate_ids else None,
        ),
    )
    report_sha256 = held_out_evaluation_report_sha256(report)
    _REPORTS[report_sha256] = report
    return ModelManifest(
        schema_version="dynamic-mapping-model-manifest-v2",
        model_kind="domain_bi_encoder",
        base_model_repo=QWEN3_EMBEDDING_REPO,
        base_model_revision=QWEN3_EMBEDDING_REVISION,
        dataset_sha256="b" * 64,
        catalog_sha256="c" * 64,
        model_artifact_sha256=ARTIFACT_SHA256,
        evaluation_report_sha256=report_sha256,
        catalog_version="v1",
        training_code_version=TRAINING_CODE_VERSION,
        evaluation_code_version=EVALUATION_CODE_VERSION,
        training_sample_count=20,
        evaluation_sample_count=10,
        training_cohort_count=8,
        evaluation_cohort_count=5,
        auto_precision=auto_precision,
        sensitive_precision=sensitive_precision,
        coverage=coverage,
        expected_calibration_error=ece,
        p95_latency_ms=p95_ms,
        training_canonical_field_ids=("worker.phone",),
        catalog_field_ids=catalog_field_ids,
    )


def baseline_manifest(**updates: float) -> ModelManifest:
    return manifest(**updates).model_copy(update={"model_kind": "qwen_baseline"})


def compare_for_test(
    *, baseline: ModelManifest, candidate: ModelManifest
):
    return compare_manifests(
        baseline=baseline,
        candidate=candidate,
        baseline_report=_REPORTS[baseline.evaluation_report_sha256],
        candidate_report=_REPORTS[candidate.evaluation_report_sha256],
        baseline_artifact_sha256=ARTIFACT_SHA256,
        candidate_artifact_sha256=ARTIFACT_SHA256,
        baseline_report_sha256=baseline.evaluation_report_sha256,
        candidate_report_sha256=candidate.evaluation_report_sha256,
    )


def write_evidence_files(
    directory: Path, name: str, model_manifest: ModelManifest
) -> tuple[Path, Path, Path]:
    manifest_path = directory / f"{name}-manifest.json"
    report_path = directory / f"{name}-report.json"
    artifact_path = directory / f"{name}-artifact.json"
    manifest_path.write_text(model_manifest.model_dump_json(indent=2), encoding="utf-8")
    report_path.write_bytes(
        held_out_evaluation_report_bytes(
            _REPORTS[model_manifest.evaluation_report_sha256]
        )
    )
    artifact_path.write_bytes(ARTIFACT_BYTES)
    return manifest_path, report_path, artifact_path


def test_model_is_not_promoted_when_precision_or_calibration_regresses() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(auto_precision=0.995, ece=0.03, p95_ms=200),
        candidate=manifest(auto_precision=0.990, ece=0.04, p95_ms=120),
    )

    assert decision.promote is False
    assert "auto_precision" in decision.reasons
    assert "expected_calibration_error" in decision.reasons


def test_model_is_not_promoted_when_sensitive_precision_regresses() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(sensitive_precision=0.997),
        candidate=manifest(sensitive_precision=0.996, coverage=0.81),
    )

    assert decision.promote is False
    assert "sensitive_precision" in decision.reasons


def test_model_is_not_promoted_without_coverage_or_latency_improvement() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(coverage=0.80, p95_ms=200),
        candidate=manifest(coverage=0.80, p95_ms=200),
    )

    assert decision.promote is False
    assert "coverage_or_p95_latency_ms" in decision.reasons


def test_model_is_not_promoted_for_catastrophic_coverage_loss_with_latency_gain() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(coverage=0.80, p95_ms=200),
        candidate=manifest(coverage=0.01, p95_ms=199),
    )

    assert decision.promote is False
    assert "coverage" in decision.reasons


def test_model_is_not_promoted_for_latency_regression_with_coverage_gain() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(coverage=0.80, p95_ms=200),
        candidate=manifest(coverage=0.81, p95_ms=999),
    )

    assert decision.promote is False
    assert "p95_latency_ms" in decision.reasons


def test_model_is_not_promoted_without_unseen_catalog_retrieval() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_field=None),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_not_promoted_for_fabricated_unseen_catalog_id() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_field="fabricated.field"),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_not_promoted_when_unseen_retrieval_evidence_is_false() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_retrieved=False),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_not_promoted_when_unseen_field_was_a_training_label() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_field="worker.phone"),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_promoted_only_when_every_gate_passes() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81),
    )

    assert decision.promote is True
    assert decision.reasons == ()


def test_model_is_not_promoted_against_an_unpinned_qwen_manifest() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest().model_copy(
            update={"base_model_revision": "unreviewed"}
        ),
        candidate=manifest(coverage=0.81),
    )

    assert decision.promote is False
    assert "base_model_manifest" in decision.reasons


@pytest.mark.parametrize("catalog_sha256", (None, "0" * 64))
def test_model_manifest_requires_a_nonzero_catalog_hash(
    catalog_sha256: str | None,
) -> None:
    payload = manifest().model_dump(mode="json")
    if catalog_sha256 is None:
        payload.pop("catalog_sha256")
    else:
        payload["catalog_sha256"] = catalog_sha256

    with pytest.raises(ValidationError):
        ModelManifest.model_validate(payload)


def test_model_is_not_promoted_when_catalog_hashes_differ() -> None:
    decision = compare_for_test(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81).model_copy(
            update={"catalog_sha256": "d" * 64}
        ),
    )

    assert decision.promote is False
    assert "catalog_sha256" in decision.reasons


def test_model_manifest_rejects_disconnected_boolean_unseen_evidence() -> None:
    payload = manifest().model_dump(mode="json")
    payload["unseen_catalog_retrieved"] = True

    with pytest.raises(ValidationError):
        ModelManifest.model_validate(payload)


def test_comparison_rejects_report_hash_not_bound_to_manifest() -> None:
    baseline = baseline_manifest()
    candidate = manifest(coverage=0.81)
    candidate_report = _REPORTS[candidate.evaluation_report_sha256]

    decision = compare_manifests(
        baseline=baseline,
        candidate=candidate,
        baseline_report=_REPORTS[baseline.evaluation_report_sha256],
        candidate_report=candidate_report,
        baseline_artifact_sha256=ARTIFACT_SHA256,
        candidate_artifact_sha256=ARTIFACT_SHA256,
        baseline_report_sha256=baseline.evaluation_report_sha256,
        candidate_report_sha256="f" * 64,
    )

    assert decision.promote is False
    assert "candidate_evaluation_evidence" in decision.reasons


def test_comparison_fails_closed_without_exact_evidence_byte_hashes() -> None:
    baseline = baseline_manifest()
    candidate = manifest(coverage=0.81)

    decision = compare_manifests(
        baseline=baseline,
        candidate=candidate,
        baseline_report=_REPORTS[baseline.evaluation_report_sha256],
        candidate_report=_REPORTS[candidate.evaluation_report_sha256],
    )

    assert decision.promote is False
    assert decision.reasons == (
        "baseline_evaluation_evidence",
        "candidate_evaluation_evidence",
    )


def test_comparison_cli_writes_deterministic_fail_closed_report(tmp_path: Path) -> None:
    output_path = tmp_path / "decision.json"
    baseline_path, baseline_report, baseline_artifact = write_evidence_files(
        tmp_path, "baseline", baseline_manifest()
    )
    candidate_path, candidate_report, candidate_artifact = write_evidence_files(
        tmp_path,
        "candidate",
        manifest(auto_precision=0.99, coverage=0.82),
    )

    exit_code = comparison.main(
        [
            "--baseline",
            str(baseline_path),
            "--baseline-artifact",
            str(baseline_artifact),
            "--baseline-report",
            str(baseline_report),
            "--candidate",
            str(candidate_path),
            "--candidate-artifact",
            str(candidate_artifact),
            "--candidate-report",
            str(candidate_report),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "promote": False,
        "reasons": ["auto_precision"],
    }


def test_comparison_script_runs_from_project_root(tmp_path: Path) -> None:
    root = Path(__file__).parents[3]
    output_path = tmp_path / "decision.json"
    baseline_path, baseline_report, baseline_artifact = write_evidence_files(
        tmp_path, "baseline", baseline_manifest()
    )
    candidate_path, candidate_report, candidate_artifact = write_evidence_files(
        tmp_path, "candidate", manifest(coverage=0.81)
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/compare_dynamic_mapping_models.py",
            "--baseline",
            str(baseline_path),
            "--baseline-artifact",
            str(baseline_artifact),
            "--baseline-report",
            str(baseline_report),
            "--candidate",
            str(candidate_path),
            "--candidate-artifact",
            str(candidate_artifact),
            "--candidate-report",
            str(candidate_report),
            "--output",
            str(output_path),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "promote": True,
        "reasons": [],
    }
