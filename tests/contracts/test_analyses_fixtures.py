# examples/analyses fixture ↔ Pydantic 스키마 roundtrip

from pathlib import Path

import pytest

from app.api.schemas.analyses import AnalysisRequest, AnalysisResponse

_FIXTURES = Path(__file__).resolve().parents[2] / "examples" / "analyses"

_REQUESTS = ("request_plan.json", "request_analyze.json")
_RESPONSES = (
    "response_context_required.json",
    "response_needs_info.json",
    "response_review_required.json",
)


# PLAN/ANALYZE 요청 fixture 역직렬화
@pytest.mark.parametrize("name", _REQUESTS)
def test_analysis_request_fixtures_parse(name: str) -> None:
    raw = (_FIXTURES / name).read_text(encoding="utf-8")
    req = AnalysisRequest.model_validate_json(raw)
    assert req.phase in {"PLAN", "ANALYZE"}
    assert req.analysis_input.instruction


# 성공 outcome 응답 fixture 역직렬화
@pytest.mark.parametrize("name", _RESPONSES)
def test_analysis_response_fixtures_parse(name: str) -> None:
    raw = (_FIXTURES / name).read_text(encoding="utf-8")
    res = AnalysisResponse.model_validate_json(raw)
    assert res.outcome in {"CONTEXT_REQUIRED", "NEEDS_INFO", "REVIEW_REQUIRED"}
    if res.outcome == "REVIEW_REQUIRED":
        assert res.candidates
        assert res.candidates[0].missing_slots == []
    if res.outcome == "NEEDS_INFO":
        assert res.questions
        assert res.candidates == []
    if res.outcome == "CONTEXT_REQUIRED":
        assert res.context_requirement is not None
