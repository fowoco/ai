"""infer_all_fields (XML Field Registry) 통합 테스트."""
from pathlib import Path

from hwp_mcp.hwpx import _analyze_xml_document
from hwp_mcp.fields import _guess_field_type, infer_all_fields


SAMPLE = Path("samples/통합신청서(신고서).hwpx")


def test_registry_detects_all_field_types() -> None:
    """registry가 checkbox, checkbox_group, text, date, phone 등 주요 타입을 모두 포함."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    types = {f["type"] for f in registry}
    assert "checkbox" in types
    assert "checkbox_group" in types
    assert "text" in types
    assert "date" in types
    assert "phone" in types


def test_registry_excludes_official_use() -> None:
    """공용란 내부 입력 후보는 제외하고 비편집 official_region 하나만 보존."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    official = [field for field in registry if field["kind"] == "official_region"]
    assert len(official) == 1
    assert official[0]["constraints"]["editable"] is False
    for field in registry:
        if field["kind"] != "official_region":
            assert field["row"] < 35, f"공용란 입력 후보가 포함됨: {field['label']}"


def test_registry_detects_sex_checkbox_group() -> None:
    """성별 [ ]남 M[ ]여 F 가 checkbox_group으로 감지되어 options에 남/여가 있는지."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    sex_fields = [f for f in registry if f["type"] == "checkbox_group" and "남" in f["label"]]
    assert len(sex_fields) == 1, f"성별 checkbox_group이 정확히 1개여야 함: {sex_fields}"
    opts = sex_fields[0]["options"]
    assert any("남" in o for o in opts)
    assert any("여" in o for o in opts)


def test_registry_detects_school_status() -> None:
    """재학 여부 checkbox_group (미취학, 초, 중, 고) 감지."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    school = [f for f in registry if f["type"] == "checkbox_group" and "미취학" in f["label"]]
    assert len(school) == 1, f"재학 여부 checkbox_group: {school}"
    opts = school[0]["options"]
    assert "미취학" in opts
    assert "초" in opts


def test_registry_detects_reentry_period() -> None:
    """재입국 신청 기간 필드 감지."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    reentry = [f for f in registry if "재입국" in f["label"]]
    assert len(reentry) >= 1, "재입국 신청 기간 필드가 registry에 없음"


def test_registry_has_all_10_application_checkboxes() -> None:
    """step1_application에 최소 10개의 checkbox 필드 (모든 신청/신고 종류)."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    step1_checkboxes = [f for f in registry if f["category"] == "step1_application" and f["type"] == "checkbox"]
    assert len(step1_checkboxes) >= 10, f"step1 체크박스 {len(step1_checkboxes)}개 (10개 이상이어야 함)"


def test_registry_has_email() -> None:
    """전자우편(E-Mail) 필드가 step3에 포함."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    email = [f for f in registry if "전자우편" in f["label"] or "E-Mail" in f["label"]]
    assert len(email) >= 1, "전자우편/E-Mail 필드가 registry에 없음"


def test_registry_categories_are_valid() -> None:
    """모든 필드의 category가 step1~step4 중 하나."""
    if not SAMPLE.exists():
        return
    manifest = _analyze_xml_document(SAMPLE)
    registry = manifest["xml_field_candidates"]
    valid = {
        "step1_application",
        "step2_personal",
        "step3_address",
        "step4_signature",
        "official",
    }
    for f in registry:
        assert f["category"] in valid, f"필드 {f['field_id']}의 category가 {f['category']}"


def test_passport_number_is_text_to_preserve_alphanumeric_value() -> None:
    assert _guess_field_type("여권번호 Passport No.") == "text"
