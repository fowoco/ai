"""Intent/Slot Agent 유닛 테스트."""

from app.agents.intent import (
    FixedExpiryRenewalIntentAgent,
    IntentSlotAgent,
    KeywordIntentSlotAgent,
    build_intent_agent,
)


def test_classifies_expiry_renewal() -> None:
    agent = KeywordIntentSlotAgent()
    result = agent.classify("체류기간 연장 준비해줘")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.workflow_id in ("WF-STY-001", "WF-CON-001")
    assert result.confidence >= 0.5


def test_classifies_document_request() -> None:
    agent = KeywordIntentSlotAgent()
    result = agent.classify("여권 사본 서류 발급해줘")
    assert result.intent == "DOCUMENT_REQUEST"


def test_extracts_date_slot() -> None:
    agent = KeywordIntentSlotAgent()
    result = agent.classify("체류 만료 2026-12-31 연장 준비")
    assert "stay_expiry_date" in result.extracted_slots
    assert result.extracted_slots["stay_expiry_date"] == "2026-12-31"


def test_extracts_worker_id_slot() -> None:
    agent = KeywordIntentSlotAgent()
    result = agent.classify("WRK-012 근로자 등록해줘")
    assert result.extracted_slots.get("worker_id") == "WRK-012"


def test_out_of_scope() -> None:
    agent = KeywordIntentSlotAgent()
    result = agent.classify("오늘 날씨 어때?")
    assert result.intent == "OUT_OF_SCOPE"
    assert result.confidence < 0.5


def test_respects_workflow_constraints() -> None:
    agent = KeywordIntentSlotAgent()
    result = agent.classify("체류 연장", workflow_constraints=["WF-CON-001"])
    assert result.workflow_id == "WF-CON-001"


def test_intent_slot_agent_alias_is_keyword() -> None:
    assert IntentSlotAgent is KeywordIntentSlotAgent


def test_fixed_expiry_renewal_ignores_unrelated_text() -> None:
    agent = FixedExpiryRenewalIntentAgent()
    result = agent.classify("오늘 날씨 어때?")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.confidence == 1.0
    assert result.workflow_id == "WF-STY-001"


def test_fixed_expiry_renewal_extracts_slots() -> None:
    agent = FixedExpiryRenewalIntentAgent()
    result = agent.classify("WRK-012 만료 2026-12-31")
    assert result.extracted_slots.get("worker_id") == "WRK-012"
    assert result.extracted_slots.get("stay_expiry_date") == "2026-12-31"


def test_fixed_respects_workflow_constraints() -> None:
    agent = FixedExpiryRenewalIntentAgent()
    result = agent.classify("연장", workflow_constraints=["WF-CON-001"])
    assert result.workflow_id == "WF-CON-001"


def test_build_intent_agent_modes() -> None:
    assert isinstance(build_intent_agent("fixed_expiry_renewal"), FixedExpiryRenewalIntentAgent)
    assert isinstance(build_intent_agent("keyword"), KeywordIntentSlotAgent)
