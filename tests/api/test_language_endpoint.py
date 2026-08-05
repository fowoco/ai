import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.language.contracts import (
    ComponentStatus,
    ComponentValidation,
    LanguageAssistantInput,
    LanguageAssistantOutput,
    RetrievalMetadata,
    ValidationSummary,
)
from app.api.dependencies import get_language_assistant_service
from app.api.schemas.language import (
    LanguageAssistantHttpRequest,
    project_http_request,
)
from app.main import app

FIXTURES_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "language"
)


@pytest.fixture
def request_payload() -> dict[str, object]:
    req_file = FIXTURES_DIR / "backend-language-request.json"
    return json.loads(req_file.read_text(encoding="utf-8"))


@pytest.fixture
def response_payload() -> dict[str, object]:
    res_file = FIXTURES_DIR / "backend-language-response.json"
    return json.loads(res_file.read_text(encoding="utf-8"))


class FakeLanguageAssistantService:
    def __init__(self, output: LanguageAssistantOutput | None = None) -> None:
        self.captured_inputs: list[LanguageAssistantInput] = []
        self.output = output

    def invoke(self, request: LanguageAssistantInput) -> LanguageAssistantOutput:
        self.captured_inputs.append(request)
        if self.output is not None:
            return self.output
        return LanguageAssistantOutput(
            worker_id=request.worker_id,
            target_language="en",
            generation_status="success",
            requires_human_review=False,
            standard_korean_text="다음 요청 내용을 확인해 주세요.",
            easy_korean_text="신청 사유: 체류기간 늘림 신청",
            translated_text="Reason: Extension of stay period",
            component_status=ComponentStatus(
                standard_korean="success",
                easy_korean="success",
                translation="success",
            ),
            validation=ValidationSummary(
                standard_korean=ComponentValidation(status="passed", retry_count=0),
                easy_korean=ComponentValidation(status="passed", retry_count=0),
                translation=ComponentValidation(status="passed", retry_count=0),
            ),
            warnings=(),
            retrieval_metadata=RetrievalMetadata(
                dataset_version="v1.0",
                query_strategies=("canonical",),
                reference_ids=("p1",),
                reference_count=1,
                fallback_used=False,
                degraded_components=(),
            ),
        )


@pytest.fixture
def client_with_fake_service(app_instance: FastAPI) -> TestClient:
    fake_service = FakeLanguageAssistantService()
    app_instance.dependency_overrides[get_language_assistant_service] = (
        lambda: fake_service
    )
    client = TestClient(app_instance)
    yield client
    app_instance.dependency_overrides.clear()


@pytest.fixture
def app_instance() -> FastAPI:
    return app


def test_http_request_accepts_required_language_fields(
    request_payload: dict[str, object],
) -> None:
    req = LanguageAssistantHttpRequest.model_validate(request_payload)
    assert req.worker_id == "worker-123"
    assert req.preferred_language == "en"


def test_http_request_accepts_unrelated_shared_context_fields(
    request_payload: dict[str, object],
) -> None:
    req = LanguageAssistantHttpRequest.model_validate(request_payload)
    assert hasattr(req, "extra_parent_field")


def test_http_request_treats_source_text_as_ignored_parent_extra(
    request_payload: dict[str, object],
) -> None:
    req = LanguageAssistantHttpRequest.model_validate(request_payload)
    domain_input = project_http_request(req)
    assert not hasattr(domain_input, "source_text")
    assert "source_text" not in domain_input.model_dump()


def test_http_request_projects_to_strict_domain_input(
    request_payload: dict[str, object],
) -> None:
    req = LanguageAssistantHttpRequest.model_validate(request_payload)
    domain_input = project_http_request(req)
    assert isinstance(domain_input, LanguageAssistantInput)
    assert domain_input.worker_id == "worker-123"


def test_http_request_does_not_serialize_parent_extras_to_service(
    request_payload: dict[str, object],
) -> None:
    req = LanguageAssistantHttpRequest.model_validate(request_payload)
    domain_input = project_http_request(req)
    dumped = domain_input.model_dump(mode="json")
    assert "extra_parent_field" not in dumped
    assert "source_text" not in dumped


def test_http_schema_declares_only_language_fields_and_allows_parent_extras() -> None:
    schema = LanguageAssistantHttpRequest.model_json_schema()
    props = schema.get("properties", {})
    assert "worker_id" in props
    assert "preferred_language" in props
    assert "nationality_code" in props
    assert "request_context" in props
    assert "source_text" not in props


def test_endpoint_returns_structured_output(
    client_with_fake_service: TestClient,
    request_payload: dict[str, object],
) -> None:
    resp = client_with_fake_service.post(
        "/internal/v1/language-assistant",
        json=request_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["worker_id"] == "worker-123"
    assert data["generation_status"] == "success"


def test_endpoint_returns_422_for_missing_request_field(
    client_with_fake_service: TestClient,
) -> None:
    resp = client_with_fake_service.post(
        "/internal/v1/language-assistant",
        json={"worker_id": "worker-123"},
    )
    assert resp.status_code == 422


def test_endpoint_returns_422_for_unsupported_preferred_language_without_fallback(
    client_with_fake_service: TestClient,
    request_payload: dict[str, object],
) -> None:
    payload = {**request_payload, "preferred_language": "unsupported_xyz_language"}
    resp = client_with_fake_service.post(
        "/internal/v1/language-assistant",
        json=payload,
    )
    assert resp.status_code == 422
    err_detail = resp.json()["detail"]
    assert any(item["loc"] == ["body", "preferred_language"] for item in err_detail)


def test_endpoint_ignores_source_text_parent_extra(
    client_with_fake_service: TestClient,
    request_payload: dict[str, object],
) -> None:
    payload_1 = {**request_payload, "source_text": "text A"}
    payload_2 = {**request_payload, "source_text": "text B"}

    resp1 = client_with_fake_service.post(
        "/internal/v1/language-assistant", json=payload_1
    )
    resp2 = client_with_fake_service.post(
        "/internal/v1/language-assistant", json=payload_2
    )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()


def test_endpoint_available_in_openapi_at_exact_path(
    app_instance: FastAPI,
) -> None:
    client = TestClient(app_instance)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    openapi = resp.json()
    assert "/internal/v1/language-assistant" in openapi["paths"]


def test_endpoint_not_mounted_under_api_v1(
    app_instance: FastAPI,
) -> None:
    client = TestClient(app_instance)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    openapi = resp.json()
    assert "/api/v1/internal/v1/language-assistant" not in openapi["paths"]
