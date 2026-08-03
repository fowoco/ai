# POST /internal/v1/analyses — Server가 호출하는 핵심 분석 API

from fastapi import APIRouter, Depends

from app.agents.pipeline import AnalysisPipeline
from app.api.dependencies import get_analysis_pipeline
from app.api.openapi import ANALYSES_TAG
from app.api.schemas.analyses import AnalysisRequest, AnalysisResponse
from app.api.security import verify_internal_bearer

router = APIRouter(prefix="/internal/v1", tags=[ANALYSES_TAG])


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    summary="자연어 지시 분석",
    description=(
        "Server가 analysisInput(instruction·WorkerContext·requestedFields)을 보내면 "
        "Intent 분류, Slot 추출, 모호성 검사 후 candidate 목록 반환. "
        "requestId/attemptId·Bearer(#8). 응답은 Server strict JSON 계약 필드만."
    ),
    dependencies=[Depends(verify_internal_bearer)],
)
# 지시문 분석 → Intent·Slot·누락 정보 서버 응답
async def analyze(
    request: AnalysisRequest,
    pipeline: AnalysisPipeline = Depends(get_analysis_pipeline),  # noqa: B008
) -> AnalysisResponse:
    return pipeline.run(request)
