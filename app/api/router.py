from fastapi import APIRouter

from app.api.routes.analyses import router as analyses_router
from app.api.routes.documents import router as documents_router

api_router = APIRouter()
api_router.include_router(analyses_router)
api_router.include_router(documents_router)
