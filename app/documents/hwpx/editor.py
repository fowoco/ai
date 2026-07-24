"""Public HWPX editor facade over package and section implementations."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .errors import HwpxError
from .package import HwpxPackage
from .section_xml import HwpxRecordAssignment, HwpxSection


class HwpxDocument:
    """Edit one HWPX section while preserving all other package resources."""

    def __init__(self, source: str | Path, *, section: int = 0):
        self.source = Path(source).resolve()
        self.section = section
        self._package = HwpxPackage(self.source)
        self._section_name = self._package.section_name(section)
        self._section = HwpxSection(
            self._package.read(self._section_name),
            location=self._section_name,
        )

    def apply_values(self, values: Mapping[str, object]) -> tuple[str, ...]:
        return self._section.apply_values(values)

    def apply_application_options(
        self,
        options: Mapping[str, object],
    ) -> tuple[str, ...]:
        return self._section.apply_application_options(options)

    def apply_record_assignments(
        self,
        assignments: tuple[HwpxRecordAssignment, ...],
    ) -> tuple[str, ...]:
        return self._section.apply_record_assignments(assignments)

    def section_xml(self) -> bytes:
        return self._section.to_bytes()

    def replace_section_xml(self, xml_source: str | Path | bytes) -> None:
        self._section.replace(xml_source)

    def save(self, destination: str | Path) -> Path:
        return self._package.save_replacing(
            self._section_name,
            self._section.to_bytes(),
            destination,
        )


def fill_hwpx_form(
    source: str | Path,
    destination: str | Path,
    values: Mapping[str, object],
) -> Path:
    document = HwpxDocument(source)
    document.apply_values(values)
    return document.save(destination)


def check_application_options(
    source: str | Path,
    destination: str | Path,
    options: Mapping[str, object],
) -> Path:
    document = HwpxDocument(source)
    document.apply_application_options(options)
    return document.save(destination)


__all__ = [
    "HwpxDocument",
    "HwpxError",
    "check_application_options",
    "fill_hwpx_form",
]
