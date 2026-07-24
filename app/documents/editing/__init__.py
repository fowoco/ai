"""Public structured document editing facade."""

from .exceptions import (
    DocumentEditingError,
    DocumentEditingNotSupportedError,
    DocumentTemplateNotFoundError,
)
from .models import (
    DocumentInspection,
    DocumentMutationResult,
    DocumentTemplateDefinition,
    DocumentTemplateVariant,
    EditableField,
)
from .service import DocumentEditingService
from .template_names import TEMPLATE_DISPLAY_NAMES, template_display_name

__all__ = [
    "DocumentEditingError",
    "DocumentEditingNotSupportedError",
    "DocumentEditingService",
    "TEMPLATE_DISPLAY_NAMES",
    "DocumentInspection",
    "DocumentMutationResult",
    "DocumentTemplateDefinition",
    "DocumentTemplateNotFoundError",
    "DocumentTemplateVariant",
    "EditableField",
    "template_display_name",
]
