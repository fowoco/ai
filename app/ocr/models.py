from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TypeAlias
from uuid import UUID

FieldValue: TypeAlias = str | date


class DocumentType(StrEnum):
    PASSPORT_COPY = "PASSPORT_COPY"
    ARC = "ARC"


class OcrStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class DocumentSide(StrEnum):
    FRONT = "FRONT"
    BACK = "BACK"


@dataclass(frozen=True)
class OcrScope:
    worker_document_id: UUID
    worker_id: UUID
    company_id: UUID


@dataclass(frozen=True)
class OcrFile:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class OcrCommand:
    request_id: UUID
    scope: OcrScope
    document_type: DocumentType
    country_code: str | None
    file: OcrFile


@dataclass(frozen=True)
class TemplateSelection:
    template_ids: tuple[int, ...]
    expected_document_type: DocumentType


@dataclass(frozen=True)
class NormalizedOcrResult:
    status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    fields: Mapping[str, FieldValue]
    field_confidences: Mapping[str, float]
    error_code: str | None
    review_reasons: tuple[str, ...]


@dataclass(frozen=True)
class OcrProcessResult:
    request_id: UUID
    worker_document_id: UUID
    status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    review_reasons: tuple[str, ...]


class TemplateResolutionError(ValueError):
    """The request cannot be mapped to an approved OCR template."""
