# HF Intent 에이전트·대표 Intent 선택 단위 테스트

from app.agents.intent.guardrail import HRRoutingGuardrail
from app.agents.intent.hybrid import HybridIntentPrediction
from app.agents.intent.service import (
    FixedExpiryRenewalIntentAgent,
    HybridHfIntentAgent,
    _primary_intent,
    build_intent_agent,
)
from app.core.config import get_settings


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


# INTENT_MODEL_ENABLED=true → HybridHfIntentAgent
def test_build_intent_agent_enabled_returns_hybrid(monkeypatch) -> None:
    monkeypatch.setenv("FOWOCO_INTENT_MODEL_ENABLED", "true")
    get_settings.cache_clear()
    try:
        agent = build_intent_agent()
        assert isinstance(agent, HybridHfIntentAgent)
    finally:
        get_settings.cache_clear()


# 파이프라인 로드 실패 시 재갱신 고정 폴백
def test_hybrid_load_failure_falls_back_to_fixed(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.agents.intent.hybrid.HybridIntentPipeline", _boom)
    agent = HybridHfIntentAgent()
    result = agent.classify("체류연장 준비해줘")
    assert result.intent == "EXPIRY_RENEWAL"
    assert agent._load_error is not None


# margin 통과 시 BERT 유지
def test_guardrail_pass_bert_when_confident() -> None:
    gate = HRRoutingGuardrail(margin_threshold=0.76)
    out = gate.should_route_to_ax(
        "응웬반안 체류연장 준비",
        {"EXPIRY_RENEWAL": 0.92, "DOCUMENT_REQUEST": 0.05},
        margin=0.87,
    )
    assert out.should_route is False
    assert out.category == "Pass_BERT"


# 서류 키워드면 A.X 라우팅
def test_guardrail_routes_on_document_keyword() -> None:
    gate = HRRoutingGuardrail()
    out = gate.should_route_to_ax(
        "신청서 서류 챙겨줘",
        {"DOCUMENT_REQUEST": 0.8},
        margin=0.9,
    )
    assert out.should_route is True
    assert out.category == "Rule_Document"
