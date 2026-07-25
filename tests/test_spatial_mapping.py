from pathlib import Path

from hwp_mcp.hwpx import analyze_document
from hwp_mcp.fields import infer_field_candidates_spatial


def test_spatial_geometry_infers_under_label_cells() -> None:
    sample_path = Path("samples/통합신청서(신고서)/original.hwpx")
    if not sample_path.exists():
        return

    manifest = analyze_document(sample_path)
    spatial_candidates = infer_field_candidates_spatial(manifest)

    # 1. 성 Surname 하단 빈 셀 추론 확인 (row14.cell0)
    surname_under = [c for c in spatial_candidates if "성 Surname" in c["label"]]
    assert len(surname_under) >= 1
    assert surname_under[0]["target_id"] == "section0.table0.row14.cell0"

    # 2. 명 Given names 하단 빈 셀 추론 확인 (row14.cell1)
    given_under = [c for c in spatial_candidates if "명 Given" in c["label"]]
    assert len(given_under) >= 1
    assert given_under[0]["target_id"] == "section0.table0.row14.cell1"

    # 3. 년 yyyy 하단 빈 셀 추론 확인 (row16.cell0)
    year_under = [c for c in spatial_candidates if "년 yyyy" in c["label"]]
    assert len(year_under) >= 1
    assert year_under[0]["target_id"] == "section0.table0.row16.cell0"
