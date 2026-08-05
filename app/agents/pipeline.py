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
    WorkerContext,
)

from .ambiguity import AmbiguityAgent
from .intent import IntentClassifier, build_intent_agent
from .workflow import WorkflowAgent

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
def _versions() -> AnalysisVersions:
    return AnalysisVersions(
        agent_version=__version__,
        contract_version=DEFAULT_CONTRACT_VERSION,
        workflow_catalog_version=DEFAULT_KNOWLEDGE_VERSION,
        context_pack_version=DEFAULT_KNOWLEDGE_VERSION,
    )


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
        workflow_id = intent_result.workflow_id or ""
        # Issue #6: Knowledge canonical key 전체 (worker_id 포함)
        if intent_result.intent == "OUT_OF_SCOPE":
            field_keys = ["worker_id"]
        else:
            required = self._required_slots_for(workflow_id)
            field_keys = list(required) if required else ["worker_id", "stay_expiry_date"]

        return AnalysisResponse(
            request_id=request.request_id,
            outcome="CONTEXT_REQUIRED",
            context_requirement=ContextRequirement(
                detected_intent=intent_result.intent or "UNKNOWN",
                confidence=intent_result.confidence,
                target_display_name=_guess_target_display_name(instruction),
                extracted_slots=dict(intent_result.extracted_slots),
                required_field_keys=field_keys,
            ),
            questions=[],
            candidates=[],
            validation_errors=[],
            versions=_versions(),
            provider_attempt_count=1,
            latency_ms=0,
        )

    # ANALYZE — DB 보충값으로 NEEDS_INFO | REVIEW_REQUIRED
    def _run_analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        ai = request.analysis_input
        instruction = ai.instruction
        intent_result = self._intent.classify(instruction)
        workflow_id = intent_result.workflow_id or ""
        public_wf = intent_result.intent or workflow_id or "UNKNOWN"

        if not ai.workers:
            return AnalysisResponse(
                request_id=request.request_id,
                outcome="NEEDS_INFO",
                context_requirement=None,
                questions=[_question_for("worker_id")],
                candidates=[],
                validation_errors=[],
                versions=_versions(),
                provider_attempt_count=1,
                latency_ms=0,
            )

        # MVP: 근로자 1명만
        worker = ai.workers[0]
        slots = _seed_slots_from_worker(worker)

        # Server가 못 채운 PLAN 요청 키 → HR 질문 후보
        hr_keys: list[str] = []
        for key in ai.requested_field_keys:
            if key not in worker.requested_fields and key not in slots:
                hr_keys.append(key)

        amb = self._ambiguity.check(workflow_id, slots, instruction)
        for key in amb.missing_slots:
            if key not in slots and key not in hr_keys:
                hr_keys.append(key)

        if hr_keys:
            return AnalysisResponse(
                request_id=request.request_id,
                outcome="NEEDS_INFO",
                context_requirement=None,
                questions=[_question_for(k) for k in hr_keys],
                candidates=[],
                validation_errors=[],
                versions=_versions(),
                provider_attempt_count=1,
                latency_ms=0,
            )

        # 응답 workflowId는 Intent형(서버 fixture) 우선
        if intent_result.intent:
            public_wf = intent_result.intent
        elif self._workflow.get_workflow(workflow_id):
            public_wf = workflow_id

        candidate = AnalysisCandidate(
            candidate_ref=f"candidate-{uuid4().hex[:8]}",
            worker_ref=worker.worker_ref,
            workflow_id=public_wf,
            extracted_slots=slots,
            missing_slots=[],
            confidence=intent_result.confidence,
        )
        return AnalysisResponse(
            request_id=request.request_id,
            outcome="REVIEW_REQUIRED",
            context_requirement=None,
            questions=[],
            candidates=[candidate],
            validation_errors=[],
            versions=_versions(),
            provider_attempt_count=1,
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
