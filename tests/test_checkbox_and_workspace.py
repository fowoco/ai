from pathlib import Path

from hwp_mcp.normalization import normalize_field, NormalizationRequest
from hwp_mcp.hwpx import analyze_document, fill_cells


def test_checkbox_normalization() -> None:
    res1 = normalize_field(NormalizationRequest(field_type="checkbox", value="남성"))
    assert res1.normalized == "[V]"

    res2 = normalize_field(NormalizationRequest(field_type="checkbox", value="V"))
    assert res2.normalized == "[V]"


def test_checkbox_cell_substitution_double_space() -> None:
    """원본 XML의 [  ] (공백 2칸) 패턴도 정확히 [V]로 치환되는지 검증."""
    sample_path = Path("samples/통합신청서(신고서).hwpx")
    if not sample_path.exists():
        return

    mod_path = Path("samples/통합신청서(신고서)/test_checkbox_mod.hwpx")

    # row4.cell0: 외국인 등록 체크박스 — 원본이 [  ] (공백 2칸)
    edits = [
        {"target_id": "section0.table0.row4.cell0", "expected_text": "[  ] 외국인 등록      FOREIGN RESIDENT REGISTRATION", "value": "[V]"}
    ]

    fill_res = fill_cells(sample_path, mod_path, edits)
    assert fill_res["applied"] == 1

    manifest = analyze_document(mod_path)
    cells = manifest["sections"][0]["tables"][0]["cells"]
    target_cell = [c for c in cells if c["id"] == "section0.table0.row4.cell0"][0]
    # [  ] -> [V]로 치환되고, 원본 텍스트가 중복으로 추가되지 않아야 함
    assert "[V]" in target_cell["text"]
    assert "[  ]" not in target_cell["text"]  # 원래 공백 2칸 브래킷이 남아있으면 안 됨
    if mod_path.exists():
        mod_path.unlink()


def test_sex_checkbox_substitution() -> None:
    """성별 체크박스 [ ]남 M / [ ]여 F 중 첫번째만 [V]로 교체되는지 검증."""
    sample_path = Path("samples/통합신청서(신고서).hwpx")
    if not sample_path.exists():
        return

    mod_path = Path("samples/통합신청서(신고서)/test_sex_mod.hwpx")
    edits = [
        {"target_id": "section0.table0.row15.cell5", "expected_text": "[ ]남 M[ ]여 F", "value": "[V]"}
    ]

    fill_res = fill_cells(sample_path, mod_path, edits)
    assert fill_res["applied"] == 1

    manifest = analyze_document(mod_path)
    cells = manifest["sections"][0]["tables"][0]["cells"]
    sex_cell = [c for c in cells if c["id"] == "section0.table0.row15.cell5"][0]
    assert "[V]남 M" in sex_cell["text"]
    # 원본 t노드 2개가 그대로 유지되고 새 run이 덧붙여지지 않아야 함
    assert sex_cell["text"].count("[V]") == 1
    if mod_path.exists():
        mod_path.unlink()
