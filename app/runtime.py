from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_intent_agent
from app.ocr.runtime import create_ocr_lifespan

logger = logging.getLogger(__name__)


# OCR 자원과 선택적 Intent 모델 warmup을 하나의 FastAPI lifespan으로 조립한다.
def create_app_lifespan(settings: Any) -> Callable[[FastAPI], Any]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with create_ocr_lifespan(settings)(app):
            if settings.intent_model_enabled and settings.intent_warmup_on_start:
                intent_agent = get_intent_agent()
                try:
                    await run_in_threadpool(intent_agent.warmup)
                except Exception as exc:
                    app.state.intent_warmup_error = str(exc)
                    logger.exception("Intent model warmup failed")
                    if settings.intent_warmup_required:
                        raise
                else:
                    app.state.intent_warmup_completed = True
            yield

    return lifespan
