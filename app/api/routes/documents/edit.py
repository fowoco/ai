"""Structured editing of uploaded HWP and HWPX documents."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import get_document_editing_service
from app.api.openapi import DOCUMENT_EDITING_TAG
from app.api.schemas.documents import DocumentEditPayload
from app.core.config import Settings, get_settings
from app.documents.editing import DocumentEditingError, DocumentEditingService

from .assets import close_uploads, parse_json_payload, save_named_assets
from .mutation_responses import mutation_file_response, raise_editing_http_error
from .uploads import (
    detect_uploaded_format,
    save_upload,
    validate_filename,
)

router = APIRouter(tags=[DOCUMENT_EDITING_TAG])


@router.post(
    "/edit",
    response_class=FileResponse,
    responses={
        400: {"description": "Filename extension and detected format do not match"},
        404: {"description": "Template was not found"},
        413: {"description": "Document or asset is too large"},
        422: {"description": "Invalid edit payload or unsupported edit"},
    },
)
def edit_document(
    file: Annotated[UploadFile, File(description="Source HWP or HWPX")],
    payload: Annotated[
        str,
        Form(
            description=(
                "JSON object containing template_id, values, "
                "application_options, and asset filename mappings"
            )
        ),
    ],
    editing_service: Annotated[
        DocumentEditingService, Depends(get_document_editing_service)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    assets: Annotated[
        list[UploadFile] | None,
        File(description="Photo and signature files referenced by payload.assets"),
    ] = None,
) -> FileResponse:
    temporary_directory = Path(tempfile.mkdtemp(prefix="fowoco-edit-"))
    uploaded_path = temporary_directory / "input.upload"
    try:
        command = parse_json_payload(payload, DocumentEditPayload)
        save_upload(
            file,
            uploaded_path,
            max_bytes=settings.document_upload_max_bytes,
        )
        source_format = detect_uploaded_format(uploaded_path)
        validate_filename(file.filename, source_format)
        source_path = uploaded_path.with_suffix(f".{source_format.value}")
        uploaded_path.replace(source_path)
        asset_paths = save_named_assets(
            assets,
            command.assets,
            temporary_directory,
            max_bytes=settings.document_upload_max_bytes,
        )
        destination_path = temporary_directory / f"output.{source_format.value}"
        try:
            result = editing_service.edit(
                source_path,
                destination_path,
                values=command.values,
                application_options=command.application_options,
                assets=asset_paths,
                template_id=command.template_id,
            )
        except DocumentEditingError as exc:
            raise_editing_http_error(exc)
        return mutation_file_response(
            result,
            original_filename=file.filename or "document",
            temporary_directory=temporary_directory,
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    finally:
        file.file.close()
        close_uploads(assets)


__all__ = ["router"]
