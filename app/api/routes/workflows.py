# POST /internal/v1/workflows/renewal/run — 재갱신 흐름 진입 API

from fastapi import APIRouter, Depends

from app.agents.slot_catalog import requested_fields_for_api
from app.agents.workflow.expired_stay import (
    EXPIRED_STAY_VARIANT,
    EXPIRED_STAY_WORKFLOW_ID,
    decide_expired_stay_exception,
)
from app.agents.workflow_graph import RenewalOrchestrator
from app.api.dependencies import get_renewal_orchestrator
from app.api.openapi import WORKFLOWS_TAG
from app.api.schemas.workflows import RenewalRunRequest, RenewalRunResponse
from app.api.security import verify_internal_bearer

router = APIRouter(prefix="/internal/v1/workflows", tags=[WORKFLOWS_TAG])


@router.post(
    "/renewal/run",
    response_model=RenewalRunResponse,
    summary="재갱신 오케스트레이션 실행",
    description=(
        "Server 요청을 LangGraph 재갱신 흐름 처리. "
        "담당자 화면 입력(ask_hr)·근로자 서류 요청(ask_worker)·OCR·초안 작성 분기. "
        "requestId/attemptId·Bearer(#8), requestedFields(#74) 포함."
    ),
    dependencies=[Depends(verify_internal_bearer)],
)
# 재갱신 그래프를 실행해 Server용 응답 생성
async def run_renewal(
    request: RenewalRunRequest,
    orchestrator: RenewalOrchestrator = Depends(get_renewal_orchestrator),  # noqa: B008
) -> RenewalRunResponse:
    import asyncio

    if request.variant == EXPIRED_STAY_VARIANT:
        decision = decide_expired_stay_exception(request.stay_verification_status)
        task_id = request.task_id or f"stay-verification-{request.worker_id or request.request_id}"
        return RenewalRunResponse(
            request_id=request.request_id,
            attempt_id=request.attempt_id,
            task_id=task_id,
            intent="EXPIRY_RENEWAL",
            workflow_id=EXPIRED_STAY_WORKFLOW_ID,
            variant=EXPIRED_STAY_VARIANT,
            next_action=decision.next_action,
            legal_conclusion=None,
            questions=decision.questions,
            suggested_workflow_ids=decision.suggested_workflow_ids,
            confidence=0.0,
            status="READY_FOR_REVIEW",
            outcome="REVIEW_REQUIRED",
            scenario="ask_hr",
            phase="PHASE_EXCEPTION_REVIEW",
            step="VERIFY_STAY_STATUS",
            slots=dict(request.slots),
            case_signals=decision.case_signals,
            supervisor_reason="Server가 확인한 체류상태를 HR 검토 흐름으로 연결",
            supervisor_source="rules",
        )

    # CPU·동기 LangGraph를 워커 스레드로 넘겨 FastAPI 이벤트 루프를 막지 않음
    state = await asyncio.to_thread(
        orchestrator.run,
        request_id=request.request_id,
        instruction=request.instruction,
        worker_id=request.worker_id,
        company_id=request.company_id,
        task_id=request.task_id,
        slots=request.slots,
        documents=[d.model_dump(by_alias=False) for d in request.documents],
        ocr_result=request.ocr_result,
        worker=request.worker.model_dump(by_alias=False) if request.worker else None,
        company=request.company.model_dump(by_alias=False) if request.company else None,
        task=request.task.model_dump(by_alias=False) if request.task else None,
        agent_mode=request.agent_mode,
    )
    missing = state.get("missing_slots") or []
    return RenewalRunResponse(
        request_id=state["request_id"],
        attempt_id=request.attempt_id,
        task_id=state["task_id"],
        intent=state.get("intent") or "",
        workflow_id=state.get("workflow_id") or "",
        confidence=float(state.get("confidence") or 0.0),
        status=state.get("status") or "",
        outcome=state.get("outcome") or "",
        scenario=state.get("scenario"),
        phase=state.get("phase"),
        step=state.get("step"),
        slots=state.get("slots") or {},
        missing_slots=missing,
        requested_fields=requested_fields_for_api(list(missing)),
        guide_message=state.get("guide_message"),
        worker_request_message=state.get("worker_request_message"),
        language_assistant=state.get("language_assistant"),
        ocr_result=state.get("ocr_result"),
        generated_documents=state.get("generated_documents") or [],
        evidence=list(state.get("evidence") or []),
        document_validation=state.get("document_validation"),
        case_signals=list(state.get("case_signals") or []),
        progress_events=list(state.get("progress_events") or []),
        supervisor_reason=state.get("supervisor_reason"),
        supervisor_source=state.get("supervisor_source"),
        active_subgraph=state.get("active_subgraph"),
        errors=state.get("errors") or [],
    )
