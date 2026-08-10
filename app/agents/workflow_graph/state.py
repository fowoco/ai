# 재갱신 Shared State 계약 — Phase/Step·서류검증·progress·슈퍼바이저 신호

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

# 여권/외국인등록증 OCR로 채우는 신분 항목
IDENTITY_SLOTS: frozenset[str] = frozenset(
    {
        "passport_number",
        "alien_registration_number",
        "nationality",
        "full_name",
        "date_of_birth",
    }
)

HR_EXCLUDED_SLOTS: frozenset[str] = frozenset(
    {"passport_status", "arc_status", "arc_expiry_date"}
)


# 재갱신 한 건의 진행 상태 (노드·서브그래프 간 공유)
class RenewalState(TypedDict):

    task_id: str
    request_id: str
    instruction: str
    worker_id: NotRequired[str | None]
    company_id: NotRequired[str | None]
    intent: str
    workflow_id: str
    confidence: float
    slots: dict[str, Any]
    missing_slots: list[str]
    status: str
    outcome: str
    guide_message: NotRequired[str | None]
    worker_request_message: NotRequired[str | None]
    # Language Assistant (태정) — projection/결과 보관
    preferred_language: NotRequired[str | None]
    nationality_code: NotRequired[str | None]
    request_context: NotRequired[dict[str, Any] | None]
    language_assistant: NotRequired[dict[str, Any] | None]
    documents: list[dict[str, Any]]
    ocr_result: NotRequired[dict[str, Any] | None]
    generated_documents: list[dict[str, Any]]
    worker_record: NotRequired[dict[str, Any] | None]
    company_record: NotRequired[dict[str, Any] | None]
    scenario: NotRequired[str | None]
    errors: list[str]
    # 회의 정렬 — Phase/Step·증거·슈퍼바이저
    phase: NotRequired[str | None]
    step: NotRequired[str | None]
    progress_events: NotRequired[list[dict[str, Any]]]
    evidence: NotRequired[list[dict[str, str]]]
    document_validation: NotRequired[dict[str, Any] | None]
    case_signals: NotRequired[list[str]]
    supervisor_reason: NotRequired[str | None]
    supervisor_source: NotRequired[str | None]
    supervisor_route: NotRequired[str | None]
    active_subgraph: NotRequired[str | None]


# 초기 Shared State 생성
def empty_renewal_state(
    *,
    task_id: str,
    request_id: str,
    instruction: str,
    worker_id: str | None = None,
    company_id: str | None = None,
    slots: dict[str, Any] | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> RenewalState:
    return RenewalState(
        task_id=task_id,
        request_id=request_id,
        instruction=instruction,
        worker_id=worker_id,
        company_id=company_id,
        intent="",
        workflow_id="",
        confidence=0.0,
        slots=dict(slots or {}),
        missing_slots=[],
        status="DRAFT",
        outcome="",
        guide_message=None,
        worker_request_message=None,
        preferred_language=None,
        nationality_code=None,
        request_context=None,
        language_assistant=None,
        documents=list(documents or []),
        ocr_result=None,
        generated_documents=[],
        worker_record=None,
        company_record=None,
        scenario=None,
        errors=[],
        phase=None,
        step=None,
        progress_events=[],
        evidence=[],
        document_validation=None,
        case_signals=[],
        supervisor_reason=None,
        supervisor_source=None,
        supervisor_route=None,
        active_subgraph=None,
    )
