"""Document API router composition."""

from fastapi import APIRouter

from .capabilities import router as capabilities_router
from .convert import router as convert_router

router = APIRouter(prefix="/documents")
router.include_router(capabilities_router)
router.include_router(convert_router)

__all__ = ["router"]
