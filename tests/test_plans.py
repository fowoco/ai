from __future__ import annotations

from pathlib import Path

import pytest

from hwp_mcp.hwpx import DocumentError, analyze_document, extract_text
from hwp_mcp.plans import CellEditInput, EditPlanError, create_edit_plan, validate_edit_plan
from hwp_mcp.server import apply_edit_plan

from test_hwpx import make_table_fixture


def test_create_plan_does_not_create_output(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)

    plan = create_edit_plan(
        source,
        analyze_document(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
                label="업체명",
            )
        ],
    )

    assert plan.status == "WAITING_APPROVAL"
    assert plan.approval_required is True
    assert plan.operations[0].old_value == ""
    assert not (tmp_path / "filled.hwpx").exists()
    validate_edit_plan(plan, source)


def test_plan_rejects_stale_document(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    plan = create_edit_plan(
        source,
        analyze_document(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
            )
        ],
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
        analyze_document(source),
        [
            CellEditInput(
                target_id="section0.table0.row0.cell1",
                expected_text="",
                value="ABC",
            )
        ],
    )

    with pytest.raises(DocumentError, match="명시적 승인"):
        apply_edit_plan("form.hwpx", "filled.hwpx", plan, approved=False)

    result = apply_edit_plan("form.hwpx", "filled.hwpx", plan, approved=True)

    assert result["validated"] is True
    assert "ABC" in extract_text(output)["text"]
