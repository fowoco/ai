"""Application service for HWPX editing and XML extraction."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .editor import HwpxDocument
from .template_registry import HwpxTemplate, HwpxTemplateRegistry


@dataclass(frozen=True)
class HwpxEditResult:
    destination: Path
    template_id: str
    changed_fields: tuple[str, ...]


class HwpxDocumentService:
    def __init__(self, registry: HwpxTemplateRegistry | None = None):
        self.registry = registry or HwpxTemplateRegistry()

    def templates(self) -> tuple[HwpxTemplate, ...]:
        return self.registry.list()

    def generate(
        self,
        template_id: str,
        destination: str | Path,
        *,
        values: Mapping[str, object] | None = None,
        application_options: Mapping[str, object] | None = None,
    ) -> HwpxEditResult:
        template = self.registry.get(template_id)
        return self._apply(
            template,
            template.source_path,
            destination,
            values,
            application_options,
        )

    def fill(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        values: Mapping[str, object] | None = None,
        application_options: Mapping[str, object] | None = None,
        template_id: str | None = None,
    ) -> HwpxEditResult:
        template = (
            self.registry.get(template_id)
            if template_id is not None
            else self.registry.identify(source)
        )
        return self._apply(template, source, destination, values, application_options)

    @staticmethod
    def _apply(
        template: HwpxTemplate,
        source: str | Path,
        destination: str | Path,
        values: Mapping[str, object] | None,
        application_options: Mapping[str, object] | None,
    ) -> HwpxEditResult:
        document = HwpxDocument(source)
        changed = list(document.apply_application_options(application_options or {}))
        changed.extend(document.apply_values(values or {}))
        output = document.save(destination)
        return HwpxEditResult(output, template.template_id, tuple(changed))

    @staticmethod
    def extract_xml(
        source: str | Path,
        destination: str | Path,
        *,
        section: int = 0,
    ) -> Path:
        document = HwpxDocument(source, section=section)
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="hwpx-xml-",
                suffix=".xml",
                dir=destination_path.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(document.section_xml())
            os.replace(temporary_path, destination_path)
            temporary_path = None
            return destination_path
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def create_from_xml(
        self,
        xml_source: str | Path,
        destination: str | Path,
        *,
        template_id: str,
        section: int = 0,
    ) -> Path:
        """Build HWPX by replacing one section in a bundled template package."""

        template = self.registry.get(template_id)
        document = HwpxDocument(template.source_path, section=section)
        document.replace_section_xml(xml_source)
        return document.save(destination)

    @staticmethod
    def create_from_xml_template(
        xml_source: str | Path | bytes,
        template_source: str | Path,
        destination: str | Path,
        *,
        section: int = 0,
    ) -> Path:
        """Build HWPX by replacing one section in an arbitrary package snapshot."""

        document = HwpxDocument(template_source, section=section)
        document.replace_section_xml(xml_source)
        return document.save(destination)


__all__ = ["HwpxDocumentService", "HwpxEditResult"]
