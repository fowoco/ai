# Shared State → HWP 서류 칸(values) 매핑

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.documents.hwp5.template_registry import Hwp5TemplateRegistry

from .state import IDENTITY_SLOTS, RenewalState

_DATE_PARTS = re.compile(
    r"(?P<y>\d{4})\D+(?P<m>\d{1,2})\D+(?P<d>\d{1,2})"
)
_ASSET_FIELD_TYPES = frozenset({"image", "photo", "signature"})


@lru_cache(maxsize=1)
def _template_registry() -> Hwp5TemplateRegistry:
    return Hwp5TemplateRegistry()


def editable_template_fields(template_id: str) -> dict[str, dict[str, object]]:
    """사진·서명을 뺀 HWP 템플릿 필드 정의를 반환한다."""
    template = _template_registry().get(template_id)
    return {
        name: dict(specification)
        for name, specification in template.fields.items()
        if str(specification.get("type", "text")) not in _ASSET_FIELD_TYPES
    }


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


def _english_working_hours(value: Any | None) -> str | None:
    text = _as_str(value)
    if not text:
        return None
    match = re.search(
        r"(?P<from_h>\d{1,2})시\s*(?P<from_m>\d{1,2})분\s*~\s*"
        r"(?P<to_h>\d{1,2})시\s*(?P<to_m>\d{1,2})분",
        text,
    )
    if not match:
        return text
    return (
        f"from ({int(match.group('from_h')):02d}:{int(match.group('from_m')):02d}) "
        f"to ({int(match.group('to_h')):02d}:{int(match.group('to_m')):02d})"
    )


def _english_probation_wage(value: Any | None) -> str | None:
    text = _as_str(value)
    if not text:
        return None
    amounts = [
        amount.replace("원", "").strip()
        for amount in re.findall(r"\d[\d,]*원", text)
    ]
    if len(amounts) < 2:
        return text
    return (
        f"{amounts[0]} won, but for up to the first 3 months of probation period: "
        f"{amounts[1]} won"
    )


def _english_payment_date(value: Any | None) -> str | None:
    text = _as_str(value)
    if not text:
        return None
    month_day = re.search(r"매월\s*\(([^)]*)\)일", text)
    weekday = re.search(r"매주\s*\(([^)]*)\)요일", text)
    if not month_day or not weekday:
        return text
    weekday_names = {
        "월": "Monday",
        "화": "Tuesday",
        "수": "Wednesday",
        "목": "Thursday",
        "금": "Friday",
        "토": "Saturday",
        "일": "Sunday",
    }
    day_name = weekday_names.get(weekday.group(1).strip(), weekday.group(1).strip())
    return (
        f"Every ({month_day.group(1)})th day of the month or every ({day_name}) day "
        "of the week. If the payment date falls on a holiday, the payment will be "
        "made on the day before the holiday."
    )


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
    values: dict[str, object] = _passthrough_known_fields(
        slots,
        set(editable_template_fields("standard_labor_contract_v6")),
    )
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
        "work_location",
        _first(slots.get("work_location"), company.get("address"), slots.get("workplace_address")),
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
    _put(values, "working_hours_en", _english_working_hours(slots.get("working_hours")))
    _put(
        values,
        "probation_wage_detail_en",
        _first(
            slots.get("probation_wage_detail_en"),
            _english_probation_wage(slots.get("probation_wage_detail")),
        ),
    )
    _put(
        values,
        "payment_date_detail_en",
        _first(
            slots.get("payment_date_detail_en"),
            _english_payment_date(slots.get("payment_date_detail")),
        ),
    )
    _put(
        values,
        "employee_home_address",
        _first(slots.get("home_country_address"), slots.get("employee_home_address")),
    )
    _put(values, "contract_date", slots.get("contract_date"))
    _put(values, "monthly_wage", _first(slots.get("monthly_wage"), slots.get("wage")))
    _put(values, "base_wage", _first(slots.get("base_wage"), slots.get("wage")))
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
        _first(
            company.get("employer_name"),
            slots.get("representative"),
            slots.get("employer_name"),
        ),
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
        _first(
            company.get("employer_name"),
            slots.get("applicant_name"),
            slots.get("employer_name"),
        ),
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
        _first(
            slots.get("lodging"),
            slots.get("work_location"),
            slots.get("foreign_korea_address"),
        ),
    )
    _put(values, "foreign_phone", slots.get("phone"))
    _put(values, "stay_purpose", _first(slots.get("stay_purpose"), "취업"))
    _put(
        values,
        "guarantor_name",
        _first(
            company.get("employer_name"),
            slots.get("guarantor_name"),
            slots.get("employer_name"),
        ),
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
    values = dict(mapper(state))
    slots = _slots(state)
    # Handwritten mapper에 아직 없는 템플릿 필드는 HR 보충 슬롯을 그대로 사용한다.
    for field_name in editable_template_fields(template_id):
        value = slots.get(field_name)
        if value not in (None, ""):
            values[field_name] = value
    fields = editable_template_fields(template_id)
    for field_name, specification in fields.items():
        source_field = specification.get("mirror_of")
        if (
            isinstance(source_field, str)
            and field_name not in values
            and source_field in values
        ):
            values[field_name] = values[source_field]
    return values


def document_field_statuses(state: RenewalState) -> dict[str, dict[str, object]]:
    """Streamlit 시연용: 템플릿별 자동 채움·빈 텍스트·체크 필드를 계산한다."""
    statuses: dict[str, dict[str, object]] = {}
    for template_id in _TEMPLATE_MAPPERS:
        fields = editable_template_fields(template_id)
        values = values_for_template(template_id, state)
        field_names = sorted(fields)
        filled = sorted(
            name for name in field_names if values.get(name) not in (None, "")
        )
        empty_text = sorted(
            name
            for name, specification in fields.items()
            if str(specification.get("type", "text")) == "text"
            and values.get(name) in (None, "")
        )
        checkboxes = sorted(
            name
            for name, specification in fields.items()
            if str(specification.get("type", "text")) == "checkbox"
        )
        statuses[template_id] = {
            "fields": field_names,
            "filled_fields": filled,
            "empty_text_fields": empty_text,
            "checkbox_fields": checkboxes,
            "values": {name: values[name] for name in filled},
        }
    return statuses
