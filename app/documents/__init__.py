"""Document generation domain.

Natural-language agents produce structured values; this package identifies
templates and turns those values into downloadable document files.
"""

from .common import DocumentFormat, DocumentFormatDetectionError, detect_document_format
from .conversion import DocumentConversionService
from .hwp5 import Hwp5DocumentService
from .hwpx import HwpxDocumentService

__all__ = [
    "DocumentConversionService",
    "DocumentFormat",
    "DocumentFormatDetectionError",
    "Hwp5DocumentService",
    "HwpxDocumentService",
    "detect_document_format",
]
