import pytest
import zipfile
from defusedxml import ElementTree as SafeET
from hwp_mcp.hwpx import analyze_document, fill_cells
from hwp_mcp.plans import create_edit_plan, CellEditInput

def test_replace_text_in_segment_precise(tmp_path):
    sample_path = "samples/별지_제6호서식_표준근로계약서(Standard_Labor_Contract)(외국인근로자의_고용_등에_관한_법률_시행규칙).hwpx"
    import os
    if not os.path.exists(sample_path):
        pytest.skip("Sample HWPX not found")

    manifest = analyze_document(sample_path)
    output_path = tmp_path / "edited_contract.hwpx"

    field_candidates = manifest.get("field_candidates", [])
    edits = []
    if field_candidates:
        cand = field_candidates[0]
        edits.append(CellEditInput(
            target_id=cand["target_id"],
            expected_text=cand["current_value"],
            value="주식회사 에이블컴퍼니",
        ))
    else:
        # Fallback cell edit
        edits.append(CellEditInput(
            target_id="section0.table0.row0.cell1",
            expected_text="",
            value="주식회사 에이블컴퍼니",
        ))

    raw_plan = create_edit_plan(
        input_path=sample_path,
        manifest=manifest,
        edits=edits,
    )
    
    result = fill_cells(sample_path, output_path, [op.model_dump() for op in raw_plan.operations])

    assert result["applied"] > 0
    assert output_path.exists()

    edited_manifest = analyze_document(output_path)
    assert edited_manifest["valid"] is True
