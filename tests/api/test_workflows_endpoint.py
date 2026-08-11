"""POST /internal/v1/workflows/renewal/run 엔드포인트 테스트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

RENEWAL_PATH = "/internal/v1/workflows/renewal/run"


@pytest.fixture
async def client():
    """테스트용 ASGI 클라이언트."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_renewal_run_waiting_worker(client: AsyncClient) -> None:
    """재갱신 요청이 WAITING_WORKER 응답을 돌려준다."""
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
    assert data["outcome"] == "WAITING_WORKER"
    assert data["scenario"] == "ask_worker"
    assert data["taskId"]
    assert data["workerRequestMessage"]


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
