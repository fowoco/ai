import json

import httpx
import pytest

from app.agents.language.generation.models import EasyKoreanDraft
from app.agents.language.generation.ollama import OllamaGenerationPort
from app.agents.language.generation.openai_compatible import GenerationSchemaError


def _valid_easy_korean_content() -> str:
    return json.dumps(
        {
            "request_reason": "체류기간 연장 신청",
            "requested_items": ["여권 사본"],
            "submission_method": "출입국 관서 방문",
        },
        ensure_ascii=False,
    )


def test_ollama_adapter_sends_native_schema_contract() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "gemma4:26b-mlx",
                "message": {
                    "role": "assistant",
                    "content": _valid_easy_korean_content(),
                },
                "done": True,
            },
        )

    port = OllamaGenerationPort(
        base_url="http://localhost:11434/v1",
        model="gemma4:26b-mlx",
        transport=httpx.MockTransport(handle_request),
    )

    draft = port.generate(
        operation="easy_korean",
        payload={
            "request_reason": "체류기간 연장 신청",
            "requested_items": ["여권 사본"],
            "submission_method": "출입국 관서 방문",
        },
        response_model=EasyKoreanDraft,
    )

    assert draft.request_reason == "체류기간 연장 신청"
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert str(request.url) == "http://localhost:11434/api/chat"
    request_body = json.loads(request.content)
    assert request_body["stream"] is False
    assert request_body["format"]["required"] == [
        "request_reason",
        "requested_items",
        "submission_method",
    ]
    assert request_body["options"] == {"temperature": 0}
    system_prompt = request_body["messages"][0]["content"]
    assert "request_reason" in system_prompt
    assert "requested_items" in system_prompt
    assert "submission_method" in system_prompt


def test_ollama_adapter_disables_thinking_for_structured_generation() -> None:
    captured_requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "gemma4:26b-mlx",
                "message": {
                    "role": "assistant",
                    "content": _valid_easy_korean_content(),
                },
                "done": True,
            },
        )

    port = OllamaGenerationPort(
        base_url="http://localhost:11434",
        model="gemma4:26b-mlx",
        transport=httpx.MockTransport(handle_request),
    )

    port.generate(
        operation="easy_korean",
        payload={},
        response_model=EasyKoreanDraft,
    )

    request_body = json.loads(captured_requests[0].content)
    assert request_body["think"] is False


def test_ollama_adapter_parses_single_json_code_fence() -> None:
    fenced_content = f"```json\n{_valid_easy_korean_content()}\n```"

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gemma4:26b-mlx",
                "message": {"role": "assistant", "content": fenced_content},
                "done": True,
            },
        )

    port = OllamaGenerationPort(
        base_url="http://localhost:11434",
        model="gemma4:26b-mlx",
        transport=httpx.MockTransport(handle_request),
    )

    draft = port.generate(
        operation="easy_korean",
        payload={},
        response_model=EasyKoreanDraft,
    )

    assert draft.requested_items == ("여권 사본",)


def test_ollama_adapter_rejects_wrong_schema_inside_code_fence() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gemma4:26b-mlx",
                "message": {
                    "role": "assistant",
                    "content": '```json\n{"easy_korean_text": "신청하세요"}\n```',
                },
                "done": True,
            },
        )

    port = OllamaGenerationPort(
        base_url="http://localhost:11434",
        model="gemma4:26b-mlx",
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(GenerationSchemaError):
        port.generate(
            operation="easy_korean",
            payload={},
            response_model=EasyKoreanDraft,
        )
