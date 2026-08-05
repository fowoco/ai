# HF Intent 에이전트·대표 Intent 선택 단위 테스트

from app.agents.intent.hybrid import HybridIntentPrediction
from app.agents.intent.service import (
    FixedExpiryRenewalIntentAgent,
    HybridHfIntentAgent,
    _primary_intent,
    build_intent_agent,
)


# 점수 있을 때 최고 점수 Intent 선택
def test_primary_intent_picks_highest_score() -> None:
    intent, conf = _primary_intent(
        ["DOCUMENT_REQUEST", "EXPIRY_RENEWAL"],
        {"DOCUMENT_REQUEST": 0.4, "EXPIRY_RENEWAL": 0.91},
    )
    assert intent == "EXPIRY_RENEWAL"
    assert conf == 0.91


# OUT_OF_SCOPE 단독 유지
def test_primary_intent_out_of_scope_alone() -> None:
    intent, conf = _primary_intent(["OUT_OF_SCOPE"], {"OUT_OF_SCOPE": 0.8})
    assert intent == "OUT_OF_SCOPE"
    assert conf == 0.8


# 기본 빌드는 재갱신 고정
def test_build_intent_agent_defaults_to_fixed() -> None:
    agent = build_intent_agent()
    assert isinstance(agent, FixedExpiryRenewalIntentAgent)
    result = agent.classify("아무 말")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.workflow_id in {"WF-STY-001", "WF-CON-001", ""}


# 주입된 파이프라인으로 Hybrid 에이전트 분류
def test_hybrid_agent_maps_pipeline_prediction() -> None:
    class _FakePipe:
        def predict(self, instruction: str) -> HybridIntentPrediction:
            del instruction
            return HybridIntentPrediction(
                intents=["EXPIRY_RENEWAL"],
                scores={"EXPIRY_RENEWAL": 0.93},
                selected_model="BERT",
            )

    agent = HybridHfIntentAgent(pipeline=_FakePipe())
    result = agent.classify("응웬반안 체류연장")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.confidence == 0.93
    assert result.workflow_id == "WF-STY-001"
