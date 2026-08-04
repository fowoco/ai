from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.ocr.models import (
    ClovaProviderError,
    ClovaTimeoutError,
    DocumentType,
    InvalidOcrRequest,
    OcrCommand,
    OcrFile,
    OcrPersistenceError,
    OcrScope,
    OcrStatus,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
    WorkerDocumentNotFound,
)
from app.ocr.service import OcrService
from app.ocr.template_resolver import TemplateResolver

REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
DOCUMENT_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
WORKER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
COMPANY_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
NOW = datetime(2026, 8, 4, 15, 30, tzinfo=UTC)


def field(name: str, text: str, confidence: float = 0.99) -> dict[str, object]:
    return {"name": name, "inferText": text, "inferConfidence": confidence}


def successful_passport_response(confidence: float = 0.99) -> dict[str, object]:
    return {
        "images": [
            {
                "inferResult": "SUCCESS",
                "matchedTemplate": {"id": 43019, "name": "synthetic"},
                "fields": [
                    field("passport_number", "M00000000", confidence),
                    field("surname", "TEST"),
                    field("given_names", "USER"),
                    field("nationality", "KOR"),
                    field("date_of_birth", "2000-01-02"),
                    field("passport_expiry_date", "2030-01-02"),
                ],
            }
        ]
    }


def command(
    *,
    content: bytes = b"synthetic-image-bytes",
    content_type: str = "image/png",
    filename: str = "sample.png",
    document_type: DocumentType = DocumentType.PASSPORT_COPY,
    country_code: str | None = "KOR",
) -> OcrCommand:
    return OcrCommand(
        request_id=REQUEST_ID,
        scope=OcrScope(DOCUMENT_ID, WORKER_ID, COMPANY_ID),
        document_type=document_type,
        country_code=country_code,
        file=OcrFile(filename, content_type, content),
    )


class FakeClovaClient:
    def __init__(
        self,
        response: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or successful_passport_response()
        self.error = error
        self.calls: list[tuple[tuple[int, ...], str]] = []

    async def infer(
        self,
        file: OcrFile,
        template_ids: tuple[int, ...],
        request_id: UUID,
    ) -> dict[str, Any]:
        assert request_id == REQUEST_ID
        self.calls.append((template_ids, file.filename))
        if self.error:
            raise self.error
        return self.response


class FakeRepository:
    def __init__(
        self,
        *,
        scope_exists: bool = True,
        fail_on: str | None = None,
    ) -> None:
        self.scope_exists = scope_exists
        self.fail_on = fail_on
        self.calls: list[str] = []
        self.saved_result = None
        self.failed_args = None

    def _record(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_on == name:
            raise OcrPersistenceError("database operation failed")

    async def verify_scope(self, scope: OcrScope, document_type: DocumentType) -> bool:
        self._record("verify_scope")
        assert scope.worker_document_id == DOCUMENT_ID
        assert document_type in DocumentType
        return self.scope_exists

    async def mark_processing(self, scope: OcrScope, request_id: UUID) -> None:
        self._record("mark_processing")

    async def save_result(
        self,
        scope: OcrScope,
        result: Any,
        processed_at: datetime,
        request_id: UUID,
    ) -> None:
        self._record("save_result")
        self.saved_result = result
        assert processed_at == NOW
        assert request_id == REQUEST_ID

    async def mark_failed(
        self,
        scope: OcrScope,
        request_id: UUID,
        error_code: str,
        processed_at: datetime,
    ) -> None:
        self._record("mark_failed")
        self.failed_args = (scope, request_id, error_code, processed_at)


def build_service(
    repository: FakeRepository | None = None,
    clova: FakeClovaClient | None = None,
) -> tuple[OcrService, FakeRepository, FakeClovaClient]:
    actual_repository = repository or FakeRepository()
    actual_clova = clova or FakeClovaClient()
    return (
        OcrService(
            resolver=TemplateResolver(),
            clova_client=actual_clova,
            repository=actual_repository,
            confidence_threshold=0.80,
            clock=lambda: NOW,
        ),
        actual_repository,
        actual_clova,
    )


@pytest.mark.asyncio
async def test_success_orchestrates_scope_processing_clova_and_save_in_order() -> None:
    service, repository, clova = build_service()

    result = await service.process(command())

    assert repository.calls == ["verify_scope", "mark_processing", "save_result"]
    assert clova.calls == [((43019,), "sample.png")]
    assert result.status is OcrStatus.SUCCEEDED
    assert result.worker_document_id == DOCUMENT_ID
    assert result.matched_template_id == 43019


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_command", "message"),
    [
        (command(content=b""), "empty"),
        (command(content_type="image/gif"), "content type"),
        (command(content=b"x" * (20 * 1024 * 1024 + 1)), "too large"),
        (command(filename="../sample.png"), "filename"),
        (command(filename="..\\sample.png"), "filename"),
    ],
)
async def test_invalid_file_is_rejected_before_database_state_changes(
    invalid_command: OcrCommand,
    message: str,
) -> None:
    service, repository, clova = build_service()

    with pytest.raises(InvalidOcrRequest, match=message):
        await service.process(invalid_command)

    assert repository.calls == []
    assert clova.calls == []


@pytest.mark.asyncio
async def test_missing_scoped_worker_document_returns_not_found_before_clova() -> None:
    repository = FakeRepository(scope_exists=False)
    service, _, clova = build_service(repository=repository)

    with pytest.raises(WorkerDocumentNotFound):
        await service.process(command())

    assert repository.calls == ["verify_scope"]
    assert clova.calls == []


@pytest.mark.asyncio
async def test_unsupported_passport_country_is_an_invalid_request() -> None:
    service, repository, clova = build_service()

    with pytest.raises(InvalidOcrRequest, match="unsupported passport country"):
        await service.process(command(country_code="USA"))

    assert repository.calls == []
    assert clova.calls == []


@pytest.mark.asyncio
async def test_clova_timeout_marks_failed_then_raises_timeout() -> None:
    clova = FakeClovaClient(error=ClovaTimeoutError("timed out"))
    service, repository, _ = build_service(clova=clova)

    with pytest.raises(OcrUpstreamTimeout):
        await service.process(command())

    assert repository.calls == ["verify_scope", "mark_processing", "mark_failed"]
    assert repository.failed_args == (command().scope, REQUEST_ID, "CLOVA_TIMEOUT", NOW)


@pytest.mark.asyncio
async def test_clova_provider_error_marks_failed_then_raises_upstream_failure() -> None:
    clova = FakeClovaClient(error=ClovaProviderError("request failed"))
    service, repository, _ = build_service(clova=clova)

    with pytest.raises(OcrUpstreamFailure):
        await service.process(command())

    assert repository.calls == ["verify_scope", "mark_processing", "mark_failed"]
    assert repository.failed_args == (command().scope, REQUEST_ID, "CLOVA_ERROR", NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on", ["verify_scope", "mark_processing", "save_result"])
async def test_persistence_failure_propagates_without_becoming_provider_error(
    fail_on: str,
) -> None:
    service, _, _ = build_service(repository=FakeRepository(fail_on=fail_on))

    with pytest.raises(OcrPersistenceError):
        await service.process(command())


@pytest.mark.asyncio
async def test_review_required_result_is_saved_and_returned() -> None:
    clova = FakeClovaClient(response=successful_passport_response(confidence=0.50))
    service, repository, _ = build_service(clova=clova)

    result = await service.process(command())

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert repository.saved_result.status is OcrStatus.REVIEW_REQUIRED
    assert result.review_reasons == ("low_confidence:passport_number",)
