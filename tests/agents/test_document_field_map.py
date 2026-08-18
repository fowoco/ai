# 재갱신 문서 필드 매핑·실생성 연동 테스트
from pathlib import Path

from app.agents.workflow_graph.document_field_map import (
    map_employment_extension_application,
    map_identity_guaranty,
    map_immigration_integrated_application,
    map_standard_labor_contract,
    merge_document_source_slots,
    values_for_template,
)
from app.agents.workflow_graph.nodes.document_generator import EditingServiceDocumentGenerator
from app.agents.workflow_graph.state import empty_renewal_state
from app.documents.hwp5 import Hwp5BinaryDocument


# 매핑·생성 검증용 샘플 Shared State
def _sample_state():
    state = empty_renewal_state(
        task_id="task-map-1",
        request_id="req-map-1",
        instruction="체류기간 연장 갱신",
        worker_id="worker-001",
        company_id="company-001",
        slots={
            "full_name": "NGUYEN VAN AN",
            "date_of_birth": "1995-03-21",
            "nationality": "베트남",
            "passport_number": "P1234567",
            "alien_registration_number": "900101-1234567",
            "stay_expiry_date": "2026-12-31",
            "job_description": "금속 부품 조립",
            "work_location": "경기도 안산시",
            "lodging": "기숙사 A동",
            "contract_period": "2026-10-01~2027-09-30",
            "wage": "2500000",
            "working_hours": "40",
            "industry": "제조업",
            "employer_name": "김민수",
        },
    )
    state["company_record"] = {
        "name": "주식회사 한빛정밀",
        "business_number": "123-45-67890",
        "phone": "031-000-0000",
        "address": "경기도 안산시 단원구 산단로 000",
        "employer_name": "김민수",
    }
    return state


# 근로계약서 매핑이 근로자·회사 슬롯을 필드에 넣는다
def test_labor_contract_mapping_uses_slots_and_company() -> None:
    values = map_standard_labor_contract(_sample_state())
    assert values["employee_name"] == "NGUYEN VAN AN"
    assert values["employee_birthdate"] == "1995-03-21"
    assert values["enterprise_name"] == "주식회사 한빛정밀"
    assert values["business_number"] == "123-45-67890"
    assert values["job_description"] == "금속 부품 조립"
    assert values["contract_period"] == "2026-10-01 ~ 2027-09-30"
    assert values["enterprise_address"] == "경기도 안산시 단원구 산단로 000"
    assert values["work_place"] == "경기도 안산시"
    assert values["working_hours_summary"] == "주 40시간 (시작·종료 시각 HR 확인 필요)"
    assert values["monthly_normal_wage"] == "2,500,000"
    assert values["accommodation_summary"] == "기숙사 A동"


def test_labor_contract_mapping_keeps_legacy_month_count() -> None:
    state = _sample_state()
    state["slots"]["contract_period"] = "12"

    values = map_standard_labor_contract(state)

    assert values["contract_months"] == "12"
    assert "contract_period" not in values


# 통합신청서 매핑이 체류연장 체크와 성·이름·생년월일을 채운다
def test_immigration_mapping_sets_stay_extension_and_name_parts() -> None:
    values = map_immigration_integrated_application(_sample_state())
    assert values["application_stay_extension"] is True
    assert values["family_name"] == "NGUYEN"
    assert values["given_names"] == "VAN AN"
    assert values["birth_year"] == "1995"
    assert values["passport_number"] == "P1234567"
    assert values["current_workplace"] == "주식회사 한빛정밀"


# 연장신청서·신원보증서 핵심 필드 매핑을 검증한다
def test_extension_and_guaranty_mapping() -> None:
    state = _sample_state()
    ext = map_employment_extension_application(state)
    assert ext["employee_1_name"] == "NGUYEN VAN AN"
    assert ext["employee_1_passport_number"] == "P1234567"
    assert ext["workplace_name"] == "주식회사 한빛정밀"

    guaranty = map_identity_guaranty(state)
    assert guaranty["foreign_name"] == "NGUYEN VAN AN"
    assert guaranty["foreign_passport"] == "P1234567"
    assert guaranty["stay_purpose"] == "취업"
    assert guaranty["guarantor_name"] == "김민수"


# 템플릿 id별 mapper 디스패치를 확인한다
def test_values_for_template_dispatches() -> None:
    state = _sample_state()
    assert values_for_template("standard_labor_contract_v6", state)["employee_name"]
    assert values_for_template("unknown_template", state) == {}


# 실생성기가 필수 4종 초안을 만들고 매핑 필드를 남긴다
def test_editing_generator_maps_and_generates_or_stubs(tmp_path: Path) -> None:
    gen = EditingServiceDocumentGenerator(output_dir=tmp_path)
    docs = gen(_sample_state())
    assert len(docs) == 4
    by_id = {d["template_id"]: d for d in docs}
    assert "standard_labor_contract_v6" in by_id
    assert "employment_extension_application_v12_3" in by_id
    assert "immigration_integrated_application_v34" in by_id
    assert "identity_guaranty_v129" in by_id
    labor = by_id["standard_labor_contract_v6"]
    assert "employee_name" in labor["mapped_fields"]
    assert labor["status"] in {"generated", "stub"}
    if labor["status"] == "generated":
        assert Path(labor["path"]).exists()
        assert labor["changed_fields"]

        paragraphs = {
            paragraph.index: paragraph.text
            for paragraph in Hwp5BinaryDocument(labor["path"]).paragraphs()
        }
        assert "2026-10-01 ~ 2027-09-30" in paragraphs[24]
        assert "경기도 안산시" in paragraphs[33]
        assert "주 40시간" in paragraphs[48]
        assert "2,500,000" in paragraphs[73]
        assert "기숙사 A동" in paragraphs[99]


# OCR 신분 값이 slots보다 우선해 서류 매핑에 반영된다
def test_ocr_merges_into_document_slots() -> None:
    state = _sample_state()
    state["slots"]["passport_number"] = "OLD"
    state["ocr_result"] = {"passport_number": "P999", "full_name": "OCR NAME"}
    merged = merge_document_source_slots(state)
    assert merged["passport_number"] == "P999"
    assert merged["full_name"] == "OCR NAME"
    values = map_standard_labor_contract(state)
    assert values["employee_name"] == "OCR NAME"
