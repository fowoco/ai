# 재갱신 문서 필드 매핑·실생성 연동 테스트
from pathlib import Path

from app.agents.workflow_graph.document_field_map import (
    document_field_statuses,
    map_employment_extension_application,
    map_identity_guaranty,
    map_immigration_integrated_application,
    map_standard_labor_contract,
    merge_document_source_slots,
    values_for_template,
)
from app.agents.workflow_graph.nodes import document_generator
from app.agents.workflow_graph.nodes.document_generator import EditingServiceDocumentGenerator
from app.agents.workflow_graph.state import empty_renewal_state
from app.documents.common import DocumentFormat
from app.documents.editing.models import DocumentMutationResult


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
            "contract_period": "12",
            "wage": "2500000",
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
    assert values["contract_months"] == "12"


def test_labor_contract_mapping_fills_body_from_renewal_slots() -> None:
    """재갱신의 계약 슬롯은 표준근로계약서 본문 필드로도 전달된다."""
    state = _sample_state()
    state["slots"].update(
        {
            "working_hours": "09시 00분 ~ 18시 00분",
            "daily_overtime_hours": "2",
            "daily_overtime_limit": "4",
            "recess_minutes": "60",
            "monthly_wage": "2,500,000",
            "base_wage": "2,400,000",
            "fixed_allowances": "식대 수당: 100,000원",
            "bonus": "0",
            "probation_wage_detail": "2,250,000원, 3개월 이내 근무기간 2,400,000원",
            "payment_date_detail": (
                "매월 (25)일 또는 매주 (금)요일. 다만, 임금 지급일이 "
                "공휴일인 경우에는 전날에 지급함."
            ),
            "accommodation_cost": "50,000",
            "meal_cost": "30,000",
        }
    )

    values = map_standard_labor_contract(state)

    assert values["working_hours"] == "09시 00분 ~ 18시 00분"
    assert values["monthly_wage"] == "2,500,000"
    assert values["daily_overtime_limit"] == "4"
    assert values["payment_date_detail"].startswith("매월 (25)일")
    assert values["accommodation_cost"] == "50,000"


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


def test_template_slot_value_fills_a_field_not_in_the_handwritten_mapper() -> None:
    """HR가 보충한 템플릿 필드는 개별 mapper 목록 밖이어도 문서에 전달한다."""
    state = _sample_state()
    state["slots"]["school_name"] = "FOWOCO Korean Academy"

    values = values_for_template("immigration_integrated_application_v34", state)

    assert values["school_name"] == "FOWOCO Korean Academy"


def test_document_field_statuses_exclude_assets_and_expose_empty_text_fields() -> None:
    """시연 화면은 사진·서명을 빼되, 비어 있는 텍스트 템플릿 필드는 숨기지 않는다."""
    statuses = document_field_statuses(_sample_state())
    immigration = statuses["immigration_integrated_application_v34"]

    assert "photo" not in immigration["fields"]
    assert "applicant_signature" not in immigration["fields"]
    assert "passport_number" in immigration["filled_fields"]
    assert "passport_issue_date" in immigration["empty_text_fields"]


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


def test_editing_generator_reports_generated_document_format(tmp_path: Path) -> None:
    class SuccessfulEditing:
        def generate(
            self,
            template_id: str,
            document_format: DocumentFormat,
            destination: Path,
            *,
            values: dict[str, object] | None = None,
            **_: object,
        ) -> DocumentMutationResult:
            destination.touch()
            return DocumentMutationResult(
                destination,
                document_format,
                template_id,
                tuple(values or {}),
            )

    state = empty_renewal_state(
        task_id="task-generator-format",
        request_id="req-generator-format",
        instruction="체류기간 연장 갱신",
        slots={"full_name": "NGUYEN VAN AN"},
    )
    docs = EditingServiceDocumentGenerator(
        SuccessfulEditing(),
        output_dir=tmp_path,
        template_ids=("standard_labor_contract_v6",),
    )(state)

    assert docs[0]["status"] == "generated"
    assert docs[0]["format"] == "hwp"


# 사전 계산된 템플릿 계획이 있으면 재매핑하지 않고 그대로 생성에 쓴다
def test_generator_uses_precomputed_document_field_values(tmp_path: Path) -> None:
    state = _sample_state()
    state["document_field_values"] = {
        "standard_labor_contract_v6": {"employee_name": "PLAN VALUE"}
    }
    generator = EditingServiceDocumentGenerator(
        output_dir=tmp_path,
        template_ids=("standard_labor_contract_v6",),
    )

    result = generator(state)

    assert result[0]["mapped_fields"] == ["employee_name"]


# 사전 계획이 없으면 기존 템플릿 mapper의 값을 생성 결과에 반영한다
def test_generator_derives_values_when_no_precomputed_plan(
    tmp_path: Path, monkeypatch
) -> None:
    state = _sample_state()
    monkeypatch.setattr(
        document_generator,
        "values_for_template",
        lambda template_id, renewal_state: {"derived_field": "DERIVED VALUE"},
    )
    generator = EditingServiceDocumentGenerator(
        output_dir=tmp_path,
        template_ids=("standard_labor_contract_v6",),
    )

    result = generator(state)

    assert result[0]["mapped_fields"] == ["derived_field"]


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
