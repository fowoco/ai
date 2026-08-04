from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ocr_service
from app.core.config import get_settings
from app.main import create_app
from app.ocr.models import (
    DocumentSide,
    InvalidOcrRequest,
    OcrPersistenceError,
    OcrProcessResult,
    OcrStatus,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
    WorkerDocumentNotFound,
)

REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
DOCUMENT_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
WORKER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
COMPANY_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")


class FakeOcrService:
    def __init__(
        self,
        *,
        result: OcrProcessResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or OcrProcessResult(
            request_id=REQUEST_ID,
            worker_document_id=DOCUMENT_ID,
            status=OcrStatus.SUCCEEDED,
            matched_template_id=43019,
            document_side=None,
            review_reasons=(),
        )
        self.error = error
        self.commands = []

    async def process(self, command):
        self.commands.append(command)
        if command.document_type.value == "PASSPORT_COPY" and not command.country_code:
            raise InvalidOcrRequest("passport country is required")
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def authenticated_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FOWOCO_INTERNAL_API_TOKEN", "internal-test-token")
    get_settings.cache_clear()
    app = create_app()
    service = FakeOcrService()
    app.dependency_overrides[get_ocr_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def request_data(**overrides: str) -> dict[str, str]:
    data = {
        "request_id": str(REQUEST_ID),
        "worker_id": str(WORKER_ID),
        "company_id": str(COMPANY_ID),
        "document_type": "PASSPORT_COPY",
        "country_code": "KOR",
    }
    data.update(overrides)
    return data


def post_ocr(
    client: TestClient,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"/internal/v1/ocr/worker-documents/{DOCUMENT_ID}",
        headers=(
            headers
            if headers is not None
            else {"Authorization": "Bearer internal-test-token"}
        ),
        data=data or request_data(),
        files={"file": ("sample.png", b"synthetic-image-bytes", "image/png")},
    )


def test_endpoint_returns_status_only_and_builds_command(authenticated_client) -> None:
    client, service = authenticated_client

    response = post_ocr(client)

    assert response.status_code == 200
    assert response.json() == {
        "request_id": str(REQUEST_ID),
        "worker_document_id": str(DOCUMENT_ID),
        "ocr_status": "SUCCEEDED",
        "matched_template_id": 43019,
        "document_side": None,
        "review_reasons": [],
    }
    command = service.commands[0]
    assert command.scope.worker_id == WORKER_ID
    assert command.scope.company_id == COMPANY_ID
    assert command.file.content == b"synthetic-image-bytes"
    assert "fields" not in response.json()
    assert "passport_number" not in response.json()


def test_endpoint_requires_configured_internal_bearer(authenticated_client) -> None:
    client, service = authenticated_client

    response = post_ocr(client, headers={})

    assert response.status_code == 401
    assert service.commands == []


def test_disabled_ocr_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOWOCO_INTERNAL_API_TOKEN", "internal-test-token")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = post_ocr(client)

    assert response.status_code == 503


@pytest.mark.parametrize(
    "data",
    [
        request_data(request_id="not-a-uuid"),
        request_data(document_type="UNKNOWN"),
    ],
)
def test_invalid_uuid_or_enum_returns_422(authenticated_client, data) -> None:
    client, service = authenticated_client

    response = post_ocr(client, data=data)

    assert response.status_code == 422
    assert service.commands == []


def test_missing_passport_country_returns_400(authenticated_client) -> None:
    client, _ = authenticated_client
    data = request_data()
    data.pop("country_code")

    response = post_ocr(client, data=data)

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (WorkerDocumentNotFound("not found"), 404),
        (OcrUpstreamFailure("provider failed"), 502),
        (OcrUpstreamTimeout("provider timed out"), 504),
        (OcrPersistenceError("database operation failed"), 500),
    ],
)
def test_application_errors_are_translated_to_safe_http_statuses(
    authenticated_client,
    error: Exception,
    status_code: int,
) -> None:
    client, service = authenticated_client
    service.error = error

    response = post_ocr(client)

    assert response.status_code == status_code
    assert set(response.json()) == {"detail"}


def test_review_required_is_returned_with_http_200(authenticated_client) -> None:
    client, service = authenticated_client
    service.result = OcrProcessResult(
        request_id=REQUEST_ID,
        worker_document_id=DOCUMENT_ID,
        status=OcrStatus.REVIEW_REQUIRED,
        matched_template_id=43025,
        document_side=DocumentSide.BACK,
        review_reasons=("low_confidence:stay_expiration_date",),
    )

    response = post_ocr(client)

    assert response.status_code == 200
    assert response.json()["ocr_status"] == "REVIEW_REQUIRED"
    assert response.json()["document_side"] == "BACK"


@pytest.mark.parametrize(
    ("missing_name", "message"),
    [
        ("FOWOCO_CLOVA_OCR_INVOKE_URL", "clova_ocr_invoke_url"),
        ("FOWOCO_CLOVA_OCR_SECRET", "clova_ocr_secret"),
        ("FOWOCO_DATABASE_URL", "database_url"),
    ],
)
def test_enabled_ocr_rejects_missing_required_startup_setting(
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
    message: str,
) -> None:
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_ENABLED", "true")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_INVOKE_URL", "https://example.invalid/infer")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_SECRET", "local-test-secret")
    monkeypatch.setenv("FOWOCO_DATABASE_URL", "postgresql://example.invalid/test")
    monkeypatch.delenv(missing_name, raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match=message):
        create_app()
