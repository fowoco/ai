"""Stable domain results and template descriptions for document editing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.documents.common import DocumentFormat


@dataclass(frozen=True)
class EditableField:
    name: str
    field_type: str
    width_mm: float | None = None
    height_mm: float | None = None


@dataclass(frozen=True)
class DocumentTemplateVariant:
    format: DocumentFormat
    fields: tuple[EditableField, ...]
    supports_dynamic_labels: bool
    supports_assets: bool


@dataclass(frozen=True)
class DocumentTemplateDefinition:
    template_id: str
    display_name: str
    variants: tuple[DocumentTemplateVariant, ...]


@dataclass(frozen=True)
class DocumentInspection:
    format: DocumentFormat
    editable: bool
    template_id: str | None


@dataclass(frozen=True)
class DocumentMutationResult:
    destination: Path
    format: DocumentFormat
    template_id: str
    changed_fields: tuple[str, ...]


__all__ = [
    "DocumentInspection",
    "DocumentMutationResult",
    "DocumentTemplateDefinition",
    "DocumentTemplateVariant",
    "EditableField",
]
