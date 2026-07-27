from __future__ import annotations

import base64
import json
from pathlib import Path

import hwp_mcp.hwpx as hwpx
import pytest

from hwp_mcp.hwpx import DocumentError
from hwp_mcp.integrity import EnvSigningKeyProvider
from hwp_mcp.plans import (
    CellEditInput,
    EditPlanError,
    create_approval_receipt,
    create_edit_plan,
    sha256_file,
)
from hwp_mcp.server import (
    _workflow_services,
    apply_edit_plan,
    confirm_visual_candidates,
)
from hwp_mcp.workspace import prepare_workspace, update_workflow_state, write_json
from analysis_helpers import make_grounded_manifest
from test_hwpx import make_table_fixture


def test_xml_only_analysis_cannot_expose_interview_registry(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)

    assert not hasattr(hwpx, "analyze_document")

    manifest = hwpx._analyze_xml_document(source)

    assert manifest["analysis_stage"] == "XML_ONLY"
    assert "field_registry" not in manifest
    assert manifest["xml_field_candidates"]


def test_stale_analysis_state_cannot_start_interview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    monkeypatch.setenv("HWP_MCP_ROOT", str(tmp_path))
    workspace = prepare_workspace(source)
    write_json(workspace["analysis_dir"] / "field-registry.json", [])
    update_workflow_state(
        workspace["workspace_dir"],
        status="ANALYZED",
        svg_analysis_status="MAPPED",
    )

    with pytest.raises(DocumentError, match="분석 계약"):
        confirm_visual_candidates("form.hwpx", [])


def test_xml_only_analysis_cannot_create_edit_plan(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    manifest = hwpx._analyze_xml_document(source)

    with pytest.raises(EditPlanError, match="rhwp SVG"):
        create_edit_plan(
            source,
            manifest,
            [
                CellEditInput(
                    target_id="section0.table0.row0.cell1",
                    expected_text="",
                    value="ABC",
                )
            ],
            dispositions={
                manifest["xml_field_candidates"][0]["field_id"]: "provided",
            },
        )


def test_apply_rejects_stale_analysis_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    monkeypatch.setenv("HWP_MCP_ROOT", str(tmp_path))
    monkeypatch.setenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "test-v1")
    monkeypatch.setenv(
        "HWP_MCP_SIGNING_KEYS",
        json.dumps(
            {
                "test-v1": base64.b64encode(b"test-signing-key-" * 2).decode(
                    "ascii"
                )
            }
        ),
    )
    workspace = prepare_workspace(source)
    manifest = make_grounded_manifest(workspace["original_path"])
    field = manifest["field_registry"][0]
    plan = create_edit_plan(
        workspace["original_path"],
        manifest,
        [
            CellEditInput(
                field_id=field["field_id"],
                target_id=field["target_id"],
                expected_text="",
                value="ABC",
            )
        ],
        dispositions={field["field_id"]: "provided"},
    )
    document_id, repository, artifacts = _workflow_services(workspace)
    repository.set_analysis_status(document_id, "READY_FOR_INTERVIEW")
    attempt_dir = workspace["attempts_dir"] / plan.plan_id
    attempt_dir.mkdir()
    plan_path = attempt_dir / "edit-plan.json"
    write_json(plan_path, plan.model_dump())
    artifacts.put(plan.plan_id, "edit_plan", plan_path)
    repository.create_plan(document_id, plan.plan_id, sha256_file(plan_path))
    receipt = create_approval_receipt(
        plan,
        plan_path,
        approved_at="2026-07-27T00:00:00+00:00",
        approver_subject="local-interactive-user",
        signer=EnvSigningKeyProvider.from_env(),
    )
    receipt_path = attempt_dir / "approval-receipt.json"
    write_json(receipt_path, receipt.model_dump())
    receipt_artifact = artifacts.put(
        plan.plan_id,
        "approval_receipt",
        receipt_path,
    )
    repository.approve_plan(
        document_id,
        plan.plan_id,
        receipt_sha256=receipt_artifact.sha256,
        approved_at=receipt.approved_at,
    )
    update_workflow_state(
        workspace["workspace_dir"],
        status="APPROVED",
        plan_id=plan.plan_id,
        approved=True,
    )

    with pytest.raises(DocumentError, match="분석 계약"):
        apply_edit_plan("form.hwpx", plan.plan_id)

    assert not (workspace["attempts_dir"] / plan.plan_id / "modified.hwpx").exists()
