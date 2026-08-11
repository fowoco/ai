# Analyses 파이프라인 — PLAN(CONTEXT_REQUIRED) → ANALYZE(NEEDS_INFO|REVIEW_REQUIRED)

from __future__ import annotations

import re
import time
from uuid import uuid4

from app import __version__
from app.api.schemas.analyses import (
    DEFAULT_CONTRACT_VERSION,
    DEFAULT_KNOWLEDGE_VERSION,
    AnalysisCandidate,
    AnalysisQuestion,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisVersions,
    ContextRequirement,
    IntentDecisionItem,
    WorkerContext,
)

from .ambiguity import AmbiguityAgent
from .intent import IntentClassifier, IntentDecision, IntentResult, build_intent_agent
from .workflow import WorkflowAgent
from .workflow_graph.state import HR_EXCLUDED_SLOTS

# instruction 끝의 `, INTENT_TAG` 제거
_INTENT_TAG_SUFFIX = re.compile(r",\s*[A-Z][A-Z0-9_]+\s*$")
# 대상 이름 추정 시 끊을 토큰
_NAME_STOP_PREFIXES = (
    "체류",
    "계약",
    "서류",
    "급여",
    "연장",
    "준비",
    "요청",
    "등록",
    "변경",
    "안내",
)

_SLOT_PROMPTS: dict[str, str] = {
    "worker_id": "대상 근로자를 지정해 주세요.",
    "stay_expiry_date": "체류 만료일을 입력해 주세요.",
    "contract_end_date": "계약 종료일을 입력해 주세요.",
    "contract_start_date": "계약 시작일을 입력해 주세요.",
    "legal_name": "여권상 성명을 입력해 주세요.",
    "full_name": "성명을 입력해 주세요.",
    "monthly_wage": "월 급여를 입력해 주세요.",
    "wage": "급여를 입력해 주세요.",
    "document_type": "서류 종류를 입력해 주세요.",
    "pay_period": "급여 기간을 입력해 주세요.",
    "change_type": "고용 변동 유형을 입력해 주세요.",
}


# 발화문에서 대상 표시 이름 추정
def _guess_target_display_name(instruction: str) -> str:
    text = _INTENT_TAG_SUFFIX.sub("", instruction).strip()
    if not text:
        return "unknown"
    parts: list[str] = []
    for tok in text.split():
        if tok in {"의", "을", "를", "이", "가"}:
            break
        if any(tok.startswith(p) for p in _NAME_STOP_PREFIXES):
            break
        parts.append(tok)
    name = " ".join(parts).strip()
    return name or "unknown"


# HR 질문 prompt 생성
def _question_for(slot_key: str) -> AnalysisQuestion:
    prompt = _SLOT_PROMPTS.get(slot_key) or f"{slot_key} 값을 입력해 주세요."
    return AnalysisQuestion(slot_key=slot_key, prompt=prompt)


# Worker requestedFields·식별자를 슬롯으로 시드
def _seed_slots_from_worker(worker: WorkerContext) -> dict[str, str]:
    slots: dict[str, str] = {}
    if worker.worker_ref:
        slots["worker_id"] = worker.worker_ref
    if worker.display_name:
        slots["display_name"] = worker.display_name
        slots.setdefault("full_name", worker.display_name)
    if worker.nationality_code:
        slots["nationality_code"] = worker.nationality_code
        slots.setdefault("nationality", worker.nationality_code)
    if worker.stay_expiry_date:
        slots["stay_expiry_date"] = worker.stay_expiry_date
    if worker.contract_start_date:
        slots["contract_start_date"] = worker.contract_start_date
    if worker.contract_end_date:
        slots["contract_end_date"] = worker.contract_end_date
    for key, value in worker.requested_fields.items():
        if value:
            slots.setdefault(key, value)
            if key == "legal_name":
                slots.setdefault("full_name", value)
    return slots


# 고정 버전 블록
def _versions(intent_result: IntentResult) -> AnalysisVersions:
    return AnalysisVersions(
        agent_version=__version__,
        model_provider=intent_result.model_provider,
        model_name=intent_result.model_name,
        model_version=intent_result.model_version,
        prompt_version=intent_result.prompt_version,
        contract_version=DEFAULT_CONTRACT_VERSION,
        workflow_catalog_version=DEFAULT_KNOWLEDGE_VERSION,
        context_pack_version=DEFAULT_KNOWLEDGE_VERSION,
    )


# 구형 단일 IntentResult도 새 결정 목록 계약으로 정규화
def _intent_decisions(intent_result: IntentResult) -> list[IntentDecision]:
    if intent_result.decisions:
        return list(intent_result.decisions)
    return [
        IntentDecision(
            intent=intent_result.intent or "UNKNOWN",
            workflow_id=intent_result.workflow_id or "",
            confidence=intent_result.confidence,
            confidence_source=intent_result.confidence_source,
            bert_routing_score=intent_result.bert_routing_score,
        )
    ]


# 내부 결정을 Server가 ANALYZE에서 재사용할 수 있는 와이어 모델로 변환
def _wire_intent_decisions(intent_result: IntentResult) -> list[IntentDecisionItem]:
    return [
        IntentDecisionItem(
            detected_intent=decision.intent,
            workflow_id=decision.workflow_id,
            evidence=decision.evidence,
            confidence=decision.confidence,
            confidence_source=decision.confidence_source,
            bert_routing_score=decision.bert_routing_score,
            model_provider=intent_result.model_provider,
            model_name=intent_result.model_name,
            model_version=intent_result.model_version,
            prompt_version=intent_result.prompt_version,
        )
        for decision in _intent_decisions(intent_result)
    ]


# PLAN에서 확정한 결정을 재구성해 ANALYZE 모델 재호출을 피한다.
def _planned_intent_result(request: AnalysisRequest) -> IntentResult | None:
    ai = request.analysis_input
    if ai.planned_intent_decisions:
        items = ai.planned_intent_decisions
        decisions = [
            IntentDecision(
                intent=item.detected_intent,
                workflow_id=item.workflow_id,
                confidence=item.confidence,
                confidence_source=item.confidence_source,
                bert_routing_score=item.bert_routing_score,
                evidence=item.evidence,
            )
            for item in items
        ]
        primary = decisions[0]
        first = items[0]
        slots = {
            f"evidence:{item.detected_intent}": item.evidence
            for item in items
            if item.evidence
        }
        return IntentResult(
            intent=primary.intent,
            workflow_id=primary.workflow_id,
            confidence=primary.confidence,
            confidence_source=primary.confidence_source,
            bert_routing_score=primary.bert_routing_score,
            decisions=decisions,
            extracted_slots=slots,
            model_provider=first.model_provider,
            model_name=first.model_name,
            model_version=first.model_version,
            prompt_version=first.prompt_version,
        )
    if ai.planned_intent is not None and ai.planned_workflow_id is not None:
        decision = IntentDecision(
            intent=ai.planned_intent,
            workflow_id=ai.planned_workflow_id,
            confidence=None,
            confidence_source="UNAVAILABLE",
        )
        return IntentResult(
            intent=decision.intent,
            workflow_id=decision.workflow_id,
            confidence=None,
            confidence_source="UNAVAILABLE",
            decisions=[decision],
            model_provider="server",
            model_name="planned-intent",
            model_version="reused",
        )
    return None


# Intent → requiredFieldKeys / questions·candidates
class AnalysisPipeline:

    # 하위 에이전트 미주입 시 기본 Intent·Ambiguity·Workflow
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

    # phase에 따라 CONTEXT_REQUIRED 또는 최종 outcome 반환
    def run(self, request: AnalysisRequest) -> AnalysisResponse:
        start = time.monotonic()
        if request.phase == "PLAN":
            response = self._run_plan(request)
        else:
            response = self._run_analyze(request)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        response.latency_ms = elapsed_ms
        return response

    # PLAN — Intent 확정 후 DB canonical key 요청
    def _run_plan(self, request: AnalysisRequest) -> AnalysisResponse:
        instruction = request.analysis_input.instruction
        intent_result = self._intent.classify(instruction)
        decisions = _intent_decisions(intent_result)
        primary = decisions[0]

        # 복합 Intent이면 각 Workflow의 canonical key를 원문 순서대로 합친다.
        field_keys: list[str] = []
        for decision in decisions:
            if decision.intent == "OUT_OF_SCOPE":
                required = ["worker_id"]
            else:
                required = self._required_slots_for(decision.workflow_id)
                if not required:
                    required = ["worker_id", "stay_expiry_date"]
            for key in required:
                if key not in field_keys:
                    field_keys.append(key)

        return AnalysisResponse(
            request_id=request.request_id,
            outcome="CONTEXT_REQUIRED",
            context_requirement=ContextRequirement(
                detected_intent=primary.intent,
                workflow_id=primary.workflow_id,
                confidence=primary.confidence,
                confidence_source=primary.confidence_source,
                bert_routing_score=primary.bert_routing_score,
                intent_decisions=_wire_intent_decisions(intent_result),
                target_display_name=_guess_target_display_name(instruction),
                extracted_slots=dict(intent_result.extracted_slots),
                required_field_keys=field_keys,
            ),
            questions=[],
            candidates=[],
            validation_errors=[],
            versions=_versions(intent_result),
            provider_attempt_count=1,
            latency_ms=0,
        )

    # ANALYZE — DB 보충값으로 NEEDS_INFO | REVIEW_REQUIRED
    def _run_analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        ai = request.analysis_input
        instruction = ai.instruction
        intent_result = _planned_intent_result(request)
        provider_attempt_count = 0
        if intent_result is None:
            # 1.0 호출자 하위호환: 계획 결정을 보내지 않으면 기존처럼 분류한다.
            intent_result = self._intent.classify(instruction)
            provider_attempt_count = 1
        decisions = _intent_decisions(intent_result)

        if not ai.workers:
            return AnalysisResponse(
                request_id=request.request_id,
                outcome="NEEDS_INFO",
                context_requirement=None,
                questions=[_question_for("worker_id")],
                candidates=[],
                validation_errors=[],
                versions=_versions(intent_result),
                provider_attempt_count=provider_attempt_count,
                latency_ms=0,
            )

        # MVP: 근로자 1명만
        worker = ai.workers[0]
        slots = _seed_slots_from_worker(worker)
        slots.update(intent_result.extracted_slots)

        # Server가 못 채운 PLAN 요청 키 → HR 질문 후보
        hr_keys: list[str] = []
        for key in ai.requested_field_keys:
            if (
                key not in HR_EXCLUDED_SLOTS
                and key not in worker.requested_fields
                and key not in slots
            ):
                hr_keys.append(key)

        for decision in decisions:
            if not decision.workflow_id:
                continue
            amb = self._ambiguity.check(decision.workflow_id, slots, instruction)
            for key in amb.missing_slots:
                if key not in HR_EXCLUDED_SLOTS and key not in slots and key not in hr_keys:
                    hr_keys.append(key)

        if hr_keys:
            return AnalysisResponse(
                request_id=request.request_id,
                outcome="NEEDS_INFO",
                context_requirement=None,
                questions=[_question_for(k) for k in hr_keys],
                candidates=[],
                validation_errors=[],
                versions=_versions(intent_result),
                provider_attempt_count=provider_attempt_count,
                latency_ms=0,
            )

        # 복합 Intent 각각에 canonical Knowledge Workflow 후보를 만든다.
        candidates = [
            AnalysisCandidate(
                candidate_ref=f"candidate-{uuid4().hex[:8]}",
                worker_ref=worker.worker_ref,
                detected_intent=decision.intent,
                workflow_id=decision.workflow_id,
                extracted_slots=slots,
                missing_slots=[],
                confidence=decision.confidence,
                confidence_source=decision.confidence_source,
                bert_routing_score=decision.bert_routing_score,
            )
            for decision in decisions
        ]
        return AnalysisResponse(
            request_id=request.request_id,
            outcome="REVIEW_REQUIRED",
            context_requirement=None,
            questions=[],
            candidates=candidates,
            validation_errors=[],
            versions=_versions(intent_result),
            provider_attempt_count=provider_attempt_count,
            latency_ms=0,
        )

    # workflow 필수 슬롯 (Catalog → Ambiguity/Knowledge 폴백)
    def _required_slots_for(self, workflow_id: str) -> list[str]:
        if not workflow_id:
            return []
        info = self._workflow.get_workflow(workflow_id)
        if info and info.required_slots:
            return list(info.required_slots)
        return self._ambiguity.check(workflow_id, {}, "").missing_slots
