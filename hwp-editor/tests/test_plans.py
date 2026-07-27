from __future__ import annotations

from pathlib import Path

import pytest

from hwp_mcp.integrity import EnvSigningKeyProvider
from hwp_mcp.plans import (
    CellEditInput,
    EditPlanError,
    create_approval_receipt,
    create_edit_plan,
    validate_approval_receipt,
    validate_edit_plan,
)
from hwp_mcp.workspace import write_json

from test_hwpx import make_table_fixture
from analysis_helpers import make_grounded_manifest


def _signer() -> EnvSigningKeyProvider:
    return EnvSigningKeyProvider("v1", {"v1": b"a" * 32})


def test_create_plan_does_not_create_output(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)

    plan = create_edit_plan(
        source,
        make_grounded_manifest(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
                label="업체명",
            )
        ],
        dispositions={"section0.table0.row0.cell1.blank": "provided"},
    )

    assert plan.status == "WAITING_APPROVAL"
    assert plan.version == 2
    assert plan.approval_required is True
    assert plan.operations[0].operation == "replace_text_range"
    assert plan.operations[0].old_value == ""
    assert not (tmp_path / "filled.hwpx").exists()
    validate_edit_plan(plan, source)


def test_plan_rejects_stale_document(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    plan = create_edit_plan(
        source,
        make_grounded_manifest(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
            )
        ],
        dispositions={"section0.table0.row0.cell1.blank": "provided"},
    )
    source.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises(EditPlanError, match="원본 문서가"):
        validate_edit_plan(plan, source)


def test_plan_requires_server_approval_receipt(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    plan = create_edit_plan(
        source,
        make_grounded_manifest(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
            )
        ],
        dispositions={"section0.table0.row0.cell1.blank": "provided"},
    )
    plan_path = tmp_path / "edit-plan.json"
    receipt_path = tmp_path / "approval-receipt.json"
    write_json(plan_path, plan.model_dump())

    with pytest.raises(EditPlanError, match="승인 receipt"):
        validate_approval_receipt(plan, plan_path, receipt_path, signer=_signer())


def test_approval_receipt_is_bound_to_stored_plan(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    plan = create_edit_plan(
        source,
        make_grounded_manifest(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
            )
        ],
        dispositions={"section0.table0.row0.cell1.blank": "provided"},
    )
    plan_path = tmp_path / "edit-plan.json"
    receipt_path = tmp_path / "approval-receipt.json"
    write_json(plan_path, plan.model_dump())
    receipt = create_approval_receipt(
        plan,
        plan_path,
        approved_at="2026-07-27T00:00:00+00:00",
        approver_subject="local-interactive-user",
        signer=_signer(),
    )
    write_json(receipt_path, receipt.model_dump())
    write_json(plan_path, {**plan.model_dump(), "operations": []})

    with pytest.raises(EditPlanError, match="무결성"):
        validate_approval_receipt(plan, plan_path, receipt_path, signer=_signer())


def test_approval_receipt_rejects_forged_signature(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    plan = create_edit_plan(
        source,
        make_grounded_manifest(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
            )
        ],
        dispositions={"section0.table0.row0.cell1.blank": "provided"},
    )
    plan_path = tmp_path / "edit-plan.json"
    receipt_path = tmp_path / "approval-receipt.json"
    write_json(plan_path, plan.model_dump())
    receipt = create_approval_receipt(
        plan,
        plan_path,
        approved_at="2026-07-27T00:00:00+00:00",
        approver_subject="local-interactive-user",
        signer=_signer(),
    )
    forged = receipt.model_dump()
    forged["signature"]["value"] = "A" * 44
    write_json(receipt_path, forged)

    with pytest.raises(EditPlanError, match="서명"):
        validate_approval_receipt(plan, plan_path, receipt_path, signer=_signer())


def test_plan_rejects_unit_inside_prefix_unit_amount(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    manifest = make_grounded_manifest(source)
    field = manifest["field_registry"][0]
    field["type"] = "amount"
    field["constraints"].update({"mode": "prefix_unit", "anchor": "만원"})

    with pytest.raises(EditPlanError, match="단위를 제외한 숫자"):
        create_edit_plan(
            source,
            manifest,
            [
                CellEditInput(
                    field_id=field["field_id"],
                    target_id=field["target_id"],
                    expected_text="",
                    value="4000만원",
                )
            ],
            dispositions={field["field_id"]: "provided"},
        )


def test_plan_rejects_invalid_calendar_date(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    manifest = make_grounded_manifest(source)
    field = manifest["field_registry"][0]
    field["type"] = "date"
    field["kind"] = "date_segments"
    field["constraints"]["mode"] = "empty_cell"

    with pytest.raises(EditPlanError, match="유효한 날짜"):
        create_edit_plan(
            source,
            manifest,
            [
                CellEditInput(
                    field_id=field["field_id"],
                    target_id=field["target_id"],
                    expected_text="",
                    value="2026-02-31",
                )
            ],
            dispositions={field["field_id"]: "provided"},
        )


def test_plan_rejects_ambiguous_checkbox_without_anchor(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source, label="[ ] 남 [ ] 여")
    manifest = make_grounded_manifest(source)
    field = manifest["field_registry"][0]
    field["type"] = "checkbox"
    field["kind"] = "checkbox"
    field["current_text"] = "[ ] 남 [ ] 여"

    with pytest.raises(EditPlanError, match="checkbox marker"):
        create_edit_plan(
            source,
            manifest,
            [
                CellEditInput(
                    field_id=field["field_id"],
                    target_id=field["target_id"],
                    expected_text="[ ] 남 [ ] 여",
                    value="selected",
                )
            ],
            dispositions={field["field_id"]: "provided"},
        )


def test_plan_preserves_example_value_origin(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    manifest = make_grounded_manifest(source)
    field = manifest["field_registry"][0]

    plan = create_edit_plan(
        source,
        manifest,
        [
            CellEditInput(
                field_id=field["field_id"],
                target_id=field["target_id"],
                expected_text="",
                value="예시 업체",
                value_origin="example",
            )
        ],
        dispositions={field["field_id"]: "provided"},
    )

    assert plan.operations[0].value_origin == "example"
