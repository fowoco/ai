"""POST /internal/v1/analyses 엔드포인트 테스트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ANALYSES_PATH = "/internal/v1/analyses"


def _make_request(
    instruction: str = "체류기간 연장 준비해줘",
    *,
    worker_ref: str = "w-001",
    workflow_constraints: list[dict] | None = None,
    stay_expiry_date: str | None = "2026-12-31",
) -> dict:
    workers = [{"workerRef": worker_ref, "preferredLanguage": "vi", "workStatus": "ACTIVE"}]
    if stay_expiry_date:
        workers[0]["stayExpiryDate"] = stay_expiry_date
    return {
        "requestId": "req-test-001",
        "attemptId": "att-001",
        "contractVersion": "1.0.0",
        "requiredKnowledgeVersion": "0.2.0",
        "deadlineMs": 10000,
        "maskedInput": {
            "maskedInstruction": instruction,
            "workers": workers,
            "workflowConstraints": workflow_constraints or [],
        },
    }


@pytest.mark.asyncio
async def test_analyses_returns_review_required_for_complete_request() -> None:
    body = _make_request(
        "WRK-012 체류기간 연장 준비 2026-12-31",
        worker_ref="WRK-012",
        workflow_constraints=[
            {"workflowId": "WF-STY-001", "allowedSlotKeys": ["stay_expiry_date", "worker_id"]},
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["requestId"] == "req-test-001"
    assert data["outcome"] in ("REVIEW_REQUIRED", "NEEDS_INFO")
    assert len(data["candidates"]) == 1
    candidate = data["candidates"][0]
    assert candidate["workerRef"] == "WRK-012"
    assert candidate["workflowId"] == "WF-STY-001"
    assert candidate["confidence"] > 0
    assert "agentVersion" in data["versions"]


@pytest.mark.asyncio
async def test_analyses_echoes_intent_style_workflow_constraint() -> None:
    """Server 계약 fixture처럼 Intent형 workflowId를 요청하면 응답에도 동일 id를 쓴다."""
    body = _make_request(
        "체류기간 연장 준비해줘",
        worker_ref="30000000-0000-0000-0000-000000000001",
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
async def test_analyses_handles_unknown_intent() -> None:
    body = _make_request("오늘 날씨 어때?")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "NEEDS_INFO"
    assert data["candidates"][0]["confidence"] < 0.65


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
        "requestId": "req-multi",
        "attemptId": "att-002",
        "contractVersion": "1.0.0",
        "requiredKnowledgeVersion": "0.2.0",
        "deadlineMs": 10000,
        "maskedInput": {
            "maskedInstruction": "체류기간 연장 준비",
            "workers": [
                {
                    "workerRef": "w-001",
                    "preferredLanguage": "vi",
                    "workStatus": "ACTIVE",
                    "stayExpiryDate": "2026-12-31",
                },
                {
                    "workerRef": "w-002",
                    "preferredLanguage": "th",
                    "workStatus": "ACTIVE",
                    "stayExpiryDate": "2026-11-30",
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
