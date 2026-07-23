"""Template-based XML section to HWPX package converter."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.conversion.errors import DocumentConversionError
from app.documents.hwpx import HwpxDocumentService
from app.documents.snapshots import (
    DocumentSnapshotRepository,
    read_snapshot_metadata,
    strip_snapshot_metadata,
)


class XmlToHwpxConverter:
    source_format = DocumentFormat.XML
    target_format = DocumentFormat.HWPX

    def __init__(
        self,
        service: HwpxDocumentService | None = None,
        snapshot_repository: DocumentSnapshotRepository | None = None,
    ):
        self.service = service or HwpxDocumentService()
        self.snapshot_repository = snapshot_repository

    def convert(
        self,
        source: Path,
        destination: Path,
        *,
        options: Mapping[str, object] | None = None,
    ) -> Path:
        converter_options = options or {}
        template_id = str(converter_options.get("template_id", "")).strip()
        try:
            section = int(converter_options.get("section", 0))
        except (TypeError, ValueError) as exc:
            raise DocumentConversionError(
                "xml -> hwpx conversion requires options.section to be an integer"
            ) from exc
        if section < 0:
            raise DocumentConversionError(
                "xml -> hwpx conversion requires options.section to be non-negative"
            )
        if template_id:
            return self.service.create_from_xml(
                source,
                destination,
                template_id=template_id,
                section=section,
            )
        if self.snapshot_repository is None:
            raise DocumentConversionError(
                "xml -> hwpx conversion requires a snapshot reference or template_id"
            )

        xml_data = source.read_bytes()
        metadata = read_snapshot_metadata(xml_data)
        if metadata is not None:
            snapshot = self.snapshot_repository.get(metadata.snapshot_ref)
            section = metadata.section
        else:
            document_name = str(
                converter_options.get("document_name", source.stem)
            ).strip()
            snapshot = self.snapshot_repository.resolve_name(document_name)
            section = snapshot.section
        return self.service.create_from_xml_template(
            strip_snapshot_metadata(xml_data),
            snapshot.package_path,
            destination,
            section=section,
        )


__all__ = ["XmlToHwpxConverter"]
