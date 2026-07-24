"""레코드 기반 문서 생성에서 발생하는 오류."""

from app.documents.editing import DocumentEditingError


class DocumentRecordError(DocumentEditingError):
    """레코드 읽기 또는 규칙 기반 기입에 실패했다."""


class DocumentRecordParseError(DocumentRecordError):
    """테스트용 TXT 레코드가 올바르지 않다."""


__all__ = ["DocumentRecordError", "DocumentRecordParseError"]
