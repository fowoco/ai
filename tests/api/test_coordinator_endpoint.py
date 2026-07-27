"""Coordinator 전이 계약·Internal API 테스트."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.coordinator.transitions import (
    TaskStatus,
    TransitionError,
    can_transition,
    require_transition,
)
from app.main import app


@pytest.fixture
def _reset_coordinator():
    from app.api.dependencies import get_coordinator_service

    get_coordinator_service.cache_clear()
    yield
    get_coordinator_service.cache_clear()


def test_transition_contract_allows_draft_to_ready() -> None:
    assert can_transition(TaskStatus.DRAFT, TaskStatus.READY_FOR_REVIEW) is True
    require_transition(TaskStatus.DRAFT, TaskStatus.READY_FOR_REVIEW)


def test_transition_contract_blocks_draft_to_completed() -> None:
    assert can_transition(TaskStatus.DRAFT, TaskStatus.COMPLETED) is False
    with pytest.raises(TransitionError):
        require_transition(TaskStatus.DRAFT, TaskStatus.COMPLETED)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_reset_coordinator")
async def test_propose_split_does_not_persist() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        proposed = await client.post(
            "/api/v1/internal/coordinator/propose-split",
            json={
                "source_request_id": "REQ-COMP-001",
                "cards": [
                    {
                        "workflow_id": "WF-STY-001",
                        "title": "체류기간 연장 준비",
                        "slots": {"worker_id": "WRK-012"},
                    },
                    {
                        "workflow_id": "WF-DOC-001",
                        "title": "여권 사본 요청",
                        "slots": {"worker_id": "WRK-012"},
                    },
                ],
            },
        )
        listed = await client.get("/api/v1/internal/coordinator/work-items")

    assert proposed.status_code == 200
    cards = proposed.json()
    assert len(cards) == 2
    assert cards[0]["group_id"] == cards[1]["group_id"]
    assert cards[0]["worker_id"] == "WRK-012"
    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("_reset_coordinator")
async def test_validate_transition_endpoint() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        ok = await client.post(
            "/api/v1/internal/coordinator/validate-transition",
            json={"current": "DRAFT", "target": "READY_FOR_REVIEW"},
        )
        bad = await client.post(
            "/api/v1/internal/coordinator/validate-transition",
            json={"current": "DRAFT", "target": "COMPLETED"},
        )

    assert ok.status_code == 200
    assert ok.json()["allowed"] is True
    assert "READY_FOR_REVIEW" in ok.json()["allowed_targets"]
    assert bad.status_code == 200
    assert bad.json()["allowed"] is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("_reset_coordinator")
async def test_prototype_work_item_lifecycle() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create = await client.post(
            "/api/v1/internal/coordinator/work-items",
            json={"workflow_id": "WF-DOC-001", "title": "서류 요청"},
        )
        card_id = create.json()["id"]

        for target in ["READY_FOR_REVIEW", "APPROVED", "IN_PROGRESS", "COMPLETED"]:
            r = await client.post(
                f"/api/v1/internal/coordinator/work-items/{card_id}/transition",
                json={"target": target},
            )
            assert r.status_code == 200

        final = await client.get(f"/api/v1/internal/coordinator/work-items/{card_id}")
        assert final.json()["status"] == "COMPLETED"

        no_more = await client.post(
            f"/api/v1/internal/coordinator/work-items/{card_id}/transition",
            json={"target": "DRAFT"},
        )
        assert no_more.status_code == 409


@pytest.mark.asyncio
@pytest.mark.usefixtures("_reset_coordinator")
async def test_prototype_invalid_transition_returns_409() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create = await client.post(
            "/api/v1/internal/coordinator/work-items",
            json={"workflow_id": "WF-DOC-001", "title": "서류 요청"},
        )
        card_id = create.json()["id"]
        response = await client.post(
            f"/api/v1/internal/coordinator/work-items/{card_id}/transition",
            json={"target": "COMPLETED"},
        )

    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.usefixtures("_reset_coordinator")
async def test_create_composite_persists_for_local_simulation() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/internal/coordinator/work-items/composite",
            json={
                "cards": [
                    {"workflow_id": "WF-STY-001", "title": "A", "worker_id": "WRK-1"},
                    {"workflow_id": "WF-DOC-001", "title": "B", "worker_id": "WRK-1"},
                ],
            },
        )
        listed = await client.get(
            "/api/v1/internal/coordinator/work-items?worker_id=WRK-1"
        )

    assert response.status_code == 201
    assert len(response.json()) == 2
    assert len(listed.json()) == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("_reset_coordinator")
async def test_coordinator_routes_in_openapi() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/openapi.json")

    paths = response.json()["paths"]
    assert "/api/v1/internal/coordinator/propose-split" in paths
    assert "/api/v1/internal/coordinator/validate-transition" in paths
    assert "/api/v1/internal/coordinator/work-items" in paths
    assert "/api/v1/tasks" not in paths
