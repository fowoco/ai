# POST /internal/v1/analyses — PLAN / ANALYZE 계약 테스트

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ANALYSES_PATH = "/internal/v1/analyses"


def _plan_body(instruction: str = "응웬반안 체류연장 준비해줘") -> dict:
    return {
        "requestId": "10000000-0000-0000-0000-000000000001",
        "phase": "PLAN",
        "analysisInput": {"instruction": instruction},
    }


def _analyze_body(
    *,
    instruction: str = "응웬반안 체류연장 준비해줘",
    worker_ref: str = "30000000-0000-0000-0000-000000000001",
    requested_field_keys: list[str] | None = None,
    requested_fields: dict[str, str] | None = None,
) -> dict:
    return {
        "requestId": "10000000-0000-0000-0000-000000000001",
        "phase": "ANALYZE",
        "analysisInput": {
            "instruction": instruction,
            "plannedIntent": "EXPIRY_RENEWAL",
            "plannedWorkflowId": "WF-STY-001",
            "requestedFieldKeys": requested_field_keys
            or ["worker_id", "stay_expiry_date"],
            "workers": [
                {
                    "workerRef": worker_ref,
                    "requestedFields": requested_fields
                    or {
                        "worker_id": worker_ref,
                        "stay_expiry_date": "2026-12-31",
                    },
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_plan_returns_context_required() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=_plan_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["requestId"] == "10000000-0000-0000-0000-000000000001"
    assert data["outcome"] == "CONTEXT_REQUIRED"
    assert data["candidates"] == []
    assert data["questions"] == []
    ctx = data["contextRequirement"]
    assert ctx["detectedIntent"] == "EXPIRY_RENEWAL"
    assert ctx["workflowId"] == "WF-STY-001"
    assert ctx["evidence"] is None
    assert ctx["confidenceSource"] == "MODEL"
    assert ctx["bertRoutingScore"] is None
    assert "intentDecisions" not in ctx
    assert ctx["targetDisplayName"] == "응웬반안"
    assert "stay_expiry_date" in ctx["requiredFieldKeys"]
    assert "worker_id" in ctx["requiredFieldKeys"]
    assert data["versions"]["contractVersion"] == "1.0.0"
    assert data["versions"]["workflowCatalogVersion"] == "0.2.0"
    assert data["versions"]["modelProvider"] != "stub"
    assert data["versions"]["modelName"] != "stub"
    assert data["versions"]["modelVersion"] != "stub"
    assert data["versions"]["promptVersion"] == "not-applicable"
    assert "attemptId" not in data


@pytest.mark.asyncio
async def test_analyze_returns_review_required_when_slots_filled() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=_analyze_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "REVIEW_REQUIRED"
    assert data["contextRequirement"] is None
    assert data["questions"] == []
    assert len(data["candidates"]) == 1
    candidate = data["candidates"][0]
    assert candidate["workerRef"] == "30000000-0000-0000-0000-000000000001"
    assert candidate["workflowId"] == "WF-STY-001"
    assert candidate["confidence"] is None
    assert "detectedIntent" not in candidate
    assert "confidenceSource" not in candidate
    assert "bertRoutingScore" not in candidate
    assert candidate["extractedSlots"]["stay_expiry_date"] == "2026-12-31"
    assert candidate["extractedSlots"]["worker_id"] == (
        "30000000-0000-0000-0000-000000000001"
    )
    assert data["providerAttemptCount"] == 0


@pytest.mark.asyncio
async def test_analyze_rejects_request_without_planned_decision() -> None:
    body = _analyze_body()
    body["analysisInput"].pop("plannedIntent")
    body["analysisInput"].pop("plannedWorkflowId")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyze_returns_needs_info_when_db_fields_missing() -> None:
    body = _analyze_body(
        requested_field_keys=["worker_id", "stay_expiry_date"],
        requested_fields={"worker_id": "30000000-0000-0000-0000-000000000001"},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "NEEDS_INFO"
    assert data["candidates"] == []
    assert data["contextRequirement"] is None
    keys = {q["slotKey"] for q in data["questions"]}
    assert "stay_expiry_date" in keys
    assert all("prompt" in q for q in data["questions"])


@pytest.mark.asyncio
async def test_analyze_mvp_uses_first_worker_only() -> None:
    body = _analyze_body()
    body["analysisInput"]["workers"].append(
        {
            "workerRef": "30000000-0000-0000-0000-000000000002",
            "requestedFields": {"stay_expiry_date": "2026-11-30"},
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "REVIEW_REQUIRED"
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["workerRef"] == (
        "30000000-0000-0000-0000-000000000001"
    )


@pytest.mark.asyncio
async def test_plan_fixed_intent_even_for_unrelated_instruction() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            ANALYSES_PATH, json=_plan_body("오늘 날씨 어때?")
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "CONTEXT_REQUIRED"
    assert data["contextRequirement"]["detectedIntent"] == "EXPIRY_RENEWAL"
    assert data["contextRequirement"]["confidence"] == 1.0


@pytest.mark.asyncio
async def test_analyses_endpoint_in_openapi() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/openapi.json")

    paths = resp.json()["paths"]
    assert ANALYSES_PATH in paths
    assert "/api/v1/internal/v1/analyses" not in paths


@pytest.mark.asyncio
async def test_intent_status_exposes_runtime_flags_without_loading_models() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/internal/v1/intent/status")

    assert resp.status_code == 200
    assert resp.json() == {
        "intentModelEnabled": False,
        "axEnabled": False,
        "initialized": True,
        "bertAvailable": False,
        "axAvailable": False,
        "degraded": False,
        "promptVersion": "not-applicable",
    }


@pytest.mark.asyncio
async def test_analyses_rejects_legacy_masked_input() -> None:
    body = {
        "requestId": "10000000-0000-0000-0000-000000000001",
        "phase": "PLAN",
        "maskedInput": {
            "maskedInstruction": "체류연장",
            "workers": [],
        },
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyses_requires_phase() -> None:
    body = {
        "requestId": "10000000-0000-0000-0000-000000000001",
        "analysisInput": {"instruction": "체류연장"},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(ANALYSES_PATH, json=body)

    assert resp.status_code == 422
