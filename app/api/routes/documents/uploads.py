"""Shared upload validation and document filename helpers."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile, status

from app.documents import (
    DocumentFormat,
    DocumentFormatDetectionError,
    detect_document_format,
)

COPY_CHUNK_BYTES = 1024 * 1024
MEDIA_TYPES = {
    DocumentFormat.HWP: "application/vnd.hancom.hwp",
    DocumentFormat.HWPX: "application/vnd.hancom.hwpx",
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.XML: "application/xml",
}


def validate_filename(filename: str | None, source_format: DocumentFormat) -> None:
    if not filename:
        return
    leaf_name = upload_leaf_name(filename)
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


def download_filename(filename: str | None, target_format: DocumentFormat) -> str:
    stem = document_name(filename)
    stem = "".join(character for character in stem if character >= " " and character != "\x7f")
    return f"{stem or 'document'}.{target_format.value}"


def document_name(filename: str | None) -> str:
    leaf_name = upload_leaf_name(filename or "document")
    return Path(leaf_name).stem.strip() or "document"


def upload_leaf_name(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).name


def save_upload(
    upload: UploadFile,
    destination: Path,
    *,
    max_bytes: int,
    description: str = "document",
) -> None:
    total_bytes = 0
    with destination.open("wb") as output:
        while chunk := upload.file.read(COPY_CHUNK_BYTES):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"uploaded {description} exceeds the {max_bytes}-byte limit",
                )
            output.write(chunk)
    if total_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"uploaded {description} is empty",
        )


def detect_uploaded_format(uploaded_path: Path) -> DocumentFormat:
    try:
        return detect_document_format(uploaded_path)
    except DocumentFormatDetectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


__all__ = [
    "MEDIA_TYPES",
    "detect_uploaded_format",
    "document_name",
    "download_filename",
    "save_upload",
    "upload_leaf_name",
    "validate_filename",
]
