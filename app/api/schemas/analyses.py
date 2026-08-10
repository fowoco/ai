# POST /internal/v1/analyses 요청·응답 스키마 (Server ai-runtime-contract)

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AnalysisPhase = Literal["PLAN", "ANALYZE"]
AnalysisOutcome = Literal["CONTEXT_REQUIRED", "NEEDS_INFO", "REVIEW_REQUIRED"]

DEFAULT_CONTRACT_VERSION = "1.0.0"
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

    model_config = {"populate_by_name": True}


# Server → AI 분석 요청 (attemptId·version·deadline은 HTTP에 없음)
class AnalysisRequest(BaseModel):

    request_id: str = Field(..., alias="requestId")
    phase: AnalysisPhase
    analysis_input: AnalysisInput = Field(..., alias="analysisInput")

    model_config = {"populate_by_name": True}


# 기계 판독용 검증 오류
class ValidationErrorItem(BaseModel):

    code: str
    field: str

    model_config = {"populate_by_name": True}


# PLAN 후 Server DB 조회 요청
class ContextRequirement(BaseModel):

    detected_intent: str = Field(..., alias="detectedIntent")
    confidence: float = Field(..., ge=0.0, le=1.0)
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
    confidence: float = Field(..., ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


# 재현성을 위한 버전 추적 정보
class AnalysisVersions(BaseModel):

    agent_version: str = Field(..., alias="agentVersion")
    model_provider: str = Field(..., alias="modelProvider")
    model_name: str = Field(..., alias="modelName")
    model_version: str = Field(..., alias="modelVersion")
    prompt_version: str = Field("prompt-1", alias="promptVersion")
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
