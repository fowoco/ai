from pydantic import BaseModel, ConfigDict

from app.agents.language.contracts import (
    LanguageAssistantInput,
    RequestContext,
    WorkerId,
)


class LanguageAssistantHttpRequest(BaseModel):
    """HTTP transport schema accepting shared parent envelope fields (extra='allow')."""

    model_config = ConfigDict(extra="allow")

    worker_id: WorkerId
    preferred_language: str | None = None
    nationality_code: str | None = None
    request_context: RequestContext


def project_http_request(request: LanguageAssistantHttpRequest) -> LanguageAssistantInput:
    """Project loose HTTP transport request to strict domain LanguageAssistantInput."""
    return LanguageAssistantInput(
        worker_id=request.worker_id,
        preferred_language=request.preferred_language,
        nationality_code=request.nationality_code,
        request_context=request.request_context,
    )


__all__ = [
    "LanguageAssistantHttpRequest",
    "project_http_request",
]
