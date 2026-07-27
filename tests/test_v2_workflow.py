from __future__ import annotations

from pathlib import Path
import zipfile

from PIL import Image, ImageDraw
import pytest

from hwp_mcp.compare import generate_visual_diff, validate_typed_postconditions
from hwp_mcp.fields import infer_all_fields
from hwp_mcp.hwpx import DocumentError, _analyze_xml_document, apply_typed_edits
from hwp_mcp.plans import (
    CellEditInput,
    EditPlanError,
    create_edit_plan,
    sha256_file,
)
from hwp_mcp.server import confirm_visual_candidates
from hwp_mcp.vision import (
    VisionImage,
    VisionView,
    build_vision_review_request,
    parse_vision_decision,
)
from hwp_mcp.workspace import (
    finalize_attempt,
    prepare_workspace,
    update_workflow_state,
    write_json,
)

from test_hwpx import NS, make_table_fixture
from analysis_helpers import make_grounded_manifest


def test_vision_rejects_same_reason_for_every_field() -> None:
    response = (
        '{"verdict":"PASS","summary":"검토 완료","fields":['
        '{"field_id":"amount","verdict":"PASS","reason":"생년월일 분할 입력"},'
        '{"field_id":"occupation","verdict":"PASS","reason":"생년월일 분할 입력"}'
        "]}"
    )

    with pytest.raises(DocumentError, match="같은 reason"):
        parse_vision_decision(response, ["amount", "occupation"])


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


def test_typed_date_segments_write_three_empty_cells(tmp_path: Path) -> None:
    source = tmp_path / "date.hwpx"
    output = tmp_path / "date-edited.hwpx"
    _make_grid_fixture(source)
    segments = [
        f"section0.table0.row0.cell{column}"
        for column in range(1, 4)
    ]
    operation = {
        "operation": "set_date_segments",
        "field_id": "birth-date",
        "target_id": segments[0],
        "old_value": "",
        "new_value": "1995-08-20",
        "expected_match_count": 1,
        "xml_segments": segments,
        "constraints": {"mode": "empty_cells"},
        "postcondition": "value_once",
        "confidence": "confirmed",
    }

    apply_typed_edits(source, output, [operation])

    cells = _analyze_xml_document(output)["sections"][0]["tables"][0]["cells"]
    assert [cell["text"] for cell in cells[1:4]] == ["1995", "08", "20"]


def test_typed_date_segments_reject_single_non_inline_cell(tmp_path: Path) -> None:
    source = tmp_path / "date.hwpx"
    output = tmp_path / "date-edited.hwpx"
    _make_grid_fixture(source)
    operation = {
        "operation": "set_date_segments",
        "field_id": "birth-date",
        "target_id": "section0.table0.row0.cell1",
        "old_value": "",
        "new_value": "1995-08-20",
        "expected_match_count": 1,
        "xml_segments": ["section0.table0.row0.cell1"],
        "constraints": {},
        "postcondition": "value_once",
        "confidence": "confirmed",
    }

    with pytest.raises(DocumentError, match="inline"):
        apply_typed_edits(source, output, [operation])

    assert not output.exists()


def test_single_empty_date_cell_uses_validated_date_operation(tmp_path: Path) -> None:
    source = tmp_path / "date.hwpx"
    output = tmp_path / "date-edited.hwpx"
    make_table_fixture(source, label="Passport Issue Date")
    manifest = make_grounded_manifest(source)
    field = next(item for item in manifest["field_registry"] if item["type"] == "date")
    plan = create_edit_plan(
        source,
        manifest,
        [
            CellEditInput(
                field_id=field["field_id"],
                target_id=field["target_id"],
                expected_text="",
                value="2020-01-02",
            )
        ],
        dispositions={field["field_id"]: "provided"},
    )
    operation = plan.operations[0]

    assert operation.operation == "set_date_segments"
    assert operation.constraints["mode"] == "empty_cell"

    apply_typed_edits(source, output, [operation.model_dump()])

    cells = _analyze_xml_document(output)["sections"][0]["tables"][0]["cells"]
    assert cells[1]["text"] == "2020-01-02"


def test_single_empty_date_postcondition_requires_exact_value(tmp_path: Path) -> None:
    source = tmp_path / "date.hwpx"
    make_table_fixture(source, label="Passport Issue Date")
    manifest = _analyze_xml_document(source)
    manifest["sections"][0]["tables"][0]["cells"][1]["text"] = "2020-invalid"
    operation = {
        "operation": "set_date_segments",
        "field_id": "passport-issue-date",
        "target_id": "section0.table0.row0.cell1",
        "new_value": "2020-01-02",
        "xml_segments": ["section0.table0.row0.cell1"],
        "constraints": {"mode": "empty_cell"},
    }

    result = validate_typed_postconditions(manifest, [operation])

    assert result == {
        "passed": False,
        "failures": ["passport-issue-date: 날짜 postcondition 불일치"],
    }


def test_typed_amount_prefix_preserves_unit_text(tmp_path: Path) -> None:
    source = tmp_path / "amount.hwpx"
    output = tmp_path / "amount-edited.hwpx"
    _make_grid_fixture(source)
    operation = {
        "operation": "set_amount",
        "field_id": "annual-income",
        "target_id": "section0.table0.row0.cell0",
        "old_value": "등록번호",
        "new_value": "3,000",
        "anchor": "등록번호",
        "expected_match_count": 1,
        "xml_segments": ["section0.table0.row0.cell0"],
        "constraints": {"mode": "prefix_unit"},
        "postcondition": "value_once",
        "confidence": "confirmed",
    }

    apply_typed_edits(source, output, [operation])

    cell = _analyze_xml_document(output)["sections"][0]["tables"][0]["cells"][0]
    assert cell["text"] == "3,000 등록번호"


def test_placeholder_value_preserves_surrounding_label(tmp_path: Path) -> None:
    source = Path("samples/통합신청서(신고서).hwpx")
    if not source.exists():
        return
    output = tmp_path / "placeholder-edited.hwpx"
    field = next(
        item
        for item in _analyze_xml_document(source)["xml_field_candidates"]
        if item["kind"] == "placeholder"
    )
    operation = {
        "operation": "replace_text_range",
        "field_id": field["field_id"],
        "target_id": field["target_id"],
        "old_value": field["current_text"],
        "new_value": "H-2",
        "anchor": field["constraints"]["anchor"],
        "expected_match_count": 1,
        "xml_segments": field["xml_segments"],
        "constraints": field["constraints"],
        "postcondition": "value_once",
        "confidence": "confirmed",
    }

    apply_typed_edits(source, output, [operation])

    edited = _analyze_xml_document(output)
    cells = edited["sections"][0]["tables"][0]["cells"]
    target = next(cell for cell in cells if cell["id"] == field["target_id"])
    assert target["text"] == "(희망 자격 : H-2)"


def test_registry_v2_detects_grid_without_specific_label(tmp_path: Path) -> None:
    source = tmp_path / "grid.hwpx"
    _make_grid_fixture(source)

    registry = infer_all_fields(_analyze_xml_document(source))
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

    registry = _analyze_xml_document(sample)["xml_field_candidates"]
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
    manifest = make_grounded_manifest(source)

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
        make_grounded_manifest(source)["field_registry"],
    )
    update_workflow_state(
        workspace["workspace_dir"],
        status="ANALYZED",
        svg_analysis_status="MAPPED",
        analysis_contract_version=2,
        registry_source="rhwp_svg",
        interview_ready=True,
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
    confirmed = next(
        field
        for field in result["field_registry"]
        if field["field_id"] == "vision.confirmed.field"
    )
    assert confirmed["constraints"]["visual_source"] == "human_confirmed_svg"


def test_typed_character_grid_writes_one_character_per_cell(tmp_path: Path) -> None:
    source = tmp_path / "grid.hwpx"
    output = tmp_path / "grid-edited.hwpx"
    _make_grid_fixture(source)
    manifest = make_grounded_manifest(source)
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
    edited = _analyze_xml_document(output)
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
    plan_id = "a" * 64
    attempt = workspace["workspace_dir"] / "attempts" / plan_id
    attempt.mkdir(parents=True)
    modified = attempt / "modified.hwpx"
    modified.write_bytes(source.read_bytes())
    report_path = attempt / "verification-report.json"
    write_json(report_path, {"status": "PENDING_VISION_REVIEW"})
    update_workflow_state(
        workspace["workspace_dir"],
        status="PENDING_VISION_REVIEW",
        plan_id=plan_id,
        modified_path=str(modified),
    )

    with pytest.raises(DocumentError, match="Vision PASS"):
        finalize_attempt(workspace["workspace_dir"], plan_id)
    assert not (workspace["workspace_dir"] / "final").exists()

    images = {}
    for kind in ("original", "modified", "diff"):
        image_path = attempt / f"{kind}.png"
        Image.new("RGB", (10, 10), "white").save(image_path)
        images[kind] = VisionImage(
            path=str(image_path),
            sha256=sha256_file(image_path),
        )
    request = build_vision_review_request(
        plan_id=plan_id,
        original_path=workspace["original_path"],
        modified_path=modified,
        verification_path=report_path,
        views=[
            VisionView(
                view_id="page-001-full",
                page=1,
                kind="full",
                bbox=None,
                field_ids=["field-1"],
                original=images["original"],
                modified=images["modified"],
                diff=images["diff"],
            )
        ],
        expected_field_ids=["field-1"],
        prompt="검토",
    )
    request_path = attempt / "vision-review-request.json"
    write_json(request_path, request.model_dump())
    vision_review = {
        "source": "mcp_sampling",
        "review_id": request.review_id,
        "plan_id": plan_id,
        "original_sha256": request.original_sha256,
        "modified_sha256": request.modified_sha256,
        "verification_report_sha256": request.verification_report_sha256,
        "verdict": "PASS",
    }
    vision_path = attempt / "vision-review.json"
    write_json(vision_path, vision_review)
    update_workflow_state(
        workspace["workspace_dir"],
        status="PENDING_VISION_REVIEW",
        plan_id=plan_id,
        modified_path=str(modified),
        vision_review_id=request.review_id,
        vision_review_request_path=str(request_path),
        vision_review_request_sha256=sha256_file(request_path),
        vision_status="PASS",
        vision_review_path=str(vision_path),
        vision_review_sha256=sha256_file(vision_path),
    )
    write_json(vision_path, {**vision_review, "verdict": "FAIL"})
    with pytest.raises(DocumentError, match="무결성"):
        finalize_attempt(workspace["workspace_dir"], plan_id)

    write_json(vision_path, vision_review)
    update_workflow_state(
        workspace["workspace_dir"],
        status="PENDING_VISION_REVIEW",
        plan_id=plan_id,
        modified_path=str(modified),
        vision_review_id=request.review_id,
        vision_review_request_path=str(request_path),
        vision_review_request_sha256=sha256_file(request_path),
        vision_status="PASS",
        vision_review_path=str(vision_path),
        vision_review_sha256=sha256_file(vision_path),
    )
    finalized = finalize_attempt(workspace["workspace_dir"], plan_id)

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
