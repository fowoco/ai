from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.agents.intent import IntentClassifier
from app.api.dependencies import get_intent_agent
from app.api.openapi import HEALTH_TAG
from app.api.schemas.analyses import IntentRuntimeStatus
from app.api.security import verify_internal_bearer

router = APIRouter(tags=[HEALTH_TAG])


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="AI Agent 프로세스 liveness",
    description="모델 상태와 무관하게 FastAPI 프로세스가 응답 가능한지 확인합니다.",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/internal/v1/health/ready",
    response_model=IntentRuntimeStatus,
    summary="AI Agent Intent readiness",
    description="BERT와 활성 A.X warmup이 끝난 경우에만 200을 반환합니다.",
    responses={503: {"description": "Intent 모델이 아직 준비되지 않음"}},
    dependencies=[Depends(verify_internal_bearer)],
)
async def readiness(
    response: Response,
    intent_agent: IntentClassifier = Depends(get_intent_agent),  # noqa: B008
) -> IntentRuntimeStatus:
    runtime_status = IntentRuntimeStatus.model_validate(
        intent_agent.runtime_status()
    )
    if not runtime_status.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return runtime_status
