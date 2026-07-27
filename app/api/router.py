from fastapi import APIRouter

from app.api.routes.coordinator import router as coordinator_router
from app.api.routes.documents import router as documents_router

api_router = APIRouter()
api_router.include_router(coordinator_router)
api_router.include_router(documents_router)
