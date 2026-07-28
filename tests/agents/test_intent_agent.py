"""Intent/Slot Agent 유닛 테스트."""

from app.agents.intent import IntentSlotAgent


def test_classifies_expiry_renewal() -> None:
    agent = IntentSlotAgent()
    result = agent.classify("체류기간 연장 준비해줘")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.workflow_id in ("WF-STY-001", "WF-CON-001")
    assert result.confidence >= 0.5


def test_classifies_document_request() -> None:
    agent = IntentSlotAgent()
    result = agent.classify("여권 사본 서류 발급해줘")
    assert result.intent == "DOCUMENT_REQUEST"


def test_extracts_date_slot() -> None:
    agent = IntentSlotAgent()
    result = agent.classify("체류 만료 2026-12-31 연장 준비")
    assert "stay_expiry_date" in result.extracted_slots
    assert result.extracted_slots["stay_expiry_date"] == "2026-12-31"


def test_extracts_worker_id_slot() -> None:
    agent = IntentSlotAgent()
    result = agent.classify("WRK-012 근로자 등록해줘")
    assert result.extracted_slots.get("worker_id") == "WRK-012"


def test_out_of_scope() -> None:
    agent = IntentSlotAgent()
    result = agent.classify("오늘 날씨 어때?")
    assert result.intent == "OUT_OF_SCOPE"
    assert result.confidence < 0.5


def test_respects_workflow_constraints() -> None:
    agent = IntentSlotAgent()
    result = agent.classify("체류 연장", workflow_constraints=["WF-CON-001"])
    assert result.workflow_id == "WF-CON-001"
