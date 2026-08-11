from __future__ import annotations

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
from app.documents.dynamic_automation.training import ModelManifest, compare_manifests
from scripts import compare_dynamic_mapping_models as comparison


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
    return ModelManifest(
        model_kind="domain_bi_encoder",
        base_model_repo=QWEN3_EMBEDDING_REPO,
        base_model_revision=QWEN3_EMBEDDING_REVISION,
        dataset_sha256="b" * 64,
        catalog_sha256="c" * 64,
        catalog_version="v1",
        auto_precision=auto_precision,
        sensitive_precision=sensitive_precision,
        coverage=coverage,
        expected_calibration_error=ece,
        p95_latency_ms=p95_ms,
        training_canonical_field_ids=("worker.phone",),
        catalog_field_ids=catalog_field_ids,
        unseen_catalog_field_id=unseen_field,
        unseen_catalog_retrieved=unseen_retrieved,
    )


def baseline_manifest(**updates: float) -> ModelManifest:
    return manifest(**updates).model_copy(update={"model_kind": "qwen_baseline"})


def test_model_is_not_promoted_when_precision_or_calibration_regresses() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(auto_precision=0.995, ece=0.03, p95_ms=200),
        candidate=manifest(auto_precision=0.990, ece=0.04, p95_ms=120),
    )

    assert decision.promote is False
    assert "auto_precision" in decision.reasons
    assert "expected_calibration_error" in decision.reasons


def test_model_is_not_promoted_when_sensitive_precision_regresses() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(sensitive_precision=0.997),
        candidate=manifest(sensitive_precision=0.996, coverage=0.81),
    )

    assert decision.promote is False
    assert "sensitive_precision" in decision.reasons


def test_model_is_not_promoted_without_coverage_or_latency_improvement() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(coverage=0.80, p95_ms=200),
        candidate=manifest(coverage=0.80, p95_ms=200),
    )

    assert decision.promote is False
    assert "coverage_or_p95_latency_ms" in decision.reasons


def test_model_is_not_promoted_without_unseen_catalog_retrieval() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_field=None),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_not_promoted_for_fabricated_unseen_catalog_id() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_field="fabricated.field"),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_not_promoted_when_unseen_retrieval_evidence_is_false() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_retrieved=False),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_not_promoted_when_unseen_field_was_a_training_label() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81, unseen_field="worker.phone"),
    )

    assert decision.promote is False
    assert "unseen_catalog_retrieval" in decision.reasons


def test_model_is_promoted_only_when_every_gate_passes() -> None:
    decision = compare_manifests(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81),
    )

    assert decision.promote is True
    assert decision.reasons == ()


def test_model_is_not_promoted_against_an_unpinned_qwen_manifest() -> None:
    decision = compare_manifests(
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
    decision = compare_manifests(
        baseline=baseline_manifest(),
        candidate=manifest(coverage=0.81).model_copy(
            update={"catalog_sha256": "d" * 64}
        ),
    )

    assert decision.promote is False
    assert "catalog_sha256" in decision.reasons


def test_comparison_cli_writes_deterministic_fail_closed_report(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    output_path = tmp_path / "decision.json"
    baseline_path.write_text(
        baseline_manifest().model_dump_json(indent=2), encoding="utf-8"
    )
    candidate_path.write_text(
        manifest(auto_precision=0.99, coverage=0.82).model_dump_json(indent=2),
        encoding="utf-8",
    )

    exit_code = comparison.main(
        [
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
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
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    output_path = tmp_path / "decision.json"
    baseline_path.write_text(
        baseline_manifest().model_dump_json(indent=2), encoding="utf-8"
    )
    candidate_path.write_text(
        manifest(coverage=0.81).model_dump_json(indent=2), encoding="utf-8"
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/compare_dynamic_mapping_models.py",
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
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
