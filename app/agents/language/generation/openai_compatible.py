import json
import logging
import re
from collections.abc import Mapping
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.agents.language.generation.models import DraftT
from app.agents.language.observability import sanitize_user_input
from app.agents.language.ports import GenerationOperation, StructuredGenerationPort
from app.agents.language.resources.prompts import load_prompt

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

_SAFE_PROVIDER_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def _sanitize_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """페이로드 문자열 값에서 프롬프트 인젝션 패턴 제거.

    LLM 전송 직전 최후 방어선 — 상위 레이어 sanitize 실패 시에도 보호.
    """
    result: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            result[key] = sanitize_user_input(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_user_input(item) if isinstance(item, str) else item for item in value
            ]
        else:
            result[key] = value
    return result


class GenerationError(Exception):
    """Base exception for generation errors."""

    code = "GENERATION_FAILED"

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id


class GenerationHTTPError(GenerationError):
    """Raised for non-retryable HTTP error statuses (e.g. 400, 401, 403, 404)."""

    def __init__(
        self,
        *,
        status_code: int,
        provider_error_code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        if status_code == 400:
            self.code = "PROVIDER_REQUEST_INVALID"
        elif status_code in (401, 403):
            self.code = "PROVIDER_AUTH_FAILED"
        else:
            self.code = "PROVIDER_HTTP_ERROR"
        self.status_code = status_code
        self.provider_error_code = provider_error_code
        provider_suffix = f" provider_code={provider_error_code}" if provider_error_code else ""
        super().__init__(
            f"HTTP generation request failed with status {status_code}{provider_suffix}",
            request_id=request_id,
        )


class GenerationTransportError(GenerationError):
    """Raised for retryable transport errors (429, 5xx, timeouts)."""

    code = "PROVIDER_UNAVAILABLE"


class GenerationSchemaError(GenerationError):
    """Raised when LLM output violates JSON schema or contract."""

    code = "STRUCTURED_OUTPUT_INVALID"


class GenerationRefusalError(GenerationError):
    """Raised when the provider explicitly refuses a structured-output request."""

    code = "PROVIDER_REFUSED"


class GenerationResponseTooLargeError(GenerationError):
    """Raised when response body exceeds 1 MiB size cap."""

    code = "PROVIDER_RESPONSE_TOO_LARGE"


def _request_id(response: httpx.Response) -> str | None:
    value = response.headers.get("x-request-id")
    if value and _SAFE_PROVIDER_CODE.fullmatch(value):
        return value
    return None


def _provider_error_code(response: httpx.Response) -> str | None:
    """Extract only a bounded provider error identifier, never the raw error body."""
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    for key in ("code", "type"):
        value = error.get(key)
        if isinstance(value, str) and _SAFE_PROVIDER_CODE.fullmatch(value):
            return value
    return None


def _log_generation_failure(
    *,
    operation: GenerationOperation,
    model: str,
    error: GenerationError,
) -> None:
    """Emit metadata only; prompts, response bodies and credentials stay excluded."""
    logger.warning(
        "structured_generation_failed operation=%s model=%s error_code=%s "
        "error_type=%s provider_request_id=%s",
        operation,
        model,
        error.code,
        type(error).__name__,
        error.request_id or "unavailable",
    )


class OpenAICompatibleGenerationPort(StructuredGenerationPort):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        model: str,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def get_system_prompt(self, operation: GenerationOperation) -> str:
        """Retrieve versioned system prompt for the given operation."""
        return load_prompt(operation)

    def generate(
        self,
        *,
        operation: GenerationOperation,
        payload: Mapping[str, object],
        response_model: type[DraftT],
    ) -> DraftT:
        system_prompt = self.get_system_prompt(operation)
        # T14: 프롬프트 인젝션 최후 방어선 — 페이로드 문자열 값 sanitize
        safe_payload = _sanitize_payload(payload)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        json_schema = response_model.model_json_schema(mode="validation")
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": json_schema,
                },
            },
        }

        url = f"{self.base_url}/chat/completions"
        max_attempts = 2
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(
                    transport=self._transport,
                    timeout=httpx.Timeout(self.timeout_seconds),
                ) as client:
                    response = client.post(url, headers=headers, json=request_body)

                if len(response.content) > 1_048_576:
                    raise GenerationResponseTooLargeError("Response content exceeds 1 MiB limit")

                if response.status_code == 200:
                    request_id = _request_id(response)
                    try:
                        resp_json = response.json()
                        choices = resp_json.get("choices", [])
                        if not choices or not isinstance(choices, list):
                            raise GenerationSchemaError(
                                "Missing or invalid choices in response",
                                request_id=request_id,
                            )
                        message = choices[0].get("message", {})
                        if not isinstance(message, dict):
                            raise GenerationSchemaError(
                                "Message is missing or not an object",
                                request_id=request_id,
                            )
                        refusal = message.get("refusal")
                        if isinstance(refusal, str) and refusal.strip():
                            raise GenerationRefusalError(
                                "Provider refused the structured-output request",
                                request_id=request_id,
                            )
                        content = message.get("content")
                        if not isinstance(content, str):
                            raise GenerationSchemaError(
                                "Content is missing or not a string",
                                request_id=request_id,
                            )
                    except (json.JSONDecodeError, AttributeError) as err:
                        raise GenerationSchemaError(
                            f"Invalid completion JSON wrapper: {type(err).__name__}",
                            request_id=request_id,
                        ) from err

                    try:
                        return response_model.model_validate_json(content)
                    except Exception as err:
                        raise GenerationSchemaError(
                            f"Model validation error for {response_model.__name__}: "
                            f"{type(err).__name__}",
                            request_id=request_id,
                        ) from err

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = GenerationTransportError(
                        f"HTTP transport status {response.status_code}",
                        request_id=_request_id(response),
                    )
                    if attempt < max_attempts:
                        continue
                    _log_generation_failure(
                        operation=operation,
                        model=self.model,
                        error=last_error,
                    )
                    raise last_error

                http_error = GenerationHTTPError(
                    status_code=response.status_code,
                    provider_error_code=_provider_error_code(response),
                    request_id=_request_id(response),
                )
                _log_generation_failure(
                    operation=operation,
                    model=self.model,
                    error=http_error,
                )
                raise http_error

            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as err:
                last_error = GenerationTransportError(
                    f"Network transport error: {type(err).__name__}"
                )
                if attempt < max_attempts:
                    continue
                _log_generation_failure(
                    operation=operation,
                    model=self.model,
                    error=last_error,
                )
                raise last_error from None

        if last_error:
            raise last_error
        raise GenerationError("Unknown generation failure")


__all__ = [
    "GenerationError",
    "GenerationHTTPError",
    "GenerationRefusalError",
    "GenerationResponseTooLargeError",
    "GenerationSchemaError",
    "GenerationTransportError",
    "OpenAICompatibleGenerationPort",
]
