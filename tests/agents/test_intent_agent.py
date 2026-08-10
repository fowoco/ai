# Intent Agent 유닛 테스트 — Knowledge Catalog 매핑 + 재갱신 고정

from app.agents.intent import FixedExpiryRenewalIntentAgent, build_intent_agent
from app.agents.intent.service import INTENT_TO_WORKFLOWS, public_workflow_id


def test_fixed_expiry_renewal_ignores_unrelated_text() -> None:
    agent = FixedExpiryRenewalIntentAgent()
    result = agent.classify("오늘 날씨 어때?")
    assert result.intent == "EXPIRY_RENEWAL"
    assert result.confidence == 1.0
    assert result.workflow_id == "WF-STY-001"
    assert result.extracted_slots == {}
    assert result.model_provider == "internal"
    assert result.model_name == "fixed-expiry-renewal"
    assert result.model_version == "rules"


def test_fixed_does_not_extract_slots_from_instruction() -> None:
    agent = FixedExpiryRenewalIntentAgent()
    result = agent.classify("WRK-012 만료 2026-12-31")
    assert result.extracted_slots == {}


def test_fixed_respects_workflow_constraints() -> None:
    agent = FixedExpiryRenewalIntentAgent()
    result = agent.classify("연장", workflow_constraints=["WF-CON-001"])
    assert result.workflow_id == "WF-CON-001"


def test_build_intent_agent_is_fixed() -> None:
    assert isinstance(build_intent_agent(), FixedExpiryRenewalIntentAgent)


def test_intent_to_workflows_matches_knowledge_catalog() -> None:
    assert INTENT_TO_WORKFLOWS["EXPIRY_RENEWAL"] == ["WF-STY-001", "WF-CON-001"]
    assert INTENT_TO_WORKFLOWS["WORKER_ONBOARDING"] == ["WF-WRK-001"]


def test_public_workflow_id_prefers_intent_constraint() -> None:
    assert (
        public_workflow_id(
            internal_workflow_id="WF-STY-001",
            intent="EXPIRY_RENEWAL",
            constraints=["EXPIRY_RENEWAL"],
        )
        == "EXPIRY_RENEWAL"
    )
