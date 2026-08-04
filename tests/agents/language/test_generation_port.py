import httpx
import pytest
from pydantic import ValidationError

from app.agents.language.generation.models import (
    EasyKoreanDraft,
    SemanticValidationDraft,
    TranslationDraft,
)
from app.agents.language.generation.openai_compatible import (
    GenerationError,
    GenerationHTTPError,
    GenerationResponseTooLargeError,
    GenerationSchemaError,
    GenerationTransportError,
    OpenAICompatibleGenerationPort,
)


def test_easy_korean_draft_valid() -> None:
    draft = EasyKoreanDraft(
        request_reason=" 체류기간 연장 신청 ",
        requested_items=("여권 사본", "근로계약서 사본"),
        submission_method="관할 출입국 관서 방문 제출",
    )
    assert draft.request_reason == "체류기간 연장 신청"
    assert draft.requested_items == ("여권 사본", "근로계약서 사본")
    assert draft.submission_method == "관할 출입국 관서 방문 제출"


def test_easy_korean_draft_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EasyKoreanDraft.model_validate(
            {
                "request_reason": "사유",
                "requested_items": ["서류"],
                "submission_method": "방법",
                "extra_field": "forbidden",
            }
        )


def test_easy_korean_draft_bounds_and_empty() -> None:
    with pytest.raises(ValidationError):
        EasyKoreanDraft(
            request_reason="",
            requested_items=("서류",),
            submission_method="방법",
        )

    with pytest.raises(ValidationError):
        EasyKoreanDraft(
            request_reason="a" * 1001,
            requested_items=("서류",),
            submission_method="방법",
        )

    with pytest.raises(ValidationError):
        EasyKoreanDraft(
            request_reason="사유",
            requested_items=("b" * 401,),
            submission_method="방법",
        )


def test_translation_draft_valid_and_bounds() -> None:
    draft = TranslationDraft(
        translated_reason="Extension of stay period",
        translated_items=("Passport copy", "Employment contract copy"),
        translated_submission_method="Visit local immigration office",
    )
    assert draft.translated_reason == "Extension of stay period"

    with pytest.raises(ValidationError):
        TranslationDraft(
            translated_reason="",
            translated_items=(),
            translated_submission_method="method",
        )


def test_semantic_validation_draft_contract() -> None:
    valid = SemanticValidationDraft(
        status="passed",
        failed_checks=(),
        inconclusive_checks=(),
    )
    assert valid.status == "passed"

    with pytest.raises(ValidationError):
        SemanticValidationDraft(
            status="passed",
            failed_checks=("request_reason.present",),
            inconclusive_checks=(),
        )

    with pytest.raises(ValidationError):
        SemanticValidationDraft(
            status="failed",
            failed_checks=(),
            inconclusive_checks=(),
        )

    with pytest.raises(ValidationError):
        SemanticValidationDraft(
            status="inconclusive",
            failed_checks=(),
            inconclusive_checks=(),
        )


def test_adapter_sends_versioned_system_prompt() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        body = (
            '{"choices": [{"message": {"content": "{\\"request_reason\\": \\"사유\\", '
            '\\"requested_items\\": [\\"서류\\"], \\"submission_method\\": \\"방법\\"}"}}]}'
        )
        return httpx.Response(200, content=body.encode("utf-8"))

    transport = httpx.MockTransport(handle_request)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret-key-123",
        model="gpt-4o-mini",
        transport=transport,
    )

    draft = port.generate(
        operation="easy_korean",
        payload={
            "request_reason": "사유",
            "requested_items": ["서류"],
            "submission_method": "방법",
        },
        response_model=EasyKoreanDraft,
    )
    assert draft.request_reason == "사유"
    assert len(captured_requests) == 1
    req_json = httpx.Response(200, content=captured_requests[0].content).json()
    assert req_json["messages"][0]["role"] == "system"
    assert "알기 쉬운" in req_json["messages"][0]["content"]


def test_adapter_sends_json_schema_response_contract() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        body = (
            '{"choices": [{"message": {"content": "{\\"request_reason\\": \\"사유\\", '
            '\\"requested_items\\": [\\"서류\\"], \\"submission_method\\": \\"방법\\"}"}}]}'
        )
        return httpx.Response(200, content=body.encode("utf-8"))

    transport = httpx.MockTransport(handle_request)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret-key-123",
        model="gpt-4o-mini",
        transport=transport,
    )

    port.generate(
        operation="easy_korean",
        payload={"request_reason": "사유"},
        response_model=EasyKoreanDraft,
    )

    req = captured_requests[0]
    assert req.headers["Authorization"] == "Bearer secret-key-123"
    req_json = httpx.Response(200, content=req.content).json()
    assert req_json["response_format"]["type"] == "json_schema"
    assert req_json["response_format"]["json_schema"]["strict"] is True
    assert req_json["response_format"]["json_schema"]["name"] == "EasyKoreanDraft"


def test_adapter_parses_valid_json() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        body = (
            '{"choices": [{"message": {"content": "{\\"status\\": \\"passed\\", '
            '\\"failed_checks\\": [], \\"inconclusive_checks\\": []}"}}]}'
        )
        return httpx.Response(200, content=body.encode("utf-8"))

    transport = httpx.MockTransport(handle_request)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret",
        model="gpt-4o-mini",
        transport=transport,
    )

    draft = port.generate(
        operation="semantic_validation",
        payload={},
        response_model=SemanticValidationDraft,
    )
    assert draft.status == "passed"


def test_adapter_rejects_trailing_non_json_text() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        content_str = (
            '{"request_reason": "사유", "requested_items": ["서류"], '
            '"submission_method": "방법"} extra prose'
        )
        body_dict = {"choices": [{"message": {"content": content_str}}]}
        return httpx.Response(200, json=body_dict)

    transport = httpx.MockTransport(handle_request)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret",
        model="gpt-4o-mini",
        transport=transport,
    )

    with pytest.raises(GenerationSchemaError):
        port.generate(
            operation="easy_korean",
            payload={},
            response_model=EasyKoreanDraft,
        )


def test_adapter_rejects_response_over_one_mebibyte() -> None:
    huge_text = "a" * (1024 * 1024 + 10)

    def handle_request(request: httpx.Request) -> httpx.Response:
        body = f'{{"choices": [{{"message": {{"content": "{huge_text}"}}}} calculations]}}'
        return httpx.Response(200, content=body.encode("utf-8"))

    transport = httpx.MockTransport(handle_request)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret",
        model="gpt-4o-mini",
        transport=transport,
    )

    with pytest.raises(GenerationResponseTooLargeError):
        port.generate(
            operation="easy_korean",
            payload={},
            response_model=EasyKoreanDraft,
        )


def test_adapter_maps_429_5xx_and_timeout_to_typed_errors() -> None:
    def handle_request_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b'{"error": "rate limit"}')

    transport = httpx.MockTransport(handle_request_429)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret",
        model="gpt-4o-mini",
        transport=transport,
    )

    with pytest.raises(GenerationTransportError):
        port.generate(
            operation="easy_korean",
            payload={},
            response_model=EasyKoreanDraft,
        )


def test_adapter_maps_400_to_http_error() -> None:
    def handle_request_400(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b'{"error": "bad request"}')

    transport = httpx.MockTransport(handle_request_400)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret",
        model="gpt-4o-mini",
        transport=transport,
    )

    with pytest.raises(GenerationHTTPError):
        port.generate(
            operation="easy_korean",
            payload={},
            response_model=EasyKoreanDraft,
        )


def test_adapter_retries_transport_once_only() -> None:
    attempts = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, content=b'{"error": "server error"}')
        body = (
            '{"choices": [{"message": {"content": "{\\"request_reason\\": \\"사유\\", '
            '\\"requested_items\\": [\\"서류\\"], \\"submission_method\\": \\"방법\\"}"}}]}'
        )
        return httpx.Response(200, content=body.encode("utf-8"))

    transport = httpx.MockTransport(handle_request)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret",
        model="gpt-4o-mini",
        transport=transport,
    )

    draft = port.generate(
        operation="easy_korean",
        payload={},
        response_model=EasyKoreanDraft,
    )
    assert draft.request_reason == "사유"
    assert attempts == 2


def test_adapter_never_logs_api_key_or_raw_response() -> None:
    secret_key = "super-secret-api-key-9999"

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b'{"secret_internal_detail": "sensitive_data"}')

    transport = httpx.MockTransport(handle_request)
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key=secret_key,
        model="gpt-4o-mini",
        transport=transport,
    )

    with pytest.raises(GenerationError) as exc_info:
        port.generate(
            operation="easy_korean",
            payload={},
            response_model=EasyKoreanDraft,
        )

    err_str = str(exc_info.value)
    assert secret_key not in err_str
    assert "sensitive_data" not in err_str


def test_prompt_spy_contains_no_worker_company_documents_or_source_text() -> None:
    port = OpenAICompatibleGenerationPort(
        base_url="https://api.fake-llm.com/v1",
        api_key="secret",
        model="gpt-4o-mini",
    )
    for op in ("easy_korean", "translation", "semantic_validation", "correction"):
        prompt = port.get_system_prompt(op)  # type: ignore[arg-type]
        assert "worker_id" not in prompt
        assert "company" not in prompt
