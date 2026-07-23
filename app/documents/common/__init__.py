"""Types shared by document formats without depending on concrete implementations."""

from .detection import DocumentFormatDetectionError, detect_document_format
from .formats import DocumentFormat

__all__ = [
    "DocumentFormat",
    "DocumentFormatDetectionError",
    "detect_document_format",
]
