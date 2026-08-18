"""Language/OCR 어댑터·태스크 재개·문서생성 훅 테스트."""

from pathlib import Path

from app.agents.workflow_graph import LanguageNodeAdapter, OcrNodeAdapter, RenewalOrchestrator
from app.agents.workflow_graph.adapters import normalize_language_output, normalize_ocr_output
from app.agents.workflow_graph.document_field_map import values_for_template
from app.agents.workflow_graph.nodes.document_generator import (
    EditingServiceDocumentGenerator,
    StubDocumentGenerator,
)
from app.agents.workflow_graph.nodes.language_stub import CONTRACT_SLOTS
from app.agents.workflow_graph.state import IDENTITY_SLOTS, empty_renewal_state
from app.agents.workflow_graph.task_store import InMemoryTaskStore
from app.db.memory import InMemoryDb


class _FakeLanguage:
    """동료 Language 엔진 흉내 (별도 스키마)."""

    def run(self, payload: dict) -> dict:
        """camelCase 결과를 반환한다."""
        del payload
        return {
            "intent": "EXPIRY_RENEWAL",
            "workflowId": "WF-STY-001",
            "confidence": 0.9,
            "extractedSlots": {"worker_id": "WRK-9"},
            "missingSlots": ["wage"],
            "guideMessage": "임금을 입력해 주세요",
        }


class _FakeOcr:
    """동료 OCR 엔진 흉내 (별도 스키마)."""

    def run(self, payload: dict) -> dict:
        """fields 키로 OCR 결과를 반환한다."""
        del payload
        return {"fields": {"passport_number": "P-FAKE", "full_name": "FAKE"}}


def test_normalize_language_accepts_teammate_aliases() -> None:
    """동료 스키마 alias를 Shared State 키로 정규화한다."""
    out = normalize_language_output(
        {"Intent": "EXPIRY_RENEWAL", "workflowId": "WF-X", "extractedSlots": {"a": 1}},
        base_slots={"b": 2},
    )
    assert out["intent"] == "EXPIRY_RENEWAL"
    assert out["workflow_id"] == "WF-X"
    assert out["slots"] == {"b": 2, "a": 1}


def test_language_adapter_wraps_external_engine() -> None:
    """LanguageNodeAdapter가 동료 엔진을 LanguageNode로 노출한다."""
    adapter = LanguageNodeAdapter(_FakeLanguage())
    state = empty_renewal_state(
        task_id="t1", request_id="r1", instruction="체류 갱신"
    )
    update = adapter(state)
    assert update["intent"] == "EXPIRY_RENEWAL"
    assert update["workflow_id"] == "WF-STY-001"
    assert update["slots"]["worker_id"] == "WRK-9"
    assert update["guide_message"]


def test_renewal_overrides_language_workflow_with_server_task_workflow() -> None:
    """외부 Language Node도 이미 확정된 Server Task Workflow를 바꾸지 못한다."""
    orch = RenewalOrchestrator(language_node=LanguageNodeAdapter(_FakeLanguage()))
    state = orch.run(
        request_id="r-task-workflow",
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


def test_ocr_adapter_wraps_external_engine() -> None:
    """OcrNodeAdapter가 동료 엔진을 OcrNode로 노출한다."""
    adapter = OcrNodeAdapter(_FakeOcr())
    state = empty_renewal_state(
        task_id="t1",
        request_id="r1",
        instruction="x",
        documents=[{"document_type": "passport"}],
    )
    state["missing_slots"] = ["passport_number", "wage"]
    update = adapter(state)
    assert update["ocr_result"]["passport_number"] == "P-FAKE"
    assert "passport_number" not in update["missing_slots"]
    assert "wage" in update["missing_slots"]


# CLOVA alias·성명 합성도 adapter 경로에서 정규화
def test_normalize_ocr_output_maps_clova_aliases() -> None:
    out = normalize_ocr_output(
        {
            "fields": {
                "stay_expiration_date": "2026-09-30",
                "legal_name": "NGUYEN VAN AN",
                "surname": "IGNORED",
                "given_names": "WHEN_LEGAL_PRESENT",
            }
        },
        base_slots={"worker_id": "w1"},
        base_missing=["stay_expiry_date", "full_name", "passport_number"],
    )
    assert out["slots"]["stay_expiry_date"] == "2026-09-30"
    assert out["slots"]["full_name"] == "NGUYEN VAN AN"
    assert out["ocr_result"]["stay_expiry_date"] == "2026-09-30"
    assert "stay_expiry_date" not in out["missing_slots"]
    assert "full_name" not in out["missing_slots"]
    assert "passport_number" in out["missing_slots"]


def test_normalize_ocr_output_consumes_stateless_response_fields_only() -> None:
    """Stateless OCR 메타데이터를 제외하고 fields만 갱신 슬롯으로 사용한다."""
    out = normalize_ocr_output(
        {
            "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "worker_document_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "ocr_status": "REVIEW_REQUIRED",
            "matched_template_id": 43019,
            "document_side": None,
            "fields": {
                "passport_number": "M12345678",
                "surname": "NGUYEN",
                "given_names": "VAN AN",
                "date_of_birth": "1995-03-01",
            },
            "field_confidences": {
                "passport_number": 0.98,
                "surname": 0.94,
            },
            "review_reasons": ["low_confidence:given_names"],
        },
        base_slots={},
        base_missing=["passport_number", "full_name"],
    )

    assert out["ocr_result"] == {
        "passport_number": "M12345678",
        "full_name": "NGUYEN VAN AN",
        "date_of_birth": "1995-03-01",
    }
    assert out["slots"] == out["ocr_result"]
    assert out["missing_slots"] == []
    assert "field_confidences" not in out["slots"]
    assert "matched_template_id" not in out["slots"]


def test_task_resume_merges_slots_across_runs() -> None:
    """task_id로 재호출하면 이전 slots에 새 slots를 합친다."""
    store = InMemoryTaskStore()
    orch = RenewalOrchestrator(task_store=store, lookup=InMemoryDb(), store=InMemoryDb())
    first = orch.run(
        request_id="r1",
        instruction="체류기간 연장 갱신",
        worker_id="worker-001",
    )
    assert first["outcome"] == "REVIEW_REQUIRED"
    assert first["guide_review_required"] is True
    assert first["worker_request_message"] is None
    task_id = first["task_id"]

    identity = {k: f"v-{k}" for k in IDENTITY_SLOTS}
    second = orch.run(
        request_id="r2",
        instruction="체류기간 연장 갱신",
        task_id=task_id,
        worker_id="worker-001",
        slots=identity,
        documents=[{"document_type": "passport", "filename": "p.jpg"}],
    )
    assert second["task_id"] == task_id
    assert second["ocr_result"]
    # OCR 1회 후 부족해도 초안 작성(빈 값)으로 진행
    assert second["outcome"] == "REVIEW_REQUIRED"
    assert second["scenario"] == "generate"
    assert len(second["generated_documents"]) == 4

    contract = {
        **{k: f"c-{k}" for k in CONTRACT_SLOTS},
        "due_at": "2026-11-30",
    }
    third = orch.run(
        request_id="r3",
        instruction="체류기간 연장 갱신",
        task_id=task_id,
        slots=contract,
    )
    assert third["outcome"] == "REVIEW_REQUIRED"
    assert third["generated_documents"]


def test_stub_document_generator_lists_required_templates() -> None:
    """stub 문서생성기는 필수 초안 4종 메타를 낸다."""
    state = empty_renewal_state(task_id="t", request_id="r", instruction="x")
    docs = StubDocumentGenerator()(state)
    assert len(docs) == 4
    assert all(d["status"] == "stub" for d in docs)
    assert all("values" in d for d in docs)
    assert all(
        d["values"] == values_for_template(d["template_id"], state) for d in docs
    )


def test_editing_service_document_generator_writes_files(
    tmp_path: Path,
) -> None:
    """실 생성기가 필수 4종 파일을 생성하고 generated 상태를 반환한다."""
    gen = EditingServiceDocumentGenerator(output_dir=tmp_path)
    state = empty_renewal_state(
        task_id="t",
        request_id="r",
        instruction="x",
        slots={"full_name": "Hong", "date_of_birth": "1990-01-01"},
    )
    docs = gen(state)
    assert len(docs) == 4
    assert all(d["status"] == "generated" for d in docs)
    assert all(Path(d["path"]).is_file() for d in docs)
    assert all(Path(d["path"]).stat().st_size > 0 for d in docs)
    assert all("mapped_fields" in d for d in docs)
    assert all(
        d["values"] == values_for_template(d["template_id"], state) for d in docs
    )
