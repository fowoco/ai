from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from app.ocr.clova_client import ClovaTemplateOcrClient
from app.ocr.repository import PsycopgWorkerDocumentOcrRepository
from app.ocr.service import OcrService
from app.ocr.template_resolver import TemplateResolver


def create_ocr_lifespan(settings: Any) -> Callable[[FastAPI], Any]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not settings.clova_ocr_enabled:
            yield
            return

        pool = AsyncConnectionPool(
            settings.database_url,
            open=False,
            min_size=1,
            max_size=5,
        )
        http_client = httpx.AsyncClient()
        try:
            await pool.open()
            repository = PsycopgWorkerDocumentOcrRepository(pool)
            await repository.verify_schema()
            clova_client = ClovaTemplateOcrClient(
                invoke_url=settings.clova_ocr_invoke_url,
                secret=settings.clova_ocr_secret,
                timeout_seconds=settings.clova_ocr_timeout_seconds,
                client=http_client,
            )
            app.state.ocr_service = OcrService(
                resolver=TemplateResolver(),
                clova_client=clova_client,
                repository=repository,
                confidence_threshold=settings.clova_ocr_confidence_threshold,
                clock=lambda: datetime.now(UTC),
            )
            yield
        finally:
            if hasattr(app.state, "ocr_service"):
                del app.state.ocr_service
            await http_client.aclose()
            await pool.close()

    return lifespan
