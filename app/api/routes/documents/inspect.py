"""Uploaded document format and template inspection."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.dependencies import get_document_editing_service
from app.api.openapi import DOCUMENT_INSPECTION_TAG
from app.api.schemas.documents import DocumentInspectionResponse
from app.core.config import Settings, get_settings
from app.documents.editing import DocumentEditingService

from .uploads import detect_uploaded_format, save_upload, validate_filename

router = APIRouter(tags=[DOCUMENT_INSPECTION_TAG])


@router.post("/inspect", response_model=DocumentInspectionResponse)
def inspect_document(
    file: Annotated[UploadFile, File(description="Document to inspect")],
    editing_service: Annotated[
        DocumentEditingService, Depends(get_document_editing_service)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentInspectionResponse:
    temporary_directory = Path(tempfile.mkdtemp(prefix="fowoco-inspect-"))
    source_path = temporary_directory / "input.upload"
    try:
        save_upload(
            file,
            source_path,
            max_bytes=settings.document_upload_max_bytes,
        )
        source_format = detect_uploaded_format(source_path)
        validate_filename(file.filename, source_format)
        inspection = editing_service.inspect(source_path)
        return DocumentInspectionResponse(
            format=inspection.format,
            editable=inspection.editable,
            template_id=inspection.template_id,
        )
    finally:
        file.file.close()
        shutil.rmtree(temporary_directory, ignore_errors=True)


__all__ = ["router"]
