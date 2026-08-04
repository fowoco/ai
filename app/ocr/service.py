from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.ocr.models import (
    ClovaProviderError,
    ClovaTimeoutError,
    InvalidOcrRequest,
    OcrCommand,
    OcrProcessResult,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
    TemplateResolutionError,
    WorkerDocumentNotFound,
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
        repository: Any,
        confidence_threshold: float,
        clock: Callable[[], datetime],
    ) -> None:
        self._resolver = resolver
        self._clova_client = clova_client
        self._repository = repository
        self._confidence_threshold = confidence_threshold
        self._clock = clock

    async def process(self, command: OcrCommand) -> OcrProcessResult:
        self._validate_file(command)
        try:
            selection = self._resolver.resolve(command.document_type, command.country_code)
        except TemplateResolutionError as exc:
            raise InvalidOcrRequest(str(exc)) from exc

        exists = await self._repository.verify_scope(command.scope, command.document_type)
        if not exists:
            raise WorkerDocumentNotFound("worker document was not found")

        await self._repository.mark_processing(command.scope, command.request_id)
        try:
            raw = await self._clova_client.infer(
                command.file,
                selection.template_ids,
                command.request_id,
            )
        except ClovaTimeoutError as exc:
            await self._repository.mark_failed(
                command.scope,
                command.request_id,
                "CLOVA_TIMEOUT",
                self._clock(),
            )
            raise OcrUpstreamTimeout("CLOVA OCR timed out") from exc
        except ClovaProviderError as exc:
            await self._repository.mark_failed(
                command.scope,
                command.request_id,
                "CLOVA_ERROR",
                self._clock(),
            )
            raise OcrUpstreamFailure("CLOVA OCR failed") from exc

        result = normalize_clova_response(
            raw,
            selection,
            self._confidence_threshold,
            self._resolver,
        )
        await self._repository.save_result(command.scope, result, self._clock())
        return OcrProcessResult(
            request_id=command.request_id,
            worker_document_id=command.scope.worker_document_id,
            status=result.status,
            matched_template_id=result.matched_template_id,
            document_side=result.document_side,
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
            raise InvalidOcrRequest("OCR file is too large")
        if (
            not file.filename
            or file.filename in {".", ".."}
            or "/" in file.filename
            or "\\" in file.filename
            or "\x00" in file.filename
        ):
            raise InvalidOcrRequest("invalid OCR filename")
