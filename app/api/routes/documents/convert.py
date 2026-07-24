"""Upload, convert, and download a document."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.dependencies import get_document_conversion_service
from app.api.openapi import DOCUMENT_CONVERSION_TAG
from app.core.config import Settings, get_settings
from app.documents import DocumentConversionService, DocumentFormat
from app.documents.conversion import (
    ConversionEngineUnavailableError,
    ConversionNotSupportedError,
    DocumentConversionError,
)
from app.documents.hwpx import HwpxError
from app.documents.snapshots import (
    DocumentSnapshotNameConflictError,
    DocumentSnapshotNotFoundError,
)

from .uploads import (
    MEDIA_TYPES,
    detect_uploaded_format,
    document_name,
    download_filename,
    save_upload,
    validate_filename,
)

router = APIRouter(tags=[DOCUMENT_CONVERSION_TAG])

def _convert_response(
    *,
    conversion_service: DocumentConversionService,
    source_path: Path,
    destination_path: Path,
    source_format: DocumentFormat,
    target_format: DocumentFormat,
    original_filename: str | None,
    temporary_directory: Path,
    options: Mapping[str, object] | None = None,
) -> FileResponse:
    try:
        result_path = conversion_service.convert(
            source_path,
            destination_path,
            source_format=source_format,
            target_format=target_format,
            options=options,
        )
    except DocumentSnapshotNameConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentSnapshotNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConversionEngineUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (ConversionNotSupportedError, DocumentConversionError, HwpxError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if not result_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="converter returned no output file",
        )
    return FileResponse(
        result_path,
        media_type=MEDIA_TYPES[target_format],
        filename=download_filename(original_filename, target_format),
        headers={"X-Detected-Source-Format": source_format.value},
        background=BackgroundTask(
            shutil.rmtree,
            temporary_directory,
            ignore_errors=True,
        ),
    )


@router.post(
    "/convert",
    response_class=FileResponse,
    responses={
        400: {"description": "Filename extension and detected format do not match"},
        404: {"description": "Referenced document snapshot was not found"},
        409: {"description": "Filename alias belongs to a different template layout"},
        413: {"description": "Upload is too large"},
        422: {"description": "Unsupported conversion or invalid document"},
        503: {"description": "Configured conversion engine is unavailable"},
    },
)
def convert_document(
    file: Annotated[UploadFile, File(description="Source document")],
    target_format: Annotated[DocumentFormat, Form(description="Requested output format")],
    conversion_service: Annotated[
        DocumentConversionService, Depends(get_document_conversion_service)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    """Detect the uploaded format, convert it, and delete temporary files."""

    temporary_directory = Path(tempfile.mkdtemp(prefix="fowoco-convert-"))
    uploaded_path = temporary_directory / "input.upload"
    try:
        save_upload(
            file,
            uploaded_path,
            max_bytes=settings.document_upload_max_bytes,
        )
        source_format = detect_uploaded_format(uploaded_path)
        validate_filename(file.filename, source_format)
        source_path = uploaded_path.with_suffix(f".{source_format.value}")
        uploaded_path.replace(source_path)
        destination_path = temporary_directory / f"output.{target_format.value}"
        return _convert_response(
            conversion_service=conversion_service,
            source_path=source_path,
            destination_path=destination_path,
            source_format=source_format,
            target_format=target_format,
            original_filename=file.filename,
            temporary_directory=temporary_directory,
            options={"document_name": document_name(file.filename)},
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    finally:
        file.file.close()

__all__ = ["router"]
