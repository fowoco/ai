"""Upload, convert, and download a document."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.dependencies import get_document_conversion_service
from app.core.config import Settings, get_settings
from app.documents import (
    DocumentConversionService,
    DocumentFormat,
    DocumentFormatDetectionError,
    detect_document_format,
)
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

router = APIRouter(tags=["documents"])

COPY_CHUNK_BYTES = 1024 * 1024
MEDIA_TYPES = {
    DocumentFormat.HWP: "application/vnd.hancom.hwp",
    DocumentFormat.HWPX: "application/vnd.hancom.hwpx",
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.XML: "application/xml",
}


def _validate_filename(filename: str | None, source_format: DocumentFormat) -> None:
    if not filename:
        return
    leaf_name = PurePosixPath(filename.replace("\\", "/")).name
    suffix = Path(leaf_name).suffix.casefold()
    known_suffixes = {f".{document_format.value}" for document_format in DocumentFormat}
    if suffix in known_suffixes and suffix != f".{source_format.value}":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"filename extension {suffix!r} does not match "
                f"detected format {source_format.value!r}"
            ),
        )


def _download_filename(filename: str | None, target_format: DocumentFormat) -> str:
    leaf_name = PurePosixPath((filename or "document").replace("\\", "/")).name
    stem = Path(leaf_name).stem.strip() or "document"
    stem = "".join(character for character in stem if character >= " " and character != "\x7f")
    return f"{stem or 'document'}.{target_format.value}"


def _document_name(filename: str | None) -> str:
    leaf_name = PurePosixPath((filename or "document").replace("\\", "/")).name
    return Path(leaf_name).stem.strip() or "document"


def _save_upload(upload: UploadFile, destination: Path, *, max_bytes: int) -> None:
    total_bytes = 0
    with destination.open("wb") as output:
        while chunk := upload.file.read(COPY_CHUNK_BYTES):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"uploaded document exceeds the {max_bytes}-byte limit",
                )
            output.write(chunk)
    if total_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="uploaded document is empty",
        )


def _detect_uploaded_format(uploaded_path: Path) -> DocumentFormat:
    try:
        return detect_document_format(uploaded_path)
    except DocumentFormatDetectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


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
        filename=_download_filename(original_filename, target_format),
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
        _save_upload(
            file,
            uploaded_path,
            max_bytes=settings.document_upload_max_bytes,
        )
        source_format = _detect_uploaded_format(uploaded_path)
        _validate_filename(file.filename, source_format)
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
            options={"document_name": _document_name(file.filename)},
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    finally:
        file.file.close()


@router.post(
    "/convert/from-xml",
    response_class=FileResponse,
    responses={
        400: {"description": "Uploaded file is not XML"},
        404: {"description": "Referenced document snapshot was not found"},
        413: {"description": "Upload is too large"},
        422: {"description": "Invalid template-based conversion"},
        503: {"description": "Configured conversion engine is unavailable"},
    },
)
def convert_from_xml(
    file: Annotated[UploadFile, File(description="HWPX section XML")],
    target_format: Annotated[
        DocumentFormat,
        Form(description="Requested output format: hwp, hwpx, or pdf"),
    ],
    conversion_service: Annotated[
        DocumentConversionService, Depends(get_document_conversion_service)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    """Resolve the XML snapshot reference, repackage it, and optionally convert it."""

    if target_format not in {DocumentFormat.HWP, DocumentFormat.HWPX, DocumentFormat.PDF}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="XML template conversion target must be hwp, hwpx, or pdf",
        )
    temporary_directory = Path(tempfile.mkdtemp(prefix="fowoco-xml-convert-"))
    uploaded_path = temporary_directory / "input.upload"
    try:
        _save_upload(
            file,
            uploaded_path,
            max_bytes=settings.document_upload_max_bytes,
        )
        source_format = _detect_uploaded_format(uploaded_path)
        if source_format is not DocumentFormat.XML:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="convert/from-xml requires an XML document",
            )
        _validate_filename(file.filename, source_format)
        source_path = uploaded_path.with_suffix(".xml")
        uploaded_path.replace(source_path)
        destination_path = temporary_directory / f"output.{target_format.value}"
        return _convert_response(
            conversion_service=conversion_service,
            source_path=source_path,
            destination_path=destination_path,
            source_format=DocumentFormat.XML,
            target_format=target_format,
            original_filename=file.filename,
            temporary_directory=temporary_directory,
            options={"document_name": _document_name(file.filename)},
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    finally:
        file.file.close()


__all__ = ["router"]
