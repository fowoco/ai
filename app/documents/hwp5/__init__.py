"""HWP document support.

The current implementation targets the HWP 5.x binary format and intentionally
keeps its exact-format class names (``Hwp5*``).
"""

from .editor import EmbeddedImage, Hwp5BinaryDocument, ParagraphSelector
from .exceptions import Hwp5TemplateError, Hwp5TemplateNotFoundError
from .service import Hwp5DocumentService, Hwp5EditResult, edit_hwp5
from .template_registry import Hwp5Template, Hwp5TemplateRegistry

__all__ = [
    "EmbeddedImage",
    "Hwp5BinaryDocument",
    "Hwp5DocumentService",
    "Hwp5EditResult",
    "Hwp5Template",
    "Hwp5TemplateError",
    "Hwp5TemplateNotFoundError",
    "Hwp5TemplateRegistry",
    "ParagraphSelector",
    "edit_hwp5",
]
