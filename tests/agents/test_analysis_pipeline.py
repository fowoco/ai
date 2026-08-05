# AnalysisPipeline PLAN/ANALYZE 단위 테스트

from uuid import uuid4

from app.agents.intent.service import IntentResult
from app.agents.pipeline import AnalysisPipeline
from app.api.schemas.analyses import AnalysisInput, AnalysisRequest, WorkerContext


# IntentClassifier Protocol용 고정 분류기
class _FakeIntent:
    def __init__(self, *, intent: str, confidence: float = 0.9, workflow_id: str = "") -> None:
        self.intent = intent
        self.confidence = confidence
        self.workflow_id = workflow_id

    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult:
        del instruction, workflow_constraints
        return IntentResult(
            intent=self.intent,
            confidence=self.confidence,
            workflow_id=self.workflow_id,
            extracted_slots={},
        )


# PLAN → CONTEXT_REQUIRED + requiredFieldKeys
def test_plan_returns_context_required_for_expiry() -> None:
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(intent="EXPIRY_RENEWAL", workflow_id="WF-STY-001")
    )
    req = AnalysisRequest(
        requestId=str(uuid4()),
        phase="PLAN",
        analysisInput=AnalysisInput(instruction="응웬반안 체류연장 준비해줘"),
    )
    res = pipe.run(req)
    assert res.outcome == "CONTEXT_REQUIRED"
    assert res.context_requirement is not None
    assert res.context_requirement.detected_intent == "EXPIRY_RENEWAL"
    assert "worker_id" in res.context_requirement.required_field_keys


# OUT_OF_SCOPE PLAN은 worker_id만 요청
def test_plan_out_of_scope_requests_worker_id_only() -> None:
    pipe = AnalysisPipeline(intent_agent=_FakeIntent(intent="OUT_OF_SCOPE", confidence=0.7))
    req = AnalysisRequest(
        requestId=str(uuid4()),
        phase="PLAN",
        analysisInput=AnalysisInput(instruction="오늘 날씨 어때"),
    )
    res = pipe.run(req)
    assert res.outcome == "CONTEXT_REQUIRED"
    assert res.context_requirement is not None
    assert res.context_requirement.required_field_keys == ["worker_id"]


# ANALYZE workers 없으면 NEEDS_INFO
def test_analyze_without_workers_needs_info() -> None:
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(intent="EXPIRY_RENEWAL", workflow_id="WF-STY-001")
    )
    req = AnalysisRequest(
        requestId=str(uuid4()),
        phase="ANALYZE",
        analysisInput=AnalysisInput(
            instruction="체류연장",
            requestedFieldKeys=["worker_id", "stay_expiry_date"],
            workers=[],
        ),
    )
    res = pipe.run(req)
    assert res.outcome == "NEEDS_INFO"
    assert any(q.slot_key == "worker_id" for q in res.questions)


# ANALYZE 슬롯 충족 시 REVIEW_REQUIRED + missingSlots 빈 목록
def test_analyze_filled_slots_review_required() -> None:
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(
            intent="EXPIRY_RENEWAL", confidence=0.91, workflow_id="WF-STY-001"
        )
    )
    worker = WorkerContext(
        workerRef="30000000-0000-0000-0000-000000000001",
        requestedFields={
            "worker_id": "30000000-0000-0000-0000-000000000001",
            "stay_expiry_date": "2026-12-31",
            "contract_end_date": "2026-12-31",
            "legal_name": "NGUYEN VAN AN",
            "passport_number": "M12345678",
            "alien_registration_number": "123456-7890123",
            "date_of_birth": "1990-01-01",
            "nationality": "VN",
            "full_name": "NGUYEN VAN AN",
        },
    )
    req = AnalysisRequest(
        requestId=str(uuid4()),
        phase="ANALYZE",
        analysisInput=AnalysisInput(
            instruction="응웬반안 체류연장",
            requestedFieldKeys=list(worker.requested_fields.keys()),
            workers=[worker],
        ),
    )
    res = pipe.run(req)
    assert res.outcome == "REVIEW_REQUIRED"
    assert len(res.candidates) == 1
    assert res.candidates[0].missing_slots == []
    assert res.candidates[0].workflow_id == "EXPIRY_RENEWAL"
