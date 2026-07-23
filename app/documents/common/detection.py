"""Content-based document format detection."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import olefile

from .formats import DocumentFormat

CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
HWP5_SIGNATURE = b"HWP Document File"
HWPX_MIMETYPE = b"application/hwp+zip"


class DocumentFormatDetectionError(ValueError):
    """The uploaded content does not match a supported document format."""


def detect_document_format(source: str | Path) -> DocumentFormat:
    """Identify HWP, HWPX, PDF, or XML from content rather than filename."""

    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    with source_path.open("rb") as document:
        signature = document.read(8)

    if signature.startswith(b"%PDF-"):
        return DocumentFormat.PDF
    if signature == CFB_SIGNATURE:
        return _detect_hwp(source_path)
    if signature.startswith(b"PK"):
        return _detect_hwpx(source_path)
    return _detect_xml(source_path)


def _detect_hwp(source: Path) -> DocumentFormat:
    try:
        with olefile.OleFileIO(str(source)) as document:
            if not document.exists("FileHeader"):
                raise DocumentFormatDetectionError(
                    "OLE container is not an HWP 5.x document"
                )
            signature = document.openstream("FileHeader").read(len(HWP5_SIGNATURE))
    except OSError as exc:
        raise DocumentFormatDetectionError("invalid HWP 5.x container") from exc
    if signature != HWP5_SIGNATURE:
        raise DocumentFormatDetectionError("invalid HWP 5.x FileHeader signature")
    return DocumentFormat.HWP


def _detect_hwpx(source: Path) -> DocumentFormat:
    try:
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            mimetype = archive.read("mimetype").strip()
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise DocumentFormatDetectionError("ZIP container is not a valid HWPX") from exc
    has_section = any(
        candidate in names
        for candidate in ("Contents/section0.xml", "Content/section0.xml")
    )
    if mimetype != HWPX_MIMETYPE or not has_section:
        raise DocumentFormatDetectionError("ZIP container is not a valid HWPX")
    return DocumentFormat.HWPX


def _detect_xml(source: Path) -> DocumentFormat:
    payload = source.read_bytes()
    upper_payload = payload.upper().replace(b"\x00", b"")
    if b"<!DOCTYPE" in upper_payload or b"<!ENTITY" in upper_payload:
        raise DocumentFormatDetectionError("DTD and entity declarations are not allowed")
    try:
        ET.fromstring(payload)
    except (ET.ParseError, ValueError) as exc:
        raise DocumentFormatDetectionError(
            "could not detect a supported document format"
        ) from exc
    return DocumentFormat.XML


__all__ = ["DocumentFormatDetectionError", "detect_document_format"]
