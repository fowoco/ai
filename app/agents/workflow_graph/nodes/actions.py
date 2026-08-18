# 재갱신 분기·안내·서류생성·OCR 저장·슈퍼바이저 적용 노드

from __future__ import annotations

from typing import Any, Literal

from ..document_validation import validate_identity_documents
from ..phases import WorkflowPhase, WorkflowStep, append_progress, progress_event
from ..state import RenewalState
from ..status import TaskStatus
from ..supervisor import decide_route


# DB에서 worker/company 조회 후 slots 선채움
def load_context(state: RenewalState, *, lookup: Any) -> dict[str, Any]:
    worker_id = state.get("worker_id")
    company_id = state.get("company_id")
    worker = lookup.get_worker(worker_id) if worker_id else None
    company = lookup.get_company(company_id) if company_id else None
    slots = dict(state.get("slots") or {})
    if worker:
        for key in ("worker_id", "stay_expiry_date", "contract_end_date", "display_name"):
            if worker.get(key) and key not in slots:
                slots[key] = worker[key]
        if worker.get("display_name") and "full_name" not in slots:
            slots["full_name"] = worker["display_name"]
    events = append_progress(
        state,
        progress_event(
            phase=WorkflowPhase.INTAKE_ANALYSIS,
            step=WorkflowStep.STEP_2_INTENT_SLOT,
            message="load_context: worker/company 조회",
            subgraph="main",
        ),
    )
    return {
        "worker_record": worker,
        "company_record": company,
        "slots": slots,
        "progress_events": events,
        "active_subgraph": "main",
    }


ScenarioRoute = Literal["ask_hr", "ask_worker", "generate", "ocr", "out_of_scope"]


# 슈퍼바이저 판단을 State에 기록하고 라우트 문자열 반환
def apply_supervisor(state: RenewalState) -> dict[str, Any]:
    decision = decide_route(state)
    validation = decision.document_validation or validate_identity_documents(state)
    events = append_progress(
        state,
        progress_event(
            phase=decision.phase,
            step=decision.step,
            message=f"Supervisor→{decision.route}: {decision.reason}",
            subgraph="supervisor",
        ),
    )
    evidence = list(state.get("evidence") or [])
    for item in validation.evidence:
        evidence.append(dict(item))
    return {
        "phase": decision.phase.value,
        "step": decision.step.value,
        "supervisor_reason": decision.reason,
        "supervisor_source": decision.source,
        "case_signals": list(decision.case_signals),
        "document_validation": {
            "passport": validation.passport,
            "alien_registration": validation.alien_registration,
            "combo": validation.combo,
            "missing_identity_slots": list(validation.missing_identity_slots),
        },
        "evidence": evidence,
        "progress_events": events,
        "active_subgraph": "supervisor",
        "supervisor_route": decision.route,
    }


# 슈퍼바이저 라우트 읽기 (apply_supervisor 직후)
def route_from_supervisor(state: RenewalState) -> ScenarioRoute:
    route = state.get("supervisor_route") or decide_route(state).route
    if route in {"ask_hr", "ask_worker", "generate", "ocr", "out_of_scope"}:
        return route  # type: ignore[return-value]
    return "ask_hr"


# 하위 호환: 예전 이름 — 슈퍼바이저 규칙 위임
def route_scenario(state: RenewalState) -> ScenarioRoute:
    return route_from_supervisor(state)


# 지원 범위 밖 요청을 종료 상태로 고정
def mark_out_of_scope(state: RenewalState) -> dict[str, Any]:
    events = append_progress(
        state,
        progress_event(
            phase=WorkflowPhase.INTAKE_ANALYSIS,
            step=WorkflowStep.STEP_2_INTENT_SLOT,
            message="OUT_OF_SCOPE 종료",
            subgraph="main",
        ),
    )
    return {
        "scenario": "out_of_scope",
        "status": TaskStatus.CANCELLED.value,
        "outcome": "OUT_OF_SCOPE",
        "phase": WorkflowPhase.INTAKE_ANALYSIS.value,
        "step": WorkflowStep.STEP_2_INTENT_SLOT.value,
        "case_signals": ["CANCEL_OUT_OF_SCOPE"],
        "progress_events": events,
    }


# 담당자 입력 — 화면에 계약·근무 정보 입력 요청
def mark_ask_hr(state: RenewalState) -> dict[str, Any]:
    events = append_progress(
        state,
        progress_event(
            phase=WorkflowPhase.VALIDATION_COMMUNICATION,
            step=WorkflowStep.STEP_5_CASE_SIGNAL,
            message="담당자 입력 대기: 임금·근무시간 등 (ask_hr)",
            subgraph="main",
        ),
    )
    return {
        "scenario": "ask_hr",
        "status": TaskStatus.NEEDS_INFO.value,
        "outcome": "NEEDS_INFO",
        "phase": WorkflowPhase.VALIDATION_COMMUNICATION.value,
        "step": WorkflowStep.STEP_5_CASE_SIGNAL.value,
        "case_signals": list(state.get("case_signals") or ["REQUEST_CONTRACT_SLOTS"]),
        "progress_events": events,
        "active_subgraph": "main",
    }


# 안내문 · 태정 자리 (동료 Language 교체점)
def mark_guide_placeholder(state: RenewalState) -> dict[str, Any]:
    events = append_progress(
        state,
        progress_event(
            phase=WorkflowPhase.VALIDATION_COMMUNICATION,
            step=WorkflowStep.STEP_7_LANGUAGE_GUIDE,
            message="안내문(태정) 자리",
            subgraph="language",
        ),
    )
    return {
        "progress_events": events,
        "active_subgraph": "language",
        "phase": WorkflowPhase.VALIDATION_COMMUNICATION.value,
        "step": WorkflowStep.STEP_7_LANGUAGE_GUIDE.value,
    }


# 근로자 서류 — 여권·등록증 요청 문구 (Language Assistant 결과 우선)
def mark_ask_worker(state: RenewalState) -> dict[str, Any]:
    if state.get("guide_review_required"):
        signals = list(state.get("case_signals") or [])
        if "REVIEW_WORKER_GUIDE" not in signals:
            signals.append("REVIEW_WORKER_GUIDE")
        events = append_progress(
            state,
            progress_event(
                phase=WorkflowPhase.VALIDATION_COMMUNICATION,
                step=WorkflowStep.STEP_5_CASE_SIGNAL,
                message="근로자 안내문은 HR 검토 후 발송",
                subgraph="main",
            ),
        )
        return {
            "scenario": "ask_worker",
            "status": TaskStatus.READY_FOR_REVIEW.value,
            "outcome": "REVIEW_REQUIRED",
            "worker_request_message": None,
            "guide_review_required": True,
            "guide_failure_code": state.get("guide_failure_code")
            or "WORKER_GUIDE_UNAVAILABLE",
            "phase": WorkflowPhase.VALIDATION_COMMUNICATION.value,
            "step": WorkflowStep.STEP_5_CASE_SIGNAL.value,
            "case_signals": signals,
            "progress_events": events,
            "active_subgraph": "main",
        }

    existing = state.get("worker_request_message")
    if existing:
        events = append_progress(
            state,
            progress_event(
                phase=WorkflowPhase.VALIDATION_COMMUNICATION,
                step=WorkflowStep.STEP_5_CASE_SIGNAL,
                message="근로자 서류 요청: Language Assistant 안내문 사용",
                subgraph="main",
            ),
        )
        return {
            "scenario": "ask_worker",
            "status": TaskStatus.WAITING_WORKER.value,
            "outcome": "WAITING_WORKER",
            "worker_request_message": existing,
            "phase": WorkflowPhase.VALIDATION_COMMUNICATION.value,
            "step": WorkflowStep.STEP_5_CASE_SIGNAL.value,
            "case_signals": list(
                state.get("case_signals") or ["REQUEST_IDENTITY_DOCUMENT"]
            ),
            "progress_events": events,
            "active_subgraph": "main",
        }

    events = append_progress(
        state,
        progress_event(
            phase=WorkflowPhase.VALIDATION_COMMUNICATION,
            step=WorkflowStep.STEP_5_CASE_SIGNAL,
            message="근로자 안내문을 만들 수 없어 HR 검토 요청",
            subgraph="main",
        ),
    )
    return {
        "scenario": "ask_worker",
        "status": TaskStatus.READY_FOR_REVIEW.value,
        "outcome": "REVIEW_REQUIRED",
        "worker_request_message": None,
        "guide_review_required": True,
        "guide_failure_code": "WORKER_GUIDE_UNAVAILABLE",
        "phase": WorkflowPhase.VALIDATION_COMMUNICATION.value,
        "step": WorkflowStep.STEP_5_CASE_SIGNAL.value,
        "case_signals": list(state.get("case_signals") or [])
        + ["REVIEW_WORKER_GUIDE"],
        "progress_events": events,
        "active_subgraph": "main",
    }


# 슬롯 충분 시 documents 서비스(또는 stub)로 문서 채움
def generate_docs(
    state: RenewalState, *, document_generator: Any | None = None
) -> dict[str, Any]:
    from .document_generator import StubDocumentGenerator

    generator = document_generator or StubDocumentGenerator()
    docs = generator(state)
    return {
        "scenario": "generate",
        "generated_documents": docs,
        "status": TaskStatus.READY_FOR_REVIEW.value,
        "outcome": "REVIEW_REQUIRED",
        "missing_slots": [],
        "guide_message": None,
        "worker_request_message": None,
        "case_signals": ["GENERATE_DRAFTS", "READY_FOR_REVIEW"],
        "phase": WorkflowPhase.EXTRACTION_DOCUMENT.value,
        "step": WorkflowStep.STEP_13_DOCUMENT_DRAFT.value,
    }


# 근로자 서류 OCR 결과를 DB 어댑터에 저장 (부족해도 초안 작성으로 진행)
def persist_ocr(state: RenewalState, *, store: Any) -> dict[str, Any]:
    ocr = state.get("ocr_result") or {}
    if ocr:
        store.save_identity_slots(
            worker_id=state.get("worker_id"),
            task_id=state["task_id"],
            slots=ocr,
        )
    slots = state.get("slots") or {}
    missing = [m for m in state.get("missing_slots", []) if not slots.get(m) and not ocr.get(m)]
    return {
        "missing_slots": missing,
        "status": TaskStatus.DRAFT.value,
        "outcome": "OCR_SAVED",
        "case_signals": ["OCR_SAVED"],
        "phase": WorkflowPhase.EXTRACTION_DOCUMENT.value,
        "step": WorkflowStep.STEP_11_OCR.value,
    }


# OCR 이후는 항상 초안 작성 (부족 필드는 빈 값)
def route_after_ocr(state: RenewalState) -> Literal["generate"]:
    del state
    return "generate"
