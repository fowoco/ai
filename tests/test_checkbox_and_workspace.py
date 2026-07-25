from pathlib import Path

from hwp_mcp.normalization import normalize_field, NormalizationRequest
from hwp_mcp.hwpx import analyze_document, fill_cells


def test_checkbox_normalization() -> None:
    res1 = normalize_field(NormalizationRequest(field_type="checkbox", value="남성"))
    assert res1.normalized == "[V]"

    res2 = normalize_field(NormalizationRequest(field_type="checkbox", value="V"))
    assert res2.normalized == "[V]"


def test_checkbox_cell_substitution() -> None:
    sample_path = Path("samples/통합신청서(신고서).hwpx")
    if not sample_path.exists():
        return

    mod_path = Path("samples/통합신청서(신고서)/test_checkbox_mod.hwpx")
    edits = [
        # 성별 [ ]남 M[ ]여 F 셀 (row15.cell5)
        {"target_id": "section0.table0.row15.cell5", "expected_text": "[ ]남 M[ ]여 F", "value": "[V]"}
    ]

    fill_res = fill_cells(sample_path, mod_path, edits)
    assert fill_res["applied"] == 1

    manifest = analyze_document(mod_path)
    cells = manifest["sections"][0]["tables"][0]["cells"]
    sex_cell = [c for c in cells if c["id"] == "section0.table0.row15.cell5"][0]
    # [ ] -> [V] 로 치환되었는지 검증
    assert "[V]남 M" in sex_cell["text"]
    if mod_path.exists():
        mod_path.unlink()
