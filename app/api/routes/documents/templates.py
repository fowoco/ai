"""Document template discovery endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_document_editing_service
from app.api.openapi import DOCUMENT_TEMPLATES_TAG
from app.api.schemas.documents import DocumentTemplateResponse
from app.documents.editing import (
    DocumentEditingService,
    DocumentTemplateNotFoundError,
)

from .template_views import template_response

router = APIRouter(tags=[DOCUMENT_TEMPLATES_TAG])


@router.get("/templates", response_model=list[DocumentTemplateResponse])
def list_document_templates(
    editing_service: Annotated[
        DocumentEditingService, Depends(get_document_editing_service)
    ],
) -> list[DocumentTemplateResponse]:
    return [template_response(template) for template in editing_service.templates()]


@router.get("/templates/{template_id}", response_model=DocumentTemplateResponse)
def get_document_template(
    template_id: str,
    editing_service: Annotated[
        DocumentEditingService, Depends(get_document_editing_service)
    ],
) -> DocumentTemplateResponse:
    try:
        return template_response(editing_service.template(template_id))
    except DocumentTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


__all__ = ["router"]
