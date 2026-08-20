from datetime import date
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ocr_service
from app.core.config import get_settings
from app.main import create_app
from app.ocr.models import (
    DocumentSide,
    OcrFileTooLarge,
    OcrProcessResult,
    OcrStatus,
    OcrUpstreamFailure,
    OcrUpstreamTimeout,
)

REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
DOCUMENT_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


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
            fields={
                "passport_number": "M00000000",
                "date_of_birth": date(2000, 1, 2),
            },
            field_confidences={"passport_number": 0.99, "date_of_birth": 0.98},
            review_reasons=(),
        )
        self.error = error
        self.commands = []

    async def process(self, command):
        self.commands.append(command)
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
            else {
                "Authorization": "Bearer internal-test-token",
                "X-Request-Id": str(REQUEST_ID),
            }
        ),
        data=data or request_data(),
        files={"file": ("sample.png", b"synthetic-image-bytes", "image/png")},
    )


def test_endpoint_returns_normalized_result_and_builds_stateless_command(
    authenticated_client,
) -> None:
    client, service = authenticated_client

    response = post_ocr(client)

    assert response.status_code == 200
    assert response.json() == {
        "request_id": str(REQUEST_ID),
        "worker_document_id": str(DOCUMENT_ID),
        "ocr_status": "SUCCEEDED",
        "matched_template_id": 43019,
        "document_side": None,
        "fields": {
            "passport_number": "M00000000",
            "date_of_birth": "2000-01-02",
        },
        "field_confidences": {
            "passport_number": 0.99,
            "date_of_birth": 0.98,
        },
        "review_reasons": [],
    }
    command = service.commands[0]
    assert command.worker_document_id == DOCUMENT_ID
    assert command.file.content == b"synthetic-image-bytes"
    assert not hasattr(command, "worker_id")
    assert not hasattr(command, "company_id")


def test_openapi_exposes_stateless_form_and_response_contract(
    authenticated_client,
) -> None:
    client, _ = authenticated_client

    schema = client.get("/openapi.json").json()
    operation = schema["paths"][
        "/internal/v1/ocr/worker-documents/{worker_document_id}"
    ]["post"]
    body_ref = operation["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    body_name = body_ref.rsplit("/", 1)[-1]
    body_properties = schema["components"]["schemas"][body_name]["properties"]
    response_properties = schema["components"]["schemas"]["OcrResponse"]["properties"]

    assert set(body_properties) == {
        "request_id",
        "document_type",
        "file",
        "country_code",
    }
    assert "fields" in response_properties
    assert "field_confidences" in response_properties
    assert any(parameter["name"] == "X-Request-Id" for parameter in operation["parameters"])


def test_endpoint_requires_configured_internal_bearer(authenticated_client) -> None:
    client, service = authenticated_client

    response = post_ocr(client, headers={"X-Request-Id": str(REQUEST_ID)})

    assert response.status_code == 401
    assert service.commands == []


def test_endpoint_requires_x_request_id(authenticated_client) -> None:
    client, service = authenticated_client

    response = post_ocr(
        client,
        headers={"Authorization": "Bearer internal-test-token"},
    )

    assert response.status_code == 422
    assert service.commands == []


def test_endpoint_rejects_mismatched_request_ids(authenticated_client) -> None:
    client, service = authenticated_client

    response = post_ocr(
        client,
        headers={
            "Authorization": "Bearer internal-test-token",
            "X-Request-Id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid OCR request"}
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


def test_invalid_x_request_id_returns_422(authenticated_client) -> None:
    client, service = authenticated_client

    response = post_ocr(
        client,
        headers={
            "Authorization": "Bearer internal-test-token",
            "X-Request-Id": "not-a-uuid",
        },
    )

    assert response.status_code == 422
    assert service.commands == []


def test_missing_passport_country_is_forwarded_for_vietnam_fallback(
    authenticated_client,
) -> None:
    client, service = authenticated_client
    data = request_data()
    data.pop("country_code")

    response = post_ocr(client, data=data)

    assert response.status_code == 200
    assert service.commands[0].country_code is None


def test_blank_passport_country_is_forwarded_for_vietnam_fallback(
    authenticated_client,
) -> None:
    client, service = authenticated_client

    response = post_ocr(client, data=request_data(country_code=""))

    assert response.status_code == 200
    assert service.commands[0].country_code is None


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (OcrFileTooLarge("too large"), 413, "OCR file is too large"),
        (OcrUpstreamFailure("provider failed"), 502, "OCR provider failed"),
        (OcrUpstreamTimeout("provider timed out"), 504, "OCR provider timed out"),
    ],
)
def test_application_errors_are_translated_to_safe_http_statuses(
    authenticated_client,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    client, service = authenticated_client
    service.error = error

    response = post_ocr(client)

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_review_required_is_returned_with_fields(authenticated_client) -> None:
    client, service = authenticated_client
    service.result = OcrProcessResult(
        request_id=REQUEST_ID,
        worker_document_id=DOCUMENT_ID,
        status=OcrStatus.REVIEW_REQUIRED,
        matched_template_id=43025,
        document_side=DocumentSide.BACK,
        fields={"stay_expiration_date": date(2028, 3, 1)},
        field_confidences={"stay_expiration_date": 0.51},
        review_reasons=("low_confidence:stay_expiration_date",),
    )

    response = post_ocr(client)

    assert response.status_code == 200
    assert response.json()["ocr_status"] == "REVIEW_REQUIRED"
    assert response.json()["document_side"] == "BACK"
    assert response.json()["fields"] == {"stay_expiration_date": "2028-03-01"}
    assert response.json()["field_confidences"] == {"stay_expiration_date": 0.51}


@pytest.mark.parametrize(
    ("missing_name", "message"),
    [
        ("FOWOCO_CLOVA_OCR_INVOKE_URL", "clova_ocr_invoke_url"),
        ("FOWOCO_CLOVA_OCR_SECRET", "clova_ocr_secret"),
        ("FOWOCO_INTERNAL_API_TOKEN", "internal_api_token"),
    ],
)
def test_enabled_ocr_rejects_missing_required_startup_setting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    missing_name: str,
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_ENABLED", "true")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_INVOKE_URL", "https://example.invalid/infer")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_SECRET", "local-test-secret")
    monkeypatch.setenv("FOWOCO_INTERNAL_API_TOKEN", "internal-test-token")
    monkeypatch.delenv(missing_name, raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match=message):
        create_app()


def test_enabled_ocr_accepts_missing_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_ENABLED", "true")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_INVOKE_URL", "https://example.invalid/infer")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_SECRET", "local-test-secret")
    monkeypatch.setenv("FOWOCO_INTERNAL_API_TOKEN", "internal-test-token")
    monkeypatch.delenv("FOWOCO_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.clova_ocr_enabled is True
