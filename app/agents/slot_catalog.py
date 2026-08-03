# 슬롯 키·sourceHint 카탈로그 (#74 Server 재조회용)

from __future__ import annotations

from typing import Any

# Knowledge/builtin required_slots와 맞춘 기본 sourceHint
SLOT_SOURCE_HINTS: dict[str, str] = {
    "worker_id": "REQUEST",
    "company_id": "REQUEST",
    "stay_expiry_date": "WORKER_DB",
    "contract_end_date": "WORKER_DB",
    "contract_start_date": "WORKER_DB",
    "display_name": "WORKER_DB",
    "full_name": "WORKER_DB",
    "nationality": "WORKER_DB",
    "nationality_code": "WORKER_DB",
    "preferred_language": "WORKER_DB",
    "work_status": "WORKER_DB",
    "document_type": "USER_INPUT",
    "pay_period": "USER_INPUT",
    "change_type": "USER_INPUT",
    "wage": "USER_INPUT",
    "working_hours": "USER_INPUT",
    "job_description": "USER_INPUT",
    "work_location": "USER_INPUT",
    "lodging": "USER_INPUT",
    "contract_period": "USER_INPUT",
    "passport_number": "DOCUMENT_OCR",
    "alien_registration_number": "DOCUMENT_OCR",
    "date_of_birth": "DOCUMENT_OCR",
}


# missing 슬롯 목록을 Server 재조회용 requestedFields로 변환
def requested_fields_from_missing(missing_slots: list[str]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()
    for key in missing_slots:
        if not key or key in seen:
            continue
        seen.add(key)
        fields.append(
            {
                "key": key,
                "source_hint": SLOT_SOURCE_HINTS.get(key, "USER_INPUT"),
            }
        )
    return fields


# camelCase API용으로 sourceHint 키 변환
def requested_fields_for_api(missing_slots: list[str]) -> list[dict[str, Any]]:
    return [
        {"key": f["key"], "sourceHint": f["source_hint"]}
        for f in requested_fields_from_missing(missing_slots)
    ]
