from datetime import date
from typing import Any
from uuid import UUID

import pytest

from app.ocr import models as ocr_models
from app.ocr.models import (
    ClovaProviderError,
    ClovaTimeoutError,
    DocumentType,
    InvalidOcrRequest,
    OcrCommand,
    OcrFile,
    OcrStatus,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
)
from app.ocr.service import OcrService
from app.ocr.template_resolver import TemplateResolver

REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
DOCUMENT_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


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
        worker_document_id=DOCUMENT_ID,
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


def build_service(
    clova: FakeClovaClient | None = None,
) -> tuple[OcrService, FakeClovaClient]:
    actual_clova = clova or FakeClovaClient()
    return (
        OcrService(
            resolver=TemplateResolver(),
            clova_client=actual_clova,
            confidence_threshold=0.80,
        ),
        actual_clova,
    )


@pytest.mark.asyncio
async def test_success_calls_clova_and_returns_normalized_result() -> None:
    service, clova = build_service()

    result = await service.process(command())

    assert clova.calls == [((43019,), "sample.png")]
    assert result.status is OcrStatus.SUCCEEDED
    assert result.worker_document_id == DOCUMENT_ID
    assert result.matched_template_id == 43019
    assert result.fields == {
        "passport_number": "M00000000",
        "surname": "TEST",
        "given_names": "USER",
        "date_of_birth": date(2000, 1, 2),
        "passport_expiry_date": date(2030, 1, 2),
    }
    assert result.field_confidences["passport_number"] == 0.99


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"content": b""}, "empty"),
        ({"content_type": "image/gif"}, "content type"),
        ({"filename": "../sample.png"}, "filename"),
        ({"filename": "..\\sample.png"}, "filename"),
    ],
)
async def test_invalid_file_is_rejected_before_provider_call(
    overrides: dict[str, object],
    message: str,
) -> None:
    service, clova = build_service()

    with pytest.raises(InvalidOcrRequest, match=message):
        await service.process(command(**overrides))  # type: ignore[arg-type]

    assert clova.calls == []


@pytest.mark.asyncio
async def test_oversized_file_has_a_distinct_application_error() -> None:
    service, clova = build_service()

    with pytest.raises(ocr_models.OcrFileTooLarge, match="too large"):
        await service.process(command(content=b"x" * (20 * 1024 * 1024 + 1)))

    assert clova.calls == []


@pytest.mark.asyncio
async def test_unsupported_passport_country_is_an_invalid_request() -> None:
    service, clova = build_service()

    with pytest.raises(InvalidOcrRequest, match="unsupported passport country"):
        await service.process(command(country_code="USA"))

    assert clova.calls == []


@pytest.mark.asyncio
async def test_clova_timeout_raises_safe_timeout() -> None:
    service, _ = build_service(FakeClovaClient(error=ClovaTimeoutError("timed out")))

    with pytest.raises(OcrUpstreamTimeout, match="timed out"):
        await service.process(command())


@pytest.mark.asyncio
async def test_clova_provider_error_raises_safe_failure() -> None:
    service, _ = build_service(
        FakeClovaClient(error=ClovaProviderError("request failed"))
    )

    with pytest.raises(OcrUpstreamFailure, match="failed"):
        await service.process(command())


@pytest.mark.asyncio
async def test_review_required_result_returns_fields_and_confidences() -> None:
    service, _ = build_service(
        FakeClovaClient(response=successful_passport_response(confidence=0.50))
    )

    result = await service.process(command())

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.fields["passport_number"] == "M00000000"
    assert result.field_confidences["passport_number"] == 0.50
    assert result.review_reasons == ("low_confidence:passport_number",)
