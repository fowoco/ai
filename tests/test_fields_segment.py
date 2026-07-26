import pytest
from hwp_mcp.hwpx import _analyze_xml_document
from hwp_mcp.fields import FieldSegment, infer_field_segments

def test_field_segment_model():
    segment = FieldSegment(
        field_id="test.segment.1",
        label="사업장변경자 시작일",
        type="date",
        cell_id="section0.table0.row11.cell1",
        paragraph_id="section0.table0.row11.cell1.paragraph1",
        anchor="년   월   일",
        current_value="",
        context="근로계약기간",
        page=1,
        requires_user_confirmation=True,
    )
    assert segment.field_id == "test.segment.1"
    assert segment.type == "date"
    assert segment.anchor == "년   월   일"

def test_infer_field_segments_from_standard_contract(tmp_path):
    # 표준근로계약서 샘플 HWPX 파일 로드 테스트
    sample_path = "samples/별지_제6호서식_표준근로계약서(Standard_Labor_Contract)(외국인근로자의_고용_등에_관한_법률_시행규칙).hwpx"
    import os
    if not os.path.exists(sample_path):
        pytest.skip("standard employment contract sample not found")

    manifest = _analyze_xml_document(sample_path)
    segments = infer_field_segments(manifest)
    
    assert len(segments) > 0
    field_ids = [s["field_id"] for s in segments]
    
    # 텍스트, 날짜, 체크박스, 사업자등록번호 등 감지 확인
    types = {s["type"] for s in segments}
    assert len(types) > 1, f"Expected multiple segment types, got {types}"

