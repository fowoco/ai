"""외부 레코드 데이터를 문서 템플릿에 연결하는 기능."""

from .errors import DocumentRecordError, DocumentRecordParseError
from .service import DocumentRecordGenerationService
from .text_reader import RecordReader, TextRecordReader

__all__ = [
    "DocumentRecordError",
    "DocumentRecordGenerationService",
    "DocumentRecordParseError",
    "RecordReader",
    "TextRecordReader",
]
