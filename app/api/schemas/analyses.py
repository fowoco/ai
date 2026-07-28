"""POST /internal/v1/analyses 요청·응답 스키마.

Server(Spring)가 보내는 JSON 계약을 Pydantic 모델로 정의한다.
fowoco-server docs/ai-runtime-contract.md 와 1:1 대응.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkerInfo(BaseModel):
    worker_ref: str = Field(..., alias="workerRef")
    preferred_language: str = Field("ko", alias="preferredLanguage")
    work_status: str = Field("ACTIVE", alias="workStatus")
    stay_expiry_date: str | None = Field(None, alias="stayExpiryDate")

    model_config = {"populate_by_name": True}


class WorkflowConstraint(BaseModel):
    workflow_id: str = Field(..., alias="workflowId")
    allowed_slot_keys: list[str] = Field(default_factory=list, alias="allowedSlotKeys")

    model_config = {"populate_by_name": True}


class MaskedInput(BaseModel):
    masked_instruction: str = Field(..., alias="maskedInstruction")
    workers: list[WorkerInfo] = Field(default_factory=list)
    workflow_constraints: list[WorkflowConstraint] = Field(
        default_factory=list, alias="workflowConstraints"
    )

    model_config = {"populate_by_name": True}


class AnalysisRequest(BaseModel):
    """Server → AI 분석 요청."""

    request_id: str = Field(..., alias="requestId")
    attempt_id: str = Field(..., alias="attemptId")
    contract_version: str = Field("1.0.0", alias="contractVersion")
    required_knowledge_version: str = Field("0.2.0", alias="requiredKnowledgeVersion")
    deadline_ms: int = Field(10_000, alias="deadlineMs")
    masked_input: MaskedInput = Field(..., alias="maskedInput")

    model_config = {"populate_by_name": True}


class AnalysisCandidate(BaseModel):
    """분석 결과 후보 1건."""

    candidate_ref: str = Field(..., alias="candidateRef")
    worker_ref: str = Field(..., alias="workerRef")
    workflow_id: str = Field(..., alias="workflowId")
    extracted_slots: dict[str, str] = Field(default_factory=dict, alias="extractedSlots")
    missing_slots: list[str] = Field(default_factory=list, alias="missingSlots")
    confidence: float = Field(..., ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


class AnalysisVersions(BaseModel):
    """재현성을 위한 버전 추적 정보."""

    agent_version: str = Field(..., alias="agentVersion")
    model_provider: str = Field("stub", alias="modelProvider")
    model_name: str = Field("stub", alias="modelName")
    model_version: str = Field("stub", alias="modelVersion")
    prompt_version: str = Field("prompt-1", alias="promptVersion")
    context_pack_version: str = Field("0.2.0", alias="contextPackVersion")
    workflow_catalog_version: str = Field("0.2.0", alias="workflowCatalogVersion")
    contract_version: str = Field("1.0.0", alias="contractVersion")

    model_config = {"populate_by_name": True}


class AnalysisResponse(BaseModel):
    """AI → Server 분석 응답."""

    request_id: str = Field(..., alias="requestId")
    outcome: str = Field(..., description="NEEDS_INFO | REVIEW_REQUIRED")
    candidates: list[AnalysisCandidate] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list, alias="validationErrors")
    versions: AnalysisVersions
    provider_attempt_count: int = Field(1, alias="providerAttemptCount")
    latency_ms: int = Field(0, alias="latencyMs")

    model_config = {"populate_by_name": True, "by_alias": True}
