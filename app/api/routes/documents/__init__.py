"""Document API router composition."""

from fastapi import APIRouter

from .capabilities import router as capabilities_router
from .convert import router as convert_router
from .edit import router as edit_router
from .generate import router as generate_router
from .inspect import router as inspect_router
from .templates import router as templates_router

router = APIRouter(prefix="/documents")
router.include_router(capabilities_router)
router.include_router(convert_router)
router.include_router(templates_router)
router.include_router(inspect_router)
router.include_router(edit_router)
router.include_router(generate_router)

__all__ = ["router"]
