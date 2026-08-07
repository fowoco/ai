from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from app.ocr.clova_client import ClovaTemplateOcrClient
from app.ocr.service import OcrService
from app.ocr.template_resolver import TemplateResolver


def create_ocr_lifespan(settings: Any) -> Callable[[FastAPI], Any]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not settings.clova_ocr_enabled:
            yield
            return

        http_client = httpx.AsyncClient()
        try:
            clova_client = ClovaTemplateOcrClient(
                invoke_url=settings.clova_ocr_invoke_url,
                secret=settings.clova_ocr_secret,
                timeout_seconds=settings.clova_ocr_timeout_seconds,
                client=http_client,
            )
            app.state.ocr_service = OcrService(
                resolver=TemplateResolver(),
                clova_client=clova_client,
                confidence_threshold=settings.clova_ocr_confidence_threshold,
            )
            yield
        finally:
            if hasattr(app.state, "ocr_service"):
                del app.state.ocr_service
            await http_client.aclose()

    return lifespan
