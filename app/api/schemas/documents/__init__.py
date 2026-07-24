"""Public document API schemas."""

from .capabilities import (
    DocumentCapabilitiesResponse,
    DocumentConversionCapability,
    DocumentTemplateCapability,
)
from .editing import (
    DocumentEditPayload,
    DocumentGeneratePayload,
    DocumentInspectionResponse,
    DocumentTemplateResponse,
    DocumentTemplateVariantResponse,
    EditableFieldResponse,
)

__all__ = [
    "DocumentCapabilitiesResponse",
    "DocumentConversionCapability",
    "DocumentEditPayload",
    "DocumentGeneratePayload",
    "DocumentInspectionResponse",
    "DocumentTemplateCapability",
    "DocumentTemplateResponse",
    "DocumentTemplateVariantResponse",
    "EditableFieldResponse",
]
