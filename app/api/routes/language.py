from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.agents.language.codes import (
    UnsupportedPreferredLanguageError,
    resolve_target_language,
)
from app.agents.language.contracts import LanguageAssistantOutput
from app.agents.language.service import LanguageAssistantService
from app.api.dependencies import get_language_assistant_service
from app.api.openapi import LANGUAGE_ASSISTANT_TAG
from app.api.schemas.language import (
    LanguageAssistantHttpRequest,
    project_http_request,
)

router = APIRouter(prefix="/internal/v1", tags=[LANGUAGE_ASSISTANT_TAG])


@router.post("/language-assistant", response_model=LanguageAssistantOutput)
async def generate_language_message(
    request: LanguageAssistantHttpRequest,
    service: Annotated[LanguageAssistantService, Depends(get_language_assistant_service)],
) -> LanguageAssistantOutput:
    """Generate structured Standard/Easy Korean & Native Translation for foreign worker."""
    try:
        if request.preferred_language is not None:
            resolve_target_language(request.preferred_language, request.nationality_code)
        strict_input = project_http_request(request)
        return await run_in_threadpool(service.invoke, strict_input)
    except UnsupportedPreferredLanguageError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "preferred_language"],
                    "msg": "unsupported preferred language",
                    "type": "value_error.language_code",
                }
            ],
        ) from exc


__all__ = ["router"]
