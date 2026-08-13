# POST /internal/v1/analyses 요청·응답 스키마 (Server ai-runtime-contract)

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

AnalysisPhase = Literal["PLAN", "ANALYZE"]
AnalysisOutcome = Literal[
    "CONTEXT_REQUIRED",
    "NEEDS_INFO",
    "REVIEW_REQUIRED",
    "OUT_OF_SCOPE",
]
ConfidenceSource = Literal["MODEL", "BERT", "UNAVAILABLE"]
AgentTarget = Literal["renewal-agent"]

DEFAULT_CONTRACT_VERSION = "1.1.0"
DEFAULT_KNOWLEDGE_VERSION = "0.2.0"


# HTTP 와이어 Worker — workerRef + requestedFields (나머지 필드는 선택·하위호환)
class WorkerContext(BaseModel):

    worker_ref: str = Field(..., alias="workerRef", description="서버 worker_id")
    display_name: str | None = Field(None, alias="displayName")
    nationality_code: str | None = Field(None, alias="nationalityCode")
    preferred_language: str | None = Field(None, alias="preferredLanguage")
    work_status: str | None = Field(None, alias="workStatus")
    stay_expiry_date: str | None = Field(None, alias="stayExpiryDate")
    contract_start_date: str | None = Field(None, alias="contractStartDate")
    contract_end_date: str | None = Field(None, alias="contractEndDate")
    requested_fields: dict[str, str] = Field(default_factory=dict, alias="requestedFields")

    model_config = {"populate_by_name": True}


# HR 지시 + PLAN/ANALYZE 문맥 (HTTP 최소 페이로드)
class AnalysisInput(BaseModel):

    instruction: str
    requested_field_keys: list[str] = Field(default_factory=list, alias="requestedFieldKeys")
    workers: list[WorkerContext] = Field(default_factory=list)
    planned_intent: str | None = Field(None, alias="plannedIntent")
    planned_workflow_id: str | None = Field(None, alias="plannedWorkflowId")
    agent_target: AgentTarget | None = Field(None, alias="agentTarget")

    model_config = {"populate_by_name": True}


# Server → AI 분석 요청 (attemptId·version·deadline은 HTTP에 없음)
class AnalysisRequest(BaseModel):

    request_id: str = Field(..., alias="requestId")
    phase: AnalysisPhase
    analysis_input: AnalysisInput = Field(..., alias="analysisInput")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_planned_decision_for_phase(self) -> Self:
        ai = self.analysis_input
        has_intent = ai.planned_intent is not None
        has_workflow = ai.planned_workflow_id is not None
        if self.phase == "PLAN" and (
            has_intent or has_workflow or ai.agent_target is not None
        ):
            raise ValueError("PLAN must not include a planned Intent decision")
        if self.phase == "ANALYZE" and not (has_intent and has_workflow):
            raise ValueError(
                "ANALYZE requires plannedIntent and plannedWorkflowId from PLAN"
            )
        return self


# 기계 판독용 검증 오류
class ValidationErrorItem(BaseModel):

    code: str
    field: str

    model_config = {"populate_by_name": True}


# PLAN 후 Server DB 조회 요청
class ContextRequirement(BaseModel):

    detected_intent: str = Field(..., alias="detectedIntent")
    workflow_id: str = Field(..., alias="workflowId")
    agent_target: AgentTarget | None = Field(None, alias="agentTarget")
    evidence: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    confidence_source: ConfidenceSource = Field(..., alias="confidenceSource")
    bert_routing_score: float | None = Field(
        None, alias="bertRoutingScore", ge=0.0, le=1.0
    )
    target_display_name: str = Field(..., alias="targetDisplayName")
    extracted_slots: dict[str, str] = Field(default_factory=dict, alias="extractedSlots")
    required_field_keys: list[str] = Field(..., alias="requiredFieldKeys")

    model_config = {"populate_by_name": True}


# NEEDS_INFO 시 HR 질문 1건
class AnalysisQuestion(BaseModel):

    slot_key: str = Field(..., alias="slotKey")
    prompt: str

    model_config = {"populate_by_name": True}


# 분석 결과 후보 1건 — Server AiCandidate 와이어 필드만
class AnalysisCandidate(BaseModel):

    candidate_ref: str = Field(..., alias="candidateRef")
    worker_ref: str = Field(..., alias="workerRef", description="서버 worker_id")
    workflow_id: str = Field(..., alias="workflowId")
    extracted_slots: dict[str, str] = Field(default_factory=dict, alias="extractedSlots")
    missing_slots: list[str] = Field(default_factory=list, alias="missingSlots")
    confidence: float | None = Field(None, ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


# 재현성을 위한 버전 추적 정보
class AnalysisVersions(BaseModel):

    agent_version: str = Field(..., alias="agentVersion")
    model_provider: str = Field(..., alias="modelProvider")
    model_name: str = Field(..., alias="modelName")
    model_version: str = Field(..., alias="modelVersion")
    prompt_version: str = Field("not-applicable", alias="promptVersion")
    context_pack_version: str = Field(DEFAULT_KNOWLEDGE_VERSION, alias="contextPackVersion")
    workflow_catalog_version: str = Field(
        DEFAULT_KNOWLEDGE_VERSION, alias="workflowCatalogVersion"
    )
    contract_version: str = Field(DEFAULT_CONTRACT_VERSION, alias="contractVersion")

    model_config = {"populate_by_name": True}


# AI → Server 분석 응답 (unknown field 금지)
class AnalysisResponse(BaseModel):

    request_id: str = Field(..., alias="requestId")
    outcome: AnalysisOutcome
    context_requirement: ContextRequirement | None = Field(None, alias="contextRequirement")
    questions: list[AnalysisQuestion] = Field(default_factory=list)
    candidates: list[AnalysisCandidate] = Field(default_factory=list)
    validation_errors: list[ValidationErrorItem] = Field(
        default_factory=list, alias="validationErrors"
    )
    versions: AnalysisVersions
    provider_attempt_count: int = Field(1, alias="providerAttemptCount")
    latency_ms: int = Field(0, alias="latencyMs")

    model_config = {"populate_by_name": True, "by_alias": True}


# Intent 모델 운영 상태 — 조회 자체는 모델을 강제로 로드하지 않는다.
class IntentRuntimeStatus(BaseModel):

    intent_model_enabled: bool = Field(..., alias="intentModelEnabled")
    ax_enabled: bool = Field(..., alias="axEnabled")
    initialized: bool
    bert_available: bool = Field(..., alias="bertAvailable")
    ax_available: bool = Field(..., alias="axAvailable")
    ready: bool
    warmup_completed: bool = Field(..., alias="warmupCompleted")
    degraded: bool
    prompt_version: str = Field(..., alias="promptVersion")

    model_config = {"populate_by_name": True, "by_alias": True}
