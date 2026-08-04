from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import get_ocr_service
from app.api.openapi import OCR_TAG
from app.api.schemas.ocr import OcrResponse
from app.api.security import verify_internal_bearer
from app.ocr.models import (
    DocumentType,
    InvalidOcrRequest,
    OcrCommand,
    OcrFile,
    OcrPersistenceError,
    OcrScope,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
    WorkerDocumentNotFound,
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
    worker_id: Annotated[UUID, Form()],
    company_id: Annotated[UUID, Form()],
    document_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File()],
    service: Annotated[OcrService, Depends(get_ocr_service)],
    country_code: Annotated[str | None, Form()] = None,
) -> OcrResponse:
    content = await file.read(MAX_FILE_BYTES + 1)
    await file.close()
    command = OcrCommand(
        request_id=request_id,
        scope=OcrScope(
            worker_document_id=worker_document_id,
            worker_id=worker_id,
            company_id=company_id,
        ),
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
    except InvalidOcrRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OCR request",
        ) from exc
    except WorkerDocumentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker document was not found",
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
    except OcrPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OCR persistence failed",
        ) from exc

    return OcrResponse(
        request_id=result.request_id,
        worker_document_id=result.worker_document_id,
        ocr_status=result.status,
        matched_template_id=result.matched_template_id,
        document_side=result.document_side,
        review_reasons=list(result.review_reasons),
    )
