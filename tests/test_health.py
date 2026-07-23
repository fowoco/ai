import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_app_boots() -> None:
    assert app.title == "fowoco-ai"
    # 애플리케이션 부팅과 OpenAPI 스키마 생성을 함께 확인한다.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "openapi" in response.json()


@pytest.mark.asyncio
async def test_document_capabilities() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/documents/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["editable_formats"] == ["hwp", "hwpx"]
    assert len(payload["templates"]) == 8
    assert payload["conversions"] == [
        {"source_format": "hwpx", "target_format": "xml"},
        {"source_format": "xml", "target_format": "hwpx"},
    ]
