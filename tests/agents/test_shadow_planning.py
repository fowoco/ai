"""Renewal Shadow Planning의 계획과 Legacy 격리 테스트."""

from app.agents.workflow_graph.agent_mode import AgentExecutionMode
from app.agents.workflow_graph.nodes.language_stub import CONTRACT_SLOTS
from app.agents.workflow_graph.planning import build_shadow_plan
from app.agents.workflow_graph.service import RenewalOrchestrator
from app.agents.workflow_graph.state import IDENTITY_SLOTS


def _complete_slots() -> dict[str, str]:
    slots = {
        "worker_id": "worker-shadow",
        "stay_expiry_date": "2026-12-31",
        "due_at": "2026-11-30",
    }
    for key in IDENTITY_SLOTS | frozenset(CONTRACT_SLOTS):
        slots[key] = f"value-{key}"
    return slots


def _shadow_event(state: dict) -> dict:
    return next(
        event
        for event in state.get("progress_events", [])
        if event.get("subgraph") == "agent-shadow"
    )


def test_shadow_plan_classifies_tool_and_server_control() -> None:
    plan = build_shadow_plan(
        {
            "intent": "EXPIRY_RENEWAL",
            "slots": _complete_slots(),
            "missing_slots": [],
            "documents": [],
            "ocr_result": None,
        }
    )

    assert plan.proposed_route == "generate"
    assert [step.action_type for step in plan.steps] == ["TOOL", "SERVER_CONTROL"]
    assert [step.action for step in plan.steps] == [
        "GENERATE_RENEWAL_DOCUMENTS",
        "REQUEST_HR_REVIEW",
    ]


def test_legacy_mode_does_not_create_shadow_trace() -> None:
    state = RenewalOrchestrator().run(
        request_id="req-legacy",
        instruction="체류기간 연장 준비해줘",
        worker_id="worker-legacy",
    )

    assert state["scenario"] == "ask_worker"
    assert not any(
        event.get("subgraph") == "agent-shadow"
        for event in state.get("progress_events", [])
    )


def test_shadow_mode_compares_plan_without_changing_legacy_route() -> None:
    state = RenewalOrchestrator().run(
        request_id="req-shadow",
        instruction="체류기간 연장 준비해줘",
        worker_id="worker-shadow",
        agent_mode=AgentExecutionMode.SHADOW,
    )

    event = _shadow_event(state)
    assert state["scenario"] == "ask_worker"
    assert event["mode"] == "SHADOW"
    assert event["decisionOwner"] == "AGENT"
    assert event["decisionType"] == "AGENT_JUDGMENT"
    assert event["proposedRoute"] == "ask_worker"
    assert event["legacyRoute"] == "ask_worker"
    assert event["matched"] is True
    assert event["plan"][0]["actionType"] == "SERVER_CONTROL"


def test_shadow_mode_records_route_difference_but_uses_supervisor_result() -> None:
    def out_of_scope_language(state: dict) -> dict:
        return {
            "intent": "OUT_OF_SCOPE",
            "workflow_id": "",
            "confidence": 0.9,
            "slots": state.get("slots", {}),
            "missing_slots": [],
        }

    state = RenewalOrchestrator(language_node=out_of_scope_language).run(
        request_id="req-shadow-out",
        instruction="오늘 날씨 알려줘",
        worker_id="worker-shadow",
        agent_mode=AgentExecutionMode.SHADOW,
    )

    event = _shadow_event(state)
    assert state["scenario"] == "out_of_scope"
    assert state["outcome"] == "OUT_OF_SCOPE"
    assert event["legacyRoute"] == "out_of_scope"
