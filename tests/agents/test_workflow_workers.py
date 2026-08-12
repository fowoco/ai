# 재갱신 워커 경계 계약
from app.agents.workflow_graph.document_field_map import values_for_template
from app.agents.workflow_graph.nodes.document_generator import RENEWAL_DRAFT_TEMPLATE_IDS
from app.agents.workflow_graph.state import empty_renewal_state
from app.agents.workflow_graph.workers import (
    BusinessRecognitionAgent,
    DocumentAutomationAgent,
    DocumentIntelligenceAgent,
    ValidationReviewAgent,
)


def empty_state():
    return empty_renewal_state(
        task_id="task-worker-1",
        request_id="req-worker-1",
        instruction="체류기간 연장 갱신",
    )


def filled_state():
    state = empty_state()
    state["slots"] = {"full_name": "NGUYEN VAN AN"}
    return state


def test_business_agent_preserves_language_patch() -> None:
    expected = {"intent": "EXPIRY_RENEWAL", "workflow_id": "WF-STY-001"}
    agent = BusinessRecognitionAgent(lambda state: expected)
    assert agent(empty_state()) == expected


def test_document_intelligence_reuses_registered_mappers() -> None:
    state = filled_state()
    patch = DocumentIntelligenceAgent()(state)
    assert tuple(patch["document_field_values"]) == RENEWAL_DRAFT_TEMPLATE_IDS
    assert patch["document_field_values"]["standard_labor_contract_v6"] == (
        values_for_template("standard_labor_contract_v6", state)
    )


def test_document_automation_passes_state_to_existing_generator() -> None:
    seen = []
    agent = DocumentAutomationAgent(lambda state: seen.append(state) or [{"status": "stub"}])
    patch = agent(empty_state())
    assert seen and patch == {"generated_documents": [{"status": "stub"}]}


def test_review_agent_preserves_review_required_patch() -> None:
    state = empty_state()
    state["generated_documents"] = [{"status": "stub"}]
    assert ValidationReviewAgent()(state) == {
        "scenario": "generate",
        "status": "READY_FOR_REVIEW",
        "outcome": "REVIEW_REQUIRED",
        "missing_slots": [],
        "guide_message": None,
        "worker_request_message": None,
        "case_signals": ["GENERATE_DRAFTS", "READY_FOR_REVIEW"],
        "phase": "PHASE_3_EXTRACTION_DOCUMENT",
        "step": "STEP_13_DOCUMENT_DRAFT",
    }


def test_empty_state_initializes_document_field_values() -> None:
    assert empty_state()["document_field_values"] == {}
