import scripts.renewal_streamlit as renewal_streamlit
from scripts.renewal_streamlit import (
    DEMO_SERVER_COMPANY_ID,
    DEMO_SERVER_WORKER_ID,
    build_renewal_payload,
    build_scenario_one_payload,
    template_statuses_for_response,
)


def test_build_renewal_payload_keeps_manual_slots_and_api_aliases() -> None:
    payload = build_renewal_payload(
        request_id="req-demo",
        instruction="체류기간 연장 갱신",
        worker_id="worker-001",
        company_id="company-001",
        slots={"full_name": "NGUYEN VAN AN", "wage": "2500000"},
    )

    assert payload == {
        "requestId": "req-demo",
        "instruction": "체류기간 연장 갱신",
        "workerId": "worker-001",
        "companyId": "company-001",
        "slots": {"full_name": "NGUYEN VAN AN", "wage": "2500000"},
        "documents": [],
    }


def test_scenario_one_payload_uses_server_context_and_only_adds_hr_answers() -> None:
    payload = build_scenario_one_payload(
        request_id="req-scenario-one",
        instruction="체류기간 연장 갱신",
        supplemental_slots={"wage": "2500000"},
    )

    assert payload["workerId"] == DEMO_SERVER_WORKER_ID
    assert payload["companyId"] == DEMO_SERVER_COMPANY_ID
    assert payload["worker"]["displayName"] == "응웬반A"
    assert payload["company"]["name"] == "FOWOCO Demo Company"
    assert payload["ocrResult"]["passport_number"] == "DEMO-P06-NOT-VALID"
    assert payload["slots"]["wage"] == "2500000"
    assert "full_name" not in payload["slots"]


def test_scenario_one_maps_company_snapshot_to_labor_contract() -> None:
    """Server 회사 스냅샷은 대표자 등 계약서 상단 필드를 바로 채운다."""
    payload = build_scenario_one_payload(
        request_id="req-scenario-one-company",
        instruction="체류기간 연장 갱신",
    )

    status = template_statuses_for_response(payload)["standard_labor_contract_v6"]

    assert payload["company"]["employer_name"] == "김민수"
    assert status["values"]["employer_name"] == "김민수"
    assert status["values"]["business_number"] == "123-45-67890"


def test_demo_defaults_cover_renewal_and_labor_contract_body() -> None:
    """시연 화면은 Graph 필수값과 표준근로계약서 본문값의 기본안을 제공한다."""
    assert hasattr(renewal_streamlit, "DEMO_FORM_DEFAULTS")
    defaults = renewal_streamlit.DEMO_FORM_DEFAULTS

    assert defaults["wage"] == "2500000"
    assert defaults["working_hours"] == "09시 00분 ~ 18시 00분"
    assert defaults["monthly_wage"] == "2,500,000"
    assert defaults["payment_bank"] is True


def test_demo_defaults_leave_only_inapplicable_repeated_or_change_fields_empty() -> None:
    """단일 근로자 체류연장 시연은 적용 대상 템플릿 필드를 모두 채운다."""
    payload = build_scenario_one_payload(
        request_id="req-scenario-one-defaults",
        instruction="체류기간 연장 갱신",
        supplemental_slots=renewal_streamlit.DEMO_FORM_DEFAULTS,
    )
    statuses = template_statuses_for_response(payload)

    assert statuses["standard_labor_contract_v6"]["empty_text_fields"] == []
    assert statuses["identity_guaranty_v129"]["empty_text_fields"] == []
    assert statuses["immigration_integrated_application_v34"]["empty_text_fields"] == [
        "new_business_number",
        "new_workplace",
        "new_workplace_phone",
    ]
    assert statuses["employment_extension_application_v12_3"]["empty_text_fields"] == [
        "employee_2_expiry_date",
        "employee_2_name",
        "employee_2_nationality",
        "employee_2_passport_number",
        "employee_2_resident_number",
        "employee_3_expiry_date",
        "employee_3_name",
        "employee_3_nationality",
        "employee_3_passport_number",
        "employee_3_resident_number",
        "employee_4_expiry_date",
        "employee_4_name",
        "employee_4_nationality",
        "employee_4_passport_number",
        "employee_4_resident_number",
        "employee_5_expiry_date",
        "employee_5_name",
        "employee_5_nationality",
        "employee_5_passport_number",
        "employee_5_resident_number",
    ]


def test_renewal_required_fields_keep_agent_slot_keys() -> None:
    """템플릿 별칭이 아니라 Agent가 실제 판정하는 슬롯을 HR 입력란으로 낸다."""
    assert hasattr(renewal_streamlit, "renewal_required_fields")
    fields = renewal_streamlit.renewal_required_fields(
        ["wage", "working_hours", "contract_period", "custom_slot"]
    )

    assert fields == [
        {"key": "wage", "label": "임금"},
        {"key": "working_hours", "label": "근무시간"},
        {"key": "contract_period", "label": "계약기간"},
        {"key": "custom_slot", "label": "custom_slot"},
    ]
