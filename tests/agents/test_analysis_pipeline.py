# AnalysisPipeline PLAN/ANALYZE 단위 테스트

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.intent.service import IntentResult
from app.agents.pipeline import AnalysisPipeline, _guess_target_display_name
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
    assert ctx.evidence == "체류연장 준비해줘"
    assert ctx.confidence_source == "BERT"
    assert ctx.extracted_slots == {}
    assert res.versions.prompt_version == "test-prompt-v1"
    assert ctx.required_field_keys == [
        "worker_id",
        "due_at",
        "stay_expiry_date",
        "passport_status",
        "arc_status",
    ]
    assert res.versions.context_pack_version == "0.3.1"
    assert res.versions.workflow_catalog_version == "0.3.1"


def test_plan_strips_trailing_josa_from_target_display_name() -> None:
    # 회귀 재현: "속 체아의" -> 조사 "의"가 안 떨어져서 server의 exact-match 조회가
    # 항상 TARGET_NOT_FOUND로 실패했던 문제 (2026-08-13).
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(intent="EXPIRY_RENEWAL", workflow_id="WF-STY-001")
    )
    res = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(instruction="속 체아의 체류기간 연장 준비해줘"),
        )
    )
    assert res.context_requirement is not None
    assert res.context_requirement.target_display_name == "속 체아"


def test_plan_stops_target_name_before_renewal_action() -> None:
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(intent="EXPIRY_RENEWAL", workflow_id="WF-STY-001")
    )
    res = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(
                instruction="응웬반A 재계약하고 체류연장 준비해줘"
            ),
        )
    )

    assert res.context_requirement is not None
    assert res.context_requirement.target_display_name == "응웬반A"


def test_plan_does_not_truncate_names_ending_in_a_particle_like_syllable() -> None:
    # "리웨이"처럼 마지막 음절이 조사(이/가 등)와 우연히 겹치는 음역 인명은
    # 잘라내면 안 된다. "웨"(받침 없음) 뒤에 "이"(받침 있는 음절 뒤에만 오는
    # 주격조사)가 온 건 받침 규칙에 안 맞으므로 조사가 아니라고 판단한다.
    pipe = AnalysisPipeline(
        intent_agent=_FakeIntent(intent="EXPIRY_RENEWAL", workflow_id="WF-STY-001")
    )
    res = pipe.run(
        AnalysisRequest(
            requestId=str(uuid4()),
            phase="PLAN",
            analysisInput=AnalysisInput(instruction="리웨이 체류기간 연장 준비"),
        )
    )
    assert res.context_requirement is not None
    assert res.context_requirement.target_display_name == "리웨이"


@pytest.mark.parametrize(
    ("instruction", "expected_name"),
    [
        ("응우옌 티 란이 체류기간 연장 준비해줘", "응우옌 티 란"),
        ("쩐 꾸옥 바오는 체류기간 연장이 필요해", "쩐 꾸옥 바오"),
        ("마크 레예스를 위해 계약 갱신 준비", "마크 레예스"),
        ("라니 위자야가 계약 종료 예정이라 준비해줘", "라니 위자야"),
        ("아르준 타파의 서류 확인 요청", "아르준 타파"),
    ],
)
def test_guess_target_display_name_strips_batchim_consistent_particles(
    instruction: str, expected_name: str
) -> None:
    # 받침 유무가 실제 조사 짝과 일치하는 경우에만 잘라낸다 (예: "란"은
    # 받침이 있어서 "이"가 올 수 있고, "바오"는 받침이 없어서 "는"이 올 수
    # 있음). 이 규칙 덕분에 "리웨이"류 오탐 없이 이/가/은/는/을/를까지
    # 넓게 처리할 수 있다.
    assert _guess_target_display_name(instruction) == expected_name


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
            "due_at": "2026-10-01T09:00:00+09:00",
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
                requestedFieldKeys=ctx.required_field_keys,
                workers=[
                    WorkerContext(
                        workerRef="worker-1",
                        requestedFields={
                            "worker_id": "worker-1",
                            "due_at": "2026-10-01T09:00:00+09:00",
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
