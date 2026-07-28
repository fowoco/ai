"""POST /internal/v1/analyses — Server가 호출하는 핵심 분석 API."""

from fastapi import APIRouter, Depends

from app.agents.pipeline import AnalysisPipeline
from app.api.dependencies import get_analysis_pipeline
from app.api.openapi import ANALYSES_TAG
from app.api.schemas.analyses import AnalysisRequest, AnalysisResponse

router = APIRouter(prefix="/internal/v1", tags=[ANALYSES_TAG])


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    summary="자연어 지시 분석",
    description=(
        "Server가 PII-마스킹된 지시문을 보내면 Intent 분류, Slot 추출, "
        "모호성 검사를 수행하고 candidate 목록을 반환한다."
    ),
)
async def analyze(
    request: AnalysisRequest,
    pipeline: AnalysisPipeline = Depends(get_analysis_pipeline),  # noqa: B008
) -> AnalysisResponse:
    return pipeline.run(request)
