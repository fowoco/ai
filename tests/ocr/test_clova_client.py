import json
from uuid import UUID

import httpx
import pytest

from app.ocr.clova_client import ClovaTemplateOcrClient
from app.ocr.models import ClovaProviderError, ClovaTimeoutError, OcrFile

REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def sample_file() -> OcrFile:
    return OcrFile(
        filename="sample.png",
        content_type="image/png",
        content=b"synthetic-image-bytes",
    )


@pytest.mark.asyncio
async def test_sends_authenticated_v2_multipart_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["X-OCR-SECRET"] == "local-test-secret"
        assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
        body = await request.aread()
        assert b'"version":"V2"' in body
        assert b'"requestId":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"' in body
        assert b'"format":"png"' in body
        assert b'"templateIds":[43024,43025]' in body
        assert b"sample.png" in body
        assert b"synthetic-image-bytes" in body
        return httpx.Response(200, json={"images": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ClovaTemplateOcrClient(
            invoke_url="https://example.invalid/infer",
            secret="local-test-secret",
            timeout_seconds=30.0,
            client=http_client,
            max_response_bytes=1_048_576,
        )

        result = await client.infer(sample_file(), (43024, 43025), REQUEST_ID)

    assert result == {"images": []}


@pytest.mark.asyncio
async def test_timeout_raises_safe_timeout_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider took too long", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ClovaTemplateOcrClient(
            "https://example.invalid/infer", "secret-value", 0.1, http_client
        )
        with pytest.raises(ClovaTimeoutError, match="timed out") as exc:
            await client.infer(sample_file(), (43019,), REQUEST_ID)

    assert "secret-value" not in str(exc.value)


@pytest.mark.asyncio
async def test_network_error_raises_safe_provider_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot connect", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ClovaTemplateOcrClient(
            "https://example.invalid/infer", "secret-value", 30.0, http_client
        )
        with pytest.raises(ClovaProviderError, match="request failed"):
            await client.infer(sample_file(), (43019,), REQUEST_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [302, 500])
async def test_non_success_http_status_raises_without_response_body(status_code: int) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            headers={"Location": "https://other.invalid"},
            text="sensitive-provider-body",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ClovaTemplateOcrClient(
            "https://example.invalid/infer", "secret-value", 30.0, http_client
        )
        with pytest.raises(ClovaProviderError, match="unexpected status") as exc:
            await client.infer(sample_file(), (43019,), REQUEST_ID)

    assert "sensitive-provider-body" not in str(exc.value)
    assert "secret-value" not in str(exc.value)


@pytest.mark.asyncio
async def test_oversized_response_is_rejected_before_json_decode() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{" + (b"x" * 128))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ClovaTemplateOcrClient(
            "https://example.invalid/infer",
            "secret-value",
            30.0,
            http_client,
            max_response_bytes=64,
        )
        with pytest.raises(ClovaProviderError, match="too large"):
            await client.infer(sample_file(), (43019,), REQUEST_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_content",
    [b"not-json", json.dumps([{"images": []}]).encode()],
)
async def test_invalid_json_object_response_is_rejected(response_content: bytes) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=response_content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ClovaTemplateOcrClient(
            "https://example.invalid/infer", "secret-value", 30.0, http_client
        )
        with pytest.raises(ClovaProviderError, match="invalid response"):
            await client.infer(sample_file(), (43019,), REQUEST_ID)


@pytest.mark.asyncio
async def test_http_success_with_inference_error_is_a_provider_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "images": [
                    {
                        "inferResult": "ERROR",
                        "message": "sensitive-provider-message",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ClovaTemplateOcrClient(
            "https://example.invalid/infer", "secret-value", 30.0, http_client
        )
        with pytest.raises(ClovaProviderError, match="recognition error") as exc:
            await client.infer(sample_file(), (43019,), REQUEST_ID)

    assert "sensitive-provider-message" not in str(exc.value)
