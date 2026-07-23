import zipfile
from pathlib import Path

import pytest

from app.documents.conversion import HwpxToXmlConverter, XmlToHwpxConverter
from app.documents.hwpx import HwpxDocumentService
from app.documents.snapshots import (
    DocumentSnapshotNameConflictError,
    DocumentSnapshotRepository,
    hwpx_layout_fingerprint,
    read_snapshot_metadata,
    strip_snapshot_metadata,
)


def test_value_changes_share_layout_but_keep_distinct_document_snapshots(
    tmp_path: Path,
) -> None:
    service = HwpxDocumentService()
    first = tmp_path / "first.hwpx"
    second = tmp_path / "second.hwpx"
    service.generate(
        "immigration_integrated_application_v34",
        first,
        values={"성": "HONG", "명": "GILDONG"},
    )
    service.generate(
        "immigration_integrated_application_v34",
        second,
        values={"성": "AAA", "명": "BBB"},
    )
    repository = DocumentSnapshotRepository(tmp_path / "repository")

    first_snapshot = repository.store(first, template_name="통합신청서")
    second_snapshot = repository.store(second, template_name="통합신청서")

    assert first_snapshot.layout_fingerprint == second_snapshot.layout_fingerprint
    assert first_snapshot.snapshot_ref != second_snapshot.snapshot_ref
    assert repository.resolve_name(" 통합신청서 ").snapshot_ref == second_snapshot.snapshot_ref


def test_same_name_rejects_structurally_different_form(tmp_path: Path) -> None:
    service = HwpxDocumentService()
    identity = service.registry.get("identity_guaranty_v129").source_path
    contract = service.registry.get("standard_labor_contract_v6").source_path
    repository = DocumentSnapshotRepository(tmp_path / "repository")
    repository.store(identity, template_name="같은 이름")

    with pytest.raises(DocumentSnapshotNameConflictError, match="different layout"):
        repository.store(contract, template_name="같은 이름")


def test_xml_embedded_reference_and_filename_fallback_restore_snapshot(
    tmp_path: Path,
) -> None:
    source = HwpxDocumentService().registry.get("identity_guaranty_v129").source_path
    repository = DocumentSnapshotRepository(tmp_path / "repository")
    to_xml = HwpxToXmlConverter(snapshot_repository=repository)
    from_xml = XmlToHwpxConverter(snapshot_repository=repository)
    xml_with_reference = tmp_path / "downloaded.xml"
    restored_from_reference = tmp_path / "reference.hwpx"
    restored_from_name = tmp_path / "name.hwpx"

    to_xml.convert(
        source,
        xml_with_reference,
        options={"document_name": "신원보증서"},
    )
    metadata = read_snapshot_metadata(xml_with_reference.read_bytes())
    assert metadata is not None
    assert repository.get(metadata.snapshot_ref).package_path.is_file()

    from_xml.convert(xml_with_reference, restored_from_reference)
    xml_without_reference = tmp_path / "신원보증서.xml"
    xml_without_reference.write_bytes(
        strip_snapshot_metadata(xml_with_reference.read_bytes())
    )
    from_xml.convert(
        xml_without_reference,
        restored_from_name,
        options={"document_name": "신원보증서"},
    )

    with zipfile.ZipFile(source) as original:
        original_section = original.read("Contents/section0.xml")
    for restored in (restored_from_reference, restored_from_name):
        with zipfile.ZipFile(restored) as archive:
            assert archive.testzip() is None
            assert archive.read("Contents/section0.xml") == original_section


def test_layout_fingerprint_ignores_entered_text(tmp_path: Path) -> None:
    service = HwpxDocumentService()
    source = service.registry.get("immigration_integrated_application_v34").source_path
    filled = tmp_path / "filled.hwpx"
    service.generate(
        "immigration_integrated_application_v34",
        filled,
        values={"성": "CHANGED", "명": "VALUE"},
    )

    assert hwpx_layout_fingerprint(source) == hwpx_layout_fingerprint(filled)
