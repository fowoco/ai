from uuid import UUID

from pydantic import BaseModel

from app.ocr.models import DocumentSide, OcrStatus


class OcrResponse(BaseModel):
    request_id: UUID
    worker_document_id: UUID
    ocr_status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    review_reasons: list[str]
