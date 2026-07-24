"""Multipart JSON payload and named asset handling for document mutations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel, ValidationError

from .uploads import save_upload, upload_leaf_name

MAX_ASSET_FILES = 20
PayloadT = TypeVar("PayloadT", bound=BaseModel)


def parse_json_payload(value: str, model: type[PayloadT]) -> PayloadT:
    try:
        decoded = json.loads(value)
        return model.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as exc:
        detail = exc.errors(include_url=False) if isinstance(exc, ValidationError) else str(exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "payload must be a valid JSON object", "errors": detail},
        ) from exc


def save_named_assets(
    uploads: list[UploadFile] | None,
    manifest: dict[str, str],
    directory: Path,
    *,
    max_bytes: int,
) -> dict[str, Path]:
    upload_list = uploads or []
    if len(upload_list) > MAX_ASSET_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"at most {MAX_ASSET_FILES} asset files are allowed",
        )
    by_name: dict[str, UploadFile] = {}
    for upload in upload_list:
        if not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="every asset needs a filename",
            )
        leaf_name = upload_leaf_name(upload.filename)
        if leaf_name in by_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"duplicate asset filename: {leaf_name!r}",
            )
        by_name[leaf_name] = upload

    requested_names: set[str] = set()
    for field_name, filename in manifest.items():
        leaf_name = upload_leaf_name(filename)
        if filename != leaf_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"asset mapping for {field_name!r} must use a plain filename",
            )
        requested_names.add(leaf_name)
        if leaf_name not in by_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"asset file was not uploaded: {leaf_name!r}",
            )
    unused_names = set(by_name) - requested_names
    if unused_names:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"uploaded assets are not referenced by payload: {sorted(unused_names)}",
        )

    saved_by_name: dict[str, Path] = {}
    for index, (filename, upload) in enumerate(by_name.items()):
        suffix = Path(filename).suffix.casefold()
        if suffix not in {".bmp", ".jpeg", ".jpg", ".png"}:
            suffix = ".upload"
        destination = directory / f"asset-{index}{suffix}"
        save_upload(upload, destination, max_bytes=max_bytes, description="asset")
        saved_by_name[filename] = destination
    return {
        field_name: saved_by_name[filename]
        for field_name, filename in manifest.items()
    }


def close_uploads(uploads: list[UploadFile] | None) -> None:
    for upload in uploads or []:
        upload.file.close()


__all__ = ["close_uploads", "parse_json_payload", "save_named_assets"]
