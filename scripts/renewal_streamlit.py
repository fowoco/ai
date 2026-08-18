"""Local UI for Renewal Graph scenario 1 and scenario 2 demonstrations."""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.agents.workflow_graph.document_field_map import document_field_statuses
from app.agents.workflow_graph.init_state import init_renewal_state_from_bundle
from app.agents.workflow_graph.ocr_bridge import normalize_ocr_fields
from app.api.schemas.workflows import RenewalRunRequest
from app.documents.editing.template_names import template_display_name

DEMO_SERVER_COMPANY_ID = "90000000-0000-0000-0000-000000000001"
DEMO_SERVER_WORKER_ID = "92000000-0000-0000-0000-000000000006"
SCENARIO_TWO_DOCUMENT_REQUESTS: tuple[dict[str, str], ...] = (
    {
        "document_type": "PASSPORT_COPY",
        "label": "여권 사본",
        "message": "체류기간 연장 신청을 위해 여권 사본을 제출해 주세요.",
    },
    {
        "document_type": "ARC",
        "label": "외국인등록증 앞·뒤면",
        "message": "체류기간 연장 신청을 위해 외국인등록증 앞·뒤면을 제출해 주세요.",
    },
)
SCENARIO_TWO_IDENTITY_DEFAULTS: dict[str, str] = {
    "full_name": "NGUYEN VAN AN",
    "date_of_birth": "1995-04-12",
    "nationality": "VIET NAM",
    "passport_number": "P1234567",
    "passport_issue_date": "2021.03.20",
    "passport_expiry_date": "2031.03.19",
    "alien_registration_number": "900101-1234567",
    "stay_expiration_date": (date.today() + timedelta(days=45)).isoformat(),
    "residence_address_1": "경기도 안산시 단원구 산단로 000",
}
RENEWAL_REQUIRED_FIELD_LABELS = {
    "wage": "임금",
    "working_hours": "근무시간",
    "job_description": "업무",
    "work_location": "근무지",
    "lodging": "숙소",
    "contract_period": "계약기간",
}
DEMO_FORM_DEFAULTS: dict[str, Any] = {
    "wage": "2500000",
    "working_hours": "09시 00분 ~ 18시 00분",
    "job_description": "금속 부품 조립",
    "industry": "제조업",
    "business_description": "자동차 부품 제조 및 조립",
    "work_location": "경기도 안산시 단원구 산단로 000",
    "lodging": "사업장 기숙사",
    "home_country_address": "Ha Noi, Viet Nam",
    "phone": "010-1234-5678",
    "contract_period": "12",
    "contract_months": "12",
    "contract_date": date.today().strftime("%Y년 %m월 %d일"),
    "application_date": date.today().strftime("%Y.%m.%d"),
    "use_probation": True,
    "probation_three_months": True,
    "daily_overtime_hours": "2",
    "daily_overtime_limit": "4",
    "shift_two_two": True,
    "recess_minutes": "60",
    "holiday_sunday": True,
    "holiday_legal": True,
    "holiday_paid": True,
    "holiday_every_saturday": True,
    "monthly_wage": "2,500,000",
    "base_wage": "2,400,000",
    "fixed_allowances": "식대 수당: 100,000원, 교통 수당: 100,000원",
    "bonus": "0",
    "probation_wage_detail": "2,250,000원, 3개월 이내 근무기간 2,400,000원",
    "payment_date_detail": (
        "매월 (25)일 또는 매주 (금)요일. 다만, 임금 지급일이 공휴일인 경우에는 전날에 지급함."
    ),
    "payment_bank": True,
    "accommodation_provided": True,
    "accommodation_workplace_building": True,
    "accommodation_cost": "50,000",
    "meal_breakfast": True,
    "meal_lunch": True,
    "meal_dinner": True,
    "meal_cost": "30,000",
    "passport_issue_date": "2021.03.20",
    "passport_expiry_date": "2031.03.19",
    "telephone": "031-000-0000",
    "cell_phone": "010-1234-5678",
    "home_country_phone": "+84-24-1234-5678",
    "school_name": "해당 없음",
    "school_phone": "해당 없음",
    "reentry_period": "해당 없음",
    "email": "nguyen.van.an@example.test",
    "refund_bank_account": "DEMO BANK 123-456-7890",
    "sex_male": True,
    "employee_1_serial": "1",
    "check_eligible_industry": True,
    "check_no_adjustment_dismissal": True,
    "check_no_unpaid_wages": True,
    "check_insurance": True,
    "check_departure_guarantee": True,
    "foreign_male": True,
    "guarantor_male": True,
    "guarantor_nationality": "대한민국",
    "guarantor_passport_or_birthdate": "1975.01.01",
    "guarantor_address": "경기도 안산시 단원구 산단로 000",
    "position": "대표이사",
    "guarantee_period": "2026.08.18 ~ 2027.08.17",
    "guarantee_date": date.today().strftime("%Y년 %m월 %d일"),
}


def renewal_required_fields(missing_slots: Sequence[object]) -> list[dict[str, str]]:
    """Agent가 실제로 판정하는 부족 슬롯을 HR 입력 필드로 만든다."""
    fields: list[dict[str, str]] = []
    for slot in missing_slots:
        if not isinstance(slot, str) or not slot:
            continue
        fields.append(
            {
                "key": slot,
                "label": RENEWAL_REQUIRED_FIELD_LABELS.get(slot, slot),
            }
        )
    return fields


def _scenario_one_server_context() -> dict[str, Any]:
    """FOWOCO Server Demo Seed IDs를 쓰는 승인 OCR 완료 가정 컨텍스트."""
    today = date.today()
    stay_expiry = (today + timedelta(days=45)).isoformat()
    contract_end = (today + timedelta(days=180)).isoformat()
    ocr_result = {
        "full_name": "NGUYEN VAN AN",
        "date_of_birth": "1995-04-12",
        "nationality": "VIET NAM",
        "passport_number": "DEMO-P06-NOT-VALID",
        "alien_registration_number": "DEMO-ARC-06-NOT-VALID",
        "stay_expiration_date": stay_expiry,
        "residence_address_1": "DEMO RESIDENCE 06, SAMPLE-RO, FOWOCO CITY",
    }
    return {
        "worker": {
            "displayName": "응웬반A",
            "nationalityCode": "VN",
            "preferredLanguage": "vi",
            "workStatus": "ACTIVE",
            "stayExpiryDate": stay_expiry,
            "contractStartDate": (today - timedelta(days=365)).isoformat(),
            "contractEndDate": contract_end,
        },
        "company": {
            "name": "FOWOCO Demo Company",
            "status": "ACTIVE",
            "employer_name": "김민수",
            "business_number": "123-45-67890",
            "phone": "031-000-0000",
            "address": "경기도 안산시 단원구 산단로 000",
        },
        "slots": {
            "passport_status": "VERIFIED",
            "arc_status": "VERIFIED",
        },
        "documents": [
            {
                "documentType": "PASSPORT_COPY",
                "filename": "server-db:passport-copy",
                "fields": {
                    "full_name": ocr_result["full_name"],
                    "date_of_birth": ocr_result["date_of_birth"],
                    "nationality": ocr_result["nationality"],
                    "passport_number": ocr_result["passport_number"],
                },
                "hints": {"submissionStatus": "VERIFIED", "source": "server_db"},
            },
            {
                "documentType": "ARC",
                "filename": "server-db:arc",
                "fields": {
                    "alien_registration_number": ocr_result[
                        "alien_registration_number"
                    ],
                    "stay_expiration_date": ocr_result["stay_expiration_date"],
                    "residence_address_1": ocr_result["residence_address_1"],
                },
                "hints": {"submissionStatus": "VERIFIED", "source": "server_db"},
            },
        ],
        "ocr_result": ocr_result,
    }


def _scenario_two_server_context() -> dict[str, Any]:
    """Server에는 근로자·회사만 있고 신분서류는 아직 없는 가정 컨텍스트."""
    context = _scenario_one_server_context()
    context["slots"] = {
        "passport_status": "MISSING",
        "arc_status": "MISSING",
    }
    context["documents"] = []
    context.pop("ocr_result", None)
    return context


def build_scenario_two_language_request() -> dict[str, Any]:
    """신분서류 요청 단계에서 Language Assistant Graph에 보낼 요청을 만든다."""
    context = _scenario_two_server_context()
    worker = context["worker"]
    return {
        "worker_id": DEMO_SERVER_WORKER_ID,
        "preferred_language": worker["preferredLanguage"],
        "nationality_code": worker["nationalityCode"],
        "request_context": {
            "request_reason": "체류기간 연장 신청",
            "requested_items": ["여권 사본 1부", "외국인등록증 사본 1부"],
            "deadline": worker["stayExpiryDate"],
            "submission_method": "담당자(HR)에게 제출",
        },
    }


def _scenario_two_documents(identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Language Assistant로 수신한 두 신분서류의 구조화 결과를 만든다."""
    values = dict(identity)

    def pick(*keys: str) -> dict[str, Any]:
        return {
            key: values[key]
            for key in keys
            if values.get(key) not in (None, "")
        }

    return [
        {
            "documentType": "PASSPORT_COPY",
            "filename": "language-assistant:passport-copy",
            "fields": pick(
                "full_name",
                "date_of_birth",
                "nationality",
                "passport_number",
                "passport_issue_date",
                "passport_expiry_date",
            ),
            "hints": {
                "submissionStatus": "RECEIVED",
                "source": "language_assistant_demo",
            },
        },
        {
            "documentType": "ARC",
            "filename": "language-assistant:arc",
            "fields": pick(
                "alien_registration_number",
                "stay_expiration_date",
                "residence_address_1",
            ),
            "hints": {
                "submissionStatus": "RECEIVED",
                "source": "language_assistant_demo",
            },
        },
    ]


def build_renewal_payload(
    *,
    request_id: str,
    instruction: str,
    worker_id: str,
    company_id: str,
    slots: Mapping[str, Any],
    worker: Mapping[str, Any] | None = None,
    company: Mapping[str, Any] | None = None,
    documents: list[Mapping[str, Any]] | None = None,
    ocr_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requestId": request_id,
        "instruction": instruction,
        "workerId": worker_id,
        "companyId": company_id,
        "slots": dict(slots),
        "documents": [dict(document) for document in documents or []],
    }
    if worker is not None:
        payload["worker"] = {"workerId": worker_id, **dict(worker)}
    if company is not None:
        payload["company"] = {"companyId": company_id, **dict(company)}
    if ocr_result is not None:
        payload["ocrResult"] = dict(ocr_result)
    return payload


def build_scenario_one_payload(
    *,
    request_id: str,
    instruction: str,
    supplemental_slots: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """직접 신분정보를 쓰지 않고 Server DB/OCR 스냅샷에서 시작하는 요청."""
    context = _scenario_one_server_context()
    slots = {**context["slots"], **dict(supplemental_slots or {})}
    return build_renewal_payload(
        request_id=request_id,
        instruction=instruction,
        worker_id=DEMO_SERVER_WORKER_ID,
        company_id=DEMO_SERVER_COMPANY_ID,
        slots=slots,
        worker=context["worker"],
        company=context["company"],
        documents=context["documents"],
        ocr_result=context["ocr_result"],
    )


def build_scenario_two_payload(
    *,
    request_id: str,
    instruction: str,
    received_identity: Mapping[str, Any] | None = None,
    supplemental_slots: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """신분서류 수신 전/후를 분리해 Scenario 2 요청 payload를 만든다."""
    context = _scenario_two_server_context()
    slots = {**context["slots"], **dict(supplemental_slots or {})}
    documents: list[Mapping[str, Any]] = []
    ocr_result: Mapping[str, Any] | None = None

    if received_identity:
        slots.update({"passport_status": "VERIFIED", "arc_status": "VERIFIED"})
        documents = _scenario_two_documents(received_identity)
        ocr_result = dict(received_identity)

    return build_renewal_payload(
        request_id=request_id,
        instruction=instruction,
        worker_id=DEMO_SERVER_WORKER_ID,
        company_id=DEMO_SERVER_COMPANY_ID,
        slots=slots,
        worker=context["worker"],
        company=context["company"],
        documents=documents,
        ocr_result=ocr_result,
    )


def call_renewal_server(
    base_url: str,
    payload: Mapping[str, Any],
    *,
    token: str = "",
    timeout: float = 120.0,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = httpx.post(
        f"{base_url.rstrip('/')}/internal/v1/workflows/renewal/run",
        json=dict(payload),
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def call_language_assistant(
    base_url: str,
    payload: Mapping[str, Any],
    *,
    token: str = "",
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Language Assistant Graph HTTP endpoint를 호출한다."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = httpx.post(
        f"{base_url.rstrip('/')}/internal/v1/language-assistant",
        json=dict(payload),
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def template_statuses_for_response(
    payload: Mapping[str, Any], result: Mapping[str, Any] | None = None
) -> dict[str, dict[str, object]]:
    """Agent가 받은 Server 컨텍스트와 응답 슬롯으로 빈 템플릿 칸을 계산한다."""
    request = RenewalRunRequest.model_validate(dict(payload))
    state = init_renewal_state_from_bundle(
        request_id=request.request_id,
        instruction=request.instruction,
        task_id=request.task_id,
        worker_id=request.worker_id,
        company_id=request.company_id,
        slots=request.slots,
        documents=[document.model_dump(by_alias=False) for document in request.documents],
        worker=request.worker.model_dump(by_alias=False) if request.worker else None,
        company=request.company.model_dump(by_alias=False) if request.company else None,
        task=request.task.model_dump(by_alias=False) if request.task else None,
    )
    if result:
        state["slots"] = {**state["slots"], **dict(result.get("slots") or {})}
    raw_ocr = dict((result or {}).get("ocrResult") or request.ocr_result or {})
    normalized = normalize_ocr_fields(raw_ocr)
    if raw_ocr or normalized:
        state["ocr_result"] = {**raw_ocr, **normalized}
        state["slots"] = {**state["slots"], **normalized}
    return document_field_statuses(state)


def _text(st: Any, label: str, key: str, default: str = "") -> str:
    return st.text_input(label, value=default, key=key).strip()


def _run(
    st: Any,
    *,
    base_url: str,
    token: str,
    payload: dict[str, Any],
    state_prefix: str = "",
) -> None:
    payload_key = f"{state_prefix}last_payload" if state_prefix else "last_payload"
    result_key = f"{state_prefix}last_result" if state_prefix else "last_result"
    st.session_state[payload_key] = payload
    try:
        st.session_state[result_key] = call_renewal_server(
            base_url,
            payload,
            token=token,
        )
    except httpx.HTTPStatusError as exc:
        st.session_state.pop(result_key, None)
        st.error(f"서버 응답 오류: HTTP {exc.response.status_code}")
        st.code(exc.response.text)
    except httpx.HTTPError as exc:
        st.session_state.pop(result_key, None)
        st.error(f"서버 연결 오류: {exc}")


def _show_result(st: Any, result: Mapping[str, Any]) -> None:
    st.subheader("Renewal Graph 결과")
    first, second, third = st.columns(3)
    first.metric("status", result.get("status", ""))
    second.metric("outcome", result.get("outcome", ""))
    third.metric("scenario", result.get("scenario", ""))
    st.write("Renewal Graph 필수 부족값:", result.get("missingSlots", []))
    if result.get("requestedFields"):
        st.write("담당자 입력 요청:", result["requestedFields"])
    if result.get("generatedDocuments"):
        st.write("생성 문서:")
        for document in result["generatedDocuments"]:
            st.json(document)
            path = document.get("path")
            if path and Path(path).is_file():
                file_path = Path(path)
                st.download_button(
                    f"다운로드: {file_path.name}",
                    data=file_path.read_bytes(),
                    file_name=file_path.name,
                    key=f"download-{file_path}",
                )


def _render_template_gap_form(
    st: Any,
    statuses: Mapping[str, Mapping[str, object]],
    *,
    missing_slots: Sequence[object],
) -> dict[str, Any] | None:
    previous = dict(st.session_state.get("scenario_one_supplemental_slots") or {})
    supplemental: dict[str, Any] = {}
    with st.form("template_gap_form"):
        required_fields = renewal_required_fields(missing_slots)
        if required_fields:
            st.markdown("#### Renewal Graph 진행 필수 정보")
            st.caption(
                "아래 항목은 템플릿의 필드명과 별개로, 문서 생성 단계 전환에 필요합니다."
            )
            for field in required_fields:
                field_name = field["key"]
                value = st.text_input(
                    field["label"],
                    value=str(previous.get(field_name, DEMO_FORM_DEFAULTS.get(field_name, ""))),
                    key=f"scenario-one-required-{field_name}",
                ).strip()
                if value:
                    supplemental[field_name] = value
        for template_id, status in statuses.items():
            fields = list(status["fields"])
            filled = list(status["filled_fields"])
            empty_text = list(status["empty_text_fields"])
            checkboxes = list(status["checkbox_fields"])
            values = dict(status["values"])
            with st.expander(
                f"{template_display_name(template_id)} — 자동 채움 {len(filled)}/{len(fields)}",
                expanded=bool(empty_text),
            ):
                st.caption("사진·서명 필드는 이번 시나리오에서 제외했습니다.")
                if values:
                    st.json(values)
                if empty_text:
                    st.caption("비어 있는 텍스트 필드 — 필요하면 입력 후 재실행")
                    for field_name in empty_text:
                        key = f"scenario-one-text-{template_id}-{field_name}"
                        value = st.text_input(
                            field_name,
                            value=str(
                                previous.get(
                                    field_name,
                                    DEMO_FORM_DEFAULTS.get(field_name, ""),
                                )
                            ),
                            key=key,
                        ).strip()
                        if value:
                            supplemental[field_name] = value
                if checkboxes:
                    st.caption("체크 항목")
                    for field_name in checkboxes:
                        key = f"scenario-one-check-{template_id}-{field_name}"
                        default = bool(
                            previous.get(
                                field_name,
                                values.get(
                                    field_name,
                                    DEMO_FORM_DEFAULTS.get(field_name, False),
                                ),
                            )
                        )
                        checked = st.checkbox(field_name, value=default, key=key)
                        if (
                            checked
                            or field_name in previous
                            or field_name in values
                            or field_name in DEMO_FORM_DEFAULTS
                        ):
                            supplemental[field_name] = checked
        submitted = st.form_submit_button("입력한 부족값으로 Renewal Graph 재실행", type="primary")
    if not submitted:
        return None
    return {**previous, **supplemental}


def _render_scenario_two(
    st: Any,
    *,
    base_url: str,
    token: str,
    instruction: str,
) -> None:
    """신분서류 요청 후 수신값을 반영해 Graph를 실행하는 Scenario 2 UI."""
    context = _scenario_two_server_context()
    st.subheader("1. Server DB 컨텍스트")
    st.caption(
        "회사·근로자 레코드는 Server에서 조회했지만, 여권과 외국인등록증은 아직 없는 상태입니다."
    )
    first, second = st.columns(2)
    first.json({"workerId": DEMO_SERVER_WORKER_ID, **context["worker"]})
    second.json({"companyId": DEMO_SERVER_COMPANY_ID, **context["company"]})
    st.warning("신분서류 없음 — 여권 사본과 외국인등록증을 먼저 요청해야 합니다.")

    st.subheader("2. Language Assistant 서류 요청")
    for request in SCENARIO_TWO_DOCUMENT_REQUESTS:
        st.markdown(f"**{request['label']}** (`{request['document_type']}`)")
        st.info(request["message"])

    if st.button(
        "Language Assistant로 근로자에게 서류 요청",
        type="primary",
        key="scenario-two-request",
    ):
        language_request = build_scenario_two_language_request()
        st.session_state["scenario_two_language_request"] = language_request
        st.session_state.pop("scenario_two_language_result", None)
        st.session_state.pop("scenario_two_language_error", None)
        try:
            language_result = call_language_assistant(
                base_url,
                language_request,
                token=token,
            )
        except httpx.HTTPStatusError as exc:
            st.session_state["scenario_two_language_error"] = (
                f"HTTP {exc.response.status_code}: {exc.response.text}"
            )
            st.session_state["scenario_two_requested"] = False
        except httpx.HTTPError as exc:
            st.session_state["scenario_two_language_error"] = str(exc)
            st.session_state["scenario_two_requested"] = False
        else:
            st.session_state["scenario_two_language_result"] = language_result
            st.session_state["scenario_two_requested"] = True
            st.session_state.pop("scenario_two_identity", None)
            st.session_state.pop("scenario_two_last_result", None)
            st.session_state.pop("scenario_two_last_payload", None)
        st.rerun()

    language_error = st.session_state.get("scenario_two_language_error")
    if language_error:
        st.error("Language Assistant Graph 실행 실패")
        st.code(language_error)
        st.caption(
            "현재 Agent 서버에 LLM provider/base URL/model이 설정되지 않아 "
            "LANGUAGE_ASSISTANT_NOT_CONFIGURED가 반환된 상태입니다."
        )
        with st.expander("Language Assistant 요청 JSON"):
            st.json(st.session_state.get("scenario_two_language_request", {}))
        return

    language_result = st.session_state.get("scenario_two_language_result")
    if language_result:
        st.success("Language Assistant Graph 실행 완료")
        first, second = st.columns(2)
        first.metric("target language", language_result.get("target_language", ""))
        second.metric("generation status", language_result.get("generation_status", ""))
        if language_result.get("standard_korean_text"):
            st.info(language_result["standard_korean_text"])
        if language_result.get("easy_korean_text"):
            st.info(language_result["easy_korean_text"])
        if language_result.get("translated_text"):
            st.info(language_result["translated_text"])
        with st.expander("Language Assistant 요청/응답 JSON"):
            st.json(
                {
                    "request": st.session_state.get(
                        "scenario_two_language_request", {}
                    ),
                    "response": language_result,
                }
            )

    requested = bool(st.session_state.get("scenario_two_requested"))
    if not requested:
        st.info("위 버튼을 누르면 Language Assistant Graph가 실행됩니다.")
        return

    st.success("Language Assistant 요청이 완료되었습니다. 이제 근로자 제출값을 수신합니다.")
    st.subheader("3. 근로자 제출 서류 수신")
    st.caption(
        "이번 로컬 테스트에서는 실제 OCR 업로드 대신, "
        "수신된 서류에서 추출된 구조화 값을 입력합니다."
    )
    previous = dict(
        st.session_state.get("scenario_two_identity") or SCENARIO_TWO_IDENTITY_DEFAULTS
    )
    received_identity: dict[str, str] = {}
    with st.form("scenario_two_received_form"):
        fields = (
            ("full_name", "이름"),
            ("date_of_birth", "생년월일"),
            ("nationality", "국적"),
            ("passport_number", "여권번호"),
            ("passport_issue_date", "여권 발급일"),
            ("passport_expiry_date", "여권 만료일"),
            ("alien_registration_number", "외국인등록번호"),
            ("stay_expiration_date", "체류 만료일"),
            ("residence_address_1", "국내 체류지 주소"),
        )
        for field_name, label in fields:
            received_identity[field_name] = st.text_input(
                label,
                value=str(previous.get(field_name, "")),
                key=f"scenario-two-received-{field_name}",
            ).strip()
        submitted = st.form_submit_button(
            "수신 서류 반영 후 Renewal Graph 실행", type="primary"
        )

    if submitted:
        st.session_state["scenario_two_identity"] = received_identity
        payload = build_scenario_two_payload(
            request_id=f"scenario-two-{uuid.uuid4().hex[:8]}",
            instruction=instruction,
            received_identity=received_identity,
            supplemental_slots=DEMO_FORM_DEFAULTS,
        )
        _run(
            st,
            base_url=base_url,
            token=token,
            payload=payload,
            state_prefix="scenario_two_",
        )
        st.rerun()

    result = st.session_state.get("scenario_two_last_result")
    payload = st.session_state.get("scenario_two_last_payload")
    if not result or not payload:
        return

    st.subheader("4. Renewal Graph 결과")
    _show_result(st, result)
    statuses = template_statuses_for_response(payload, result)
    st.subheader("5. 템플릿 매핑 결과")
    for template_id, status in statuses.items():
        filled = len(status["filled_fields"])
        total = len(status["fields"])
        empty = list(status["empty_text_fields"])
        if empty:
            st.warning(f"{template_display_name(template_id)}: 빈 텍스트 필드 {empty}")
        else:
            st.success(f"{template_display_name(template_id)}: {filled}/{total} 자동 매핑")

    with st.expander("Agent 요청 JSON"):
        st.json(payload)
    with st.expander("Agent 응답 JSON"):
        st.json(result)


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Renewal Graph 로컬 테스트", layout="wide")

    with st.sidebar:
        scenario = st.radio(
            "테스트 시나리오",
            (
                "시나리오 1: Server DB/OCR 보유",
                "시나리오 2: 신분서류 요청 후 수신",
            ),
            key="scenario_mode",
        )
        base_url = _text(
            st,
            "Agent server URL",
            "base_url",
            os.getenv("FOWOCO_AGENT_BASE_URL", "http://127.0.0.1:8000"),
        )
        token = st.text_input(
            "Internal API token",
            value=os.getenv("FOWOCO_INTERNAL_API_TOKEN", ""),
            type="password",
            key="token",
        ).strip()
        instruction = _text(st, "요청", "instruction", "체류기간 연장 갱신")

    if scenario.startswith("시나리오 2"):
        st.title("Renewal Graph 로컬 테스트 — 시나리오 2")
        st.caption("신분서류 없음 → Language Assistant 요청 → 제출값 수신 → 문서 초안")
        _render_scenario_two(
            st,
            base_url=base_url,
            token=token,
            instruction=instruction,
        )
        return

    st.title("Renewal Graph 로컬 테스트 — 시나리오 1")
    st.caption("Server DB/OCR 컨텍스트 → 서류별 빈 필드 확인 → HR 보충 입력 → 문서 초안")

    context = _scenario_one_server_context()
    st.subheader("1. Server DB 컨텍스트")
    st.caption(
        "FOWOCO Server Demo Seed ID를 사용한 로컬 승인 OCR 완료 가정입니다. "
        "회사·근로자 정보는 여기서 수정하지 않습니다."
    )
    first, second = st.columns(2)
    first.json({"workerId": DEMO_SERVER_WORKER_ID, **context["worker"]})
    second.json({"companyId": DEMO_SERVER_COMPANY_ID, **context["company"]})
    st.write("DB/OCR에서 채운 신분 필드:", sorted(context["ocr_result"]))

    if st.button("DB 컨텍스트로 부족값 검사", type="primary"):
        payload = build_scenario_one_payload(
            request_id=f"scenario-one-{uuid.uuid4().hex[:8]}",
            instruction=instruction,
            supplemental_slots=st.session_state.get("scenario_one_supplemental_slots", {}),
        )
        _run(st, base_url=base_url, token=token, payload=payload)

    result = st.session_state.get("last_result")
    payload = st.session_state.get("last_payload")
    if not result or not payload:
        return

    _show_result(st, result)
    st.subheader("2. 서류별 빈 필드 확인·입력")
    missing_slots = list(result.get("missingSlots") or [])
    if missing_slots:
        st.warning(
            "문서 생성으로 진행하려면 아래 ‘Renewal Graph 진행 필수 정보’부터 입력해 주세요."
        )
    st.caption(
        "여기서의 ‘빈 필드’는 템플릿에 값이 아직 매핑되지 않은 칸입니다. "
        "법적 필수 여부와는 별도입니다."
    )
    supplemental = _render_template_gap_form(
        st,
        template_statuses_for_response(payload, result),
        missing_slots=missing_slots,
    )
    if supplemental is not None:
        st.session_state["scenario_one_supplemental_slots"] = supplemental
        refreshed_payload = build_scenario_one_payload(
            request_id=f"scenario-one-{uuid.uuid4().hex[:8]}",
            instruction=instruction,
            supplemental_slots=supplemental,
        )
        _run(st, base_url=base_url, token=token, payload=refreshed_payload)
        st.rerun()

    with st.expander("Agent 요청 JSON"):
        st.json(payload)
    with st.expander("Agent 응답 JSON"):
        st.json(result)


if __name__ == "__main__":
    main()
