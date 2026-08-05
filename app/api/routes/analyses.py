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
    summary="자연어 지시 분석 (PLAN / ANALYZE)",
    description=(
        "phase=PLAN 이면 Intent 분류 후 CONTEXT_REQUIRED(requiredFieldKeys) 반환. "
        "phase=ANALYZE 이면 DB 보충값으로 NEEDS_INFO(questions) 또는 REVIEW_REQUIRED(candidates). "
        "HTTP는 requestId·phase·analysisInput만. Bearer(#8)."
    ),
    dependencies=[Depends(verify_internal_bearer)],
)
# PLAN/ANALYZE 분기 → Server 계약 outcome 응답
async def analyze(
    request: AnalysisRequest,
    pipeline: AnalysisPipeline = Depends(get_analysis_pipeline),  # noqa: B008
) -> AnalysisResponse:
    return pipeline.run(request)
