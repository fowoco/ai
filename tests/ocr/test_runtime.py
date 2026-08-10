from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.ocr import runtime


class FakeHttpClient:
    instances = []

    def __init__(self) -> None:
        self.closed = False
        self.instances.append(self)

    async def aclose(self) -> None:
        self.closed = True


def enabled_settings():
    return SimpleNamespace(
        clova_ocr_enabled=True,
        clova_ocr_invoke_url="https://example.invalid/infer",
        clova_ocr_secret="local-test-secret",
        clova_ocr_timeout_seconds=30.0,
        clova_ocr_confidence_threshold=0.80,
    )


@pytest.mark.asyncio
async def test_enabled_lifespan_uses_no_database_and_closes_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeHttpClient.instances.clear()
    monkeypatch.setattr(runtime.httpx, "AsyncClient", FakeHttpClient)
    app = FastAPI()

    async with runtime.create_ocr_lifespan(enabled_settings())(app):
        assert app.state.ocr_service is not None
        assert len(FakeHttpClient.instances) == 1
        assert FakeHttpClient.instances[0].closed is False

    assert FakeHttpClient.instances[0].closed is True
    assert not hasattr(app.state, "ocr_service")


@pytest.mark.asyncio
async def test_disabled_lifespan_does_not_create_external_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("disabled OCR must not create external resources")

    monkeypatch.setattr(runtime.httpx, "AsyncClient", fail_if_called)
    settings = SimpleNamespace(clova_ocr_enabled=False)
    app = FastAPI()

    async with runtime.create_ocr_lifespan(settings)(app):
        assert not hasattr(app.state, "ocr_service")
