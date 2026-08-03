from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.openapi import OPENAPI_TAGS_METADATA
from app.api.router import api_router
from app.api.routes.analyses import router as analyses_router
from app.api.routes.workflows import router as workflows_router
from app.core.config import get_settings
from app.documents.conversion import ConversionEngineUnavailableError


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="FOWOCO AI Agent Server",
        debug=settings.debug,
        default_response_class=UTF8JSONResponse,
        openapi_tags=OPENAPI_TAGS_METADATA,
    )

    @app.exception_handler(ConversionEngineUnavailableError)
    async def conversion_engine_unavailable(
        request: Request,
        exc: ConversionEngineUnavailableError,
    ) -> JSONResponse:
        del request
        return UTF8JSONResponse(
            status_code=503,
            content={"detail": str(exc)},
        )

    # Server 계약: /internal/v1/* 는 /api/v1 prefix 없음
    app.include_router(analyses_router)
    app.include_router(workflows_router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
