"""재갱신 공개 워크플로 동작 고정 테스트."""

from typing import Any

from app.agents.workflow_graph import RenewalOrchestrator
from app.agents.workflow_graph.nodes.document_generator import StubDocumentGenerator
from app.agents.workflow_graph.nodes.language_stub import CONTRACT_SLOTS
from app.agents.workflow_graph.state import IDENTITY_SLOTS, RenewalState
from app.db.memory import InMemoryDb

PUBLIC_KEYS = (
    "intent",
    "workflow_id",
    "confidence",
    "status",
    "outcome",
    "scenario",
    "phase",
    "step",
    "slots",
    "missing_slots",
    "guide_message",
    "worker_request_message",
    "language_assistant",
    "ocr_result",
    "evidence",
    "document_validation",
    "case_signals",
    "progress_events",
    "supervisor_reason",
    "supervisor_source",
    "active_subgraph",
    "errors",
)


def public_result(state: RenewalState) -> dict[str, object]:
    result = {key: state.get(key) for key in PUBLIC_KEYS}
    result["generated_documents"] = [
        {key: value for key, value in item.items() if key != "path"}
        for item in state.get("generated_documents", [])
    ]
    return result


def _filled_renewal_slots() -> dict[str, str]:
    slots = {
        "worker_id": "WRK-001",
        "stay_expiry_date": "2026-12-31",
    }
    for key in IDENTITY_SLOTS:
        slots[key] = f"stub-{key}"
    for key in CONTRACT_SLOTS:
        slots[key] = f"stub-{key}"
    return slots


def test_ask_worker_without_language_service_requires_review_without_internal_keys() -> None:
    result = public_result(
        RenewalOrchestrator().run(
            request_id="character-worker",
            instruction="체류기간 연장 갱신",
            worker_id="worker-001",
        )
    )

    assert result["status"] == "READY_FOR_REVIEW"
    assert result["outcome"] == "REVIEW_REQUIRED"
    assert result["scenario"] == "ask_worker"
    assert result["language_assistant"] is None
    assert result["guide_message"] is None
    assert result["worker_request_message"] is None
    assert result["case_signals"] == ["REVIEW_WORKER_GUIDE"]
    assert result["document_validation"] is not None
    assert result["document_validation"]["combo"] == "both_missing"
    assert [event["subgraph"] for event in result["progress_events"]] == [
        "main",
        "language",
        "language",
        "supervisor",
        "language",
        "main",
    ]


def test_ask_hr_preserves_needs_info_without_generated_documents() -> None:
    identity = {key: f"stub-{key}" for key in IDENTITY_SLOTS}
    result = public_result(
        RenewalOrchestrator().run(
            request_id="character-hr",
            instruction="체류기간 연장 갱신",
            worker_id="worker-001",
            slots={
                "worker_id": "WRK-001",
                "stay_expiry_date": "2026-12-31",
                **identity,
            },
        )
    )

    assert result["status"] == "NEEDS_INFO"
    assert result["outcome"] == "NEEDS_INFO"
    assert result["scenario"] == "ask_hr"
    assert result["generated_documents"] == []


def test_ocr_persists_identity_then_generates_four_review_drafts() -> None:
    db = InMemoryDb()

    def document_generator(state: RenewalState) -> list[dict[str, Any]]:
        assert db.identity_saves
        return StubDocumentGenerator()(state)

    result = public_result(
        RenewalOrchestrator(
            lookup=db,
            store=db,
            document_generator=document_generator,
        ).run(
            request_id="character-ocr",
            instruction="체류기간 연장 갱신",
            worker_id="worker-001",
            documents=[{"document_type": "passport", "filename": "p.jpg", "hints": {}}],
        )
    )

    assert len(db.identity_saves) == 1
    assert db.identity_saves[0]["worker_id"] == "worker-001"
    assert db.identity_saves[0]["task_id"]
    assert db.identity_saves[0]["slots"] == {
        "passport_number": "P-STUB-0001",
        "nationality": "VN",
        "full_name": "STUB WORKER",
    }
    assert result["ocr_result"] == {
        "passport_number": "P-STUB-0001",
        "nationality": "VN",
        "full_name": "STUB WORKER",
    }
    assert result["status"] == "READY_FOR_REVIEW"
    assert result["outcome"] == "REVIEW_REQUIRED"
    assert result["scenario"] == "generate"
    assert len(result["generated_documents"]) == 4


def test_generate_preserves_registered_template_ids_and_review_required() -> None:
    result = public_result(
        RenewalOrchestrator().run(
            request_id="character-generate",
            instruction="체류기간 연장 갱신",
            worker_id="worker-001",
            slots=_filled_renewal_slots(),
        )
    )

    assert tuple(document["template_id"] for document in result["generated_documents"]) == (
        "standard_labor_contract_v6",
        "employment_extension_application_v12_3",
        "immigration_integrated_application_v34",
        "identity_guaranty_v129",
    )
    assert result["status"] == "READY_FOR_REVIEW"
    assert result["outcome"] == "REVIEW_REQUIRED"
    assert result["scenario"] == "generate"
    assert result["case_signals"] == ["GENERATE_DRAFTS", "READY_FOR_REVIEW"]
    assert [
        event["message"]
        for event in result["progress_events"]
        if event.get("subgraph") == "document"
    ] == ["Document 서브그래프: 초안 생성"]


def test_out_of_scope_cancels_without_executing_ocr_or_document_tools() -> None:
    def out_of_scope_language(state: RenewalState) -> dict[str, Any]:
        return {
            "intent": "OUT_OF_SCOPE",
            "workflow_id": "",
            "confidence": 1.0,
            "slots": state["slots"],
            "missing_slots": [],
            "guide_message": "요청이 지원 범위를 벗어났습니다. 다시 시작해 주세요.",
            "scenario": "out_of_scope",
            "status": "CANCELLED",
            "outcome": "OUT_OF_SCOPE",
        }

    def unexpected_tool(state: RenewalState) -> dict[str, Any]:
        del state
        raise AssertionError("out_of_scope route must not execute a tool")

    result = public_result(
        RenewalOrchestrator(
            language_node=out_of_scope_language,
            ocr_node=unexpected_tool,
            document_generator=unexpected_tool,
        ).run(
            request_id="character-out-of-scope",
            instruction="지원하지 않는 요청",
            worker_id="worker-001",
        )
    )

    assert result["status"] == "CANCELLED"
    assert result["outcome"] == "OUT_OF_SCOPE"
    assert result["scenario"] == "out_of_scope"
    assert result["generated_documents"] == []
