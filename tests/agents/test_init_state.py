# Server 일괄 JSON → Shared State 초기화 테스트
from app.agents.workflow_graph.init_state import (
    init_renewal_state_from_bundle,
    slots_from_server_bundle,
)


# worker·company 필드가 slots에 선채움되는지 확인
def test_slots_from_server_bundle_prefills_worker_company():
    slots = slots_from_server_bundle(
        worker={
            "worker_id": "worker-001",
            "display_name": "Nguyen Van A",
            "stay_expiry_date": "2026-12-31",
            "nationality_code": "VN",
        },
        company={"company_id": "company-001", "name": "Demo Co"},
        task={"business_data_json": '{"wage": "2500000"}'},
    )
    assert slots["worker_id"] == "worker-001"
    assert slots["full_name"] == "Nguyen Van A"
    assert slots["nationality"] == "VN"
    assert slots["enterprise_name"] == "Demo Co"
    assert slots["wage"] == "2500000"


# 일괄 페이로드로 State 초깃값 생성
def test_init_renewal_state_from_bundle():
    state = init_renewal_state_from_bundle(
        request_id="req-1",
        instruction="체류연장 준비",
        worker={"worker_id": "worker-001", "stay_expiry_date": "2026-12-31"},
        company={"company_id": "company-001", "name": "Demo Co"},
        task={"task_id": "task-1", "workflow_id": "WF-STY-001"},
    )
    assert state["task_id"] == "task-1"
    assert state["worker_id"] == "worker-001"
    assert state["company_id"] == "company-001"
    assert state["workflow_id"] == "WF-STY-001"
    assert state["worker_record"]["worker_id"] == "worker-001"
    assert state["slots"]["stay_expiry_date"] == "2026-12-31"
