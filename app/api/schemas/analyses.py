# POST /internal/v1/analyses 요청·응답 스키마 (Server #56 계약)

from __future__ import annotations

from pydantic import BaseModel, Field


# 서버가 허용한 워크플로·슬롯 범위
class WorkflowConstraint(BaseModel):

    workflow_id: str = Field(..., alias="workflowId")
    allowed_slot_keys: list[str] = Field(default_factory=list, alias="allowedSlotKeys")

    model_config = {"populate_by_name": True}


# 요청에 실린 근로자 컨텍스트 (Server WorkerContext)
class WorkerContext(BaseModel):

    worker_ref: str = Field(..., alias="workerRef", description="서버 worker_id와 동일")
    display_name: str = Field(..., alias="displayName")
    nationality_code: str | None = Field(None, alias="nationalityCode")
    preferred_language: str = Field("ko", alias="preferredLanguage")
    work_status: str = Field("ACTIVE", alias="workStatus")
    stay_expiry_date: str | None = Field(None, alias="stayExpiryDate")
    contract_start_date: str | None = Field(None, alias="contractStartDate")
    contract_end_date: str | None = Field(None, alias="contractEndDate")
    # Agent가 요구한 field의 Server 원본값 (서비스 인증정보 금지)
    requested_fields: dict[str, str] = Field(default_factory=dict, alias="requestedFields")

    model_config = {"populate_by_name": True}


# HR 지시문과 근로자·제약 목록
class AnalysisInput(BaseModel):

    instruction: str
    workers: list[WorkerContext] = Field(default_factory=list)
    workflow_constraints: list[WorkflowConstraint] = Field(
        default_factory=list, alias="workflowConstraints"
    )

    model_config = {"populate_by_name": True}


# Server → AI 분석 요청
class AnalysisRequest(BaseModel):

    request_id: str = Field(..., alias="requestId")
    attempt_id: str = Field(..., alias="attemptId")
    contract_version: str = Field("1.0.0", alias="contractVersion")
    required_knowledge_version: str = Field("0.2.0", alias="requiredKnowledgeVersion")
    deadline_ms: int = Field(10_000, alias="deadlineMs")
    analysis_input: AnalysisInput = Field(..., alias="analysisInput")

    model_config = {"populate_by_name": True}


# 기계 판독용 검증 오류 (자유문 Provider 메시지 금지)
class ValidationErrorItem(BaseModel):

    code: str
    field: str

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
    model_provider: str = Field("stub", alias="modelProvider")
    model_name: str = Field("stub", alias="modelName")
    model_version: str = Field("stub", alias="modelVersion")
    prompt_version: str = Field("prompt-1", alias="promptVersion")
    context_pack_version: str = Field("0.2.0", alias="contextPackVersion")
    workflow_catalog_version: str = Field("0.2.0", alias="workflowCatalogVersion")
    contract_version: str = Field("1.0.0", alias="contractVersion")

    model_config = {"populate_by_name": True}


# AI → Server 분석 응답 (unknown field 금지 — Server FAIL_ON_UNKNOWN_PROPERTIES)
class AnalysisResponse(BaseModel):

    request_id: str = Field(..., alias="requestId")
    outcome: str = Field(..., description="NEEDS_INFO | REVIEW_REQUIRED")
    candidates: list[AnalysisCandidate] = Field(default_factory=list)
    validation_errors: list[ValidationErrorItem] = Field(
        default_factory=list, alias="validationErrors"
    )
    versions: AnalysisVersions
    provider_attempt_count: int = Field(1, alias="providerAttemptCount")
    latency_ms: int = Field(0, alias="latencyMs")

    model_config = {"populate_by_name": True, "by_alias": True}
