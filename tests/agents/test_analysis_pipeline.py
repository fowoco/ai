# AnalysisPipeline PLAN/ANALYZE 단위 테스트

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.intent.service import IntentResult
from app.agents.pipeline import AnalysisPipeline
from app.api.schemas.analyses import AnalysisInput, AnalysisRequest, WorkerContext


class _FakeIntent:
    def __init__(
        self,
        *,
        intent: str,
        confidence: float | None = 0.9,
        workflow_id: str = "",
        evidence: str | None = None,
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.workflow_id = workflow_id
        self.evidence = evidence
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
            prompt_version="test-prompt-v1",
            confidence_source="BERT",
            bert_routing_score=self.confidence,
            evidence=self.evidence,
        )


def _analyze_request(
    *,
    workers: list[WorkerContext],
    requested_field_keys: list[str],
    instruction: str = "체류연장 준비해줘",
) -> AnalysisRequest:
    return AnalysisRequest(
        requestId=str(uuid4()),
        phase="ANALYZE",
        analysisInput=AnalysisInput(
            instruction=instruction,
            plannedIntent="EXPIRY_RENEWAL",
            plannedWorkflowId="WF-STY-001",
            agentTarget="renewal-agent",
            requestedFieldKeys=requested_field_keys,
            workers=workers,
        ),
    )


def test_plan_returns_single_context_decision_without_fake_evidence_slot() -> None:
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(
            intent="EXPIRY_RENEWAL",
            workflow_id="WF-STY-001",
            evidence="체류연장 준비해줘",
        )
    )
    res = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(instruction="응웬반안 체류연장 준비해줘"),
        )
    )

    assert res.outcome == "CONTEXT_REQUIRED"
    assert res.context_requirement is not None
    ctx = res.context_requirement
    assert ctx.detected_intent == "EXPIRY_RENEWAL"
    assert ctx.workflow_id == "WF-STY-001"
    assert ctx.agent_target == "renewal-agent"
    assert ctx.evidence == "체류연장 준비해줘"
    assert ctx.confidence_source == "BERT"
    assert ctx.extracted_slots == {}
    assert res.versions.prompt_version == "test-prompt-v1"
    assert "worker_id" in ctx.required_field_keys
    assert "passport_status" in ctx.required_field_keys
    assert "arc_status" in ctx.required_field_keys


def test_plan_out_of_scope_terminates_without_context_lookup() -> None:
    pipe = AnalysisPipeline(intent_agent=_FakeIntent(intent="OUT_OF_SCOPE", confidence=0.7))
    res = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(instruction="오늘 날씨 어때"),
        )
    )

    assert res.outcome == "OUT_OF_SCOPE"
    assert res.context_requirement is None
    assert res.questions == []
    assert res.candidates == []
    assert res.provider_attempt_count == 1


def test_plan_does_not_advertise_unimplemented_logical_agent() -> None:
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(
            intent="DOCUMENT_REQUEST",
            workflow_id="WF-DOC-001",
        )
    )

    res = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(instruction="여권 사본을 요청해줘"),
        )
    )

    assert res.context_requirement is not None
    assert res.context_requirement.agent_target is None


def test_analyze_requires_planned_intent_and_workflow() -> None:
    with pytest.raises(ValidationError, match="requires plannedIntent"):
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="ANALYZE",
            analysisInput=AnalysisInput(
                instruction="체류연장",
                requestedFieldKeys=["worker_id"],
                workers=[],
            ),
        )


def test_analyze_without_workers_needs_info_without_model_call() -> None:
    intent = _FakeIntent(intent="DOCUMENT_REQUEST", workflow_id="WF-DOC-001")
    pipe = AnalysisPipeline(intent_agent=intent)

    res = pipe.run(
        _analyze_request(
            workers=[],
            requested_field_keys=["worker_id", "stay_expiry_date"],
        )
    )

    assert res.outcome == "NEEDS_INFO"
    assert any(q.slot_key == "worker_id" for q in res.questions)
    assert res.provider_attempt_count == 0
    assert intent.calls == 0


def test_analyze_does_not_ask_hr_for_document_managed_fields() -> None:
    intent = _FakeIntent(intent="DOCUMENT_REQUEST", workflow_id="WF-DOC-001")
    pipe = AnalysisPipeline(intent_agent=intent)
    worker = WorkerContext(
        workerRef="worker-1",
        requestedFields={
            "worker_id": "worker-1",
            "stay_expiry_date": "2026-12-31",
        },
    )

    res = pipe.run(
        _analyze_request(
            workers=[worker],
            requested_field_keys=[
                "worker_id",
                "passport_status",
                "arc_status",
                "arc_expiry_date",
            ],
        )
    )

    assert res.outcome == "REVIEW_REQUIRED"
    assert res.questions == []
    assert intent.calls == 0


def test_analyze_reuses_plan_decision_without_classifying_again() -> None:
    intent = _FakeIntent(
        intent="EXPIRY_RENEWAL",
        confidence=0.91,
        workflow_id="WF-STY-001",
        evidence="체류연장 준비해줘",
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
    ctx = plan.context_requirement

    analyze = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="ANALYZE",
            analysisInput=AnalysisInput(
                instruction="체류연장 준비해줘",
                plannedIntent=ctx.detected_intent,
                plannedWorkflowId=ctx.workflow_id,
                agentTarget=ctx.agent_target,
                requestedFieldKeys=ctx.required_field_keys,
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
    assert len(analyze.candidates) == 1
    assert analyze.candidates[0].workflow_id == "WF-STY-001"
    assert analyze.candidates[0].confidence is None
    assert not any(key.startswith("evidence:") for key in analyze.candidates[0].extracted_slots)
