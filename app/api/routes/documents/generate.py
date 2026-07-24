"""Generate a new HWP or HWPX from a registered template."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.dependencies import (
    get_document_conversion_service,
    get_document_editing_service,
    get_document_record_generation_service,
)
from app.api.openapi import DOCUMENT_GENERATION_TAG
from app.api.schemas.documents import DocumentGeneratePayload
from app.core.config import Settings, get_settings
from app.documents import DocumentConversionService, DocumentFormat
from app.documents.conversion import (
    ConversionEngineUnavailableError,
    DocumentConversionError,
)
from app.documents.editing import (
    DocumentEditingError,
    DocumentEditingService,
    DocumentMutationResult,
    template_display_name,
)
from app.documents.hwpx import HwpxError
from app.documents.records import DocumentRecordGenerationService

from .assets import close_uploads, parse_json_payload, save_named_assets
from .mutation_responses import mutation_file_response, raise_editing_http_error
from .uploads import save_upload, upload_leaf_name

router = APIRouter(tags=[DOCUMENT_GENERATION_TAG])


@router.post(
    "/generate",
    response_class=FileResponse,
    responses={
        404: {"description": "Template was not found"},
        413: {"description": "Asset is too large"},
        422: {"description": "Invalid generation payload or unsupported generation"},
    },
)
def generate_document(
    payload: Annotated[
        str,
        Form(
            description=(
                "JSON object containing template_id, format, values, "
                "application_options, and asset filename mappings"
            )
        ),
    ],
    editing_service: Annotated[
        DocumentEditingService, Depends(get_document_editing_service)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    assets: Annotated[
        list[UploadFile] | None,
        File(description="Photo and signature files referenced by payload.assets"),
    ] = None,
) -> FileResponse:
    temporary_directory = Path(tempfile.mkdtemp(prefix="fowoco-generate-"))
    try:
        command = parse_json_payload(payload, DocumentGeneratePayload)
        asset_paths = save_named_assets(
            assets,
            command.assets,
            temporary_directory,
            max_bytes=settings.document_upload_max_bytes,
        )
        destination_path = (
            temporary_directory / f"output.{command.format.value}"
        )
        try:
            result = editing_service.generate(
                command.template_id,
                command.format,
                destination_path,
                values=command.values,
                application_options=command.application_options,
                assets=asset_paths,
            )
        except DocumentEditingError as exc:
            raise_editing_http_error(exc)
        return mutation_file_response(
            result,
            original_filename=(
                f"{template_display_name(command.template_id)}."
                f"{command.format.value}"
            ),
            temporary_directory=temporary_directory,
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    finally:
        close_uploads(assets)


@router.post(
    "/generate/from-txt",
    response_class=FileResponse,
    summary="TXT 테스트 데이터로 HWP 문서 생성",
    description=(
        "DB 연결 전 테스트를 위해 UTF-8 key=value 형식의 TXT 레코드를 읽고, "
        "선택한 고정 양식의 XML 셀 규칙에 따라 값을 입력한 뒤 HWP로 변환해 "
        "반환합니다."
    ),
    responses={
        404: {"description": "템플릿 또는 템플릿 매핑 규칙을 찾을 수 없음"},
        413: {"description": "TXT 파일 크기 제한 초과"},
        422: {"description": "잘못된 TXT 형식 또는 기입할 수 없는 레코드"},
        503: {"description": "HWP 변환 엔진을 사용할 수 없음"},
    },
)
def generate_document_from_txt(
    template_id: Annotated[
        str,
        Form(description="값을 입력할 등록 템플릿 ID", min_length=1),
    ],
    file: Annotated[
        UploadFile,
        File(description="UTF-8 key=value 형식의 테스트 레코드 TXT"),
    ],
    record_service: Annotated[
        DocumentRecordGenerationService,
        Depends(get_document_record_generation_service),
    ],
    conversion_service: Annotated[
        DocumentConversionService,
        Depends(get_document_conversion_service),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    filename = upload_leaf_name(file.filename or "record.txt")
    if Path(filename).suffix.casefold() != ".txt":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="record file must use the .txt extension",
        )

    temporary_directory = Path(tempfile.mkdtemp(prefix="fowoco-record-generate-"))
    try:
        record_path = temporary_directory / "record.txt"
        save_upload(
            file,
            record_path,
            max_bytes=settings.document_upload_max_bytes,
            description="TXT record",
        )
        try:
            hwpx_result = record_service.generate_from_txt(
                record_path,
                temporary_directory / "output.hwpx",
                template_id=template_id,
            )
        except DocumentEditingError as exc:
            raise_editing_http_error(exc)
        try:
            hwp_path = conversion_service.convert(
                hwpx_result.destination,
                temporary_directory / "output.hwp",
                source_format=DocumentFormat.HWPX,
                target_format=DocumentFormat.HWP,
            )
        except ConversionEngineUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except (DocumentConversionError, HwpxError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        result = DocumentMutationResult(
            destination=hwp_path,
            format=DocumentFormat.HWP,
            template_id=hwpx_result.template_id,
            changed_fields=hwpx_result.changed_fields,
        )
        return mutation_file_response(
            result,
            original_filename=f"{template_display_name(template_id)}.hwp",
            temporary_directory=temporary_directory,
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    finally:
        file.file.close()


__all__ = ["router"]
