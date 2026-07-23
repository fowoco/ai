import zipfile
from pathlib import Path

import pytest

from app.api.dependencies import get_document_conversion_service
from app.documents import DocumentFormat
from app.documents.conversion import DocumentConversionError, XmlToHwpxConverter
from app.documents.hwpx import HwpxDocumentService, HwpxError
from app.documents.snapshots import strip_snapshot_metadata

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "documents"


def test_hwpx_registry_and_xml_extraction_match_fixtures(tmp_path: Path) -> None:
    service = HwpxDocumentService()
    templates = service.templates()

    assert len(templates) == 4
    for template in templates:
        expected = FIXTURE_ROOT / "xml" / f"{template.source_path.stem}.xml"
        output = tmp_path / expected.name
        service.extract_xml(template.source_path, output)
        assert output.read_bytes() == expected.read_bytes()


def test_hwpx_generate_fills_values_and_application_options(tmp_path: Path) -> None:
    service = HwpxDocumentService()
    output = tmp_path / "filled.hwpx"

    result = service.generate(
        "immigration_integrated_application_v34",
        output,
        values={"성": "PARK", "명": "TAEJUNG", "년": "1998"},
        application_options={"외국인 등록": True},
    )

    assert result.destination == output.resolve()
    assert {"성", "명", "년", "외국인 등록"}.issubset(result.changed_fields)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert "PARK" in section
    assert "TAEJUNG" in section
    assert "1998" in section
    assert "[v]" in section


def test_registered_hwpx_to_xml_converter(tmp_path: Path) -> None:
    template = HwpxDocumentService().templates()[0]
    output = tmp_path / "section.xml"

    result = get_document_conversion_service().convert(
        template.source_path,
        output,
        source_format=DocumentFormat.HWPX,
        target_format=DocumentFormat.XML,
    )

    assert result == output.resolve()
    assert output.read_bytes().startswith(b"<?xml")


def test_registered_xml_to_hwpx_converter_round_trip(tmp_path: Path) -> None:
    service = get_document_conversion_service()
    template = HwpxDocumentService().registry.get(
        "immigration_integrated_application_v34"
    )
    source_xml = FIXTURE_ROOT / "xml" / "통합신청서.xml"
    output_hwpx = tmp_path / "rebuilt.hwpx"
    round_trip_xml = tmp_path / "round-trip.xml"

    result = service.convert(
        source_xml,
        output_hwpx,
        source_format=DocumentFormat.XML,
        target_format=DocumentFormat.HWPX,
        options={"template_id": "immigration_integrated_application_v34"},
    )

    assert result == output_hwpx.resolve()
    with (
        zipfile.ZipFile(template.source_path) as original,
        zipfile.ZipFile(output_hwpx) as rebuilt,
    ):
        assert rebuilt.testzip() is None
        assert rebuilt.infolist()[0].filename == "mimetype"
        assert rebuilt.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert rebuilt.read("mimetype") == b"application/hwp+zip"
        assert rebuilt.namelist() == original.namelist()
        assert rebuilt.read("Contents/section0.xml") == source_xml.read_bytes()
        for name in original.namelist():
            if name != "Contents/section0.xml":
                assert rebuilt.read(name) == original.read(name)

    service.convert(
        output_hwpx,
        round_trip_xml,
        source_format=DocumentFormat.HWPX,
        target_format=DocumentFormat.XML,
    )
    assert strip_snapshot_metadata(round_trip_xml.read_bytes()) == source_xml.read_bytes()


def test_xml_to_hwpx_converter_requires_template_id(tmp_path: Path) -> None:
    source_xml = FIXTURE_ROOT / "xml" / "통합신청서.xml"

    with pytest.raises(
        DocumentConversionError,
        match=r"requires a snapshot reference or template_id",
    ):
        XmlToHwpxConverter().convert(
            source_xml,
            tmp_path / "rebuilt.hwpx",
        )


def test_xml_to_hwpx_rejects_non_section_xml(tmp_path: Path) -> None:
    source_xml = tmp_path / "not-a-section.xml"
    source_xml.write_text("<root />", encoding="utf-8")

    with pytest.raises(HwpxError, match="section XML root"):
        HwpxDocumentService().create_from_xml(
            source_xml,
            tmp_path / "rebuilt.hwpx",
            template_id="immigration_integrated_application_v34",
        )


def test_xml_to_hwpx_rejects_malformed_xml(tmp_path: Path) -> None:
    source_xml = tmp_path / "malformed.xml"
    source_xml.write_text("<hs:sec>", encoding="utf-8")

    with pytest.raises(HwpxError, match="invalid HWPX section XML"):
        HwpxDocumentService().create_from_xml(
            source_xml,
            tmp_path / "rebuilt.hwpx",
            template_id="immigration_integrated_application_v34",
        )
