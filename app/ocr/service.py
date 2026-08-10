from typing import Any

from app.ocr.models import (
    ClovaProviderError,
    ClovaTimeoutError,
    InvalidOcrRequest,
    OcrCommand,
    OcrFileTooLarge,
    OcrProcessResult,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
    TemplateResolutionError,
)
from app.ocr.normalizer import normalize_clova_response
from app.ocr.template_resolver import TemplateResolver

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "application/pdf"})
MAX_FILE_BYTES = 20 * 1024 * 1024


class OcrService:
    def __init__(
        self,
        *,
        resolver: TemplateResolver,
        clova_client: Any,
        confidence_threshold: float,
    ) -> None:
        self._resolver = resolver
        self._clova_client = clova_client
        self._confidence_threshold = confidence_threshold

    async def process(self, command: OcrCommand) -> OcrProcessResult:
        self._validate_file(command)
        try:
            selection = self._resolver.resolve(command.document_type, command.country_code)
        except TemplateResolutionError as exc:
            raise InvalidOcrRequest(str(exc)) from exc

        try:
            raw = await self._clova_client.infer(
                command.file,
                selection.template_ids,
                command.request_id,
            )
        except ClovaTimeoutError as exc:
            raise OcrUpstreamTimeout("CLOVA OCR timed out") from exc
        except ClovaProviderError as exc:
            raise OcrUpstreamFailure("CLOVA OCR failed") from exc

        result = normalize_clova_response(
            raw,
            selection,
            self._confidence_threshold,
            self._resolver,
        )
        return OcrProcessResult(
            request_id=command.request_id,
            worker_document_id=command.worker_document_id,
            status=result.status,
            matched_template_id=result.matched_template_id,
            document_side=result.document_side,
            fields=dict(result.fields),
            field_confidences=dict(result.field_confidences),
            review_reasons=result.review_reasons,
        )

    @staticmethod
    def _validate_file(command: OcrCommand) -> None:
        file = command.file
        if not file.content:
            raise InvalidOcrRequest("OCR file is empty")
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise InvalidOcrRequest("unsupported OCR content type")
        if len(file.content) > MAX_FILE_BYTES:
            raise OcrFileTooLarge("OCR file is too large")
        if (
            not file.filename
            or file.filename in {".", ".."}
            or "/" in file.filename
            or "\\" in file.filename
            or "\x00" in file.filename
        ):
            raise InvalidOcrRequest("invalid OCR filename")
