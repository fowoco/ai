from uuid import UUID

from pydantic import BaseModel

from app.ocr.models import DocumentSide, FieldValue, OcrStatus


class OcrResponse(BaseModel):
    request_id: UUID
    worker_document_id: UUID
    ocr_status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    fields: dict[str, FieldValue]
    field_confidences: dict[str, float]
    review_reasons: list[str]
