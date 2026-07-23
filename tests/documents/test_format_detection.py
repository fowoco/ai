from pathlib import Path

import pytest

from app.documents import (
    DocumentFormat,
    DocumentFormatDetectionError,
    Hwp5DocumentService,
    HwpxDocumentService,
    detect_document_format,
)


def test_detects_hwp_from_file_header_not_filename(tmp_path: Path) -> None:
    source = Hwp5DocumentService().registry.get("identity_guaranty_v129").source_path
    disguised = tmp_path / "uploaded.bin"
    disguised.write_bytes(source.read_bytes())

    assert detect_document_format(disguised) is DocumentFormat.HWP


def test_detects_hwpx_from_package_not_filename(tmp_path: Path) -> None:
    source = HwpxDocumentService().registry.get("identity_guaranty_v129").source_path
    disguised = tmp_path / "uploaded.bin"
    disguised.write_bytes(source.read_bytes())

    assert detect_document_format(disguised) is DocumentFormat.HWPX


def test_detects_pdf_and_xml(tmp_path: Path) -> None:
    pdf = tmp_path / "uploaded.data"
    pdf.write_bytes(b"%PDF-1.7\nfixture")
    xml = tmp_path / "uploaded.data.xml"
    xml.write_bytes(b'<?xml version="1.0" encoding="UTF-8"?><root/>')

    assert detect_document_format(pdf) is DocumentFormat.PDF
    assert detect_document_format(xml) is DocumentFormat.XML


def test_rejects_unknown_or_unsafe_xml_content(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.bin"
    unknown.write_bytes(b"not a supported document")
    unsafe_xml = tmp_path / "unsafe.xml"
    unsafe_xml.write_bytes(b"<!DOCTYPE root [<!ENTITY x 'value'>]><root>&x;</root>")
    unsafe_utf16_xml = tmp_path / "unsafe-utf16.xml"
    unsafe_utf16_xml.write_bytes(
        "<!DOCTYPE root [<!ENTITY x 'value'>]><root>&x;</root>".encode("utf-16")
    )

    with pytest.raises(DocumentFormatDetectionError, match="could not detect"):
        detect_document_format(unknown)
    with pytest.raises(DocumentFormatDetectionError, match="DTD"):
        detect_document_format(unsafe_xml)
    with pytest.raises(DocumentFormatDetectionError, match="DTD"):
        detect_document_format(unsafe_utf16_xml)
