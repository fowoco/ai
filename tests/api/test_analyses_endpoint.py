"""POST /internal/v1/analyses 엔드포인트 테스트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ANALYSES_PATH = "/internal/v1/analyses"


def _make_request(
    instruction: str = "체류기간 연장 준비해줘",
    *,
    worker_ref: str = "30000000-0000-0000-0000-000000000001",
    display_name: str = "테스트근로자",
    workflow_constraints: list[dict] | None = None,
    stay_expiry_date: str | None = "2026-12-31",
    requested_fields: dict[str, str] | None = None,
) -> dict:
    workers = [
        {
            "workerRef": worker_ref,
            "displayName": display_name,
            "preferredLanguage": "vi",
            "workStatus": "ACTIVE",
            "requestedFields": requested_fields or {},
        }
    ]
    if stay_expiry_date:
        workers[0]["stayExpiryDate"] = stay_expiry_date
    return {
        "requestId": "10000000-0000-0000-0000-000000000001",
        "attemptId": "20000000-0000-0000-0000-000000000001",
        "contractVersion": "1.0.0",
        "requiredKnowledgeVersion": "0.2.0",
        "deadlineMs": 10000,
        "analysisInput": {
            "instruction": instruction,
            "workers": workers,
            "workflowConstraints": workflow_constraints or [],
        },
    }


@pytest.mark.asyncio
async def test_analyses_returns_review_required_for_complete_request() -> None:
    body = _make_request(
        "WRK-012 체류기간 연장 준비 2026-12-31",
        worker_ref="WRK-012",
        display_name="WRK-012",
        workflow_constraints=[
            {"workflowId": "WF-STY-001", "allowedSlotKeys": ["stay_expiry_date", "worker_id"]},
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["requestId"] == "10000000-0000-0000-0000-000000000001"
    assert data["outcome"] in ("REVIEW_REQUIRED", "NEEDS_INFO")
    assert "attemptId" not in data
    assert len(data["candidates"]) == 1
    candidate = data["candidates"][0]
    assert candidate["workerRef"] == "WRK-012"
    assert candidate["workflowId"] == "WF-STY-001"
    assert candidate["confidence"] > 0
    assert "requestedFields" not in candidate
    assert "evidence" not in candidate
    assert "caseSignals" not in candidate
    assert "agentVersion" in data["versions"]


@pytest.mark.asyncio
async def test_analyses_echoes_intent_style_workflow_constraint() -> None:
    """Server 계약 fixture처럼 Intent형 workflowId를 요청하면 응답에도 동일 id를 쓴다."""
    body = _make_request(
        "체류기간 연장 준비해줘",
        workflow_constraints=[
            {
                "workflowId": "EXPIRY_RENEWAL",
                "allowedSlotKeys": [
                    "stay_expiry_date",
                    "contract_end_date",
                    "monthly_wage",
                ],
            }
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"][0]["workflowId"] == "EXPIRY_RENEWAL"
    assert "stay_expiry_date" in data["candidates"][0]["extractedSlots"]


@pytest.mark.asyncio
async def test_analyses_accepts_server_requested_fields_map() -> None:
    body = _make_request(
        "응웬반안 체류연장 준비해줘",
        display_name="응웬반안",
        requested_fields={
            "legal_name": "NGUYEN VAN AN",
            "passport_number": "M12345678",
        },
        workflow_constraints=[
            {
                "workflowId": "EXPIRY_RENEWAL",
                "allowedSlotKeys": [
                    "stay_expiry_date",
                    "contract_end_date",
                    "monthly_wage",
                ],
            }
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    slots = resp.json()["candidates"][0]["extractedSlots"]
    assert slots["worker_id"] == "30000000-0000-0000-0000-000000000001"
    assert "stay_expiry_date" in slots


@pytest.mark.asyncio
async def test_analyses_returns_needs_info_when_slots_missing() -> None:
    body = _make_request(
        "서류 요청해줘",
        stay_expiry_date=None,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "NEEDS_INFO"
    assert len(data["candidates"]) == 1
    assert len(data["candidates"][0]["missingSlots"]) > 0


@pytest.mark.asyncio
async def test_analyses_fixed_intent_treats_unrelated_as_expiry_renewal() -> None:
    """기본 Intent 고정 모드에서는 무관 문장도 EXPIRY_RENEWAL로 본다."""
    body = _make_request("오늘 날씨 어때?")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    candidate = data["candidates"][0]
    assert candidate["confidence"] == 1.0
    assert candidate["workflowId"] in {"EXPIRY_RENEWAL", "WF-STY-001", "WF-CON-001"}
    assert data["outcome"] in {"NEEDS_INFO", "REVIEW_REQUIRED"}


@pytest.mark.asyncio
async def test_analyses_endpoint_in_openapi() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/openapi.json")

    paths = resp.json()["paths"]
    assert ANALYSES_PATH in paths
    assert "/api/v1/internal/v1/analyses" not in paths


@pytest.mark.asyncio
async def test_analyses_multiple_workers() -> None:
    body = {
        "requestId": "10000000-0000-0000-0000-000000000099",
        "attemptId": "20000000-0000-0000-0000-000000000099",
        "contractVersion": "1.0.0",
        "requiredKnowledgeVersion": "0.2.0",
        "deadlineMs": 10000,
        "analysisInput": {
            "instruction": "체류기간 연장 준비",
            "workers": [
                {
                    "workerRef": "w-001",
                    "displayName": "근로자1",
                    "preferredLanguage": "vi",
                    "workStatus": "ACTIVE",
                    "stayExpiryDate": "2026-12-31",
                    "requestedFields": {},
                },
                {
                    "workerRef": "w-002",
                    "displayName": "근로자2",
                    "preferredLanguage": "th",
                    "workStatus": "ACTIVE",
                    "stayExpiryDate": "2026-11-30",
                    "requestedFields": {},
                },
            ],
            "workflowConstraints": [],
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["candidates"]) == 2
    refs = {c["workerRef"] for c in data["candidates"]}
    assert refs == {"w-001", "w-002"}


@pytest.mark.asyncio
async def test_analyses_rejects_legacy_masked_input() -> None:
    body = {
        "requestId": "10000000-0000-0000-0000-000000000001",
        "attemptId": "20000000-0000-0000-0000-000000000001",
        "maskedInput": {
            "maskedInstruction": "체류연장",
            "workers": [],
            "workflowConstraints": [],
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 422
