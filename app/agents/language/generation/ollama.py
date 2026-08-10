import json
from collections.abc import Mapping

import httpx

from app.agents.language.generation.models import DraftT
from app.agents.language.generation.openai_compatible import (
    GenerationError,
    GenerationHTTPError,
    GenerationResponseTooLargeError,
    GenerationSchemaError,
    GenerationTransportError,
    _sanitize_payload,
)
from app.agents.language.ports import GenerationOperation, StructuredGenerationPort
from app.agents.language.resources.prompts import load_prompt


def _strip_single_json_code_fence(content: str) -> str:
    stripped = content.strip()
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        return stripped
    if lines[0].strip().lower() not in {"```", "```json"}:
        return stripped
    return "\n".join(lines[1:-1]).strip()


class OllamaGenerationPort(StructuredGenerationPort):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        native_base_url = base_url.rstrip("/")
        if native_base_url.endswith("/v1"):
            native_base_url = native_base_url[:-3]
        self.base_url = native_base_url
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def get_system_prompt(self, operation: GenerationOperation) -> str:
        return load_prompt(operation)

    def generate(
        self,
        *,
        operation: GenerationOperation,
        payload: Mapping[str, object],
        response_model: type[DraftT],
    ) -> DraftT:
        json_schema = response_model.model_json_schema(mode="validation")
        required_fields = json_schema.get("required", [])
        required_instruction = json.dumps(required_fields, ensure_ascii=False)
        system_prompt = (
            f"{self.get_system_prompt(operation)}\n"
            f"Required JSON keys: {required_instruction}. Return every required key."
        )
        safe_payload = _sanitize_payload(payload)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False)},
            ],
            "stream": False,
            "format": json_schema,
            "options": {"temperature": 0},
        }
        url = f"{self.base_url}/api/chat"
        last_error: Exception | None = None

        for attempt in range(1, 3):
            try:
                with httpx.Client(
                    transport=self._transport,
                    timeout=httpx.Timeout(self.timeout_seconds),
                ) as client:
                    response = client.post(url, headers=headers, json=request_body)

                if len(response.content) > 1_048_576:
                    raise GenerationResponseTooLargeError(
                        "Response content exceeds 1 MiB limit"
                    )

                if response.status_code == 200:
                    try:
                        response_json = response.json()
                        content = response_json.get("message", {}).get("content")
                        if not isinstance(content, str):
                            raise GenerationSchemaError(
                                "Content is missing or not a string"
                            )
                    except (json.JSONDecodeError, AttributeError) as err:
                        raise GenerationSchemaError(
                            f"Invalid Ollama response wrapper: {err}"
                        ) from err

                    normalized_content = _strip_single_json_code_fence(content)
                    try:
                        return response_model.model_validate_json(normalized_content)
                    except Exception as err:
                        raise GenerationSchemaError(
                            f"Model validation error for {response_model.__name__}: {err}"
                        ) from err

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = GenerationTransportError(
                        f"HTTP transport status {response.status_code}"
                    )
                    if attempt < 2:
                        continue
                    raise last_error

                raise GenerationHTTPError(
                    f"HTTP generation request failed with status {response.status_code}"
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as err:
                last_error = GenerationTransportError(
                    f"Network transport error: {type(err).__name__}"
                )
                if attempt < 2:
                    continue
                raise last_error from None

        if last_error:
            raise last_error
        raise GenerationError("Unknown generation failure")


__all__ = ["OllamaGenerationPort"]
