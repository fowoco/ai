"""HWPX section XML extraction converter."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.hwpx import HwpxDocumentService
from app.documents.snapshots import DocumentSnapshotRepository, add_snapshot_metadata


class HwpxToXmlConverter:
    source_format = DocumentFormat.HWPX
    target_format = DocumentFormat.XML

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
        section = int(converter_options.get("section", 0))
        result = self.service.extract_xml(source, destination, section=section)
        if self.snapshot_repository is not None:
            template_name = str(
                converter_options.get("document_name", source.stem)
            ).strip()
            snapshot = self.snapshot_repository.store(
                source,
                template_name=template_name,
                section=section,
            )
            result.write_bytes(
                add_snapshot_metadata(
                    result.read_bytes(),
                    snapshot_ref=snapshot.snapshot_ref,
                    section=section,
                )
            )
        return result


__all__ = ["HwpxToXmlConverter"]
