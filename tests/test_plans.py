from __future__ import annotations

from pathlib import Path

import pytest

from hwp_mcp.hwpx import DocumentError
from hwp_mcp.plans import CellEditInput, EditPlanError, create_edit_plan, validate_edit_plan
from hwp_mcp.server import apply_edit_plan

from test_hwpx import make_table_fixture
from analysis_helpers import make_grounded_manifest


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


def test_plan_operations_can_be_applied_only_after_external_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "form.hwpx"
    output = tmp_path / "filled.hwpx"
    make_table_fixture(source)
    monkeypatch.setenv("HWP_MCP_ROOT", str(tmp_path))
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

    with pytest.raises(DocumentError, match="명시적 승인"):
        apply_edit_plan("form.hwpx", "filled.hwpx", plan, approved=False)

    assert not output.exists()


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
