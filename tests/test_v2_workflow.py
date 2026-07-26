from __future__ import annotations

from pathlib import Path
import zipfile

from PIL import Image, ImageDraw
import pytest

from hwp_mcp.compare import generate_visual_diff
from hwp_mcp.fields import infer_all_fields
from hwp_mcp.hwpx import DocumentError, analyze_document, apply_typed_edits
from hwp_mcp.plans import (
    CellEditInput,
    EditPlanError,
    create_edit_plan,
    sha256_file,
)
from hwp_mcp.server import confirm_visual_candidates
from hwp_mcp.workspace import (
    finalize_attempt,
    prepare_workspace,
    update_workflow_state,
    write_json,
)

from test_hwpx import NS, make_table_fixture


def _make_grid_fixture(path: Path) -> None:
    cells = [
        "<hp:tc><hp:p><hp:run><hp:t>등록번호</hp:t></hp:run></hp:p></hp:tc>",
        *[
            "<hp:tc><hp:p><hp:run><hp:t></hp:t></hp:run></hp:p></hp:tc>"
            for _ in range(4)
        ],
    ]
    section = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hs:sec xmlns:hs="{NS["hs"]}" xmlns:hp="{NS["hp"]}">'
        f"<hp:tbl><hp:tr>{''.join(cells)}</hp:tr></hp:tbl></hs:sec>"
    ).encode()
    header = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hh:head xmlns:hh="{NS["hh"]}" secCnt="1" />'
    ).encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr(
            "Contents/content.hpf",
            b'<?xml version="1.0"?><package />',
        )
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)


def test_registry_v2_detects_grid_without_specific_label(tmp_path: Path) -> None:
    source = tmp_path / "grid.hwpx"
    _make_grid_fixture(source)

    registry = infer_all_fields(analyze_document(source))
    grids = [field for field in registry if field["kind"] == "character_grid"]

    assert len(grids) == 1
    assert grids[0]["constraints"]["slot_count"] == 4
    assert len(grids[0]["xml_segments"]) == 4
    assert grids[0]["disposition"] is None


def test_registry_embedded_field_anchors_are_unique() -> None:
    sample = next(
        (
            path
            for path in Path("samples").glob("*.hwpx")
            if "Standard_Labor_Contract" in path.name
        ),
        None,
    )
    if sample is None:
        return

    registry = analyze_document(sample)["field_registry"]
    embedded = [
        field
        for field in registry
        if field["constraints"].get("replacement_token")
    ]

    assert embedded
    assert all(
        field["current_text"].count(field["constraints"]["anchor"]) == 1
        for field in embedded
    )


def test_plan_requires_a_disposition_for_every_registry_field(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    manifest = analyze_document(source)

    with pytest.raises(EditPlanError, match="disposition"):
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
            dispositions={},
        )


def test_only_confirmed_visual_candidate_can_extend_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    monkeypatch.setenv("HWP_MCP_ROOT", str(tmp_path))
    workspace = prepare_workspace(source)
    write_json(
        workspace["analysis_dir"] / "field-registry.json",
        analyze_document(source)["field_registry"],
    )
    update_workflow_state(
        workspace["workspace_dir"],
        status="ANALYZED",
        svg_analysis_status="MAPPED",
    )

    result = confirm_visual_candidates(
        "form.hwpx",
        [
            {
                "candidate_id": "vision-1",
                "decision": "confirmed",
                "field": {
                    "field_id": "vision.confirmed.field",
                    "target_id": "section0.table0.row0.cell1",
                    "label": "사람 확인 필드",
                    "type": "text",
                    "kind": "text_field",
                    "category": "step1_application",
                    "row": 0,
                    "column": 1,
                    "current_text": "",
                    "required": False,
                    "xml_segments": ["section0.table0.row0.cell1"],
                    "visual_regions": ["page_001:10,10,20,20"],
                    "constraints": {},
                },
            }
        ],
    )

    assert result["alignment_status"] == "CONSISTENT"
    assert any(
        field["field_id"] == "vision.confirmed.field"
        for field in result["field_registry"]
    )


def test_typed_character_grid_writes_one_character_per_cell(tmp_path: Path) -> None:
    source = tmp_path / "grid.hwpx"
    output = tmp_path / "grid-edited.hwpx"
    _make_grid_fixture(source)
    manifest = analyze_document(source)
    field = next(
        item for item in manifest["field_registry"] if item["kind"] == "character_grid"
    )
    plan = create_edit_plan(
        source,
        manifest,
        [
            CellEditInput(
                field_id=field["field_id"],
                target_id=field["target_id"],
                expected_text="",
                value="1234",
            )
        ],
        dispositions={field["field_id"]: "provided"},
    )

    result = apply_typed_edits(
        source,
        output,
        [operation.model_dump() for operation in plan.operations],
    )
    edited = analyze_document(output)
    cells = edited["sections"][0]["tables"][0]["cells"]

    assert result["applied"] == 1
    assert [cell["text"] for cell in cells[1:]] == list("1234")


def test_typed_anchor_must_match_exactly_once(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    output = tmp_path / "edited.hwpx"
    make_table_fixture(source)
    operation = {
        "operation": "replace_text_range",
        "target_id": "section0.table0.row0.cell0",
        "field_id": "label",
        "old_value": "업체명",
        "new_value": "회사명",
        "anchor": "없는앵커",
        "expected_match_count": 1,
        "xml_segments": ["section0.table0.row0.cell0"],
        "postcondition": "value_once",
        "confidence": "confirmed",
    }

    with pytest.raises(DocumentError, match="1회"):
        apply_typed_edits(source, output, [operation])

    assert not output.exists()


def test_workspace_copies_original_and_finalizes_only_after_vision_pass(
    tmp_path: Path,
) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    workspace = prepare_workspace(source)
    attempt = workspace["workspace_dir"] / "attempts" / "plan-1"
    attempt.mkdir(parents=True)
    modified = attempt / "modified.hwpx"
    modified.write_bytes(source.read_bytes())
    write_json(
        attempt / "verification-report.json",
        {"status": "PENDING_VISION_REVIEW"},
    )
    update_workflow_state(
        workspace["workspace_dir"],
        status="PENDING_VISION_REVIEW",
        plan_id="plan-1",
        modified_path=str(modified),
    )

    with pytest.raises(DocumentError, match="Vision PASS"):
        finalize_attempt(workspace["workspace_dir"], "plan-1")
    assert not (workspace["workspace_dir"] / "final").exists()

    vision_review = {
        "source": "mcp_sampling",
        "plan_id": "plan-1",
        "modified_sha256": sha256_file(modified),
        "verdict": "PASS",
    }
    vision_path = attempt / "vision-review.json"
    write_json(vision_path, vision_review)
    update_workflow_state(
        workspace["workspace_dir"],
        status="PENDING_VISION_REVIEW",
        plan_id="plan-1",
        modified_path=str(modified),
        vision_status="PASS",
        vision_review_path=str(vision_path),
        vision_review_sha256=sha256_file(vision_path),
    )
    write_json(vision_path, {**vision_review, "verdict": "FAIL"})
    with pytest.raises(DocumentError, match="무결성"):
        finalize_attempt(workspace["workspace_dir"], "plan-1")

    write_json(vision_path, vision_review)
    update_workflow_state(
        workspace["workspace_dir"],
        status="PENDING_VISION_REVIEW",
        plan_id="plan-1",
        modified_path=str(modified),
        vision_status="PASS",
        vision_review_path=str(vision_path),
        vision_review_sha256=sha256_file(vision_path),
    )
    finalized = finalize_attempt(workspace["workspace_dir"], "plan-1")

    assert source.exists()
    assert workspace["original_path"].read_bytes() == source.read_bytes()
    assert finalized["status"] == "VERIFIED_FINAL"
    assert Path(finalized["final_path"]).exists()


def test_visual_diff_reports_separate_components(tmp_path: Path) -> None:
    original = tmp_path / "original.png"
    modified = tmp_path / "modified.png"
    diff = tmp_path / "diff.png"
    Image.new("RGB", (100, 100), "white").save(original)
    image = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 20, 20), fill="black")
    draw.rectangle((70, 70, 80, 80), fill="black")
    image.save(modified)

    result = generate_visual_diff(
        original,
        modified,
        diff,
        {"field-1": [5, 5, 25, 25]},
    )

    assert len(result["components"]) == 2
    assert result["components"][0]["related_field_ids"] == ["field-1"]
    assert result["components"][1]["related_field_ids"] == []
