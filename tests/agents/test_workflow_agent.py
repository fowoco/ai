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
    assert wf.workflow_id == "WF-STY-001"


def test_resolve_stay_workflow_from_instruction() -> None:
    agent = WorkflowAgent()
    wf = agent.resolve_workflow(
        "EXPIRY_RENEWAL",
        instruction="체류기간 연장 준비해줘",
    )
    assert wf is not None
    assert wf.workflow_id == "WF-STY-001"


def test_resolve_contract_workflow_from_instruction() -> None:
    agent = WorkflowAgent()
    wf = agent.resolve_workflow(
        "EXPIRY_RENEWAL",
        instruction="근로계약 종료 전에 재계약 준비해줘",
    )
    assert wf is not None
    assert wf.workflow_id == "WF-CON-001"


def test_resolve_document_and_administration_workflows() -> None:
    agent = WorkflowAgent()

    document = agent.resolve_workflow(
        "DOCUMENT_REQUEST",
        instruction="여권 사본을 업로드해 달라고 요청해줘",
    )
    administration = agent.resolve_workflow(
        "DOCUMENT_REQUEST",
        instruction="재직증명서를 발급해줘",
    )

    assert document is not None
    assert document.workflow_id == "WF-DOC-001"
    assert administration is not None
    assert administration.workflow_id == "WF-ADM-001"


def test_resolve_with_constraints() -> None:
    agent = WorkflowAgent()
    wf = agent.resolve_workflow("EXPIRY_RENEWAL", constraints=["WF-CON-001"])
    assert wf is not None
    assert wf.workflow_id == "WF-CON-001"
