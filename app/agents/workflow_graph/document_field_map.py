# Shared State → HWP 서류 칸(values) 매핑

from __future__ import annotations

import re
from typing import Any

from .state import IDENTITY_SLOTS, RenewalState

_DATE_PARTS = re.compile(
    r"(?P<y>\d{4})\D+(?P<m>\d{1,2})\D+(?P<d>\d{1,2})"
)


# 첫 번째 truthy 값 반환
def _first(*values: Any) -> Any | None:
    for value in values:
        if value is not None and value != "":
            return value
    return None


# 값을 문자열로 정규화
def _as_str(value: Any | None) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


# 성·이름을 대략 분리 실패 시 given_names에 전체
def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    if not full_name:
        return None, None
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return None, full_name.strip()


# 생년월일 문자열에서 year/month/day 추출
def _birth_parts(date_of_birth: str | None) -> dict[str, str]:
    if not date_of_birth:
        return {}
    match = _DATE_PARTS.search(str(date_of_birth))
    if not match:
        return {}
    return {
        "birth_year": match.group("y"),
        "birth_month": f"{int(match.group('m')):02d}",
        "birth_day": f"{int(match.group('d')):02d}",
    }


# 값이 있을 때만 필드 설정
def _put(values: dict[str, object], field: str, value: Any | None) -> None:
    text = _as_str(value)
    if text is not None:
        values[field] = text


# company_record dict 반환
def _company(state: RenewalState) -> dict[str, Any]:
    record = state.get("company_record")
    return dict(record) if isinstance(record, dict) else {}


# DB slots + OCR 결과를 서류 매핑용으로 병합 (신분 키는 OCR 우선)
def merge_document_source_slots(state: RenewalState) -> dict[str, Any]:
    slots = dict(state.get("slots") or {})
    ocr = state.get("ocr_result")
    if not isinstance(ocr, dict):
        return slots
    nested = ocr.get("fields") or ocr.get("extracted")
    flat = {k: v for k, v in ocr.items() if k not in ("fields", "extracted", "status", "error")}
    if isinstance(nested, dict):
        flat = {**flat, **nested}
    for key, value in flat.items():
        if value in (None, ""):
            continue
        if key in IDENTITY_SLOTS or key not in slots:
            slots[key] = value
    return slots


# 병합된 slots dict 반환
def _slots(state: RenewalState) -> dict[str, Any]:
    return merge_document_source_slots(state)

# 슬롯 키가 템플릿 필드명과 같으면 그대로 복사
def _passthrough_known_fields(
    slots: dict[str, Any], field_names: set[str]
) -> dict[str, object]:
    return {k: v for k, v in slots.items() if k in field_names and v not in (None, "")}


# 표준근로계약서에 넣을 값
def map_standard_labor_contract(state: RenewalState) -> dict[str, object]:
    slots = _slots(state)
    company = _company(state)
    fields = {
        "enterprise_name",
        "enterprise_phone",
        "enterprise_address",
        "employer_name",
        "business_number",
        "employee_name",
        "employee_birthdate",
        "employee_home_address",
        "contract_months",
        "industry",
        "business_description",
        "job_description",
        "contract_date",
    }
    values: dict[str, object] = _passthrough_known_fields(slots, fields)
    _put(values, "employee_name", _first(slots.get("full_name"), slots.get("employee_name")))
    _put(
        values,
        "employee_birthdate",
        _first(slots.get("date_of_birth"), slots.get("employee_birthdate")),
    )
    _put(values, "job_description", slots.get("job_description"))
    _put(
        values,
        "enterprise_address",
        _first(slots.get("work_location"), company.get("address"), slots.get("enterprise_address")),
    )
    _put(
        values,
        "contract_months",
        _first(slots.get("contract_period"), slots.get("contract_months")),
    )
    _put(values, "enterprise_name", _first(company.get("name"), slots.get("enterprise_name")))
    _put(
        values,
        "business_number",
        _first(company.get("business_number"), slots.get("business_number")),
    )
    _put(values, "enterprise_phone", _first(company.get("phone"), slots.get("enterprise_phone")))
    _put(values, "employer_name", _first(company.get("employer_name"), slots.get("employer_name")))
    _put(values, "industry", slots.get("industry"))
    _put(values, "business_description", slots.get("business_description"))
    _put(
        values,
        "employee_home_address",
        _first(slots.get("home_country_address"), slots.get("employee_home_address")),
    )
    _put(values, "contract_date", slots.get("contract_date"))
    return values


# 통합신청서에 넣을 값. 재갱신 시 체류연장 체크
def map_immigration_integrated_application(state: RenewalState) -> dict[str, object]:
    slots = _slots(state)
    company = _company(state)
    fields = {
        "family_name",
        "given_names",
        "nationality",
        "passport_number",
        "passport_issue_date",
        "passport_expiry_date",
        "address_in_korea",
        "telephone",
        "cell_phone",
        "home_country_address",
        "home_country_phone",
        "current_workplace",
        "current_business_number",
        "current_workplace_phone",
        "annual_income",
        "occupation",
        "email",
        "application_date",
    }
    values: dict[str, object] = _passthrough_known_fields(slots, fields)
    family, given = _split_name(_as_str(slots.get("full_name")))
    _put(values, "family_name", _first(slots.get("family_name"), family))
    _put(values, "given_names", _first(slots.get("given_names"), given, slots.get("full_name")))
    values.update(_birth_parts(_as_str(slots.get("date_of_birth"))))
    _put(values, "nationality", slots.get("nationality"))
    _put(values, "passport_number", slots.get("passport_number"))
    _put(
        values,
        "address_in_korea",
        _first(slots.get("lodging"), slots.get("work_location"), slots.get("address_in_korea")),
    )
    _put(values, "current_workplace", _first(company.get("name"), slots.get("current_workplace")))
    _put(
        values,
        "current_business_number",
        _first(company.get("business_number"), slots.get("current_business_number")),
    )
    _put(
        values,
        "current_workplace_phone",
        _first(company.get("phone"), slots.get("current_workplace_phone")),
    )
    _put(values, "occupation", slots.get("job_description"))
    _put(values, "annual_income", slots.get("wage"))
    _put(values, "home_country_address", slots.get("home_country_address"))
    values["application_stay_extension"] = True  # 재갱신 기본: 체류기간 연장
    return values


# 취업활동 기간 연장신청서에 넣을 값
def map_employment_extension_application(state: RenewalState) -> dict[str, object]:
    slots = _slots(state)
    company = _company(state)
    fields = {
        "workplace_name",
        "workplace_phone",
        "workplace_address",
        "representative",
        "business_type",
        "business_number",
        "employee_1_name",
        "employee_1_resident_number",
        "employee_1_nationality",
        "employee_1_passport_number",
        "employee_1_expiry_date",
        "applicant_name",
        "application_date",
    }
    values: dict[str, object] = _passthrough_known_fields(slots, fields)
    _put(values, "workplace_name", _first(company.get("name"), slots.get("workplace_name")))
    _put(values, "workplace_phone", _first(company.get("phone"), slots.get("workplace_phone")))
    _put(
        values,
        "workplace_address",
        _first(company.get("address"), slots.get("work_location"), slots.get("workplace_address")),
    )
    _put(
        values,
        "representative",
        _first(company.get("employer_name"), slots.get("representative"), slots.get("employer_name")),
    )
    _put(values, "business_type", _first(slots.get("industry"), slots.get("business_type")))
    _put(
        values,
        "business_number",
        _first(company.get("business_number"), slots.get("business_number")),
    )
    _put(values, "employee_1_name", _first(slots.get("full_name"), slots.get("employee_1_name")))
    _put(
        values,
        "employee_1_resident_number",
        _first(slots.get("alien_registration_number"), slots.get("employee_1_resident_number")),
    )
    _put(
        values,
        "employee_1_nationality",
        _first(slots.get("nationality"), slots.get("employee_1_nationality")),
    )
    _put(
        values,
        "employee_1_passport_number",
        _first(slots.get("passport_number"), slots.get("employee_1_passport_number")),
    )
    _put(
        values,
        "employee_1_expiry_date",
        _first(slots.get("stay_expiry_date"), slots.get("employee_1_expiry_date")),
    )
    _put(
        values,
        "applicant_name",
        _first(company.get("employer_name"), slots.get("applicant_name"), slots.get("employer_name")),
    )
    _put(values, "application_date", slots.get("application_date"))
    return values


# 신원보증서에 넣을 값. 보증인은 회사 담당자 정보 우선 사용
def map_identity_guaranty(state: RenewalState) -> dict[str, object]:
    slots = _slots(state)
    company = _company(state)
    fields = {
        "foreign_name",
        "foreign_birthdate",
        "foreign_nationality",
        "foreign_passport",
        "foreign_korea_address",
        "foreign_phone",
        "stay_purpose",
        "guarantor_name",
        "guarantor_nationality",
        "guarantor_phone",
        "guarantor_address",
        "relationship",
        "workplace",
        "position",
        "workplace_address",
        "guarantee_period",
        "guarantee_date",
    }
    values: dict[str, object] = _passthrough_known_fields(slots, fields)
    _put(values, "foreign_name", _first(slots.get("full_name"), slots.get("foreign_name")))
    _put(
        values,
        "foreign_birthdate",
        _first(slots.get("date_of_birth"), slots.get("foreign_birthdate")),
    )
    _put(
        values,
        "foreign_nationality",
        _first(slots.get("nationality"), slots.get("foreign_nationality")),
    )
    _put(
        values,
        "foreign_passport",
        _first(slots.get("passport_number"), slots.get("foreign_passport")),
    )
    _put(
        values,
        "foreign_korea_address",
        _first(slots.get("lodging"), slots.get("work_location"), slots.get("foreign_korea_address")),
    )
    _put(values, "foreign_phone", slots.get("phone"))
    _put(values, "stay_purpose", _first(slots.get("stay_purpose"), "취업"))
    _put(
        values,
        "guarantor_name",
        _first(company.get("employer_name"), slots.get("guarantor_name"), slots.get("employer_name")),
    )
    _put(values, "workplace", _first(company.get("name"), slots.get("workplace")))
    _put(
        values,
        "workplace_address",
        _first(company.get("address"), slots.get("work_location"), slots.get("workplace_address")),
    )
    _put(values, "guarantor_phone", _first(company.get("phone"), slots.get("guarantor_phone")))
    _put(values, "relationship", _first(slots.get("relationship"), "고용주"))
    return values


_TEMPLATE_MAPPERS = {
    "standard_labor_contract_v6": map_standard_labor_contract,
    "immigration_integrated_application_v34": map_immigration_integrated_application,
    "employment_extension_application_v12_3": map_employment_extension_application,
    "identity_guaranty_v129": map_identity_guaranty,
}


# 템플릿 id에 맞는 values dict 반환 미등록 시 빈 dict
def values_for_template(template_id: str, state: RenewalState) -> dict[str, object]:
    mapper = _TEMPLATE_MAPPERS.get(template_id)
    if mapper is None:
        return {}
    return mapper(state)
