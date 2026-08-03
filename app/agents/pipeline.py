# Analyses MVP 파이프라인 — Intent → Ambiguity → Workflow

from __future__ import annotations

import time
from uuid import uuid4

from app import __version__
from app.api.schemas.analyses import (
    AnalysisCandidate,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisVersions,
    WorkerContext,
)

from .ambiguity import AmbiguityAgent
from .intent import IntentClassifier, build_intent_agent
from .intent.service import public_workflow_id
from .workflow import WorkflowAgent

# requestedFields 맵에서 extractedSlots로 승격할 키
_REQUESTED_FIELD_SLOT_KEYS = frozenset(
    {
        "legal_name",
        "full_name",
        "passport_number",
        "phone",
        "email",
        "company_id",
        "alien_registration_number",
        "date_of_birth",
        "nationality",
        "wage",
        "monthly_wage",
    }
)


# WorkerContext·requestedFields를 초기 슬롯으로 시드
def _seed_slots_from_worker(worker: WorkerContext) -> dict[str, str]:
    slots: dict[str, str] = {}
    if worker.worker_ref:
        slots["worker_id"] = worker.worker_ref
    if worker.display_name:
        slots["display_name"] = worker.display_name
    if worker.nationality_code:
        slots["nationality_code"] = worker.nationality_code
    if worker.stay_expiry_date:
        slots["stay_expiry_date"] = worker.stay_expiry_date
    if worker.contract_start_date:
        slots["contract_start_date"] = worker.contract_start_date
    if worker.contract_end_date:
        slots["contract_end_date"] = worker.contract_end_date
    for key, value in worker.requested_fields.items():
        if key in _REQUESTED_FIELD_SLOT_KEYS and value:
            slots.setdefault(key, value)
            if key == "legal_name":
                slots.setdefault("full_name", value)
    company_id = worker.requested_fields.get("company_id")
    if company_id:
        slots.setdefault("company_id", company_id)
    return slots


# 의도 분류·슬롯 검사·워크플로 조회를 이어 붙인 분석기
class AnalysisPipeline:

    # 하위 에이전트 수신 안 주면 설정 기반 Intent + 기본 Ambiguity/Workflow 사용
    def __init__(
        self,
        *,
        intent_agent: IntentClassifier | None = None,
        ambiguity_agent: AmbiguityAgent | None = None,
        workflow_agent: WorkflowAgent | None = None,
    ) -> None:
        self._intent = intent_agent or build_intent_agent()
        self._ambiguity = ambiguity_agent or AmbiguityAgent()
        self._workflow = workflow_agent or WorkflowAgent()

    # 요청 실행 → outcome·candidates 목록 생성
    def run(self, request: AnalysisRequest) -> AnalysisResponse:
        start = time.monotonic()
        ai = request.analysis_input
        instruction = ai.instruction
        constraint_ids = [c.workflow_id for c in ai.workflow_constraints]
        allowed_keys_by_constraint = {
            c.workflow_id: c.allowed_slot_keys for c in ai.workflow_constraints
        }

        candidates: list[AnalysisCandidate] = []

        for worker in ai.workers:
            intent_result = self._intent.classify(
                instruction, workflow_constraints=constraint_ids or None
            )

            if not intent_result.workflow_id:
                candidates.append(
                    AnalysisCandidate(
                        candidate_ref=f"candidate-{uuid4().hex[:8]}",
                        worker_ref=worker.worker_ref,
                        workflow_id="UNKNOWN",
                        extracted_slots={},
                        missing_slots=[],
                        confidence=intent_result.confidence,
                    )
                )
                continue

            workflow = self._workflow.get_workflow(intent_result.workflow_id)
            if workflow is None:
                candidates.append(
                    AnalysisCandidate(
                        candidate_ref=f"candidate-{uuid4().hex[:8]}",
                        worker_ref=worker.worker_ref,
                        workflow_id="UNKNOWN",
                        extracted_slots={},
                        missing_slots=[],
                        confidence=intent_result.confidence,
                    )
                )
                continue

            response_workflow_id = public_workflow_id(
                internal_workflow_id=intent_result.workflow_id,
                intent=intent_result.intent,
                constraints=constraint_ids,
            )

            seeded = _seed_slots_from_worker(worker)
            for key, value in seeded.items():
                intent_result.extracted_slots.setdefault(key, value)

            allowed_keys = allowed_keys_by_constraint.get(
                response_workflow_id
            ) or allowed_keys_by_constraint.get(intent_result.workflow_id)
            filtered_slots = intent_result.extracted_slots
            if allowed_keys:
                # Step 3 조회 키는 allowed 목록과 무관하게 항상 유지
                keep = {"worker_id", "company_id"}
                filtered_slots = {
                    k: v
                    for k, v in intent_result.extracted_slots.items()
                    if k in allowed_keys or k in keep
                }

            amb_result = self._ambiguity.check(
                intent_result.workflow_id, filtered_slots, instruction
            )

            candidates.append(
                AnalysisCandidate(
                    candidate_ref=f"candidate-{uuid4().hex[:8]}",
                    worker_ref=worker.worker_ref,
                    workflow_id=response_workflow_id,
                    extracted_slots=filtered_slots,
                    missing_slots=amb_result.missing_slots,
                    confidence=intent_result.confidence,
                )
            )

        has_missing = any(c.missing_slots for c in candidates)
        has_low_confidence = any(c.confidence < 0.65 for c in candidates)
        outcome = "NEEDS_INFO" if (has_missing or has_low_confidence) else "REVIEW_REQUIRED"

        elapsed_ms = int((time.monotonic() - start) * 1000)

        return AnalysisResponse(
            request_id=request.request_id,
            outcome=outcome,
            candidates=candidates,
            validation_errors=[],
            versions=AnalysisVersions(
                agent_version=__version__,
                contract_version=request.contract_version,
            ),
            provider_attempt_count=1,
            latency_ms=elapsed_ms,
        )
