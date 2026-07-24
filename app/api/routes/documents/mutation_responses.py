"""Shared response and error mapping for document edit/generate endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import NoReturn

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.documents.editing import (
    DocumentEditingError,
    DocumentMutationResult,
    DocumentTemplateNotFoundError,
)

from .uploads import MEDIA_TYPES, download_filename


def mutation_file_response(
    result: DocumentMutationResult,
    *,
    original_filename: str,
    temporary_directory: Path,
) -> FileResponse:
    return FileResponse(
        result.destination,
        media_type=MEDIA_TYPES[result.format],
        filename=download_filename(original_filename, result.format),
        headers={
            "X-Document-Template-Id": result.template_id,
            "X-Changed-Field-Count": str(len(result.changed_fields)),
        },
        background=BackgroundTask(
            shutil.rmtree,
            temporary_directory,
            ignore_errors=True,
        ),
    )


def raise_editing_http_error(exc: DocumentEditingError) -> NoReturn:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(exc, DocumentTemplateNotFoundError)
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


__all__ = ["mutation_file_response", "raise_editing_http_error"]
