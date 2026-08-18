# POST /internal/v1/workflows/renewal 요청·응답 스키마

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# 담당자가 업로드한 신분서류 메타 (OCR 입력)
class RenewalDocumentInput(BaseModel):

    document_type: str = Field(..., alias="documentType")
    filename: str | None = None
    # CLOVA/DB에서 채운 구조화 필드 (주현 worker_document 컬럼명과 동일)
    fields: dict[str, Any] = Field(default_factory=dict)
    hints: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


# Server worker 일괄 스냅샷 (ERD worker 컬럼)
class WorkerSnapshot(BaseModel):

    worker_id: str = Field(..., alias="workerId")
    company_id: str | None = Field(None, alias="companyId")
    display_name: str | None = Field(None, alias="displayName")
    nationality_code: str | None = Field(None, alias="nationalityCode")
    preferred_language: str | None = Field(None, alias="preferredLanguage")
    work_status: str | None = Field(None, alias="workStatus")
    stay_expiry_date: str | None = Field(None, alias="stayExpiryDate")
    contract_start_date: str | None = Field(None, alias="contractStartDate")
    contract_end_date: str | None = Field(None, alias="contractEndDate")
    created_at: str | None = Field(None, alias="createdAt")
    updated_at: str | None = Field(None, alias="updatedAt")
    version: int | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


# Server company 일괄 스냅샷 (ERD company 컬럼)
class CompanySnapshot(BaseModel):

    company_id: str = Field(..., alias="companyId")
    name: str | None = None
    status: str | None = None
    created_at: str | None = Field(None, alias="createdAt")
    updated_at: str | None = Field(None, alias="updatedAt")
    version: int | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


# Server task 일괄 스냅샷 (ERD task 컬럼)
class TaskSnapshot(BaseModel):

    task_id: str = Field(..., alias="taskId")
    company_id: str | None = Field(None, alias="companyId")
    worker_id: str | None = Field(None, alias="workerId")
    case_id: str | None = Field(None, alias="caseId")
    task_type: str | None = Field(None, alias="taskType")
    workflow_id: str | None = Field(None, alias="workflowId")
    workflow_catalog_version: str | None = Field(None, alias="workflowCatalogVersion")
    title: str | None = None
    description: str | None = None
    business_data_json: Any = Field(None, alias="businessDataJson")
    critical_fingerprint: str | None = Field(None, alias="criticalFingerprint")
    content_revision: int | None = Field(None, alias="contentRevision")
    source: str | None = None
    status: str | None = None
    due_date: str | None = Field(None, alias="dueDate")
    created_by: str | None = Field(None, alias="createdBy")
    updated_by: str | None = Field(None, alias="updatedBy")
    created_at: str | None = Field(None, alias="createdAt")
    updated_at: str | None = Field(None, alias="updatedAt")
    version: int | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


# Server → AI 재갱신 오케스트레이션 요청
class RenewalRunRequest(BaseModel):

    request_id: str = Field(..., alias="requestId")
    attempt_id: str | None = Field(None, alias="attemptId")
    instruction: str
    worker_id: str | None = Field(None, alias="workerId")
    company_id: str | None = Field(None, alias="companyId")
    task_id: str | None = Field(None, alias="taskId")
    variant: Literal["EXPIRED_STAY_EXCEPTION"] | None = None
    stay_verification_status: str | None = Field(None, alias="stayVerificationStatus")
    slots: dict[str, Any] = Field(default_factory=dict)
    documents: list[RenewalDocumentInput] = Field(default_factory=list)
    # Server가 CLOVA OCR API 후 DB에서 읽어 실어 보낼 선행 OCR 스냅샷
    ocr_result: dict[str, Any] | None = Field(None, alias="ocrResult")
    worker: WorkerSnapshot | None = None
    company: CompanySnapshot | None = None
    task: TaskSnapshot | None = None

    model_config = {"populate_by_name": True}


# AI → Server 재갱신 오케스트레이션 결과 (판단 신호)
class RenewalRunResponse(BaseModel):

    request_id: str = Field(..., alias="requestId")
    attempt_id: str | None = Field(None, alias="attemptId")
    task_id: str = Field(..., alias="taskId")
    intent: str
    workflow_id: str = Field(..., alias="workflowId")
    variant: str | None = None
    next_action: str | None = Field(None, alias="nextAction")
    legal_conclusion: str | None = Field(None, alias="legalConclusion")
    questions: list[dict[str, str]] = Field(default_factory=list)
    suggested_workflow_ids: list[str] = Field(
        default_factory=list, alias="suggestedWorkflowIds"
    )
    confidence: float
    status: str
    outcome: str
    scenario: str | None = Field(
        None,
        description=(
            "ask_hr=담당자 화면 입력 | ask_worker=근로자 서류 요청 | "
            "generate=초안 작성 | ocr=서류 읽기 | out_of_scope=범위 밖"
        ),
    )
    phase: str | None = Field(
        None, description="PHASE_1~4 — Server UI 진행 표시용"
    )
    step: str | None = Field(
        None, description="STEP_2/4/5/7/11/13 등 AI 신호 단계"
    )
    slots: dict[str, Any] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list, alias="missingSlots")
    requested_fields: list[dict[str, str]] = Field(
        default_factory=list,
        alias="requestedFields",
        description="Server DB/화면 재조회용 {key, sourceHint}",
    )
    guide_message: str | None = Field(None, alias="guideMessage")
    worker_request_message: str | None = Field(None, alias="workerRequestMessage")
    guide_review_required: bool = Field(False, alias="guideReviewRequired")
    guide_failure_code: str | None = Field(None, alias="guideFailureCode")
    # Language Assistant 전체 출력 (태정 contracts JSON)
    language_assistant: dict[str, Any] | None = Field(None, alias="languageAssistant")
    ocr_result: dict[str, Any] | None = Field(None, alias="ocrResult")
    generated_documents: list[dict[str, Any]] = Field(
        default_factory=list, alias="generatedDocuments"
    )
    evidence: list[dict[str, str]] = Field(
        default_factory=list, description="Intent/서류 근거 요약"
    )
    document_validation: dict[str, Any] | None = Field(
        None,
        alias="documentValidation",
        description="여권·등록증 보유 조합 (Step4)",
    )
    case_signals: list[str] = Field(
        default_factory=list,
        alias="caseSignals",
        description="Server Case/Task 생성·대기용 신호 (생성 자체는 Server)",
    )
    progress_events: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="progressEvents",
        description="이번 호출의 phase/step 진행 로그 (UI·폴링용)",
    )
    supervisor_reason: str | None = Field(None, alias="supervisorReason")
    supervisor_source: str | None = Field(
        None, alias="supervisorSource", description="rules | llm"
    )
    active_subgraph: str | None = Field(None, alias="activeSubgraph")
    errors: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
