"""Workflow Agent 유닛 테스트."""

from app.agents.workflow import WorkflowAgent


def test_get_known_workflow() -> None:
    agent = WorkflowAgent()
    wf = agent.get_workflow("WF-STY-001")
    assert wf is not None
    assert wf.name == "체류기간 연장 준비"
    assert wf.sensitivity == "high"
    assert "worker_id" in wf.required_slots


def test_get_unknown_workflow() -> None:
    agent = WorkflowAgent()
    assert agent.get_workflow("WF-XXX-999") is None


def test_list_workflows() -> None:
    agent = WorkflowAgent()
    workflows = agent.list_workflows()
    assert len(workflows) == 8


def test_resolve_workflow_by_intent() -> None:
    agent = WorkflowAgent()
    wf = agent.resolve_workflow("EXPIRY_RENEWAL")
    assert wf is not None
    assert wf.workflow_id in ("WF-STY-001", "WF-CON-001")


def test_resolve_with_constraints() -> None:
    agent = WorkflowAgent()
    wf = agent.resolve_workflow("EXPIRY_RENEWAL", constraints=["WF-CON-001"])
    assert wf is not None
    assert wf.workflow_id == "WF-CON-001"
