import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import httpx

from app.ocr.models import ClovaProviderError, ClovaTimeoutError, OcrFile

_FORMAT_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
}


class ClovaTemplateOcrClient:
    def __init__(
        self,
        invoke_url: str,
        secret: str,
        timeout_seconds: float,
        client: httpx.AsyncClient,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        self._invoke_url = invoke_url
        self._secret = secret
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._max_response_bytes = max_response_bytes

    async def infer(
        self,
        file: OcrFile,
        template_ids: tuple[int, ...],
        request_id: UUID,
    ) -> dict[str, Any]:
        message = {
            "version": "V2",
            "requestId": str(request_id),
            "timestamp": _unix_time_milliseconds(),
            "images": [
                {
                    "format": _FORMAT_BY_CONTENT_TYPE.get(file.content_type, "png"),
                    "name": file.filename,
                    "templateIds": list(template_ids),
                }
            ],
        }
        request = self._client.build_request(
            "POST",
            self._invoke_url,
            headers={"X-OCR-SECRET": self._secret},
            files={
                "message": (
                    None,
                    json.dumps(message, ensure_ascii=False, separators=(",", ":")),
                    "application/json",
                ),
                "file": (file.filename, file.content, file.content_type),
            },
            timeout=self._timeout_seconds,
        )

        try:
            response = await self._client.send(
                request,
                stream=True,
                follow_redirects=False,
            )
            try:
                response_body = await self._read_response(response)
            finally:
                await response.aclose()
        except httpx.TimeoutException as exc:
            raise ClovaTimeoutError("CLOVA request timed out") from exc
        except httpx.RequestError as exc:
            raise ClovaProviderError("CLOVA request failed") from exc

        try:
            decoded = json.loads(response_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ClovaProviderError("CLOVA returned an invalid response") from exc
        if not isinstance(decoded, Mapping):
            raise ClovaProviderError("CLOVA returned an invalid response")
        images = decoded.get("images")
        if isinstance(images, list) and any(
            isinstance(image, Mapping) and image.get("inferResult") == "ERROR"
            for image in images
        ):
            raise ClovaProviderError("CLOVA reported a recognition error")
        return dict(decoded)

    async def _read_response(self, response: httpx.Response) -> bytes:
        if not 200 <= response.status_code < 300:
            raise ClovaProviderError("CLOVA returned an unexpected status")

        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > self._max_response_bytes:
                    raise ClovaProviderError("CLOVA response is too large")
            except ValueError:
                pass

        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self._max_response_bytes:
                raise ClovaProviderError("CLOVA response is too large")
            chunks.append(chunk)
        return b"".join(chunks)


def _unix_time_milliseconds() -> int:
    from time import time

    return int(time() * 1000)
