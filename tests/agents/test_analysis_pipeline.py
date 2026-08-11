# AnalysisPipeline PLAN/ANALYZE 단위 테스트

from uuid import uuid4

from app.agents.intent.service import IntentDecision, IntentResult
from app.agents.pipeline import AnalysisPipeline
from app.api.schemas.analyses import AnalysisInput, AnalysisRequest, WorkerContext


# IntentClassifier Protocol용 고정 분류기
class _FakeIntent:
    def __init__(
        self,
        *,
        intent: str,
        confidence: float | None = 0.9,
        workflow_id: str = "",
        decisions: list[IntentDecision] | None = None,
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.workflow_id = workflow_id
        self.decisions = decisions or []
        self.calls = 0

    def runtime_status(self) -> dict[str, object]:
        return {}

    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult:
        del instruction, workflow_constraints
        self.calls += 1
        return IntentResult(
            intent=self.intent,
            confidence=self.confidence,
            workflow_id=self.workflow_id,
            model_provider="test",
            model_name="fake-intent",
            model_version="1",
            extracted_slots={},
            prompt_version="test-prompt-v1",
            confidence_source="BERT",
            bert_routing_score=self.confidence,
            decisions=self.decisions,
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
    assert res.context_requirement.workflow_id == "WF-STY-001"
    assert res.context_requirement.confidence_source == "BERT"
    assert res.context_requirement.intent_decisions[0].workflow_id == "WF-STY-001"
    assert res.versions.model_provider == "test"
    assert res.versions.model_name == "fake-intent"
    assert res.versions.model_version == "1"
    assert res.versions.prompt_version == "test-prompt-v1"
    assert "worker_id" in res.context_requirement.required_field_keys
    assert "passport_status" in res.context_requirement.required_field_keys
    assert "arc_status" in res.context_requirement.required_field_keys


def test_analyze_does_not_ask_hr_for_document_managed_fields() -> None:
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(intent="EXPIRY_RENEWAL", workflow_id="WF-STY-001")
    )
    worker = WorkerContext(
        workerRef="30000000-0000-0000-0000-000000000001",
        requestedFields={
            "worker_id": "30000000-0000-0000-0000-000000000001",
            "stay_expiry_date": "2026-12-31",
        },
    )
    req = AnalysisRequest(
        requestId=str(uuid4()),
        phase="ANALYZE",
        analysisInput=AnalysisInput(
            instruction="체류 연장",
            requestedFieldKeys=[
                "worker_id",
                "passport_status",
                "arc_status",
                "arc_expiry_date",
            ],
            workers=[worker],
        ),
    )

    res = pipe.run(req)

    assert res.outcome == "REVIEW_REQUIRED"
    assert res.questions == []


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
    assert res.candidates[0].workflow_id == "WF-STY-001"


def test_analyze_reuses_plan_decisions_without_classifying_again() -> None:
    intent = _FakeIntent(
        intent="EXPIRY_RENEWAL", confidence=0.91, workflow_id="WF-STY-001"
    )
    pipe = AnalysisPipeline(intent_agent=intent)
    plan = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(instruction="체류연장 준비해줘"),
        )
    )
    assert plan.context_requirement is not None

    analyze = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="ANALYZE",
            analysisInput=AnalysisInput(
                instruction="체류연장 준비해줘",
                requestedFieldKeys=plan.context_requirement.required_field_keys,
                plannedIntentDecisions=plan.context_requirement.intent_decisions,
                workers=[
                    WorkerContext(
                        workerRef="worker-1",
                        requestedFields={
                            "worker_id": "worker-1",
                            "stay_expiry_date": "2026-12-31",
                        },
                    )
                ],
            ),
        )
    )

    assert intent.calls == 1
    assert analyze.provider_attempt_count == 0
    assert analyze.outcome == "REVIEW_REQUIRED"
    assert analyze.candidates[0].detected_intent == "EXPIRY_RENEWAL"


def test_multi_intent_unions_plan_fields_and_builds_one_candidate_per_intent() -> None:
    decisions = [
        IntentDecision(
            intent="EXPIRY_RENEWAL",
            workflow_id="WF-STY-001",
            confidence=None,
            confidence_source="UNAVAILABLE",
            bert_routing_score=0.31,
            evidence="체류연장 준비하고",
        ),
        IntentDecision(
            intent="PAYROLL_EXPLANATION",
            workflow_id="WF-PAY-001",
            confidence=None,
            confidence_source="UNAVAILABLE",
            bert_routing_score=0.22,
            evidence="급여도 확인해줘",
        ),
    ]
    intent = _FakeIntent(
        intent="EXPIRY_RENEWAL",
        confidence=None,
        workflow_id="WF-STY-001",
        decisions=decisions,
    )
    pipe = AnalysisPipeline(intent_agent=intent)
    plan = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(
                instruction="체류연장 준비하고 급여도 확인해줘"
            ),
        )
    )
    assert plan.context_requirement is not None
    assert plan.context_requirement.required_field_keys == [
        "worker_id",
        "stay_expiry_date",
        "passport_status",
        "arc_status",
        "pay_period",
    ]

    analyze = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="ANALYZE",
            analysisInput=AnalysisInput(
                instruction="체류연장 준비하고 급여도 확인해줘",
                requestedFieldKeys=plan.context_requirement.required_field_keys,
                plannedIntentDecisions=plan.context_requirement.intent_decisions,
                workers=[
                    WorkerContext(
                        workerRef="worker-1",
                        requestedFields={
                            "worker_id": "worker-1",
                            "stay_expiry_date": "2026-12-31",
                            "pay_period": "2026-08",
                        },
                    )
                ],
            ),
        )
    )

    assert intent.calls == 1
    assert analyze.provider_attempt_count == 0
    assert [candidate.detected_intent for candidate in analyze.candidates] == [
        "EXPIRY_RENEWAL",
        "PAYROLL_EXPLANATION",
    ]
    assert [candidate.workflow_id for candidate in analyze.candidates] == [
        "WF-STY-001",
        "WF-PAY-001",
    ]
    assert all(candidate.confidence is None for candidate in analyze.candidates)
