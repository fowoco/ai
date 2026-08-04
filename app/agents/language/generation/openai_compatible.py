import json
from collections.abc import Mapping
from typing import TypeVar

import httpx
from pydantic import BaseModel

from app.agents.language.generation.models import DraftT
from app.agents.language.ports import GenerationOperation, StructuredGenerationPort
from app.agents.language.resources.prompts import load_prompt

T = TypeVar("T", bound=BaseModel)


class GenerationError(Exception):
    """Base exception for generation errors."""


class GenerationHTTPError(GenerationError):
    """Raised for non-retryable HTTP error statuses (e.g. 400, 401, 403, 404)."""


class GenerationTransportError(GenerationError):
    """Raised for retryable transport errors (429, 5xx, timeouts)."""


class GenerationSchemaError(GenerationError):
    """Raised when LLM output violates JSON schema or contract."""


class GenerationResponseTooLargeError(GenerationError):
    """Raised when response body exceeds 1 MiB size cap."""


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

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        json_schema = response_model.model_json_schema(mode="validation")
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0,
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
                    try:
                        resp_json = response.json()
                        choices = resp_json.get("choices", [])
                        if not choices or not isinstance(choices, list):
                            raise GenerationSchemaError("Missing or invalid choices in response")
                        content = choices[0].get("message", {}).get("content")
                        if not isinstance(content, str):
                            raise GenerationSchemaError("Content is missing or not a string")
                    except (json.JSONDecodeError, AttributeError) as err:
                        raise GenerationSchemaError(
                            f"Invalid completion JSON wrapper: {err}"
                        ) from err

                    try:
                        return response_model.model_validate_json(content)
                    except Exception as err:
                        raise GenerationSchemaError(
                            f"Model validation error for {response_model.__name__}: {err}"
                        ) from err

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = GenerationTransportError(
                        f"HTTP transport status {response.status_code}"
                    )
                    if attempt < max_attempts:
                        continue
                    raise last_error

                raise GenerationHTTPError(
                    f"HTTP generation request failed with status {response.status_code}"
                )

            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as err:
                last_error = GenerationTransportError(
                    f"Network transport error: {type(err).__name__}"
                )
                if attempt < max_attempts:
                    continue
                raise last_error from None

        if last_error:
            raise last_error
        raise GenerationError("Unknown generation failure")


__all__ = [
    "GenerationError",
    "GenerationHTTPError",
    "GenerationResponseTooLargeError",
    "GenerationSchemaError",
    "GenerationTransportError",
    "OpenAICompatibleGenerationPort",
]
