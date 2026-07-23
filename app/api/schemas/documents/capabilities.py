"""Schemas for document generation and conversion capabilities."""

from pydantic import BaseModel

from app.documents import DocumentFormat


class DocumentTemplateCapability(BaseModel):
    format: DocumentFormat
    template_id: str
    field_count: int


class DocumentConversionCapability(BaseModel):
    source_format: DocumentFormat
    target_format: DocumentFormat


class DocumentCapabilitiesResponse(BaseModel):
    editable_formats: tuple[DocumentFormat, ...]
    templates: tuple[DocumentTemplateCapability, ...]
    conversions: tuple[DocumentConversionCapability, ...]


__all__ = [
    "DocumentCapabilitiesResponse",
    "DocumentConversionCapability",
    "DocumentTemplateCapability",
]
