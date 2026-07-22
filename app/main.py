from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings


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
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
