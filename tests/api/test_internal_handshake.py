# slot_catalog·Internal Bearer 테스트
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.slot_catalog import requested_fields_for_api
from app.core.config import get_settings
from app.main import create_app


# missing 슬롯이 sourceHint와 함께 requestedFields로 바뀌는지
def test_requested_fields_for_api_maps_source_hints() -> None:
    fields = requested_fields_for_api(["stay_expiry_date", "wage", "passport_number"])
    by_key = {f["key"]: f["sourceHint"] for f in fields}
    assert by_key["stay_expiry_date"] == "WORKER_DB"
    assert by_key["wage"] == "USER_INPUT"
    assert by_key["passport_number"] == "DOCUMENT_OCR"


def _analysis_body(*, request_id: str = "req-open") -> dict:
    return {
        "requestId": request_id,
        "phase": "PLAN",
        "analysisInput": {"instruction": "체류연장"},
    }


# 토큰 미설정 시 Internal API는 인증 없이 통과
def test_internal_api_open_when_token_unset() -> None:
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post("/internal/v1/analyses", json=_analysis_body())
    assert response.status_code == 200
    body = response.json()
    assert body["requestId"] == "req-open"
    assert "attemptId" not in body


# 토큰 설정 시 Bearer 없으면 401
def test_internal_api_requires_bearer_when_token_set(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("FOWOCO_INTERNAL_API_TOKEN", "secret-token")
    get_settings.cache_clear()
    client = TestClient(create_app())
    denied = client.post(
        "/internal/v1/analyses",
        json={
            "requestId": "req-auth",
            "phase": "PLAN",
            "analysisInput": {"instruction": "체류연장"},
        },
    )
    assert denied.status_code == 401
    ok = client.post(
        "/internal/v1/analyses",
        headers={"Authorization": "Bearer secret-token"},
        json=_analysis_body(request_id="req-auth"),
    )
    assert ok.status_code == 200
    get_settings.cache_clear()
    monkeypatch.delenv("FOWOCO_INTERNAL_API_TOKEN", raising=False)
    get_settings.cache_clear()


def test_required_internal_auth_rejects_startup_without_token(monkeypatch) -> None:
    monkeypatch.setenv("FOWOCO_INTERNAL_API_AUTH_REQUIRED", "true")
    monkeypatch.delenv("FOWOCO_INTERNAL_API_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match="requires internal_api_token"):
            create_app()
    finally:
        get_settings.cache_clear()
