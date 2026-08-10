from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status

from app.api.dependencies import get_ocr_service
from app.api.openapi import OCR_TAG
from app.api.schemas.ocr import OcrResponse
from app.api.security import verify_internal_bearer
from app.ocr.models import (
    DocumentType,
    InvalidOcrRequest,
    OcrCommand,
    OcrFile,
    OcrFileTooLarge,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
)
from app.ocr.service import MAX_FILE_BYTES, OcrService

router = APIRouter(prefix="/internal/v1/ocr", tags=[OCR_TAG])


@router.post(
    "/worker-documents/{worker_document_id}",
    response_model=OcrResponse,
    dependencies=[Depends(verify_internal_bearer)],
    summary="Run CLOVA Template OCR for one worker document",
)
async def recognize_worker_document(
    worker_document_id: UUID,
    request_id: Annotated[UUID, Form()],
    x_request_id: Annotated[UUID, Header(alias="X-Request-Id")],
    document_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File()],
    service: Annotated[OcrService, Depends(get_ocr_service)],
    country_code: Annotated[str | None, Form()] = None,
) -> OcrResponse:
    if x_request_id != request_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OCR request",
        )

    content = await file.read(MAX_FILE_BYTES + 1)
    await file.close()
    command = OcrCommand(
        request_id=request_id,
        worker_document_id=worker_document_id,
        document_type=document_type,
        country_code=country_code,
        file=OcrFile(
            filename=file.filename or "",
            content_type=file.content_type or "",
            content=content,
        ),
    )
    try:
        result = await service.process(command)
    except OcrFileTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="OCR file is too large",
        ) from exc
    except InvalidOcrRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OCR request",
        ) from exc
    except OcrUpstreamTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="OCR provider timed out",
        ) from exc
    except OcrUpstreamFailure as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OCR provider failed",
        ) from exc
    return OcrResponse(
        request_id=result.request_id,
        worker_document_id=result.worker_document_id,
        ocr_status=result.status,
        matched_template_id=result.matched_template_id,
        document_side=result.document_side,
        fields=dict(result.fields),
        field_confidences=dict(result.field_confidences),
        review_reasons=list(result.review_reasons),
    )
