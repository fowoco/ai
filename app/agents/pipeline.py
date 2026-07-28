"""분석 파이프라인 — POST /internal/v1/analyses 의 핵심 로직.

Intent/Slot → Ambiguity → Workflow 검증 순서로 에이전트를 실행하고
AnalysisResponse를 조립한다. (규칙 기반 MVP, LLM 없음)
"""

from __future__ import annotations

import time
from uuid import uuid4

from app import __version__
from app.api.schemas.analyses import (
    AnalysisCandidate,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisVersions,
)

from .ambiguity import AmbiguityAgent
from .intent import IntentSlotAgent
from .workflow import WorkflowAgent


class AnalysisPipeline:
    """에이전트 파이프라인 오케스트레이터."""

    def __init__(
        self,
        *,
        intent_agent: IntentSlotAgent | None = None,
        ambiguity_agent: AmbiguityAgent | None = None,
        workflow_agent: WorkflowAgent | None = None,
    ) -> None:
        self._intent = intent_agent or IntentSlotAgent()
        self._ambiguity = ambiguity_agent or AmbiguityAgent()
        self._workflow = workflow_agent or WorkflowAgent()

    def run(self, request: AnalysisRequest) -> AnalysisResponse:
        start = time.monotonic()
        mi = request.masked_input
        instruction = mi.masked_instruction
        constraint_ids = [c.workflow_id for c in mi.workflow_constraints]
        allowed_keys_by_wf = {c.workflow_id: c.allowed_slot_keys for c in mi.workflow_constraints}

        candidates: list[AnalysisCandidate] = []

        for worker in mi.workers:
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

            if worker.worker_ref and "worker_id" not in intent_result.extracted_slots:
                intent_result.extracted_slots["worker_id"] = worker.worker_ref
            if worker.stay_expiry_date and "stay_expiry_date" not in intent_result.extracted_slots:
                intent_result.extracted_slots["stay_expiry_date"] = worker.stay_expiry_date

            allowed_keys = allowed_keys_by_wf.get(intent_result.workflow_id)
            filtered_slots = intent_result.extracted_slots
            if allowed_keys:
                filtered_slots = {
                    k: v for k, v in intent_result.extracted_slots.items() if k in allowed_keys
                }

            amb_result = self._ambiguity.check(
                intent_result.workflow_id, filtered_slots, instruction
            )

            candidates.append(
                AnalysisCandidate(
                    candidate_ref=f"candidate-{uuid4().hex[:8]}",
                    worker_ref=worker.worker_ref,
                    workflow_id=intent_result.workflow_id,
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
