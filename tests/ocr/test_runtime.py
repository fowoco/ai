from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.ocr import runtime


class FakePool:
    instances = []

    def __init__(self, conninfo: str, *, open: bool, min_size: int, max_size: int) -> None:
        self.conninfo = conninfo
        self.open_immediately = open
        self.min_size = min_size
        self.max_size = max_size
        self.opened = False
        self.closed = False
        self.instances.append(self)

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True


class FakeHttpClient:
    instances = []

    def __init__(self) -> None:
        self.closed = False
        self.instances.append(self)

    async def aclose(self) -> None:
        self.closed = True


class FakeRepository:
    instances = []

    def __init__(self, pool: FakePool) -> None:
        self.pool = pool
        self.schema_verified = False
        self.instances.append(self)

    async def verify_schema(self) -> None:
        self.schema_verified = True


def enabled_settings():
    return SimpleNamespace(
        clova_ocr_enabled=True,
        clova_ocr_invoke_url="https://example.invalid/infer",
        clova_ocr_secret="local-test-secret",
        clova_ocr_timeout_seconds=30.0,
        clova_ocr_confidence_threshold=0.80,
        database_url="postgresql://example.invalid/test",
    )


@pytest.mark.asyncio
async def test_enabled_lifespan_opens_verifies_exposes_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakePool.instances.clear()
    FakeHttpClient.instances.clear()
    FakeRepository.instances.clear()
    monkeypatch.setattr(runtime, "AsyncConnectionPool", FakePool)
    monkeypatch.setattr(runtime.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(runtime, "PsycopgWorkerDocumentOcrRepository", FakeRepository)
    app = FastAPI()

    async with runtime.create_ocr_lifespan(enabled_settings())(app):
        assert app.state.ocr_service is not None
        assert FakePool.instances[0].opened is True
        assert FakeRepository.instances[0].schema_verified is True

    assert FakePool.instances[0].closed is True
    assert FakeHttpClient.instances[0].closed is True
    assert not hasattr(app.state, "ocr_service")


@pytest.mark.asyncio
async def test_disabled_lifespan_does_not_create_external_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("disabled OCR must not create external resources")

    monkeypatch.setattr(runtime, "AsyncConnectionPool", fail_if_called)
    monkeypatch.setattr(runtime.httpx, "AsyncClient", fail_if_called)
    settings = SimpleNamespace(clova_ocr_enabled=False)
    app = FastAPI()

    async with runtime.create_ocr_lifespan(settings)(app):
        assert not hasattr(app.state, "ocr_service")
