import pytest
from hwp_mcp.hwpx import analyze_document, apply_typed_edits
from hwp_mcp.plans import create_edit_plan, CellEditInput

def test_replace_text_in_segment_precise(tmp_path):
    sample_path = "samples/별지_제6호서식_표준근로계약서(Standard_Labor_Contract)(외국인근로자의_고용_등에_관한_법률_시행규칙).hwpx"
    import os
    if not os.path.exists(sample_path):
        pytest.skip("Sample HWPX not found")

    manifest = analyze_document(sample_path)
    output_path = tmp_path / "edited_contract.hwpx"

    field = next(
        item
        for item in manifest["field_registry"]
        if item["kind"] == "text_field" and item["current_text"] == ""
    )
    edits = [
        CellEditInput(
            field_id=field["field_id"],
            target_id=field["target_id"],
            expected_text="",
            value="주식회사 에이블컴퍼니",
        )
    ]
    dispositions = {
        item["field_id"]: (
            "manual_after_export"
            if item["kind"] == "signable_region"
            else "provided"
            if item["field_id"] == field["field_id"]
            else "not_applicable"
        )
        for item in manifest["field_registry"]
    }

    raw_plan = create_edit_plan(
        input_path=sample_path,
        manifest=manifest,
        edits=edits,
        dispositions=dispositions,
    )
    
    result = apply_typed_edits(
        sample_path,
        output_path,
        [op.model_dump() for op in raw_plan.operations],
    )

    assert result["applied"] > 0
    assert output_path.exists()

    edited_manifest = analyze_document(output_path)
    assert edited_manifest["valid"] is True
