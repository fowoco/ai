"""슈퍼바이저·서류 조합 라우팅 유닛 테스트."""

from app.agents.workflow_graph.document_validation import validate_identity_documents
from app.agents.workflow_graph.state import empty_renewal_state
from app.agents.workflow_graph.supervisor import decide_route_rules


def test_both_missing_routes_ask_worker() -> None:
    state = empty_renewal_state(
        task_id="t", request_id="r", instruction="연장", worker_id="w1"
    )
    state["intent"] = "EXPIRY_RENEWAL"
    state["missing_slots"] = ["passport_number", "alien_registration_number", "wage"]
    decision = decide_route_rules(state)
    assert decision.route == "ask_worker"
    assert "REQUEST_IDENTITY_DOCUMENT" in decision.case_signals


def test_passport_only_requests_alien() -> None:
    state = empty_renewal_state(
        task_id="t", request_id="r", instruction="연장", worker_id="w1"
    )
    state["intent"] = "EXPIRY_RENEWAL"
    state["slots"] = {"passport_number": "P-1", "full_name": "A"}
    state["missing_slots"] = ["alien_registration_number", "nationality", "date_of_birth"]
    validation = validate_identity_documents(state)
    assert validation.combo == "passport_only"
    decision = decide_route_rules(state)
    assert decision.route == "ask_worker"
    assert "REQUEST_ALIEN_REGISTRATION" in decision.case_signals


def test_documents_route_ocr() -> None:
    state = empty_renewal_state(
        task_id="t", request_id="r", instruction="연장", worker_id="w1"
    )
    state["intent"] = "EXPIRY_RENEWAL"
    state["documents"] = [{"document_type": "passport", "filename": "p.jpg"}]
    decision = decide_route_rules(state)
    assert decision.route == "ocr"


def test_contract_missing_routes_ask_hr() -> None:
    state = empty_renewal_state(
        task_id="t", request_id="r", instruction="연장", worker_id="w1"
    )
    state["intent"] = "EXPIRY_RENEWAL"
    state["slots"] = {
        "passport_number": "P-1",
        "alien_registration_number": "A-1",
        "nationality": "VN",
        "full_name": "A",
        "date_of_birth": "1990-01-01",
    }
    state["ocr_result"] = {"passport_number": "P-1"}
    state["missing_slots"] = ["wage", "working_hours"]
    decision = decide_route_rules(state)
    assert decision.route == "ask_hr"


def test_ready_routes_generate() -> None:
    state = empty_renewal_state(
        task_id="t", request_id="r", instruction="연장", worker_id="w1"
    )
    state["intent"] = "EXPIRY_RENEWAL"
    state["slots"] = {
        "passport_number": "P-1",
        "alien_registration_number": "A-1",
        "nationality": "VN",
        "full_name": "A",
        "date_of_birth": "1990-01-01",
        "wage": "1",
        "working_hours": "8",
        "job_description": "x",
        "work_location": "y",
        "lodging": "z",
        "contract_period": "1y",
    }
    state["ocr_result"] = {"passport_number": "P-1"}
    state["missing_slots"] = []
    decision = decide_route_rules(state)
    assert decision.route == "generate"
