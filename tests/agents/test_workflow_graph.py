"""재갱신 LangGraph 오케스트레이터 유닛 테스트."""

from app.agents.workflow_graph import RenewalOrchestrator
from app.agents.workflow_graph.nodes.language_stub import CONTRACT_SLOTS
from app.agents.workflow_graph.state import IDENTITY_SLOTS
from app.db.memory import InMemoryDb


def _filled_renewal_slots() -> dict[str, str]:
    """문서생성까지 가기 위한 최소 슬롯 세트."""
    slots = {
        "worker_id": "WRK-001",
        "due_at": "2026-11-30",
        "stay_expiry_date": "2026-12-31",
    }
    for key in IDENTITY_SLOTS:
        slots[key] = f"stub-{key}"
    for key in CONTRACT_SLOTS:
        slots[key] = f"stub-{key}"
    return slots


def test_expiry_renewal_requires_guide_review_when_language_is_unavailable() -> None:
    """안내 생성기가 없으면 내부 키를 보내지 않고 HR 검토로 멈춘다."""
    orch = RenewalOrchestrator(lookup=InMemoryDb(), store=InMemoryDb())
    state = orch.run(
        request_id="req-1",
        instruction="체류기간 연장 갱신 어떻게 해?",
        worker_id="worker-001",
        company_id="company-001",
    )
    assert state["intent"] == "EXPIRY_RENEWAL"
    assert state["scenario"] == "ask_worker"
    assert state["outcome"] == "REVIEW_REQUIRED"
    assert state["worker_request_message"] is None
    assert state["guide_review_required"] is True
    assert state["guide_failure_code"] == "LANGUAGE_ASSISTANT_NOT_CONFIGURED"
    assert "REVIEW_WORKER_GUIDE" in state["case_signals"]
    assert "passport_number" in state["missing_slots"]


def test_renewal_preserves_server_task_workflow() -> None:
    """Renewal 실행은 발화 재분류보다 Server Task Workflow를 우선한다."""
    orch = RenewalOrchestrator(lookup=InMemoryDb(), store=InMemoryDb())
    state = orch.run(
        request_id="req-contract-task",
        instruction="체류기간 연장 준비해줘",
        task_id="task-contract",
        worker_id="worker-001",
        task={
            "task_id": "task-contract",
            "workflow_id": "WF-CON-001",
            "task_type": "RECONTRACT",
        },
    )

    assert state["intent"] == "EXPIRY_RENEWAL"
    assert state["workflow_id"] == "WF-CON-001"


def test_out_of_scope_clears_server_task_workflow() -> None:
    """OUT_OF_SCOPE에는 Server Task가 있어도 실행 Workflow를 반환하지 않는다."""

    def out_of_scope_language(state: dict) -> dict:
        return {
            "intent": "OUT_OF_SCOPE",
            "workflow_id": state.get("workflow_id"),
            "confidence": 0.9,
            "slots": state.get("slots", {}),
            "missing_slots": [],
        }

    orch = RenewalOrchestrator(language_node=out_of_scope_language)
    state = orch.run(
        request_id="req-out-of-scope-task",
        instruction="오늘 날씨 어때?",
        task_id="task-contract",
        worker_id="worker-001",
        task={
            "task_id": "task-contract",
            "workflow_id": "WF-CON-001",
            "task_type": "RECONTRACT",
        },
    )

    assert state["intent"] == "OUT_OF_SCOPE"
    assert state["workflow_id"] == ""
    assert state["outcome"] == "OUT_OF_SCOPE"


def test_ask_hr_when_identity_filled_but_contract_missing() -> None:
    """신분은 있고 계약 슬롯만 비면 담당자 입력(NEEDS_INFO)로 간다."""
    orch = RenewalOrchestrator()
    identity = {key: f"v-{key}" for key in IDENTITY_SLOTS}
    state = orch.run(
        request_id="req-s1",
        instruction="체류기간 연장 갱신",
        worker_id="worker-001",
        slots={
            "worker_id": "WRK-001",
            "stay_expiry_date": "2026-12-31",
            **identity,
        },
    )
    assert state["scenario"] == "ask_hr"
    assert state["outcome"] == "NEEDS_INFO"
    assert "wage" in state["missing_slots"]


def test_fixed_intent_treats_unrelated_as_expiry_renewal() -> None:
    """기본(고정) Intent는 무관한 문장도 EXPIRY_RENEWAL로 본다."""
    orch = RenewalOrchestrator()
    state = orch.run(
        request_id="req-fixed",
        instruction="오늘 날씨 어때?",
        worker_id="worker-001",
    )
    assert state["intent"] == "EXPIRY_RENEWAL"
    assert state["outcome"] != "OUT_OF_SCOPE"


def test_ocr_documents_persist_then_generate_with_empty_gaps() -> None:
    """서류 업로드 시 OCR 저장 후 부족해도 초안 작성(빈 값)으로 간다."""
    db = InMemoryDb()
    orch = RenewalOrchestrator(lookup=db, store=db)
    state = orch.run(
        request_id="req-2",
        instruction="체류기간 연장 갱신해줘",
        worker_id="worker-001",
        documents=[{"document_type": "passport", "filename": "p.jpg", "hints": {}}],
    )
    assert state["ocr_result"]
    assert db.identity_saves
    assert state["outcome"] == "REVIEW_REQUIRED"
    assert state["scenario"] == "generate"
    assert len(state["generated_documents"]) == 4


def test_filled_slots_generates_docs() -> None:
    """신분·계약 슬롯이 채워지면 문서생성 stub로 간다."""
    orch = RenewalOrchestrator()
    state = orch.run(
        request_id="req-3",
        instruction="체류기간 연장 갱신",
        worker_id="worker-001",
        slots=_filled_renewal_slots(),
    )
    assert state["scenario"] == "generate"
    assert state["outcome"] == "REVIEW_REQUIRED"
    assert len(state["generated_documents"]) == 4
    assert state.get("progress_events")
    assert state.get("phase")
    assert "GENERATE_DRAFTS" in (state.get("case_signals") or [])


def test_ask_worker_passes_through_guide_placeholder() -> None:
    """서류 부족 시 안내문(태정) 자리를 거쳐 근로자 서류 요청으로 간다."""
    orch = RenewalOrchestrator()
    state = orch.run(
        request_id="req-guide",
        instruction="체류기간 연장 갱신",
        worker_id="worker-001",
    )
    assert state["scenario"] == "ask_worker"
    assert any(
        "안내문" in (e.get("message") or "")
        for e in (state.get("progress_events") or [])
    )


def test_supervisor_document_combo_requires_worker_guide_review() -> None:
    """신분 서류가 부족하고 안내문이 없으면 HR 검토로 안전하게 전환한다."""
    orch = RenewalOrchestrator()
    state = orch.run(
        request_id="req-combo",
        instruction="체류기간 연장 갱신",
        worker_id="worker-001",
    )
    assert state["outcome"] == "REVIEW_REQUIRED"
    assert state["status"] == "READY_FOR_REVIEW"
    assert state["worker_request_message"] is None
    assert state["guide_review_required"] is True
    assert state["guide_failure_code"] == "LANGUAGE_ASSISTANT_NOT_CONFIGURED"
    assert state.get("document_validation", {}).get("combo") in {
        "both_missing",
        "passport_only",
        "alien_only",
        "partial_unknown",
    }
    assert "REVIEW_WORKER_GUIDE" in (state.get("case_signals") or [])
