"""POST /internal/v1/workflows/renewal/run 엔드포인트 테스트."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.workflow_graph import RenewalOrchestrator
from app.agents.workflow_graph.nodes.document_generator import (
    HwpxDocumentGenerator,
)
from app.agents.workflow_graph.nodes.language_stub import CONTRACT_SLOTS
from app.agents.workflow_graph.state import IDENTITY_SLOTS, RenewalState
from app.agents.workflow_graph.task_store import InMemoryTaskStore
from app.api.dependencies import get_renewal_orchestrator
from app.db.memory import InMemoryDb
from app.main import app

RENEWAL_PATH = "/internal/v1/workflows/renewal/run"
EXPIRED_STAY_CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "expired_stay_exception_cases.json")
    .read_text(encoding="utf-8")
)


@pytest.fixture
async def client():
    """테스트용 ASGI 클라이언트."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_renewal_run_blocks_worker_delivery_without_language_service(
    client: AsyncClient,
) -> None:
    """안내 생성기가 없으면 임시 문장을 발송하지 않고 HR 검토로 돌린다."""
    payload = {
        "requestId": "req-renewal-001",
        "instruction": "외국인 근로자 체류기간 연장 갱신 어떻게 해?",
        "workerId": "worker-001",
        "companyId": "company-001",
    }
    res = await client.post(RENEWAL_PATH, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["requestId"] == "req-renewal-001"
    assert data["intent"] == "EXPIRY_RENEWAL"
    assert data["outcome"] == "REVIEW_REQUIRED"
    assert data["status"] == "READY_FOR_REVIEW"
    assert data["scenario"] == "ask_worker"
    assert data["taskId"]
    assert data["workerRequestMessage"] is None
    assert data["guideReviewRequired"] is True
    assert data["guideFailureCode"] == "LANGUAGE_ASSISTANT_NOT_CONFIGURED"
    assert data["caseSignals"] == ["REVIEW_WORKER_GUIDE"]


@pytest.mark.asyncio
async def test_renewal_run_with_ocr_upload(client: AsyncClient) -> None:
    """서류 업로드 요청이 OCR 결과를 포함한다."""
    payload = {
        "requestId": "req-renewal-002",
        "instruction": "체류기간 연장 갱신",
        "workerId": "worker-001",
        "documents": [
            {"documentType": "passport", "filename": "pass.jpg"},
            {"documentType": "alien_registration", "filename": "arc.jpg"},
        ],
    }
    res = await client.post(RENEWAL_PATH, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ocrResult"]
    assert "passport_number" in data["ocrResult"]
    assert all("values" in document for document in data["generatedDocuments"])
    immigration = next(
        document
        for document in data["generatedDocuments"]
        if document["template_id"] == "immigration_integrated_application_v34"
    )
    assert immigration["values"]["passport_number"] == data["ocrResult"]["passport_number"]


@pytest.mark.asyncio
async def test_renewal_run_uses_document_fields_not_stub(client: AsyncClient) -> None:
    """documents.fields에 CLOVA 값이 있으면 stub 대신 실제 필드를 쓴다."""
    payload = {
        "requestId": "req-renewal-fields",
        "instruction": "체류기간 연장 갱신",
        "workerId": "worker-001",
        "documents": [
            {
                "documentType": "passport",
                "filename": "pass.jpg",
                "fields": {
                    "passport_number": "P-REAL-99",
                    "surname": "NGUYEN",
                    "given_names": "VAN AN",
                },
            }
        ],
    }
    res = await client.post(RENEWAL_PATH, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ocrResult"]["passport_number"] == "P-REAL-99"
    assert data["slots"]["full_name"] == "NGUYEN VAN AN"


@pytest.mark.asyncio
async def test_renewal_run_accepts_prefilled_ocr_result(client: AsyncClient) -> None:
    """Server가 DB에서 읽은 ocrResult 스냅샷을 요청에 실을 수 있다."""
    payload = {
        "requestId": "req-renewal-ocr-snap",
        "instruction": "체류기간 연장 갱신",
        "workerId": "worker-001",
        "ocrResult": {
            "alien_registration_number": "900315-5123456",
            "stay_expiration_date": "2026-12-31",
        },
    }
    res = await client.post(RENEWAL_PATH, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ocrResult"]["alien_registration_number"] == "900315-5123456"
    assert data["slots"]["stay_expiry_date"] == "2026-12-31"


@pytest.mark.asyncio
async def test_renewal_run_resumes_same_task_from_approved_ocr_to_generated_drafts(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """Server가 승인 OCR State를 재전달하면 동일 Task에서 실제 초안을 생성한다."""

    def successful_guide(state: RenewalState) -> dict[str, object]:
        del state
        return {
            "guide_message": "여권과 외국인등록증 사본을 제출해 주세요.",
            "worker_request_message": (
                "여권과 외국인등록증 사본을 제출해 주세요.\n\n"
                "Vui lòng nộp bản sao hộ chiếu và thẻ đăng ký người nước ngoài."
            ),
            "guide_review_required": False,
            "guide_failure_code": None,
        }

    db = InMemoryDb()
    orchestrator = RenewalOrchestrator(
        guide_node=successful_guide,
        lookup=db,
        store=db,
        document_generator=HwpxDocumentGenerator(output_dir=tmp_path),
        task_store=InMemoryTaskStore(),
    )
    app.dependency_overrides[get_renewal_orchestrator] = lambda: orchestrator
    try:
        first = await client.post(
            RENEWAL_PATH,
            json={
                "requestId": "req-renewal-resume-1",
                "instruction": "응웬반A의 체류기간 연장 준비",
                "workerId": "worker-qa-001",
            },
        )
        assert first.status_code == 200
        first_data = first.json()
        assert first_data["outcome"] == "WAITING_WORKER"
        assert first_data["workerRequestMessage"]
        assert first_data["guideReviewRequired"] is False
        assert first_data["guideFailureCode"] is None

        contract_slots = {key: f"qa-{key}" for key in CONTRACT_SLOTS}
        contract_slots.update(
            {
                "worker_id": "worker-qa-001",
                "stay_expiry_date": "2026-12-31",
            }
        )
        ocr_result = {
            "passport_number": "M12345678",
            "alien_registration_number": "900315-5123456",
            "nationality": "VN",
            "full_name": "NGUYEN VAN A",
            "date_of_birth": "1990-03-15",
        }
        assert set(ocr_result) == set(IDENTITY_SLOTS)
        second = await client.post(
            RENEWAL_PATH,
            json={
                "requestId": "req-renewal-resume-2",
                "instruction": "응웬반A의 체류기간 연장 준비",
                "workerId": "worker-qa-001",
                "taskId": first_data["taskId"],
                "slots": contract_slots,
                "ocrResult": ocr_result,
            },
        )
    finally:
        app.dependency_overrides.pop(get_renewal_orchestrator, None)

    assert second.status_code == 200
    data = second.json()
    assert data["taskId"] == first_data["taskId"]
    assert data["outcome"] == "REVIEW_REQUIRED"
    assert data["status"] == "READY_FOR_REVIEW"
    assert data["scenario"] == "generate"
    assert data["ocrResult"] == ocr_result
    assert data["slots"]["passport_number"] == "M12345678"
    assert len(data["generatedDocuments"]) == 4
    assert all(
        document["status"] == "generated"
        for document in data["generatedDocuments"]
    )
    assert all(document["format"] == "hwpx" for document in data["generatedDocuments"])
    immigration = next(
        document
        for document in data["generatedDocuments"]
        if document["template_id"] == "immigration_integrated_application_v34"
    )
    assert immigration["values"]["passport_number"] == "M12345678"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", EXPIRED_STAY_CASES, ids=lambda case: case["caseId"])
async def test_expired_stay_exception_follows_knowledge_golden_cases(
    client: AsyncClient,
    case: dict[str, object],
) -> None:
    """Knowledge #53의 E2E-012~016 상태별 다음 행동을 회귀 검증한다."""
    payload = {
        "requestId": f"req-{case['caseId']}",
        "taskId": f"task-{case['caseId']}",
        "instruction": "기록상 체류기간이 지나 상태 확인이 필요합니다.",
        "workerId": "worker-001",
        "variant": "EXPIRED_STAY_EXCEPTION",
        "stayVerificationStatus": case["status"],
        "slots": {
            "worker_id": "worker-001",
            "stay_expiry_date": "2026-08-10",
            "stay_verification_status": case["status"],
        },
    }

    response = await client.post(RENEWAL_PATH, json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "EXPIRY_RENEWAL"
    assert data["workflowId"] == "WF-STY-EXC-001"
    assert data["variant"] == "EXPIRED_STAY_EXCEPTION"
    assert data["nextAction"] == case["nextAction"]
    assert data["legalConclusion"] is None
    assert data["suggestedWorkflowIds"] == case["suggestedWorkflowIds"]
    assert data["questions"]
    assert data["generatedDocuments"] == []
    assert data["workerRequestMessage"] is None


@pytest.mark.asyncio
async def test_expired_stay_never_suggests_employment_change_before_confirmation(
    client: AsyncClient,
) -> None:
    """기한 경과·미신청만으로 고용변동 Workflow를 제안하지 않는다."""
    response = await client.post(
        RENEWAL_PATH,
        json={
            "requestId": "req-no-auto-employment-change",
            "instruction": "연장 신청을 안 했으니 자동으로 퇴사 처리해줘",
            "workerId": "worker-001",
            "variant": "EXPIRED_STAY_EXCEPTION",
            "stayVerificationStatus": "NOT_APPLIED",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["legalConclusion"] is None
    assert "WF-CHG-001" not in data["suggestedWorkflowIds"]
    assert data["nextAction"] == "REQUEST_HR_STATUS_CONFIRMATION"
